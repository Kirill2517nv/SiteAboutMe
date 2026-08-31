"""Перенос ручных решений учителя по банку задач ЕГЭ между базами.

В fixtures/bank-*.json задача приходит от парсера: текст, вложения, ответ,
сложность. Чего в json нет – того, что учитель решил уже в приложении:

  * в какой пул положена задача (Question.classroom_only / exam_only);
  * сколько задач этого номера идёт в контрольную (EgeTask.exam_size) и
    сколько нужно решить, чтобы экзамен открылся (exam_unlock_threshold,
    classroom_enabled).

Эти решения не выводятся из json и теряются при переезде на другую базу.
Команда снимает их в отдельный файл и накатывает на другой базе:

    python manage.py ege_pools --dump fixtures/ege-pools.json   # на деве
    python manage.py ege_pools --load fixtures/ege-pools.json --dry-run
    python manage.py ege_pools --load fixtures/ege-pools.json   # на проде

Связка идёт по external_id, потому что id задачи на другой базе будет другой.
Загрузка – полная синхронизация, а не доливка: задача, которой нет в списках
файла, теряет оба флага. Иначе повторный прогон после того, как учитель убрал
задачу из классного набора, оставил бы её в наборе навсегда.
"""
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from quizzes.ege_constants import PRACTICE_QUIZ_TYPES
from quizzes.models import Question
from textbook.models import EgeTask

TASK_FIELDS = ('exam_size', 'exam_unlock_threshold', 'classroom_enabled')


class Command(BaseCommand):
    help = 'Выгружает или накатывает пулы задач ЕГЭ и настройки заданий (external_id)'

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument('--dump', metavar='FILE', help='Записать текущее состояние в файл')
        group.add_argument('--load', metavar='FILE', help='Применить состояние из файла')
        parser.add_argument('--dry-run', action='store_true',
                            help='Только показать, что изменится (с --load)')

    def handle(self, *args, **options):
        if options['dump']:
            self.dump(Path(options['dump']))
        else:
            self.load(Path(options['load']), options['dry_run'])

    def bank(self):
        return Question.objects.filter(quiz__quiz_type__in=PRACTICE_QUIZ_TYPES)

    def dump(self, path):
        data = {
            'tasks': {
                str(t.number): {f: getattr(t, f) for f in TASK_FIELDS}
                for t in EgeTask.objects.order_by('number')
            },
            'classroom': sorted(self.bank().filter(classroom_only=True)
                                .exclude(external_id='')
                                .values_list('external_id', flat=True)),
            'exam_only': sorted(self.bank().filter(exam_only=True)
                                .exclude(external_id='')
                                .values_list('external_id', flat=True)),
        }
        # Задача без external_id связать на другой базе нечем – она бы молча
        # выпала из выгрузки, поэтому о ней говорим вслух.
        orphans = self.bank().filter(external_id='').filter(
            classroom_only=True) | self.bank().filter(external_id='', exam_only=True)
        if orphans.exists():
            self.stderr.write(self.style.WARNING(
                f'{orphans.count()} помеченных задач без external_id – не попали в выгрузку'))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n',
                        encoding='utf-8')
        self.stdout.write(self.style.SUCCESS(
            f'{path}: заданий {len(data["tasks"])}, '
            f'в классе {len(data["classroom"])}, в экзамене {len(data["exam_only"])}'))

    @transaction.atomic
    def load(self, path, dry_run):
        if not path.exists():
            raise CommandError(f'Файл не найден: {path}')
        data = json.loads(path.read_text(encoding='utf-8'))
        classroom = set(data.get('classroom', ()))
        exam_only = set(data.get('exam_only', ()))
        if classroom & exam_only:
            raise CommandError(f'Задача в двух пулах сразу: {sorted(classroom & exam_only)}')

        changed, seen = [], set()
        for q in self.bank().only('id', 'external_id', 'classroom_only', 'exam_only'):
            want_c, want_e = q.external_id in classroom, q.external_id in exam_only
            if want_c or want_e:
                seen.add(q.external_id)
            if (q.classroom_only, q.exam_only) != (want_c, want_e):
                q.classroom_only, q.exam_only = want_c, want_e
                changed.append(q)

        tasks = {t.number: t for t in EgeTask.objects.all()}
        task_changed = []
        for number, values in data.get('tasks', {}).items():
            task = tasks.get(int(number))
            if task is None:
                self.stderr.write(self.style.WARNING(
                    f'Задание {number} не найдено – сначала seed_ege_tasks'))
                continue
            if any(getattr(task, f) != values[f] for f in TASK_FIELDS if f in values):
                for f in TASK_FIELDS:
                    if f in values:
                        setattr(task, f, values[f])
                task_changed.append(task)

        missing = sorted((classroom | exam_only) - seen)
        if missing:
            self.stderr.write(self.style.WARNING(
                f'{len(missing)} external_id из файла нет в банке этой базы: '
                f'{", ".join(missing[:10])}{" …" if len(missing) > 10 else ""}'))

        self.stdout.write(f'Задач сменит пул: {len(changed)}, заданий обновится: {len(task_changed)}')
        if dry_run:
            self.stdout.write(self.style.WARNING('--dry-run: ничего не записано'))
            transaction.set_rollback(True)
            return
        Question.objects.bulk_update(changed, ['classroom_only', 'exam_only'])
        EgeTask.objects.bulk_update(task_changed, list(TASK_FIELDS))
        self.stdout.write(self.style.SUCCESS('Готово'))
