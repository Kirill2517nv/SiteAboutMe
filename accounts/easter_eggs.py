"""
Пасхалки – секреты сайта, которые ученик находит сам.

Список – здесь, в коде, а не в базе: новая пасхалка – это запись в EGGS и её
логика на странице. У ученика хранится только Profile.easter_eggs –
{ключ: включена}; ключа нет – пасхалка не найдена. Секрет открытия живёт в
JavaScript страницы и найдётся в исходнике: это игрушка, а не защита.
В статистику и отчёты учителя пасхалки не попадают.
"""
from collections import namedtuple
from datetime import timedelta

from django.utils import timezone

# title/blurb – открытая карточка в профиле, hint – закрытая («???»), toast –
# строка всплывающего «Найдена пасхалка» (страница получает её в ответе
# easter_egg_found). Суперпользователь видит все три вида в своём профиле.
Egg = namedtuple('Egg', 'key title blurb hint image toast')

# «Заваруду»: остановка времени на работе с таймером. Первое применение даёт
# базовые секунды, каждое следующее – на шаг больше, но не выше потолка.
# Кулдаун – сутки; учителю-суперпользователю ждать нечего.
ZA_WARUDO_BASE = 15
ZA_WARUDO_STEP = 3
ZA_WARUDO_MAX = 60
ZA_WARUDO_COOLDOWN = timedelta(days=1)

EGGS = [
    Egg(
        key='brainrot',
        title='Чемпион по пролистыванию',
        blurb='Ролики рядом с задачами',
        hint='Не задерживайся ни на одной задаче',
        image='img/easter-eggs/brainrot.png',
        toast='Полистал задачи – устал. Пора смотреть тикитоки)',
    ),
    Egg(
        key='streak',
        title='Серия',
        blurb='Огонь за задачи подряд',
        hint='Не ошибайся несколько раз подряд',
        image='img/easter-eggs/streak.png',
        toast='Три задачи подряд без ошибки – сайт это заметил.',
    ),
    Egg(
        key='zawarudo',
        title='Заваруду',
        blurb='Остановка времени на работе с таймером, раз в сутки',
        hint='Сдай работу, когда часы почти на нуле',
        image='img/easter-eggs/zawarudo.png',
        toast='ZA WARUDO! Время остановлено.',
    ),
]
EGGS_BY_KEY = {egg.key: egg for egg in EGGS}


def _eggs(user):
    profile = getattr(user, 'profile', None) if user.is_authenticated else None
    return profile.easter_eggs if profile else {}


def is_found(user, key):
    return key in _eggs(user)


def is_on(user, key):
    return bool(_eggs(user).get(key))


def unlock(user, key):
    """Открывает и сразу включает. True – только при первом открытии: повтор
    не включает обратно то, что ученик выключил в профиле."""
    from .models import Profile

    profile, _ = Profile.objects.get_or_create(user=user)
    if key not in EGGS_BY_KEY or key in profile.easter_eggs:
        return False
    profile.easter_eggs[key] = True
    profile.save(update_fields=['easter_eggs'])
    return True


def switch(profile, key, on):
    """Включить или выключить найденную. Ненайденную так не открыть."""
    if key in profile.easter_eggs:
        profile.easter_eggs[key] = on
        profile.save(update_fields=['easter_eggs'])


def cards(user):
    """Карточки раздела «Пасхалки» в профиле, в порядке EGGS."""
    eggs = _eggs(user)
    return [{'egg': egg, 'found': egg.key in eggs, 'on': bool(eggs.get(egg.key))} for egg in EGGS]


def za_warudo_seconds(profile):
    """Сколько секунд даст следующее применение: 15, 18, 21… но не больше 60."""
    uses = profile.za_warudo_uses if profile is not None else 0
    return min(ZA_WARUDO_BASE + ZA_WARUDO_STEP * uses, ZA_WARUDO_MAX)


