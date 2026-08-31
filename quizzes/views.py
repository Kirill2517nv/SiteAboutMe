from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.contrib.auth.decorators import login_required, user_passes_test
from django.utils import timezone
from django.contrib.auth.models import User
from django.db.models import Max, Count, Sum
from django.http import FileResponse, Http404, JsonResponse
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.views.decorators.http import require_POST, require_GET
from django.views.decorators.csrf import csrf_protect
from .models import PracticeItem, Quiz, Choice, UserResult, UserAnswer, TestCase, QuizAssignment, Question, CodeSubmission, QuestionFile, ExamTaskProgress, SolutionAttachment, SolutionLike, HintChoice
from accounts.models import StudentGroup
import datetime
import os
import json
import mimetypes
import re
from urllib.parse import quote
from .utils import js_json, run_code_in_docker
from .tasks import check_code_task

# Константы ЕГЭ переехали в ege_constants.py – их делят между собой views,
# ege_practice, ege_stats и accounts. Импорт оставлен здесь, чтобы старые
# `from quizzes.views import EGE_RECOMMENDED_TIME` продолжали работать.
from .ege_constants import (  # noqa: F401
    EGE_SCORE_CONVERSION, EGE_RECOMMENDED_TIME, EGE_TASK_POINTS,
    EGE_MAX_PRIMARY, EGE_EXAM_MINUTES, EGE_CODE_TASKS,
    ege_time_color, test_score_for,
)
from .ege_constants import EXCLUDED_KINDS, PRACTICE_QUIZ_TYPES
from .ege_scoring import grade as ege_grade


def _natural_sort_key(text):
    """Ключ для натуральной сортировки: 'Задача 2' перед 'Задача 10'."""
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r'(\d+)', text)]


def _sort_questions(quiz, questions):
    """
    Порядок вопросов для показа ученику.

    У самопроверок учебника заголовков нет, и сортировка по get_title()
    раскладывала вопросы по алфавиту текста — то есть в случайном для автора
    порядке. Им нужен порядок создания. Остальным тестам (ЕГЭ) — прежняя
    натуральная сортировка по заголовку «Задача 2, Задача 10».
    """
    if quiz.is_self_check:
        questions.sort(key=lambda q: q.id)
    else:
        questions.sort(key=lambda q: _natural_sort_key(q.get_title()))


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

from .ege_scoring import outputs_match


def get_effective_quiz_settings(user, quiz):
    """
    Returns a dict with effective start_date, end_date, max_attempts
    based on user/group assignments.
    Returns None if no assignment found for this user (unless superuser).
    """
    # Тесты-самопроверки учебника доступны любому авторизованному ученику
    # (доступ гейтится статьёй учебника, а не назначением на группу).
    if getattr(quiz, 'is_self_check', False) and user.is_authenticated:
        # Единственный гейт для них — публикация блока: спрятанный блок не
        # должен отдавать свои задачи по прямой ссылке /quizzes/<id>/.
        from textbook.services import quiz_is_hidden
        if quiz_is_hidden(quiz) and not user.is_superuser:
            return None
        return {
            'start_date': quiz.start_date,
            'end_date': quiz.end_date,
            'max_attempts': quiz.max_attempts,
        }

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
    ).select_related('question', 'user_result__user', 'user_result__user__profile')

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


def _student_list():
    """Ученики для панели учителя – тот же список и порядок, что в профиле."""
    return (
        User.objects.filter(is_superuser=False)
        .select_related('profile__group')
        .order_by('profile__group__name', 'last_name', 'username')
    )


def _viewed_student(request):
    """
    Чей прогресс открыт на хабе: None – свой, иначе ученик из ?student=<id>.

    Критерий доступа тот же, что у чужого профиля (accounts.ProfileView):
    смотреть чужие цифры может только суперпользователь.
    """
    student_id = request.GET.get('student')
    if not student_id:
        return None
    if not request.user.is_superuser:
        raise PermissionDenied('Чужой прогресс открыт учителю')
    if not student_id.isdigit():
        raise Http404('Нет такого ученика')
    return get_object_or_404(User, id=int(student_id), is_superuser=False)


