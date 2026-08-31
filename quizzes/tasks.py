import os
from celery import shared_task
from django.utils import timezone
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from datetime import timedelta


@shared_task(bind=True, max_retries=1)
def check_code_task(self, submission_id):
    """
    Celery task for checking code submission in Docker.
    Updates CodeSubmission status and sends WebSocket notification.
    """
    from .ege_scoring import grade, is_partial_task, outputs_match
    from .models import CodeSubmission, TestCase
    from .utils import run_code_in_docker

    try:
        submission = CodeSubmission.objects.select_related('question', 'user', 'quiz').get(id=submission_id)
    except CodeSubmission.DoesNotExist:
        return {'error': 'Submission not found'}

    # Update status to running
    submission.status = 'running'
    submission.celery_task_id = self.request.id
    submission.save(update_fields=['status', 'celery_task_id'])

    # Send WebSocket notification - running
    send_ws_notification(submission, 'running')

    question = submission.question
    code = submission.code
    all_tests_passed = False
    error_log = None
    score = None
    passed_cpu_time = None
    passed_memory_kb = None

    try:
        # Get test cases
        test_cases = list(question.test_cases.all())

        if not test_cases:
            error_log = "Нет тестовых примеров для проверки."
        else:
            # Prepare extra files from QuestionFile attachments
            extra_files = {}
            files_ok = True
            for qf in question.files.all():
                try:
                    with qf.file.open('rb') as f:
                        extra_files[os.path.basename(qf.file.name)] = f.read()
                except Exception as e:
                    error_log = f"Ошибка чтения файла задания: {e}"
                    files_ok = False
                    break

            if files_ok:
                # Задача засчитана, только если пройдены ВСЕ тесты: первый же
                # провал прекращает проверку и попадает в сообщение об ошибке.
                # Исключение – задания 26 и 27: неверный ответ там ещё может
                # стоить 1 балла, поэтому тесты прогоняются до конца, а баллом
                # становится худший из них.
                partial = is_partial_task(question)
                all_tests_passed = True
                for i, test_case in enumerate(test_cases, 1):
                    output, error, cpu_time_ms, memory_kb = run_code_in_docker(code, test_case.input_data, extra_files)

                    if error:
                        all_tests_passed = False
                        error_log = error
                        score = 0
                        break

                    if partial:
                        test_score = grade(question, output, test_case.output_data)
                        score = test_score if score is None else min(score, test_score)

                    if not outputs_match(output, test_case.output_data):
                        all_tests_passed = False
                        if error_log is None:
                            error_log = (
                                f"Неверный ответ на тесте #{i}.\n"
                                f"Входные данные: {test_case.input_data}\n"
                                f"Ваш ответ: {output}"
                            )
                        if not partial:
                            break
                        continue

                    # Метрики берём по худшему из пройденных тестов — так честнее
                    # оценивать решение, чем по одному удачному запуску.
                    if cpu_time_ms is not None:
                        passed_cpu_time = max(passed_cpu_time or 0, cpu_time_ms)
                    if memory_kb is not None:
                        passed_memory_kb = max(passed_memory_kb or 0, memory_kb)

                if partial and score:
                    # Сравнение строк придирается к раскладке чисел, оценка – нет:
                    # полный балл и есть «решено верно».
                    all_tests_passed = score >= question.points
                    if all_tests_passed:
                        error_log = None

                if not all_tests_passed:
                    passed_cpu_time = passed_memory_kb = None

        # Update submission with result and metrics
        submission.is_correct = all_tests_passed
        submission.score = score
        submission.status = 'success' if all_tests_passed else 'failed'
        submission.error_log = error_log
        submission.completed_at = timezone.now()
        submission.cpu_time_ms = passed_cpu_time if passed_cpu_time is not None else None
        submission.memory_kb = passed_memory_kb if passed_memory_kb is not None else None
        submission.save(update_fields=['is_correct', 'score', 'status', 'error_log',
                                       'completed_at', 'cpu_time_ms', 'memory_kb'])

        # Update linked UserAnswer if quiz was already finished
        update_user_answer_from_submission(submission)

        # Update ExamTaskProgress (best metrics, solved status) — works even without UserAnswer
        update_exam_progress_from_submission(submission)

        # Записать исход в открытую сессию тренировки, если ученик решает в ней
        update_practice_item_from_submission(submission)

        # Send WebSocket notification - completed
        send_ws_notification(submission, 'completed')

        return {
            'submission_id': submission_id,
            'is_correct': all_tests_passed,
            'score': score,
            'status': submission.status,
            'error_log': error_log,
        }

    except Exception as e:
        # System error
        submission.status = 'error'
        submission.error_log = f"Системная ошибка: {str(e)}"
        submission.completed_at = timezone.now()
        submission.save(update_fields=['status', 'error_log', 'completed_at'])

        # Send WebSocket notification - error
        send_ws_notification(submission, 'error')

        return {
            'submission_id': submission_id,
            'status': 'error',
            'error': str(e),
        }


