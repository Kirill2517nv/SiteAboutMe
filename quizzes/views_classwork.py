"""
Эндпоинты самостоятельной работы: ученик пишет, учитель ведёт.

Для ученика – вход, сама работа, автосохранение черновика, журнал надзора,
сдача, балл и итог. Для учителя – открыть и закрыть работу класса, минуты на
неё, разморозка и оценка. Ученику отдаются три страницы, учителю – пульт;
остальное – JSON/POST.
"""
import json
import os

from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Count, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from accounts.models import StudentGroup
from accounts.templatetags.profile_tags import surname_first

from . import classwork
from .models import ClassworkAttempt, Quiz
from .utils import js_json

MAX_SECONDS = 36000  # десять часов: больше за урок не бывает, а опечатку срезаем


def _json(request):
    """Тело запроса как словарь. None – битый JSON или не объект."""
    try:
        data = json.loads(request.body or '{}')
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _attempt(request, pk):
    """Попытка только своя: чужой id – 404, а не рассказ о её существовании."""
    return get_object_or_404(ClassworkAttempt, pk=pk, user=request.user)


def _teacher(user):
    return user.is_superuser


@login_required
def intro_view(request, quiz_id):
    """Вход в работу: правила и кнопка «Начать»."""
    quiz = get_object_or_404(Quiz, id=quiz_id, quiz_type='classwork')
    if request.user.is_superuser:
        return redirect('classwork:panel', quiz_id=quiz.id)
    attempt = ClassworkAttempt.objects.filter(user=request.user, quiz=quiz).first()
    if attempt:
        if attempt.is_finished:
            return redirect('classwork:result', pk=attempt.pk)
        return redirect('classwork:work', pk=attempt.pk)
    return render(request, 'quizzes/classwork_intro.html', {
        'quiz': quiz,
        'open': classwork.window_open(quiz, request.user),
        'minutes': classwork.minutes(quiz),
        'count': quiz.questions.count(),
    })


@login_required
@require_POST
def start_view(request, quiz_id):
    quiz = get_object_or_404(Quiz, id=quiz_id, quiz_type='classwork')
    attempt = classwork.start(request.user, quiz)
    if attempt is None:
        return redirect('classwork:intro', quiz_id=quiz.id)
    return redirect('classwork:work', pk=attempt.pk)


@login_required
def work_view(request, pk):
    """Сама работа. Правильных ответов в странице нет – только условия."""
    from .views import _sort_questions

    attempt = _attempt(request, pk)
    if classwork.is_expired(attempt):
        classwork.finalize(attempt)
    if attempt.is_finished:
        return redirect('classwork:result', pk=attempt.pk)

    quiz = attempt.quiz
    questions = list(quiz.questions.prefetch_related('choices', 'images', 'files'))
    _sort_questions(quiz, questions)
    tasks = []
    for question in questions:
        # Имена как их кладёт песочница рядом с программой (quizzes/tasks.py).
        question.file_names = [os.path.basename(f.file.name) for f in question.files.all()]
        tasks.append({
            'id': question.id,
            'type': question.question_type,
            'title': question.get_title(),
            'files': question.file_names,
        })
    return render(request, 'quizzes/classwork_work.html', {
        'quiz': quiz,
        'attempt': attempt,
        'questions': questions,
        'tasks_json': js_json(tasks),
        'drafts_json': js_json({'answers': attempt.answers, 'languages': attempt.languages}),
        'left': max(0, int((attempt.deadline - timezone.now()).total_seconds())),
        'frozen': attempt.is_frozen,
    })


@login_required
def result_view(request, pk):
    """Итог: барабан с баллом; разбор задач – только после закрытия работы."""
    from .views import _sort_questions

    attempt = _attempt(request, pk)
    if not attempt.is_finished:
        return redirect('classwork:work', pk=attempt.pk)

    quiz = attempt.quiz
    released = quiz.check_released()
    answers = []
    if released and attempt.result_id:
        questions = list(quiz.questions.all())
        _sort_questions(quiz, questions)
        rows = {
            answer.question_id: answer
            for answer in attempt.result.answers.select_related('question', 'submission')
        }
        for number, question in enumerate(questions, 1):
            answer = rows.get(question.id)
            if answer is None:
                continue
            answers.append({
                'number': number,
                'title': question.get_title(),
                'is_correct': answer.is_correct,
                'pending': bool(answer.submission_id
                                and answer.submission.status in ('pending', 'running')),
            })

    return render(request, 'quizzes/classwork_result.html', {
        'quiz': quiz,
        'attempt': attempt,
        'score': classwork.score(attempt.result),
        'max': classwork.max_score(quiz),
        'pending': classwork.pending(attempt.result),
        'released': released,
        'answers': answers,
    })


