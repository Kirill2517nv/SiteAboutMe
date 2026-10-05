import docker
from docker.errors import DockerException, APIError
import json
import tarfile
import io
import re
import time
import os

# Лимиты для Docker-контейнера
CONTAINER_TIMEOUT = 120       # секунд на выполнение
CONTAINER_MEM_LIMIT = "128m" # RAM контейнера
CONTAINER_CPU_QUOTA = 100000  # 100% одного ядра (из 100000)
OUTPUT_MAX_BYTES = 65536     # 64 KB макс. вывода
CONTAINER_PIDS_LIMIT = 64    # процессов на контейнер
CONTAINER_FSIZE_LIMIT = 64 * 1024 * 1024  # 64 МБ на файл, который пишет решение

# Рабочий каталог – /tmp, а не собственный /app: контейнер работает от nobody,
# а каталог, созданный ключом working_dir, принадлежит root с правами 755 –
# создать в нём файл ученик бы не смог, и задачи «запиши результат в файл»
# перестали бы решаться. /tmp в образе имеет права 1777.
CONTAINER_WORKDIR = "/tmp"

# Ограничения контейнера с кодом ученика. Внутри песочницы ученик может всё,
# что может Python: создавать файлы, читать их, запускать процессы. Это не
# дыра – solution.py и так исполняется целиком, запрет execve только сломал бы
# запуск самого раннера. Значение имеет не запрет действий, а их потолок:
#   network_disabled – ни выкачать, ни выложить наружу (pip тоже не работает);
#   user=nobody      – запись только в свой каталог, не в /etc и не в корень;
#   cap_drop ALL     – ни одной capability, даже из дефолтного набора Docker;
#   no-new-privileges – setuid-бинарь не поднимет права обратно;
#   pids_limit       – потолок для форк-бомбы: без него `while True: os.fork()`
#                      выедает таблицу процессов всего сервера, а не контейнера.
# Память и CPU ограничены cgroup, контейнер живёт один прогон и сносится в
# finally. Проверено пробой изнутри: CapEff=0, NoNewPrivs=1, запись в /etc и /
# отбита, сеть недоступна, форков не больше лимита.
CONTAINER_SECURITY = {
    "network_disabled": True,
    "user": "nobody",
    "pids_limit": CONTAINER_PIDS_LIMIT,
    "cap_drop": ["ALL"],
    "security_opt": ["no-new-privileges"],
    # Вес в борьбе за CPU (по умолчанию 1024). На свободном сервере проверка идёт
    # с той же скоростью, а в пике ядро уступается gunicorn: на нагрузочном тесте
    # 2026-10-05 шесть контейнеров при равном весе растягивали вход до 55 с.
    "cpu_shares": 256,
}

# Runner-скрипт: замер CPU-времени и памяти решения через resource.getrusage
# Запускает solution.py через exec() в том же процессе,
# замеряет память через ru_maxrss (нулевой overhead, в отличие от tracemalloc)
RUNNER_PY = '''\
import sys, os, io, time, resource, signal

# 0) Потолок на размер файла, который пишет решение. Диск контейнера – это
# верхний слой образа на диске сервера, и цикл записи без условия выхода
# (обычная ошибка в задачах «запиши результат в файл») забивал бы его целиком.
# SIGXFSZ глушим: иначе процесс умирает молча, а так ученик видит привычную
# ошибку «File too large». Потолок на ОДИН файл – тысяча файлов по чуть-чуть
# его обойдёт; суммарную квоту даёт только storage_opt на xfs/pquota, которого
# на обычном overlay2 нет.
signal.signal(signal.SIGXFSZ, signal.SIG_IGN)
resource.setrlimit(resource.RLIMIT_FSIZE, (__FSIZE__, __FSIZE__))

# Сохраняем настоящие потоки — маркеры пойдут сюда
_real_stdout = sys.stdout
_real_stderr = sys.stderr

# 1) Читаем входные данные из pipe и подменяем stdin
input_data = sys.stdin.read()
sys.stdin = io.StringIO(input_data)

# 2) Подменяем stdout — перехватываем вывод solution.py
captured_out = io.StringIO()
sys.stdout = captured_out

# 3) Замеряем базовую память интерпретатора (до запуска решения)
base_mem_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
t0 = time.process_time()

# 4) Выполняем solution.py
exit_code = 0
try:
    exec(open("solution.py").read(), {"__name__": "__main__"})
except SystemExit as e:
    exit_code = e.code if isinstance(e.code, int) else 1
except Exception:
    import traceback
    traceback.print_exc(file=_real_stderr)
    exit_code = 1

# 5) Замеряем метрики
cpu_ms = (time.process_time() - t0) * 1000
peak_mem_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
mem_kb = max(0, peak_mem_kb - base_mem_kb)

# 6) Выводим перехваченный stdout решения в настоящий stdout
_real_stdout.write(captured_out.getvalue())
_real_stdout.flush()

# 7) Пишем маркеры метрик в stderr
print(f"__CPU_TIME_MS__:{cpu_ms:.3f}", file=_real_stderr)
print(f"__MEMORY_KB__:{mem_kb}", file=_real_stderr)

sys.exit(exit_code)
'''

