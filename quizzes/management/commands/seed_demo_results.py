"""Демо-ученики с разными результатами по одному варианту ЕГЭ.

Странице результатов (`/ege/<id>/results/`) нужна таблица, на которой видно
все её состояния сразу: сильный ученик, средний с частичным баллом за 26/27,
слабый, тот, кто не дошёл до конца. Данные создаются теми же моделями, что
пишет настоящая сдача (`UserResult`/`UserAnswer`/`ExamTaskProgress`), поэтому
страница считает их своим обычным путём, а не нарисованными числами.

Повторный прогон перезаписывает результаты и снимки кода этих учеников; чужие
результаты, в том числе учителя, не трогает.
"""
import datetime

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from accounts.models import Profile, StudentGroup
from quizzes.ege_constants import EGE_RECOMMENDED_TIME
from quizzes.ege_scoring import check_answer, expected_answer
from quizzes.models import (
    CodeSubmission, ExamTaskProgress, Quiz, SharedSolution, SolutionLike,
    UserAnswer, UserResult,
)

GROUP_NAME = '11Б (демо)'
PASSWORD = 'demo12345'

# plan: номер задания -> 'ok' | 'wrong' | 'partial1'. Номера, которых нет в плане,
# ученик не открывал: пустой ответ, ноль времени.
STUDENTS = [
    {
        'username': 'demo_anna', 'first': 'Анна', 'last': 'Ковалёва',
        'pace': 0.95,
        'plan': {n: 'ok' for n in range(1, 28) if n not in (12, 24)},
        'code': [(2, 41.0, 9100), (5, 33.0, 8800), (13, 96.0, 11200), (19, 58.0, 9900)],
    },
    {
        'username': 'demo_maksim', 'first': 'Максим', 'last': 'Орлов',
        'pace': 0.8,
        'plan': {
            **{n: 'ok' for n in (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 13, 14, 16,
                                 19, 20, 21, 22, 23, 25, 26)},
            **{n: 'wrong' for n in (12, 15, 17, 18, 24)},
            27: 'partial1',
        },
        'code': [(2, 55.0, 9400), (6, 61.0, 10200)],
    },
    {
        'username': 'demo_sofya', 'first': 'Софья', 'last': 'Никитина',
        'pace': 0.7,
        'plan': {
            **{n: 'ok' for n in (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 13, 15, 19, 20, 22, 24)},
            **{n: 'wrong' for n in (12, 14, 16, 17, 18, 21, 23)},
            26: 'partial1',
        },
        'code': [(2, 88.0, 10800)],
    },
    {
        'username': 'demo_egor', 'first': 'Егор', 'last': 'Васильев',
        'pace': 0.55,
        'plan': {
            **{n: 'ok' for n in (1, 2, 3, 5, 8, 10, 13, 19)},
            **{n: 'wrong' for n in (4, 6, 7, 9, 11, 12, 14, 15, 16)},
        },
    },
    {
        'username': 'demo_polina', 'first': 'Полина', 'last': 'Захарова',
        'pace': 0.45,
        'plan': {
            **{n: 'ok' for n in (1, 3, 7, 9, 22)},
            **{n: 'wrong' for n in (2, 4, 5, 6, 10, 11)},
        },
    },
    {
        'username': 'demo_nikita', 'first': 'Никита', 'last': 'Соколов',
        'pace': 0.35,
        'plan': {1: 'ok', 2: 'ok', 3: 'wrong', 4: 'wrong'},
    },
]


def swapped_numbers(answer):
    """Тот же ответ с числами в обратном порядке – один балл за 26/27."""
    import re
    numbers = re.findall(r'-?\d+', answer)
    if len(numbers) != 2:
        raise CommandError(f'Ожидались два числа в эталоне, получено: {answer!r}')
    sep = '\n' if '\n' in answer.strip() else ' '
    return sep.join(reversed(numbers))


def spent_seconds(number, pace, planned):
    """Время по нормативу с детерминированным разбросом – без random."""
    norm = EGE_RECOMMENDED_TIME.get(number, 5) * 60
    jitter = (number * 137) % 45
    if not planned:
        return 0
    return int(norm * pace) + jitter


