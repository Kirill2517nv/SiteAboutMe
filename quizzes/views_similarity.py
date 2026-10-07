"""
«Похожие решения» – страница учителя: пары учеников, чей код подозрительно
совпадает. Расчёт – similarity.question_pairs.

Две точки входа на один шаблон: номер ЕГЭ (банк и варианты, кнопка на
карточке задания) и тест (практикум блока учебника, ссылка из отчёта по блоку).
"""
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from accounts.templatetags.profile_tags import surname_first

from .models import Question, Quiz
from .similarity import question_pairs


def _label(entry):
    group = getattr(getattr(entry['user'], 'profile', None), 'group', None)
    at = timezone.localtime(entry['at']).strftime('%d.%m.%Y %H:%M') if entry['at'] else ''
    return ' · '.join(filter(None, [surname_first(entry['user']), str(group or 'без класса'), at]))


def _render(request, questions, title, back_url, back_label):
    from .views import _class_filter

    students, groups, loose, current = _class_filter(request)
    user_ids = set(students.values_list('id', flat=True))
    blocks = []
    for q in questions:
        pairs = question_pairs(q, user_ids)
        for p in pairs:
            p['sides'] = [{'label': _label(p['a']), 'lines': p['a_lines']},
                          {'label': _label(p['b']), 'lines': p['b_lines']}]
        if pairs:
            blocks.append({'question': q, 'pairs': pairs})
    return render(request, 'quizzes/similar.html', {
        'title': title,
        'back_url': back_url,
        'back_label': back_label,
        'blocks': blocks,
        'checked': questions.count(),
        'groups': groups,
        'has_loose': loose,
        'current_group': current,
    })


@login_required
def ege_similar_view(request, number):
    from .views_practice import _teacher_task_numbers

    numbers = _teacher_task_numbers(request, number)
    if number != numbers[0]:
        return redirect('ege:ege_similar', number=numbers[0])
    label = f'{numbers[0]}–{numbers[-1]}' if len(numbers) > 1 else str(number)
    questions = (Question.objects.filter(question_type='code', ege_number__in=numbers)
                 .select_related('quiz').order_by('ege_number', 'id'))
    return _render(request, questions, f'Задание {label}: похожие решения',
                   reverse('ege:ege_task', args=[number]), 'Карточка задания')


@login_required
def quiz_similar_view(request, quiz_id):
    if not request.user.is_superuser:
        raise PermissionDenied('Страница открыта учителю')
    quiz = get_object_or_404(Quiz, id=quiz_id)
    questions = quiz.questions.filter(question_type='code').select_related('quiz').order_by('id')
    return _render(request, questions, f'{quiz.title}: похожие решения',
                   reverse('quizzes:quiz_stats', args=[quiz.id]), 'Статистика теста')
