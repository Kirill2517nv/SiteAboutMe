"""«Решения других»: галерея задачи, своё решение, лайк, модерация учителя."""
import os
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from accounts.models import Profile

from . import solutions as gallery_rules
from .models import Question, SharedSolution, SolutionLike
from .utils import js_json

ALLOWED_FILE_EXT = {"txt", "csv", "ods", "odt", "xlsx", "doc", "docx", "pdf", "py", "cpp"}
ALLOWED_IMAGE_EXT = {"jpg", "jpeg", "png", "gif", "webp"}
VISIBILITY_VALUES = {value for value, _ in Profile.NAME_VISIBILITY_CHOICES}


def _back_link(question):
    """Откуда пришли в галерею: банк – архив решённого, вариант – его таблица, иначе – тест."""
    quiz = question.quiz
    if quiz.quiz_type in ('bank', 'check') and question.ege_number:
        return reverse('ege:ege_solved', args=[question.ege_number]), f'Задание {question.ege_number}'
    if quiz.quiz_type == 'exam':
        return reverse('ege:ege_results', args=[quiz.id]), 'Результаты варианта'
    return reverse('quizzes:quiz_detail', args=[quiz.id]), quiz.title


def _own_preview(question, user, mine, cards, sort, language):
    """
    Своя карточка для формы «Моё решение» – превью того, что видят другие. В
    общем списке она тоже остаётся (первой): ученик хочет видеть себя среди
    остальных. Под фильтром языка своей карточки в списке может не быть,
    поэтому для превью она берётся из полной галереи.
    """
    full = cards if not language else gallery_rules.gallery(question, user, sort)[0]
    own = next((card for card in full if card['is_own']), None)
    if own is None:
        # Ни кода, ни разбора – карточки ещё нет; псевдоним – тот, что будет,
        # когда она появится (по тем же авторам плюс сам ученик).
        authors = [card['solution'].user_id for card in full] + [user.pk]
        own = {'solution': mine, 'languages': [], 'best_cpu': None, 'best_memory': None,
               'likes': mine.likes.count(), 'is_own': True,
               'pseudonym': gallery_rules.pseudonyms(f'q{question.id}', authors)[user.pk]}
    draft = gallery_rules.draft_view(mine)
    preview = js_json({
        'vis': mine.name_visibility,
        'profileVis': gallery_rules.visibility(user),
        'real': gallery_rules.full_name(user),
        'pseudo': own['pseudonym'],
        # Форма и превью показывают присланное (черновик поверх одобренного):
        # это то, что увидят другие, когда учитель примет.
        'comment': draft['comment'],
        'savedImage': draft['image'].url if draft['image'] else '',
        'savedFile': os.path.basename(draft['file'].name) if draft['file'] else '',
    })
    return own, cards, preview


def _query(sort, language):
    params = {'sort': sort} if sort != 'likes' else {}
    if language:
        params['lang'] = language
    return '?' + urlencode(params) if params else '?'


@login_required
def solutions_view(request, question_id):
    question = get_object_or_404(
        Question.objects.select_related('quiz').prefetch_related('images', 'files'), pk=question_id,
    )
    allowed = gallery_rules.can_view(request.user, question)
    sort = request.GET.get('sort')
    if sort not in gallery_rules.SORTS or (sort != 'likes' and question.question_type != 'code'):
        sort = 'likes'

    language = request.GET.get('lang')
    if language not in gallery_rules.LANGUAGE_LABELS or question.question_type != 'code':
        language = None

    cards, mine, counts, own_card, preview = [], None, {}, None, None
    if allowed:
        cards, counts = gallery_rules.gallery(question, request.user, sort, language)
        if not request.user.is_superuser:
            # Своя запись нужна и без кода: к текстовой задаче приложить разбор.
            mine, _ = SharedSolution.objects.get_or_create(user=request.user, question=question)
            own_card, cards, preview = _own_preview(question, request.user, mine, cards, sort, language)

    mine_draft = gallery_rules.draft_view(mine) if mine else None
    back_url, back_label = _back_link(question)
    profile = getattr(request.user, 'profile', None)
    current = profile.solution_name_visibility if profile else 'anon'
    in_profile = next(title for value, _, title, _ in Profile.NAME_VISIBILITY_OPTIONS if value == current)
    return render(request, 'quizzes/solutions.html', {
        'question': question,
        'is_ege': question.quiz.quiz_type in ('exam', 'bank'),
        'allowed': allowed,
        'cards': cards,
        'mine': mine,
        'mine_draft': mine_draft,
        'own_card': own_card,
        'others_count': sum(1 for card in cards if not card['is_own']),
        'preview_json': preview,
        'sort': sort,
        # Адреса фильтров собираются здесь: у страницы два параметра, и каждая
        # кнопка обязана сохранить второй.
        'sort_links': [
            (key, label, _query(key, language))
            for key, label in (('likes', 'с лайками'), ('cpu', 'быстрые'), ('memory', 'экономные по памяти'))
        ],
        'language_links': [('', 'Все языки', None, _query(sort, None))] + [
            (key, label, counts.get(key, 0), _query(sort, key))
            for key, label in gallery_rules.LANGUAGE_LABELS.items()
        ],
        'language': language or '',
        'back_url': back_url,
        'back_label': back_label,
        # Первая плитка – «как в профиле», с тем, что там выбрано сейчас.
        'visibility_options': [('', '⚙️', 'Как в профиле', f'Сейчас: {in_profile.lower()}')]
                              + Profile.NAME_VISIBILITY_OPTIONS,
        # (поле, значок, заголовок, подпись, accept, что уже загружено, флажок «убрать»)
        'uploads': [
            ('file', '📎', 'Файл', 'Таблица, черновик, код – до 20 МБ', '',
             os.path.basename(mine_draft['file'].name) if mine_draft and mine_draft['file'] else '', 'remove_file'),
            ('image', '🖼️', 'Картинка', 'Фото черновика, скриншот – до 5 МБ', 'image/*',
             'загруженную картинку' if mine_draft and mine_draft['image'] else '', 'remove_image'),
        ],
    })