class Command(BaseCommand):
    help = 'Демо-ученики с разными результатами по варианту ЕГЭ'

    def add_arguments(self, parser):
        parser.add_argument('quiz_id', type=int, help='id варианта (quiz_type="exam")')

    def handle(self, *args, **options):
        quiz = Quiz.objects.filter(id=options['quiz_id'], quiz_type='exam').first()
        if quiz is None:
            raise CommandError('Нет варианта с таким id')

        questions = {
            q.ege_number: q
            for q in quiz.questions.filter(ege_number__isnull=False)
        }
        group, _ = StudentGroup.objects.get_or_create(
            name=GROUP_NAME, defaults={'is_ege_class': True},
        )

        with transaction.atomic():
            pupils = []
            for spec in STUDENTS:
                user, _ = User.objects.get_or_create(
                    username=spec['username'],
                    defaults={'first_name': spec['first'], 'last_name': spec['last']},
                )
                user.first_name, user.last_name = spec['first'], spec['last']
                user.set_password(PASSWORD)
                user.is_active = True
                user.save()
                Profile.objects.update_or_create(
                    user=user, defaults={'group': group, 'is_ege': True},
                )
                pupils.append(user)

            # Только своё: результаты и снимки прошлого прогона.
            UserResult.objects.filter(quiz=quiz, user__in=pupils).delete()
            ExamTaskProgress.objects.filter(quiz=quiz, user__in=pupils).delete()
            CodeSubmission.objects.filter(quiz=quiz, user__in=pupils).delete()

            now = timezone.now()
            for spec, user in zip(STUDENTS, pupils):
                self._seed_student(quiz, questions, user, spec, now)

            self._seed_likes(questions, pupils)

        self.stdout.write(self.style.SUCCESS(
            f'{len(pupils)} учеников в группе «{GROUP_NAME}», вариант «{quiz.title}»',
        ))

    def _seed_student(self, quiz, questions, user, spec, now):
        plan = spec['plan']
        answers = {}

        for number, verdict in plan.items():
            question = questions.get(number)
            if question is None:
                raise CommandError(f'В варианте нет задания {number}')
            expected = expected_answer(question)
            if verdict == 'ok':
                answer, want_correct, want_score = expected, True, None
            elif verdict == 'partial1':
                answer = swapped_numbers(expected)
                want_correct, want_score = check_answer(question, answer)
                if want_score != 1:
                    raise CommandError(
                        f'Задание {number}: перестановка чисел дала {want_score} балла',
                    )
            else:
                answer, want_correct, want_score = '0', False, None

            got_correct, got_score = check_answer(question, answer)
            if got_correct != want_correct or (want_score is not None and got_score != want_score):
                raise CommandError(
                    f'{user.username}, задание {number}: проверка ответа дала '
                    f'({got_correct}, {got_score}), план – ({want_correct}, {want_score})',
                )
            answers[number] = (answer, got_correct, got_score)

        total_seconds = sum(
            spent_seconds(q.ege_number, spec['pace'], q.ege_number in plan)
            for q in questions.values()
        )
        result = UserResult.objects.create(
            user=user, quiz=quiz, score=0,
            date_completed=now - datetime.timedelta(minutes=(len(user.username) % 5) * 37),
            duration=datetime.timedelta(seconds=total_seconds),
        )

        code_metrics = {number: (cpu, memory) for number, cpu, memory in spec.get('code') or []}
        primary = 0
        for number, question in sorted(questions.items()):
            answer, is_correct, score = answers.get(number, ('', False, None))
            seconds = spent_seconds(number, spec['pace'], number in plan)
            if is_correct:
                primary += question.points
            elif score:
                primary += score

            # Снимок – по каждой верной задаче с кодом, а не только там, где
            # заданы метрики: «Решения других» строятся из верных снимков, и
            # без них учитель видит у решённой задачи «0 решений».
            submission = None
            if is_correct and question.question_type == 'code':
                cpu, memory = code_metrics.get(
                    number, (round(40 + number * 1.7, 1), 9000 + number * 41),
                )
                submission = CodeSubmission.objects.create(
                    user=user, quiz=quiz, question=question,
                    code=f'# демо-решение задания {number}\nprint({answer!r})\n',
                    language='python', status='success',
                    is_correct=True, answer=answer,
                    completed_at=now,
                    cpu_time_ms=cpu, memory_kb=memory,
                )

            UserAnswer.objects.create(
                user_result=result, question=question,
                text_answer=answer or None,
                code_answer=submission.code if submission else None,
                is_correct=is_correct, score=score, submission=submission,
            )

            # Прогресс – только по открытым задачам, как в ege_finish_view:
            # неотвеченная задача попытки не засчитывает.
            if number in plan:
                ExamTaskProgress.objects.create(
                    user=user, quiz=quiz, question=question,
                    time_spent_seconds=seconds,
                    attempts_to_solve=1,
                    is_solved=is_correct,
                    score=score,
                    first_solved_at=now if is_correct else None,
                    best_cpu_time_ms=submission.cpu_time_ms if submission else None,
                    best_memory_kb=submission.memory_kb if submission else None,
                    best_cpu_code=submission.code if submission else '',
                    best_memory_code=submission.code if submission else '',
                )

        result.score = primary
        result.save(update_fields=['score'])

    def _seed_likes(self, questions, pupils):
        """Пара лайков, иначе сортировка по ❤ в таблице проверяется на нулях."""
        pairs = [(pupils[0], 2), (pupils[0], 5), (pupils[1], 2),
                 (pupils[2], 19), (pupils[3], 1)]
        for author, number in pairs:
            question = questions.get(number)
            if question is None:
                continue
            solution, _ = SharedSolution.objects.get_or_create(
                user=author, question=question,
            )
            for liker in pupils:
                if liker != author:
                    SolutionLike.objects.get_or_create(
                        user=liker, solution=solution,
                    )
