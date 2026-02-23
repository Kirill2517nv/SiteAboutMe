from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.utils import timezone
from django.contrib.auth.models import User
from django.db.models import Max, Count, Q, Sum, Prefetch
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.conf import settings
from django.views.decorators.http import require_POST, require_GET
from django.views.decorators.csrf import csrf_protect
from .models import Quiz, Choice, UserResult, UserAnswer, TestCase, QuizAssignment, Question, CodeSubmission, HelpRequest, HelpComment, QuestionFile, ExamTaskProgress, SolutionAttachment, SolutionLike
from accounts.models import StudentGroup
import datetime
import os
import json
import mimetypes
import re
from urllib.parse import quote
from .utils import run_code_in_docker
from .tasks import check_code_task

# Рекомендуемое время на задачу ЕГЭ по информатике (минуты)
EGE_RECOMMENDED_TIME = {
    1: 3, 2: 3, 3: 3, 4: 2, 5: 4, 6: 4, 7: 5, 8: 4,
    9: 6, 10: 3, 11: 3, 12: 6, 13: 3, 14: 3, 15: 3, 16: 5,
    17: 14, 18: 8, 19: 6, 20: 8, 21: 11, 22: 7, 23: 8,
    24: 18, 25: 20, 26: 35, 27: 40,
}


def _natural_sort_key(text):
    """Ключ для натуральной сортировки: 'Задача 2' перед 'Задача 10'."""
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r'(\d+)', text)]


def _attachment_content_disposition(filename: str) -> str:
    """
    Nginx-friendly Content-Disposition:
    - ASCII fallback in filename=""
    - RFC 5987 filename*=UTF-8''...
    Also strips CR/LF to prevent header injection / invalid headers.
    """
    safe = (filename or "download").replace("\r", "").replace("\n", "")
    ascii_fallback = re.sub(r"[^A-Za-z0-9.\-_]", "_", safe) or "download"
    return f'attachment; filename="{ascii_fallback}"; filename*=UTF-8\'\'{quote(safe)}'

def normalize_output(text):
    if not text:
        return ""
    lines = text.strip().splitlines()
    return "\n".join([line.rstrip() for line in lines])

def get_effective_quiz_settings(user, quiz):
    """
    Returns a dict with effective start_date, end_date, max_attempts
    based on user/group assignments.
    Returns None if no assignment found for this user (unless superuser).
    """
    # Check for individual assignment first
    assignment = QuizAssignment.objects.filter(user=user, quiz=quiz).first()
    
    # If no individual, check group
    if not assignment and hasattr(user, 'profile') and user.profile.group:
        assignment = QuizAssignment.objects.filter(group=user.profile.group, quiz=quiz).first()
    
    if assignment:
        return {
            'start_date': assignment.start_date if assignment.start_date else quiz.start_date,
            'end_date': assignment.end_date if assignment.end_date else quiz.end_date,
            'max_attempts': assignment.max_attempts if assignment.max_attempts is not None else quiz.max_attempts
        }

    # If not assigned, but superuser -> show global settings
    if user.is_superuser:
        return {
            'start_date': quiz.start_date,
            'end_date': quiz.end_date,
            'max_attempts': quiz.max_attempts
        }

    return None

@login_required
def question_file_download_view(request, file_id):
    """
    Download a QuestionFile attachment with a stable filename across browsers/OS.
    """
    qf = get_object_or_404(QuestionFile, id=file_id)

    filename = qf.get_filename()
    content_type, _ = mimetypes.guess_type(filename)

    response = FileResponse(
        qf.file.open("rb"),
        as_attachment=True,
        content_type=content_type or "application/octet-stream",
    )
    response["Content-Disposition"] = _attachment_content_disposition(filename)
    return response

def quiz_list_view(request):
    if not request.user.is_authenticated:
        return render(request, 'quizzes/quiz_list.html', {'educational_tasks': [], 'assessments': [], 'archived': []})

    user = request.user
    
    effective_assignments = {} # quiz_id -> {start, end, max}

    # Get assignments for user (even if superuser, we want to see if they are assigned)
    filters = Q(user=user)
    if hasattr(user, 'profile') and user.profile.group:
        filters |= Q(group=user.profile.group)
    
    assignments = QuizAssignment.objects.filter(filters).select_related('quiz')
    
    # Deduplicate, prioritizing user assignment over group
    temp_assignments = {} # quiz_id -> assignment object

    for a in assignments:
        qid = a.quiz_id
        if qid not in temp_assignments:
            temp_assignments[qid] = a
        else:
            existing = temp_assignments[qid]
            if existing.user is None and a.user is not None:
                temp_assignments[qid] = a
    
    if user.is_superuser:
        quizzes = Quiz.objects.exclude(quiz_type='exam')
    else:
        quizzes = []
        for qid, a in temp_assignments.items():
            if a.quiz.quiz_type != 'exam':
                quizzes.append(a.quiz)

    # Process effective settings
    for quiz in quizzes:
        a = temp_assignments.get(quiz.id)
        if a:
            effective_assignments[quiz.id] = {
                'start_date': a.start_date if a.start_date else quiz.start_date,
                'end_date': a.end_date if a.end_date else quiz.end_date,
                'max_attempts': a.max_attempts if a.max_attempts is not None else quiz.max_attempts
            }
        else:
            # Fallback for superuser viewing unassigned quizzes
            effective_assignments[quiz.id] = {
                'start_date': quiz.start_date,
                'end_date': quiz.end_date,
                'max_attempts': quiz.max_attempts
            }

    # Pre-load attempts and best scores
    user_results = {}
    if request.user.is_authenticated:
        stats = UserResult.objects.filter(user=request.user).values('quiz_id').annotate(
            count=Count('id'),
            best_score=Max('score')
        )
        user_results = {item['quiz_id']: item for item in stats}
    
    # Pre-load question counts
    all_quiz_ids = [q.id for q in quizzes]
    question_counts = {}
    if all_quiz_ids:
        q_counts = Question.objects.filter(quiz_id__in=all_quiz_ids).values('quiz_id').annotate(count=Count('id'))
        question_counts = {item['quiz_id']: item['count'] for item in q_counts}

    educational_tasks = []
    assessments = []
    archived = []

    now = timezone.now()

    for quiz in quizzes:
        settings = effective_assignments.get(quiz.id)
        if not settings:
            continue

        start_date = settings['start_date']
        end_date = settings['end_date']
        max_attempts = settings['max_attempts']

        stats = user_results.get(quiz.id, {})
        attempts_count = stats.get('count', 0)
        best_score = stats.get('best_score')
        total_questions = question_counts.get(quiz.id, 0)

        is_blocked = False
        remaining_attempts = None
        status_text = "(Открыто)"
        status_color = "green"

        if start_date and now < start_date:
            is_blocked = True
            status_text = "(Недоступно)"
            status_color = "#e6b800" # Dark yellow/gold

        elif end_date and now > end_date:
            is_blocked = True
            status_text = "(Завершился)"
            status_color = "red"

        if max_attempts > 0:
            remaining_attempts = max_attempts - attempts_count
            if remaining_attempts <= 0:
                is_blocked = True
                remaining_attempts = 0
                # If it was open by date, but blocked by attempts -> show attempts exhausted
                if status_text == "(Открыто)":
                    status_text = "(Попытки исчерпаны)"
                    status_color = "red"

        item_data = {
            'quiz': quiz,
            'attempts_count': attempts_count,
            'best_score': best_score,
            'total_questions': total_questions,
            'is_blocked': is_blocked,
            'remaining_attempts': remaining_attempts,
            'status_text': status_text,
            'status_color': status_color,
            'start_date': start_date,
            'end_date': end_date,
            'max_attempts': max_attempts
        }

        # Expired quizzes go to archive instead of main lists
        if end_date and now > end_date:
            archived.append(item_data)
        elif max_attempts == 0:
            educational_tasks.append(item_data)
        else:
            assessments.append(item_data)

    # Sort archive: most recently expired first
    archived.sort(key=lambda x: x['end_date'], reverse=True)

    context = {
        'educational_tasks': educational_tasks,
        'assessments': assessments,
        'archived': archived,
    }
    return render(request, 'quizzes/quiz_list.html', context)

def get_user_ege_stats(user, quiz_ids):
    """Агрегация результатов пользователя по вариантам ЕГЭ (один запрос)."""
    stats = UserResult.objects.filter(user=user, quiz_id__in=quiz_ids).values('quiz_id').annotate(
            count=Count('id'),
            best_score=Max('score')
        )
    return {
        item['quiz_id']: {'attempts': item['count'], 'best_score': item['best_score']}
        for item in stats
    }


