"""
Аналитика ЕГЭ: что ученик уже умеет и куда ему смотреть дальше.

Данные собираются из трёх источников и намеренно живут в одном модуле: та же
разбивка по заданиям 1–27 показывается на хабе тренажёра, в профиле ученика и в
отчёте учителя, и расхождение цифр между ними читалось бы как ошибка в данных.

  PracticeItem       – журнал тренировок: исход, время, дата каждой попытки
  ExamTaskProgress   – работа в вариантах: решена ли задача и сколько ушло времени
  ArticleProgress    – прочитанная теория
"""
from collections import defaultdict
from datetime import timedelta
from types import SimpleNamespace

from django.db.models import (
    Avg, Case, Count, FloatField, Max, Min, Q, Sum, Value, When,
)
from django.db.models.functions import Cast
from django.utils import timezone

from textbook.models import Article, ArticleProgress, EgeTask

from .ege_constants import (  # noqa: F401
    DEFAULT_TASK_MINUTES, EGE_EXAM_MINUTES, EGE_MAX_PRIMARY, EGE_QUIZ_TYPES,
    EGE_RECOMMENDED_TIME, EGE_TASK_POINTS, EXCLUDED_KINDS, PRACTICE_QUIZ_TYPES,
    ege_mistakes_color, ege_score_color, ege_time_color, test_score_for,
)
from .models import (
    ExamTaskProgress, PracticeItem, PracticeSession, Question, Quiz, UserResult,
)

# Вклад одной задачи в «решено верно». Обычно это 0 или 1, но за задания 26 и
# 27 бывает 1 балл из 2 – половина верного ответа. Балл хранится только там, где
# он частичный, поэтому пустое поле означает старое доброе «верно/неверно».
def _credit(flag):
    return Case(
        When(score__isnull=False,
             then=Cast('score', FloatField()) / Cast('question__points', FloatField())),
        When(flag, then=Value(1.0)),
        default=Value(0.0),
        output_field=FloatField(),
    )


PRACTICE_CREDIT = _credit(Q(is_correct=True))
PROGRESS_CREDIT = _credit(Q(is_solved=True))


def _tidy(value):
    """Половинки показываем как 16.5, целое – как 16, а не 16.0."""
    value = round(value or 0, 1)
    return int(value) if value == int(value) else value


TASK_NUMBERS = range(1, 28)

# Ниже этой доли верных ответов задание попадает в «что подтянуть»
WEAK_THRESHOLD = 0.75


def _practice_rows(user):
    """
    Попытки тренировок, свёрнутые по номеру задания.

    Задачи из архива (quiz_type вне EGE_QUIZ_TYPES) не учитываются: когда ФИПИ
    меняет тему номера, старые задачи уезжают в архив командой retag_ege, и
    подмешивать их в точность по этому номеру нельзя – прогноз балла должен
    показывать готовность к сегодняшнему экзамену, а не к прошлогоднему.
    """
    return (
        PracticeItem.objects
        .filter(session__user=user, answered_at__isnull=False,
                question__ege_number__isnull=False,
                question__quiz__quiz_type__in=EGE_QUIZ_TYPES)
        .exclude(session__kind__in=EXCLUDED_KINDS)
        # Перенесённый ответ – копия прошлого зачёта, второй раз он не считается.
        .exclude(carried=True)
        .values('question__ege_number')
        .annotate(
            attempted=Count('id'),
            correct=Sum(PRACTICE_CREDIT),
            avg_seconds=Avg('seconds', filter=Q(seconds__gt=0)),
            total_seconds=Sum('seconds'),
        )
    )


def _practice_by_number(user):
    """
    Статистика тренировок по заданиям: {номер: {attempted, correct, seconds...}}.

    Только тренировки. Варианты сюда не подмешиваются: наборы задач у них разные
    (PRACTICE_QUIZ_TYPES), и складывать «проработал тему» с «написал работу
    целиком» значит получать число, которое ни на один вопрос не отвечает.
    Работа в вариантах живёт своей вкладкой – variant_summary.

    Результат кешируется на объекте пользователя: за один рендер профиля этот
    запрос просят четыре разные функции, а user живёт ровно один HTTP-запрос,
    так что устареть кеш не успевает.
    """
    cached = getattr(user, '_ege_practice_cache', None)
    if cached is not None:
        return cached

    merged = {
        n: {'attempted': 0, 'correct': 0, 'seconds_sum': 0, 'seconds_n': 0, 'total_seconds': 0}
        for n in TASK_NUMBERS
    }

    # Гостю карта заданий тоже показывается – как оглавление теории. Личных
    # цифр у него нет, а фильтр по AnonymousUser в ORM просто упал бы.
    if not user.is_authenticated:
        return merged

    for row in _practice_rows(user):
        number = row['question__ege_number']
        item = merged.get(number)
        if item is None:
            continue
        item['attempted'] += row['attempted']
        item['correct'] = _tidy(item['correct'] + (row['correct'] or 0))
        item['total_seconds'] += row['total_seconds'] or 0
        # Среднее время держим как сумму и счётчик: усреднять два готовых
        # средних нельзя – у них разные веса.
        if row['avg_seconds']:
            item['seconds_sum'] += row['avg_seconds'] * row['attempted']
            item['seconds_n'] += row['attempted']

    user._ege_practice_cache = merged
    return merged


def _solved_by_number(user):
    """
    {номер: {'solved': n, 'first_try': n}} – разные задачи, решённые в тренировке.

    Считаем задачи, а не попытки: карточка обещает «решено X из Y», где Y – это
    размер банка, поэтому и X должен быть числом задач. Одна задача, решённая
    в трёх сессиях, – это одна решённая задача.

    attempts=0 – записи старше самого поля; считаем их решёнными с первой
    попытки, иначе прошлые успехи выглядели бы как многократные.
    """
    empty = {n: {'solved': 0, 'first_try': 0} for n in TASK_NUMBERS}
    if not user.is_authenticated:
        return empty

    rows = (
        PracticeItem.objects
        .filter(session__user=user, is_correct=True,
                question__ege_number__isnull=False,
                question__quiz__quiz_type__in=PRACTICE_QUIZ_TYPES)
        .exclude(session__kind__in=EXCLUDED_KINDS)
        # Перенесённый ответ – копия прошлого зачёта, второй раз он не считается.
        .exclude(carried=True)
        .values('question__ege_number', 'question_id')
        .annotate(best=Min('attempts'))
    )
    for row in rows:
        item = empty.get(row['question__ege_number'])
        if item is None:
            continue
        item['solved'] += 1
        if row['best'] <= 1:
            item['first_try'] += 1
    return empty