# Раннер – обычная строка, а не f-строка: внутри него свои фигурные скобки
# (f"__CPU_TIME_MS__:{cpu_ms:.3f}"), поэтому число подставляем заменой.
RUNNER_PY = RUNNER_PY.replace('__FSIZE__', str(CONTAINER_FSIZE_LIMIT))

# C++. Граница безопасности та же, что у Python, – контейнер, а не язык:
# выход за массив в C++ задевает только память своего процесса (её изолирует
# ядро), а дальше процесса всё упирается в те же nobody / cap_drop / без сети.
# Нового тут два этапа: компиляция (один раз на отправку, отдельным
# контейнером с запасом памяти – g++ на <bits/stdc++.h> берёт 200+ МБ) и
# запуск бинарника в контейнере каждого теста, как обычно.
CPP_IMAGE = "site-sandbox-cpp"  # docker/sandbox-cpp/Dockerfile
# -fno-diagnostics-show-line-numbers: без колонки «5 |» слева от строки с
# ошибкой – ученику она только мешает, а стрелка «^» под ошибкой остаётся.
CPP_COMPILE_CMD = "g++ -std=c++17 -O2 -fno-diagnostics-show-line-numbers -o a.out main.cpp metrics.cpp"

# Метрики C++ меряет сама программа, а не раннер. ru_maxrss ребёнка из
# RUSAGE_CHILDREN наследует пик процесса, который его запустил (exec переносит
# maxrss старого адресного пространства), – и любая программа «весила» ровно
# столько, сколько Python-раннер, ~13 МБ. А utime ребёнка идёт квантами
# планировщика: быстрое решение получало 0 мс. Поэтому так же, как RUNNER_PY:
# прирост памяти (VmHWM − VmRSS на старте) и CPU-время процесса после старта.
# Конструктор с приоритетом 101 – раньше глобальных объектов ученика. Маркеры
# печатаются при нормальном выходе (return из main, exit) – метрики нужны
# только верному решению, а оно завершается нормально.
CPP_METRICS_SRC = r'''
#include <cstdio>
#include <cstring>
#include <ctime>
static long metrics_kb(const char* key) {
    FILE* f = std::fopen("/proc/self/status", "r");
    if (!f) return 0;
    char line[256];
    long kb = 0;
    while (std::fgets(line, sizeof line, f))
        if (!std::strncmp(line, key, std::strlen(key))) { std::sscanf(line + std::strlen(key), "%ld", &kb); break; }
    std::fclose(f);
    return kb;
}
static double metrics_cpu_ms() {
    timespec ts;
    clock_gettime(CLOCK_PROCESS_CPUTIME_ID, &ts);
    return ts.tv_sec * 1000.0 + ts.tv_nsec / 1e6;
}
static long metrics_base_kb;
static double metrics_t0;
__attribute__((constructor(101))) static void metrics_start() {
    metrics_base_kb = metrics_kb("VmRSS:");
    metrics_t0 = metrics_cpu_ms();
}
__attribute__((destructor(101))) static void metrics_stop() {
    long peak = metrics_kb("VmHWM:") - metrics_base_kb;
    std::fprintf(stderr, "__CPU_TIME_MS__:%.3f\n__MEMORY_KB__:%ld\n",
                 metrics_cpu_ms() - metrics_t0, peak > 0 ? peak : 0);
}
'''
CPP_COMPILE_TIMEOUT = 20      # секунд; `timeout` вернёт 124
CPP_COMPILE_MEM_LIMIT = "512m"
# Стек решения. По умолчанию 8 МБ, а рекурсия в задачах ЕГЭ (16, 23) уходит
# на десятки тысяч уровней – segfault на верном алгоритме выглядел бы как
# ошибка ученика. Общий потолок всё равно держит mem_limit контейнера.
CPP_STACK_LIMIT = 64 * 1024 * 1024