@user_passes_test(lambda user: user.is_superuser)
def ege_class_view(request):
    """
    Сравнительная таблица класса: по строке на ученика, по разделу на группу.

    Существует затем, что переключаться между двумя десятками личных страниц,
    держа цифры в голове, невозможно. В строке ровно то, по чему принимают
    решение перед занятием: прогноз балла и на скольких заданиях он держится,
    последний написанный вариант, долг по ошибкам, три самые дорогие дыры и
    график активности по неделям.

    Числа считает ege_stats.class_rows теми же формулами, что и личная вкладка:
    учитель держит таблицу и карточку ученика открытыми рядом.

    Показывается один класс за раз (?group=<id>), а не все сразу: классов со
    временем становится много, и страница из пяти таблиц по два десятка строк
    перестаёт отвечать на свой единственный вопрос – «с кем работать сегодня».
    ?group=all остаётся для тех редких случаев, когда сравнить нужно поперёк
    классов, ?group=none – для учеников, которых ещё никуда не записали.
    """
    from . import ege_stats

    students = _student_list()
    groups = list(
        StudentGroup.objects
        .filter(students__user__is_superuser=False).distinct().order_by('name')
    )
    loose = students.filter(profile__group__isnull=True).exists()

    # По умолчанию – первый класс списка: конкретный класс перед глазами полезнее
    # общего свода, а «все» и «без класса» стоят рядом отдельными вкладками.
    current = request.GET.get('group') or (str(groups[0].id) if groups else 'all')
    # id класса приходит из адреса: нечисловой ?group= уронил бы фильтр по
    # profile__group_id пятисоткой. Мусор трактуем как «все».
    if not (current in ('all', 'none') or current.isdigit()):
        current = 'all'
    if current == 'none':
        students = students.filter(profile__group__isnull=True)
    elif current != 'all':
        students = students.filter(profile__group_id=current)

    return render(request, 'quizzes/ege_class.html', {
        'rows': ege_stats.class_rows(students),
        'students': _student_list(),
        'groups': groups,
        'has_loose': loose,
        'current_group': current,
    })


@user_passes_test(lambda user: user.is_superuser)
def ege_student_mistakes_view(request, user_id):
    """
    Долг ученика по ошибкам глазами учителя: условие задачи и что он ответил.

    Это не сессия: сессию нельзя открыть чужую и «просто посмотреть» – её
    задачи выбираются в момент старта и попадают в статистику того, кто её
    завёл. Здесь тот же набор задач, что получит ученик, нажав «Работа над
    ошибками», но в режиме чтения: условие, ответ ученика, и под кнопкой –
    правильный ответ, как на остальных страницах учителя.

    Отбор повторяет ege_practice.mistake_count буквально – счётчик в таблице
    класса ведёт сюда, и число задач на странице обязано совпасть с числом на
    кнопке, иначе ссылке перестанут верить.
    """
    student = get_object_or_404(User, id=user_id, is_superuser=False)

    items = (
        PracticeItem.objects
        .filter(session__user=student, answered_at__isnull=False,
                question__quiz__quiz_type__in=PRACTICE_QUIZ_TYPES)
        .exclude(session__kind__in=EXCLUDED_KINDS)
        .exclude(carried=True)
        .select_related('question', 'submission', 'session')
        .prefetch_related('question__images', 'question__test_cases')
        .order_by('question_id', '-answered_at')
    )

    # Первая строка по задаче – её последняя попытка. Ошибкой задача считается
    # только по ней: провал, закрытый более поздним решением, из долга уходит.
    rows = []
    seen = set()
    for item in items:
        if item.question_id in seen:
            continue
        seen.add(item.question_id)
        if item.is_correct is not False:
            continue
        rows.append(item)

    # Группируем по заданию: учитель разбирает тему целиком, а не задачу за
    # задачей вразнобой. Внутри задания сверху свежие ошибки.
    by_task = {}
    for item in rows:
        by_task.setdefault(item.question.ege_number or 0, []).append(item)
    groups = [
        {'number': number, 'items': sorted(items_, key=lambda i: i.answered_at, reverse=True)}
        for number, items_ in sorted(by_task.items())
    ]

    return render(request, 'quizzes/ege_student_mistakes.html', {
        'student': student,
        'groups': groups,
        'total': len(rows),
    })