@shared_task
def cleanup_stale_submissions():
    """
    Periodic task: find and clean up submissions stuck in pending/running.
    Runs every 3 minutes via Celery Beat.
    """
    from .models import CodeSubmission

    threshold = timezone.now() - timedelta(minutes=10)

    stale = CodeSubmission.objects.filter(
        status__in=['pending', 'running'],
        created_at__lt=threshold
    )

    for submission in stale:
        submission.status = "error"
        submission.error_log = 'Превышено время ожидания'
        submission.completed_at = timezone.now()
        submission.save(update_fields=['status', 'error_log', 'completed_at'])
        update_user_answer_from_submission(submission)
        send_ws_notification(submission, 'error')


@shared_task
def recalc_ege_difficulty_task():
    """
    Периодический пересчёт фактической сложности задач ЕГЭ.

    Логика целиком в management-команде: её же надо уметь гонять руками при
    разборе, и держать две копии подсчёта смысла нет.
    """
    from django.core.management import call_command

    call_command('recalc_ege_difficulty')



def update_user_answer_from_submission(submission):
    """
    After Celery checks a submission, update linked UserAnswer and recalculate score.
    Called when quiz was already finished while submission was still pending.
    Uses select_for_update to prevent race conditions between parallel workers.
    """
    from django.db import transaction
    from django.db.models import Sum
    from .models import UserAnswer, UserResult, ExamTaskProgress

    user_answer = UserAnswer.objects.filter(submission=submission).first()
    if not user_answer:
        return

    user_answer.is_correct = submission.is_correct or False
    user_answer.score = submission.score
    user_answer.error_log = submission.error_log
    user_answer.code_answer = submission.code
    user_answer.save(update_fields=['is_correct', 'score', 'error_log', 'code_answer'])

    # Recalculate UserResult score with row-level lock to prevent race conditions
    with transaction.atomic():
        user_result = UserResult.objects.select_for_update().get(
            id=user_answer.user_result_id
        )
        quiz = user_result.quiz

        if quiz.quiz_type == 'exam':
            # ЕГЭ: сумма баллов. За задания 26 и 27 балл бывает частичным –
            # тогда он записан в самом ответе, а не выводится из question.points.
            total_score = sum(
                answer.score if answer.score is not None
                else (answer.question.points if answer.is_correct else 0)
                for answer in UserAnswer.objects
                .filter(user_result=user_result)
                .select_related('question')
            )
        else:
            # Стандартный тест: считаем количество правильных ответов
            total_score = UserAnswer.objects.filter(
                user_result__user=user_result.user,
                user_result__quiz=quiz,
                is_correct=True
            ).values('question_id').distinct().count()

        user_result.score = total_score
        user_result.save(update_fields=['score'])

    # Хук учебника: отметить статью «освоено», если пройдена самопроверка
    if getattr(quiz, 'is_self_check', False):
        from textbook.services import update_article_mastery
        update_article_mastery(user_result.user, quiz)

    # ExamTaskProgress обновляется в update_exam_progress_from_submission()