def mode_rows(user):
    """
    Статистика по режимам: {номер: {'study': {...}, 'exam': {...}}}.

    Тренировка и экзамен считаются раздельно намеренно. В тренировке ученик разбирается
    с темой и ошибается – это нормальная часть работы, и подмешивать её к
    экзамену значит занижать картину готовности. Экзамен же идёт по резерву,
    которого ученик на тренировках не видел, и показывает знание темы, а не
    память о конкретных задачах.
    """
    result = {
        n: {mode: {'attempted': 0, 'correct': 0, 'sessions': 0, 'last': None,
                   'seconds_sum': 0, 'seconds_n': 0, 'avg_seconds': 0, 'avg_mm_ss': ''}
            for mode in ('study', 'exam')}
        for n in TASK_NUMBERS
    }
    if not user.is_authenticated:
        return result

    rows = (
        PracticeItem.objects
        .filter(session__user=user, answered_at__isnull=False,
                question__ege_number__isnull=False,
                question__quiz__quiz_type__in=EGE_QUIZ_TYPES)
        .exclude(session__kind__in=EXCLUDED_KINDS)
        # Перенесённый ответ – копия прошлого зачёта, второй раз он не считается.
        .exclude(carried=True)
        .values('question__ege_number', 'session__mode')
        .annotate(attempted=Count('id'), correct=Sum(PRACTICE_CREDIT),
                  seconds_sum=Sum('seconds', filter=Q(seconds__gt=0)),
                  seconds_n=Count('id', filter=Q(seconds__gt=0)))
    )
    for row in rows:
        item = result.get(row['question__ege_number'])
        if item is None:
            continue
        bucket = item.get(row['session__mode'])
        if bucket is None:
            continue
        bucket['attempted'] = row['attempted']
        bucket['correct'] = _tidy(row['correct'])
        bucket['seconds_sum'] = row['seconds_sum'] or 0
        bucket['seconds_n'] = row['seconds_n'] or 0

    # Число сессий – отдельным запросом: считаем сессии, а не задачи.
    # Экзамен засчитывается только завершённый: брошенный на середине контролем
    # не был.
    sessions = (
        PracticeSession.objects
        .filter(user=user, ege_number__isnull=False)
        .exclude(kind__in=EXCLUDED_KINDS)
        .filter(Q(mode='study') | Q(mode='exam', finished_at__isnull=False))
        .values('ege_number', 'mode')
        .annotate(n=Count('id'))
    )
    for row in sessions:
        item = result.get(row['ege_number'])
        if item and row['mode'] in item:
            item[row['mode']]['sessions'] = row['n']

    for number, item in result.items():
        for bucket in item.values():
            bucket['accuracy'] = (
                round(bucket['correct'] / bucket['attempted'] * 100)
                if bucket['attempted'] else None
            )
            if bucket['seconds_n']:
                bucket['avg_seconds'] = int(bucket['seconds_sum'] / bucket['seconds_n'])
                bucket['avg_mm_ss'] = _mm_ss(bucket['avg_seconds'])
            # Цвет считается здесь же, рядом с самим временем: везде, где
            # показывается avg_mm_ss, рядом ожидается и его цвет, и разъехаться
            # они не должны. Пустая строка – времени нет, красить нечего.
            bucket['color'] = ege_time_color(bucket['avg_seconds'], number)

    # Последняя попытка экзамена. Средняя точность по всем экзаменам ученику
    # ничего не говорит: первый экзамен он писал, ничего не зная, и этот ноль
    # будет тянуть картину вниз ещё долго после того, как тема разобрана.
    for number, row in _last_exam_by_number(user).items():
        if number in result:
            result[number]['exam']['last'] = row
    return result


def _last_exam_by_number(user):
    """{номер задания: итог последнего завершённого экзамена}."""
    if not user.is_authenticated:
        return {}

    latest = {}
    for session in (
        PracticeSession.objects
        .filter(user=user, mode='exam', finished_at__isnull=False,
                ege_number__isnull=False)
        .order_by('ege_number', '-finished_at')
        .values('id', 'ege_number', 'finished_at')
    ):
        latest.setdefault(session['ege_number'], session)

    if not latest:
        return {}

    totals = {
        row['session_id']: row
        for row in PracticeItem.objects
        .filter(session_id__in=[s['id'] for s in latest.values()])
        .values('session_id')
        .annotate(total=Count('id'), correct=Sum(PRACTICE_CREDIT))
    }

    result = {}
    for number, session in latest.items():
        row = totals.get(session['id'], {'total': 0, 'correct': 0})
        total, correct = row['total'], _tidy(row['correct'])
        result[number] = {
            'total': total,
            'correct': correct,
            'accuracy': round(correct / total * 100) if total else None,
            'finished_at': session['finished_at'],
        }
    return result


def task_accuracy(user):
    """{номер задания: доля верных 0..1}. None – ученик за задание не брался."""
    merged = _practice_by_number(user)
    return {
        n: (item['correct'] / item['attempted'] if item['attempted'] else None)
        for n, item in merged.items()
    }


def task_stats(user):
    """
    Полная карта 27 заданий для хаба тренажёра.

    Возвращает список словарей по возрастанию номера: название задания, сколько
    задач банка решено (и сколько из них с первой попытки), среднее время против
    норматива, прочитана ли теория.

    На карточке живут «решено X из Y» и «с первой попытки»: ученику важно, много
    ли он прошёл, а не сколько раз нажал «Проверить». Попытки видны там, где они
    что-то значат, – в списке решённых задач у каждой задачи. Точность по
    попыткам (accuracy) остаётся в данных: по ней сортируется «что подтянуть».
    """
    merged = _practice_by_number(user)
    solved_rows = _solved_by_number(user)

    titles = dict(EgeTask.objects.values_list('number', 'title'))
    # Обещание карточки – «столько задач можно порешать», поэтому счётчик читает
    # тот же источник, что и тренировка (PRACTICE_QUIZ_TYPES), а не всю базу ЕГЭ.
    # Пока здесь стояло EGE_QUIZ_TYPES, карточка показывала задачи из вариантов,
    # которые тренировка не выдаёт, и «что подтянуть» советовало задания
    # с пустой подборкой.
    bank_counts = dict(
        Question.objects
        .filter(quiz__quiz_type__in=PRACTICE_QUIZ_TYPES, ege_number__isnull=False)
        .values_list('ege_number')
        .annotate(n=Count('id'))
    )
    # Связки: сколько троек в банке и где на карте открывать рамку. Для 19–21
    # число связок совпадает с числом задач номера – в каждой тройке ровно одна
    # задача каждого номера, – но считаем его честно, по group_id.
    linked = linked_numbers()
    group_counts = dict(
        Question.objects
        .filter(quiz__quiz_type__in=PRACTICE_QUIZ_TYPES, ege_number__in=linked)
        .exclude(group_id='')
        .values_list('ege_number')
        .annotate(n=Count('group_id', distinct=True))
    ) if linked else {}

    theory = _theory_by_number(user)
    modes = mode_rows(user)

    result = []
    for number in TASK_NUMBERS:
        item = merged[number]
        attempted, correct = item['attempted'], item['correct']
        avg_seconds = int(item['seconds_sum'] / item['seconds_n']) if item['seconds_n'] else 0
        minutes, secs = divmod(avg_seconds, 60)
        accuracy = round(correct / attempted * 100) if attempted else None

        bank_size = bank_counts.get(number, 0)
        solved = solved_rows[number]['solved']
        # Решить больше, чем есть в банке, нельзя, но задача могла уехать
        # в архив уже после того, как ученик её решил. Обрезаем, иначе на
        # карточке появится «решено 7 из 5».
        solved = min(solved, bank_size)

        result.append({
            'number': number,
            'title': titles.get(number, f'Задание {number}'),
            'points': EGE_TASK_POINTS[number],
            'attempted': attempted,
            'correct': correct,
            'accuracy': accuracy,
            'solved': solved,
            'first_try': min(solved_rows[number]['first_try'], solved),
            'progress': round(solved / bank_size * 100) if bank_size else None,
            'avg_seconds': avg_seconds,
            'avg_mm_ss': f'{minutes}:{secs:02d}' if avg_seconds else '',
            'recommended_min': EGE_RECOMMENDED_TIME.get(number, DEFAULT_TASK_MINUTES),
            'color': ege_time_color(avg_seconds, number),
            'bank_size': bank_size,
            'theory': theory.get(number, {'total': 0, 'read': 0}),
            'study': modes[number]['study'],
            'exam': modes[number]['exam'],
            'linked': number in linked,
            # Куда ведёт карточка: у связки все три ведут на общую страницу.
            'page_number': min(linked) if number in linked else number,
            'linked_first': bool(linked) and number == min(linked),
            'linked_last': bool(linked) and number == max(linked),
            'groups': group_counts.get(number, 0),
        })
    return result


