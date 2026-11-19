"""
План подготовки к ЕГЭ: форма плана, запуск повторения, страница учителя.

Расчёты – в ege_plan; здесь только HTTP.
"""
from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import ege_plan
from .models import EgePlan
from .utils import js_json


def _hub_url(student):
    url = reverse('ege:ege_list')
    return f'{url}?student={student.id}#plan' if student else f'{url}#plan'


def _default_deadline(today):
    """1 мая учебного года: к этой дате и задуман первый план."""
    deadline = date(today.year, 5, 1)
    return deadline if deadline > today else date(today.year + 1, 5, 1)


@login_required
def plan_edit_view(request):
    """
    Составить или поправить план. Учитель правит план ученика по ?student=<id>
    – ученик может заболеть или прийти в класс посреди года.
    """
    from .views import _viewed_student

    student = _viewed_student(request)
    owner = student or request.user
    plan = EgePlan.objects.filter(user=owner).first()
    bank = ege_plan.bank_sizes()
    max_per_task = max(bank.values(), default=EgePlan.MIN_PER_TASK)
    today = timezone.localdate()
    errors = []

    if request.method == 'POST':
        try:
            deadline = date.fromisoformat(request.POST.get('deadline', ''))
        except ValueError:
            deadline = None
        if deadline is None or deadline <= today:
            errors.append('Дедлайн – дата позже сегодняшней.')
        elif deadline > today + timedelta(weeks=EgePlan.MAX_WEEKS):
            # Без потолка дата 9999 года разложила бы план на сотни тысяч
            # недель – и так на каждом открытии хаба и таблицы учителя.
            errors.append('Дедлайн – не дальше двух лет от сегодняшнего дня.')
            deadline = None
        try:
            per_task = int(request.POST.get('per_task', ''))
        except ValueError:
            per_task = 0
        if not EgePlan.MIN_PER_TASK <= per_task <= max_per_task:
            errors.append(f'Задач на номер – от {EgePlan.MIN_PER_TASK} до {max_per_task}.')
        preset = request.POST.get('preset', EgePlan.DEFAULT_PRESET)
        if preset not in dict(EgePlan.PRESET_CHOICES):
            preset = EgePlan.DEFAULT_PRESET
        order = None
        if preset == 'own':
            order = ege_plan.clean_order(request.POST.get('order', '').split(','))
            if order is None:
                errors.append('Порядок номеров не разобран – выберите его заново.')
        if not errors:
            ege_plan.save_plan(owner, deadline, per_task, preset, order)
            messages.success(request, 'План сохранён')
            return redirect(_hub_url(student))

    presets = {key: ege_plan.preset_order(key) for key in ('easy', 'fast', 'paper')}
    if request.method == 'POST':
        # Форма с ошибкой возвращает введённое, но только разобранное –
        # сырой POST в данные страницы не попадает.
        deadline_value = deadline.isoformat() if deadline else ''
        preset_value, order_value = preset, order or presets.get(preset, presets[EgePlan.DEFAULT_PRESET])
        per_task_value = per_task or EgePlan.DEFAULT_PER_TASK
    else:
        deadline_value = (plan.deadline if plan else _default_deadline(today)).isoformat()
        preset_value = plan.preset if plan else EgePlan.DEFAULT_PRESET
        order_value = plan.order if plan else presets[EgePlan.DEFAULT_PRESET]
        per_task_value = plan.per_task if plan else EgePlan.DEFAULT_PER_TASK
    return render(request, 'quizzes/ege_plan_form.html', {
        'plan': plan,
        'student': student,
        'errors': errors,
        'preset_choices': EgePlan.PRESET_CHOICES,
        'min_per_task': EgePlan.MIN_PER_TASK,
        'default_per_task': EgePlan.DEFAULT_PER_TASK,
        'default_preset': EgePlan.DEFAULT_PRESET,
        'default_deadline': _default_deadline(today),
        'max_per_task': max_per_task,
        'form_json': js_json({
            'presets': presets,
            'order': order_value,
            'preset': preset_value,
            'perTask': min(max(per_task_value, EgePlan.MIN_PER_TASK), max_per_task),
            'deadline': deadline_value,
            'minutes': {n: ege_plan.EGE_RECOMMENDED_TIME[n] for n in ege_plan.NUMBERS},
            'bank': {n: bank.get(n, 0) for n in ege_plan.NUMBERS},
            'monday': ege_plan.monday(today).isoformat(),
        }),
        'today': today.isoformat(),
        'hub_url': _hub_url(student),
    })


@login_required
@require_POST
def review_start_view(request):
    """
    Сессия повторения. numbers – номера через запятую; пусто – все, чей срок
    подошёл. Повторять можно только изученное: номер без верного решения
    повторением не станет, это уже план.
    """
    status = ege_plan.status(request.user)['reviews']
    learned = {row['number'] for row in status['learned']}
    raw = request.POST.get('numbers', '')
    if raw:
        numbers = [int(x) for x in raw.split(',') if x.strip().isdigit()]
    else:
        numbers = status['batch']
    if not numbers or not set(numbers) <= learned:
        raise PermissionDenied('Повторять можно только пройденные номера')
    session = ege_plan.build_review_session(request.user, numbers)
    if session is None:
        messages.warning(request, 'Задач для повторения не нашлось')
        return redirect(_hub_url(None))
    return redirect('ege:ege_practice', pk=session.pk)


@user_passes_test(lambda user: user.is_superuser)
def plans_view(request):
    """
    Планы класса: кто отстаёт и насколько. Числа – из ege_plan.class_rows,
    той же plan_status, что рисует вкладку ученика.
    """
    from .views import _class_filter, _student_list

    students, groups, loose, current = _class_filter(request)
    rows = ege_plan.class_rows(students)

    # По алфавиту – по той же строке, что стоит в ячейке («Фамилия Имя»,
    # иначе логин; ё = е), как в отчёте по блоку учебника. Отстающих видно
    # по красному в колонке отставания, искать в списке приходится человека.
    from accounts.templatetags.profile_tags import surname_first
    rows.sort(key=lambda row: surname_first(row['user']).lower().replace('ё', 'е'))

    # Шкала недель – последние восемь, одна на всю таблицу.
    this_monday = ege_plan.monday(timezone.localdate())
    weeks = [this_monday - timedelta(weeks=i) for i in range(8, 0, -1)]
    for row in rows:
        if row['plan']:
            by_week = {h['monday']: h for h in row['plan']['history']}
            row['cells'] = [by_week.get(w) for w in weeks]

    return render(request, 'quizzes/ege_plans.html', {
        'rows': rows,
        'weeks': weeks,
        'students': _student_list(),
        'groups': groups,
        'has_loose': loose,
        'current_group': current,
    })
