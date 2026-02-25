import docker
from docker.errors import DockerException, APIError
import tarfile
import io
import re
import time
import os

# Лимиты для Docker-контейнера
CONTAINER_TIMEOUT = 150       # секунд на выполнение
CONTAINER_MEM_LIMIT = "128m" # RAM контейнера
CONTAINER_CPU_QUOTA = 100000  # 100% одного ядра (из 100000)
OUTPUT_MAX_BYTES = 65536     # 64 KB макс. вывода

# Runner-скрипт: замер CPU-времени и памяти решения через resource.getrusage
# Запускает solution.py через exec() в том же процессе,
# замеряет память через ru_maxrss (нулевой overhead, в отличие от tracemalloc)
RUNNER_PY = '''\
import sys, os, io, time, resource

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


def run_code_in_docker(code, input_data, extra_files=None):
    """
    Запускает код в Docker-контейнере через runner.py wrapper.
    extra_files: словарь {'filename': content} дополнительных файлов (например, input.txt)
    Возвращает (output, error_message, cpu_time_ms, memory_kb).
    """
    container = None
    try:
        # Пытаемся подключиться к Docker
        try:
            client = docker.from_env()
            client.ping()
        except (DockerException, APIError) as e:
            error_msg = str(e)
            if "CreateFile" in error_msg or "Не удается найти указанный файл" in error_msg:
                return None, "Ошибка: Docker не запущен. Пожалуйста, запустите Docker Desktop и попробуйте снова.", None, None
            elif "Connection refused" in error_msg or "connection" in error_msg.lower():
                return None, "Ошибка: Не удается подключиться к Docker. Убедитесь, что Docker Desktop запущен.", None, None
            else:
                return None, f"Ошибка подключения к Docker: {error_msg}", None, None

        # 1. Создаем контейнер с ограничениями CPU и памяти
        container = client.containers.run(
            "python:3.11-slim",
            command=f"sleep {CONTAINER_TIMEOUT}",
            detach=True,
            mem_limit=CONTAINER_MEM_LIMIT,
            cpu_quota=CONTAINER_CPU_QUOTA,
            network_disabled=True,
            working_dir="/app"
        )

        # 2. Подготавливаем файлы: solution.py + runner.py + extra
        files_to_send = {
            'solution.py': code,
            'runner.py': RUNNER_PY,
        }
        if extra_files:
            files_to_send.update(extra_files)

        # 3. Закидываем архив с файлами
        tar_stream = create_tar_from_files(files_to_send)
        container.put_archive("/app/", tar_stream)

        # 4. Запускаем через runner.py (demux=True для раздельного stdout/stderr)
        safe_input = input_data.replace('\\', '\\\\').replace('"', '\\"')
        command = f'sh -c "printf \\"{safe_input}\\" | python runner.py"'

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
            return output, f"Ошибка выполнения (Exit code {exit_code}):\n{combined}", cpu_time_ms, memory_kb

        return output, None, cpu_time_ms, memory_kb

    except (DockerException, APIError) as e:
        error_msg = str(e)
        if "CreateFile" in error_msg or "Не удается найти указанный файл" in error_msg:
            return None, "Ошибка: Docker не запущен. Пожалуйста, запустите Docker Desktop и попробуйте снова.", None, None
        elif "Connection refused" in error_msg or "connection" in error_msg.lower():
            return None, "Ошибка: Не удается подключиться к Docker. Убедитесь, что Docker Desktop запущен.", None, None
        else:
            return None, f"Ошибка Docker: {error_msg}", None, None
    except Exception as e:
        return None, f"Неожиданная ошибка при выполнении кода: {str(e)}", None, None

    finally:
        if container:
            try:
                container.remove(force=True)
            except:
                pass
