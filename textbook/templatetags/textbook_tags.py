"""Шаблонные фильтры учебника: безопасный Markdown и JSON для виджетов."""
import json
import re

import bleach
import markdown as md
from django import template
from django.utils.html import escape
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
    # sane_lists пишет start у списка, прерванного таблицей или абзацем:
    # без него пункты 5–6 после таблицы нумеровались бы заново с 1.
    'ol': ['start'],
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

# Ссылка на выходе bleach: атрибуты сериализуются в алфавитном порядке,
# поэтому href идёт первым; rel закрывает новой вкладке доступ к window.opener.
# Все ссылки из текста урока уходят в новую вкладку, не только внешние:
# ссылка внутри урока — это справка «если подзабыли», и уводить с неё читателя
# со страницы, которую он читает, незачем. Раньше здесь стоял lookahead
# `(?=https?:)`, и ссылка на соседний урок открывалась поверх текущего.
_LINK = re.compile(r'<a href="')
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
    return mark_safe(_LINK.sub(_TARGET_BLANK, clean))


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


_TITLE_CODE = re.compile(r'`([^`]+)`')


@register.filter(name='title_code')
def title_code(value):
    """Заголовок блока: бэктики → <code>, и ничего больше.

    Уроки про методы и операторы состоят из кода прямо в заголовке –
    «`find()` и `rfind()`: где именно стоит кусок», – а сырым текстом бэктики
    так и выводились бэктиками. Полный markdown сюда не годится: заголовок
    «1. Попасть в мишень» он превращает в нумерованный список, а строку,
    начатую с решётки, – в ещё один заголовок внутри h2. Нужен ровно один
    случай, поэтому разбирается только он.
    """
    escaped = escape(value or '')
    return mark_safe(_TITLE_CODE.sub(r'<code>\1</code>', escaped))


@register.filter(name='widget_config_json')
def widget_config_json(value):
    """Сериализовать widget_config (dict|None) в JSON-строку для data-атрибута."""
    if not value:
        return '{}'
    try:
        return json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return '{}'


@register.filter(name='plural')
def plural(value, forms):
    """
    Русское окончание по числу: «1 балл», «2 балла», «5 баллов».

    Встроенный pluralize знает только две формы и на третьей молча отдаёт
    пустую строку – отсюда «2 балл» и «3 блок» на страницах. Три формы через
    запятую: для 1, для 2–4 и для 5–20.
    """
    try:
        value = abs(int(value))
    except (TypeError, ValueError):
        return ''
    bits = forms.split(',')
    if len(bits) != 3:
        return ''
    # 11–19 – исключение: «11 баллов», а не «11 балл».
    if value % 100 // 10 == 1:
        return bits[2]
    remainder = value % 10
    if remainder == 1:
        return bits[0]
    if 2 <= remainder <= 4:
        return bits[1]
    return bits[2]


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


#: Классы пометок diff – общие с живым diff в редакторе (article-feedback.js).
DIFF_DEL = 'bg-red-100 text-red-800 line-through dark:bg-red-950/60 dark:text-red-300'
DIFF_INS = 'bg-green-100 text-green-800 dark:bg-green-950/60 dark:text-green-300'
_DIFF_TOKEN = re.compile(r'\s+|\w+|[^\w\s]')


@register.simple_tag
def word_diff(before, after):
    """Пословный diff «было/стало» для страницы правок: удалённое красным, новое зелёным.

    Слова, а не символы: правка «ячейка → именованная ячейка» читается как
    вставка одного слова, а посимвольный diff нарезал бы её на буквы.
    """
    import difflib

    a, b = _DIFF_TOKEN.findall(before or ''), _DIFF_TOKEN.findall(after or '')
    out = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op == 'equal':
            out.append(escape(''.join(a[i1:i2])))
            continue
        if i2 > i1:
            out.append(f'<del class="{DIFF_DEL}">{escape("".join(a[i1:i2]))}</del>')
        if j2 > j1:
            out.append(f'<ins class="{DIFF_INS} no-underline">{escape("".join(b[j1:j2]))}</ins>')
    return mark_safe(''.join(out))


# Метки вставки – символы из Private Use Area: Markdown и bleach пропускают их
# как обычный текст, в статьях их не бывает, и после рендера они становятся <ins>.
_INS_OPEN, _INS_CLOSE = '', ''
# Формула и `код` – один токен: метка внутри $…$ сломала бы MathJax.
_PREVIEW_TOKEN = re.compile(r'\$\$.*?\$\$|\$[^$\n]+\$|`[^`\n]+`|\s+|\w+|[^\w\s]', re.S)
# Разметка начала строки (пункт списка, заголовок, цитата, ячейка таблицы) и
# хвостовой «|» остаются снаружи метки, иначе «- пункт» – уже не список.
_LINE_PARTS = re.compile(r'(\s*(?:(?:[-*+]|\d+\.)\s+|#{1,6}\s+|>\s*|\|\s*)?)(.*?)(\s*\|?\s*)$', re.S)


def _mark_inserted(chunk):
    """Обернуть вставленный кусок метками – по строке, чтобы <ins> не пересекал абзацы."""
    if '$$' in chunk and '\n' in chunk:
        return chunk   # многострочная формула – метка разорвала бы её
    lines = []
    for line in chunk.split('\n'):
        lead, body, trail = _LINE_PARTS.match(line).groups()
        if body and not body.startswith('```'):
            line = f'{lead}{_INS_OPEN}{body}{_INS_CLOSE}{trail}'
        lines.append(line)
    return '\n'.join(lines)


def markdown_preview(before, after):
    """Предложенный текст так, как его нарисует статья, – новые слова подсвечены.

    Рендер – тот же `markdownify`, что у статьи: превью в редакторе правки не
    может разойтись со страницей. Удалённое не показывается – его видно в поле
    над превью, а вставленный обратно в разметку зачёркнутый Markdown
    (половина `**`, пункт списка) ломал бы структуру того, что осталось.
    """
    import difflib

    # Метки из самого текста вычищаем: вписанная вручную метка внутри атрибута
    # (`title="…"`) после замены на <ins class="…"> разорвала бы кавычки.
    strip = str.maketrans('', '', _INS_OPEN + _INS_CLOSE)
    before, after = (before or '').translate(strip), (after or '').translate(strip)
    a, b = _PREVIEW_TOKEN.findall(before), _PREVIEW_TOKEN.findall(after)
    parts = []
    for op, _, _, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        chunk = ''.join(b[j1:j2])
        parts.append(_mark_inserted(chunk) if op != 'equal' and chunk.strip() else chunk)
    html = str(markdownify(''.join(parts)))
    return mark_safe(html.replace(_INS_OPEN, f'<ins class="{DIFF_INS} no-underline">')
                         .replace(_INS_CLOSE, '</ins>'))