def build_ege_results_matrix(quiz):
    """Матрица: пользователи x задачи для таблицы результатов.

    Одна строка на пользователя — лучший результат по каждой задаче
    из ВСЕХ попыток (если задача решена хотя бы в одной попытке — ✓).
    """
    from collections import defaultdict

    questions = list(quiz.questions.filter(
        ege_number__isnull=False
    ).order_by('ege_number'))

    # Все ответы по варианту, группируем по user
    all_answers = UserAnswer.objects.filter(
        user_result__quiz=quiz
    ).select_related('question', 'user_result__user')

    # {user_id: {question_id: True}} — True если хоть раз верно
    user_best = defaultdict(dict)
    users_map = {}  # user_id -> User object
    # {(user_id, question_id): answer_id} — лучший ответ (correct > latest)
    best_answer_map = {}

    for ans in all_answers:
        uid = ans.user_result.user_id
        qid = ans.question_id
        users_map[uid] = ans.user_result.user
        # Берём лучший результат: True перезаписывает False, но не наоборот
        prev_solved = user_best[uid].get(qid) is True
        if not prev_solved:
            user_best[uid][qid] = ans.is_correct
        key = (uid, qid)
        if key not in best_answer_map:
            best_answer_map[key] = ans.id
        elif ans.is_correct and not prev_solved:
            best_answer_map[key] = ans.id

    # Собираем матрицу
    matrix = []
    for uid, best_map in user_best.items():
        user = users_map[uid]
        task_results = [
            {'correct': best_map.get(q.id), 'ege_number': q.ege_number, 'user_id': uid}
            for q in questions
        ]
        correct_count = sum(1 for r in task_results if r['correct'] is True)
        score = sum(q.points for q, r in zip(questions, task_results) if r['correct'] is True)

        full_name = f"{user.last_name} {user.first_name}".strip()
        if not full_name:
            full_name = user.username

        matrix.append({
            'user': user,
            'user_id': uid,
            'full_name': full_name,
            'task_results': task_results,
            'correct_count': correct_count,
            'score': score,
        })

    # Сортировка: по баллам desc, затем по фамилии
    matrix.sort(key=lambda r: (-r['score'], r['full_name']))

    return matrix, questions, best_answer_map


def ege_list_view(request):
    quizzes = Quiz.objects.filter(
        quiz_type='exam', is_public=True,
    ).annotate(
        num_questions=Count('questions'),
        total_points=Sum('questions__points'),
    ).order_by('title')

    user_stats = {}
    if request.user.is_authenticated:
        quiz_ids = [q.id for q in quizzes]
        user_stats = get_user_ege_stats(request.user, quiz_ids) or {}

    variants = []
    for quiz in quizzes:
        stats = user_stats.get(quiz.id, {})
        attempts = stats.get('attempts', 0)
        best_score = stats.get('best_score')

        variants.append({
            'quiz': quiz,
            'num_questions': quiz.num_questions,
            'total_points': quiz.total_points or 0,
            'exam_mode': quiz.exam_mode,
            'attempts': attempts,
            'best_score': best_score,
        })

    return render(request, 'quizzes/ege_list.html', {
        'variants': variants,
    })


# --- EGE DETAIL / CHECK / FINISH / RESULT / SAVE-TIME ---

@login_required
def ege_detail_view(request, quiz_id):
    """Страница прохождения варианта ЕГЭ."""
    quiz = get_object_or_404(
        Quiz.objects.prefetch_related(
            'questions__images',
            'questions__files',
            'questions__test_cases',
        ),
        id=quiz_id,
        quiz_type='exam',
        is_public=True,
    )

    # Режим экзамена + уже есть результат → redirect на результат
    if quiz.exam_mode == 'exam':
        existing_result = UserResult.objects.filter(user=request.user, quiz=quiz).order_by('-date_completed').first()
        if existing_result:
            return redirect('ege:ege_result', quiz_id=quiz.id)

    questions = list(quiz.questions.all().order_by('ege_number', 'id'))

    # Загрузка прогресса
    progress_qs = ExamTaskProgress.objects.filter(user=request.user, quiz=quiz)
    progress_map = {p.question_id: p for p in progress_qs}

    # Последние CodeSubmission для code-задач (для тренировки — показать статус)
    code_questions = [q for q in questions if q.question_type == 'code']
    last_submissions = {}
    if code_questions:
        for q in code_questions:
            sub = CodeSubmission.objects.filter(
                user=request.user, quiz=quiz, question=q
            ).order_by('-created_at').first()
            if sub:
                last_submissions[q.id] = {
                    'id': sub.id,
                    'status': sub.status,
                    'is_correct': sub.is_correct,
                    'code': sub.code,
                    'cpu_time_ms': sub.cpu_time_ms,
                    'memory_kb': sub.memory_kb,
                }

    # Последние текстовые ответы из UserAnswer (для нерешённых text-задач)
    text_questions = [q for q in questions if q.question_type == 'text']
    last_text_answers = {}  # question_id -> text_answer
    if text_questions:
        text_ua_qs = UserAnswer.objects.filter(
            user_result__user=request.user,
            user_result__quiz=quiz,
            question__in=text_questions,
            text_answer__isnull=False,
        ).exclude(text_answer='').order_by('-user_result__date_completed')
        for ua in text_ua_qs:
            if ua.question_id not in last_text_answers:
                last_text_answers[ua.question_id] = ua.text_answer

    # Данные для Alpine.js
    tasks_data = []
    for q in questions:
        prog = progress_map.get(q.id)
        saved_answer = ''
        saved_answer_wrong = False
        if q.question_type == 'text':
            if prog and prog.is_solved:
                # Решена — показываем правильный ответ
                saved_answer = q.correct_text_answer or ''
            elif q.id in last_text_answers:
                # Не решена, но есть предыдущий ответ — показываем его
                saved_answer = last_text_answers[q.id]
                saved_answer_wrong = True
        task_data = {
            'id': q.id,
            'ege_number': q.ege_number,
            'topic': q.topic,
            'type': q.question_type,
            'points': q.points,
            'is_solved': prog.is_solved if prog else False,
            'attempts': prog.attempts_to_solve if prog else 0,
            'time_spent': prog.time_spent_seconds if prog else 0,
            'saved_answer': saved_answer,
            'saved_answer_wrong': saved_answer_wrong,
        }
        # Лучшие метрики для code-задач
        if q.question_type == 'code' and prog:
            task_data['best_cpu_time_ms'] = prog.best_cpu_time_ms
            task_data['best_memory_kb'] = prog.best_memory_kb
            task_data['best_cpu_code'] = prog.best_cpu_code or ''
            task_data['best_memory_code'] = prog.best_memory_code or ''
        tasks_data.append(task_data)

    # Сохраняем время начала в session
    session_key = f'ege_{quiz_id}_start'
    if session_key not in request.session:
        request.session[session_key] = timezone.now().isoformat()

    context = {
        'quiz': quiz,
        'questions': questions,
        'tasks_json': json.dumps(tasks_data),
        'last_submissions_json': json.dumps(last_submissions),
        'total_points': sum(q.points for q in questions),
    }
    return render(request, 'quizzes/ege_detail.html', context)


@login_required
@require_POST
def ege_check_answer_view(request, quiz_id):
    """AJAX: проверка одного text-ответа (только тренировка)."""
    quiz = get_object_or_404(Quiz, id=quiz_id, quiz_type='exam', is_public=True)

    if quiz.exam_mode != 'practice':
        return JsonResponse({'error': 'Проверка по одному доступна только в тренировке'}, status=403)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Невалидный JSON'}, status=400)

    question_id = data.get('question_id')
    answer = data.get('answer', '').strip()
    if not question_id or not answer:
        return JsonResponse({'error': 'Укажите question_id и answer'}, status=400)

    question = get_object_or_404(Question, id=question_id, quiz=quiz)

    if question.question_type not in ('text', 'choice'):
        return JsonResponse({'error': 'Тип задачи не поддерживает синхронную проверку'}, status=400)

    is_correct = question.check_text_answer(answer)

    # Обновляем ExamTaskProgress
    progress, _ = ExamTaskProgress.objects.get_or_create(
        user=request.user, quiz=quiz, question=question,
    )
    progress.attempts_to_solve += 1
    fields_to_update = ['attempts_to_solve']

    if is_correct and not progress.is_solved:
        progress.is_solved = True
        progress.first_solved_at = timezone.now()
        fields_to_update += ['is_solved', 'first_solved_at']

    progress.save(update_fields=fields_to_update)

    return JsonResponse({
        'is_correct': is_correct,
        'attempts': progress.attempts_to_solve,
        'is_solved': progress.is_solved,
    })


