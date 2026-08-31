"""Наполнение выделенных пулов задач ЕГЭ.

Пулов два, и оба живут по одному правилу – задача из пула не попадается
в обычной тренировке:

  * exam (Question.exam_only) – резерв под режим «Экзамен». Контрольная должна
    проверять знание темы, а не память о задачах, прорешанных на тренировках.
  * classroom (Question.classroom_only) – набор для урока. Он одинаков у всех
    учеников, поэтому дома его прорешивать нельзя: иначе на уроке половина
    класса уже знает ответы.

    python manage.py mark_exam_pool --dry-run             # посмотреть, что будет
    python manage.py mark_exam_pool                       # добить резерв до 5
    python manage.py mark_exam_pool --pool classroom      # набрать классный пул
    python manage.py mark_exam_pool --size 8              # другой размер пула
    python manage.py mark_exam_pool --task 17             # только одно задание
    python manage.py mark_exam_pool --reset               # снять флаги и набрать заново

Команда идемпотентна: повторный запуск ничего не меняет, если пул уже полон.
Флаги, расставленные вручную в админке, она не снимает – только добирает
недостающее (кроме режима --reset). Пулы не пересекаются: задача из одного
никогда не попадёт в другой.
"""
import random

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from quizzes.ege_constants import CLASSROOM_POOL_SIZE, EGE_QUIZ_TYPES, EXAM_POOL_SIZE
from quizzes.models import PracticeItem, Question

POOLS = {
    'exam': ('exam_only', 'classroom_only', EXAM_POOL_SIZE, 'резерв'),
    'classroom': ('classroom_only', 'exam_only', CLASSROOM_POOL_SIZE, 'классный набор'),
}


class Command(BaseCommand):
    help = 'Помечает задачи в выделенный пул: exam_only или classroom_only'

    def add_arguments(self, parser):
        parser.add_argument('--pool', choices=sorted(POOLS), default='exam',
                            help='Какой пул наполнять (по умолчанию exam)')
        parser.add_argument('--size', type=int,
                            help='Сколько задач держать в пуле на задание '
                                 f'(по умолчанию {EXAM_POOL_SIZE} для exam, '
                                 f'{CLASSROOM_POOL_SIZE} для classroom)')
        parser.add_argument('--task', type=int,
                            help='Только это задание ЕГЭ (1-27), иначе все')
        parser.add_argument('--reset', action='store_true',
                            help='Снять существующие флаги и набрать резерв заново')
        parser.add_argument('--dry-run', action='store_true',
                            help='Показать план, ничего не меняя')

    def handle(self, *args, **options):
        field, other_field, default_size, label = POOLS[options['pool']]
        size = options['size'] or default_size
        only_task = options['task']
        reset = options['reset']
        dry_run = options['dry_run']

        if size < 1:
            raise CommandError('--size должен быть больше нуля')
        if only_task is not None and only_task not in range(1, 28):
            raise CommandError('--task должен быть от 1 до 27')

        numbers = [only_task] if only_task else list(range(1, 28))
        plan = []

        for number in numbers:
            pool = Question.objects.filter(
                quiz__quiz_type__in=EGE_QUIZ_TYPES, ege_number=number,
            )
            total = pool.count()
            if not total:
                continue

            current = list(pool.filter(**{field: True}).values_list('id', flat=True))
            if reset:
                current = []

            # Свободные задачи – без флага другого пула: пересечение сделало бы
            # классный набор частью экзамена и наоборот.
            #
            # Задачи в связках (19–21) в пулы не берём вовсе. Флаг стоит на одной
            # задаче, а выдаётся связка целиком, поэтому помеченное «только для
            # экзамена» 19-е утекло бы в тренировку вместе с 20-м. Связку целиком
            # в резерв тоже не отправить: она лежит сразу на трёх номерах, и
            # ограничение «не больше половины банка» у каждого своё.
            free = pool.filter(**{field: False, other_field: False}, group_id='')

            # Пул не может съесть банк: в тонкой теме из двух задач пометка
            # обеих оставила бы учебную тренировку вообще без материала.
            cap = total // 2
            need = min(size, cap) - len(current)
            if need <= 0:
                plan.append((number, total, len(current), [], []))
                continue

            # В резерв идут задачи, которых ученики ещё не касались: помечать
            # уже прорешанную значит сразу лишить резерв смысла.
            untouched = list(
                free
                .exclude(id__in=current)
                .exclude(id__in=PracticeItem.objects.values('question_id'))
                .values_list('id', flat=True)
            )
            random.shuffle(untouched)
            chosen = untouched[:need]

            # Если нетронутых не хватило, добираем из остальных – лучше неполный
            # резерв из знакомых задач, чем пустой.
            if len(chosen) < need:
                rest = list(
                    free
                    .exclude(id__in=current + chosen)
                    .values_list('id', flat=True)
                )
                random.shuffle(rest)
                chosen += rest[: need - len(chosen)]

            plan.append((number, total, len(current), chosen, untouched))

        if not plan:
            self.stdout.write(self.style.WARNING('Задач ЕГЭ в банках и вариантах не найдено.'))
            return

        marked = 0
        for number, total, current, chosen, untouched in plan:
            marked += len(chosen)
            status = (f'{label} {current} + {len(chosen)}' if chosen
                      else f'{label} {current}, полон')
            short = ' (нетронутых не хватило)' if chosen and len(untouched) < len(chosen) else ''
            self.stdout.write(f'  задание {number:>2}: {total:>4} задач, {status}{short}')

        if dry_run:
            self.stdout.write(self.style.SUCCESS(
                f'\n[dry-run] Пометили бы {marked} задач. Ничего не изменено.'
            ))
            return

        with transaction.atomic():
            if reset:
                scope = Question.objects.filter(quiz__quiz_type__in=EGE_QUIZ_TYPES)
                if only_task:
                    scope = scope.filter(ege_number=only_task)
                scope.update(**{field: False})

            ids = [qid for _, _, _, chosen, _ in plan for qid in chosen]
            if ids:
                Question.objects.filter(id__in=ids).update(**{field: True})

        self.stdout.write(self.style.SUCCESS(f'\nПомечено задач в пул «{label}»: {marked}.'))
