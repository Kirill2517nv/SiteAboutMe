"""Прогон кода из статьи – общий для разборов ЕГЭ с файлом данных.

Модуль начинается с `_`, поэтому Django не считает его командой.
"""
import contextlib
import io
import os
import tempfile
from pathlib import Path


def run_solution(code, data_file, data):
    """Запускает `code` на тексте `data` и возвращает напечатанное словами.

    Проверяется тот самый код, который ученик скопирует со страницы, а не
    его пересказ в команде: файл кладётся во временный каталог под именем
    `data_file`, и программа открывает его, как открыла бы у ученика.
    """
    out = io.StringIO()
    cwd = os.getcwd()
    with tempfile.TemporaryDirectory() as tmp:
        Path(tmp, data_file).write_text(data, encoding='utf-8')
        os.chdir(tmp)
        try:
            with contextlib.redirect_stdout(out):
                exec(code, {})
        finally:
            os.chdir(cwd)
    return out.getvalue().split()