def linked_numbers():
    """
    Номера заданий, задачи которых связаны в группы: {19, 20, 21}.

    Берём из банка, а не из константы: пока связанный банк не импортирован,
    выделять на карте нечего. Набор считается непрерывным – связка 19–21 идёт
    подряд, и карточки на карте обрамляются от min до max.
    """
    return set(
        Question.objects
        .filter(quiz__quiz_type__in=PRACTICE_QUIZ_TYPES, ege_number__isnull=False)
        .exclude(group_id='')
        .values_list('ege_number', flat=True)
        .distinct()
    )


def _theory_by_number(user):
    """{номер задания: {total, read}} по опубликованным статьям теории."""
    totals = dict(
        Article.objects
        .filter(track='ege', is_published=True, ege_task__isnull=False)
        .values_list('ege_task__number')
        .annotate(n=Count('id'))
    )
    read = {}
    if user.is_authenticated:
        read = dict(
            ArticleProgress.objects
            .filter(user=user, article__track='ege', article__is_published=True,
                    article__ege_task__isnull=False, status__in=('read', 'mastered'))
            .values_list('article__ege_task__number')
            .annotate(n=Count('id'))
        )
    return {
        number: {'total': totals.get(number, 0), 'read': read.get(number, 0)}
        for number in TASK_NUMBERS
    }


def predicted_score(user):
    """
    Прогноз результата – строго по экзаменам, тренировки в него не входят.

    Балл: цена задания × точность на экзамене по этому заданию.
    Время: сумма средних времён экзаменационных задач.

    Задание, по которому экзамена не было, не даёт ни балла, ни минут – и это
    не осторожность, а честность. На тренировке ученик может подглядеть теорию
    и пробовать ответ дважды; переносить такую точность в прогноз значит
    обещать балл, которого на настоящем экзамене не будет. Норматив времени
    сюда тоже не подставляется: пока ученик не писал экзамен по заданию, мы не
    знаем ни сколько он наберёт, ни сколько потратит.
    """
    modes = mode_rows(user)
    primary = 0.0
    seconds = 0
    covered = 0

    for number in TASK_NUMBERS:
        bucket = modes[number]['exam']
        if bucket['accuracy'] is None:
            continue
        covered += 1
        primary += bucket['accuracy'] / 100 * EGE_TASK_POINTS[number]
        seconds += bucket['avg_seconds']

    primary_rounded = int(round(primary))
    minutes = int(round(seconds / 60))
    return {
        'primary': primary_rounded,
        'primary_max': EGE_MAX_PRIMARY,
        'test': test_score_for(primary_rounded),
        'color': ege_score_color(test_score_for(primary_rounded)),
        'minutes': minutes,
        'limit': EGE_EXAM_MINUTES,
        'over': max(0, minutes - EGE_EXAM_MINUTES),
        # Общий с variant_forecast ключ: обе карточки прогноза рисует один
        # шаблон, и обе прячут минуты, пока их не из чего сложить.
        'has_time': minutes > 0,
        'covered': covered,
        'covered_total': len(TASK_NUMBERS),
        'has_data': covered > 0,
    }


def weak_tasks(user, limit=5):
    """
    Что подтянуть: задания, где теряется больше всего баллов.

    Сортировка не по голой точности, а по цене ошибки – провал на 27-м (2 балла)
    важнее провала на 4-м. Задания без задач в банке пропускаем: советовать
    тренироваться там, где решать нечего, бессмысленно.
    """
    stats = {item['number']: item for item in task_stats(user)}
    candidates = []
    for number, item in stats.items():
        if not item['bank_size']:
            continue
        if item['attempted'] and item['accuracy'] / 100 >= WEAK_THRESHOLD:
            continue
        accuracy = (item['accuracy'] / 100) if item['attempted'] else 0.0
        candidates.append({**item, 'loss': (1 - accuracy) * EGE_TASK_POINTS[number]})

    # При равной потере вперёд идёт то, за что ученик уже брался: там пробел
    # подтверждён попытками, а не просто не начат.
    candidates.sort(key=lambda item: (-item['loss'], -item['attempted']))
    return candidates[:limit]


# Источники задач в динамике. Разведены намеренно: тренировка, контрольная и
# готовый вариант – разная работа, и общий столбик прятал бы, чем именно
# ученик занимался на этой неделе.
DYNAMICS_SOURCES = ('study', 'exam', 'variant')
DYNAMICS_LABELS = {
    'study': 'Тренировка',
    'exam': 'Экзамен',
    'variant': 'Вариант',
}