# Раннер C++ на Python: бинарник – отдельный процесс, метрики печатает он сам
# (CPP_METRICS_SRC). Лимиты (размер файла, стек) выставляются здесь и
# наследуются ребёнком; SIG_IGN для SIGXFSZ тоже переживает exec.
RUNNER_CPP = '''\
import resource, signal, subprocess, sys

signal.signal(signal.SIGXFSZ, signal.SIG_IGN)
resource.setrlimit(resource.RLIMIT_FSIZE, (__FSIZE__, __FSIZE__))
try:
    _, hard = resource.getrlimit(resource.RLIMIT_STACK)
    soft = __STACK__ if hard == resource.RLIM_INFINITY else min(__STACK__, hard)
    resource.setrlimit(resource.RLIMIT_STACK, (soft, hard))
except (ValueError, OSError):
    pass

# restore_signals=False: иначе Python вернёт ребёнку SIGXFSZ по умолчанию,
# и цикл записи убьёт программу молча вместо ошибки записи.
rc = subprocess.run(["./a.out"], restore_signals=False).returncode
# Смерть от сигнала (rc = -11) – в код возврата, как его даёт shell: 128 + сигнал.
sys.exit(128 - rc if rc < 0 else rc)
'''.replace('__FSIZE__', str(CONTAINER_FSIZE_LIMIT)).replace('__STACK__', str(CPP_STACK_LIMIT))

# Понятный текст для смерти программы от сигнала. Python до такого почти не
# доходит, C++ – постоянно, а «Exit code 139» ученику ничего не говорит.
SIGNAL_MESSAGES = {
    134: "Программа аварийно завершилась (abort): необработанное исключение или нехватка памяти.",
    136: "Арифметическая ошибка: деление на ноль.",
    139: "Segmentation fault: обращение к памяти за пределами массива или переполнение стека (слишком глубокая рекурсия).",
}


def truncate_output(raw_bytes, max_bytes=OUTPUT_MAX_BYTES):
    if len(raw_bytes) < max_bytes:
        return raw_bytes.decode(errors='replace').strip()
    truncated = raw_bytes[:max_bytes].decode(errors='replace').strip()
    dropped = len(raw_bytes) - max_bytes
    return truncated + f"\n\n... Вывод обрезан (отброшено {dropped:,} байт). Ваш код выводит слишком много данных."



def create_tar_from_files(files_dict):
    """
    Создает архив tar с несколькими файлами.
    files_dict: словарь {'filename': b'content_bytes' или 'content_string'}
    """
    tar_stream = io.BytesIO()
    tar = tarfile.open(fileobj=tar_stream, mode='w')
    
    for filename, content in files_dict.items():
        if isinstance(content, str):
            encoded_content = content.encode('utf-8')
        else:
            encoded_content = content
            
        tarinfo = tarfile.TarInfo(name=filename)
        tarinfo.size = len(encoded_content)
        tarinfo.mtime = time.time()
        # Бинарник C++ контейнер запускает от nobody – без бита исполнения отказ.
        tarinfo.mode = 0o755 if filename == 'a.out' else 0o644
        
        tar.addfile(tarinfo, io.BytesIO(encoded_content))
        
    tar.close()
    tar_stream.seek(0)
    return tar_stream

