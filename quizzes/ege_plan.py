"""
План подготовки к ЕГЭ и повторение пройденного.

Ученик выбирает дедлайн, сколько задач решить по каждому номеру и порядок
номеров. Всё остальное считается здесь из его решений – отдельного журнала нет,
поэтому план не может разойтись с карточкой задания («решено X из Y»).

План
  Зачёт – разные верно решённые задачи номера по тому же правилу, что
  ege_stats._solved_by_number (PlanCountTests сверяет). Неделя – понедельник–
  воскресенье. Остаток раскладывается по неделям до дедлайна по минутам
  (EGE_RECOMMENDED_TIME), номера подряд в порядке плана. Квота недели считается
  от того, что было решено к её понедельнику, поэтому внутри недели не меняется,
  а пропущенная неделя размазывается по оставшимся. Отставание – от снимка
  исходного графика (EgePlan.baseline): пересчитанный график сам подтягивается
  к факту и долга бы не показал.

Повторение
  Только номера, где есть хотя бы одно верное решение (тренировка, экзамен,
  срез, вариант): не изученное повторять нечего. Интервал восстанавливается из
  истории, а не хранится: первое верное решение – 2 недели; верное решение в
  срок или позже – ступень вверх (потолок 4); раньше срока – только перезапуск
  часов; ошибка на повторении (неверно или не с первой попытки) – 1 неделя.
"""
from bisect import bisect_left
from collections import defaultdict
from datetime import datetime, time, timedelta

from django.db.models import Count, Max, Min, Q
from django.utils import timezone

from .ege_constants import (
    EGE_CODE_TASKS, EGE_QUIZ_TYPES, EGE_RECOMMENDED_TIME, EXCLUDED_KINDS,
    practice_pool_q,
)
from .models import EgePlan, ExamTaskProgress, PracticeItem, PracticeSession, Question

NUMBERS = range(1, 28)
LINKED = (19, 20, 21)

FIRST_INTERVAL = 2   # недель после первого верного решения
ERROR_INTERVAL = 1   # после ошибки на повторении – чаще
MAX_INTERVAL = 4
# Сколько номеров повторять за один заход. Пропущенное повторение копится
# (к восьмой неделе плана – десяток номеров разом), а кнопка «Повторить 15
# задач» – это не повторение, а ещё одна неделя плана. Берутся самые просроченные.
REVIEW_BATCH = 5


# --- Порядок номеров ---------------------------------------------------------

def _keep_linked(order):
    """Связка 19–21 – одним блоком на месте 19-го: задачи выдаются тройкой."""
    out = []
    for n in order:
        if n == LINKED[0]:
            out.extend(LINKED)
        elif n not in LINKED:
            out.append(n)
    return out


def preset_order(preset):
    """
    Порядок номеров пресета. Все три идут от простого к сложному, отличается
    главный признак: номер кодификатора (уровни базовый → повышенный → высокий),
    норма времени или способ решения (сначала на бумаге, потом программой).
    """
    keys = {
        'fast': lambda n: (EGE_RECOMMENDED_TIME[n], n),
        'paper': lambda n: (n in EGE_CODE_TASKS, n),
    }
    return _keep_linked(sorted(NUMBERS, key=keys.get(preset, lambda n: n)))


def clean_order(raw):
    """Свой порядок из формы: перестановка 1–27 или None."""
    try:
        order = [int(x) for x in raw]
    except (TypeError, ValueError):
        return None
    if sorted(order) != list(NUMBERS):
        return None
    return _keep_linked(order)


# --- Недели --------------------------------------------------------------------

def monday(day):
    return day - timedelta(days=day.weekday())


def _start_of(day):
    """Полночь дня по часовому поясу сайта – граница недели."""
    return timezone.make_aware(datetime.combine(day, time.min))


def weeks_between(first_monday, deadline):
    """
    Сколько недель плана от этого понедельника до дедлайна (≥ 1).

    Неделя дедлайна идёт в план, только если до дедлайна в ней прожита
    хотя бы половина: дедлайн в понедельник – значит, работа к воскресенью
    прошлой недели, а не к следующему воскресенью, на неделю позже обещанного.
    """
    return max(1, round(((deadline - first_monday).days + 1) / 7))