def ege_list_view(request):
    """
    Хаб тренажёра: карта 27 заданий, варианты и личный прогресс.

    Сетка заданий стоит первой вкладкой намеренно. Вариант целиком – это почти
    четыре часа, и как ежедневный режим подготовки он не работает; тренировка по
    отдельному заданию помещается в один присест.
    """
    student = _viewed_student(request)
    # Чьи цифры показываем. Учитель открывает ту же страницу с ?student=<id> –
    # отдельного шаблона для чужого прогресса нет намеренно: расхождение между
    # «своей» и «учительской» вёрсткой читалось бы как расхождение в данных.
    target = student or request.user

    quizzes = Quiz.objects.filter(
        quiz_type='exam', is_public=True,
    ).annotate(
        num_questions=Count('questions'),
        total_points=Sum('questions__points'),
    ).order_by('title')

    user_stats = {}
    if target.is_authenticated:
        quiz_ids = [q.id for q in quizzes]
        user_stats = get_user_ege_stats(target, quiz_ids) or {}

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

    from . import ege_stats

    context = {'variants': variants, 'student': student}

    # Панель учителя: список учеников для переключения и ссылка на таблицу класса.
    if request.user.is_superuser:
        context['students'] = _student_list()

    if target.is_authenticated:
        context['overview'] = ege_stats.overview(target)
    else:
        # Гостю показываем ту же сетку заданий, но без личных цифр: карта тем –
        # это ещё и оглавление теории, прятать её за логином незачем. Вкладку
        # прогресса он получает заполненной примером (`is_demo`): пустые
        # карточки не объясняют, ради чего заводить аккаунт.
        context['overview'] = {
            'tasks': ege_stats.task_stats(request.user),
            **ege_stats.demo_overview(),
        }

    return render(request, 'quizzes/ege_list.html', context)


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
        'tasks_json': js_json(tasks_data),
        'last_submissions_json': js_json(last_submissions),
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
    fields_to_update = []
    # Счётчик отвечает на вопрос «с какой попытки решена задача», поэтому после
    # решения он замирает: проверки, сделанные из любопытства после верного
    # ответа, к трудности задачи отношения не имеют.
    if not progress.is_solved:
        progress.attempts_to_solve += 1
        fields_to_update.append('attempts_to_solve')

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
        score = None
        text_answer = None
        code_answer = None
        error_log = None
        submission = None

        if question.question_type == 'text':
            text_answer = user_input
            if user_input:
                # За задания 26 и 27 бывает 1 балл из 2: числа перепутаны
                # местами или верна половина ответа.
                score = ege_grade(question, user_input, question.correct_text_answer or '')
                if score is not None:
                    is_correct = score >= question.points
                    total_score += score
                else:
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
                    # За задания 26 и 27 бывает 1 балл из 2 – он уже посчитан
                    # проверкой и лежит в отправке.
                    score = latest_sub.score
                    if score is not None:
                        total_score += score
                    elif is_correct:
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
            score=submission.score if submission else score,
            submission=submission,
        ))

    UserAnswer.objects.bulk_create(user_answers_to_create)

    user_result.score = total_score
    user_result.save(update_fields=['score'])

    # Обновляем ExamTaskProgress по каждой отвеченной задаче – не только по
    # решённым. Неверный ответ тоже часть работы: без него точность по вариантам
    # считалась бы по одним удачам.
    for ua in user_answers_to_create:
        answered = bool(ua.text_answer or ua.code_answer or ua.selected_choice_id)
        if not answered:
            continue
        progress, _ = ExamTaskProgress.objects.get_or_create(
            user=request.user, quiz=quiz, question=ua.question,
        )
        fields = []
        # Попытку засчитываем, только если её ещё никто не засчитал: проверки
        # ответа и отправки кода уже увеличили счётчик, и завершение варианта
        # не должно добавлять к ним лишнюю.
        if not progress.attempts_to_solve:
            progress.attempts_to_solve = 1
            fields.append('attempts_to_solve')
        # Частичный балл задачу не закрывает, но заработанное фиксирует.
        if ua.score is not None and ua.score > (progress.score or 0):
            progress.score = ua.score
            fields.append('score')
        if ua.is_correct and not progress.is_solved:
            progress.is_solved = True
            progress.first_solved_at = timezone.now()
            fields += ['is_solved', 'first_solved_at']
        if fields:
            progress.save(update_fields=fields)

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

    # Суммарное время по каждому пользователю
    user_total_time = {}
    for (uid, qid), secs in time_map.items():
        user_total_time[uid] = user_total_time.get(uid, 0) + secs
    for row in results_matrix:
        total_secs = user_total_time.get(row['user_id'], 0)
        if total_secs > 0:
            h = total_secs // 3600
            m = (total_secs % 3600) // 60
            s = total_secs % 60
            row['total_time'] = f"{h}ч {m:02d}м" if h > 0 else f"{m}м {s:02d}с"
        else:
            row['total_time'] = ''
        row['test_score'] = EGE_SCORE_CONVERSION.get(row['score'], 100 if row['score'] > 29 else 0)

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

    question_types_json = js_json(question_types)
    sort_data_json = js_json(sort_data)

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
                seconds = p.time_spent_seconds if p else 0

                mins, secs = divmod(seconds, 60)
                time_mm_ss = f"{mins}:{secs:02d}" if seconds else ''
                color = ege_time_color(seconds, ege_num)

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
def ege_student_stats_view(request, quiz_id, user_id):
    """Статистика конкретного ученика по варианту ЕГЭ (только для суперпользователя)."""
    if not request.user.is_superuser:
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied

    quiz = get_object_or_404(Quiz, id=quiz_id, quiz_type='exam', is_public=True)
    student = get_object_or_404(User, id=user_id)

    questions = list(quiz.questions.filter(ege_number__isnull=False).order_by('ege_number'))

    progress_qs = ExamTaskProgress.objects.filter(user=student, quiz=quiz).select_related('question')
    progress_map = {p.question_id: p for p in progress_qs}

    stats = []
    for q in questions:
        p = progress_map.get(q.id)
        ege_num = q.ege_number or 0
        seconds = p.time_spent_seconds if p else 0

        mins, secs = divmod(seconds, 60)
        time_mm_ss = f"{mins}:{secs:02d}" if seconds else ''
        color = ege_time_color(seconds, ege_num)

        stats.append({
            'ege_number': ege_num,
            'time_mm_ss': time_mm_ss,
            'attempts': p.attempts_to_solve if p else 0,
            'is_solved': p.is_solved if p else False,
            'color': color,
            'is_code': q.question_type == 'code',
            'cpu_time_ms': p.best_cpu_time_ms if p else None,
            'memory_kb': p.best_memory_kb if p else None,
        })

    full_name = f"{student.last_name} {student.first_name}".strip() or student.username

    return render(request, 'quizzes/ege_student_stats.html', {
        'quiz': quiz,
        'student': student,
        'full_name': full_name,
        'questions': questions,
        'stats': stats,
        'stats_json': js_json(stats),
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

    # Из тестов учебника возвращаемся в учебник, из обычного теста — в список тестов.
    from textbook.services import textbook_link_for_quiz
    textbook_url, back_label, after_finish_url = textbook_link_for_quiz(quiz)
    back_url = textbook_url or reverse('textbook:home')
    back_label = back_label or 'Вернуться в учебник'

    # Check assignment/availability
    eff_settings = get_effective_quiz_settings(request.user, quiz)
    if not eff_settings:
        # Not assigned to this user
        return redirect(back_url)

    start_date = eff_settings['start_date']
    end_date = eff_settings['end_date']
    max_attempts = eff_settings['max_attempts']

    now = timezone.now()

    # Access checks
    read_only = False
    if start_date and now < start_date: return redirect(back_url)

    if end_date and now > end_date:
        if request.method == 'POST':
            return redirect(back_url)
        # GET on expired quiz → read-only mode
        read_only = True

    # Дедлайн блока учебника закрывает и задачи блока, и самопроверки его уроков:
    # решать нельзя, смотреть свои ответы — можно.
    from textbook.services import quiz_is_locked
    if quiz_is_locked(quiz):
        if request.method == 'POST':
            return redirect(back_url)
        read_only = True

    if not read_only and max_attempts > 0:
        attempts_count = UserResult.objects.filter(user=request.user, quiz=quiz).count()
        if attempts_count >= max_attempts: return redirect(back_url)

    # Read-only mode: show all questions with student's best answers
    if read_only:
        all_questions = list(quiz.questions.all())
        _sort_questions(quiz, all_questions)

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
            'back_url': back_url,
            'back_label': back_label,
            'questions_to_show': [],
            'all_questions': all_questions,
            'correctly_answered_ids': set(),
            'last_attempt_codes': {},
            'last_attempt_codes_json': '{}',
            'end_date': end_date,
            'is_admin': request.user.is_superuser,
            'read_only': True,
            'tasks_json': '[]',
            'last_submissions_json': '{}',
            'total_points': sum(q.points for q in all_questions),
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
                    # check_text_answer() учитывает alternative_answers и нормализацию,
                    # инлайновое сравнение их игнорировало.
                    if question.check_text_answer(user_input):
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

                            if not outputs_match(output, test_case.output_data):
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

        # Хук учебника: отметить статью «освоено», если пройдена самопроверка
        if quiz.is_self_check:
            from textbook.services import update_article_mastery
            update_article_mastery(request.user, quiz)

        # Тест учебника — часть урока, а не отдельный «результат теста»:
        # возвращаем ученика туда, откуда он пришёл.
        if after_finish_url:
            return redirect(after_finish_url)

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
    last_attempt_codes_json = js_json({str(k): v for k, v in last_attempt_codes.items()})

    # Все вопросы теста, отсортированные натурально по заголовку
    all_questions = list(quiz.questions.all())
    _sort_questions(quiz, all_questions)

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

    # Последние CodeSubmission для code-задач
    code_questions = [q for q in all_questions if q.question_type == 'code']
    last_submissions = {}
    # Лучшие метрики для code-задач (из всех successful submissions)
    best_metrics = {}  # question_id -> {best_cpu_time_ms, best_cpu_code, best_memory_kb, best_memory_code}
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
        # Лучшие метрики из всех правильных submissions
        best_cpu_sub = CodeSubmission.objects.filter(
            user=request.user, quiz=quiz, question=q,
            is_correct=True, cpu_time_ms__isnull=False,
        ).order_by('cpu_time_ms').first()
        best_mem_sub = CodeSubmission.objects.filter(
            user=request.user, quiz=quiz, question=q,
            is_correct=True, memory_kb__isnull=False,
        ).order_by('memory_kb').first()
        if best_cpu_sub or best_mem_sub:
            best_metrics[q.id] = {
                'best_cpu_time_ms': best_cpu_sub.cpu_time_ms if best_cpu_sub else None,
                'best_cpu_code': best_cpu_sub.code if best_cpu_sub else '',
                'best_memory_kb': best_mem_sub.memory_kb if best_mem_sub else None,
                'best_memory_code': best_mem_sub.code if best_mem_sub else '',
            }

    # Построить tasks_data для Alpine.js (навигация по одной задаче)
    from textbook.services import hint_states
    from textbook.templatetags.textbook_tags import markdownify

    states = hint_states(request.user, quiz, all_questions)
    tasks_data = []
    for q in all_questions:
        task = {
            'id': q.id,
            'type': q.question_type,
            'title': q.get_title(),
            'points': q.points,
            'is_solved': q.is_solved,
            'saved_answer': '',
        }
        # Подсказки нет в задаче, пока она закрыта: ученик не должен знать даже
        # о её существовании (hint_state вернёт None).
        state = states.get(q.id)
        if state:
            task['hint_state'] = state
            if state == 'taken':
                task['hint_html'] = str(markdownify(q.hint))
        if q.question_type == 'choice' and q.is_solved and q.solved_answer:
            task['saved_answer'] = str(q.solved_answer.selected_choice_id or '')
        elif q.question_type == 'text' and q.is_solved and q.solved_answer:
            task['saved_answer'] = q.solved_answer.text_answer or ''
        # Лучшие метрики для code-задач
        if q.question_type == 'code' and q.id in best_metrics:
            bm = best_metrics[q.id]
            task['best_cpu_time_ms'] = bm['best_cpu_time_ms']
            task['best_cpu_code'] = bm['best_cpu_code']
            task['best_memory_kb'] = bm['best_memory_kb']
            task['best_memory_code'] = bm['best_memory_code']
        tasks_data.append(task)

    return render(request, 'quizzes/quiz_detail.html', {
        'quiz': quiz,
        'back_url': back_url,
        'back_label': back_label,
        'questions_to_show': questions_to_show,
        'all_questions': all_questions,
        'correctly_answered_ids': set(correctly_answered_question_ids),
        'last_attempt_codes': last_attempt_codes,
        'last_attempt_codes_json': last_attempt_codes_json,
        'end_date': end_date,
        'is_admin': request.user.is_superuser,
        'tasks_json': js_json(tasks_data),
        'last_submissions_json': js_json(last_submissions),
        'total_points': sum(q.points for q in all_questions),
    })

@login_required
@csrf_protect
def question_hint_view(request, question_id):
    """Подсказка к задаче.

    GET отдаёт только состояние: пока ученик не нажал «показать», текста в
    ответе нет — иначе подсказку можно было бы вычитать из сети, не делая
    выбора. POST с action=take|decline фиксирует выбор (учителю в статистику).
    """
    from textbook.services import hint_state

    question = get_object_or_404(Question.objects.select_related('quiz'), id=question_id)
    # Тот же гейт, что и у страницы теста: без него перебор question_id отдаёт
    # подсказки к задачам чужой группы или спрятанного блока — блочные условия
    # открытия (рубильник, близкий дедлайн) не зависят от назначения теста.
    # Ответ такой же, как у закрытой подсказки: её существование не палим.
    if not get_effective_quiz_settings(request.user, question.quiz):
        return JsonResponse({'state': None})

    state = hint_state(request.user, question)
    if state is None:
        return JsonResponse({'state': None})

    if request.method == 'POST':
        try:
            action = json.loads(request.body or '{}').get('action')
        except json.JSONDecodeError:
            action = None
        accepted = action == 'take'
        HintChoice.objects.update_or_create(
            user=request.user, question=question, defaults={'accepted': accepted}
        )
        state = 'taken' if accepted else 'declined'

    payload = {'state': state}
    if state == 'taken':
        from textbook.templatetags.textbook_tags import markdownify
        payload['hint'] = str(markdownify(question.hint))
    return JsonResponse(payload)


@login_required
@require_POST
def question_check_view(request, question_id):
    """AJAX: вердикт по одному текстовому ответу, без записи результата.

    Мгновенная обратная связь была только у задач на код: текстовый ответ ученик
    узнавал верным или нет лишь после «Сохранить результат». Балл по-прежнему
    выставляет finish_quiz_view – здесь только «верно/неверно», ничего не
    сохраняем и правильный ответ наружу не отдаём.
    """
    question = get_object_or_404(Question.objects.select_related('quiz'), id=question_id)
    # Тот же гейт, что у страницы теста и у подсказки: без него перебором
    # question_id проверяются задачи чужой группы.
    if not get_effective_quiz_settings(request.user, question.quiz):
        return JsonResponse({'error': 'Тест не назначен'}, status=403)

    if question.question_type != 'text':
        return JsonResponse({'error': 'Проверяется только текстовый ответ'}, status=400)

    try:
        answer = (json.loads(request.body or '{}').get('answer') or '').strip()
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Невалидный JSON'}, status=400)

    if not answer:
        return JsonResponse({'error': 'Ответ пуст'}, status=400)

    return JsonResponse({'is_correct': question.check_text_answer(answer)})


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
        'quiz_has_hints': quiz.questions.exclude(hint='').exists(),
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

    # Что ученик выбрал, когда ему предложили подсказку. Ему самому это нигде
    # не показывается — колонка только для учителя.
    hints = HintChoice.objects.filter(user=user, question__quiz=quiz).select_related('question')
    hints_taken = [h.question.get_title() for h in hints if h.accepted]
    hints_declined = [h.question.get_title() for h in hints if not h.accepted]

    return {
        'hints_taken': hints_taken,
        'hints_declined': hints_declined,
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

    from textbook.services import quiz_is_locked
    if quiz_is_locked(quiz):
        return JsonResponse({'error': 'Дедлайн блока прошёл — решения больше не принимаются'},
                            status=403)

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
        'score': submission.score,
        'points': submission.question.points,
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

    from textbook.services import quiz_is_locked, textbook_link_for_quiz
    _, _, after_finish_url = textbook_link_for_quiz(quiz)

    if quiz_is_locked(quiz):
        return JsonResponse({'error': 'Дедлайн блока прошёл — решения больше не принимаются'},
                            status=403)

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
                # check_text_answer() учитывает alternative_answers и нормализацию.
                if question.check_text_answer(user_input):
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
        # Тест учебника закрываем возвратом в учебник, там итог показан бейджем.
        'redirect_url': after_finish_url or '/quizzes/'
    })