def update_practice_item_from_submission(submission):
    """
    Записывает исход проверки кода в открытую сессию тренировки.

    В отличие от ExamTaskProgress, сюда попадают и провалы: именно по последнему
    исходу собирается пул задач для работы над ошибками. Ищем незавершённую
    сессию ученика с этой задачей – если он решает её вне тренировки, ничего
    не происходит.
    """
    from .models import PracticeItem

    item = (
        PracticeItem.objects
        .filter(
            session__user=submission.user,
            session__finished_at__isnull=True,
            question=submission.question,
        )
        .select_related('session')
        .order_by('-session__created_at')
        .first()
    )
    if item is None or item.is_locked:
        # Закрытую задачу (решена или открыт ответ) повторная отправка не меняет:
        # счётчик попыток и отказ от задачи должны остаться такими, как были.
        return

    item.attempts += 1

    if item.session.kind == 'retry':
        # Задача уже решена раньше, сейчас ученик улучшает решение. Провал
        # такой попытки не должен переводить задачу в нерешённые: он означает
        # лишь, что очередной вариант кода не прошёл тесты. Лучшие время и
        # память берутся из CodeSubmission – там сохранена каждая отправка.
        if not submission.is_correct:
            item.save(update_fields=['attempts'])
            return
        item.submission = submission
        item.is_correct = True
        item.answered_at = timezone.now()
        item.save(update_fields=['submission', 'is_correct', 'attempts', 'answered_at'])
        return

    item.submission = submission
    item.is_correct = bool(submission.is_correct)
    item.score = submission.score
    item.answered_at = timezone.now()
    item.save(update_fields=['submission', 'is_correct', 'score', 'attempts', 'answered_at'])


def update_exam_progress_from_submission(submission):
    """
    Обновляет ExamTaskProgress после проверки code-задачи ЕГЭ.
    Вызывается из check_code_task напрямую (не зависит от UserAnswer).
    """
    if submission.quiz.quiz_type != 'exam':
        return

    from .models import ExamTaskProgress

    progress, _ = ExamTaskProgress.objects.get_or_create(
        user=submission.user,
        quiz=submission.quiz,
        question=submission.question,
    )

    # Каждая проверка кода – попытка. Без этого задача на код, отправленная
    # десять раз и так и не решённая, не попадала в статистику вовсе: строка
    # прогресса заводится учётом времени, а фильтр отбрасывает её по нулевым
    # попыткам, и точность по вариантам считалась только по решённым задачам.
    # После решения счётчик замирает: он показывает, с какой попытки задача
    # была взята, а не сколько раз ученик потом переписывал решение.
    fields_to_update = []
    if not progress.is_solved:
        progress.attempts_to_solve += 1
        fields_to_update.append('attempts_to_solve')

    # Частичный балл (задания 26 и 27) задачу решённой не делает – она остаётся
    # в работе над ошибками, – но в баллы ученика идёт. Держим лучший результат:
    # неудачная вторая попытка не должна отнимать уже заработанное.
    if submission.score is not None and submission.score > (progress.score or 0):
        progress.score = submission.score
        fields_to_update.append('score')

    if not submission.is_correct:
        if fields_to_update:
            progress.save(update_fields=fields_to_update)
        return

    if not progress.is_solved:
        progress.is_solved = True
        progress.first_solved_at = timezone.now()
        fields_to_update += ['is_solved', 'first_solved_at']

    # Обновляем лучшие метрики (меньше = лучше) и запоминаем код
    if submission.cpu_time_ms is not None:
        if progress.best_cpu_time_ms is None or submission.cpu_time_ms < progress.best_cpu_time_ms:
            progress.best_cpu_time_ms = submission.cpu_time_ms
            progress.best_cpu_code = submission.code
            fields_to_update += ['best_cpu_time_ms', 'best_cpu_code']
    if submission.memory_kb is not None:
        if progress.best_memory_kb is None or submission.memory_kb < progress.best_memory_kb:
            progress.best_memory_kb = submission.memory_kb
            progress.best_memory_code = submission.code
            fields_to_update += ['best_memory_kb', 'best_memory_code']

    if fields_to_update:
        progress.save(update_fields=fields_to_update)


def send_ws_notification(submission, event_type):
    """
    Send WebSocket notification about submission status change.
    """
    channel_layer = get_channel_layer()
    if not channel_layer:
        return

    group_name = f"user_{submission.user_id}_quiz_{submission.quiz_id}"

    message = {
        'type': 'submission_update',
        'submission_id': submission.id,
        'question_id': submission.question_id,
        'status': submission.status,
        'is_correct': submission.is_correct,
        'error_log': submission.error_log,
        'event_type': event_type,
        'cpu_time_ms': submission.cpu_time_ms,
        'memory_kb': submission.memory_kb,
    }

    try:
        async_to_sync(channel_layer.group_send)(group_name, message)
    except Exception:
        pass  # Ignore WebSocket errors, they are non-critical
