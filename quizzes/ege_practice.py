"""
Отбор задач для сессии тренировки ЕГЭ.

Три сценария – практикум после статьи теории, свободная тренировка по теме и
работа над ошибками – это одна и та же сессия с разным правилом отбора. Правила
собраны здесь, чтобы вью занимались только HTTP.
"""
from django.utils import timezone

from django.db.models import (
    Case, Count, IntegerField, Max, Min, OuterRef, Q, Subquery, Value, When,
)

from .ege_constants import (  # noqa: F401
    CLASSROOM_POOL_SIZE, DEFAULT_EXAM_UNLOCK, DEFAULT_TASK_MINUTES,
    EGE_QUIZ_TYPES, EGE_RECOMMENDED_TIME, EXAM_MAX_SIZE, EXAM_MINUTES,
    EXAM_POOL_SIZE, EXCLUDED_KINDS, PRACTICE_QUIZ_TYPES, STUDY_DEFAULT_SIZE,
    STUDY_MAX_SIZE, STUDY_MINUTES,
)
from .models import PracticeItem, PracticeSession, Question


def study_session_size(ege_number):
    """
    Размер учебной сессии по умолчанию: 45 минут по нормативу, но не больше восьми.

    Задание 17 (14 мин) → 3 задачи, задание 27 (40 мин) → 1, короткие задания
    упираются в потолок → 8. Потолок важнее норматива: пятнадцать однотипных
    задач подряд ученик дорешивает механически, ничего уже не разбирая.
    Захочет больше – ставит число руками, до STUDY_MAX_SIZE.
    """
    minutes = EGE_RECOMMENDED_TIME.get(ege_number, DEFAULT_TASK_MINUTES)
    return max(1, min(STUDY_DEFAULT_SIZE, round(STUDY_MINUTES / minutes)))


def _ege_task_field(ege_number, field):
    """Одно поле справочника заданий или None, если задания нет."""
    from textbook.models import EgeTask

    return EgeTask.objects.filter(number=ege_number).values_list(
        field, flat=True).first()


def exam_session_size(ege_number):
    """
    Размер экзаменационной сессии: не дольше часа по нормативу и не больше пяти задач.

    Округление вниз, а не к ближайшему: «не превышая час» значит не превышая.
    Задание 1 → 5 (в час влезло бы 20, но потолок пять), 17 → 4, 24 → 3, 27 → 1.

    Норматив ФИПИ описывает среднюю задачу номера, а в банке попадаются такие,
    что и четыре штуки за час не решить, – поэтому число перебивается вручную
    (EgeTask.exam_size, правится прямо в списке админки). Ручное значение
    потолком EXAM_MAX_SIZE не режется: раз учитель ставит его сам, это его
    решение, а не опечатка формы.
    """
    override = _ege_task_field(ege_number, 'exam_size')
    if override:
        return override
    minutes = EGE_RECOMMENDED_TIME.get(ege_number, DEFAULT_TASK_MINUTES)
    return max(1, min(EXAM_MAX_SIZE, int(EXAM_MINUTES / minutes)))


def session_size(ege_number, mode='study'):
    """Размер сессии по режиму. Оставлена как единая точка входа для вью."""
    return exam_session_size(ege_number) if mode == 'exam' else study_session_size(ege_number)


def effective_difficulty_expr():
    """
    SQL-версия Question.effective_difficulty() для фильтрации на стороне базы.

    Пороги берутся из модели – если развести их по двум местам, фильтр
    «повышенная» однажды начнёт выдавать базовые задачи.
    """
    return Case(
        When(solve_rate__isnull=True, then='difficulty'),
        When(solve_rate__gte=Question.SOLVE_RATE_EASY, then=Value(1)),
        When(solve_rate__gte=Question.SOLVE_RATE_MEDIUM, then=Value(2)),
        default=Value(3),
        output_field=IntegerField(),
    )


