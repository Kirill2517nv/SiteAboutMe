import docker
from docker.errors import DockerException, APIError
import tarfile
import io
import time
import os

# Лимиты для Docker-контейнера
CONTAINER_TIMEOUT = 150       # секунд на выполнение
CONTAINER_MEM_LIMIT = "128m" # RAM контейнера
CONTAINER_CPU_QUOTA = 50000  # 50% одного ядра (из 100000)
OUTPUT_MAX_BYTES = 65536     # 64 KB макс. вывода


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

def run_code_in_docker(code, input_data, extra_files=None):
    """
    Запускает код в Docker-контейнере.
    extra_files: словарь {'filename': content} дополнительных файлов (например, input.txt)
    Возвращает (output, error_message).
    """
    container = None
    try:
        # Пытаемся подключиться к Docker
        try:
            client = docker.from_env()
            # Проверяем, что Docker работает
            client.ping()
        except (DockerException, APIError) as e:
            error_msg = str(e)
            if "CreateFile" in error_msg or "Не удается найти указанный файл" in error_msg:
                return None, "Ошибка: Docker не запущен. Пожалуйста, запустите Docker Desktop и попробуйте снова."
            elif "Connection refused" in error_msg or "connection" in error_msg.lower():
                return None, "Ошибка: Не удается подключиться к Docker. Убедитесь, что Docker Desktop запущен."
            else:
                return None, f"Ошибка подключения к Docker: {error_msg}"
        
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
        
        # 2. Подготавливаем файлы для отправки
        files_to_send = {'solution.py': code}
        
        if extra_files:
            files_to_send.update(extra_files)
            
        # 3. Закидываем архив с файлами
        tar_stream = create_tar_from_files(files_to_send)
        container.put_archive("/app/", tar_stream)

        # 4. Запускаем код
        safe_input = input_data.replace('\\', '\\\\').replace('"', '\\"')
        command = f'sh -c "printf \\"{safe_input}\\" | python solution.py"'
        
        exec_result = container.exec_run(command)

        output = truncate_output(exec_result.output)
        exit_code = exec_result.exit_code

        if exit_code != 0:
            if exit_code == 137:
                return None, "Превышен лимит времени или памяти."
            return output, f"Ошибка выполнения (Exit code {exit_code}):\n{output}"

        return output, None

    except (DockerException, APIError) as e:
        error_msg = str(e)
        if "CreateFile" in error_msg or "Не удается найти указанный файл" in error_msg:
            return None, "Ошибка: Docker не запущен. Пожалуйста, запустите Docker Desktop и попробуйте снова."
        elif "Connection refused" in error_msg or "connection" in error_msg.lower():
            return None, "Ошибка: Не удается подключиться к Docker. Убедитесь, что Docker Desktop запущен."
        else:
            return None, f"Ошибка Docker: {error_msg}"
    except Exception as e:
        return None, f"Неожиданная ошибка при выполнении кода: {str(e)}"
    
    finally:
        if container:
            try:
                container.remove(force=True)
            except:
                pass
