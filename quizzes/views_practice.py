"""
Вью тренажёра ЕГЭ: карточка задания и сессии тренировки.

Отдельный модуль, а не хвост views.py: там уже больше двух тысяч строк, и
подсистема сессий с ними ничем не связана, кроме отправки кода.
"""
import json
from collections import Counter, defaultdict

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from textbook.models import Article, EgeTask

from . import ege_practice, ege_stats
from .ege_scoring import grade as ege_grade
from .ege_constants import (
    EGE_QUIZ_TYPES, EGE_RECOMMENDED_TIME, EGE_TASK_POINTS, EXAM_MINUTES,
    LINKED_GROUP_TITLE, STUDY_MAX_SIZE, ege_time_color,
)
from .models import CodeSubmission, PracticeItem, PracticeSession, Question
from .utils import js_json

# Потолок одной порции времени. Страница досылает время раз в минуту и не
# считает минуты, пока вкладка скрыта, поэтому честная порция всегда мала;
# потолок остаётся защитой от подделанного запроса, а не от забытой вкладки.
MAX_SECONDS_PER_REPORT = 600


def _task_or_404(number):
    if number not in range(1, 28):
        raise PermissionDenied('Нет такого задания ЕГЭ')
    return EgeTask.objects.filter(number=number).first()