def bank_queryset(ege_number=None, difficulty=None, include_exam_only=False,
                  include_classroom=False):
    """
    Все задачи ЕГЭ, доступные тренировке, с опциональными фильтрами.

    Источник – только банки (PRACTICE_QUIZ_TYPES): задачи из собранных вариантов
    тренировке не принадлежат, их ученик встречает, когда пишет вариант целиком.

    По умолчанию оба выделенных пула исключены. Экзаменационный резерв – чтобы
    ученик не встретил эти задачи на тренировке раньше, чем на контрольной.
    Классный набор – чтобы к уроку он пришёл, не прорешав его дома.
    """
    qs = Question.objects.filter(quiz__quiz_type__in=PRACTICE_QUIZ_TYPES)
    if not include_classroom:
        qs = qs.exclude(classroom_only=True)
    if not include_exam_only:
        qs = qs.exclude(exam_only=True)
    if ege_number is not None:
        qs = qs.filter(ege_number=ege_number)
    if difficulty is not None:
        qs = qs.annotate(eff_difficulty=effective_difficulty_expr()).filter(
            eff_difficulty=difficulty
        )
    return qs


def _last_outcome_subquery(user):
    """
    Исход последней попытки ученика по задаче из внешнего запроса.

    Берётся по максимальному answered_at: задача, проваленная год назад и решённая
    вчера, ошибкой уже не считается.
    """
    latest = (
        PracticeItem.objects
        .filter(question=OuterRef('pk'), session__user=user, answered_at__isnull=False)
        .exclude(session__kind__in=EXCLUDED_KINDS)
        # Перенесённый ответ – копия прошлого зачёта, второй раз он не считается.
        .exclude(carried=True)
        .order_by('-answered_at')
    )
    return Subquery(latest.values('is_correct')[:1])


def _solved_question_ids(user, ege_number=None):
    """
    ID задач, которые ученик уже решал верно в тренировке.

    Раньше сюда подмешивался ExamTaskProgress – решённое в варианте. Смысла
    в этом больше нет: задача принадлежит одному квизу, а тренировка берёт
    только банки (PRACTICE_QUIZ_TYPES), так что записи о вариантах ни с чем
    здесь не пересекаются. Хуже того, они ломали счётчик на карточке задания:
    «решено» могло оказаться больше, чем всего задач в банке.
    """
    practice = PracticeItem.objects.filter(session__user=user, is_correct=True)
    if ege_number is not None:
        practice = practice.filter(question__ege_number=ege_number)
    return set(practice.values_list('question_id', flat=True))


def exclude_solved(qs, solved_ids):
    """
    Убирает из выборки решённые задачи – но только текстовые.

    Решать второй раз задачу, ответ на которую уже знаешь, бессмысленно: это
    не тренировка, а переписывание. С задачами на код иначе: тот же алгоритм
    можно написать быстрее или экономнее по памяти, и второй заход имеет смысл.
    Их ученик берёт сам, из списка решённых.
    """
    if not solved_ids:
        return qs
    return qs.exclude(Q(id__in=solved_ids) & ~Q(question_type='code'))


def pick_topic_questions(user, ege_number, difficulty=None, size=None):
    """
    Задачи для тренировки по одному заданию.

    Решённые текстовые задачи не выдаются вовсе. Решённые code-задачи могут
    вернуться, но последними и начиная с самых давних: свежий материал важнее
    повторного захода на уже работающее решение.
    """
    size = size or session_size(ege_number)
    solved = _solved_question_ids(user, ege_number)
    qs = exclude_solved(bank_queryset(ege_number, difficulty), solved)

    fresh = list(qs.exclude(id__in=solved).order_by('?')[:size])
    if len(fresh) >= size:
        return fresh

    # ponytail: order_by('?') – полный скан таблицы. При банке в десятки тысяч
    # задач переходим на выборку по случайному id в диапазоне.
    seen_last = (
        qs.filter(id__in=solved)
        .annotate(last_seen=Max('practice_items__answered_at'))
        .order_by('last_seen')[: size - len(fresh)]
    )
    return fresh + list(seen_last)


def pick_mistake_questions(user, size=None, ege_number=None):
    """
    Задачи, на которых ученик споткнулся последний раз.

    Именно последний: если после провала он задачу дорешал, из долга она уходит.
    Размер по умолчанию не ограничен: долг разбирается целиком, иначе счётчик на
    кнопке обещает одно число, а сессия выдаёт другое.
    """
    qs = (
        bank_queryset(ege_number)
        .annotate(last_correct=_last_outcome_subquery(user))
        .filter(last_correct=False)
        .order_by('?')
    )
    return list(qs[:size] if size else qs)