@login_required
@require_POST
def ege_finish_view(request, quiz_id):
    """Завершение варианта ЕГЭ: создание UserResult + UserAnswer."""
    quiz = get_object_or_404(Quiz, id=quiz_id, quiz_type='exam', is_public=True)

    # Экзамен — не более 1 попытки
    if quiz.exam_mode == 'exam':
        if UserResult.objects.filter(user=request.user, quiz=quiz).exists():
            return JsonResponse({'error': 'Вариант уже завершён'}, status=403)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        data = {}

    answers_data = data.get('answers', {})  # {question_id: answer_text}
    force = data.get('force', False)

    questions = list(quiz.questions.all().order_by('ege_number', 'id'))

    # Длительность
    duration = None
    session_key = f'ege_{quiz_id}_start'
    start_time_str = request.session.get(session_key)
    if start_time_str:
        start_time = datetime.datetime.fromisoformat(start_time_str)
        duration = timezone.now() - start_time
        if session_key in request.session:
            del request.session[session_key]

    user_result = UserResult.objects.create(
        user=request.user, quiz=quiz, score=0, duration=duration,
    )

    total_score = 0
    user_answers_to_create = []

    for question in questions:
        user_input = answers_data.get(str(question.id), '')
        is_correct = False
        text_answer = None
        code_answer = None
        error_log = None
        submission = None

        if question.question_type == 'text':
            text_answer = user_input
            if user_input:
                is_correct = question.check_text_answer(user_input)
                if is_correct:
                    total_score += question.points

        elif question.question_type == 'code':
            # Берём последний completed CodeSubmission
            latest_sub = CodeSubmission.objects.filter(
                user=request.user, quiz=quiz, question=question,
            ).order_by('-created_at').first()

            if latest_sub:
                code_answer = latest_sub.code
                submission = latest_sub
                if latest_sub.status in ('success', 'failed'):
                    is_correct = latest_sub.is_correct or False
                    error_log = latest_sub.error_log
                    if is_correct:
                        total_score += question.points
                elif latest_sub.status in ('pending', 'running'):
                    # Ещё проверяется — Celery обновит позже
                    code_answer = latest_sub.code
            elif user_input:
                # Код написан, но "Проверить" не нажималась — создаём submission
                new_sub = CodeSubmission.objects.create(
                    user=request.user, quiz=quiz, question=question,
                    code=user_input, status='pending',
                )
                try:
                    task = check_code_task.delay(new_sub.id)
                    new_sub.celery_task_id = task.id
                    new_sub.save(update_fields=['celery_task_id'])
                except Exception:
                    new_sub.status = 'error'
                    new_sub.error_log = 'Сервер проверки временно недоступен'
                    new_sub.completed_at = timezone.now()
                    new_sub.save(update_fields=['status', 'error_log', 'completed_at'])
                code_answer = user_input
                submission = new_sub

        user_answers_to_create.append(UserAnswer(
            user_result=user_result,
            question=question,
            text_answer=text_answer,
            code_answer=code_answer,
            error_log=error_log,
            is_correct=is_correct,
            submission=submission,
        ))

    UserAnswer.objects.bulk_create(user_answers_to_create)

    user_result.score = total_score
    user_result.save(update_fields=['score'])

    # Обновляем ExamTaskProgress для всех верно решённых задач
    for ua in user_answers_to_create:
        if ua.is_correct:
            progress, _ = ExamTaskProgress.objects.get_or_create(
                user=request.user, quiz=quiz, question=ua.question,
            )
            if not progress.is_solved:
                progress.is_solved = True
                progress.first_solved_at = timezone.now()
                progress.save(update_fields=['is_solved', 'first_solved_at'])

    # Pending code submissions count
    pending_checks = sum(
        1 for ua in user_answers_to_create
        if ua.submission and ua.submission.status in ('pending', 'running')
    )

    return JsonResponse({
        'success': True,
        'result_id': user_result.id,
        'score': total_score,
        'total_points': sum(q.points for q in questions),
        'pending_checks': pending_checks,
        'redirect_url': f'/ege/{quiz_id}/result/',
    })


@login_required
def ege_result_view(request, quiz_id):
    """Страница результата прохождения ЕГЭ."""
    quiz = get_object_or_404(Quiz, id=quiz_id, quiz_type='exam', is_public=True)

    user_result = UserResult.objects.filter(
        user=request.user, quiz=quiz,
    ).order_by('-date_completed').first()

    if not user_result:
        return redirect('ege:ege_detail', quiz_id=quiz.id)

    answers = user_result.answers.select_related(
        'question', 'submission',
    ).prefetch_related('question__images').order_by('question__ege_number', 'question__id')

    total_points = quiz.questions.aggregate(total=Sum('points'))['total'] or 0

    # Pending code checks
    pending_count = answers.filter(
        submission__isnull=False,
        submission__status__in=['pending', 'running'],
    ).count()

    # Format duration as H:MM:SS
    duration_display = None
    if user_result.duration:
        total_secs = int(user_result.duration.total_seconds())
        hours, remainder = divmod(total_secs, 3600)
        minutes, secs = divmod(remainder, 60)
        duration_display = f'{hours}:{minutes:02d}:{secs:02d}'

    return render(request, 'quizzes/ege_result.html', {
        'quiz': quiz,
        'user_result': user_result,
        'answers': answers,
        'total_points': total_points,
        'pending_count': pending_count,
        'duration_display': duration_display,
    })


@login_required
def ege_results_view(request, quiz_id):
    """Сводная таблица результатов варианта ЕГЭ."""
    quiz = get_object_or_404(Quiz, id=quiz_id, quiz_type='exam', is_public=True)
    results_matrix, questions, best_answer_map = build_ege_results_matrix(quiz)
    total_points = sum(q.points for q in questions)

    # --- Sort data для клиентской сортировки ---
    question_types = {q.ege_number: q.question_type for q in questions}
    question_id_map = {q.id: q.ege_number for q in questions}

    # Лайки по best_answer_id
    all_answer_ids = list(best_answer_map.values())
    like_counts = {}
    if all_answer_ids:
        like_qs = SolutionLike.objects.filter(
            answer_id__in=all_answer_ids,
        ).values('answer_id').annotate(cnt=Count('id'))
        like_counts = {row['answer_id']: row['cnt'] for row in like_qs}

    # CPU/memory из CodeSubmission
    code_answer_ids = [
        aid for (uid, qid), aid in best_answer_map.items()
        if question_id_map.get(qid) and question_types.get(question_id_map[qid]) == 'code'
    ]
    cpu_mem_map = {}  # answer_id -> {cpu, mem}
    if code_answer_ids:
        sub_qs = UserAnswer.objects.filter(
            id__in=code_answer_ids, submission__isnull=False,
        ).values_list('id', 'submission__cpu_time_ms', 'submission__memory_kb')
        for aid, cpu, mem in sub_qs:
            cpu_mem_map[aid] = {'cpu': cpu, 'mem': mem}

    # Время из ExamTaskProgress
    user_ids = [row['user_id'] for row in results_matrix]
    time_map = {}  # (user_id, question_id) -> seconds
    if user_ids:
        progress_qs = ExamTaskProgress.objects.filter(
            quiz=quiz, user_id__in=user_ids,
        ).values_list('user_id', 'question_id', 'time_spent_seconds')
        for uid, qid, secs in progress_qs:
            time_map[(uid, qid)] = secs

    # Собираем sort_data: {user_id: {ege_number: {likes, cpu, memory, time}}}
    sort_data = {}
    for (uid, qid), aid in best_answer_map.items():
        ege_num = question_id_map.get(qid)
        if ege_num is None:
            continue
        sort_data.setdefault(uid, {})[ege_num] = {
            'likes': like_counts.get(aid, 0),
            'cpu': (cpu_mem_map.get(aid) or {}).get('cpu'),
            'memory': (cpu_mem_map.get(aid) or {}).get('mem'),
            'time': time_map.get((uid, qid)),
        }

    question_types_json = json.dumps(question_types)
    sort_data_json = json.dumps(sort_data)

    # Личная статистика из ExamTaskProgress
    personal_stats = None
    if request.user.is_authenticated:
        progress_qs = ExamTaskProgress.objects.filter(
            user=request.user, quiz=quiz,
        ).select_related('question')
        progress_map = {p.question_id: p for p in progress_qs}

        if progress_map:
            personal_stats = []
            for q in questions:
                p = progress_map.get(q.id)
                ege_num = q.ege_number or 0
                rec_min = EGE_RECOMMENDED_TIME.get(ege_num, 5)

                if p and p.time_spent_seconds > 0:
                    mins = p.time_spent_seconds // 60
                    secs = p.time_spent_seconds % 60
                    time_mm_ss = f"{mins}:{secs:02d}"
                    if mins <= rec_min:
                        color = 'green'
                    elif mins <= rec_min * 1.5:
                        color = 'yellow'
                    else:
                        color = 'red'
                else:
                    time_mm_ss = ''
                    color = ''

                personal_stats.append({
                    'ege_number': ege_num,
                    'time_mm_ss': time_mm_ss,
                    'attempts': p.attempts_to_solve if p else 0,
                    'is_solved': p.is_solved if p else False,
                    'color': color,
                    'is_code': q.question_type == 'code',
                    'cpu_time_ms': p.best_cpu_time_ms if p else None,
                    'memory_kb': p.best_memory_kb if p else None,
                })

    return render(request, 'quizzes/ege_results.html', {
        'quiz': quiz,
        'results_matrix': results_matrix,
        'questions': questions,
        'total_points': total_points,
        'personal_stats': personal_stats,
        'sort_data_json': sort_data_json,
        'question_types_json': question_types_json,
    })