def weekly_dynamics(user, weeks=8):
    """
    Решено задач по неделям, раздельно по трём источникам.

    Вариант даёт только решённые задачи: ExamTaskProgress хранит дату первого
    верного решения, а неудачные попытки без даты, и показать их нечем.
    """
    today = timezone.localdate()
    start = today - timedelta(days=today.weekday() + 7 * (weeks - 1))

    def empty():
        return {source: {'attempted': 0, 'correct': 0} for source in DYNAMICS_SOURCES}

    buckets = defaultdict(empty)

    practice = (
        PracticeItem.objects
        .filter(session__user=user, answered_at__date__gte=start)
        .exclude(session__kind__in=EXCLUDED_KINDS)
        # Перенесённый ответ – копия прошлого зачёта, второй раз он не считается.
        .exclude(carried=True)
        .values_list('answered_at__date', 'is_correct', 'session__mode')
    )
    for day, is_correct, mode in practice:
        week = day - timedelta(days=day.weekday())
        cell = buckets[week]['exam' if mode == 'exam' else 'study']
        cell['attempted'] += 1
        if is_correct:
            cell['correct'] += 1

    variants = (
        ExamTaskProgress.objects
        .filter(user=user, first_solved_at__date__gte=start)
        .values_list('first_solved_at__date', flat=True)
    )
    for day in variants:
        week = day - timedelta(days=day.weekday())
        cell = buckets[week]['variant']
        cell['attempted'] += 1
        cell['correct'] += 1

    series = []
    for i in range(weeks):
        week_start = start + timedelta(days=7 * i)
        item = buckets.get(week_start, empty())
        attempted = sum(cell['attempted'] for cell in item.values())
        correct = sum(cell['correct'] for cell in item.values())
        series.append({
            'week_start': week_start,
            'label': week_start.strftime('%d.%m'),
            'attempted': attempted,
            'correct': correct,
            'accuracy': round(correct / attempted * 100) if attempted else None,
            'bars': [
                {
                    'key': source,
                    'title': DYNAMICS_LABELS[source],
                    'attempted': item[source]['attempted'],
                    'correct': item[source]['correct'],
                }
                for source in DYNAMICS_SOURCES
            ],
        })

    # Высоты считаются здесь: в шаблоне деления нет, а тащить ради одного
    # графика библиотеку в страницу тем более незачем. Масштаб общий на все
    # столбики – иначе неделя из одной задачи выглядела бы как рекордная.
    peak = max((bar['attempted'] for row in series for bar in row['bars']), default=0)
    for row in series:
        row['height_pct'] = round(row['attempted'] / peak * 100) if peak else 0
        for bar in row['bars']:
            bar['height_pct'] = round(bar['attempted'] / peak * 100) if peak else 0
            bar['correct_pct'] = (
                round(bar['correct'] / bar['attempted'] * 100) if bar['attempted'] else 0
            )
        row['correct_pct'] = (
            round(row['correct'] / row['attempted'] * 100) if row['attempted'] else 0
        )
    return series


def activity(user):
    """
    Серия дней подряд с решённой задачей и сколько задач решено всего.

    Серия считается от сегодня, а если сегодня ученик ещё не занимался – от
    вчера: иначе она обнулялась бы каждое утро и обесценивала сама себя.
    """
    days = set(
        PracticeItem.objects
        .filter(session__user=user, answered_at__isnull=False)
        .exclude(session__kind__in=EXCLUDED_KINDS)
        # Перенесённый ответ – копия прошлого зачёта, второй раз он не считается.
        .exclude(carried=True)
        .values_list('answered_at__date', flat=True)
    )
    days |= set(
        ExamTaskProgress.objects
        .filter(user=user, first_solved_at__isnull=False)
        .values_list('first_solved_at__date', flat=True)
    )

    today = timezone.localdate()
    cursor = today if today in days else today - timedelta(days=1)
    streak = 0
    while cursor in days:
        streak += 1
        cursor -= timedelta(days=1)

    merged = _practice_by_number(user)
    return {
        'streak': streak,
        'active_days': len(days),
        'solved': sum(item['correct'] for item in merged.values()),
        'attempted': sum(item['attempted'] for item in merged.values()),
    }


def theory_coverage(user):
    """Сколько статей теории прочитано из опубликованных."""
    total = Article.objects.filter(track='ege', is_published=True).count()
    read = 0
    if user.is_authenticated:
        read = ArticleProgress.objects.filter(
            user=user, article__track='ege', article__is_published=True,
            status__in=('read', 'mastered'),
        ).count()
    return {
        'total': total,
        'read': read,
        'pct': round(read / total * 100) if total else 0,
    }


def mode_task_table(user):
    """
    По каждому из 27 заданий: как оно идёт на тренировке и как на экзамене.

    В таблицу попадают только задания, за которые ученик брался: строка из
    сплошных прочерков ничего не сообщает, а два десятка таких строк прячут
    те, где данные есть.
    """
    modes = mode_rows(user)
    titles = dict(EgeTask.objects.values_list('number', 'title'))

    rows = []
    for number in TASK_NUMBERS:
        item = modes[number]
        if not (item['study']['attempted'] or item['exam']['attempted']):
            continue
        rows.append({
            'number': number,
            'title': titles.get(number, f'Задание {number}'),
            'points': EGE_TASK_POINTS[number],
            'recommended_min': EGE_RECOMMENDED_TIME.get(number, DEFAULT_TASK_MINUTES),
            'study': item['study'],
            'exam': item['exam'],
        })
    return {'rows': rows}


def _mm_ss(seconds):
    """Секунды в «м:сс». Пустая строка – времени нет, рисовать нечего."""
    if not seconds:
        return ''
    minutes, secs = divmod(int(seconds), 60)
    return f'{minutes}:{secs:02d}'


def overview(user):
    """Единая сводка для хаба тренажёра, вкладки прогресса и профиля."""
    from .ege_practice import mistake_count

    stats = task_stats(user)
    mistakes = mistake_count(user)
    return {
        'tasks': stats,
        'score': predicted_score(user),
        'weak': weak_tasks(user),
        'dynamics': weekly_dynamics(user),
        'activity': activity(user),
        'theory': theory_coverage(user),
        'by_task': mode_task_table(user),
        'variants': variant_summary(user),
        'mistakes': mistakes,
        'mistakes_color': ege_mistakes_color(mistakes),
    }


# Пример прогресса для гостя: доля верных на экзамене по каждому из 27 заданий.
# Выдуманный ученик в середине подготовки – начало КИМа идёт уверенно, вторая
# половина заметно хуже. Все остальные числа примера (прогноз, «что подтянуть»,
# таблица) выводятся отсюда теми же формулами, что и настоящая статистика:
# иначе карточка прогноза показывала бы балл, который не сходится с собственной
# таблицей под ней, и первый же внимательный ученик перестал бы верить цифрам.
DEMO_ACCURACY = (
    100, 100, 88, 75, 75, 88, 100, 63, 75, 75,
    75, 63, 75, 63, 63, 75, 75, 50, 38, 38,
    38, 63, 50, 38, 50, 25, 25,
)
DEMO_EXAM_ATTEMPTS = 8
DEMO_STUDY_ATTEMPTS = 16
# Номера, которые выдуманный ученик встретил в своих вариантах. Не все 27:
# вариант он писал трижды, и часть номеров осталась нерешённой.
DEMO_VARIANT_NUMBERS = (1, 2, 3, 5, 7, 8, 11, 14, 17, 19, 23, 25, 27)


