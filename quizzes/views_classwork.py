"""
Эндпоинты самостоятельной работы: ученик пишет, учитель ведёт.

Для ученика – начать, автосохранение черновика, журнал надзора, сдача и
балл. Для учителя – открыть и закрыть работу класса, минуты на неё,
разморозка и оценка. Всё JSON/POST, без своих шаблонов.
"""
import json

from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from accounts.models import StudentGroup

from . import classwork
from .models import ClassworkAttempt, Quiz

MAX_SECONDS = 36000  # десять часов: больше за урок не бывает, а опечатку срезаем


def _json(request):
    """Тело запроса как словарь. None – битый JSON или не объект."""
    try:
        data = json.loads(request.body or '{}')
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _attempt(request, pk):
    """Попытка только своя: чужой id – 404, а не рассказ о её существовании."""
    return get_object_or_404(ClassworkAttempt, pk=pk, user=request.user)


def _teacher(user):
    return user.is_superuser


@login_required
@require_POST
def start_view(request, quiz_id):
    quiz = get_object_or_404(Quiz, id=quiz_id, quiz_type='classwork')
    attempt = classwork.start(request.user, quiz)
    if attempt is None:
        return redirect('textbook:home')
    return JsonResponse({'attempt': attempt.id})


@login_required
@require_POST
def save_view(request, pk):
    attempt = _attempt(request, pk)
    data = _json(request)
    if data is None:
        return JsonResponse({'error': 'Невалидный JSON'}, status=400)
    # Проверяем время раньше «заморожена»: если ученик ушёл и время вышло,
    # сдавать надо по часам, а не ждать учителя.
    if classwork.is_expired(attempt):
        classwork.finalize(attempt)
        return JsonResponse({'finished': True}, status=409)
    # Автосохранение, пришедшее уже после «Сдана»: черновик больше не нужен,
    # и отвечать «ok», ничего не записав, было бы враньём.
    if attempt.is_finished:
        return JsonResponse({'finished': True}, status=409)
    if attempt.is_frozen:
        return JsonResponse({'frozen': True}, status=409)
    classwork.save_draft(attempt, data.get('answers'), data.get('languages'))
    return JsonResponse({'ok': True})


@login_required
@require_POST
def event_view(request, pk):
    """Журнал надзора. sendBeacon шлёт FormData, поэтому поля из request.POST."""
    attempt = _attempt(request, pk)
    if attempt.is_finished:
        return HttpResponse(status=204)

    kind = request.POST.get('kind')
    if kind not in ('leave', 'return', 'paste'):
        # Маячок не читает ответ, спорить с ним нечем – просто не пишем мусор.
        return HttpResponse(status=204)

    if kind == 'leave':
        classwork.leave(attempt)
    else:
        raw = request.POST.get('seconds', '')
        seconds = int(raw) if str(raw).isdigit() else 0
        classwork.log(attempt, kind, seconds=max(0, min(seconds, MAX_SECONDS)))
    return HttpResponse(status=204)


@login_required
@require_GET
def state_view(request, pk):
    attempt = _attempt(request, pk)
    if classwork.is_expired(attempt):
        classwork.finalize(attempt)
        attempt.refresh_from_db()
    left = int((attempt.deadline - timezone.now()).total_seconds())
    return JsonResponse({
        'frozen': attempt.is_frozen,
        'finished': attempt.is_finished,
        'left': max(0, left),
    })


@login_required
@require_POST
def finish_view(request, pk):
    attempt = _attempt(request, pk)
    data = _json(request)
    if data is None:
        return JsonResponse({'error': 'Невалидный JSON'}, status=400)
    # Замороженную работу сдаём по последнему сохранённому черновику, а
    # присланное игнорируем: иначе заморозка обходилась бы одним запросом.
    if classwork.accepts_answers(attempt):
        classwork.save_draft(attempt, data.get('answers'), data.get('languages'))
    classwork.finalize(attempt)
    return JsonResponse({'ok': True})


@login_required
@require_GET
def score_view(request, pk):
    attempt = _attempt(request, pk)
    if not attempt.is_finished:
        return JsonResponse({'error': 'Работа не сдана'}, status=409)
    return JsonResponse({
        'score': classwork.score(attempt.result),
        'max': classwork.max_score(attempt.quiz),
        'pending': classwork.pending(attempt.result),
        'released': attempt.quiz.check_released(),
    })


@login_required
@user_passes_test(_teacher)
@require_POST
def control_view(request, quiz_id):
    """Панель учителя: начать и закрыть работу класса, минуты на неё."""
    quiz = get_object_or_404(Quiz, id=quiz_id, quiz_type='classwork')
    action = request.POST.get('action')
    group_id = request.POST.get('group') or ''
    group = StudentGroup.objects.filter(id=group_id).first() if group_id.isdigit() else None

    if action == 'start' and group:
        classwork.open_for_group(quiz, group)
    elif action == 'close' and group:
        classwork.close(quiz, group)
    elif action == 'minutes':
        value = request.POST.get('minutes', '').strip()
        quiz.check_minutes = int(value) if value.isdigit() and 1 <= int(value) <= 235 else None
        quiz.save(update_fields=['check_minutes'])

    # Возврат туда, откуда пришли. Протокол-относительный // не пускаем.
    next_url = request.POST.get('next') or ''
    if not (next_url.startswith('/') and not next_url.startswith('//')):
        next_url = '/'
    return redirect(next_url)


@login_required
@user_passes_test(_teacher)
@require_POST
def unfreeze_view(request, pk):
    attempt = get_object_or_404(ClassworkAttempt, pk=pk)
    classwork.unfreeze(attempt)
    return JsonResponse({'ok': True})


@login_required
@user_passes_test(_teacher)
@require_POST
def grade_view(request, pk):
    attempt = get_object_or_404(ClassworkAttempt, pk=pk)
    value = request.POST.get('grade', '').strip()
    attempt.grade = int(value) if value in ('2', '3', '4', '5') else None
    attempt.save(update_fields=['grade'])
    return JsonResponse({'ok': True, 'grade': classwork.final_grade(attempt)})
