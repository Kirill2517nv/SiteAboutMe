from types import SimpleNamespace

from django.db.models import Prefetch
from django.shortcuts import get_object_or_404, render

from textbook.models import Article

from .models import CourseTask


# Витрина в шапке лендинга. Это НЕ задача из базы: Task_3 – учебное задание, и
# Луну вокруг планеты ученик дописывает в нём сам, поэтому у сайта своя сборка
# (GuiLibrary/Demo_Gravity), где спутник уже есть. Отдельного CourseTask ей не
# заводим – он попал бы в список задач и в статистику; кадру нужны ровно три
# поля, и SimpleNamespace их даёт.
HERO_TASK_SLUG = 'gravity'
HERO_SIM = SimpleNamespace(
    title='Звезда, планета и спутник',
    html_path='spetskurs/wasm/Demo_Gravity.html',
    # 16:9 – под кадр во всю ширину страницы: панели параметров достаётся 30 %
    # ширины, и подписи ползунков перестают обрезаться.
    frame_ratio='16 / 9',
)


def _published_articles(**filters):
    """Статьи спецкурса. Трек тот же, что у учебника, – модель одна на весь сайт."""
    return (Article.objects
            .filter(track='spetskurs', is_published=True, **filters)
            .order_by('order', 'title'))


def landing_view(request):
    # Карточки семестров собираются из тех же CourseTask, что и страница задач:
    # раньше лендинг рисовал их вручную и расходился с базой при первом же
    # переименовании. Статьи – одним prefetch, иначе карточка задачи стоит
    # запроса.
    tasks = list(CourseTask.objects
                 .filter(is_published=True)
                 .prefetch_related(Prefetch(
                     'articles',
                     queryset=_published_articles(),
                     to_attr='published_articles')))
    context = {
        'semester1': [t for t in tasks if t.semester == 1],
        # Семестр 2 – это и есть проекты: LBM и молекулярная динамика написаны
        # школьниками прошлого года, поэтому они показаны как работы, а не как
        # обязательная программа.
        'projects': [t for t in tasks if t.semester == 2],
        'hero_sim': HERO_SIM,
        # Ссылка «открыть разбор» под витриной ведёт на задачу, из которой
        # витрина выросла.
        'hero_task': next((t for t in tasks if t.slug == HERO_TASK_SLUG), None),
        'active_section': 'landing',
    }
    return render(request, 'spetskurs/landing.html', context)


def task_list_view(request):
    # Тот же prefetch, что и на лендинге: карточка пишет, сколько у задачи
    # материалов, и цифра обязана считаться там же, где список под ней. Обратный
    # счётчик `task.articles.count` фильтра публикации не знает и обещал бы
    # «7 материалов» у задачи, разбор которой ещё не выпущен.
    context = {
        'tasks': CourseTask.objects.filter(is_published=True).prefetch_related(
            Prefetch('articles', queryset=_published_articles(),
                     to_attr='published_articles')),
        'active_section': 'tasks',
    }
    return render(request, 'spetskurs/task_list.html', context)


def task_detail_view(request, slug):
    task = get_object_or_404(CourseTask, slug=slug, is_published=True)

    all_tasks = list(CourseTask.objects.filter(is_published=True))
    idx = next((i for i, t in enumerate(all_tasks) if t.pk == task.pk), None)

    context = {
        'task': task,
        # Кадр симуляции ждёт объект под именем simulation – партиал общий с
        # отдельной страницей симуляции, и переименовывать переменную в двух
        # местах ради одного слова смысла нет.
        'simulation': task,
        'articles': _published_articles(course_task=task),
        'prev_task': all_tasks[idx - 1] if idx else None,
        'next_task': all_tasks[idx + 1] if idx is not None and idx < len(all_tasks) - 1 else None,
        'active_section': 'tasks',
    }
    return render(request, 'spetskurs/task_detail.html', context)


def basics_view(request):
    """Основы C++ – статьи спецкурса, не привязанные ни к одной задаче."""
    context = {
        'articles': _published_articles(course_task__isnull=True),
        'active_section': 'basics',
    }
    return render(request, 'spetskurs/basics.html', context)
