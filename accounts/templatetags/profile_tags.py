from django import template
from datetime import timedelta
from django.utils.html import conditional_escape
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter(is_safe=True)
def bio_paragraphs(value):
    """Разбивает текст по любым переносам строк в <p> теги (для красной строки каждого абзаца)."""
    if not value:
        return ''
    lines = [l.strip() for l in value.splitlines() if l.strip()]
    return mark_safe(''.join(f'<p>{conditional_escape(l)}</p>' for l in lines))


@register.filter
def duration_display(value):
    """timedelta → 'Xч Yм' или 'Yм Zс'."""
    if not isinstance(value, timedelta):
        return '—'
    total_seconds = int(value.total_seconds())
    if total_seconds <= 0:
        return '0с'
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours > 0:
        return f'{hours}ч {minutes}м'
    if minutes > 0:
        return f'{minutes}м {seconds}с'
    return f'{seconds}с'


@register.filter
def duration_short(value):
    """timedelta → компактный формат для карточек: '4ч20м' или '15м'."""
    if not isinstance(value, timedelta):
        return '—'
    total_seconds = int(value.total_seconds())
    if total_seconds <= 0:
        return '0с'
    hours, remainder = divmod(total_seconds, 3600)
    minutes, _ = divmod(remainder, 60)
    if hours > 0:
        return f'{hours}ч{minutes:02d}м' if minutes else f'{hours}ч'
    if minutes > 0:
        return f'{minutes}м'
    return f'{total_seconds}с'