@login_required
@require_POST
def ege_save_time_view(request, quiz_id):
    """AJAX: сохранение времени по задаче."""
    quiz = get_object_or_404(Quiz, id=quiz_id, quiz_type='exam', is_public=True)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Невалидный JSON'}, status=400)

    question_id = data.get('question_id')
    seconds = data.get('seconds', 0)

    if not question_id or seconds <= 0:
        return JsonResponse({'error': 'Невалидные данные'}, status=400)

    # Cap per request: защита от стухших таймеров (вкладка открыта без активности).
    # Периодик шлёт каждые 30 с, поэтому 120 с — разумный лимит на один запрос.
    seconds = min(seconds, 120)

    question = get_object_or_404(Question, id=question_id, quiz=quiz)

    progress, _ = ExamTaskProgress.objects.get_or_create(
        user=request.user, quiz=quiz, question=question,
    )

    # Не считаем время после первого верного решения
    if progress.is_solved:
        return JsonResponse({'ok': True, 'total_seconds': progress.time_spent_seconds, 'frozen': True})

    progress.time_spent_seconds += seconds
    progress.save(update_fields=['time_spent_seconds'])

    return JsonResponse({'ok': True, 'total_seconds': progress.time_spent_seconds})


@login_required
@require_POST
def ege_upload_attachment_view(request, quiz_id, ege_number):
    from django.contrib import messages
    """Загрузка/обновление SolutionAttachment."""
    quiz = get_object_or_404(Quiz, id=quiz_id, quiz_type='exam', is_public=True)
    question = get_object_or_404(Question, quiz=quiz, ege_number=ege_number)

    # Проверка: решил задачу
    if not ExamTaskProgress.objects.filter(
        user=request.user, quiz=quiz, question=question, is_solved=True,
    ).exists():
        return redirect('ege:ege_user_solution', quiz_id=quiz.id, ege_number=ege_number, user_id=request.user.id)

    attachment, _ = SolutionAttachment.objects.get_or_create(
        user=request.user, quiz=quiz, question=question,
    )

    ALLOWED_FILE_EXT = {"txt", "csv", "ods", "odt", "xlsx", "doc", "docx", "pdf"}
    ALLOWED_IMAGE_EXT = {"jpg", "jpeg", "png", "gif", "webp"}
    has_changes = False

    if request.FILES.get('file'):
        if request.FILES['file'].size > 20 * 1024 * 1024:
            messages.error(request, 'Нельзя загрузить документ более 20 МБ')
            return redirect('ege:ege_user_solution', quiz_id=quiz.id, ege_number=ege_number, user_id=request.user.id)
        ext = os.path.splitext(request.FILES['file'].name)[1].lower().lstrip('.')
        if ext not in ALLOWED_FILE_EXT:
            messages.error(request, f'Допустимые расширения: {", ".join(sorted(ALLOWED_FILE_EXT))}')
            return redirect('ege:ege_user_solution', quiz_id=quiz.id, ege_number=ege_number, user_id=request.user.id)
        attachment.file = request.FILES['file']
        has_changes = True

    if request.FILES.get('image'):
        if request.FILES['image'].size > 5 * 1024 * 1024:
            messages.error(request, 'Нельзя загрузить изображение более 5 МБ')
            return redirect('ege:ege_user_solution', quiz_id=quiz.id, ege_number=ege_number, user_id=request.user.id)
        ext = os.path.splitext(request.FILES['image'].name)[1].lower().lstrip('.')
        if ext not in ALLOWED_IMAGE_EXT:
            messages.error(request, f'Допустимые расширения: {", ".join(sorted(ALLOWED_IMAGE_EXT))}')
            return redirect('ege:ege_user_solution', quiz_id=quiz.id, ege_number=ege_number, user_id=request.user.id)
        attachment.image = request.FILES['image']
        has_changes = True

    comment = request.POST.get('comment', '').strip()
    if comment:
        attachment.comment = comment
        has_changes = True

    if has_changes:
        attachment.save()

    return redirect('ege:ege_user_solution', quiz_id=quiz.id, ege_number=ege_number, user_id=request.user.id)


@login_required
@require_POST
def ege_toggle_like_view(request, answer_id):
    """Toggle лайка на решение. POST, возвращает JSON {liked, like_count}."""
    answer = get_object_or_404(
        UserAnswer.objects.select_related('user_result__user'),
        id=answer_id,
    )

    if answer.user_result.user == request.user:
        return JsonResponse({'error': 'Нельзя лайкать своё решение'}, status=403)

    existing = SolutionLike.objects.filter(user=request.user, answer=answer)
    if existing.exists():
        existing.delete()
        liked = False
    else:
        SolutionLike.objects.create(user=request.user, answer=answer)
        liked = True

    return JsonResponse({'liked': liked, 'like_count': answer.likes.count()})


@login_required
@require_GET
def ege_solution_detail_view(request, quiz_id, ege_number, user_id):
    """Страница просмотра решения конкретного пользователя по задаче ЕГЭ."""
    quiz = get_object_or_404(Quiz, id=quiz_id, quiz_type='exam', is_public=True)
    question = get_object_or_404(Question, quiz=quiz, ege_number=ege_number)

    # Проверка доступа: текущий пользователь решил задачу или superuser
    has_solved = request.user.is_superuser or ExamTaskProgress.objects.filter(
        user=request.user, quiz=quiz, question=question, is_solved=True,
    ).exists()
    if not has_solved:
        from django.contrib import messages
        messages.warning(request, 'Решите задачу, чтобы увидеть решения других.')
        return redirect('ege:ege_results', quiz_id=quiz.id)

    # Лучший ответ целевого пользователя (prefer correct, потом latest)
    all_answers = UserAnswer.objects.filter(
        user_result__quiz=quiz, question=question, user_result__user_id=user_id,
    ).select_related('user_result__user', 'submission').order_by('-user_result__date_completed')

    best = None
    for ans in all_answers:
        if best is None:
            best = ans
        elif ans.is_correct and not best.is_correct:
            best = ans

    if not best:
        raise Http404('Решение не найдено')

    user = best.user_result.user
    full_name = f"{user.last_name} {user.first_name}".strip() or user.username

    cpu_time_ms = None
    memory_kb = None
    if best.submission:
        cpu_time_ms = best.submission.cpu_time_ms
        memory_kb = best.submission.memory_kb

    # Лучшие попытки по CPU и памяти из ExamTaskProgress (для code-задач)
    best_cpu_code = ''
    best_cpu_time_ms = None
    best_memory_code = ''
    best_memory_kb = None
    if question.question_type == 'code':
        try:
            progress = ExamTaskProgress.objects.get(
                user_id=user_id, quiz=quiz, question=question,
            )
            best_cpu_code = progress.best_cpu_code or ''
            best_cpu_time_ms = progress.best_cpu_time_ms
            best_memory_code = progress.best_memory_code or ''
            best_memory_kb = progress.best_memory_kb
        except ExamTaskProgress.DoesNotExist:
            pass

    # Аттачмент
    attachment = None
    try:
        attachment = SolutionAttachment.objects.get(user_id=user_id, quiz=quiz, question=question)
    except SolutionAttachment.DoesNotExist:
        pass

    # Лайки
    like_count = best.likes.count()
    user_liked = best.likes.filter(user=request.user).exists()

    is_own = (user_id == request.user.id)

    return render(request, 'quizzes/ege_solution_detail.html', {
        'quiz': quiz,
        'question': question,
        'ege_number': ege_number,
        'target_user_name': full_name,
        'answer': best,
        'cpu_time_ms': cpu_time_ms,
        'memory_kb': memory_kb,
        'attachment': attachment,
        'like_count': like_count,
        'user_liked': user_liked,
        'is_own': is_own,
        'has_solved': has_solved,
        'answer_id': best.id,
        'best_cpu_code': best_cpu_code,
        'best_cpu_time_ms': best_cpu_time_ms,
        'best_memory_code': best_memory_code,
        'best_memory_kb': best_memory_kb,
    })


