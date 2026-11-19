"""Переезд на КИМ-2027 в редакции ФИПИ от 13.11.2026 – разовая команда.

Редакция вернула раскладку 2026 года: 10 – поиск в текстовом процессоре (новая
тема), 13 – маска подсети (у нас была на 10), 23 – анализ хода исполнения
алгоритма (была на 13), задача о графах (наша 23) из экзамена ушла. Подробно –
docs/ege-2027-kim-update.md.

Что делает, одной транзакцией:
  1. Банки: графы bank-23 – в архив, bank-13 → 23, bank-10 → 13 (retag_ege
     с --quiz: варианты kompege уже в раскладке 2026, их трогать нельзя).
     Вместе с задачами переезжают сессии тренажёра.
  2. Старый демо variant-fipi-demo-2027 становится новым: исполнитель 13 → 23
     (задача дословно та же, решения учеников остаются при ней), маска
     с прежними числами и графы – в архив, добавляются новые 10 и 13.
  3. Slug-и и названия банков – под новые номера; опустевший bank-23 становится
     архивным квизом (не удаляется: на него ссылаются отправки кода).
  4. Настройки EgeTask (порог экзамена, размер, «задачи для урока», «разобрали
     на уроке») и статьи теории переезжают вместе с темой; статья о графах
     снимается с публикации. Slug-и статей не меняются – на них ссылки.

Перед запуском в MEDIA должны лежать новые файлы ФИПИ (команда проверяет):
  ege/variant-fipi-demo-2027/files/demo_10.odt
  ege/variant-fipi-demo-2027/files/demo_27.txt  – файл редакции 13.11 (ключ 27
      539936 100704 считается по нему; по старому файлу выходило 100666)
После – load_ege банков из fixtures/bank_fipi_demo_2027_11/ и seed_ege_tasks.
"""
import hashlib
import os

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from quizzes.models import Question, QuestionFile, Quiz, TestCase, UserResult
from textbook.models import Article, EgeTask

DEMO = 'variant-fipi-demo-2027'
DONE_MARK = 'fipi-demo-2027-11-10'  # external_id новой задачи 10 – признак, что переезд был
FILES = f'ege/{DEMO}/files'
DEMO_27_MD5 = '80517f8a'  # начало md5 demo_27.txt редакции 13.11.2026
EGE_TASK_FIELDS = ('exam_size', 'classroom_enabled', 'covered')

NEW_10 = (
    'Задание выполняется с использованием прилагаемого файла.\n\n'
    'С помощью текстового редактора определите, сколько раз встречается отдельное слово '
    '«и» или «И» в тексте главы II повести А.И. Куприна «Поединок».\n'
    'В ответе укажите только число.'
)
NEW_13 = (
    'В терминологии сетей TCP/IP маской сети называют двоичное число, которое показывает, '
    'какая часть IP-адреса узла сети относится к адресу сети, а какая – к адресу узла в этой '
    'сети. Адрес сети получается в результате применения поразрядной конъюнкции к заданному '
    'адресу узла и его маске. Широковещательным адресом называется специализированный адрес, '
    'в котором на месте нулей в маске стоят единицы. Адрес сети и широковещательный адрес не '
    'могут быть использованы для адресации сетевых устройств.\n\n'
    'Сеть задана IP-адресом одного из входящих в неё узлов 95.106.135.150 и сетевой маской '
    '255.255.255.0.\nНайдите IP-адрес сети. В ответе укажите сумму числовых значений октетов '
    'найденного IP-адреса.\nНапример, если бы найденный адрес был равен 100.20.3.4, то в ответе '
    'следовало бы записать: 127.'
)


