"""Пересчёт фактической сложности задач ЕГЭ по решаемости.

Сложность приходит из импорта разметкой источника, и она регулярно врёт: задача,
помеченная «повышенной», может решаться всеми с первого раза. Эта команда считает
долю верных ПЕРВЫХ попыток и записывает её в Question.solve_rate; дальше
Question.effective_difficulty() показывает уже фактический уровень.

Считается первая задача каждого ученика и внутри неё – только первая попытка:
решённая с третьего раза задача лёгкой не была. Открытый ответ («сдался»)
идёт в знаменатель как неудача – он и есть неудача.

    python manage.py recalc_ege_difficulty            # порог 20 попыток
    python manage.py recalc_ege_difficulty --min 5    # для небольшой группы
    python manage.py recalc_ege_difficulty --dry-run
"""
from django.core.management.base import BaseCommand
from django.db.models import Min

from quizzes.models import PracticeItem, Question

DEFAULT_MIN_ATTEMPTS = 20


class Command(BaseCommand):
    help = 'Пересчитывает Question.solve_rate по доле верных первых попыток'

    def add_arguments(self, parser):
        parser.add_argument(
            '--min', type=int, default=DEFAULT_MIN_ATTEMPTS,
            help=f'Минимум учеников, попробовавших задачу (по умолчанию {DEFAULT_MIN_ATTEMPTS})',
        )
        parser.add_argument('--dry-run', action='store_true', help='Показать, ничего не записывая')

    def handle(self, *args, **options):
        min_attempts = options['min']
        dry_run = options['dry_run']

        # Первая попытка каждого ученика по каждой задаче.
        first_ids = (
            PracticeItem.objects
            .filter(answered_at__isnull=False, question__quiz__quiz_type__in=('exam', 'bank'))
            .values('question_id', 'session__user_id')
            .annotate(first_id=Min('id'))
            .values_list('first_id', flat=True)
        )

        outcomes = {}
        for question_id, is_correct, attempts in (
            PracticeItem.objects.filter(id__in=list(first_ids))
            .values_list('question_id', 'is_correct', 'attempts')
        ):
            total, correct = outcomes.get(question_id, (0, 0))
            solved_at_once = bool(is_correct) and attempts <= 1
            outcomes[question_id] = (total + 1, correct + (1 if solved_at_once else 0))

        changed = []
        skipped = 0
        for question_id, (total, correct) in outcomes.items():
            if total < min_attempts:
                skipped += 1
                continue
            changed.append((question_id, round(correct / total, 3)))

        if dry_run:
            for question_id, rate in sorted(changed, key=lambda row: row[1]):
                question = Question.objects.get(pk=question_id)
                self.stdout.write(
                    f'  #{question_id} задание {question.ege_number}: '
                    f'solve_rate {question.solve_rate} → {rate} '
                    f'(сложность {question.difficulty} → '
                    f'{Question(difficulty=question.difficulty, solve_rate=rate).effective_difficulty()})'
                )
        else:
            for question_id, rate in changed:
                Question.objects.filter(pk=question_id).update(solve_rate=rate)

        prefix = '[dry-run] ' if dry_run else ''
        self.stdout.write(self.style.SUCCESS(
            f'{prefix}Пересчитано задач: {len(changed)}. '
            f'Пропущено (меньше {min_attempts} попыток): {skipped}.'
        ))