@login_required
def quiz_detail_view(request, quiz_id):
    # Оптимизация: предзагружаем связанные объекты
    quiz = get_object_or_404(
        Quiz.objects.prefetch_related(
            'questions__choices',
            'questions__test_cases',
            'questions__images',
            'questions__files'
        ),
        id=quiz_id
    )
    
    # Check assignment/availability
    eff_settings = get_effective_quiz_settings(request.user, quiz)
    if not eff_settings:
        # Not assigned to this user
        return redirect('quizzes:quiz_list')

    start_date = eff_settings['start_date']
    end_date = eff_settings['end_date']
    max_attempts = eff_settings['max_attempts']

    now = timezone.now()

    # Access checks
    read_only = False
    if start_date and now < start_date: return redirect('quizzes:quiz_list')

    if end_date and now > end_date:
        if request.method == 'POST':
            return redirect('quizzes:quiz_list')
        # GET on expired quiz → read-only mode
        read_only = True

    if not read_only and max_attempts > 0:
        attempts_count = UserResult.objects.filter(user=request.user, quiz=quiz).count()
        if attempts_count >= max_attempts: return redirect('quizzes:quiz_list')

    # Read-only mode: show all questions with student's best answers
    if read_only:
        all_questions = list(quiz.questions.all())
        all_questions.sort(key=lambda q: _natural_sort_key(q.get_title()))

        # Load student's best answer per question (correct preferred, then most recent)
        student_answers = {}
        all_user_answers = UserAnswer.objects.filter(
            user_result__user=request.user,
            user_result__quiz=quiz,
        ).select_related('question', 'selected_choice').order_by('-user_result__date_completed')

        for ans in all_user_answers:
            qid = ans.question_id
            if qid not in student_answers:
                student_answers[qid] = ans
            elif ans.is_correct and not student_answers[qid].is_correct:
                # Prefer correct answer over incorrect
                student_answers[qid] = ans

        for q in all_questions:
            q.is_solved = q.id in student_answers and student_answers[q.id].is_correct
            q.solved_answer = student_answers.get(q.id)

        return render(request, 'quizzes/quiz_detail.html', {
            'quiz': quiz,
            'questions_to_show': [],
            'all_questions': all_questions,
            'correctly_answered_ids': set(),
            'last_attempt_codes': {},
            'last_attempt_codes_json': '{}',
            'end_date': end_date,
            'is_admin': request.user.is_superuser,
            'read_only': True,
        })

    # --- Active quiz mode (not read-only) ---

    # Находим уже решенные вопросы
    correctly_answered_question_ids = UserAnswer.objects.filter(
        user_result__user=request.user,
        user_result__quiz=quiz,
        is_correct=True
    ).values_list('question_id', flat=True).distinct()

    # Считаем, сколько баллов уже "в кармане"
    already_earned_score = len(correctly_answered_question_ids)

    # Исключаем решенные из списка для показа
    # Вопросы уже предзагружены через prefetch_related
    questions_to_show = list(quiz.questions.exclude(id__in=correctly_answered_question_ids))

    # Восстанавливаем код из последней неудачной попытки для задач с кодом
    last_failed_attempt = UserResult.objects.filter(
        user=request.user,
        quiz=quiz
    ).order_by('-date_completed').first()

    last_attempt_codes = {}
    if last_failed_attempt:
        # Получаем код из последней попытки для вопросов, которые были решены неверно
        failed_code_answers = UserAnswer.objects.filter(
            user_result=last_failed_attempt,
            question__question_type='code',
            is_correct=False,
            code_answer__isnull=False
        ).exclude(code_answer='').select_related('question')

        # Создаем словарь: question_id -> code_answer для быстрого доступа в шаблоне
        last_attempt_codes = {answer.question_id: answer.code_answer for answer in failed_code_answers}

    if request.method == 'POST':
        current_attempt_score = 0

        duration = None
        start_time_str = request.session.get(f'quiz_{quiz_id}_start')
        if start_time_str:
            start_time = datetime.datetime.fromisoformat(start_time_str)
            end_time = timezone.now()
            duration = end_time - start_time
            if f'quiz_{quiz_id}_start' in request.session: del request.session[f'quiz_{quiz_id}_start']

        user_result = UserResult.objects.create(user=request.user, quiz=quiz, score=0, duration=duration)

        # Оптимизация: предзагружаем все choices в словарь для быстрого доступа
        all_choices = {}
        for question in questions_to_show:
            if question.question_type == 'choice':
                all_choices[question.id] = {choice.id: choice for choice in question.choices.all()}

        # Создаем список UserAnswer для bulk_create
        user_answers_to_create = []

        for question in questions_to_show:
            user_input = request.POST.get(f'question_{question.id}')
            is_correct = False
            selected_choice = None
            text_answer = None
            code_answer = None
            error_log = None

            # TODO: Refactor into separate function to avoid massive duplication if needed, but keeping inline for now
            if question.question_type == 'choice':
                if user_input:
                    # Используем предзагруженные choices
                    choice_dict = all_choices.get(question.id, {})
                    selected_choice = choice_dict.get(int(user_input)) if user_input.isdigit() else None
                    if selected_choice and selected_choice.is_correct:
                        is_correct = True
                        current_attempt_score += 1

            elif question.question_type == 'text':
                text_answer = user_input
                if user_input and question.correct_text_answer:
                    if user_input.strip().lower() == question.correct_text_answer.strip().lower():
                        is_correct = True
                        current_attempt_score += 1

            elif question.question_type == 'code':
                code_answer = user_input
                if user_input:
                    all_tests_passed = True
                    # test_cases уже предзагружены через prefetch_related
                    test_cases = list(question.test_cases.all())

                    if not test_cases:
                        all_tests_passed = False
                        error_log = "Нет тестовых примеров для проверки."

                    extra_files = {}
                    for qf in question.files.all():
                        try:
                            with qf.file.open('rb') as f:
                                extra_files[os.path.basename(qf.file.name)] = f.read()
                        except Exception as e:
                            error_log = f"Ошибка чтения файла задания: {e}"
                            all_tests_passed = False
                            break

                    if all_tests_passed:
                        for test_case in test_cases:
                            output, error, _, _ = run_code_in_docker(user_input, test_case.input_data, extra_files)

                            if error:
                                all_tests_passed = False
                                error_log = error
                                break

                            if normalize_output(output) != normalize_output(test_case.output_data):
                                all_tests_passed = False
                                # Скрываем правильный ответ от пользователя
                                error_log = f"Неверный ответ на тесте.\nВходные данные: {test_case.input_data}\nВаш ответ: {output}"
                                break

                    if all_tests_passed:
                        is_correct = True
                        current_attempt_score += 1

            user_answers_to_create.append(
                UserAnswer(
                    user_result=user_result,
                    question=question,
                    selected_choice=selected_choice,
                    text_answer=text_answer,
                    code_answer=code_answer,
                    error_log=error_log,
                    is_correct=is_correct
                )
            )

        # Оптимизация: создаем все ответы одним запросом
        UserAnswer.objects.bulk_create(user_answers_to_create)

        # Финальный балл = (баллы за эту попытку) + (баллы за старые решенные вопросы)
        total_score = current_attempt_score + already_earned_score

        user_result.score = total_score
        user_result.save()

        # Получаем неудачные ответы для детального отчета
        failed_answers = UserAnswer.objects.filter(
            user_result=user_result,
            is_correct=False
        ).select_related('question').order_by('question_id')

        # Используем предзагруженные вопросы вместо запроса к БД
        total_questions = quiz.questions.count() if hasattr(quiz.questions, 'count') else len(list(quiz.questions.all()))

        return render(request, 'quizzes/quiz_result.html', {
            'quiz': quiz,
            'score': total_score,
            'total': total_questions,  # Общее кол-во вопросов в тесте
            'failed_answers': failed_answers,  # Неудачные ответы для детального отчета
            'user_result': user_result,
        })

    request.session[f'quiz_{quiz_id}_start'] = timezone.now().isoformat()
    # Конвертируем ключи в строки для JSON сериализации
    last_attempt_codes_json = json.dumps({str(k): v for k, v in last_attempt_codes.items()})

    # Все вопросы теста, отсортированные натурально по заголовку
    all_questions = list(quiz.questions.all())
    all_questions.sort(key=lambda q: _natural_sort_key(q.get_title()))

    # Данные о решённых вопросах (для просмотра удачного решения)
    solved_answers = {}
    if correctly_answered_question_ids:
        solved_qs = UserAnswer.objects.filter(
            user_result__user=request.user,
            user_result__quiz=quiz,
            is_correct=True,
            question_id__in=correctly_answered_question_ids,
        ).select_related('question', 'selected_choice').order_by('-user_result__date_completed')
        for ans in solved_qs:
            if ans.question_id not in solved_answers:
                solved_answers[ans.question_id] = ans

    # Аннотируем вопросы статусом решённости для единого цикла в шаблоне
    for q in all_questions:
        q.is_solved = q.id in set(correctly_answered_question_ids)
        q.solved_answer = solved_answers.get(q.id)

    return render(request, 'quizzes/quiz_detail.html', {
        'quiz': quiz,
        'questions_to_show': questions_to_show,
        'all_questions': all_questions,
        'correctly_answered_ids': set(correctly_answered_question_ids),
        'last_attempt_codes': last_attempt_codes,
        'last_attempt_codes_json': last_attempt_codes_json,
        'end_date': end_date,
        'is_admin': request.user.is_superuser,
    })