@login_required
@require_POST
def my_solution_view(request, question_id):
    """Своё решение: как подписать, разбор (комментарий, картинка, файл)."""
    question = get_object_or_404(Question.objects.select_related('quiz'), pk=question_id)
    back = redirect('quizzes:solutions', question_id=question.id)
    if question.id not in gallery_rules.solved_question_ids(request.user, [question.id]):
        messages.error(request, 'Решите задачу, чтобы делиться решением.')
        return back

    solution, _ = SharedSolution.objects.get_or_create(user=request.user, question=question)

    # Подпись касается только автора – сохраняется сразу, без проверки учителем.
    value = request.POST.get('name_visibility')
    if value is not None and (value == '' or value in VISIBILITY_VALUES) and value != solution.name_visibility:
        solution.name_visibility = value
        solution.save(update_fields=['name_visibility'])

    upload = request.FILES.get('file')
    if upload and (upload.size > 20 * 1024 * 1024
                   or os.path.splitext(upload.name)[1].lower().lstrip('.') not in ALLOWED_FILE_EXT):
        messages.error(request, f'Файл – до 20 МБ, расширения: {", ".join(sorted(ALLOWED_FILE_EXT))}')
        return back
    image = request.FILES.get('image')
    if image and (image.size > 5 * 1024 * 1024
                  or os.path.splitext(image.name)[1].lower().lstrip('.') not in ALLOWED_IMAGE_EXT):
        messages.error(request, f'Картинка – до 5 МБ, расширения: {", ".join(sorted(ALLOWED_IMAGE_EXT))}')
        return back

    if 'comment' in request.POST or upload or image:
        sent = gallery_rules.submit_notes(
            solution, request.POST.get('comment', solution.draft_comment or solution.comment).strip(),
            upload, image,
            remove_file=bool(request.POST.get('remove_file')),
            remove_image=bool(request.POST.get('remove_image')),
        )
        messages.success(request, 'Разбор отправлен учителю на проверку – другие увидят его после одобрения.'
                         if sent else 'Сохранено.')
    else:
        messages.success(request, 'Сохранено.')
    return back


@login_required
@require_POST
def like_view(request, solution_id):
    """Лайк/снятие лайка. Лайкать можно то, что можно видеть: решил сам и не скрыто."""
    solution = get_object_or_404(SharedSolution.objects.select_related('question'), pk=solution_id)
    if solution.user_id == request.user.id:
        return JsonResponse({'error': 'Нельзя лайкать своё решение'}, status=403)
    if not gallery_rules.can_view(request.user, solution.question):
        return JsonResponse({'error': 'Сначала решите задачу'}, status=403)
    if solution.hidden and not request.user.is_superuser:
        raise Http404

    deleted, _ = SolutionLike.objects.filter(user=request.user, solution=solution).delete()
    if not deleted:
        SolutionLike.objects.get_or_create(user=request.user, solution=solution)
    return JsonResponse({'liked': not deleted, 'like_count': solution.likes.count()})


@user_passes_test(lambda user: user.is_superuser)
@require_POST
def moderate_view(request, solution_id):
    """Учитель скрывает решение целиком или только разбор – и возвращает обратно."""
    solution = get_object_or_404(SharedSolution, pk=solution_id)
    field = request.POST.get('field')
    if field in ('hidden', 'notes_hidden'):
        setattr(solution, field, not getattr(solution, field))
        solution.save(update_fields=[field])
    return redirect(f"{reverse('quizzes:solutions', args=[solution.question_id])}#s{solution.pk}")


@user_passes_test(lambda user: user.is_superuser)
def review_view(request):
    """Очередь разборов на проверку – самые давние сверху: дольше всех ждут."""
    pending = (SharedSolution.objects.filter(review_status='pending')
               .select_related('user__profile__group', 'question__quiz')
               .order_by('submitted_at', 'pk'))
    return render(request, 'quizzes/solutions_review.html', {
        'items': [
            {'solution': solution, 'author': gallery_rules.full_name(solution.user),
             'draft_filename': os.path.basename(solution.draft_file.name) if solution.draft_file else ''}
            for solution in pending
        ],
    })


@user_passes_test(lambda user: user.is_superuser)
@require_POST
def review_decide_view(request, solution_id):
    """Принять (текст учителя можно поправить, картинку и файл – снять) или отклонить."""
    solution = get_object_or_404(SharedSolution, pk=solution_id)
    if solution.review_status != 'pending':
        messages.error(request, 'Этот разбор уже проверен.')
        return redirect('quizzes:solutions_review')
    note = request.POST.get('note', '').strip()
    if request.POST.get('action') == 'reject':
        gallery_rules.reject_notes(solution, note)
        messages.success(request, 'Разбор отклонён – автор увидит ваше слово.')
    else:
        gallery_rules.approve_notes(
            solution, request.POST.get('comment', solution.draft_comment).strip(),
            drop_image=bool(request.POST.get('drop_image')),
            drop_file=bool(request.POST.get('drop_file')),
            note=note,
        )
        messages.success(request, 'Разбор опубликован.')
    return redirect('quizzes:solutions_review')