def _demo_seconds(number, factor=1.0):
    """
    Среднее время примера – от норматива, а не выдуманное отдельно.

    Множитель гуляет по номеру: часть заданий ученик делает быстрее нормы,
    часть медленнее, и в таблице видно, что цвет времени вообще бывает разным.
    Сумма при этом держится около 235 минут – столько и длится экзамен.
    """
    minutes = EGE_RECOMMENDED_TIME.get(number, DEFAULT_TASK_MINUTES)
    return int(minutes * 60 * (0.8 + number % 5 * 0.1) * factor)


def _demo_bucket(number, accuracy, attempts, factor):
    """Один режим одного задания: верных из попыток и среднее время."""
    correct = round(accuracy / 100 * attempts)
    seconds = _demo_seconds(number, factor)
    return {
        'attempted': attempts,
        'correct': correct,
        'accuracy': round(correct / attempts * 100),
        'avg_seconds': seconds,
        'avg_mm_ss': _mm_ss(seconds),
        'color': ege_time_color(seconds, number),
    }


def demo_overview():
    """
    Пример вкладки прогресса для неавторизованного гостя.

    Гостю нечего показать: своих цифр у него нет, а пустые карточки не
    объясняют, ради чего заводить аккаунт. Поэтому вкладка рисуется теми же
    шаблонами, но по выдуманному ученику из DEMO_ACCURACY – и помечается как
    пример прямо над блоком (`is_demo`), чтобы её нельзя было принять за свои
    результаты.

    Названия заданий берутся настоящие: сменится кодификатор – сменятся и
    подписи в примере, отдельно про него вспоминать не придётся.
    """
    titles = dict(EgeTask.objects.values_list('number', 'title'))

    by_task, weak, primary, seconds = [], [], 0.0, 0
    for number, accuracy in zip(TASK_NUMBERS, DEMO_ACCURACY):
        title = titles.get(number, f'Задание {number}')
        # На тренировке ученик всегда точнее: там можно подумать и переспросить
        # теорию. Зато и времени на задачу уходит больше.
        study_row = _demo_bucket(number, min(100, accuracy + 15),
                                 DEMO_STUDY_ATTEMPTS, 1.3)
        exam_row = _demo_bucket(number, accuracy, DEMO_EXAM_ATTEMPTS, 1.0)
        by_task.append({
            'number': number,
            'title': title,
            'points': EGE_TASK_POINTS[number],
            'recommended_min': EGE_RECOMMENDED_TIME.get(number, DEFAULT_TASK_MINUTES),
            'study': study_row,
            'exam': exam_row,
        })
        # Прогноз считается ровно как в predicted_score: цена задания на
        # точность экзамена, минуты – суммой средних времён.
        primary += exam_row['accuracy'] / 100 * EGE_TASK_POINTS[number]
        seconds += exam_row['avg_seconds']
        weak.append({
            'number': number, 'title': title, 'attempted': exam_row['attempted'],
            'correct': exam_row['correct'], 'accuracy': exam_row['accuracy'],
            'points': EGE_TASK_POINTS[number],
            'loss': (1 - exam_row['accuracy'] / 100) * EGE_TASK_POINTS[number],
        })

    primary_rounded = int(round(primary))
    minutes = int(round(seconds / 60))
    weak.sort(key=lambda item: -item['loss'])

    return {
        'is_demo': True,
        'score': {
            'primary': primary_rounded,
            'primary_max': EGE_MAX_PRIMARY,
            'test': test_score_for(primary_rounded),
            'color': ege_score_color(test_score_for(primary_rounded)),
            'minutes': minutes,
            'limit': EGE_EXAM_MINUTES,
            'over': max(0, minutes - EGE_EXAM_MINUTES),
            'has_time': True,
            'has_data': True,
            'covered': len(DEMO_ACCURACY),
            'covered_total': len(TASK_NUMBERS),
        },
        'weak': weak[:4],
        'by_task': {'rows': by_task},
        'variants': _demo_variants(by_task),
    }


