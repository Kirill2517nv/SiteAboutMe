"""Отзывы читателей: звёзды под статьёй и совещательные правки к блокам.

Правка в статью не попадает никогда – её читает учитель на /textbook/feedback/
и вносит в seed сам (почему – в докстринге `Suggestion`).
"""
from django import forms
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.core.validators import FileExtensionValidator
from django.db.models import Avg, Count, Prefetch
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.html import escape
from django.views.decorators.http import require_POST

from .models import Article, ArticleBlock, ArticleRating, Suggestion
from .services import visible_articles, visible_blocks
from .templatetags.textbook_tags import markdown_preview

#: Блоки, у которых есть текстовый исходник: его правят прямо в поле, и под
#: полем строится diff. Картинку, видео и виджет описывают словами.
EDITABLE_TYPES = ('text', 'code', 'formula')
IMAGE_MAX_BYTES = 5 * 1024 * 1024


class SuggestionForm(forms.Form):
    proposed = forms.CharField(max_length=20000, strip=False)
    comment = forms.CharField(required=False, max_length=2000)
    # ImageField сам открывает файл Pillow'ом: переименованный .exe не пройдёт.
    image = forms.ImageField(
        required=False,
        validators=[FileExtensionValidator(['png', 'jpg', 'jpeg', 'webp'])],
    )

    def clean_image(self):
        image = self.cleaned_data.get('image')
        if image and image.size > IMAGE_MAX_BYTES:
            raise forms.ValidationError('Картинка больше 5 МБ')
        return image


def _suggestable_block(user, pk):
    """Блок, который этот человек видит, – иначе 404.

    Правило то же, что у страницы статьи: `visible_articles` + `visible_blocks`.
    Закрытый разбор ученик видит заглушкой, и править в нём нечего – а GET
    исходника иначе отдал бы ему само решение.
    """
    block = get_object_or_404(ArticleBlock.objects.select_related('article'), pk=pk)
    if not visible_articles(user).filter(pk=block.article_id).exists():
        raise Http404
    shown = {b.pk: b for b in visible_blocks(block.article, user)}
    if pk not in shown or (shown[pk].visibility == 'teacher' and not user.is_superuser):
        raise Http404
    return block


@login_required
def block_suggest_view(request, pk):
    """GET – исходник блока для редактора; POST – отправить правку."""
    block = _suggestable_block(request.user, pk)
    editable = block.block_type in EDITABLE_TYPES

    if request.method == 'GET':
        return JsonResponse({
            'editable': editable,
            'type': block.block_type,
            'language': block.code_language,
            'preview_url': reverse('textbook:block_preview', args=[pk]),
            'original': block.content if editable else '',
            'kind': block.get_block_type_display(),
        })
    if request.method != 'POST':
        return JsonResponse({'error': 'Метод не поддерживается'}, status=405)

    open_count = Suggestion.objects.filter(user=request.user, status='new').count()
    if open_count >= Suggestion.OPEN_LIMIT:
        return JsonResponse({'error': f'У вас уже {open_count} нерассмотренных '
                                      'предложений – дождитесь ответа по ним'}, status=429)

    form = SuggestionForm(request.POST, request.FILES)
    if not form.is_valid():
        first = next(iter(form.errors.values()))[0]
        return JsonResponse({'error': first}, status=400)
    data = form.cleaned_data

    # Исходник блока берём из базы, а не из запроса: снимок «было» должен
    # совпадать с тем, что стояло в статье.
    original = block.content if editable else ''
    proposed = data['proposed']
    if not proposed.strip():
        return JsonResponse({'error': 'Напишите, как было бы лучше'}, status=400)
    if original and proposed == original and not data['comment'].strip():
        return JsonResponse({'error': 'Текст не изменён'}, status=400)

    Suggestion.objects.create(
        user=request.user, article=block.article, block=block,
        original=original, proposed=proposed, comment=data['comment'],
        image=data['image'],
    )
    return JsonResponse({'ok': True})


@login_required
@require_POST
def block_preview_view(request, pk):
    """Превью правки так, как её нарисует статья. Код превью не нужно – он и
    на странице показан исходником, для него редактор строит diff сам."""
    block = _suggestable_block(request.user, pk)
    proposed = request.POST.get('proposed', '')[:20000]
    if block.block_type == 'formula':
        html = f'<div class="text-center text-lg">\\[ {escape(proposed)} \\]</div>'
    elif block.block_type == 'text':
        html = markdown_preview(block.content, proposed)
    else:
        raise Http404
    return JsonResponse({'html': html})