class Command(BaseCommand):
    help = 'Переезд на раскладку КИМ-2027 от 13.11.2026: банки 10→13→23, демо, теория'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help='Выполнить всё и откатить – посмотреть отчёт без изменений')

    def handle(self, *args, dry_run=False, **options):
        if Question.objects.filter(external_id=DONE_MARK).exists():
            self.stdout.write(self.style.WARNING('Переезд уже выполнен – менять нечего.'))
            return
        self._check_media()

        with transaction.atomic():
            self._retag()
            self._demo()
            self._banks()
            self._ege_tasks()
            self._theory()
            if dry_run:
                transaction.set_rollback(True)
                self.stdout.write(self.style.WARNING('\n[dry-run] Всё откачено.'))
                return
        self.stdout.write(self.style.SUCCESS(
            '\nГотово. Дальше: load_ege для fixtures/bank_fipi_demo_2027_11/*.json, '
            'затем seed_ege_tasks --force.'))

    def _check_media(self):
        root = settings.MEDIA_ROOT
        odt = os.path.join(root, FILES, 'demo_10.odt')
        txt = os.path.join(root, FILES, 'demo_27.txt')
        if not os.path.exists(odt):
            raise CommandError(f'Нет {odt} – положите файл ФИПИ до запуска.')
        with open(txt, 'rb') as f:
            if not hashlib.md5(f.read()).hexdigest().startswith(DEMO_27_MD5):
                raise CommandError(f'{txt} – не файл редакции 13.11.2026: ключ 27 не совпадёт.')

    def _retag(self):
        self.stdout.write('== Банки и демо: перенумерация')
        run = call_command
        # Порядок важен: номер освобождается раньше, чем на него переезжают.
        run('retag_ege', '--from', '23', '--archive', '--quiz', 'bank-23', '--quiz', DEMO)
        run('retag_ege', '--from', '10', '--archive', '--quiz', DEMO)
        run('retag_ege', '--from', '13', '--to', '23', '--quiz', 'bank-13', '--quiz', DEMO)
        run('retag_ege', '--from', '10', '--to', '13', '--quiz', 'bank-10')

    def _demo(self):
        self.stdout.write('== Демо-вариант')
        quiz = Quiz.objects.get(slug=DEMO)
        quiz.title = 'ЕГЭ-2027, демонстрационный вариант ФИПИ'
        quiz.description = (
            'Демонстрационный вариант КИМ ЕГЭ 2027 по информатике (ФИПИ, редакция 13.11.2026). '
            'На позициях 14 и 25 в демоверсии несколько примеров – в вариант взят первый, '
            'остальные добавлены в банки заданий.')
        quiz.save(update_fields=['title', 'description'])

        q10 = Question.objects.create(
            quiz=quiz, ege_number=10, title='Задание 10', text=NEW_10, question_type='text',
            correct_text_answer='93', points=1, difficulty=1, external_id=DONE_MARK)
        QuestionFile.objects.create(question=q10, file=f'{FILES}/demo_10.odt',
                                    description='Текст повести', order=0)
        q13 = Question.objects.create(
            quiz=quiz, ege_number=13, title='Задание 13', text=NEW_13, question_type='code',
            points=1, difficulty=2, external_id='fipi-demo-2027-11-13')
        TestCase.objects.create(question=q13, input_data='', output_data='336')

        numbers = sorted(quiz.questions.values_list('ege_number', flat=True))
        if numbers != list(range(1, 28)):
            raise CommandError(f'В демо не 27 позиций по одной: {numbers}')
        self.stdout.write(f'  27 задач, итогов учеников по варианту: '
                          f'{UserResult.objects.filter(quiz=quiz).count()}')

    def _banks(self):
        self.stdout.write('== Банки: slug и названия')
        old23 = Quiz.objects.get(slug='bank-23')
        if old23.questions.exists():
            raise CommandError('В bank-23 остались задачи – архивация не прошла.')
        # Не удалять: на квиз ссылаются отправки кода по графам (CodeSubmission.quiz,
        # CASCADE) – удаление унесло бы их. Квиз уходит из банков в архивный тип.
        old23.slug, old23.quiz_type = 'ege-archive-bank-23-grafy', 'standard'
        old23.title = 'Архив: банк задания 23 (графы, до 13.11.2026)'
        old23.save(update_fields=['slug', 'quiz_type', 'title'])
        self.stdout.write(f'  bank-23 → {old23.slug}')
        for old, new in (('bank-13', 23), ('bank-10', 13)):
            Quiz.objects.filter(slug=old).update(slug=f'bank-{new}', title=f'Банк задач: задание {new}')
            self.stdout.write(f'  {old} → bank-{new}')

    def _ege_tasks(self):
        self.stdout.write('== Настройки заданий')
        tasks = {t.number: t for t in EgeTask.objects.filter(number__in=(10, 13, 23))}
        before = {n: {f: getattr(t, f) for f in EGE_TASK_FIELDS} for n, t in tasks.items()}
        defaults = {f: EgeTask._meta.get_field(f).get_default() for f in EGE_TASK_FIELDS}
        for number, source in ((13, before[10]), (23, before[13]), (10, defaults)):
            for field, value in source.items():
                setattr(tasks[number], field, value)
            tasks[number].save(update_fields=list(EGE_TASK_FIELDS))
            self.stdout.write(f'  {number}: {source}')

    def _theory(self):
        self.stdout.write('== Теория')
        tasks = {t.number: t for t in EgeTask.objects.filter(number__in=(10, 13, 23))}
        moved = {n: list(Article.objects.filter(track='ege', ege_task=tasks[n])) for n in (10, 13, 23)}
        for article in moved[23]:
            article.ege_task, article.is_published = None, False
            article.save(update_fields=['ege_task', 'is_published'])
            self.stdout.write(f'  {article.slug}: снята с публикации')
        for old, new in ((13, 23), (10, 13)):
            for article in moved[old]:
                article.ege_task, article.order = tasks[new], new
                article.save(update_fields=['ege_task', 'order'])
                self.stdout.write(f'  {article.slug}: задание {old} → {new}')