def _demo_variants(by_task):
    """Пример раздела «Варианты»: два экзаменационных и один тренировочный."""
    def variant(title, best, spent):
        # SimpleNamespace, а не Quiz: у примера нет и не должно быть строки в
        # базе. id=None – шаблон по нему понимает, что ссылки быть не может.
        return SimpleNamespace(
            id=None, title=title, attempts=1, best_score=best,
            max_points=EGE_MAX_PRIMARY, test_score=test_score_for(best),
            spent_seconds=spent,
        )

    exam_rows = [
        variant('Вариант ЕГЭ № 1', 17, 235 * 60),
        variant('Вариант ЕГЭ № 2', 21, 228 * 60),
    ]
    study_rows = [variant('Тренировочный вариант', 19, 300 * 60)]

    def bucket(rows):
        best = max(v.best_score for v in rows)
        return {
            'rows': rows, 'total': len(rows), 'written': len(rows),
            'attempts': len(rows), 'best_primary': best,
            'best_test': test_score_for(best),
            'seconds': sum(v.spent_seconds for v in rows),
        }

    last = exam_rows[-1]
    return {
        'exam': bucket(exam_rows),
        'study': bucket(study_rows),
        # Темп по номерам – только по тем заданиям, что встретились в вариантах
        # (DEMO_VARIANT_NUMBERS), и это часть примера: таблица по заданиям
        # длиннее, потому что тренажёр охватывает весь кодификатор, а три
        # написанных варианта – нет.
        'by_number': [
            {
                'number': row['number'],
                'title': row['title'],
                'recommended_min': row['recommended_min'],
                # В варианте на задачу уходит больше, чем на разборе одной темы:
                # рядом чужие номера и нет возможности остановиться.
                'study': _demo_number(row['study']['avg_seconds'], row['number'], 1, 1),
                'exam': _demo_number(row['exam']['avg_seconds'] * 1.15, row['number'], 2, 2),
            }
            for row in by_task if row['number'] in DEMO_VARIANT_NUMBERS
        ],
        'forecast': {
            'primary': last.best_score,
            'primary_max': last.max_points,
            'test': last.test_score,
            'minutes': last.spent_seconds // 60,
            'limit': EGE_EXAM_MINUTES,
            'over': max(0, last.spent_seconds // 60 - EGE_EXAM_MINUTES),
            'has_time': True,
            'has_data': True,
            'title': last.title,
            'date': timezone.now() - timedelta(days=5),
        },
    }


def _demo_number(seconds, number, solved, total):
    seconds = int(seconds)
    return {
        'attempted': total, 'solved': solved, 'total': total,
        'avg_seconds': seconds, 'avg_mm_ss': _mm_ss(seconds),
        'color': ege_time_color(seconds, number),
    }


# Режим варианта в статистике зовётся так же, как режим сессии тренажёра:
# 'study' – тренировка, 'exam' – экзамен. В БД у Quiz.exam_mode тренировка
# называется 'practice', и эта таблица – единственное место, где две системы
# названий встречаются. Одинаковые ключи нужны, чтобы разделы «Задания» и
# «Варианты» на странице прогресса читались одним словарём цветов и подписей.
VARIANT_MODES = {'study': 'practice', 'exam': 'exam'}


def variant_ids(mode=None):
    """
    id опубликованных вариантов: всех, либо одного режима ('study'/'exam').

    Тренировочный вариант решают с открытой теорией, без таймера и сколько
    угодно раз, экзаменационный – один раз и за 235 минут. Считать их вместе
    нельзя, поэтому режим просачивается до самого запроса: у каждого свой
    список id, и ни один свод не собирает их в кучу.
    """
    qs = Quiz.objects.filter(quiz_type='exam', is_public=True)
    if mode is not None:
        qs = qs.filter(exam_mode=VARIANT_MODES[mode])
    return list(qs.values_list('id', flat=True))


def exam_variant_ids():
    """Варианты, по которым строится прогноз, – только экзаменационные."""
    return variant_ids('exam')


def variant_stats(user, mode=None):
    """
    Результаты по опубликованным вариантам, при желании одного режима.

    Перенесено из accounts.views._ege_stats без изменений логики.
    """
    ids = variant_ids(mode)
    progress = ExamTaskProgress.objects.filter(user=user, quiz_id__in=ids)

    variants = list(
        Quiz.objects.filter(id__in=ids)
        .annotate(
            num_questions=Count('questions', distinct=True),
            best_score=Max('userresult__score', filter=Q(userresult__user=user)),
            attempts=Count('userresult', distinct=True, filter=Q(userresult__user=user)),
        )
        .order_by('title')
    )
    # Время по варианту – отдельным запросом: ещё один JOIN в annotate выше
    # размножил бы строки и испортил Max/Count.
    spent_by_variant = dict(
        progress.values('quiz_id').annotate(t=Sum('time_spent_seconds'))
        .values_list('quiz_id', 't')
    )
    # Цена варианта в баллах – тоже отдельным запросом и по той же причине:
    # Sum по вопросам в общем annotate размножился бы на число попыток ученика.
    points_by_variant = dict(
        Question.objects.filter(quiz_id__in=ids)
        .values('quiz_id').annotate(p=Sum('points')).values_list('quiz_id', 'p')
    )
    for variant in variants:
        variant.spent_seconds = spent_by_variant.get(variant.id) or 0
        variant.max_points = points_by_variant.get(variant.id) or 0
        # Первичный балл сам по себе ученику мало что говорит – переводим.
        variant.test_score = test_score_for(variant.best_score) if variant.attempts else None
    return variants


def variant_forecast(user):
    """
    Прогноз по вариантам – по последней написанной работе, а не по среднему.

    Форма совпадает с predicted_score, чтобы обе карточки прогноза рисовались
    одним шаблоном и читались как одно и то же измерение с двух сторон: там
    балл собирается из заданий, здесь снимается с целой работы.

    Берётся последний вариант, а не среднее по всем: первый вариант ученик
    писал, ещё не зная половины тем, и этот балл тянул бы прогноз вниз ещё
    долго после того, как темы разобраны. Минуты – реальная длительность
    работы; там, где таймер не сработал (старые попытки без duration), время
    не показывается, вместо этого не подставляется норматив.
    """
    empty = {
        'primary': 0, 'primary_max': EGE_MAX_PRIMARY, 'test': 0,
        'minutes': 0, 'limit': EGE_EXAM_MINUTES, 'over': 0,
        'has_data': False, 'has_time': False, 'title': '', 'date': None,
    }
    if not user.is_authenticated:
        return empty

    last = (
        UserResult.objects
        .filter(user=user, quiz_id__in=exam_variant_ids())
        .select_related('quiz')
        .order_by('-date_completed')
        .first()
    )
    if last is None:
        return empty

    max_points = (
        Question.objects.filter(quiz_id=last.quiz_id)
        .aggregate(p=Sum('points'))['p'] or EGE_MAX_PRIMARY
    )
    minutes = int(round(last.duration.total_seconds() / 60)) if last.duration else 0
    return {
        'primary': last.score,
        'primary_max': max_points,
        'test': test_score_for(last.score),
        'minutes': minutes,
        'limit': EGE_EXAM_MINUTES,
        'over': max(0, minutes - EGE_EXAM_MINUTES),
        'has_data': True,
        'has_time': bool(minutes),
        'title': last.quiz.title,
        'date': last.date_completed,
    }


def _variant_bucket(user, mode):
    """Свод по вариантам одного режима: сколько написано и какой балл вышел."""
    variants = variant_stats(user, mode)
    written = [v for v in variants if v.attempts]
    best = max((v.best_score or 0 for v in written), default=0)
    return {
        'rows': variants,
        'total': len(variants),
        'written': len(written),
        'attempts': sum(v.attempts for v in written),
        'best_primary': best,
        'best_test': test_score_for(best) if written else None,
        'seconds': sum(v.spent_seconds for v in written),
    }


def variant_summary(user):
    """
    Свод по вариантам, разложенный по режимам – ровно как таблица по заданиям.

    Тренировочный и экзаменационный варианты не складываются: первый решают с
    открытой теорией, без таймера и сколько угодно раз, второй – один раз и за
    235 минут. Общий «лучший балл» по обоим означал бы, что тренировка с
    подсказками поднимает картину готовности, а она её не поднимает.

    Прогноз при этом один и только по экзаменам (variant_forecast): режимов
    два, но обещать балл на настоящем ЕГЭ может лишь работа в его условиях.

    Отдельно от статистики по задачам: вариант – это работа целиком, с чужими
    темами вперемешку и с ограничением по времени, и складывать его точность
    с точностью по одному заданию значит смешивать разные измерения.
    """
    return {
        'study': _variant_bucket(user, 'study'),
        'exam': _variant_bucket(user, 'exam'),
        'by_number': variant_by_number(user),
        'forecast': variant_forecast(user),
    }


def _variant_numbers(user, mode):
    """{номер: {'solved', 'total', 'avg_seconds', ...}} по вариантам одного режима."""
    ids = variant_ids(mode)
    # «Всего» – по опубликованным вариантам, чтобы прочерк у нерешённого номера
    # отличался от «такого задания в вариантах нет».
    totals = dict(
        Question.objects
        .filter(quiz_id__in=ids, ege_number__isnull=False)
        .values_list('ege_number').annotate(n=Count('id'))
    )
    # Среднее время – только по решённым задачам с засечённым временем: нули от
    # задач, где таймер не сработал, занизили бы среднее и покрасили бы номер
    # зелёным на пустом месте. «Бралcя» считается по всем записям прогресса,
    # включая нерешённые: неверный ответ – тоже работа, и строку он заслуживает.
    progress = {
        row['question__ege_number']: row
        for row in ExamTaskProgress.objects
        .filter(user=user, quiz_id__in=ids, question__ege_number__isnull=False)
        .values('question__ege_number')
        .annotate(attempted=Count('id'),
                  n=Count('id', filter=Q(is_solved=True)),
                  t=Avg('time_spent_seconds',
                        filter=Q(is_solved=True, time_spent_seconds__gt=0)))
    }
    result = {}
    for number, total in totals.items():
        row = progress.get(number)
        seconds = int(row['t'] or 0) if row else 0
        result[number] = {
            'attempted': row['attempted'] if row else 0,
            'solved': min(row['n'], total) if row else 0,
            'total': total,
            'avg_seconds': seconds,
            'avg_mm_ss': _mm_ss(seconds),
            'color': ege_time_color(seconds, number),
        }
    return result


def variant_by_number(user):
    """
    Темп по номерам заданий – только по работе в вариантах, раздельно по режимам.

    Разбивка та же, что в mode_task_table у заданий, и по той же причине: в
    тренировочном варианте задачу разбирают с теорией под рукой и без таймера,
    и её минуты, подмешанные к экзаменационным, покрасили бы номер не тем
    цветом. Цель из EGE_RECOMMENDED_TIME рассчитана на экзаменационный темп.

    В список попадает только номер, за который ученик брался хотя бы в одном
    режиме, – как и в mode_task_table. Строка из одних прочерков не сообщает
    ничего, чего не видно из списка вариантов, а два десятка таких строк прячут
    те, где данные есть.
    """
    by_mode = {mode: _variant_numbers(user, mode) for mode in VARIANT_MODES}
    titles = dict(EgeTask.objects.values_list('number', 'title'))
    rows = []
    for number in sorted(set(by_mode['study']) | set(by_mode['exam'])):
        empty = {'attempted': 0, 'solved': 0, 'total': 0,
                 'avg_seconds': 0, 'avg_mm_ss': '', 'color': ''}
        study = by_mode['study'].get(number, empty)
        exam = by_mode['exam'].get(number, empty)
        if not (study['attempted'] or exam['attempted']):
            continue
        rows.append({
            'number': number,
            'title': titles.get(number, f'Задание {number}'),
            'study': study,
            'exam': exam,
            'recommended_min': EGE_RECOMMENDED_TIME.get(number, DEFAULT_TASK_MINUTES),
        })
    return rows


# ══════════════ Сравнительная таблица класса ══════════════

def _class_last_active(ids):
    """{user_id: когда ученик занимался в последний раз} – тренировки и варианты."""
    last = {}
    for row in (
        PracticeItem.objects
        .filter(session__user_id__in=ids, answered_at__isnull=False)
        .exclude(session__kind__in=EXCLUDED_KINDS)
        # Перенесённый ответ – копия прошлого зачёта, второй раз он не считается.
        .exclude(carried=True)
        .values('session__user_id').annotate(last=Max('answered_at'))
    ):
        last[row['session__user_id']] = row['last']

    # Вариант – тоже работа: после недели вариантов ученик не «пропал».
    for row in (
        ExamTaskProgress.objects
        .filter(user_id__in=ids, first_solved_at__isnull=False)
        .values('user_id').annotate(last=Max('first_solved_at'))
    ):
        uid = row['user_id']
        if last.get(uid) is None or row['last'] > last[uid]:
            last[uid] = row['last']
    return last


def _class_mistakes(ids):
    """
    {user_id: сколько задач ждёт разбора} – то же правило, что у mistake_count.

    Считается исход последней попытки по каждой задаче, поэтому провал,
    закрытый более поздним решением, из долга уходит. Какие именно это задачи,
    показывает отдельная страница (views.ege_student_mistakes_view) – с
    условием и ответом ученика, потому что учителю нужно не «где», а «что».
    """
    outcomes = {}
    for uid, question_id, correct in (
        PracticeItem.objects
        .filter(session__user_id__in=ids, answered_at__isnull=False,
                question__quiz__quiz_type__in=PRACTICE_QUIZ_TYPES)
        .exclude(session__kind__in=EXCLUDED_KINDS)
        .exclude(carried=True)
        .order_by('answered_at')
        .values_list('session__user_id', 'question_id', 'is_correct')
    ):
        outcomes[(uid, question_id)] = correct

    counts = {}
    for (uid, _), correct in outcomes.items():
        if correct is False:
            counts[uid] = counts.get(uid, 0) + 1
    return counts


def _class_variants(ids):
    """{user_id: последняя экзаменационная работа} и {user_id: {id вариантов}}."""
    last = {}
    written = {}
    for result in (
        UserResult.objects
        .filter(user_id__in=ids, quiz_id__in=exam_variant_ids())
        .select_related('quiz')
        .order_by('-date_completed')
    ):
        written.setdefault(result.user_id, set()).add(result.quiz_id)
        last.setdefault(result.user_id, result)
    return last, written


def _class_dynamics(ids, weeks=4):
    """
    {user_id: столбики активности по неделям} – тот же график, что на хабе.

    Расклад по трём источникам повторяет weekly_dynamics, а вот масштаб высот
    здесь общий на весь класс, а не свой у каждого ученика. В личном виджете
    свой масштаб уместен – ученик сравнивает себя с собой. В таблице класса он
    бы врал: неделя из трёх задач у одного и из тридцати у другого нарисовались
    бы одинаковыми столбиками, а таблицу читают именно поперёк строк.
    """
    today = timezone.localdate()
    start = today - timedelta(days=today.weekday() + 7 * (weeks - 1))

    def empty():
        return {source: {'attempted': 0, 'correct': 0} for source in DYNAMICS_SOURCES}

    buckets = defaultdict(lambda: defaultdict(empty))

    for uid, day, is_correct, mode in (
        PracticeItem.objects
        .filter(session__user_id__in=ids, answered_at__date__gte=start)
        .exclude(session__kind__in=EXCLUDED_KINDS)
        .exclude(carried=True)
        .values_list('session__user_id', 'answered_at__date',
                     'is_correct', 'session__mode')
    ):
        week = day - timedelta(days=day.weekday())
        cell = buckets[uid][week]['exam' if mode == 'exam' else 'study']
        cell['attempted'] += 1
        if is_correct:
            cell['correct'] += 1

    for uid, day in (
        ExamTaskProgress.objects
        .filter(user_id__in=ids, first_solved_at__date__gte=start)
        .values_list('user_id', 'first_solved_at__date')
    ):
        week = day - timedelta(days=day.weekday())
        cell = buckets[uid][week]['variant']
        cell['attempted'] += 1
        cell['correct'] += 1

    weeks_range = [start + timedelta(days=7 * i) for i in range(weeks)]
    peak = max(
        (cell['attempted']
         for by_week in buckets.values()
         for item in by_week.values()
         for cell in item.values()),
        default=0,
    )

    result = {}
    for uid in ids:
        by_week = buckets.get(uid, {})
        series = []
        for week_start in weeks_range:
            item = by_week.get(week_start) or empty()
            series.append({
                'label': week_start.strftime('%d.%m'),
                # Неделя – с понедельника по воскресенье (week_start получен
                # вычитанием weekday()), поэтому в подсказке стоит весь отрезок:
                # подпись под столбиком – это его начало, а не «за какое число».
                'range': (f'{week_start:%d.%m}–'
                          f'{week_start + timedelta(days=6):%d.%m}'),
                'attempted': sum(cell['attempted'] for cell in item.values()),
                'bars': [
                    {
                        'key': source,
                        'title': DYNAMICS_LABELS[source],
                        'attempted': item[source]['attempted'],
                        'correct': item[source]['correct'],
                        'height_pct': (round(item[source]['attempted'] / peak * 100)
                                       if peak else 0),
                        'correct_pct': (
                            round(item[source]['correct'] / item[source]['attempted'] * 100)
                            if item[source]['attempted'] else 0
                        ),
                    }
                    for source in DYNAMICS_SOURCES
                ],
            })
        result[uid] = series
    return result


def class_rows(users):
    """
    Строка на ученика для сравнительной таблицы класса.

    Считается пачкой на всех сразу – семь запросов на класс, а не полтора
    десятка на ученика: те же цифры, собранные вызовом overview() в цикле, дали
    бы под полтысячи запросов на страницу.

    Формулы повторяют личную вкладку буквально – точность округляется до
    процента до умножения на цену задания (predicted_score), «слабое» – это
    меньше WEAK_THRESHOLD верных, вес – цена задания (weak_tasks). Учитель
    открывает таблицу и карточку ученика рядом, и разойтись они не должны.

    Разница с личной вкладкой одна: в «слабых» попадают только задания, за
    которые ученик уже брался. Нетронутая тема в личном списке – это план
    занятий, а в таблице класса из таких тем состояла бы вся строка новичка.
    """
    users = list(users)
    ids = [u.id for u in users]
    if not ids:
        return []

    # Точность по (ученик, задание, режим) – основа и прогноза, и слабых мест.
    # Столбцов «тренировка» и «экзамен» в таблице нет: два процента на строку
    # учитель всё равно сводил в один вопрос «где дыры», а на него отвечают
    # соседние колонки – прогноз, ошибки и «что подтянуть».
    by_user = {uid: {'study': {}, 'exam': {}} for uid in ids}
    for row in (
        PracticeItem.objects
        .filter(session__user_id__in=ids, answered_at__isnull=False,
                question__ege_number__isnull=False,
                question__quiz__quiz_type__in=EGE_QUIZ_TYPES)
        .exclude(session__kind__in=EXCLUDED_KINDS)
        .exclude(carried=True)
        .values('session__user_id', 'question__ege_number', 'session__mode')
        .annotate(attempted=Count('id'), correct=Sum(PRACTICE_CREDIT))
    ):
        bucket = by_user[row['session__user_id']].get(row['session__mode'])
        if bucket is None:
            continue
        bucket[row['question__ege_number']] = {
            'attempted': row['attempted'], 'correct': _tidy(row['correct']),
        }

    last_active = _class_last_active(ids)
    mistakes = _class_mistakes(ids)
    last_variant, written = _class_variants(ids)
    dynamics = _class_dynamics(ids)
    today = timezone.localdate()

    rows = []
    for user in users:
        modes = by_user[user.id]

        # Прогноз – только по экзаменам, ровно как predicted_score.
        primary = 0.0
        covered = 0
        for number, item in modes['exam'].items():
            if number not in EGE_TASK_POINTS or not item['attempted']:
                continue
            covered += 1
            accuracy = round(item['correct'] / item['attempted'] * 100)
            primary += accuracy / 100 * EGE_TASK_POINTS[number]
        primary = int(round(primary))
        test = test_score_for(primary)

        # Что подтянуть: сортировка по цене ошибки, а не по голой точности –
        # провал на 27-м (2 балла) дороже провала на 4-м.
        weak = []
        for number in TASK_NUMBERS:
            attempted = sum(modes[mode].get(number, {}).get('attempted', 0)
                            for mode in ('study', 'exam'))
            if not attempted:
                continue
            correct = sum(modes[mode].get(number, {}).get('correct', 0)
                          for mode in ('study', 'exam'))
            accuracy = correct / attempted
            if accuracy >= WEAK_THRESHOLD:
                continue
            weak.append({'number': number, 'accuracy': round(accuracy * 100),
                         'loss': (1 - accuracy) * EGE_TASK_POINTS[number]})
        weak.sort(key=lambda item: -item['loss'])

        variant = last_variant.get(user.id)
        variant_test = test_score_for(variant.score) if variant else None
        debt = mistakes.get(user.id, 0)
        last = last_active.get(user.id)

        rows.append({
            'user': user,
            'group': getattr(getattr(user, 'profile', None), 'group', None),
            'score': {
                'primary': primary,
                'test': test,
                'color': ege_score_color(test),
                # На скольких заданиях держится прогноз: 60 баллов, собранные с
                # двух номеров и с двадцати, – обещания разной надёжности.
                'covered': covered,
                'covered_total': len(TASK_NUMBERS),
                'has_data': covered > 0,
            },
            'mistakes': debt,
            'mistakes_color': ege_mistakes_color(debt),
            'weak': weak[:3],
            'variant': {
                'written': len(written.get(user.id, ())),
                'test': variant_test,
                'color': ege_score_color(variant_test) if variant else '',
                'title': variant.quiz.title if variant else '',
                'date': variant.date_completed if variant else None,
            },
            'dynamics': dynamics[user.id],
            'last_active': last,
            'days_ago': (today - timezone.localtime(last).date()).days if last else None,
        })

    # Сначала класс, внутри класса – по прогнозу вниз: таблицу читают сверху, а
    # искать в ней надо отставших, и теряться в середине алфавита они не должны.
    # regroup в шаблоне требует, чтобы класс шёл подряд, – отсюда первый ключ.
    rows.sort(key=lambda row: (str(row['group'] or 'яяя'),
                               -row['score']['primary'],
                               row['user'].last_name, row['user'].username))
    return rows