def mistake_count(user):
    """Сколько задач ждёт разбора – для счётчика на кнопке «Работа над ошибками»."""
    return (
        Question.objects
        # Тот же источник, что у pick_mistake_questions: счётчик на кнопке
        # и содержимое сессии обязаны совпадать.
        .filter(quiz__quiz_type__in=PRACTICE_QUIZ_TYPES)
        .annotate(last_correct=_last_outcome_subquery(user))
        .filter(last_correct=False)
        .count()
    )


def _seen_in_exams(user, ege_number):
    """ID задач, которые ученик уже видел в экзаменационных сессиях."""
    return set(
        PracticeItem.objects
        .filter(session__user=user, session__mode='exam',
                question__ege_number=ege_number)
        .values_list('question_id', flat=True)
    )


def classroom_queryset(ege_number):
    """Задачи, отложенные учителем на урок по этому заданию."""
    return Question.objects.filter(
        quiz__quiz_type__in=PRACTICE_QUIZ_TYPES, ege_number=ege_number,
        classroom_only=True,
    )


def pick_classroom_questions(ege_number, size=None):
    """
    Набор задач для урока: одинаковый у всех и в одном и том же порядке.

    Никакого order_by('?'): весь смысл в том, чтобы «задача 3» у всего класса
    была одной задачей. Порядок по id – он не меняется от запуска к запуску.
    Размер не фиксирован: сколько задач учитель пометил, столько и будет.
    """
    qs = classroom_queryset(ege_number).order_by('id')
    return list(qs[:size] if size else qs)


def classroom_pool_size(ege_number):
    """Сколько задач отложено на урок по этому заданию."""
    return classroom_queryset(ege_number).count()


def classroom_open(ege_number):
    """
    Видят ли ученики кнопку «Задачи для урока».

    Рубильник у учителя: набор к завтрашнему занятию собирается заранее, и до
    урока ученикам его показывать незачем.
    """
    from textbook.models import EgeTask

    enabled = EgeTask.objects.filter(number=ege_number).values_list(
        'classroom_enabled', flat=True).first()
    return bool(enabled) and classroom_pool_size(ege_number) > 0


def study_solved_count(user, ege_number):
    """
    Сколько разных задач этого задания ученик решил верно в режиме «Учёба».

    Считаем задачи, а не попытки: иначе порог открытия экзамена закрывался бы
    одной задачей, решённой десять раз.
    """
    if not user.is_authenticated:
        return 0
    return (
        PracticeItem.objects
        .filter(session__user=user, session__mode='study', is_correct=True,
                question__ege_number=ege_number,
                # Тот же фильтр, что в статистике: задачи снятой темы уехали
                # в архив и открывать экзамен по сегодняшнему заданию не должны.
                question__quiz__quiz_type__in=EGE_QUIZ_TYPES)
        # Урок и переписывание решения экзамен не открывают по той же
        # причине, по которой не идут в статистику: там не решают задачу заново.
        .exclude(session__kind__in=('classroom', 'retry'))
        # Перенесённый ответ – копия прошлого зачёта, второй раз он не считается.
        .exclude(carried=True)
        .values('question_id').distinct().count()
    )


def exam_unlock_threshold(ege_number):
    """Порог из справочника заданий; там же его правит админ."""
    row = _ege_task_field(ege_number, 'exam_unlock_threshold')
    return DEFAULT_EXAM_UNLOCK if row is None else row


def exam_access(user, ege_number):
    """
    Открыт ли экзамен по заданию: (открыт, решено, порог).

    Экзамен – проверка, а не первое знакомство с темой: пока ученик не разобрал
    её на тренировках, контрольная измерит только незнание.
    """
    threshold = exam_unlock_threshold(ege_number)
    if threshold <= 0:
        return True, 0, 0
    solved = study_solved_count(user, ege_number)
    return solved >= threshold, solved, threshold


