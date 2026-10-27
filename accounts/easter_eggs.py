"""
Пасхалки – секреты сайта, которые ученик находит сам.

Список – здесь, в коде, а не в базе: новая пасхалка – это запись в EGGS и её
логика на странице. У ученика хранится только Profile.easter_eggs –
{ключ: включена}; ключа нет – пасхалка не найдена. Секрет открытия живёт в
JavaScript страницы и найдётся в исходнике: это игрушка, а не защита.
В статистику и отчёты учителя пасхалки не попадают.
"""
from collections import namedtuple

Egg = namedtuple('Egg', 'key title blurb hint image')

EGGS = [
    Egg(
        key='brainrot',
        title='Чемпион по пролистыванию',
        blurb='Ролики рядом с задачами',
        hint='Не задерживайся ни на одной задаче',
        image='img/easter-eggs/brainrot.png',
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
