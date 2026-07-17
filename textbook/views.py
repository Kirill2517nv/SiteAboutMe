from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import Article, ArticleProgress, EgeTask, Section


def textbook_home_view(request):
    """Главная учебника с двумя вкладками: учебный материал (аккордеон по блокам) и теория ЕГЭ."""
    progress_map = {}
    if request.user.is_authenticated:
        progress_map = dict(
            ArticleProgress.objects.filter(user=request.user, article__track='material')
            .values_list('article_id', 'status')
        )

    material_sections = []
    total_lessons = total_done = 0
    for section in Section.objects.filter(is_published=True):
        items = []
        done = 0
        for art in section.articles.filter(track='material', is_published=True):
            status = progress_map.get(art.id, 'not_started')
            is_done = status in ('read', 'mastered')
            is_progress = status == 'reading'
            done += is_done
            items.append({
                'article': art,
                'num_label': f'{section.order}.{art.order}',
                'is_done': is_done,
                'is_progress': is_progress,
                'is_todo': not is_done and not is_progress,
            })
        total_lessons += len(items)
        total_done += done
        material_sections.append({
            'section': section, 'items': items, 'done': done, 'total': len(items),
        })

    ege_tasks = []
    for task in EgeTask.objects.all():
        articles = task.articles.filter(track='ege', is_published=True)
        if articles:
            ege_tasks.append({'task': task, 'articles': articles})

    context = {
        'material_sections': material_sections,
        'ege_tasks': ege_tasks,
        'total_lessons': total_lessons,
        'total_done': total_done,
        'progress_pct': round(total_done / total_lessons * 100) if total_lessons else 0,
    }
    return render(request, 'textbook/textbook_home.html', context)


def article_detail_view(request, slug):
    """Детальная статья: блоки контента + самопроверки. Открытие фиксирует прогресс."""
    article = get_object_or_404(
        Article.objects.select_related('section', 'ege_task').prefetch_related(
            'blocks', 'self_check_quizzes__quiz',
        ),
        slug=slug, is_published=True,
    )
    blocks = article.blocks.all()
    self_checks = article.self_check_quizzes.all()

    # Соседние статьи для сайдбара и prev/next: тот же блок (material) или то же задание ЕГЭ.
    if article.track == 'ege' and article.ege_task_id:
        siblings = list(article.ege_task.articles.filter(track='ege', is_published=True))
        group_title = f'Задание {article.ege_task.number}. {article.ege_task.title}'
        article_number = ''
        back_url = reverse('textbook:home') + '#ege'
    elif article.section_id:
        siblings = list(article.section.articles.filter(track='material', is_published=True))
        group_title = article.section.title
        article_number = f'{article.section.order}.{article.order}'
        back_url = reverse('textbook:home')
    else:
        siblings = [article]
        group_title = ''
        article_number = ''
        back_url = reverse('textbook:home')

    progress_map = {}
    if request.user.is_authenticated and siblings:
        progress_map = dict(
            ArticleProgress.objects.filter(user=request.user, article__in=siblings)
            .values_list('article_id', 'status')
        )
    sidebar_items = [
        {'article': sib, 'status': progress_map.get(sib.id, 'not_started')}
        for sib in siblings
    ]

    current_index = siblings.index(article) if article in siblings else 0
    prev_article = siblings[current_index - 1] if current_index > 0 else None
    next_article = siblings[current_index + 1] if current_index < len(siblings) - 1 else None

    progress = None
    if request.user.is_authenticated:
        progress, _ = ArticleProgress.objects.get_or_create(
            user=request.user, article=article,
        )

    context = {
        'article': article,
        'blocks': blocks,
        'self_checks': self_checks,
        'progress': progress,
        'sidebar_items': sidebar_items,
        'group_title': group_title,
        'article_number': article_number,
        'back_url': back_url,
        'prev_article': prev_article,
        'next_article': next_article,
    }
    return render(request, 'textbook/article_detail.html', context)


@login_required
@require_POST
def mark_article_read_view(request, slug):
    """Отметить статью прочитанной (ученик долистал до конца). Вызывается из JS."""
    article = get_object_or_404(Article, slug=slug, is_published=True)
    progress, _ = ArticleProgress.objects.get_or_create(
        user=request.user, article=article,
    )
    # Не понижаем статус, если уже освоено самопроверкой
    if progress.status not in ('read', 'mastered'):
        progress.status = 'read'
        progress.read_at = timezone.now()
        progress.save(update_fields=['status', 'read_at', 'updated_at'])
    elif progress.read_at is None:
        progress.read_at = timezone.now()
        progress.save(update_fields=['read_at', 'updated_at'])

    from django.http import JsonResponse
    return JsonResponse({'status': progress.status})
