"""
Самостоятельная работа на уроке с надзором.

Ученик начинает работу со страницы, таймер идёт на сервере, ответы лежат
черновиком здесь же, а уход со страницы замораживает попытку до учителя.
Итог при сдаче пишется в обычные UserResult/UserAnswer: отчёты и разбор
попытки учителя работают без изменений.

Окно класса живёт в QuizAssignment, как у среза: «Начать» – назначение классу
со start=now и end=None, «Закрыть» – end=now. Поэтому check_window и
check_released работают без правок, а «разбор открыт» = quiz.check_released().
"""
from datetime import timedelta

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from .ege_constants import EXAM_ANSWER_GRACE
from .models import ClassworkAttempt, Quiz, QuizAssignment

DEFAULT_MINUTES = 40
# Шкала одна на все работы; править здесь.
GRADE_SCALE = ((85, 5), (65, 4), (45, 3))  # процент от максимума -> оценка, ниже – 2
DRAFT_LIMIT = 20000


def minutes(quiz):
    """Минуты на работу: заданные учителем или 40 по умолчанию."""
    return quiz.check_minutes or DEFAULT_MINUTES


def window_open(quiz, user):
    """Окно ученика открыто прямо сейчас."""
    window = quiz.check_window(user)
    if not window:
        return False
    now = timezone.now()
    return bool(window.start_date and window.start_date <= now
                and (window.end_date is None or window.end_date > now))


def open_works(user):
    """
    Работы, доступные ученику прямо сейчас, – для плашки в учебнике.

    Сданные выпадают: «Начать» второй раз нечего. Учителю список пуст –
    баннер ему не нужен, а окна он видит в панели.
    """
    if user.is_superuser:
        return []
    done = ClassworkAttempt.objects.filter(
        user=user, finished_at__isnull=False).values('quiz_id')
    works = Quiz.objects.filter(quiz_type='classwork').exclude(id__in=done)
    return [quiz for quiz in works if window_open(quiz, user)]


def start(user, quiz):
    """Открыть попытку или вернуть уже идущую. Повторный «Начать» время не продлевает."""
    attempt = ClassworkAttempt.objects.filter(user=user, quiz=quiz).first()
    if attempt:
        return attempt
    if not window_open(quiz, user):
        return None
    attempt, _ = ClassworkAttempt.objects.get_or_create(
        user=user, quiz=quiz,
        defaults={'deadline': timezone.now() + timedelta(minutes=minutes(quiz))},
    )
    return attempt


def max_score(quiz):
    return quiz.questions.aggregate(total=Sum('points'))['total'] or 0


def score(result):
    """Балл попытки – сумма points верно решённых задач."""
    if result is None:
        return 0
    return result.answers.filter(is_correct=True).aggregate(
        total=Sum('question__points'))['total'] or 0


def auto_grade(points, maximum):
    if not maximum:
        return None
    percent = points * 100 / maximum
    for threshold, grade in GRADE_SCALE:
        if percent >= threshold:
            return grade
    return 2


def final_grade(attempt):
    if attempt.grade is not None:
        return attempt.grade
    if not attempt.result_id:
        return None
    return auto_grade(score(attempt.result), max_score(attempt.quiz))


def accepts_answers(attempt, now=None):
    """Работа идёт: не сдана, не заморожена, время и окно не вышли."""
    if attempt.finished_at or attempt.frozen_at:
        return False
    return not is_expired(attempt, now)


def is_expired(attempt, now=None):
    """Пора сдавать по часам или учитель закрыл окно класса."""
    now = now or timezone.now()
    if attempt.finished_at:
        return False
    if now > attempt.deadline + EXAM_ANSWER_GRACE:
        return True
    window = attempt.quiz.check_window(attempt.user)
    end = window.end_date if window else None
    return bool(end and now > end + EXAM_ANSWER_GRACE)


def log(attempt, kind, seconds=0, now=None):
    """
    Дописать событие в журнал надзора.

    Под select_for_update: событие «ушёл» с автосохранением приходят от
    разных запросов почти одновременно, и без блокировки одно из них терялось.
    """
    now = now or timezone.now()
    with transaction.atomic():
        row = ClassworkAttempt.objects.select_for_update().get(pk=attempt.pk)
        events = list(row.events or [])
        events.append({'kind': kind, 'at': now.isoformat(), 'seconds': int(seconds)})
        row.events = events
        row.save(update_fields=['events'])
    attempt.events = row.events


def leave(attempt, now=None):
    """Ученик ушёл со страницы: замораживаем попытку до учителя."""
    if attempt.finished_at:
        return
    now = now or timezone.now()
    if not attempt.frozen_at:
        # Условный UPDATE, а не save(): второй уход не должен сдвигать время
        # первой заморозки, с которого учитель считает отсутствие.
        ClassworkAttempt.objects.filter(pk=attempt.pk, frozen_at__isnull=True).update(frozen_at=now)
        attempt.frozen_at = now
    log(attempt, 'leave', now=now)


def unfreeze(attempt):
    ClassworkAttempt.objects.filter(pk=attempt.pk).update(frozen_at=None)
    attempt.frozen_at = None
    log(attempt, 'unfreeze')