def _parse_metrics(stderr_text):
    """Извлекает CPU-время и память из маркеров runner.py в stderr."""
    cpu_time_ms = None
    memory_kb = None
    if stderr_text:
        m = re.search(r'__CPU_TIME_MS__:([\d.]+)', stderr_text)
        if m:
            cpu_time_ms = float(m.group(1))
        m = re.search(r'__MEMORY_KB__:(\d+)', stderr_text)
        if m:
            memory_kb = int(m.group(1))
    return cpu_time_ms, memory_kb


def _docker_error(e, prefix="Ошибка Docker"):
    error_msg = str(e)
    if "CreateFile" in error_msg or "Не удается найти указанный файл" in error_msg:
        return "Ошибка: Docker не запущен. Пожалуйста, запустите Docker Desktop и попробуйте снова."
    if "Connection refused" in error_msg or "connection" in error_msg.lower():
        return "Ошибка: Не удается подключиться к Docker. Убедитесь, что Docker Desktop запущен."
    return f"{prefix}: {error_msg}"


def _docker_client():
    client = docker.from_env()
    client.ping()
    return client


def compile_code(code, language='python'):
    """
    Готовит программу к запуску: (программа, ошибка).

    Python не компилируется – программа и есть исходник. C++ собирается один
    раз на отправку, а не на каждый тест: компиляция стоит секунды, прогон
    бинарника – миллисекунды. Ошибка компиляции возвращается текстом g++.
    """
    if language != 'cpp':
        return code, None

    container = None
    try:
        try:
            client = _docker_client()
        except (DockerException, APIError) as e:
            return None, _docker_error(e, "Ошибка подключения к Docker")

        # Исходник ученика – такой же недоверенный ввод, как и программа:
        # `#include "/dev/urandom"` гоняет компилятор вечно, поэтому те же
        # nobody / без сети / cap_drop, свой таймаут и память.
        container = client.containers.run(
            CPP_IMAGE,
            command=f"sleep {CPP_COMPILE_TIMEOUT + 10}",
            detach=True,
            mem_limit=CPP_COMPILE_MEM_LIMIT,
            cpu_quota=CONTAINER_CPU_QUOTA,
            working_dir=CONTAINER_WORKDIR,
            **CONTAINER_SECURITY,
        )
        container.put_archive(f"{CONTAINER_WORKDIR}/", create_tar_from_files({'main.cpp': code, 'metrics.cpp': CPP_METRICS_SRC}))
        result = container.exec_run(f"timeout {CPP_COMPILE_TIMEOUT} {CPP_COMPILE_CMD}", demux=True)
        raw_stdout, raw_stderr = result.output
        if result.exit_code != 0:
            if result.exit_code in (124, 137):
                return None, "Ошибка компиляции: превышено время или память компилятора."
            log = truncate_output((raw_stdout or b'') + (raw_stderr or b''))
            return None, f"Ошибка компиляции:\n{log}"

        stream, _ = container.get_archive(f"{CONTAINER_WORKDIR}/a.out")
        with tarfile.open(fileobj=io.BytesIO(b''.join(stream))) as tar:
            return tar.extractfile('a.out').read(), None

    except (DockerException, APIError) as e:
        return None, _docker_error(e)
    except Exception as e:
        return None, f"Неожиданная ошибка при компиляции: {str(e)}"
    finally:
        if container:
            try:
                container.remove(force=True)
            except Exception:
                pass