# --- СТАТИСТИКА (без изменений) ---
@user_passes_test(lambda u: u.is_superuser)
def quiz_stats_view(request, quiz_id):
    quiz = get_object_or_404(Quiz, id=quiz_id)
    total_questions = quiz.questions.count()
    groups = StudentGroup.objects.filter(students__user__userresult__quiz=quiz).distinct()
    users_without_group = User.objects.filter(
        userresult__quiz=quiz, profile__group__isnull=True
    ).select_related('profile').distinct()

    stats_by_group = []

    for group in groups:
        group_data = {
            'group_name': group.name,
            'students': []
        }
        students = User.objects.filter(
            profile__group=group, userresult__quiz=quiz
        ).select_related('profile').distinct()
        for user in students:
            group_data['students'].append(get_user_stats(user, quiz, total_questions))
        group_data['students'].sort(key=lambda s: s['full_name'])
        stats_by_group.append(group_data)

    if users_without_group.exists():
        no_group_data = {
            'group_name': 'Без класса',
            'students': []
        }
        for user in users_without_group:
            no_group_data['students'].append(get_user_stats(user, quiz, total_questions))
        no_group_data['students'].sort(key=lambda s: s['full_name'])
        stats_by_group.append(no_group_data)

    return render(request, 'quizzes/quiz_stats.html', {
        'quiz': quiz,
        'total_questions': total_questions,
        'stats_by_group': stats_by_group,
    })

def _score_color_class(score, total):
    """Возвращает Tailwind-классы для бейджа по проценту решённых задач."""
    if total == 0:
        return 'bg-gray-100 text-gray-700'
    pct = score / total * 100
    if pct <= 50:
        return 'bg-red-100 text-red-700'
    elif pct <= 60:
        return 'bg-yellow-100 text-yellow-700'
    elif pct <= 80:
        return 'bg-blue-100 text-blue-700'
    else:
        return 'bg-green-100 text-green-700'


def get_user_stats(user, quiz, total_questions):
    results = UserResult.objects.filter(user=user, quiz=quiz).order_by('-date_completed')
    last_result = results.first()
    best_score = results.aggregate(Max('score'))['score__max']

    full_name = f"{user.last_name} {user.first_name}".strip()
    if not full_name:
        full_name = user.username

    is_ege = hasattr(user, 'profile') and user.profile.is_ege

    return {
        'user': user,
        'full_name': full_name,
        'is_ege': is_ege,
        'attempts_count': results.count(),
        'last_score': last_result.score,
        'best_score': best_score,
        'total_questions': total_questions,
        'best_score_color': _score_color_class(best_score, total_questions),
        'last_duration': last_result.duration,
        'last_date': last_result.date_completed,
    }

@user_passes_test(lambda u: u.is_superuser)
def user_attempts_view(request, quiz_id, user_id):
    quiz = get_object_or_404(Quiz, id=quiz_id)
    user = get_object_or_404(User, id=user_id)
    results = UserResult.objects.filter(quiz=quiz, user=user).order_by('-date_completed')
    
    full_name = f"{user.last_name} {user.first_name}".strip() or user.username
    
    return render(request, 'quizzes/user_attempts.html', {
        'quiz': quiz, 
        'student': user, 
        'student_name': full_name,
        'results': results
    })

@user_passes_test(lambda u: u.is_superuser)
def attempt_detail_view(request, result_id):
    result = get_object_or_404(UserResult, id=result_id)
    answers = result.answers.select_related('question', 'selected_choice').prefetch_related(
        'question__images', 'question__files'
    )

    full_name = f"{result.user.last_name} {result.user.first_name}".strip() or result.user.username

    return render(request, 'quizzes/attempt_detail.html', {
        'result': result,
        'answers': answers,
        'student_name': full_name
    })


# --- ASYNC CODE SUBMISSION API ---

@login_required
@require_POST
@csrf_protect
def submit_code_view(request, quiz_id, question_id):
    """
    API endpoint for async code submission.
    Creates a CodeSubmission and queues Celery task.
    Returns submission_id for tracking.
    """
    quiz = get_object_or_404(Quiz, id=quiz_id)
    question = get_object_or_404(Question, id=question_id, quiz=quiz)

    # Публичные ЕГЭ — пропускаем проверку назначения
    if not quiz.is_public:
        eff_settings = get_effective_quiz_settings(request.user, quiz)
        if not eff_settings:
            return JsonResponse({'error': 'Тест не назначен'}, status=403)

        # Check time limits
        now = timezone.now()
        if eff_settings['start_date'] and now < eff_settings['start_date']:
            return JsonResponse({'error': 'Тест ещё не начался'}, status=403)
        if eff_settings['end_date'] and now > eff_settings['end_date']:
            return JsonResponse({'error': 'Время теста истекло'}, status=403)

    # Check if question type is code
    if question.question_type != 'code':
        return JsonResponse({'error': 'Вопрос не является задачей на код'}, status=400)

    # Check if already solved (в тренировке разрешаем переотправку)
    if quiz.exam_mode != 'practice':
        already_solved = UserAnswer.objects.filter(
            user_result__user=request.user,
            user_result__quiz=quiz,
            question=question,
            is_correct=True
        ).exists()

        if already_solved:
            return JsonResponse({'error': 'Задача уже решена'}, status=400)

    # Get code from request
    try:
        data = json.loads(request.body)
        code = data.get('code', '').strip()
    except json.JSONDecodeError:
        code = request.POST.get('code', '').strip()

    if not code:
        return JsonResponse({'error': 'Код не может быть пустым'}, status=400)

    # Check for pending/running submission for same question
    existing_submission = CodeSubmission.objects.filter(
        user=request.user,
        quiz=quiz,
        question=question,
        status__in=['pending', 'running']
    ).first()

    if existing_submission:
        return JsonResponse({
            'error': 'Код уже на проверке',
            'submission_id': existing_submission.id,
            'status': existing_submission.status
        }, status=409)

    # Create new submission
    submission = CodeSubmission.objects.create(
        user=request.user,
        quiz=quiz,
        question=question,
        code=code,
        status='pending'
    )

    # Queue Celery task
    try:
        task = check_code_task.delay(submission.id)
        submission.celery_task_id = task.id
        submission.save(update_fields=['celery_task_id'])
    except Exception:
        submission.status = 'error'
        submission.error_log = 'Сервер проверки временно недоступен. Попробуйте через минуту.'
        submission.save(update_fields=['status', 'error_log'])
        return JsonResponse({
            'submission_id': submission.id,
            'status': 'error',
            'error': submission.error_log
        }, status=503)

    return JsonResponse({
        'submission_id': submission.id,
        'status': 'pending',
        'message': 'Код отправлен на проверку'
    })


