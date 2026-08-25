import re
from pathlib import Path
from django.shortcuts import render
from django.conf import settings
from .models import ContentBlock


def parse_changelog():
    """Парсит CHANGELOG.md в структурированные данные для шаблона."""
    changelog_path = Path(settings.BASE_DIR) / 'CHANGELOG.md'
    if not changelog_path.exists():
        return []

    text = changelog_path.read_text(encoding='utf-8')
    versions = []
    current_version = None
    current_category = None
    current_items = None

    for line in text.splitlines():
        # Версия: ## [0.0.2] - 2026-02-09
        m = re.match(r'^## \[(.+?)\] - (.+)$', line)
        if m:
            current_version = {
                'number': m.group(1),
                'date': '.'.join(m.group(2).split('-')[::-1]),
                'categories': [],
            }
            versions.append(current_version)
            current_category = None
            current_items = None
            continue

        if not current_version:
            continue

        # Категория: ### Добавлено
        m = re.match(r'^### (.+)$', line)
        if m:
            current_category = {
                'name': m.group(1),
                'sections': [],
            }
            current_version['categories'].append(current_category)
            current_items = []
            current_category['sections'].append({'title': None, 'items': current_items})
            continue

        if not current_category:
            continue

        # Подраздел: #### Система помощи (`quizzes`)
        m = re.match(r'^#### (.+)$', line)
        if m:
            title = re.sub(r'`([^`]*)`', r'\1', m.group(1))
            current_items = []
            current_category['sections'].append({'title': title, 'items': current_items})
            continue

        # Пункт: - текст
        m = re.match(r'^- (.+)$', line)
        if m and current_items is not None:
            item_text = re.sub(r'`([^`]*)`', r'\1', m.group(1))
            current_items.append(item_text)

    # Убираем пустые секции (top-level без пунктов)
    for version in versions:
        for category in version['categories']:
            category['sections'] = [s for s in category['sections'] if s['items']]

    return versions


def _plural(n, forms):
    """Русское склонение по числу: 1 урок, 2 урока, 5 уроков.

    Встроенный `pluralize` знает только две формы и на «2 урока» ломается.
    """
    if 11 <= n % 100 <= 14:
        return forms[2]
    if n % 10 == 1:
        return forms[0]
    if 2 <= n % 10 <= 4:
        return forms[1]
    return forms[2]


def home_page_view(request):
    """Главная – карта курса: маршрут по всем блокам учебника с прогрессом."""
    from accounts.models import StudentGroup
    from textbook.services import (
        course_map,
        frontier_by_section,
        frontier_positions,
        visible_group_ids,
    )

    rows = course_map(request.user)
    current = next((r for r in rows if r['is_current']), None)

    # Неопубликованные блоки на карте не рисуются вовсе – вместо них в конце
    # маршрута стоит одна карточка «скоро». Так состав будущих блоков можно
    # менять, не показывая ученикам черновые названия.
    has_soon = any(r['is_soon'] for r in rows)
    rows = [r for r in rows if not r['is_soon']]

    # Фишки одноклассников – та же механика, что в списке уроков внутри
    # учебника. Кого показывать, решает `visible_group_ids`: аноним не видит
    # никого, ученик – свой класс, учитель – выбранные галочками.
    # Маршрут прогоняется один раз: лицевая сторона карточки показывает фишки
    # по блоку, оборотная – по каждому уроку.
    group_ids = visible_group_ids(request)
    positions = frontier_positions(group_ids) if group_ids else {}
    by_section = frontier_by_section(positions)
    for row in rows:
        row['frontier'] = by_section.get(row['section'].id, [])
        for item in row['lesson_items']:
            item['frontier'] = positions.get(item['article'].id, [])

    # Змейка: нечётные ряды идут слева направо, чётные – справа налево,
    # поэтому маршрут читается одной непрерывной линией. Колонку считаем
    # здесь, а не в шаблоне: {% cycle %} не умеет разворачивать порядок.
    per_row = 3

    def snake(i):
        line, idx = divmod(i, per_row)
        return line + 1, (idx + 1 if line % 2 == 0 else per_row - idx)

    for i, row in enumerate(rows):
        row['grid_row'], row['grid_col'] = snake(i)
        # Номер уже стоит в кружке карточки – в названии он только съедает ширину
        row['title'] = re.sub(r'^Блок \d+\.\s*', '', row['section'].title)
        n = row['lessons']
        row['lessons_label'] = f"{n} {_plural(n, ('статья', 'статьи', 'статей'))}"

    # Карточка «скоро» занимает следующую клетку змейки после последнего блока.
    soon = dict(zip(('grid_row', 'grid_col'), snake(len(rows)))) if has_soon else None

    # Горизонтальная линия ряда рисуется пунктиром, если в нём стоит только
    # карточка «скоро». Развороты всегда сплошные: пунктирная вертикальная
    # скобка выглядит грубо, а без разворота маршрут рвётся между рядами.
    cells = len(rows) + (1 if has_soon else 0)
    row_count = -(-cells // per_row)
    lines = [
        {'index': k, 'is_soon': k * per_row >= len(rows)}
        for k in range(row_count)
    ]
    turns = [
        {'index': k, 'side': 'right' if k % 2 == 0 else 'left'}
        for k in range(row_count - 1)
    ]

    sections = len(rows)
    lessons = sum(r['lessons'] for r in rows)
    return render(request, 'home.html', {
        'rows': rows,
        'soon': soon,
        'lines': lines,
        'turns': turns,
        'current': current,
        # Карточка с фишками выше – место под ряд аватарок. Признак берём
        # по факту, а не по роли: свой класс видит и ученик.
        'has_pins': any(r['frontier'] for r in rows),
        # Панель выбора классов – только учителю; ученик видит свой класс без выбора.
        'student_groups': (
            [{'group': g, 'checked': g.id in group_ids}
             for g in StudentGroup.objects.filter(graduation_year__isnull=True).order_by('name')]
            if request.user.is_superuser else []
        ),
        'section_label': f"{sections} {_plural(sections, ('блок', 'блока', 'блоков'))}",
        'lesson_label': f"{lessons} {_plural(lessons, ('статья', 'статьи', 'статей'))}",
    })


def changelog_view(request):
    """История версий – раньше жила на главной, теперь отдельной страницей."""
    return render(request, 'changelog.html', {'changelog_versions': parse_changelog()})


def about_page_view(request):
    from .models import AuthorProfile, AuthorPhoto, AuthorVideo, AuthorEvent
    profile = AuthorProfile.objects.filter(is_active=True).first()
    photos = AuthorPhoto.objects.filter(is_visible=True)
    videos = AuthorVideo.objects.filter(is_visible=True)
    events = AuthorEvent.objects.filter(is_visible=True)
    education = events.filter(event_type='education')
    publications = events.filter(event_type='publication')
    conferences = events.filter(event_type='conference')
    blocks = ContentBlock.objects.filter(page='about').order_by('order')
    return render(request, 'about.html', {
        'profile': profile,
        'photos': photos,
        'videos': videos,
        'education': education,
        'publications': publications,
        'conferences': conferences,
        'blocks': blocks,
        'page_type': 'about',
    })
