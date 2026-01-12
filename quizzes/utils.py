import docker
import tarfile
import io
import time

def create_tar_from_string(content, filename):
    """Создает архив tar с одним файлом внутри (из строки)"""
    encoded_content = content.encode('utf-8')
    tar_stream = io.BytesIO()
    
    tar = tarfile.open(fileobj=tar_stream, mode='w')
    
    tarinfo = tarfile.TarInfo(name=filename)
    tarinfo.size = len(encoded_content)
    tarinfo.mtime = time.time()
    
    tar.addfile(tarinfo, io.BytesIO(encoded_content))
    tar.close()
    
    tar_stream.seek(0)
    return tar_stream

def run_code_in_docker(code, input_data):
    """
    Запускает код в Docker-контейнере.
    Возвращает (output, error_message).
    """
    client = docker.from_env()
    
    container = None
    try:
        # 1. Создаем контейнер, который спит, чтобы мы успели закинуть файл
        container = client.containers.run(
            "python:3.11-slim",
            command="sleep 30", 
            detach=True,
            mem_limit="128m",
            network_disabled=True,
            working_dir="/app"
        )
        
        # 2. Закидываем код ученика
        tar_stream = create_tar_from_string(code, "solution.py")
        container.put_archive("/app/", tar_stream)

        # 3. Запускаем код через exec_run
        # Важно: используем демонизацию или просто запускаем python
        # Но exec_run в python-библиотеке docker не умеет красиво слать stdin.
        # Поэтому используем проверенный трюк: echo через sh
        
        # Экранируем input_data:
        # 1. Экранируем слеши
        # 2. Экранируем кавычки
        safe_input = input_data.replace('\\', '\\\\').replace('"', '\\"')
        
        # Команда: printf "input" | python solution.py
        # Используем printf, так как echo в sh может вести себя по-разному с \n
        command = f'sh -c "printf \\"{safe_input}\\" | python solution.py"'
        
        exec_result = container.exec_run(command)
        
        output = exec_result.output.decode('utf-8').strip()
        exit_code = exec_result.exit_code
        
        if exit_code != 0:
            # Если ошибка выполнения (SyntaxError и т.д.)
            # output содержит stderr в том числе
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
