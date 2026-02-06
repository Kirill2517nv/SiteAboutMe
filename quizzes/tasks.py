import os
from celery import shared_task
from django.utils import timezone
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync


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
            # Prepare extra files if question has data file
            extra_files = {}
            if question.data_file:
                try:
                    with question.data_file.open('rb') as f:
                        content = f.read()
                        filename = os.path.basename(question.data_file.name)
                        extra_files[filename] = content
                except Exception as e:
                    error_log = f"Ошибка чтения файла задания: {e}"
                    all_tests_passed = False

            # Run tests
            if all_tests_passed:
                for i, test_case in enumerate(test_cases, 1):
                    output, error = run_code_in_docker(code, test_case.input_data, extra_files)

                    if error:
                        all_tests_passed = False
                        error_log = error
                        break

                    if normalize_output(output) != normalize_output(test_case.output_data):
                        all_tests_passed = False
                        error_log = f"Неверный ответ на тесте #{i}.\nВходные данные: {test_case.input_data}\nВаш ответ: {output}"
                        break

        # Update submission with result
        submission.is_correct = all_tests_passed
        submission.status = 'success' if all_tests_passed else 'failed'
        submission.error_log = error_log
        submission.completed_at = timezone.now()
        submission.save(update_fields=['is_correct', 'status', 'error_log', 'completed_at'])

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
    }

    try:
        async_to_sync(channel_layer.group_send)(group_name, message)
    except Exception:
        pass  # Ignore WebSocket errors, they are non-critical
