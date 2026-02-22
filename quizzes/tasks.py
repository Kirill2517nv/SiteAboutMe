import os
from celery import shared_task
from django.utils import timezone
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from datetime import timedelta


def normalize_output(text):
    """Normalize output for comparison."""
    if not text:
        return ""
    lines = text.strip().splitlines()
    return "\n".join([line.rstrip() for line in lines])


@shared_task(bind=True, max_retries=1)
def check_code_task(self, submission_id):
    """
    Celery task for checking code submission in Docker.
    Updates CodeSubmission status and sends WebSocket notification.
    """
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
    all_tests_passed = True
    error_log = None

    try:
        # Get test cases
        test_cases = list(question.test_cases.all())

        if not test_cases:
            all_tests_passed = False
            error_log = "Нет тестовых примеров для проверки."
        else:
            # Prepare extra files from QuestionFile attachments
            extra_files = {}
            for qf in question.files.all():
                try:
                    with qf.file.open('rb') as f:
                        extra_files[os.path.basename(qf.file.name)] = f.read()
                except Exception as e:
                    error_log = f"Ошибка чтения файла задания: {e}"
                    all_tests_passed = False
                    break

            # Run tests, accumulate metrics
            total_cpu_time = 0.0
            peak_memory = 0
            if all_tests_passed:
                for i, test_case in enumerate(test_cases, 1):
                    output, error, cpu_time_ms, memory_kb = run_code_in_docker(code, test_case.input_data, extra_files)

                    total_cpu_time += cpu_time_ms or 0
                    peak_memory = max(peak_memory, memory_kb or 0)

                    if error:
                        all_tests_passed = False
                        error_log = error
                        break

                    if normalize_output(output) != normalize_output(test_case.output_data):
                        all_tests_passed = False
                        error_log = f"Неверный ответ на тесте #{i}.\nВходные данные: {test_case.input_data}\nВаш ответ: {output}"
                        break

        # Update submission with result and metrics
        submission.is_correct = all_tests_passed
        submission.status = 'success' if all_tests_passed else 'failed'
        submission.error_log = error_log
        submission.completed_at = timezone.now()
        submission.cpu_time_ms = total_cpu_time if total_cpu_time > 0 else None
        submission.memory_kb = peak_memory if peak_memory > 0 else None
        submission.save(update_fields=['is_correct', 'status', 'error_log', 'completed_at', 'cpu_time_ms', 'memory_kb'])

        # Update linked UserAnswer if quiz was already finished
        update_user_answer_from_submission(submission)

        # Update ExamTaskProgress (best metrics, solved status) — works even without UserAnswer
        update_exam_progress_from_submission(submission)

        # Send WebSocket notification - completed
        send_ws_notification(submission, 'completed')

        return {
            'submission_id': submission_id,
            'is_correct': all_tests_passed,
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
    user_answer.error_log = submission.error_log
    user_answer.code_answer = submission.code
    user_answer.save(update_fields=['is_correct', 'error_log', 'code_answer'])

    # Recalculate UserResult score with row-level lock to prevent race conditions
    with transaction.atomic():
        user_result = UserResult.objects.select_for_update().get(
            id=user_answer.user_result_id
        )
        quiz = user_result.quiz

        if quiz.quiz_type == 'exam':
            # ЕГЭ: считаем сумму баллов (points) за правильные ответы
            correct_answers = UserAnswer.objects.filter(
                user_result=user_result,
                is_correct=True
            )
            total_score = correct_answers.aggregate(
                total=Sum('question__points')
            )['total'] or 0
        else:
            # Стандартный тест: считаем количество правильных ответов
            total_score = UserAnswer.objects.filter(
                user_result__user=user_result.user,
                user_result__quiz=quiz,
                is_correct=True
            ).values('question_id').distinct().count()

        user_result.score = total_score
        user_result.save(update_fields=['score'])

    # ExamTaskProgress обновляется в update_exam_progress_from_submission()


def update_exam_progress_from_submission(submission):
    """
    Обновляет ExamTaskProgress после проверки code-задачи ЕГЭ.
    Вызывается из check_code_task напрямую (не зависит от UserAnswer).
    """
    if submission.quiz.quiz_type != 'exam' or not submission.is_correct:
        return

    from .models import ExamTaskProgress

    progress, _ = ExamTaskProgress.objects.get_or_create(
        user=submission.user,
        quiz=submission.quiz,
        question=submission.question,
    )
    fields_to_update = []

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
