"""
Эндпоинты самостоятельной работы: ученик пишет, учитель ведёт.

Для ученика – вход, сама работа, автосохранение черновика, журнал надзора,
сдача, балл и итог. Для учителя – открыть и закрыть работу класса, минуты на
неё, разморозка и оценка. Ученику отдаются три страницы, учителю – пульт;
остальное – JSON/POST.
"""
import json
import os

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Count, Q
from django.db.models import prefetch_related_objects
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from accounts.models import StudentGroup
from accounts.templatetags.profile_tags import surname_first
from textbook.models import Section

from . import classwork
from .models import ClassworkAttempt, Question, Quiz
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
    count = quiz.questions.count()
    drawn = quiz.classwork_size
    if drawn and drawn >= count:
        drawn = None
    return render(request, 'quizzes/classwork_intro.html', {
        'quiz': quiz,
        'open': classwork.window_open(quiz, request.user),
        'minutes': classwork.minutes(quiz),
        'count': count,
        'drawn': drawn,
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
    attempt = _attempt(request, pk)
    if classwork.is_expired(attempt):
        classwork.finalize(attempt)
    if attempt.is_finished:
        return redirect('classwork:result', pk=attempt.pk)

    quiz = attempt.quiz
    # Набор зафиксирован при старте: перезагрузка страницы не перемешивает
    # задачи заново, и сосед по парте видит другой набор.
    questions = classwork.attempt_questions(attempt)
    # Варианты, картинки и файлы – тремя запросами на весь набор: шаблон
    # обходит их у каждой задачи, и без предзагрузки это был бы N+1.
    prefetch_related_objects(questions, 'choices', 'images', 'files')
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
    attempt = _attempt(request, pk)
    if not attempt.is_finished:
        return redirect('classwork:work', pk=attempt.pk)

    quiz = attempt.quiz
    released = quiz.check_released()
    return render(request, 'quizzes/classwork_result.html', {
        'quiz': quiz,
        'attempt': attempt,
        'score': classwork.score(attempt.result),
        'max': classwork.attempt_max(attempt),
        'pending': classwork.pending(attempt.result),
        'released': released,
        'tasks_json': js_json(_task_rows(attempt) if released else []),
        'review': _review(attempt) if released else [],
    })


def _review(attempt):
    """
    Задачи попытки с ответом ученика: условие, свой код, вход в «Решения других».

    Только после закрытия работы – то же правило, что у списка статусов и у
    самой галереи (solutions.can_view): пока класс пишет, условие с кодом
    соседа по парте – готовая подсказка.
    """
    questions = classwork.attempt_questions(attempt)
    prefetch_related_objects(questions, 'images', 'files')
    answers = {}
    if attempt.result_id:
        answers = {answer.question_id: answer for answer
                   in attempt.result.answers.select_related('submission')}
    for question in questions:
        question.my_answer = answers.get(question.id)
    return questions


def _task_rows(attempt):
    """
    Разбор попытки по задачам: номер, заголовок, статус ok / wrong / pending.

    Отдаётся и при открытии страницы, и в каждом ответе score_view: код
    проверяется после сдачи, и список, нарисованный один раз, оставался с
    «проверяется» у задач, которые давно проверены, – рядом с барабаном,
    уже вставшим на итоговом балле.
    """
    if not attempt.result_id:
        return []
    rows = {
        answer.question_id: answer
        for answer in attempt.result.answers.select_related('submission')
    }
    tasks = []
    for number, question in enumerate(classwork.attempt_questions(attempt), 1):
        answer = rows.get(question.id)
        if answer is None:
            continue
        if answer.submission_id and answer.submission.status in ('pending', 'running'):
            status = 'pending'
        else:
            status = 'ok' if answer.is_correct else 'wrong'
        tasks.append({'number': number, 'title': question.get_title(), 'status': status})
    return tasks


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
    released = attempt.quiz.check_released()
    return JsonResponse({
        'score': classwork.score(attempt.result),
        'max': classwork.attempt_max(attempt),
        'pending': classwork.pending(attempt.result),
        'released': released,
        # Разбор – только после закрытия работы, как и на самой странице.
        'tasks': _task_rows(attempt) if released else [],
    })


@login_required
@user_passes_test(_teacher)
@require_POST
def control_view(request, quiz_id):
    """Панель учителя: начать, запланировать, отменить и закрыть работу класса."""
    from .views_practice import _local_datetime

    quiz = get_object_or_404(Quiz, id=quiz_id, quiz_type='classwork')
    action = request.POST.get('action')
    group_id = request.POST.get('group') or ''
    group = StudentGroup.objects.filter(id=group_id).first() if group_id.isdigit() else None

    if action == 'start' and group:
        classwork.open_for_group(quiz, group)
    elif action == 'schedule' and group:
        start = _local_datetime(request.POST.get('start'))
        end = _local_datetime(request.POST.get('end'))
        if start is None:
            messages.error(request, 'Нужно начало работы.')
        elif end is not None and end <= start:
            messages.error(request, 'Конец раньше начала.')
        else:
            classwork.open_for_group(quiz, group, start=start, end=end)
    elif action == 'cancel' and group:
        if not classwork.cancel(quiz, group):
            messages.error(request, 'Работу уже начали – её можно только закрыть.')
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


# --- управление работами ---

def _section(value):
    """Блок из формы: id или None (группа «Без блока»)."""
    return Section.objects.filter(id=int(value)).first() if str(value).isdigit() else None


def _minutes(value):
    """Минуты из формы: 1–235 или None (у самостоятельной это 40)."""
    value = (value or '').strip()
    return int(value) if value.isdigit() and 1 <= int(value) <= 235 else None


def _size(value):
    """«Задач каждому» из формы: целое ≥1 или None (все задачи).

    Больше банка – допустимо и значит «все»: число правят до того, как банк
    набран, и запрещать заранее завышенное значение было бы вредно.
    """
    value = (value or '').strip()
    if not value.isdigit():
        return None
    number = int(value)
    return number if 1 <= number <= 32767 else None


@login_required
@user_passes_test(_teacher)
@require_POST
def create_view(request):
    """Новая самостоятельная: название, блок и минуты – остальное наборется в edit."""
    title = (request.POST.get('title') or '').strip()
    if not title:
        messages.error(request, 'Название самостоятельной пустое.')
        return redirect('classwork:list')
    quiz = Quiz.objects.create(
        title=title, quiz_type='classwork', max_attempts=1,
        section=_section(request.POST.get('section')),
        check_minutes=_minutes(request.POST.get('minutes')),
    )
    return redirect('classwork:edit', quiz_id=quiz.id)


@login_required
@user_passes_test(_teacher)
@require_POST
def import_view(request):
    """Работа из JSON формата load_quiz – той же функцией, что у команды."""
    upload = request.FILES.get('file')
    if upload is None:
        messages.error(request, 'Выберите JSON-файл.')
        return redirect('classwork:list')
    try:
        data = json.loads(upload.read().decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError):
        messages.error(request, 'Файл не читается как JSON в кодировке UTF-8.')
        return redirect('classwork:list')
    try:
        quiz = classwork.import_json(
            data, _section(request.POST.get('section')), request.user)
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect('classwork:list')
    return redirect('classwork:edit', quiz_id=quiz.id)


@login_required
@user_passes_test(_teacher)
def edit_view(request, quiz_id):
    """Свойства работы, её задачи и набор задач из блока учебника."""
    quiz = get_object_or_404(Quiz, id=quiz_id, quiz_type='classwork')

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'meta':
            title = (request.POST.get('title') or '').strip()
            if not title:
                messages.error(request, 'Название пустое.')
            else:
                quiz.title = title
                quiz.section = _section(request.POST.get('section'))
                quiz.check_minutes = _minutes(request.POST.get('minutes'))
                quiz.classwork_size = _size(request.POST.get('classwork_size'))
                quiz.save(update_fields=['title', 'section', 'check_minutes',
                                         'classwork_size'])
                messages.success(request, 'Сохранено.')
        elif action == 'topics':
            # Темы и баллы правятся и после начала работы: балл сданной
            # попытки уже посчитан и в UserAnswer записан, поэтому прошлые
            # работы не пересчитываются.
            questions = list(quiz.questions.all())
            for question in questions:
                topic = request.POST.get(f'topic_{question.id}')
                if topic is not None:
                    question.topic = topic.strip()[:200]
                points = (request.POST.get(f'points_{question.id}') or '').strip()
                if points.isdigit() and 1 <= int(points) <= 10:
                    question.points = int(points)
            Question.objects.bulk_update(questions, ['topic', 'points'])
            messages.success(request, 'Темы и баллы сохранены.')
        elif action == 'remove':
            value = request.POST.get('question', '')
            if classwork.has_answers(quiz):
                messages.error(request, 'Работу уже писали – убрать задачу нельзя, '
                                        'ответы учеников пропали бы.')
            elif value.isdigit():
                quiz.questions.filter(id=int(value)).delete()
                messages.success(request, 'Задача убрана.')
        elif action == 'add':
            # Только задачи из показанных источников: скрытый id чужого теста
            # не должен давать копию в работу.
            candidates = {q.id for group in classwork.sources(quiz)
                          for q in group['questions']}
            chosen = [int(v) for v in request.POST.getlist('add')
                      if v.isdigit() and int(v) in candidates]
            questions = list(Question.objects.filter(id__in=chosen).order_by('id'))
            for question in questions:
                classwork.copy_question(question, quiz)
            messages.success(request, f'Добавлено задач: {len(questions)}.')
        return redirect('classwork:edit', quiz_id=quiz.id)

    from .views import _sort_questions

    questions = list(quiz.questions.all())
    _sort_questions(quiz, questions)
    drawn = quiz.classwork_size
    if drawn and drawn >= len(questions):
        drawn = None
    return render(request, 'quizzes/classwork_edit.html', {
        'quiz': quiz,
        'questions': questions,
        'sources': classwork.sources(quiz),
        'has_answers': classwork.has_answers(quiz),
        'sections': Section.objects.order_by('order', 'title'),
        'max_score': classwork.max_score(quiz),
        'minutes': classwork.minutes(quiz),
        'topics': classwork.topic_counts(quiz),
        'drawn': drawn,
    })


@login_required
@user_passes_test(_teacher)
@require_GET
def preview_view(request, quiz_id):
    """Все задачи с ответами – вычитать работу до урока."""
    from .views import _sort_questions

    quiz = get_object_or_404(Quiz, id=quiz_id, quiz_type='classwork')
    questions = list(quiz.questions.prefetch_related('choices', 'test_cases', 'images', 'files'))
    _sort_questions(quiz, questions)
    drawn = quiz.classwork_size
    if drawn and drawn >= len(questions):
        drawn = None
    return render(request, 'quizzes/classwork_preview.html', {
        'quiz': quiz,
        'questions': questions,
        'max_score': classwork.max_score(quiz),
        'minutes': classwork.minutes(quiz),
        'topics': classwork.topic_counts(quiz),
        'drawn': drawn,
    })


@login_required
@user_passes_test(_teacher)
@require_POST
def try_view(request, quiz_id):
    """«Пройти как ученик»: своя попытка без окна, старую стираем."""
    quiz = get_object_or_404(Quiz, id=quiz_id, quiz_type='classwork')
    attempt = classwork.try_as_teacher(request.user, quiz)
    return redirect('classwork:work', pk=attempt.pk)


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
            'max': None,
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
                # Максимум у каждой попытки свой: задачи достались разные.
                maximum = classwork.attempt_max(attempt)
                auto = classwork.auto_grade(points, maximum)
                row.update({
                    'score': points,
                    'max': maximum,
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
    """
    Все самостоятельные, сгруппированные по блоку учебника.

    Блок – то, по чему учитель ищет работу перед уроком («это по графам»),
    поэтому группы идут в порядке блоков, а «Без блока» – в конце. Сверху
    две формы: завести пустую и загрузить готовый JSON.
    """
    quizzes = (Quiz.objects.filter(quiz_type='classwork')
               .select_related('section')
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

    # Группы в порядке блоков; «Без блока» – последней.
    rows.sort(key=lambda row: (
        row['quiz'].section is None,
        row['quiz'].section.order if row['quiz'].section else 0,
        row['quiz'].section.title if row['quiz'].section else '',
        row['quiz'].title,
    ))
    groups = []
    for row in rows:
        section = row['quiz'].section
        if not groups or groups[-1]['section'] != section:
            groups.append({'section': section, 'rows': []})
        groups[-1]['rows'].append(row)

    default_section = Section.objects.filter(slug=request.GET.get('section', '')).first()
    return render(request, 'quizzes/classwork_list.html', {
        'groups': groups,
        'sections': Section.objects.order_by('order', 'title'),
        'default_section': default_section,
    })


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

    # Состояние окна класса считаем здесь: шаблон не умеет сравнивать даты,
    # а рисовать состояние по «есть ли end_date» нельзя – запланированное
    # окно с концом в будущем ничем не отличается от идущего.
    now = timezone.now()
    if assignment is None or assignment.start_date is None:
        state = 'none'
    elif assignment.start_date > now:
        state = 'scheduled'
    elif assignment.end_date and assignment.end_date <= now:
        state = 'closed'
    else:
        state = 'open'

    return render(request, 'quizzes/classwork_panel.html', {
        'quiz': quiz,
        'groups': groups,
        'has_loose': loose,
        'current_group': current,
        'group': group,
        'assignment': assignment,
        'state': state,
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