@login_required
@require_POST
def article_rate_view(request, slug):
    """Звёзды читателя. Повторный POST меняет оценку, а не добавляет вторую."""
    article = get_object_or_404(visible_articles(request.user), slug=slug)
    try:
        stars = int(request.POST.get('stars', ''))
    except ValueError:
        stars = 0
    if not 1 <= stars <= 5:
        return JsonResponse({'error': 'Оценка от 1 до 5'}, status=400)
    comment = request.POST.get('comment', '').strip()[:2000]
    ArticleRating.objects.update_or_create(
        user=request.user, article=article,
        defaults={'stars': stars, 'comment': comment},
    )
    return JsonResponse({'ok': True, 'stars': stars})


@login_required
def my_suggestions_view(request):
    """Все предложения автора – продолжение блока из профиля (там последние 8).

    Учитель смотрит чужие через `?user=<id>` – то же правило, что у чужого
    профиля в accounts.ProfileView; ученику параметр ничего не даёт.
    """
    owner = request.user
    if request.user.is_superuser and request.GET.get('user', '').isdigit():
        owner = get_object_or_404(User, pk=request.GET['user'])
    return render(request, 'textbook/my_suggestions.html', {
        'owner': owner,
        'is_own': owner == request.user,
        # ponytail: без пагинации – у одного автора правок десятки, не тысячи.
        'suggestions': owner.suggestions.select_related('article'),
    })


STATUS_FILTERS = ('new', 'accepted', 'rejected', 'all')
#: Сколько правок показывает страница за раз.
PAGE_LIMIT = 200


@user_passes_test(lambda u: u.is_superuser)
def feedback_view(request):
    """Страница учителя: правки (было/стало) и сводка оценок по статьям."""
    tab = 'ratings' if request.GET.get('tab') == 'ratings' else 'suggestions'
    status = request.GET.get('status')
    if status not in STATUS_FILTERS:
        status = 'new'

    # order_by() обязателен: Meta.ordering по дате иначе попадёт в GROUP BY,
    # и каждая правка станет своей группой.
    counts = dict(Suggestion.objects.order_by().values_list('status')
                  .annotate(n=Count('id')))
    context = {
        'tab': tab,
        'status': status,
        'status_tabs': [
            (key, label, counts.get(key, 0) if key != 'all' else sum(counts.values()))
            for key, label in (*Suggestion.STATUS_CHOICES, ('all', 'Все'))
        ],
    }

    if tab == 'suggestions':
        qs = Suggestion.objects.select_related('user', 'article', 'block')
        if status != 'all':
            qs = qs.filter(status=status)
        # ponytail: срез вместо пагинации – очередь «новых» разбирается,
        # и 200 строк хватает; Paginator – когда архив «всех» станет длинным.
        context['suggestions'] = qs[:PAGE_LIMIT]
    else:
        commented = (ArticleRating.objects.exclude(comment='')
                     .select_related('user').order_by('stars', '-updated_at'))
        context['articles'] = (
            Article.objects.annotate(avg=Avg('ratings__stars'), n=Count('ratings'))
            .filter(n__gt=0).order_by('avg', '-n')
            .prefetch_related(Prefetch('ratings', queryset=commented, to_attr='commented'))
        )
    return render(request, 'textbook/feedback.html', context)


@user_passes_test(lambda u: u.is_superuser)
@require_POST
def suggestion_update_view(request, pk):
    """Статус и ответ автору. Возвращает на ту же вкладку и к той же карточке."""
    suggestion = get_object_or_404(Suggestion, pk=pk)
    status = request.POST.get('status')
    if status in dict(Suggestion.STATUS_CHOICES):
        suggestion.status = status
    suggestion.reply = request.POST.get('reply', '').strip()[:2000]
    suggestion.save(update_fields=['status', 'reply'])

    back = request.POST.get('filter')
    if back not in STATUS_FILTERS:
        back = 'new'
    return redirect(f"{reverse('textbook:feedback')}?status={back}#s{pk}")
