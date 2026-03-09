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


def home_page_view(request):
    changelog_versions = parse_changelog()
    return render(request, 'home.html', {'changelog_versions': changelog_versions})


def about_page_view(request):
    blocks = ContentBlock.objects.filter(page='about').order_by('order')
    return render(request, 'about.html', {'blocks': blocks, 'page_type': 'about'})