def pick_exam_questions(user, ege_number, size=None):
    """
    Задачи для экзаменационной сессии.

    Порядок предпочтения:
      1. резерв (exam_only), который ученик ещё не видел ни на одном экзамене;
      2. добор из обычных задач, которые ученик дольше всего не открывал;
      3. резерв, виденный давнее всего – последний рубеж, когда взять больше
         неоткуда.

    Второй шаг важнее третьего: резерв фиксированный (пять задач на задание), а
    экзамены ученик проходит сколько угодно раз, и второй экзамен на буквально
    тех же задачах проверял бы память, а не знание темы.
    """
    size = size or exam_session_size(ege_number)
    reserve = bank_queryset(ege_number, include_exam_only=True).filter(exam_only=True)
    seen = _seen_in_exams(user, ege_number)

    picked = list(reserve.exclude(id__in=seen).order_by('?')[:size])

    if len(picked) < size:
        taken = {q.id for q in picked}
        picked += list(
            exclude_solved(bank_queryset(ege_number), _solved_question_ids(user, ege_number))
            .exclude(id__in=taken)
            .annotate(last_seen=Max('practice_items__answered_at'))
            .order_by('last_seen')[: size - len(picked)]
        )

    if len(picked) < size:
        taken = {q.id for q in picked}
        picked += list(
            reserve.exclude(id__in=taken)
            .annotate(last_seen=Max('practice_items__answered_at'))
            .order_by('last_seen')[: size - len(picked)]
        )

    return picked


def exam_pool_size(ege_number):
    """Сколько задач лежит в экзаменационном резерве этого задания."""
    return (
        Question.objects
        .filter(quiz__quiz_type__in=PRACTICE_QUIZ_TYPES, ege_number=ege_number,
                exam_only=True)
        .count()
    )


def pick_by_mix(user, ege_number, mix):
    """
    Сессия из заданного числа задач каждой сложности: {1: 2, 2: 0, 3: 2}.

    Уровни не пересекаются – у задачи ровно одна эффективная сложность, поэтому
    выборки складываются без риска задвоить задачу.
    """
    picked = []
    for level in sorted(mix):
        count = mix.get(level) or 0
        if count > 0:
            picked += pick_topic_questions(user, ege_number, difficulty=level, size=count)
    return picked


def pick_mixed_questions(user, size=5):
    """
    Смешанная сессия: по одной задаче из разных заданий, начиная со слабых.

    Слабость определяется по доле верных ответов ученика; задания, которых он
    ещё не касался, идут первыми – там неизвестность, а не подтверждённый навык.
    """
    from .ege_stats import task_accuracy

    accuracy = task_accuracy(user)
    numbers = sorted(
        range(1, 28),
        key=lambda n: (accuracy.get(n) if accuracy.get(n) is not None else -1),
    )

    picked = []
    for number in numbers:
        if len(picked) >= size:
            break
        found = pick_topic_questions(user, number, size=1)
        if found:
            picked.append(found[0])
    return picked


def build_retry_session(user, question):
    """
    Сессия из одной задачи: ученик хочет переписать своё решение.

    Только для задач на код – именно там есть что улучшать: время работы и
    память. У текстовой задачи второй заход означал бы просто ввод известного
    ответа, и такой сессии не будет.
    """
    if question.question_type != 'code':
        return None

    # Задача связки и здесь не идёт одна: 20-е без условия игры из 19-го
    # переписать невозможно. Соседи приходят с подставленным ответом – они
    # тут как условие, а не как задание.
    questions = expand_groups([question])

    session = PracticeSession.objects.create(
        user=user, kind='retry', mode='study', ege_number=question.ege_number,
    )
    PracticeItem.objects.bulk_create([
        PracticeItem(session=session, question=q, order=i)
        for i, q in enumerate(questions)
    ])
    _carry_solved(user, session, skip_question_id=question.id)
    return session


def best_code_metrics(user, question_ids):
    """
    {id задачи: лучшие время и память среди верных решений ученика}.

    Считается по CodeSubmission, а не по последней отправке: переписывая код,
    ученик может сделать быстрее, но прожорливее – тогда лучшими остаются
    показатели разных попыток, и подменять их последней было бы враньём.
    Неверные отправки не учитываются: быстрый неправильный ответ – не результат.
    """
    from .models import CodeSubmission

    if not question_ids:
        return {}
    rows = (
        CodeSubmission.objects
        .filter(user=user, question_id__in=question_ids, is_correct=True)
        .values('question_id')
        .annotate(best_cpu=Min('cpu_time_ms'), best_memory=Min('memory_kb'),
                  attempts=Count('id'))
    )
    return {row['question_id']: row for row in rows}