@login_required
@require_GET
def submission_status_view(request, submission_id):
    """
    API endpoint to check submission status (polling fallback).
    """
    submission = get_object_or_404(
        CodeSubmission,
        id=submission_id,
        user=request.user
    )

    return JsonResponse({
        'submission_id': submission.id,
        'question_id': submission.question_id,
        'status': submission.status,
        'is_correct': submission.is_correct,
        'error_log': submission.error_log,
        'cpu_time_ms': submission.cpu_time_ms,
        'memory_kb': submission.memory_kb,
        'created_at': submission.created_at.isoformat(),
        'completed_at': submission.completed_at.isoformat() if submission.completed_at else None,
    })


@login_required
@require_POST
@csrf_protect
def finish_quiz_view(request, quiz_id):
    """
    API endpoint to finish quiz.
    Waits for all pending submissions, creates UserResult with all answers.
    """
    quiz = get_object_or_404(Quiz, id=quiz_id)

    # Check assignment/availability
    eff_settings = get_effective_quiz_settings(request.user, quiz)
    if not eff_settings:
        return JsonResponse({'error': 'Тест не назначен'}, status=403)

    max_attempts = eff_settings['max_attempts']
    if max_attempts > 0:
        attempts_count = UserResult.objects.filter(user=request.user, quiz=quiz).count()
        if attempts_count >= max_attempts:
            return JsonResponse({'error': 'Попытки исчерпаны'}, status=403)

    # Parse request body early (needed for force flag)
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        data = {}

    force = data.get('force', False)

    # Check for pending/running submissions
    pending_submissions = CodeSubmission.objects.filter(
        user=request.user,
        quiz=quiz,
        status__in=['pending', 'running']
    )

    if pending_submissions.exists() and not force:
        return JsonResponse({
            'error': 'Есть незавершённые проверки',
            'pending_questions': list(pending_submissions.values_list('question_id', flat=True))
        }, status=409)
    # If force=true: proceed with pending submissions — they were submitted
    # in time. Celery will update UserAnswer and recalculate score when done.

    # Get already correctly answered questions
    correctly_answered_question_ids = set(UserAnswer.objects.filter(
        user_result__user=request.user,
        user_result__quiz=quiz,
        is_correct=True
    ).values_list('question_id', flat=True).distinct())

    already_earned_score = len(correctly_answered_question_ids)

    # Get questions to process (not already solved)
    questions_to_process = list(quiz.questions.exclude(id__in=correctly_answered_question_ids))

    # Calculate duration
    duration = None
    start_time_str = request.session.get(f'quiz_{quiz_id}_start')
    if start_time_str:
        start_time = datetime.datetime.fromisoformat(start_time_str)
        end_time = timezone.now()
        duration = end_time - start_time
        if f'quiz_{quiz_id}_start' in request.session:
            del request.session[f'quiz_{quiz_id}_start']

    # Create UserResult
    user_result = UserResult.objects.create(
        user=request.user,
        quiz=quiz,
        score=0,
        duration=duration
    )

    current_attempt_score = 0
    user_answers_to_create = []

    answers_data = data.get('answers', {})

    # Process each question
    for question in questions_to_process:
        user_input = answers_data.get(str(question.id))
        is_correct = False
        selected_choice = None
        text_answer = None
        code_answer = None
        error_log = None
        submission = None

        if question.question_type == 'choice':
            if user_input:
                try:
                    choice = Choice.objects.get(id=int(user_input), question=question)
                    selected_choice = choice
                    if choice.is_correct:
                        is_correct = True
                        current_attempt_score += 1
                except (Choice.DoesNotExist, ValueError):
                    pass

        elif question.question_type == 'text':
            text_answer = user_input
            if user_input and question.correct_text_answer:
                if user_input.strip().lower() == question.correct_text_answer.strip().lower():
                    is_correct = True
                    current_attempt_score += 1

        elif question.question_type == 'code':
            # Get latest completed submission for this question
            latest_submission = CodeSubmission.objects.filter(
                user=request.user,
                quiz=quiz,
                question=question,
                status__in=['success', 'failed']
            ).order_by('-completed_at').first()

            if latest_submission:
                code_answer = latest_submission.code
                is_correct = latest_submission.is_correct or False
                error_log = latest_submission.error_log
                submission = latest_submission
                if is_correct:
                    current_attempt_score += 1
            else:
                # Check for pending/running submission (submitted but still checking)
                pending_sub = CodeSubmission.objects.filter(
                    user=request.user,
                    quiz=quiz,
                    question=question,
                    status__in=['pending', 'running']
                ).order_by('-created_at').first()

                if pending_sub:
                    # Link pending submission — Celery will update score when done
                    code_answer = pending_sub.code
                    submission = pending_sub
                elif user_input:
                    # Never clicked "Проверить" — auto-create submission and queue check
                    new_sub = CodeSubmission.objects.create(
                        user=request.user,
                        quiz=quiz,
                        question=question,
                        code=user_input,
                        status='pending'
                    )
                    try:
                        task = check_code_task.delay(new_sub.id)
                        new_sub.celery_task_id = task.id
                        new_sub.save(update_fields=['celery_task_id'])
                    except Exception:
                        new_sub.status = 'error'
                        new_sub.error_log = 'Сервер проверки временно недоступен'
                        new_sub.completed_at = timezone.now()
                        new_sub.save(update_fields=['status', 'error_log', 'completed_at'])
                    code_answer = user_input
                    submission = new_sub

        user_answers_to_create.append(
            UserAnswer(
                user_result=user_result,
                question=question,
                selected_choice=selected_choice,
                text_answer=text_answer,
                code_answer=code_answer,
                error_log=error_log,
                is_correct=is_correct,
                submission=submission
            )
        )

    # Bulk create answers
    UserAnswer.objects.bulk_create(user_answers_to_create)

    # Calculate final score
    total_score = current_attempt_score + already_earned_score
    user_result.score = total_score
    user_result.save()

    total_questions = quiz.questions.count()

    # Get failed answers for response
    failed_questions = [
        {
            'id': ua.question_id,
            'title': ua.question.get_title(),
            'error_log': ua.error_log
        }
        for ua in user_answers_to_create if not ua.is_correct
    ]

    # Count pending code checks (submitted but still being checked by Celery)
    pending_checks = sum(
        1 for ua in user_answers_to_create
        if ua.submission and ua.submission.status in ('pending', 'running')
    )

    return JsonResponse({
        'success': True,
        'result_id': user_result.id,
        'score': total_score,
        'total': total_questions,
        'failed_questions': failed_questions,
        'pending_checks': pending_checks,
        'redirect_url': f'/quizzes/{quiz_id}/'
    })


# --- HELP REQUEST SYSTEM ---

def _serialize_comment(comment):
    """Сериализация HelpComment в dict для JSON."""
    return {
        'id': comment.id,
        'author': comment.author.get_full_name() or comment.author.username,
        'author_id': comment.author_id,
        'is_teacher': comment.author.is_superuser,
        'text': comment.text,
        'line_number': comment.line_number,
        'code_snapshot': comment.code_snapshot,
        'created_at': comment.created_at.isoformat(),
    }