@login_required
@require_POST
def save_view(request, pk):
    attempt = _attempt(request, pk)
    data = _json(request)
    if data is None:
        return JsonResponse({'error': 'Невалидный JSON'}, status=400)
    # Проверяем время раньше «заморожена»: если ученик ушёл и время вышло,
    # сдавать надо по часам, а не ждать учителя.
    if classwork.is_expired(attempt):
        classwork.finalize(attempt)
        return JsonResponse({'finished': True}, status=409)
    # Автосохранение, пришедшее уже после «Сдана»: черновик больше не нужен,
    # и отвечать «ok», ничего не записав, было бы враньём.
    if attempt.is_finished:
        return JsonResponse({'finished': True}, status=409)
    if attempt.is_frozen:
        return JsonResponse({'frozen': True}, status=409)
    classwork.save_draft(attempt, data.get('answers'), data.get('languages'))
    return JsonResponse({'ok': True})


@login_required
@require_POST
def event_view(request, pk):
    """Журнал надзора. sendBeacon шлёт FormData, поэтому поля из request.POST."""
    attempt = _attempt(request, pk)
    if attempt.is_finished:
        return HttpResponse(status=204)

    kind = request.POST.get('kind')
    if kind not in ('leave', 'return', 'paste'):
        # Маячок не читает ответ, спорить с ним нечем – просто не пишем мусор.
        return HttpResponse(status=204)

    if kind == 'leave':
        classwork.leave(attempt)
    else:
        raw = request.POST.get('seconds', '')
        seconds = int(raw) if str(raw).isdigit() else 0
        classwork.log(attempt, kind, seconds=max(0, min(seconds, MAX_SECONDS)))
    return HttpResponse(status=204)


@login_required
@require_GET
def state_view(request, pk):
    attempt = _attempt(request, pk)
    if classwork.is_expired(attempt):
        classwork.finalize(attempt)
        attempt.refresh_from_db()
    left = int((attempt.deadline - timezone.now()).total_seconds())
    return JsonResponse({
        'frozen': attempt.is_frozen,
        'finished': attempt.is_finished,
        'left': max(0, left),
    })


@login_required
@require_POST
def finish_view(request, pk):
    attempt = _attempt(request, pk)
    data = _json(request)
    if data is None:
        return JsonResponse({'error': 'Невалидный JSON'}, status=400)
    # Замороженную работу сдаём по последнему сохранённому черновику, а
    # присланное игнорируем: иначе заморозка обходилась бы одним запросом.
    if classwork.accepts_answers(attempt):
        classwork.save_draft(attempt, data.get('answers'), data.get('languages'))
    classwork.finalize(attempt)
    return JsonResponse({'ok': True})


@login_required
@require_GET
def score_view(request, pk):
    attempt = _attempt(request, pk)
    if not attempt.is_finished:
        return JsonResponse({'error': 'Работа не сдана'}, status=409)
    return JsonResponse({
        'score': classwork.score(attempt.result),
        'max': classwork.max_score(attempt.quiz),
        'pending': classwork.pending(attempt.result),
        'released': attempt.quiz.check_released(),
    })


@login_required
@user_passes_test(_teacher)
@require_POST
def control_view(request, quiz_id):
    """Панель учителя: начать и закрыть работу класса, минуты на неё."""
    quiz = get_object_or_404(Quiz, id=quiz_id, quiz_type='classwork')
    action = request.POST.get('action')
    group_id = request.POST.get('group') or ''
    group = StudentGroup.objects.filter(id=group_id).first() if group_id.isdigit() else None

    if action == 'start' and group:
        classwork.open_for_group(quiz, group)
    elif action == 'close' and group:
        classwork.close(quiz, group)
    elif action == 'minutes':
        value = request.POST.get('minutes', '').strip()
        quiz.check_minutes = int(value) if value.isdigit() and 1 <= int(value) <= 235 else None
        quiz.save(update_fields=['check_minutes'])

    # Возврат туда, откуда пришли. Протокол-относительный // не пускаем.
    next_url = request.POST.get('next') or ''
    if not (next_url.startswith('/') and not next_url.startswith('//')):
        next_url = '/'
    return redirect(next_url)


@login_required
@user_passes_test(_teacher)
@require_POST
def unfreeze_view(request, pk):
    attempt = get_object_or_404(ClassworkAttempt, pk=pk)
    classwork.unfreeze(attempt)
    return JsonResponse({'ok': True})


@login_required
@user_passes_test(_teacher)
@require_POST
def grade_view(request, pk):
    attempt = get_object_or_404(ClassworkAttempt, pk=pk)
    value = request.POST.get('grade', '').strip()
    attempt.grade = int(value) if value in ('2', '3', '4', '5') else None
    attempt.save(update_fields=['grade'])
    return JsonResponse({'ok': True, 'grade': classwork.final_grade(attempt)})


# --- панель учителя ---