def ege_task_view(request, number):
    """
    Карточка задания: теория, личная статистика, старт тренировки.

    Связка 19–21 живёт одной страницей: игра, теория и разбор у них общие, и
    три отдельные карточки с одинаковым текстом ученику только мешали бы.
    Номера 20 и 21 ведут на страницу первого задания связки; статистика при
    этом остаётся раздельной – решает-то он три разные задачи.
    """
    task = _task_or_404(number)

    linked = ege_stats.linked_numbers()
    if number in linked and number != min(linked):
        return redirect('ege:ege_task', number=min(linked))

    # Номера, которые обслуживает эта страница: связка целиком или один номер.
    numbers = sorted(linked) if number in linked else [number]

    articles = list(
        Article.objects
        .filter(track='ege', ege_task__number__in=numbers, is_published=True)
        .order_by('ege_task__number', 'order', 'title')
    )

    counts = ege_practice.available_counts(number, request.user)

    stats = None
    stats_list = []
    if request.user.is_authenticated:
        rows = {item['number']: item for item in ege_stats.task_stats(request.user)}
        stats = rows.get(number)
        stats_list = [rows[n] for n in numbers if n in rows]

    # Флаги снимаем при показе: иначе предупреждение висело бы на карточке
    # до конца сессии браузера.
    empty = request.session.pop('ege_practice_empty', False)
    locked_warning = request.session.pop('ege_exam_locked', False)

    exam_open, study_solved, unlock_threshold = (
        ege_practice.exam_access(request.user, number)
        if request.user.is_authenticated else (False, 0, 0)
    )

    # Сколько задач в банке всего и сколько ученик уже закрыл: без этой пары
    # «Всего задач: 22» врало бы – часть из них ему больше не выдадут.
    bank_total = ege_practice.bank_queryset(number).count()
    solved_count = len(ege_practice._solved_question_ids(request.user, number)) \
        if request.user.is_authenticated else 0

    running_exam = ege_practice.active_exam(request.user)         if request.user.is_authenticated else None

    # Связка 19–21: три задания на одном условии игры. Ученику нужно сказать об
    # этом до старта – иначе тройка в сессии выглядит как сбой отбора.
    group_total = ege_practice.group_count(number) if number in linked else 0
    span = ege_practice.group_span(number) if number in linked else 1

    # У связанных заданий единица измерения – связка, а не задача: форма
    # спрашивает «сколько троек», и норматив пересчитывается в них же.
    default_size = ege_practice.study_session_size(number)
    max_size = STUDY_MAX_SIZE
    if span > 1:
        default_size = max(1, default_size // span)
        max_size = max(1, min(group_total, STUDY_MAX_SIZE // span))

    return render(request, 'quizzes/ege_task.html', {
        'number': number,
        'running_exam': running_exam,
        'running_exam_left': (
            int((running_exam.deadline - timezone.now()).total_seconds() // 60) + 1
            if running_exam else 0
        ),
        'task': task,
        'empty_warning': empty,
        'articles': articles,
        'counts': counts,
        'bank_total': bank_total,
        'solved_count': solved_count,
        'stats': stats,
        'points': EGE_TASK_POINTS[number],
        'recommended_min': EGE_RECOMMENDED_TIME.get(number, 5),
        'default_size': default_size,
        'exam_size': ege_practice.exam_session_size(number),
        'exam_open': exam_open,
        'exam_locked_warning': locked_warning,
        'study_solved': study_solved,
        'unlock_threshold': unlock_threshold,
        'classroom_pool': ege_practice.classroom_pool_size(number),
        'classroom_open': ege_practice.classroom_open(number),
        'classroom_enabled': bool(task and task.classroom_enabled),
        'max_size': max_size,
        'exam_minutes': EXAM_MINUTES,
        'exam_pool': ege_practice.exam_pool_size(number),
        'linked': number in linked,
        'linked_range': f'{min(linked)}–{max(linked)}' if linked else '',
        'linked_size': len(linked),
        'linked_lead': min(linked) if linked else 0,
        'group_span': span,
        'group_total': group_total,
        'stats_list': stats_list,
        # Заголовок страницы: у связки он свой, «Теория игр» на все три задания.
        'page_badge': '-'.join(str(n) for n in (numbers[0], numbers[-1])) if len(numbers) > 1 else str(number),
        'page_title': LINKED_GROUP_TITLE if len(numbers) > 1 else (task.title if task else f'Задание {number}'),
        'page_points': sum(EGE_TASK_POINTS[n] for n in numbers),
        'page_minutes': sum(EGE_RECOMMENDED_TIME.get(n, 5) for n in numbers),
    })


@login_required
@require_POST
def classroom_toggle_view(request, number):
    """
    Учитель включает и выключает набор для урока, не заходя в админку.

    Ровно то же поле EgeTask.classroom_enabled, что и в админке: перед занятием
    рубильник дёргают каждый раз, и ходить ради одного флажка в /admin/ –
    лишний десяток кликов посреди урока.
    """
    if not request.user.is_superuser:
        raise PermissionDenied('Набор для урока включает учитель')

    task = get_object_or_404(EgeTask, number=number)
    task.classroom_enabled = not task.classroom_enabled
    task.save(update_fields=['classroom_enabled'])
    return redirect('ege:ege_task', number=number)


# Три корзины, по которым учитель раскладывает банк. Умолчание – 'study':
# задача, не отмеченная ничем, идёт в обычную тренировку.
BANK_POOLS = ('study', 'classroom', 'exam')


def _question_pool(question):
    if question.classroom_only:
        return 'classroom'
    if question.exam_only:
        return 'exam'
    return 'study'


@login_required
def ege_bank_view(request, number):
    """
    Банк задач одного задания глазами учителя: условие целиком и его корзина.

    Те же две галочки стоят в админке, но там виден один заголовок, а решать,
    идёт ли задача на урок или в экзаменационный резерв, приходится по условию.
    Здесь условие раскрывается прямо в строке, рядом с переключателем.
    """
    if not request.user.is_superuser:
        raise PermissionDenied('Банк задач открыт учителю')
    if number not in range(1, 28):
        raise Http404('Нет такого задания ЕГЭ')

    # Связку 19–21 разбирают как одну задачу, поэтому страница показывает её
    # целиком – так же, как карточка задания.
    linked = ege_stats.linked_numbers()
    numbers = sorted(linked) if number in linked else [number]

    questions = list(
        ege_practice.bank_queryset(include_exam_only=True, include_classroom=True)
        .filter(ege_number__in=numbers)
        .select_related('quiz')
        .prefetch_related('images', 'test_cases')
        .order_by('group_id', 'group_order', 'ege_number', 'id')
    )

    if request.method == 'POST':
        return _save_bank_pools(request, number, questions)

    rows = [{'question': q, 'pool': _question_pool(q)} for q in questions]
    counts = Counter(row['pool'] for row in rows)
    return render(request, 'quizzes/ege_bank.html', {
        'number': number,
        'task': _task_or_404(number),
        'rows': rows,
        'counts': counts,
        'linked': number in linked,
        'linked_range': f'{min(numbers)}–{max(numbers)}' if len(numbers) > 1 else '',
    })


def _save_bank_pools(request, number, questions):
    """Раскладывает отмеченные задачи по корзинам одним запросом."""
    desired = {}
    for question in questions:
        pool = request.POST.get(f'pool_{question.id}')
        if pool in BANK_POOLS:
            desired[question.id] = pool

    # У связки корзина общая: резерв, поставленный на 19-е, увёл бы в экзамен
    # и 20-е с 21-м, а тренировке оставил бы разорванную тройку. Ведущей
    # считается та задача связки, которую учитель тронул.
    groups = defaultdict(list)
    for question in questions:
        if question.group_id:
            groups[question.group_id].append(question)
    for members in groups.values():
        moved = [desired[q.id] for q in members
                 if desired.get(q.id, _question_pool(q)) != _question_pool(q)]
        if moved:
            for question in members:
                desired[question.id] = moved[0]

    changed = []
    for question in questions:
        pool = desired.get(question.id)
        if pool is None or pool == _question_pool(question):
            continue
        question.classroom_only = pool == 'classroom'
        question.exam_only = pool == 'exam'
        changed.append(question)

    Question.objects.bulk_update(changed, ['classroom_only', 'exam_only'])
    messages.success(request, f'Перемещено задач: {len(changed)}' if changed
                     else 'Ничего не изменилось')
    return redirect('ege:ege_bank', number=number)


@login_required
@require_POST
def practice_start_view(request):
    """Создаёт сессию тренировки по параметрам формы и ведёт на неё."""
    kind = request.POST.get('kind', 'topic')
    if kind not in dict(PracticeSession.KIND_CHOICES) or kind == 'retry':
        kind = 'topic'

    mode = request.POST.get('mode', 'study')
    if mode not in dict(PracticeSession.MODE_CHOICES):
        mode = 'study'

    def _int_or_none(name):
        value = request.POST.get(name)
        return int(value) if value and value.isdigit() else None

    number = _int_or_none('ege_number')
    difficulty = _int_or_none('difficulty')
    size = _int_or_none('size')

    if kind in ('topic', 'classroom') and number not in range(1, 28):
        raise PermissionDenied('Не указано задание ЕГЭ')

    # Кнопку урока учитель включает рубильником в справочнике заданий –
    # значит и запуск по прямому POST должен подчиняться тому же рубильнику.
    # Учитель открывает набор и при выключенном рубильнике: ему нужно увидеть
    # задачи до урока. Ученику выключенный рубильник закрывает вход.
    if (kind == 'classroom' and not ege_practice.classroom_open(number)
            and not request.user.is_superuser):
        raise PermissionDenied('Задачи для урока сейчас закрыты')

    # Экзамен один за раз: вторая вкладка вернёт ученика в уже идущую попытку,
    # а не выдаст ему второй час и выбор лучшего результата из двух.
    if mode == 'exam':
        running = ege_practice.active_exam(request.user)
        if running:
            return redirect('ege:ege_practice', pk=running.pk)

    # Экзамен по неразобранной теме измерил бы только незнание. Порог задаёт
    # админ в справочнике заданий; проверка на сервере, а не только в форме.
    if mode == 'exam' and kind == 'topic':
        exam_open, _, _ = ege_practice.exam_access(request.user, number)
        if not exam_open:
            request.session['ege_exam_locked'] = True
            return redirect('ege:ege_task', number=number)

    # Ручной состав: сколько задач какой сложности. Пустой микс – значит ученик
    # оставил простой выбор «сложность + количество».
    mix = {}
    for level in (1, 2, 3):
        count = _int_or_none(f'mix_{level}')
        if count:
            mix[level] = min(count, STUDY_MAX_SIZE)
    if sum(mix.values()) > STUDY_MAX_SIZE:
        raise PermissionDenied(f'Не больше {STUDY_MAX_SIZE} задач за сессию')

    if size is not None:
        size = max(1, min(STUDY_MAX_SIZE, size))
        # По связанным заданиям (19–21) форма спрашивает число троек, а отбору
        # нужны задачи. Переводим здесь, чтобы ниже по течению size везде
        # означал одно и то же.
        if number:
            size *= ege_practice.group_span(number)

    session = ege_practice.build_session(
        request.user, kind=kind, ege_number=number,
        difficulty=difficulty, mode=mode, size=size, mix=mix or None,
    )

    if session is None:
        # Пустая сессия – не ошибка сервера, а пустой банк по этому фильтру.
        target = 'ege:ege_task' if number else 'ege:ege_list'
        request.session['ege_practice_empty'] = True
        if number:
            return redirect(target, number=number)
        return redirect(target)

    return redirect('ege:ege_practice', pk=session.pk)


def _owned_session(request, pk):
    session = get_object_or_404(
        PracticeSession.objects.prefetch_related(
            'items__question__images',
            'items__question__files',
            'items__question__test_cases',
        ),
        pk=pk,
    )
    if session.user_id != request.user.id and not request.user.is_superuser:
        raise PermissionDenied('Это чужая сессия тренировки')

    # Время экзамена вышло – закрываем сессию тем же моментом, а не «сейчас»:
    # иначе вкладка, открытая до утра, добавила бы в статистику лишние часы.
    if session.is_expired:
        session.finished_at = session.deadline
        session.save(update_fields=['finished_at'])
    return session


def _navigator_rows(items, per_row=4):
    """
    Строки сетки задач: [{'linked': bool, 'cells': [индексы задач]}].

    Связка занимает отдельную строку целиком – это одна игра, и разрывать её
    между рядами нельзя. Всё остальное идёт обычными рядами.
    """
    rows, plain = [], []

    def flush():
        while plain:
            rows.append({'linked': False, 'cells': plain[:per_row]})
            del plain[:per_row]

    for index, item in enumerate(items):
        group = item.question.group_id
        if not group:
            plain.append(index)
            if len(plain) == per_row:
                flush()
            continue
        flush()
        if rows and rows[-1]['linked'] and rows[-1]['group'] == group:
            rows[-1]['cells'].append(index)
        else:
            rows.append({'linked': True, 'group': group, 'cells': [index]})
    flush()
    return rows


def _item_payload(item, reveal):
    """
    Данные одной задачи для Alpine.

    Правильный ответ не уходит в браузер вообще – ни в «Экзамене», ни в «Учёбе».
    В тренировке его отдаёт только practice_reveal_view по кнопке «Показать ответ»,
    и это решение фиксируется как отказ от задачи. Единственное исключение –
    задача, по которой ответ уже открыт: иначе после перезагрузки страницы он
    исчезал бы, а вторая попытка всё равно уже не засчитается.
    """
    question = item.question
    payload = {
        'item_id': item.id,
        'question_id': question.id,
        # Задачи сессии приходят из разных квизов (банки и варианты), поэтому
        # адрес отправки кода считается по каждой задаче отдельно.
        'quiz_id': question.quiz_id,
        'ege_number': question.ege_number,
        'type': question.question_type,
        'points': question.points,
        'difficulty': question.effective_difficulty(),
        'difficulty_label': question.get_effective_difficulty_display(),
        'recommended_min': EGE_RECOMMENDED_TIME.get(question.ege_number or 0, 5),
        'answer': item.text_answer or '',
        # На экзамене исход задачи скрыт до конца сессии – иначе после
        # перезагрузки страницы сетка задач раскрасилась бы верно/неверно.
        'is_correct': item.is_correct if reveal else None,
        # Частичный балл – такая же обратная связь, как исход: на экзамене
        # молчим о нём до разбора.
        'score': item.score if reveal else None,
        'attempts': item.attempts if reveal else 0,
        'gave_up': item.gave_up,
        # Задача связки, решённая раньше: ответ подставлен, решать её заново
        # не нужно – в сессии она стоит как условие для соседних.
        'carried': item.carried,
        'locked': item.is_locked if reveal else False,
        'seconds': item.seconds,
        'answered': item.answered_at is not None,
    }
    if reveal and item.gave_up:
        payload['correct_answer'] = question.correct_text_answer or ''
    return payload


@login_required
def ege_solved_view(request, number):
    """
    Решённые задачи одного задания вместе с решениями ученика.

    Задача, которую больше не выдадут, не должна исчезать бесследно: своё
    решение нужно уметь перечитать. Для задач на код здесь же вход на второй
    заход – переписать алгоритм быстрее или экономнее по памяти.
    """
    if number not in range(1, 28):
        raise Http404('Нет такого задания ЕГЭ')

    items = (
        PracticeItem.objects
        .filter(session__user=request.user, is_correct=True,
                question__ege_number=number,
                question__quiz__quiz_type__in=EGE_QUIZ_TYPES)
        .select_related('question', 'submission')
        .prefetch_related('question__images', 'question__files')
        .order_by('question_id', '-answered_at')
    )

    # Первая строка по каждой задаче – последнее верное решение. Сортировка
    # выше уже расставила их в нужном порядке, второй запрос не нужен.
    rows = []
    seen = set()
    for item in items:
        if item.question_id in seen:
            continue
        seen.add(item.question_id)
        minutes, secs = divmod(item.seconds, 60)
        rows.append({
            'item': item,
            'question': item.question,
            'is_code': item.question.question_type == 'code',
            'mm_ss': f'{minutes}:{secs:02d}' if item.seconds else '–',
            'color': ege_time_color(item.seconds, number),
            'answered_at': item.answered_at,
            'attempts': item.attempts,
        })

    rows.sort(key=lambda row: row['answered_at'] or timezone.now(), reverse=True)

    best = ege_practice.best_code_metrics(
        request.user, [row['question'].id for row in rows if row['is_code']]
    )
    for row in rows:
        row['best'] = best.get(row['question'].id)

    return render(request, 'quizzes/ege_solved.html', {
        'number': number,
        'task': _task_or_404(number),
        'rows': rows,
        'recommended_min': EGE_RECOMMENDED_TIME.get(number, 5),
    })


@login_required
@require_POST
def practice_retry_view(request, question_id):
    """Ещё один заход на решённую задачу с кодом – попробовать другой способ."""
    question = get_object_or_404(
        Question, pk=question_id, quiz__quiz_type__in=EGE_QUIZ_TYPES,
    )
    session = ege_practice.build_retry_session(request.user, question)
    if session is None:
        raise PermissionDenied('Переписать можно только решение на коде')
    return redirect('ege:ege_practice', pk=session.pk)


@login_required
def practice_view(request, pk):
    """Страница решения сессии: одна задача на экране."""
    session = _owned_session(request, pk)

    if session.is_finished:
        return redirect('ege:ege_practice_result', pk=session.pk)

    items = list(session.items.select_related('question').order_by('order'))
    reveal = session.mode == 'study'

    # Последняя отправка кода по каждой задаче – чтобы ученик, вернувшийся на
    # вкладку, увидел свой код, а не пустой редактор.
    last_submissions = {}
    code_items = [item for item in items if item.question.question_type == 'code']
    if code_items:
        subs = (
            CodeSubmission.objects
            .filter(user=request.user, question__in=[i.question_id for i in code_items])
            .order_by('question_id', '-created_at')
        )
        for sub in subs:
            if sub.question_id not in last_submissions:
                last_submissions[sub.question_id] = {
                    'id': sub.id, 'status': sub.status,
                    'is_correct': sub.is_correct, 'code': sub.code,
                }

    # Сколько секунд осталось до конца экзамена: считаем на сервере, чтобы
    # переведённые назад часы в браузере не продлевали контрольную.
    deadline = session.deadline
    left = int((deadline - timezone.now()).total_seconds()) if deadline else None

    return render(request, 'quizzes/ege_practice.html', {
        'session': session,
        'is_retry': session.kind == 'retry',
        'seconds_left': max(0, left) if left is not None else None,
        'items': items,
        'items_json': js_json([_item_payload(item, reveal) for item in items]),
        'last_submissions_json': js_json(last_submissions),
        'reveal': reveal,
        'answered_count': sum(1 for item in items if item.answered_at),
        # Раскладка навигатора считается здесь, а не в браузере: связка идёт
        # своей строкой в рамке, остальные задачи – обычными рядами по четыре.
        # В работе над ошибками сессия смешанная, и одной ширины на всех не
        # хватает: ряд из четырёх разъезжался бы с тройкой.
        'nav_rows_json': js_json(_navigator_rows(items)),
    })


def _apply_answer(item, answer, seconds, study):
    """Записывает ответ ученика в задачу сессии. Возвращает исход."""
    # Задания 26 и 27 оцениваются по шкале 0/1/2 – балл пишем рядом с исходом,
    # а решённой задача считается только при полном балле.
    score = ege_grade(item.question, answer, item.question.correct_text_answer or '')
    is_correct = (score >= item.question.points if score is not None
                  else item.question.check_text_answer(answer))
    item.text_answer = answer[:200]
    item.is_correct = is_correct
    item.score = score
    # «Попытка» имеет смысл только там, где есть обратная связь: на экзамене
    # ученик правит черновик вслепую, и считать правки попытками нечестно.
    item.attempts = item.attempts + 1 if study else 1
    item.answered_at = timezone.now()
    item.seconds = min(int(seconds), MAX_SECONDS_PER_REPORT) if seconds else item.seconds
    item.save(update_fields=['text_answer', 'is_correct', 'score', 'attempts',
                             'answered_at', 'seconds'])
    return is_correct


@login_required
@require_POST
def practice_answer_view(request, pk):
    """AJAX: приём ответа на одну задачу сессии."""
    session = _owned_session(request, pk)
    if session.is_finished:
        return JsonResponse({'error': 'Сессия уже завершена'}, status=403)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Невалидный JSON'}, status=400)

    item = get_object_or_404(PracticeItem, pk=data.get('item_id'), session=session)
    answer = (data.get('answer') or '').strip()
    seconds = data.get('seconds') or 0

    if item.question.question_type == 'code':
        return JsonResponse({'error': 'Задачи на код проверяются отправкой кода'}, status=400)

    if not answer:
        return JsonResponse({'error': 'Ответ пуст'}, status=400)

    study = session.mode == 'study'

    # Решённую или открытую задачу не переигрывают: иначе счётчик попыток
    # и отказ от задачи можно было бы затереть повторной отправкой. На экзамене
    # замка нет – там ответ до конца сессии остаётся черновиком.
    if study and item.is_locked:
        return JsonResponse({'error': 'Задача уже закрыта'}, status=409)

    is_correct = _apply_answer(item, answer, seconds, study)

    if not study:
        # Ни исхода, ни намёка на него: разбор ученик увидит после завершения.
        return JsonResponse({'saved': True, 'item_id': item.id})

    # Верный ответ здесь не отдаём даже в «Учёбе»: неверная попытка не должна
    # закрывать задачу за ученика. Хочет увидеть – жмёт «Показать ответ».
    return JsonResponse({
        'is_correct': is_correct,
        'score': item.score,
        'item_id': item.id,
        'attempts': item.attempts,
        'locked': item.is_locked,
    })


@login_required
@require_POST
def practice_reveal_view(request, pk):
    """
    AJAX: «Показать ответ» – ученик сдался.

    Задача закрывается как нерешённая независимо от того, что было введено
    раньше. Это и есть цена подсказки: в статистике она стоит столько же,
    сколько неверный ответ, поэтому смотреть её ради проверки себя незачем.
    """
    session = _owned_session(request, pk)
    if session.is_finished:
        return JsonResponse({'error': 'Сессия уже завершена'}, status=403)
    if session.mode != 'study':
        return JsonResponse({'error': 'На экзамене ответы открываются в конце'}, status=403)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Невалидный JSON'}, status=400)

    item = get_object_or_404(PracticeItem, pk=data.get('item_id'), session=session)
    if item.is_correct:
        return JsonResponse({'error': 'Задача уже решена'}, status=409)

    if not item.gave_up:
        item.gave_up = True
        item.is_correct = False
        item.answered_at = item.answered_at or timezone.now()
        item.save(update_fields=['gave_up', 'is_correct', 'answered_at'])

    return JsonResponse({
        'item_id': item.id,
        'correct_answer': item.question.correct_text_answer or '',
        'attempts': item.attempts,
        'locked': True,
    })


@login_required
@require_POST
def practice_time_view(request, pk):
    """AJAX: докидывает время, потраченное на задачу."""
    session = _owned_session(request, pk)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Невалидный JSON'}, status=400)

    item = get_object_or_404(PracticeItem, pk=data.get('item_id'), session=session)
    seconds = data.get('seconds') or 0
    try:
        seconds = int(seconds)
    except (TypeError, ValueError):
        return JsonResponse({'error': 'seconds должно быть числом'}, status=400)

    # Обрезаем порцию: браузер присылает что угодно, а цифры идут в отчёт учителю.
    seconds = max(0, min(seconds, MAX_SECONDS_PER_REPORT))
    if seconds:
        item.seconds += seconds
        item.save(update_fields=['seconds'])
    return JsonResponse({'seconds': item.seconds})


@login_required
@require_POST
def practice_finish_view(request, pk):
    """
    Закрывает сессию и ведёт на разбор.

    Уходя с экзамена, браузер шлёт сюда sendBeacon с ещё не сохранёнными
    ответами: закрыть попытку и сохранить ответы нужно одним запросом, иначе
    отдельное сохранение приходит в уже закрытую сессию и ответ теряется.
    Ответ маячка никто не читает – отсюда 204 вместо редиректа.
    """
    session = _owned_session(request, pk)
    # Маячок шлётся формой, а не JSON: sendBeacon не умеет заголовки, и токен
    # CSRF в него можно положить только полем формы.
    beacon = request.POST.get('beacon') == '1'

    if beacon and not session.is_finished:
        try:
            pending = json.loads(request.POST.get('answers') or '[]')
        except json.JSONDecodeError:
            pending = []
        by_id = {item.pk: item for item in session.items.select_related('question')}
        study = session.mode == 'study'
        for row in pending[:100]:
            item = by_id.get(row.get('item_id'))
            answer = (row.get('answer') or '').strip()
            if not item or not answer or item.question.question_type == 'code':
                continue
            if study and item.is_locked:
                continue
            _apply_answer(item, answer, row.get('seconds') or 0, study)

    if not session.is_finished:
        session.finished_at = timezone.now()
        session.save(update_fields=['finished_at'])
    if beacon:
        return HttpResponse(status=204)
    return redirect('ege:ege_practice_result', pk=session.pk)


@login_required
def practice_result_view(request, pk):
    """Разбор сессии: что верно, сколько времени ушло против норматива."""
    session = _owned_session(request, pk)

    # Разбор открывается только у закрытой сессии. Иначе ученик посреди
    # экзамена открывал бы эту страницу второй вкладкой, читал верные ответы
    # (ответы на экзамене правятся до самого конца) и возвращался их вписать.
    # В тренировке та же дыра обходила бы «Показать ответ» вместе с его ценой.
    # Учителю разбор чужой сессии тоже нужен только законченный.
    if not session.is_finished:
        return redirect('ege:ege_practice', pk=session.pk)

    items = list(session.items.select_related('question').order_by('order'))
    rows = []
    total_seconds = 0
    correct = 0

    # Ссылки на теорию собираем одним запросом: в смешанной сессии задачи из
    # разных заданий, и запрос на строку дал бы N+1.
    numbers = {item.question.ege_number for item in items if item.question.ege_number}
    theory_slugs = dict(
        Article.objects
        .filter(track='ege', is_published=True, ege_task__number__in=numbers)
        .order_by('order')
        .values_list('ege_task__number', 'slug')
    )

    for item in items:
        question = item.question
        seconds = item.seconds
        total_seconds += seconds
        if item.is_correct:
            correct += 1
        minutes, secs = divmod(seconds, 60)
        # Статус считаем здесь, а не в шаблоне: у is_correct три состояния,
        # и «не отвечал» (None) в шаблонной логике легко спутать с «неверно».
        if item.is_correct is None:
            status = 'skipped'
        elif item.gave_up:
            # Отдельный статус, а не просто «неверно»: ученику важно видеть,
            # где он не смог, а где не стал пробовать.
            status = 'revealed'
        else:
            status = 'correct' if item.is_correct else 'wrong'

        rows.append({
            'item': item,
            'question': question,
            'status': status,
            'number': question.ege_number,
            'mm_ss': f'{minutes}:{secs:02d}' if seconds else '–',
            'color': ege_time_color(seconds, question.ege_number),
            'recommended_min': EGE_RECOMMENDED_TIME.get(question.ege_number or 0, 5),
            'correct_answer': question.correct_text_answer or '',
            'attempts': item.attempts,
            'gave_up': item.gave_up,
            'theory_slug': theory_slugs.get(question.ege_number),
        })

    answered = sum(1 for item in items if item.answered_at)
    avg_seconds = total_seconds // answered if answered else 0
    avg_min, avg_sec = divmod(avg_seconds, 60)

    # Норматив сессии – сумма нормативов вошедших в неё заданий, а не число
    # из головы: смешанная сессия может собрать задачи разной стоимости.
    norm_minutes = sum(row['recommended_min'] for row in rows)

    return render(request, 'quizzes/ege_practice_result.html', {
        'session': session,
        'rows': rows,
        'total': len(items),
        'answered': answered,
        'correct': correct,
        'accuracy': round(correct / answered * 100) if answered else 0,
        'total_minutes': total_seconds // 60,
        'norm_minutes': norm_minutes,
        'avg_mm_ss': f'{avg_min}:{avg_sec:02d}' if avg_seconds else '–',
    })