@login_required
def help_request_view(request, quiz_id, question_id):
    """
    GET: Получить тред + все комментарии (JSON).
    POST: Создать/дополнить HelpRequest, добавить HelpComment.
    """
    quiz = get_object_or_404(Quiz, id=quiz_id)
    question = get_object_or_404(Question, id=question_id, quiz=quiz)

    # Только для code-вопросов
    if question.question_type != 'code':
        return JsonResponse({'error': 'Помощь доступна только для задач с кодом'}, status=400)

    # Проверяем доступ
    eff_settings = get_effective_quiz_settings(request.user, quiz)
    if not eff_settings and not request.user.is_superuser:
        return JsonResponse({'error': 'Тест не назначен'}, status=403)

    if request.method == 'GET':
        try:
            hr = HelpRequest.objects.get(student=request.user, question=question)
            comments = hr.comments.select_related('author').all()
            # Отмечаем как прочитанное только при явном открытии диалога
            if hr.has_unread_for_student and request.GET.get('mark_read') == '1':
                hr.has_unread_for_student = False
                hr.save(update_fields=['has_unread_for_student'])
            return JsonResponse({
                'help_request_id': hr.id,
                'status': hr.status,
                'comments': [_serialize_comment(c) for c in comments],
            })
        except HelpRequest.DoesNotExist:
            return JsonResponse({
                'help_request_id': None,
                'status': None,
                'comments': [],
            })

    elif request.method == 'POST':
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Невалидный JSON'}, status=400)

        text = data.get('text', '').strip()
        if not text:
            return JsonResponse({'error': 'Текст комментария не может быть пустым'}, status=400)
        if len(text) > 10000:
            return JsonResponse({'error': 'Комментарий не может превышать 10000 символов'}, status=400)

        line_number = data.get('line_number')
        code_snapshot = data.get('code_snapshot')

        # Создаём или получаем HelpRequest
        hr, created = HelpRequest.objects.get_or_create(
            student=request.user,
            question=question,
            defaults={'quiz': quiz}
        )

        # Если запрос был решён — переоткрываем
        if hr.status == 'resolved':
            hr.status = 'open'

        hr.has_unread_for_teacher = True
        hr.save(update_fields=['status', 'has_unread_for_teacher', 'updated_at'])

        # Создаём комментарий
        comment = HelpComment.objects.create(
            help_request=hr,
            author=request.user,
            text=text,
            line_number=line_number,
            code_snapshot=code_snapshot,
        )

        # WebSocket-нотификация учителю
        _send_help_ws_notification(hr, comment, is_teacher_reply=False)

        comments = hr.comments.select_related('author').all()
        return JsonResponse({
            'help_request_id': hr.id,
            'status': hr.status,
            'comment': _serialize_comment(comment),
            'comments': [_serialize_comment(c) for c in comments],
        })

    return JsonResponse({'error': 'Method not allowed'}, status=405)


@user_passes_test(lambda u: u.is_superuser)
def help_requests_list_view(request):
    """Дашборд учителя: список запросов помощи."""
    status_filter = request.GET.get('status', 'open')

    qs = HelpRequest.objects.select_related('student', 'question', 'quiz').order_by('-updated_at')

    if status_filter == 'open':
        qs = qs.filter(status='open')
    elif status_filter == 'answered':
        qs = qs.filter(status='answered')
    elif status_filter == 'resolved':
        qs = qs.filter(status='resolved')
    # 'all' — без фильтра

    # Добавляем последний комментарий для превью
    help_requests = list(qs)
    for hr in help_requests:
        hr.last_comment = hr.comments.select_related('author').last()

    return render(request, 'quizzes/help_requests_list.html', {
        'help_requests': help_requests,
        'status_filter': status_filter,
    })


@user_passes_test(lambda u: u.is_superuser)
def help_request_review_view(request, help_request_id):
    """Страница code review для учителя."""
    hr = get_object_or_404(
        HelpRequest.objects.select_related('student', 'question', 'quiz'),
        id=help_request_id
    )
    comments = hr.comments.select_related('author').all()

    # Отмечаем как прочитанное для учителя
    if hr.has_unread_for_teacher:
        hr.has_unread_for_teacher = False
        hr.save(update_fields=['has_unread_for_teacher'])

    # Получаем код: из последнего снапшота или из последней CodeSubmission
    code = ''
    for c in reversed(list(comments)):
        if c.code_snapshot:
            code = c.code_snapshot
            break
    if not code:
        last_sub = CodeSubmission.objects.filter(
            user=hr.student, question=hr.question
        ).order_by('-created_at').first()
        if last_sub:
            code = last_sub.code

    # Группируем line-комментарии по строкам
    line_comments = {}
    general_comments = []
    for c in comments:
        if c.line_number:
            line_comments.setdefault(c.line_number, []).append(c)
        else:
            general_comments.append(c)

    return render(request, 'quizzes/help_request_review.html', {
        'hr': hr,
        'comments': comments,
        'code': code,
        'line_comments_json': json.dumps({
            str(k): [_serialize_comment(c) for c in v]
            for k, v in line_comments.items()
        }),
        'general_comments': general_comments,
    })


@user_passes_test(lambda u: u.is_superuser)
@require_POST
def help_request_reply_view(request, help_request_id):
    """Учитель отправляет ответ."""
    hr = get_object_or_404(HelpRequest, id=help_request_id)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Невалидный JSON'}, status=400)

    text = data.get('text', '').strip()
    if not text:
        return JsonResponse({'error': 'Текст не может быть пустым'}, status=400)
    if len(text) > 10000:
        return JsonResponse({'error': 'Комментарий не может превышать 10000 символов'}, status=400)

    line_number = data.get('line_number')

    comment = HelpComment.objects.create(
        help_request=hr,
        author=request.user,
        text=text,
        line_number=line_number,
    )

    hr.has_unread_for_student = True
    hr.has_unread_for_teacher = False
    hr.status = 'answered'
    hr.save(update_fields=['status', 'has_unread_for_student', 'has_unread_for_teacher', 'updated_at'])

    # WebSocket-нотификация ученику
    _send_help_ws_notification(hr, comment, is_teacher_reply=True)

    return JsonResponse({
        'comment': _serialize_comment(comment),
        'status': hr.status,
    })


@user_passes_test(lambda u: u.is_superuser)
@require_POST
def help_request_resolve_view(request, help_request_id):
    """Учитель помечает запрос как решённый."""
    hr = get_object_or_404(HelpRequest, id=help_request_id)
    hr.status = 'resolved'
    hr.has_unread_for_student = True
    hr.has_unread_for_teacher = False
    hr.save(update_fields=['status', 'has_unread_for_student', 'has_unread_for_teacher', 'updated_at'])

    # Нотификация ученику
    _send_help_ws_notification(hr, None, is_teacher_reply=True, resolved=True)

    return JsonResponse({'status': 'resolved'})


@login_required
def help_unread_count_view(request):
    """Счётчик непрочитанных (polling fallback)."""
    if request.user.is_superuser:
        count = HelpRequest.objects.filter(has_unread_for_teacher=True).exclude(status='resolved').count()
    else:
        count = HelpRequest.objects.filter(student=request.user, has_unread_for_student=True).count()
    return JsonResponse({'unread_count': count})


@login_required
def help_my_notifications_view(request):
    """Список уведомлений ученика: непрочитанные ответы учителя (JSON)."""
    if request.user.is_superuser:
        return JsonResponse({'notifications': []})

    hrs = HelpRequest.objects.filter(
        student=request.user,
        has_unread_for_student=True,
    ).select_related('question', 'quiz').order_by('-updated_at')[:20]

    notifications = []
    for hr in hrs:
        last_teacher_comment = hr.comments.filter(
            author__is_superuser=True
        ).order_by('-created_at').first()

        notifications.append({
            'id': hr.id,
            'quiz_id': hr.quiz_id,
            'quiz_title': hr.quiz.title,
            'question_id': hr.question_id,
            'question_title': hr.question.get_title(),
            'status': hr.status,
            'preview': last_teacher_comment.text[:100] if last_teacher_comment else '',
            'teacher_name': (last_teacher_comment.author.get_full_name()
                             or last_teacher_comment.author.username) if last_teacher_comment else '',
            'updated_at': hr.updated_at.isoformat(),
        })

    return JsonResponse({'notifications': notifications})


def _send_help_ws_notification(hr, comment, is_teacher_reply, resolved=False):
    """Отправляет WebSocket-нотификацию через channel layer."""
    try:
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync

        channel_layer = get_channel_layer()
        if not channel_layer:
            return

        comment_data = _serialize_comment(comment) if comment else None

        if is_teacher_reply:
            # Ученику через quiz-consumer (inline на quiz_detail)
            quiz_group = f"user_{hr.student_id}_quiz_{hr.quiz_id}"
            async_to_sync(channel_layer.group_send)(quiz_group, {
                'type': 'help_comment_update',
                'question_id': hr.question_id,
                'comment': comment_data,
                'status': hr.status,
                'resolved': resolved,
            })
            # Ученику через notification consumer (бейдж)
            notif_group = f"notifications_{hr.student_id}"
            async_to_sync(channel_layer.group_send)(notif_group, {
                'type': 'help_notification',
                'help_request_id': hr.id,
                'question_id': hr.question_id,
                'quiz_id': hr.quiz_id,
            })
        else:
            # Учителям через notification consumer (бейдж)
            async_to_sync(channel_layer.group_send)('notifications_teachers', {
                'type': 'help_notification',
                'help_request_id': hr.id,
                'question_id': hr.question_id,
                'quiz_id': hr.quiz_id,
                'student_name': hr.student.get_full_name() or hr.student.username,
            })
    except Exception:
        # WS нотификации не критичны — есть polling fallback
        pass