def _mmss(seconds):
    """Секунды как «M:SS»: столько же, сколько видит ученик на таймере."""
    seconds = max(0, int(seconds))
    return f'{seconds // 60}:{seconds % 60:02d}'


def _rows(quiz, students):
    """
    По строке на ученика; попытки класса – одним запросом.

    Сортировка – по той же строке «Фамилия Имя», что стоит в ячейке, а не
    order_by('last_name'): ученик без фамилии иначе уехал бы в начало, хотя
    в таблице у него логин.
    """
    students = list(students)
    now = timezone.now()
    maximum = classwork.max_score(quiz)
    attempts = {
        attempt.user_id: attempt
        for attempt in ClassworkAttempt.objects.filter(quiz=quiz, user__in=students)
        .select_related('result')
    }

    rows = []
    for student in sorted(students,
                          key=lambda u: surname_first(u).lower().replace('ё', 'е')):
        attempt = attempts.get(student.id)
        if attempt is None:
            state = 'none'
        elif attempt.finished_at:
            state = 'finished'
        elif attempt.frozen_at:
            state = 'frozen'
        else:
            state = 'writing'

        row = {
            'student': student,
            'name': surname_first(student),
            'attempt': attempt,
            'state': state,
            'left_seconds': 0,
            'left': '',
            'frozen_at': None,
            'leaves': 0,
            'away': '0:00',
            'pastes': 0,
            'score': None,
            'max': maximum,
            'pending': False,
            'auto': None,
            'grade': None,
            'final': None,
        }
        if attempt:
            row.update({
                'frozen_at': attempt.frozen_at,
                'leaves': attempt.leaves,
                'away': _mmss(attempt.away_seconds),
                'pastes': attempt.pastes,
                'grade': attempt.grade,
            })
            if state == 'writing':
                row['left_seconds'] = max(
                    0, int((attempt.deadline - now).total_seconds()))
                row['left'] = _mmss(row['left_seconds'])
            elif state == 'finished':
                points = classwork.score(attempt.result)
                auto = classwork.auto_grade(points, maximum)
                row.update({
                    'score': points,
                    'pending': classwork.pending(attempt.result),
                    'auto': auto,
                    'final': attempt.grade if attempt.grade is not None else auto,
                })
        rows.append(row)
    return rows


@login_required
@user_passes_test(_teacher)
@require_GET
def list_view(request):
    """Все самостоятельные: карточка работы со счётчиками и окнами классов."""
    quizzes = (Quiz.objects.filter(quiz_type='classwork')
               .annotate(submitted=Count('classwork_attempts', distinct=True,
                                         filter=Q(classwork_attempts__finished_at__isnull=False)))
               .prefetch_related('questions', 'assignments__group')
               .order_by('title'))
    rows = []
    for quiz in quizzes:
        questions = list(quiz.questions.all())
        rows.append({
            'quiz': quiz,
            'count': len(questions),
            'max': sum(question.points for question in questions),
            'minutes': classwork.minutes(quiz),
            'submitted': quiz.submitted,
            # Личные назначения – не окно класса: в панели они не показываются.
            'assignments': [a for a in quiz.assignments.all() if a.group_id],
        })
    return render(request, 'quizzes/classwork_list.html', {'rows': rows})


@login_required
@user_passes_test(_teacher)
@require_GET
def panel_view(request, quiz_id):
    """Учительский пульт: окно класса, заморозки, оценки."""
    from .views import _class_filter

    quiz = get_object_or_404(Quiz, id=quiz_id, quiz_type='classwork')
    # Первая отрисовка тоже закрывает просроченные: иначе до первого опроса
    # в таблице висело бы «пишет · осталось 0:00».
    classwork.expire(quiz)
    students, groups, loose, current = _class_filter(request)
    group = StudentGroup.objects.filter(id=current).first() if current.isdigit() else None
    assignment = quiz.assignments.filter(group=group).first() if group else None
    return render(request, 'quizzes/classwork_panel.html', {
        'quiz': quiz,
        'groups': groups,
        'has_loose': loose,
        'current_group': current,
        'group': group,
        'assignment': assignment,
        'minutes': classwork.minutes(quiz),
        'max_score': classwork.max_score(quiz),
        'rows': _rows(quiz, students),
    })


@login_required
@user_passes_test(_teacher)
@require_GET
def rows_view(request, quiz_id):
    """Только строки таблицы – для опроса раз в четыре секунды."""
    from .views import _class_filter

    quiz = get_object_or_404(Quiz, id=quiz_id, quiz_type='classwork')
    # Закрытая вкладка ученика иначе держала бы работу незакрытой до учителя.
    classwork.expire(quiz)
    students, _, _, _ = _class_filter(request)
    return render(request, 'quizzes/_classwork_rows.html', {'rows': _rows(quiz, students)})
