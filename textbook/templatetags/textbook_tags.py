"""Шаблонные фильтры учебника: безопасный Markdown и JSON для виджетов."""
import json
import re

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


# Строка-пункт списка: «- », «* » или «1. » в начале строки.
_LIST_ITEM = r'(?:[-*+]|\d+\.)[ \t]'
# Абзац, к которому список «прилип» без пустой строки: обычная строка, а сразу
# следом — пункт. В Markdown это не список, а продолжение абзаца, и с nl2br
# дефисы выводятся как текст. Вставляем недостающую пустую строку.
_GLUED_LIST = re.compile(
    r'(?m)^(?P<prev>(?!%s)[^\n]*\S)\n(?=%s)' % (_LIST_ITEM, _LIST_ITEM)
)
_FENCE = re.compile(r'(?ms)^```.*?^```[ \t]*$')

# Внешняя ссылка на выходе bleach: атрибуты сериализуются в алфавитном
# порядке, поэтому href идёт первым. Уводить ученика со страницы урока не
# нужно — такие ссылки открываем в новой вкладке; rel закрывает доступ к
# window.opener. Относительные ссылки (внутри сайта) под шаблон не подходят
# и остаются как есть.
_EXTERNAL_LINK = re.compile(r'<a href="(?=https?:)')
_TARGET_BLANK = '<a target="_blank" rel="noopener noreferrer" href="'


def _unglue_lists(text):
    """Отделяет пустой строкой список, приклеенный к предыдущему абзацу.

    Контент учебника написан без пустой строки перед списками (301 блок),
    а Markdown в этом случае списка не видит. Чиним на рендере, а не правкой
    контента: правило одно, а блоков сотни, и будущие тоже подхватятся.
    Внутри ``` -фенсов ничего не трогаем — там может быть любой текст.
    """
    parts, last = [], 0
    for m in _FENCE.finditer(text):
        parts.append(_GLUED_LIST.sub(r'\g<prev>\n\n', text[last:m.start()]))
        parts.append(m.group(0))
        last = m.end()
    parts.append(_GLUED_LIST.sub(r'\g<prev>\n\n', text[last:]))
    return ''.join(parts)


@register.filter(name='markdownify')
def markdownify(value):
    """Рендер Markdown → санитизированный HTML."""
    if not value:
        return ''
    html = md.markdown(
        _unglue_lists(value),
        extensions=['fenced_code', 'tables', 'nl2br', 'sane_lists'],
    )
    clean = bleach.clean(
        html,
        tags=_ALLOWED_TAGS,
        attributes=_ALLOWED_ATTRS,
        protocols=_ALLOWED_PROTOCOLS,
        strip=True,
    )
    return mark_safe(_EXTERNAL_LINK.sub(_TARGET_BLANK, clean))


@register.filter(name='markdownify_inline')
def markdownify_inline(value):
    """Markdown без внешнего <p> — для заголовков.

    Условие вопроса-однострочника целиком уходит в get_title() и выводится
    внутри <h3>: обёртка в абзац там ломает вёрстку, а разметка вроде `код`
    и **жирного** нужна.
    """
    html = str(markdownify(value)).strip()
    if html.startswith('<p>') and html.endswith('</p>') and '<p>' not in html[3:-4]:
        html = html[3:-4]
    return mark_safe(html)


@register.filter(name='widget_config_json')
def widget_config_json(value):
    """Сериализовать widget_config (dict|None) в JSON-строку для data-атрибута."""
    if not value:
        return '{}'
    try:
        return json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return '{}'


@register.filter(name='time_short')
def time_short(seconds):
    """Секунды → «45 с», «12 мин», «1 ч 05 мин». Ноль показываем прочерком."""
    try:
        seconds = int(seconds or 0)
    except (TypeError, ValueError):
        return '–'
    if seconds <= 0:
        return '–'
    if seconds < 60:
        return f'{seconds} с'
    minutes, secs = divmod(seconds, 60)
    if minutes < 60:
        return f'{minutes} мин'
    hours, minutes = divmod(minutes, 60)
    return f'{hours} ч {minutes:02d} мин'
