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


def demo_file_link(external_id):
    """Ссылка на файл вопроса демоверсии и имя, под которым он скачивается.

    Адрес не пишется строкой: `QuestionFile.id` на проде свой. Нет вопроса
    или файла – (None, None): разбор читается и без файла, а команда
    предупреждает. Та же функция живёт копиями в seed_ege_theory_24 и 26.
    """
    from django.urls import reverse
    from quizzes.models import QuestionFile

    qf = (QuestionFile.objects
          .filter(question__external_id=external_id)
          .order_by('order', 'id')
          .first())
    if qf is None:
        return None, None
    url = reverse('quizzes:question_file_download', args=[qf.id])
    name = qf.get_filename()
    return f'[{name}]({url})', name
