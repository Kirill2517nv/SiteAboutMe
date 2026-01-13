import docker
import tarfile
import io
import time
import os

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
    client = docker.from_env()
    
    container = None
    try:
        # 1. Создаем контейнер
        container = client.containers.run(
            "python:3.11-slim",
            command="sleep 30", 
            detach=True,
            mem_limit="128m",
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
        
        output = exec_result.output.decode('utf-8', errors='replace').strip()
        exit_code = exec_result.exit_code
        
        if exit_code != 0:
            return output, f"Ошибка выполнения (Exit code {exit_code}):\n{output}"
            
        return output, None

    except Exception as e:
        return None, f"Ошибка Docker: {str(e)}"
    
    finally:
        if container:
            try:
                container.remove(force=True)
            except:
                pass