def active_exam(user):
    """
    Незакрытый экзамен ученика – или None, если такого нет.

    Экзамен один за раз: вторая вкладка с новой попыткой означала бы два часа
    вместо одного и выбор лучшего результата из двух. Просроченные попытки
    здесь же и закрываются – иначе они висели бы открытыми до первого захода
    на свою страницу и вечно блокировали бы старт нового экзамена.
    """
    if not user.is_authenticated:
        return None
    for session in PracticeSession.objects.filter(
        user=user, mode='exam', finished_at__isnull=True,
    ).order_by('-created_at'):
        if session.is_expired:
            session.finished_at = session.deadline
            session.save(update_fields=['finished_at'])
            continue
        return session
    return None


def expand_groups(questions, size=None):
    """
    Достраивает связки до полного состава и ставит их в правильный порядок.

    Задания 19–21 держатся на одном условии: игра описана в 19-м, а 20-е и 21-е
    начинаются словами «Для игры, описанной в задании 19». Выдать их порознь
    нельзя, поэтому любая отобранная задача связки тянет за собой всю связку
    по group_order – даже те её части, которые ученик уже решал.

    size режет по целым связкам: лучше дать на задачу меньше, чем половину
    связки. Первая связка проходит всегда, иначе сессия оказалась бы пустой.
    """
    if not any(q.group_id for q in questions):
        return questions

    members = {}
    for member in (Question.objects
                   .filter(group_id__in={q.group_id for q in questions if q.group_id})
                   .order_by('group_order', 'id')):
        members.setdefault(member.group_id, []).append(member)

    result, seen = [], set()
    for question in questions:
        if question.group_id:
            if question.group_id in seen:
                continue
            seen.add(question.group_id)
            block = members.get(question.group_id) or [question]
        else:
            block = [question]
        # Хвост, который не влезает целиком, не берём: половина связки хуже,
        # чем её отсутствие.
        if size and result and len(result) + len(block) > size:
            continue
        result.extend(block)
    return result


def group_count(ege_number):
    """Сколько связок в банке этого задания. Для 19–21 это и есть «сколько задач»."""
    return (
        bank_queryset(ege_number, include_exam_only=True, include_classroom=True)
        .exclude(group_id='')
        .values('group_id').distinct().count()
    )


def group_span(ege_number):
    """
    Сколько задач в одной связке этого задания. 1 – связок по нему нет.

    Считаем по факту, а не по константе «три»: состав связки задаёт банк, и
    менять код из-за нового формата КИМ не придётся. Ученик в форме запуска
    указывает число связок, а отбору нужны задачи – переводит одно в другое
    именно этот множитель.
    """
    first = (
        bank_queryset(ege_number, include_exam_only=True, include_classroom=True)
        .exclude(group_id='')
        .values_list('group_id', flat=True)
        .first()
    )
    return Question.objects.filter(group_id=first).count() if first else 1


def build_session(user, kind='topic', ege_number=None, difficulty=None,
                  mode='study', size=None, mix=None):
    """
    Создаёт сессию с задачами. Возвращает None, если подходящих задач нет.

    mix – словарь {уровень: сколько задач}, задаётся вместо difficulty и size,
    когда ученик собирает состав вручную («две базовых и две высокой»).
    """
    # cap – потолок для достройки связок. None означает «сколько получится»:
    # там, где состав задан не числом, а самим набором задач (долг по ошибкам,
    # набор для урока), обрезать нечего – иначе связка вытеснила бы реальную
    # ошибку, и счётчик на кнопке разошёлся бы с содержимым сессии.
    if kind == 'classroom':
        # Урок идёт в режиме учёбы: разбор задачи нужен сразу, на месте.
        questions = pick_classroom_questions(ege_number)
        mode = 'study'
        cap = None
    elif kind == 'mistakes':
        questions = pick_mistake_questions(user, size=size, ege_number=ege_number)
        ege_number = None
        cap = size
    elif kind == 'mixed':
        questions = pick_mixed_questions(user, size=size or EXAM_MAX_SIZE)
        ege_number = None
        cap = size or EXAM_MAX_SIZE
    elif mode == 'exam':
        # Состав экзамена ученик не выбирает: ни сложность, ни размер. Иначе
        # «экзамен» из пяти базовых задач ничего не проверял бы.
        questions = pick_exam_questions(user, ege_number)
        difficulty = None
        cap = exam_session_size(ege_number)
    elif mix:
        questions = pick_by_mix(user, ege_number, mix)
        difficulty = None
        cap = sum(mix.values())
    else:
        questions = pick_topic_questions(user, ege_number, difficulty, size)
        cap = size or session_size(ege_number)

    if not questions:
        return None

    # Связки достраиваем на выходе из отбора – одно место на все сценарии.
    questions = expand_groups(questions, size=cap)

    session = PracticeSession.objects.create(
        user=user, kind=kind, mode=mode,
        ege_number=ege_number, difficulty=difficulty,
    )
    PracticeItem.objects.bulk_create([
        PracticeItem(session=session, question=q, order=i)
        for i, q in enumerate(questions)
    ])
    _carry_solved(user, session)
    return session


