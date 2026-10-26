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
    from .ege_scoring import check_answer, grade, is_partial_task, outputs_match
    from .models import CodeSubmission, TestCase
    from .utils import compile_code, run_code_in_docker

    # Берём только ждущую: «Остановить» закрывает отправку прямо в очереди
    # (submission_stop_view), и такую проверять уже не надо.
    if not CodeSubmission.objects.filter(id=submission_id, status='pending').update(
            status='running', celery_task_id=self.request.id):
        return {'submission_id': submission_id, 'status': 'skipped'}
    submission = CodeSubmission.objects.select_related('question', 'user', 'quiz').get(id=submission_id)

    # Send WebSocket notification - running
    send_ws_notification(submission, 'running')

    question = submission.question
    code = submission.code
    # Снимок тренажёра ЕГЭ: задачу уже оценил ответ, прогон нужен только ради
    # времени, памяти и «отработала без ошибки». Вывод с эталоном не сравниваем.
    snapshot = submission.answer is not None
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
            try:
                extra_files = question_files(question)
            except Exception as e:
                error_log = f"Ошибка чтения файла задания: {e}"
                files_ok = False

            program = None
            if files_ok:
                program, compile_error = compile_code(code, submission.language, submission_id)
                if compile_error:
                    error_log = compile_error
                    score = 0

            if program is not None:
                # Задача засчитана, только если пройдены ВСЕ тесты: первый же
                # провал прекращает проверку и попадает в сообщение об ошибке.
                # Исключение – задания 26 и 27: неверный ответ там ещё может
                # стоить 1 балла, поэтому тесты прогоняются до конца, а баллом
                # становится худший из них.
                partial = not snapshot and is_partial_task(question)
                all_tests_passed = True
                for i, test_case in enumerate(test_cases, 1):
                    output, error, cpu_time_ms, memory_kb = run_code_in_docker(
                        program, test_case.input_data, extra_files, submission.language, submission_id)

                    if error:
                        all_tests_passed = False
                        error_log = error
                        score = 0
                        break

                    if partial:
                        test_score = grade(question, output, test_case.output_data)
                        score = test_score if score is None else min(score, test_score)

                    if not snapshot and not outputs_match(output, test_case.output_data):
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

                if snapshot:
                    all_tests_passed = (all_tests_passed and bool(submission.answer)
                                        and check_answer(question, submission.answer)[0])

                if not all_tests_passed:
                    passed_cpu_time = passed_memory_kb = None

        # Update submission with result and metrics
        submission.is_correct = all_tests_passed
        # Балл снимка живёт рядом с ответом (PracticeItem, UserAnswer), не здесь.
        submission.score = None if snapshot else score
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


def create_snapshot(user, quiz, question, code, language, answer):
    """
    Снимок кода к ответу в тренажёре ЕГЭ: CodeSubmission с answer, прогон в очередь.

    Пустой код снимка не даёт – ответ без кода законен. Тот же код с тем же
    ответом второй раз не сохраняется: «Проверить» в тренировке и завершение
    варианта прислали бы одно и то же дважды.
    """
    from .models import CodeSubmission
    code = str(code or '').strip()
    if not code:
        return None
    last = (CodeSubmission.objects.filter(user=user, quiz=quiz, question=question)
            .order_by('-created_at').first())
    if last and last.code == code and last.language == language and last.answer == answer:
        return last
    submission = CodeSubmission.objects.create(
        user=user, quiz=quiz, question=question, code=code,
        language=language, answer=answer, status='pending',
    )
    try:
        task = check_code_task.delay(submission.id)
        submission.celery_task_id = task.id
        submission.save(update_fields=['celery_task_id'])
    except Exception:
        submission.status = 'error'
        submission.error_log = 'Сервер проверки временно недоступен'
        submission.completed_at = timezone.now()
        submission.save(update_fields=['status', 'error_log', 'completed_at'])
    return submission


RUN_LOCK_SECONDS = 90  # дольше компиляции C++ (20 с) и контейнера вместе