def za_warudo_ready_at(profile):
    """Когда способность снова готова. None – готова сейчас; учителю – всегда None."""
    if profile is None or profile.za_warudo_used_at is None:
        return None
    if getattr(profile.user, 'is_superuser', False):
        return None
    ready = profile.za_warudo_used_at + ZA_WARUDO_COOLDOWN
    return ready if ready > timezone.now() else None


def use_za_warudo(user, kind, obj_id, started=False):
    """
    Остановить время на идущей работе с таймером.

    Возвращает (статус, payload). Секунды реально добавляются к серверному
    дедлайну, а не только рисуются в браузере: иначе обновление страницы или
    второе устройство вернули бы ученика к исходному концу. Кулдаун и счётчик
    живут в профиле, поэтому вся функция под select_for_update – два клика
    подряд не обойдут суточный срок.
    """
    from django.db import transaction

    from quizzes.models import ClassworkAttempt, PracticeSession, Quiz

    from .models import Profile

    with transaction.atomic():
        profile, _ = Profile.objects.select_for_update().get_or_create(user=user)

        # 1. Пасхалка открыта и включена в профиле. Учитель проверяет
        # способность кнопкой отладки, не открывая пасхалку себе.
        if not profile.easter_eggs.get('zawarudo') and not user.is_superuser:
            return 403, {'error': 'off'}

        # 2. Кулдаун. Суперпользователь не ждёт – ему проверять способность.
        ready = za_warudo_ready_at(profile)
        if ready is not None:
            return 409, {'error': 'cooldown', 'ready_at': ready.isoformat()}

        seconds = za_warudo_seconds(profile)
        now = timezone.now()
        deadline = None

        # 3. Работа идёт. Объект чужой или его нет – 404, не идёт – 409.
        if kind == 'practice':
            session = PracticeSession.objects.filter(user=user, pk=obj_id).first()
            if session is None:
                return 404, {'error': 'not_found'}
            if session.mode != 'exam' or session.finished_at is not None:
                return 409, {'error': 'not_running'}
            end = session.deadline
            if end is None or now >= end:
                return 409, {'error': 'not_running'}
            if session.check_quiz_id:
                check = session.check_quiz
                if not check.za_warudo_allowed:
                    return 403, {'error': 'not_allowed'}
            session.frozen_seconds += seconds
            session.save(update_fields=['frozen_seconds'])
            deadline = session.deadline
        elif kind == 'classwork':
            attempt = ClassworkAttempt.objects.filter(user=user, pk=obj_id).first()
            if attempt is None:
                return 404, {'error': 'not_found'}
            if attempt.finished_at is not None or now >= attempt.deadline:
                return 409, {'error': 'not_running'}
            if not attempt.quiz.za_warudo_allowed:
                return 403, {'error': 'not_allowed'}
            attempt.deadline += timedelta(seconds=seconds)
            attempt.save(update_fields=['deadline'])
            deadline = attempt.deadline
        elif kind == 'variant':
            quiz = Quiz.objects.filter(
                pk=obj_id, quiz_type='exam', exam_mode='exam').first()
            if quiz is None:
                return 404, {'error': 'not_found'}
            # У варианта таймер только в браузере, сервер продлевать нечего.
            # Но «начат» надо подтвердить: остановка на неначатом варианте –
            # это просто повторное открытие страницы.
            if not started:
                return 409, {'error': 'not_running'}
        else:
            return 404, {'error': 'not_found'}

        # 4. Секунды выданы – счётчик и срок.
        profile.za_warudo_uses += 1
        profile.za_warudo_used_at = now
        profile.save(update_fields=['za_warudo_uses', 'za_warudo_used_at'])

        next_ready = za_warudo_ready_at(profile)
        return 200, {
            'seconds': seconds,
            'deadline': deadline.isoformat() if deadline else None,
            'next_seconds': za_warudo_seconds(profile),
            'ready_at': next_ready.isoformat() if next_ready else None,
        }