def spread(order, remaining, weeks):
    """
    Раскладка остатка по неделям: [{номер: задач}, …] длиной weeks.

    Задачи идут подряд в порядке плана, неделя набирается по минутам: задача
    попадает в ту неделю, куда падает её середина на шкале времени. Так у
    задания 27 (40 минут) неделя короче по числу задач, чем у задания 1.
    """
    out = [defaultdict(int) for _ in range(weeks)]
    units = [n for n in order for _ in range(remaining.get(n, 0))]
    total = sum(EGE_RECOMMENDED_TIME[n] for n in units)
    if not total:
        return out
    budget, acc = total / weeks, 0
    for n in units:
        minutes = EGE_RECOMMENDED_TIME[n]
        out[min(weeks - 1, int((acc + minutes / 2) // budget))][n] += 1
        acc += minutes
    return out


# --- Данные из базы -------------------------------------------------------------

def bank_sizes():
    """Размер банка по номерам – тот же знаменатель, что у карточки задания."""
    return dict(
        Question.objects
        .filter(practice_pool_q(), ege_number__isnull=False)
        .exclude(classroom_only=True)
        .values_list('ege_number').annotate(n=Count('id'))
    )


def _first_solves(user_ids):
    """
    {uid: {номер: [моменты первого верного решения каждой задачи, по порядку]}}.

    Фильтр повторяет ege_stats._solved_by_number буквально: план обещает то же
    «решено», что карточка задания.
    """
    result = defaultdict(lambda: defaultdict(list))
    rows = (
        PracticeItem.objects
        .filter(session__user_id__in=user_ids, is_correct=True,
                question__ege_number__isnull=False)
        .filter(practice_pool_q('question__'))
        .exclude(session__kind__in=EXCLUDED_KINDS)
        .exclude(carried=True)
        .values('session__user_id', 'question__ege_number', 'question_id')
        .annotate(first=Min('answered_at'))
    )
    epoch = timezone.make_aware(datetime(2000, 1, 1))
    for row in rows:
        result[row['session__user_id']][row['question__ege_number']].append(
            row['first'] or epoch)
    for numbers in result.values():
        for moments in numbers.values():
            moments.sort()
    return result


def _review_events(user_ids):
    """
    {uid: {номер: [(момент, засчитано, это повторение)], …}} по времени.

    Верные решения – из любого режима и из вариантов. Неверные берутся только
    с повторения: ошибка на тренировке – часть учёбы, а не забытая тема.
    """
    # ponytail: тянет все верные ответы класса строками; если таблица
    # учителя начнёт тормозить – сворачивать в SQL до (номер, день).
    events = defaultdict(lambda: defaultdict(list))
    for uid, number, at, correct, attempts, kind in (
        PracticeItem.objects
        .filter(session__user_id__in=user_ids, answered_at__isnull=False,
                question__ege_number__isnull=False,
                question__quiz__quiz_type__in=EGE_QUIZ_TYPES)
        .filter(Q(is_correct=True) | Q(session__kind='review'))
        .exclude(session__kind__in=EXCLUDED_KINDS)
        .exclude(carried=True)
        .values_list('session__user_id', 'question__ege_number', 'answered_at',
                     'is_correct', 'attempts', 'session__kind')
    ):
        review = kind == 'review'
        # На повторении ошибка – и вторая попытка: тему надо было помнить сразу.
        ok = bool(correct) and (not review or attempts <= 1)
        events[uid][number].append((at, ok, review))
    for uid, number, at in (
        ExamTaskProgress.objects
        .filter(user_id__in=user_ids, is_solved=True, first_solved_at__isnull=False,
                question__ege_number__isnull=False)
        .values_list('user_id', 'question__ege_number', 'first_solved_at')
    ):
        events[uid][number].append((at, True, False))
    for numbers in events.values():
        for rows in numbers.values():
            rows.sort(key=lambda row: row[0])
    return events


# --- Повторение -------------------------------------------------------------------

def review_state(events, today):
    """
    Состояние номера по его истории: None – номер не изучен, иначе
    {interval, due, is_due, error}. events – [(момент, засчитано, повторение)].
    """
    interval = last = None
    error = False
    for at, ok, _review in events:
        if not ok:
            if interval is not None:
                interval, last, error = ERROR_INTERVAL, at, True
            continue
        if interval is None:
            interval = FIRST_INTERVAL
        elif at >= last + timedelta(weeks=interval):
            interval = min(MAX_INTERVAL, interval + 1)
        last, error = at, False
    if interval is None:
        return None
    due = timezone.localtime(last + timedelta(weeks=interval)).date()
    return {'interval': interval, 'due': due, 'is_due': due <= today, 'error': error}


def reviews(events_by_number, today):
    """Сводка повторения ученика: что пора, где ошибся, точность на повторениях."""
    learned, due, errors = [], [], []
    total = ok = 0
    for number in NUMBERS:
        rows = events_by_number.get(number, [])
        for _at, good, review in rows:
            if review:
                total += 1
                ok += good
        state = review_state(rows, today)
        if state is None:
            continue
        state['number'] = number
        learned.append(state)
        if state['is_due']:
            due.append(state)
        if state['error']:
            errors.append(number)
    due.sort(key=lambda row: (row['due'], row['number']))
    due = [row['number'] for row in due]
    return {
        'learned': learned,
        'due': due,
        'batch': due[:REVIEW_BATCH],
        'more': max(0, len(due) - REVIEW_BATCH),
        'errors': errors,
        'total': total,
        'ok': ok,
        'accuracy': round(ok / total * 100) if total else None,
    }


def _review_question(user, number):
    """Задача на повторение: нерешённая, иначе давно не встречавшаяся решённая."""
    from .ege_practice import bank_queryset, pick_topic_questions

    found = pick_topic_questions(user, number, size=1)
    if found:
        return found[0]
    return (
        bank_queryset(number)
        .annotate(seen=Max('practice_items__answered_at',
                           filter=Q(practice_items__session__user=user)))
        .order_by('seen').first()
    )


def build_review_session(user, numbers):
    """
    Сессия повторения: по задаче на номер. Связка – одна тройка на все три
    номера. Решённых соседей не подставляем (в отличие от _carry_solved):
    на повторении тройку решают заново целиком.
    """
    from .ege_practice import expand_groups

    picked, covered = [], set()
    for number in numbers:
        if number in covered:
            continue
        question = _review_question(user, number)
        if question is None:
            continue
        picked.append(question)
        covered.update(LINKED if number in LINKED else (number,))
    if not picked:
        return None
    session = PracticeSession.objects.create(user=user, kind='review', mode='study')
    PracticeItem.objects.bulk_create([
        PracticeItem(session=session, question=q, order=i)
        for i, q in enumerate(expand_groups(picked))
    ])
    return session


# --- План -----------------------------------------------------------------------

def targets(per_task, bank):
    """Сколько задач каждого номера в плане: число ученика, но не больше банка."""
    return {n: min(per_task, bank.get(n, 0)) for n in NUMBERS}


def _done_at(firsts, goal, moment):
    """Засчитано к моменту: {номер: решено до moment, не больше цели}."""
    return {n: min(goal[n], bisect_left(firsts.get(n, []), moment)) for n in NUMBERS}


def make_baseline(order, goal, firsts, today, deadline):
    """Снимок исходного графика на момент создания или правки плана."""
    first = monday(today)
    done = _done_at(firsts, goal, timezone.now())
    weeks = spread(order, {n: goal[n] - done[n] for n in NUMBERS},
                   weeks_between(first, deadline))
    total, cum = sum(done.values()), []
    for week in weeks:
        total += sum(week.values())
        cum.append(total)
    return {
        'start': sum(done.values()),
        'weeks': [(first + timedelta(weeks=i)).isoformat() for i in range(len(weeks))],
        'cum': cum,
    }


def _week_quota(order, goal, firsts, week_monday, deadline):
    """Квота недели и решённое к её понедельнику."""
    done = _done_at(firsts, goal, _start_of(week_monday))
    weeks = spread(order, {n: goal[n] - done[n] for n in NUMBERS},
                   weeks_between(week_monday, deadline))
    return weeks, done


def plan_status(plan, firsts, bank, today, now=None):
    """
    Всё о плане на сегодня: неделя, график, история недель, отставание, прогноз.

    Одна функция на вкладку ученика, страницу учителя и пример для гостя –
    числа на них обязаны совпадать.
    """
    now = now or timezone.now()
    goal = targets(plan.per_task, bank)
    order = plan.order
    this_monday = monday(today)

    weeks, done_monday = _week_quota(order, goal, firsts, this_monday, plan.deadline)
    done_now = _done_at(firsts, goal, now)
    # Сверх плана: решено больше нормы номера. В числа плана не идёт – иначе
    # тридцать задач лёгкого номера «закрыли» бы остальные, – только
    # показывается рядом. Банк – потолок, как у карточки задания.
    extra = {n: max(0, min(bisect_left(firsts.get(n, []), now), bank.get(n, 0)) - goal[n])
             for n in NUMBERS}
    quota = weeks[0]
    week_rows = [
        {'number': n, 'quota': quota[n],
         'done': min(quota[n], done_now[n] - done_monday[n])}
        for n in order if quota.get(n)
    ]
    for row in week_rows:
        row['left'] = row['quota'] - row['done']

    # История: каждая прошлая неделя со своей квотой на её понедельник.
    history, streak = [], 0
    week = monday(plan.started)
    while week < this_monday:
        q, before = _week_quota(order, goal, firsts, week, plan.deadline)
        after = _done_at(firsts, goal, _start_of(week + timedelta(weeks=1)))
        need = sum(q[0].values())
        # Неделя засчитывается по номерам своей квоты, как карточка недели:
        # задачи чужого номера идут в общий план, но квоту недели не закрывают.
        got = sum(min(c, after[n] - before[n]) for n, c in q[0].items())
        state = 'empty' if not need else ('done' if got >= need else ('part' if got else 'miss'))
        history.append({'monday': week, 'need': need, 'got': got, 'state': state})
        week += timedelta(weeks=1)
    week_need = sum(r['quota'] for r in week_rows)
    week_got = sum(r['done'] for r in week_rows)
    current = {'monday': this_monday, 'need': week_need, 'got': week_got,
               'state': 'done' if week_need and week_got >= week_need else 'now'}
    for row in reversed(history + ([current] if current['state'] == 'done' else [])):
        if row['state'] == 'done':
            streak += 1
        elif row['state'] != 'empty':
            break

    total_goal = sum(goal.values())
    total_done = sum(done_now.values())
    # Процент – по минутам норматива, а не по числу задач: простые номера
    # короткие, и «59 % задач» к ноябрю обещало бы почти готовый план, когда
    # впереди самые долгие 24–27.
    goal_minutes = sum(EGE_RECOMMENDED_TIME[n] * goal[n] for n in NUMBERS)
    done_minutes = sum(EGE_RECOMMENDED_TIME[n] * done_now[n] for n in NUMBERS)

    # Отставание – от исходного графика: недели, закончившиеся до этой.
    base = plan.baseline or {}
    expected, behind_weeks = base.get('start', 0), 0
    for iso, cum in zip(base.get('weeks', []), base.get('cum', [])):
        if iso < this_monday.isoformat():
            expected = cum
            behind_weeks += cum > total_done
    lag = max(0, expected - total_done)

    # Прогноз при нынешнем темпе – в минутах норматива, как и процент: темп в
    # штуках набран на коротких номерах, а впереди долгие 24–27, и прогноз
    # в задачах выходил бы оптимистичным. Темп – по закончившимся неделям:
    # ученик решает рывками, и полнедели без задач к четвергу занижали бы его
    # (идущий по графику получал прогноз позже дедлайна). Пока закончившихся
    # недель нет, берётся текущая по прожитым дням.
    def minutes(done):
        return sum(EGE_RECOMMENDED_TIME[n] * done[n] for n in NUMBERS)
    start_minutes = minutes(_done_at(firsts, goal, _start_of(monday(plan.started))))
    full_weeks = (this_monday - monday(plan.started)).days // 7
    if full_weeks:
        pace = max(0, minutes(done_monday) - start_minutes) / full_weeks
    else:
        pace = max(0, done_minutes - start_minutes) / (((today - this_monday).days + 1) / 7)
    left = total_goal - total_done
    forecast = None
    if left <= 0:
        forecast = today
    elif pace > 0:
        forecast = today + timedelta(weeks=(goal_minutes - done_minutes) / pace)

    schedule = [
        {'monday': this_monday + timedelta(weeks=i),
         'items': [(n, w[n]) for n in order if w.get(n)],
         'minutes': sum(EGE_RECOMMENDED_TIME[n] * c for n, c in w.items())}
        for i, w in enumerate(weeks)
    ]
    return {
        'plan': plan,
        'week': week_rows,
        'week_need': week_need,
        'week_got': week_got,
        'week_minutes': schedule[0]['minutes'] if schedule else 0,
        'schedule': schedule,
        'history': history,
        'streak': streak,
        'goal': goal,
        'done': done_now,
        'total_goal': total_goal,
        'total_done': total_done,
        'total_extra': sum(extra.values()),
        'left': max(0, left),
        'percent': round(done_minutes / goal_minutes * 100) if goal_minutes else 0,
        'lag': lag,
        'behind_weeks': behind_weeks,
        'forecast': forecast,
        # Неделя допуска: квоты недель колеблются вокруг средней на ±15 %,
        # и прогноз по темпу гуляет на несколько дней даже у идущего ровно
        # по графику. Жёлтым – только настоящее опоздание.
        'late_forecast': bool(forecast and forecast > plan.deadline + timedelta(weeks=1)),
        'overdue': today > plan.deadline and left > 0,
        'finished': left <= 0,
        'by_number': [{'number': n, 'goal': goal[n], 'done': done_now[n], 'extra': extra[n]}
                      for n in order],
    }


# --- Входные точки ---------------------------------------------------------------

def status(user):
    """План (или None) и повторение одного ученика."""
    today = timezone.localdate()
    plan = EgePlan.objects.filter(user=user).first()
    events = _review_events([user.id]).get(user.id, {})
    result = {'plan': None, 'reviews': reviews(events, today)}
    if plan:
        result['plan'] = plan_status(
            plan, _first_solves([user.id]).get(user.id, {}), bank_sizes(), today)
    return result


def save_plan(user, deadline, per_task, preset, order=None):
    """Создаёт или переписывает план; график-снимок строится заново."""
    order = order or preset_order(preset)
    today = timezone.localdate()
    bank = bank_sizes()
    goal = targets(per_task, bank)
    firsts = _first_solves([user.id]).get(user.id, {})
    plan, created = EgePlan.objects.get_or_create(
        user=user, defaults={'deadline': deadline, 'started': monday(today)})
    plan.deadline, plan.per_task, plan.preset, plan.order = deadline, per_task, preset, order
    plan.baseline = make_baseline(order, goal, firsts, today, deadline)
    if created:
        plan.started = monday(today)
    plan.save()
    return plan


def class_rows(users):
    """
    Строки страницы учителя: ученик, его план (или None) и повторение.
    Три запроса на весь класс вместо status() на каждого.
    """
    users = list(users)
    ids = [u.id for u in users]
    today = timezone.localdate()
    plans = {p.user_id: p for p in EgePlan.objects.filter(user_id__in=ids)}
    firsts = _first_solves(ids) if plans else {}
    events = _review_events(ids)
    bank = bank_sizes()
    rows = []
    for user in users:
        plan = plans.get(user.id)
        rows.append({
            'user': user,
            'plan': plan_status(plan, firsts.get(user.id, {}), bank, today) if plan else None,
            'reviews': reviews(events.get(user.id, {}), today),
        })
    return rows


def demo_status():
    """
    Пример для гостя: выдуманный ученик, посчитанный той же plan_status.
    План с первого сентября к первому мая, восемь недель работы с одной
    пропущенной – чтобы были видны и квота, и отставание.
    """
    from types import SimpleNamespace

    today = timezone.localdate()
    start = monday(today) - timedelta(weeks=8)
    deadline = today.replace(month=5, day=1)
    if deadline <= today:
        deadline = deadline.replace(year=deadline.year + 1)
    bank = {n: 30 for n in NUMBERS}
    order = preset_order('easy')
    goal = targets(EgePlan.DEFAULT_PER_TASK, bank)
    firsts, moment = defaultdict(list), _start_of(start) + timedelta(hours=18)
    budget = sum(goal.values()) * 0.8 / weeks_between(start, deadline)
    week_index, spent = 0, 0
    for n in order:
        for _ in range(goal[n]):
            if week_index >= 8:
                break
            if week_index == 5:   # пропущенная неделя
                week_index += 1
            firsts[n].append(moment + timedelta(weeks=week_index, days=spent % 5))
            spent += 1
            if spent >= budget:
                week_index, spent = week_index + 1, 0
    plan = SimpleNamespace(per_task=EgePlan.DEFAULT_PER_TASK, order=order, started=start,
                           deadline=deadline, preset='easy', id=None)
    plan.baseline = make_baseline(order, goal, {}, start, deadline)
    plan.baseline['start'] = 0
    learned = [
        {'number': n, 'interval': 2, 'due': today - timedelta(days=1 - (n % 3)),
         'is_due': n % 3 < 2, 'error': n == 4}
        for n in order[:6]
    ]
    return {
        'plan': plan_status(plan, firsts, bank, today),
        'reviews': {'learned': learned, 'due': [r['number'] for r in learned if r['is_due']],
                    'batch': [r['number'] for r in learned if r['is_due']], 'more': 0,
                    'errors': [4], 'total': 9, 'ok': 7, 'accuracy': 78},
    }
