"""Переразметка задач ЕГЭ при смене кодификатора.

КИМ пересматривают: тема переезжает с одного номера на другой, а иногда уходит
из экзамена совсем. Справочник заданий чинится повторным seed_ege_tasks, но
задачи в банках остаются висеть на старом номере – и тренировка по заданию
продолжает выдавать задачи снятой темы. Эта команда правит именно их.

    # тема переехала с задания 2 на задание 5
    python manage.py retag_ege --from 2 --to 5 --dry-run
    python manage.py retag_ege --from 2 --to 5

    # тема ушла из экзамена: убрать задачи из выдачи, сохранив статистику
    python manage.py retag_ege --from 2 --archive

    # тема ушла, задачи не нужны совсем
    python manage.py retag_ege --from 2 --delete

Архивация не удаляет ничего: задачи переезжают в служебный квиз с
quiz_type='standard', и отбор в сессию перестаёт их видеть – тренировка берёт
только 'bank'. Ответы учеников, время и solve_rate остаются в базе.

Команда работает и по вариантам, и по банкам: ege_number в варианте – это
позиция задачи в работе, и при смене кодификатора она значит уже другую тему.
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from quizzes.ege_practice import EGE_QUIZ_TYPES
from quizzes.models import PracticeItem, Question, Quiz

ARCHIVE_SLUG = 'ege-archive'
ARCHIVE_TITLE = 'Архив задач ЕГЭ (снятые темы)'


class Command(BaseCommand):
    help = 'Перевешивает, архивирует или удаляет задачи ЕГЭ по номеру задания'

    def add_arguments(self, parser):
        parser.add_argument('--from', type=int, required=True, dest='source',
                            help='Номер задания, задачи которого трогаем (1-27)')
        parser.add_argument('--to', type=int, dest='target',
                            help='Новый номер задания (1-27)')
        parser.add_argument('--archive', action='store_true',
                            help='Убрать задачи из выдачи, сохранив их и статистику')
        parser.add_argument('--delete', action='store_true',
                            help='Удалить задачи вместе с ответами учеников')
        parser.add_argument('--dry-run', action='store_true',
                            help='Показать, что будет сделано, ничего не меняя')

    def handle(self, *args, **options):
        source = options['source']
        target = options['target']
        archive = options['archive']
        delete = options['delete']
        dry_run = options['dry_run']

        if source not in range(1, 28):
            raise CommandError('--from должен быть от 1 до 27')

        chosen = [name for name, flag in
                  (('--to', target is not None), ('--archive', archive), ('--delete', delete))
                  if flag]
        if len(chosen) != 1:
            raise CommandError('Укажите ровно одно действие: --to N, --archive или --delete')

        if target is not None and target not in range(1, 28):
            raise CommandError('--to должен быть от 1 до 27')
        if target == source:
            raise CommandError('--to совпадает с --from, менять нечего')

        questions = Question.objects.filter(
            ege_number=source, quiz__quiz_type__in=EGE_QUIZ_TYPES,
        ).select_related('quiz')
        total = questions.count()

        if not total:
            self.stdout.write(self.style.WARNING(
                f'Задач с номером {source} в банках и вариантах не найдено.'
            ))
            return

        # Ответы учеников – главное, что можно потерять. Считаем до, а не после.
        answered = PracticeItem.objects.filter(
            question__in=questions, answered_at__isnull=False,
        ).count()

        by_quiz = {}
        for question in questions:
            by_quiz.setdefault(question.quiz.title, 0)
            by_quiz[question.quiz.title] += 1

        self.stdout.write(f'Задач с номером {source}: {total}')
        for title, count in sorted(by_quiz.items()):
            self.stdout.write(f'    {count:>4}  {title}')
        self.stdout.write(f'Ответов учеников по ним: {answered}')

        # Операция необратима, если на целевом номере уже что-то лежит: после
        # слияния «свои» и «переехавшие» задачи в базе ничем не отличаются, и
        # обратный retag_ege утащит назад и те, и другие.
        if target is not None:
            occupied = Question.objects.filter(
                ege_number=target, quiz__quiz_type__in=EGE_QUIZ_TYPES,
            ).count()
            if occupied:
                self.stdout.write(self.style.WARNING(
                    f'\nВНИМАНИЕ: на задании {target} уже есть {occupied} задач. '
                    f'После переноса отличить их от переехавших будет нечем, '
                    f'и обратная переразметка вернёт назад все {occupied + total}.\n'
                    f'Если это не то, что нужно, сначала разведите задачи по разным '
                    f'банкам или сделайте дамп базы.'
                ))

        if delete and answered and not dry_run:
            self.stdout.write(self.style.WARNING(
                f'\nВНИМАНИЕ: удаление унесёт {answered} ответов учеников. '
                f'Если статистику надо сохранить, используйте --archive.'
            ))

        if dry_run:
            action = (f'перевесить на задание {target}' if target
                      else 'архивировать' if archive else 'удалить')
            self.stdout.write(self.style.SUCCESS(f'\n[dry-run] Действие: {action}. Ничего не изменено.'))
            return

        with transaction.atomic():
            if target is not None:
                updated = questions.update(ege_number=target)
                message = f'Перевешено на задание {target}: {updated} задач.'

            elif archive:
                archive_quiz, _ = Quiz.objects.get_or_create(
                    slug=ARCHIVE_SLUG,
                    defaults={
                        'title': ARCHIVE_TITLE,
                        # 'standard' – именно то, что убирает задачи из отбора:
                        # ege_practice.bank_queryset берёт только 'bank'.
                        'quiz_type': 'standard',
                        'is_public': False,
                        'max_attempts': 0,
                    },
                )
                updated = questions.update(quiz=archive_quiz)
                message = (f'Архивировано: {updated} задач переехали в «{ARCHIVE_TITLE}». '
                           f'Ответы учеников сохранены.')

            else:
                deleted, _ = questions.delete()
                message = f'Удалено объектов: {deleted} (задачи и связанные с ними записи).'

        self.stdout.write(self.style.SUCCESS(message))

        if target is not None:
            self.stdout.write(
                'Не забудьте поправить название задания в EGE_TASKS '
                '(textbook/management/commands/seed_ege_tasks.py) и перезапустить '
                'seed_ege_tasks --force.'
            )
