"""Шаблонные фильтры учебника: безопасный Markdown и JSON для виджетов."""
import json

import bleach
import markdown as md
from django import template
from django.utils.safestring import mark_safe

register = template.Library()

# Разрешённые теги/атрибуты для санитизации Markdown-вывода.
# Сознательно уходим от небезопасного {{ content|safe }} из lessons.
_ALLOWED_TAGS = [
    'p', 'br', 'hr',
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    'strong', 'b', 'em', 'i', 'u', 's', 'del', 'mark', 'sub', 'sup',
    'ul', 'ol', 'li',
    'blockquote', 'pre', 'code',
    'a', 'img',
    'table', 'thead', 'tbody', 'tr', 'th', 'td',
    'span', 'div',
]
_ALLOWED_ATTRS = {
    '*': ['class'],
    'a': ['href', 'title', 'target', 'rel'],
    'img': ['src', 'alt', 'title', 'width', 'height'],
}
_ALLOWED_PROTOCOLS = ['http', 'https', 'mailto', 'data']


@register.filter(name='markdownify')
def markdownify(value):
    """Рендер Markdown → санитизированный HTML."""
    if not value:
        return ''
    html = md.markdown(
        value,
        extensions=['fenced_code', 'tables', 'nl2br', 'sane_lists'],
    )
    clean = bleach.clean(
        html,
        tags=_ALLOWED_TAGS,
        attributes=_ALLOWED_ATTRS,
        protocols=_ALLOWED_PROTOCOLS,
        strip=True,
    )
    return mark_safe(clean)


@register.filter(name='widget_config_json')
def widget_config_json(value):
    """Сериализовать widget_config (dict|None) в JSON-строку для data-атрибута."""
    if not value:
        return '{}'
    try:
        return json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return '{}'