def save_draft(attempt, answers, languages):
    """
    Сохранить черновик. Принимаем только id вопросов этой работы и годные языки.

    UPDATE по колонкам, а не save(update_fields): журнал и заморозка живут в
    той же строке, и черновик не должен приносить с собой устаревшую копию.
    """
    if not accepts_answers(attempt):
        return False
    if not isinstance(answers, dict):
        answers = {}
    if not isinstance(languages, dict):
        languages = {}
    valid = {str(pk) for pk in attempt.quiz.questions.values_list('id', flat=True)}
    clean_answers = {
        key: value[:DRAFT_LIMIT]
        for key, value in answers.items()
        if str(key) in valid and isinstance(value, str)
    }
    clean_languages = {
        key: value for key, value in languages.items()
        if str(key) in valid and value in ('python', 'cpp')
    }
    ClassworkAttempt.objects.filter(pk=attempt.pk).update(
        answers=clean_answers, languages=clean_languages)
    attempt.answers = clean_answers
    attempt.languages = clean_languages
    return True


def _queue(submission_id):
    """
    Поставить снимок в очередь на проверку.

    Зовётся только после коммита: Celery берёт задачу сразу, и если
    транзакция ещё не закрылась, CodeSubmission для неё не существует.
    """
    from .models import CodeSubmission
    from .tasks import check_code_task

    try:
        task = check_code_task.delay(submission_id)
    except Exception:
        CodeSubmission.objects.filter(pk=submission_id).update(
            status='error',
            error_log='Сервер проверки временно недоступен',
            completed_at=timezone.now(),
        )
        return
    CodeSubmission.objects.filter(pk=submission_id).update(celery_task_id=task.id)


def finalize(attempt, now=None):
    """
    Сдать работу: черновик превращается в UserResult с ответами.

    Идемпотентно – страница жмёт «Сдана» на нуле таймера, а учитель в это же
    время может закрыть работу. finished_at = min(now, deadline): поблажка на
    досылку ответов не идёт в длительность работы.
    """
    from .models import Choice, CodeSubmission, UserAnswer, UserResult

    now = now or timezone.now()
    with transaction.atomic():
        row = (ClassworkAttempt.objects.select_for_update()
               .select_related('quiz', 'user').get(pk=attempt.pk))
        if row.finished_at:
            return row.result

        finished_at = min(now, row.deadline)
        result = UserResult.objects.create(
            user=row.user, quiz=row.quiz, score=0,
            duration=finished_at - row.started_at,
        )
        answers = row.answers or {}
        languages = row.languages or {}
        batch = []
        queued = []
        for question in row.quiz.questions.all():
            value = str(answers.get(str(question.id)) or '')
            selected = None
            text_answer = None
            code_answer = None
            submission = None
            is_correct = False
            if question.question_type == 'choice':
                if value.isdigit():
                    selected = Choice.objects.filter(id=int(value), question=question).first()
                    is_correct = bool(selected and selected.is_correct)
            elif question.question_type == 'text':
                text_answer = value[:500] or None
                if value:
                    is_correct = question.check_text_answer(value)
            elif question.question_type == 'code' and value:
                # Та же ветка, что в finish_quiz_view: проверку ведёт Celery,
                # is_correct выставит update_user_answer_from_submission.
                # ponytail: дубль осознан – объединять, если появится третий потребитель.
                language = languages.get(str(question.id))
                submission = CodeSubmission.objects.create(
                    user=row.user, quiz=row.quiz, question=question, code=value,
                    language=language if language in ('python', 'cpp') else 'python',
                    status='pending',
                )
                queued.append(submission.id)
                code_answer = value
            batch.append(UserAnswer(
                user_result=result, question=question, selected_choice=selected,
                text_answer=text_answer, code_answer=code_answer,
                is_correct=is_correct, submission=submission,
            ))
        UserAnswer.objects.bulk_create(batch)
        result.score = score(result)
        result.save(update_fields=['score'])
        row.result = result
        row.finished_at = finished_at
        row.save(update_fields=['result', 'finished_at'])

        # Только после коммита: иначе Celery может взяться за проверку, пока
        # отправки ещё не видны другим соединениям. Каждый id – своим
        # аргументом, чтобы лямбда не взяла последний из цикла.
        for submission_id in queued:
            transaction.on_commit(lambda sid=submission_id: _queue(sid))

    attempt.result = result
    attempt.finished_at = finished_at
    return result


def expire(quiz):
    """
    Сдать все просроченные попытки работы.

    Зовёт панель учителя при каждом опросе: закрытая вкладка ученика иначе
    оставляла бы работу висеть незакрытой до ручного вмешательства.
    """
    for attempt in (ClassworkAttempt.objects.filter(quiz=quiz, finished_at__isnull=True)
                    .select_related('quiz', 'user')):
        if is_expired(attempt):
            finalize(attempt)


def close(quiz, group):
    """Закрыть окно класса и сразу сдать всех, кто ещё пишет."""
    now = timezone.now()
    QuizAssignment.objects.filter(quiz=quiz, group=group, user=None).update(end_date=now)
    for attempt in (ClassworkAttempt.objects.filter(
            quiz=quiz, user__profile__group=group, finished_at__isnull=True)
            .select_related('quiz', 'user')):
        finalize(attempt, now)


def open_for_group(quiz, group):
    """«Начать»: окно класса открыто, конца у него пока нет."""
    QuizAssignment.objects.update_or_create(
        quiz=quiz, group=group, user=None,
        defaults={'start_date': timezone.now(), 'end_date': None},
    )


def pending(result):
    """Проверка кода ещё идёт – балл может вырасти, барабан ждёт."""
    if result is None:
        return False
    return result.answers.filter(submission__status__in=('pending', 'running')).exists()