def run_lock_key(user_id):
    return f'code-run:{user_id}'


@shared_task
def run_code_task(code, language, stdin, question_id, run_id, user_id):
    """
    «Запустить» в тренажёре ЕГЭ: прогон без оценки и без записи в базу.

    Та же песочница и те же файлы задачи, что у проверки, но с тем stdin,
    который ввёл ученик. Результат живёт в result backend Celery (час), и его
    забирает run_status_view. Метка контейнера `run-<id>` нужна «Остановить».
    """
    from .models import Question
    from .utils import compile_code, run_code_in_docker
    label = f'run-{run_id}'
    try:
        question = Question.objects.get(id=question_id)
        program, error = compile_code(code, language, label)
        if error:
            return {'output': '', 'error': error, 'cpu_time_ms': None, 'memory_kb': None}
        output, error, cpu_time_ms, memory_kb = run_code_in_docker(
            program, stdin, question_files(question), language, label)
        return {'output': output or '', 'error': error,
                'cpu_time_ms': cpu_time_ms, 'memory_kb': memory_kb}
    finally:
        # Один запуск на ученика за раз: снимаем замок, только если он наш.
        import redis
        from django.conf import settings
        client = redis.Redis.from_url(settings.CELERY_BROKER_URL)
        if client.get(run_lock_key(user_id)) == run_id.encode():
            client.delete(run_lock_key(user_id))


def question_files(question):
    """Файлы задачи {имя: байты} – их программа читает так же, как на экзамене."""
    files = {}
    for qf in question.files.all():
        with qf.file.open('rb') as f:
            files[os.path.basename(qf.file.name)] = f.read()
    return files


# Сутки: даже 3 200 снимков варианта на 200 учеников при ~100 проверках в
# минуту проходят за полчаса. Дольше снимок висит, только если воркер лежит.
SNAPSHOT_STALE_AFTER = timedelta(hours=24)


@shared_task
def cleanup_stale_submissions():
    """
    Periodic task: find and clean up submissions stuck in pending/running.
    Runs every 3 minutes via Celery Beat.
    """
    from .models import CodeSubmission

    from django.db.models import Q

    now = timezone.now()
    # Снимок к ответу (answer не пуст) никто не ждёт на экране: исход задачи уже
    # записан. После экзамена класса их в очереди тысячи, и 10 минут – обычная
    # очередь, а не зависание. Закрыв снимок, мы бы потеряли его для «Решений
    # других» и рекордов: check_code_task берёт только pending.
    stale = CodeSubmission.objects.filter(status__in=['pending', 'running']).filter(
        Q(answer__isnull=True, created_at__lt=now - timedelta(minutes=10))
        | Q(answer__isnull=False, created_at__lt=now - SNAPSHOT_STALE_AFTER)
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

    if submission.answer is not None:
        return  # снимок: ответ в UserAnswer оценён при завершении варианта
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

        if quiz.quiz_type in ('exam', 'classwork'):
            # Экзамен и самостоятельная: сумма баллов. За задания 26 и 27 балл
            # бывает частичным – тогда он записан в самом ответе, а не
            # выводится из question.points. У самостоятельной попытка одна,
            # поэтому сумма по её ответам – и есть итог работы.
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

    if submission.answer is not None:
        return  # снимок: исход задачи уже записал ответ (practice_answer_view)

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

    if submission.answer is not None:
        # Снимок: попытку, балл и «решена» записал ответ. Снимку остаются рекорды.
        if submission.is_correct:
            fields = _update_best_metrics(progress, submission)
            if fields:
                progress.save(update_fields=fields)
        return

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

    fields_to_update += _update_best_metrics(progress, submission)

    if fields_to_update:
        progress.save(update_fields=fields_to_update)


def _update_best_metrics(progress, submission):
    """Лучшие время и память (меньше = лучше) вместе с кодом. Возвращает поля."""
    fields_to_update = []
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
    return fields_to_update


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