def _carry_solved(user, session, skip_question_id=None):
    """
    Подставляет прошлый верный ответ в те задачи связки, что уже решены.

    skip_question_id – задача, которую ученик как раз сел решать: в сессии
    «Переписать решение» она тоже давно решена, но подставлять в неё ответ
    значит отменить сам заход.

    Связка приходит целиком, но перерешивать решённое незачем: в работе над
    ошибками ученик должен править ровно то, где ошибся, а 19-е нужно ему как
    условие игры, а не как задача. Такая запись помечается carried и не идёт
    ни в статистику, ни в долг по ошибкам – зачёт за неё уже получен раньше.

    Экзамена это не касается: там обратной связи нет вообще, и подставленный
    ответ выдал бы исход до конца попытки.
    """
    if session.mode != 'study':
        return

    items = [item for item in session.items.select_related('question')
             if item.question.group_id and item.question_id != skip_question_id]
    if not items:
        return

    previous = {}
    for old in (PracticeItem.objects
                .filter(session__user=user, is_correct=True,
                        question_id__in=[i.question_id for i in items])
                .exclude(session=session)
                .exclude(session__kind__in=EXCLUDED_KINDS)
                .order_by('answered_at')):
        previous[old.question_id] = old

    now = timezone.now()
    carried = []
    for item in items:
        source = previous.get(item.question_id)
        if source is None:
            continue
        item.text_answer = source.text_answer
        item.submission_id = source.submission_id
        item.is_correct = True
        item.score = source.score
        item.answered_at = now
        item.carried = True
        carried.append(item)

    if carried:
        PracticeItem.objects.bulk_update(
            carried,
            ['text_answer', 'submission', 'is_correct', 'score', 'answered_at', 'carried'],
        )


# Имена уровней сложности для шаблонов: числовые ключи словаря Django-шаблон
# разбирает через list-index lookup, и это молча ломается при любой правке.
DIFFICULTY_KEYS = {1: 'base', 2: 'medium', 3: 'high'}


def available_counts(ege_number, user=None):
    """
    Сколько задач доступно ученику по заданию, с разбивкой по сложности.

    Нужно экрану старта: предложить «высокую сложность», когда таких задач ноль,
    значит обещать ученику пустую сессию. Решённые текстовые задачи из счётчика
    вычтены – их он уже не получит.
    """
    qs = bank_queryset(ege_number)
    if user is not None and user.is_authenticated:
        qs = exclude_solved(qs, _solved_question_ids(user, ege_number))
    rows = (
        # Резерв в счётчики формы не входит: ученик не может выбрать эти задачи
        # на тренировку, и показывать их как доступные было бы обманом.
        qs
        .annotate(eff_difficulty=effective_difficulty_expr())
        .values('eff_difficulty')
        .annotate(n=Count('id'))
    )
    counts = {'base': 0, 'medium': 0, 'high': 0}
    for row in rows:
        key = DIFFICULTY_KEYS.get(row['eff_difficulty'])
        if key:
            counts[key] = row['n']
    counts['total'] = counts['base'] + counts['medium'] + counts['high']
    return counts