def run_code_in_docker(code, input_data, extra_files=None, language='python'):
    """
    Запускает программу в Docker-контейнере через раннер.
    code: исходник Python или бинарник C++ из compile_code().
    extra_files: словарь {'filename': content} дополнительных файлов (например, input.txt)
    Возвращает (output, error_message, cpu_time_ms, memory_kb).
    """
    container = None
    try:
        # Пытаемся подключиться к Docker
        try:
            client = _docker_client()
        except (DockerException, APIError) as e:
            return None, _docker_error(e, "Ошибка подключения к Docker"), None, None

        # 1. Создаем контейнер с ограничениями CPU и памяти
        container = client.containers.run(
            CPP_IMAGE if language == 'cpp' else "python:3.11-slim",
            command=f"sleep {CONTAINER_TIMEOUT}",
            detach=True,
            mem_limit=CONTAINER_MEM_LIMIT,
            cpu_quota=CONTAINER_CPU_QUOTA,
            working_dir=CONTAINER_WORKDIR,
            **CONTAINER_SECURITY,
        )

        # 2. Подготавливаем файлы: программа + раннер + stdin + extra.
        # Входные данные кладём файлом, а не подставляем в командную строку:
        # printf принимал за опцию данные, начинающиеся с «-» (например,
        # отрицательное число), а также толковал %, $ и обратные слэши.
        if language == 'cpp':
            files_to_send = {'a.out': code, 'runner.py': RUNNER_CPP}
        else:
            files_to_send = {'solution.py': code, 'runner.py': RUNNER_PY}
        files_to_send['stdin.txt'] = input_data or ''
        if extra_files:
            files_to_send.update(extra_files)

        # 3. Закидываем архив с файлами
        tar_stream = create_tar_from_files(files_to_send)
        container.put_archive(f"{CONTAINER_WORKDIR}/", tar_stream)

        # 4. Запускаем через runner.py (demux=True для раздельного stdout/stderr)
        command = 'sh -c "python runner.py < stdin.txt"'

        exec_result = container.exec_run(command, demux=True)
        exit_code = exec_result.exit_code
        raw_stdout, raw_stderr = exec_result.output  # demux=True → tuple

        # Обработка None (demux может вернуть None если нет вывода)
        raw_stdout = raw_stdout or b''
        raw_stderr = raw_stderr or b''

        output = truncate_output(raw_stdout)
        stderr_text = raw_stderr.decode(errors='replace')

        # Парсим метрики из stderr
        cpu_time_ms, memory_kb = _parse_metrics(stderr_text)

        if exit_code != 0:
            if exit_code == 137:
                return None, "Превышен лимит времени или памяти.", cpu_time_ms, memory_kb
            # Ошибка — stderr без маркеров runner.py (чистый вывод ошибки)
            error_output = re.sub(r'__CPU_TIME_MS__:[\d.]+\n?', '', stderr_text)
            error_output = re.sub(r'__MEMORY_KB__:\d+\n?', '', error_output).strip()
            combined = (output + '\n' + error_output).strip() if output else error_output
            title = f"Ошибка выполнения (Exit code {exit_code})"
            if exit_code in SIGNAL_MESSAGES:
                title += f". {SIGNAL_MESSAGES[exit_code]}"
            return output, f"{title}:\n{combined}" if combined else title, cpu_time_ms, memory_kb

        return output, None, cpu_time_ms, memory_kb

    except (DockerException, APIError) as e:
        return None, _docker_error(e), None, None
    except Exception as e:
        return None, f"Неожиданная ошибка при выполнении кода: {str(e)}", None, None

    finally:
        if container:
            try:
                container.remove(force=True)
            except:
                pass


# Экранирование, которым Django пользуется в json_script. json.dumps не трогает
# «<» и «>», поэтому строка «</script>» внутри данных закрывает тег и остаток
# уходит в разметку. В данные страницы попадает и ответ ученика, и его код –
# то есть текст, который пишет он сам, а страницу его сессии открывает учитель.
_JS_JSON_ESCAPES = {ord('<'): '\\u003C', ord('>'): '\\u003E', ord('&'): '\\u0026'}


def js_json(value):
    """JSON, который безопасно вставить в <script> шаблона."""
    return json.dumps(value).translate(_JS_JSON_ESCAPES)
