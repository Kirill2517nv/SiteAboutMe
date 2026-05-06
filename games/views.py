import json
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from django.db import transaction

from .models import Category, Question, QuestionMedia, GamePack, GamePackCategory, GameSession
from .forms import CategoryForm, QuestionFormSet, CategoryModerationForm, GamePackForm, QuestionEditForm

MAX_QUESTION_MEDIA_SIZE = 20 * 1024 * 1024  # 20 МБ


def _is_staff(user):
    return user.is_staff


# ─── Landing ─────────────────────────────────────────────────────────────────

def games_landing_view(request):
    game_types = [
        {
            'title': 'Своя игра',
            'description': 'Классическая викторина с темами и вопросами разной стоимости. Создавайте собственные темы и играйте с друзьями.',
            'url_name': 'games:si_list',
            'icon': 'question',
        },
    ]
    return render(request, 'games/landing.html', {'game_types': game_types})


# ─── Своя игра: список паков ──────────────────────────────────────────────────

def svoya_igra_list_view(request):
    packs = (
        GamePack.objects
        .filter(is_public=True)
        .prefetch_related('pack_categories__category__created_by')
    )
    return render(request, 'games/svoya_igra/list.html', {'packs': packs})


# ─── Своя игра: детали пака ───────────────────────────────────────────────────

def svoya_igra_pack_detail_view(request, pack_id):
    qs = {} if request.user.is_staff else {'is_public': True}
    pack = get_object_or_404(GamePack, id=pack_id, **qs)
    pack_categories = (
        pack.pack_categories
        .select_related('category', 'category__created_by')
        .prefetch_related('category__questions')
        .order_by('order')
    )
    return render(request, 'games/svoya_igra/pack_detail.html', {
        'pack': pack,
        'pack_categories': pack_categories,
    })


# ─── Своя игра: игра ──────────────────────────────────────────────────────────

@login_required
def svoya_igra_play_view(request, pack_id):
    pack = get_object_or_404(GamePack, id=pack_id, is_public=True)

    session = (
        GameSession.objects
        .filter(game_pack=pack, created_by=request.user, is_active=True)
        .first()
    )
    if not session:
        session = GameSession.objects.create(
            game_pack=pack,
            created_by=request.user,
            board_state={},
            players=[],
        )

    pack_categories = (
        pack.pack_categories
        .select_related('category', 'category__created_by')
        .prefetch_related('category__questions__media_files')
        .order_by('order')
    )

    categories_data = []
    for pc in pack_categories:
        questions_data = []
        for q in pc.category.questions.all():
            media, answer_media = [], []
            for m in q.media_files.all():
                entry = {'type': m.media_type, 'url': m.file.url}
                (answer_media if m.is_answer else media).append(entry)
            questions_data.append({
                'id': q.id,
                'text': q.text,
                'answer': q.answer,
                'points': q.points,
                'order': q.order,
                'media': media,
                'answer_media': answer_media,
            })
        creator = pc.category.created_by
        author = (creator.get_full_name() or creator.username) if creator else ''
        categories_data.append({
            'id': pc.category.id,
            'title': pc.category.title,
            'author': author,
            'questions': sorted(questions_data, key=lambda x: (x['order'], x['id'])),
        })

    return render(request, 'games/svoya_igra/play.html', {
        'pack': pack,
        'session_id': session.id,
        'board_state_json': json.dumps(session.board_state),
        'players_json': json.dumps(session.players),
        'categories_json': json.dumps(categories_data, ensure_ascii=False),
    })


# ─── Своя игра: обновление сессии (AJAX) ─────────────────────────────────────

@login_required
@require_POST
def svoya_igra_session_update_view(request, session_id):
    session = get_object_or_404(GameSession, id=session_id, created_by=request.user)
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Невалидный JSON'}, status=400)

    session.board_state = data.get('board_state', session.board_state)
    session.players = data.get('players', session.players)
    if 'is_active' in data:
        session.is_active = bool(data['is_active'])
    session.save(update_fields=['board_state', 'players', 'is_active', 'updated_at'])
    return JsonResponse({'ok': True})


# ─── Своя игра: создание темы ─────────────────────────────────────────────────

@login_required
def svoya_igra_create_view(request):
    if request.method == 'POST':
        cat_form = CategoryForm(request.POST)
        q_formset = QuestionFormSet(request.POST, queryset=Question.objects.none())
        size_errors = {}
        if cat_form.is_valid() and q_formset.is_valid():
            for i, form in enumerate(q_formset):
                if not form.cleaned_data or form.cleaned_data.get('DELETE'):
                    continue
                total = sum(
                    f.size
                    for prefix in ('media', 'answer_media')
                    for mt in ('image', 'audio', 'video')
                    for f in request.FILES.getlist(f'{prefix}_{mt}_{i}')
                )
                if total > MAX_QUESTION_MEDIA_SIZE:
                    size_errors[i] = True
            if not size_errors:
                with transaction.atomic():
                    category = cat_form.save(commit=False)
                    category.created_by = request.user
                    category.status = 'pending'
                    category.save()
                    for i, form in enumerate(q_formset):
                        if form.cleaned_data and not form.cleaned_data.get('DELETE'):
                            question = form.save(commit=False)
                            question.category = category
                            question.order = i
                            question.save()
                            _save_media_files(request, question, prefix='media', is_answer=False)
                            _save_media_files(request, question, prefix='answer_media', is_answer=True)
                return redirect('games:si_my')
    else:
        cat_form = CategoryForm()
        q_formset = QuestionFormSet(queryset=Question.objects.none())
        size_errors = {}

    return render(request, 'games/svoya_igra/create.html', {
        'cat_form': cat_form,
        'q_formset': q_formset,
        'size_errors': size_errors,
    })


def _save_media_files(request, question, prefix='media', is_answer=False):
    for media_type in ('image', 'audio', 'video'):
        files = request.FILES.getlist(f'{prefix}_{media_type}_{question.order}')
        for idx, f in enumerate(files[:5]):
            QuestionMedia.objects.create(
                question=question,
                media_type=media_type,
                file=f,
                order=idx,
                is_answer=is_answer,
            )


# ─── Своя игра: мои заявки ───────────────────────────────────────────────────

@login_required
def svoya_igra_my_view(request):
    categories = (
        Category.objects
        .filter(created_by=request.user)
        .prefetch_related('questions')
        .order_by('-created_at')
    )
    pending = [c for c in categories if c.status == 'pending']
    approved = [c for c in categories if c.status == 'approved']
    rejected = [c for c in categories if c.status == 'rejected']
    return render(request, 'games/svoya_igra/my.html', {
        'pending': pending,
        'approved': approved,
        'rejected': rejected,
        'categories_groups': [
            ('На проверке', 'pending', pending, 'text-amber-600 dark:text-amber-400'),
            ('Одобренные', 'approved', approved, 'text-green-600 dark:text-green-400'),
            ('Отклонённые', 'rejected', rejected, 'text-red-600 dark:text-red-400'),
        ],
    })


# ─── Своя игра: модерация ────────────────────────────────────────────────────

@user_passes_test(_is_staff)
def svoya_igra_moderate_list_view(request):
    status_filter = request.GET.get('status', 'pending')
    categories = (
        Category.objects
        .filter(status=status_filter)
        .select_related('created_by')
        .prefetch_related('questions')
        .order_by('-created_at')
    )
    return render(request, 'games/svoya_igra/moderate_list.html', {
        'categories': categories,
        'status_filter': status_filter,
        'status_choices': [('pending', 'На проверке'), ('approved', 'Одобренные'), ('rejected', 'Отклонённые')],
    })


@user_passes_test(_is_staff)
def svoya_igra_moderate_detail_view(request, category_id):
    category = get_object_or_404(Category, id=category_id)
    questions = list(category.questions.prefetch_related('media_files').order_by('order', 'id'))

    if request.method == 'POST':
        form = CategoryModerationForm(request.POST, instance=category)
        if form.is_valid():
            form.save()
            return redirect('games:si_moderate_list')
    else:
        form = CategoryModerationForm(instance=category)

    questions_data = []
    for q in questions:
        media_files = list(q.media_files.all())
        questions_data.append({
            'question': q,
            'q_media': [m for m in media_files if not m.is_answer],
            'a_media': [m for m in media_files if m.is_answer],
            'edit_form': QuestionEditForm(instance=q),
        })

    return render(request, 'games/svoya_igra/moderate_detail.html', {
        'category': category,
        'questions_data': questions_data,
        'form': form,
    })


@user_passes_test(_is_staff)
@require_POST
def svoya_igra_category_edit_view(request, category_id):
    category = get_object_or_404(Category, id=category_id)
    title = request.POST.get('title', '').strip()
    description = request.POST.get('description', '').strip()
    if title:
        category.title = title
        category.description = description
        category.save(update_fields=['title', 'description', 'updated_at'])
    return redirect('games:si_moderate_detail', category_id=category_id)


@login_required
@require_POST
def svoya_igra_question_edit_view(request, question_id):
    question = get_object_or_404(Question, id=question_id)
    is_owner_edit = (
        question.category.created_by == request.user and
        question.category.status == 'rejected'
    )
    if not (request.user.is_staff or is_owner_edit):
        return redirect('games:si_list')

    form = QuestionEditForm(request.POST, instance=question)
    if form.is_valid():
        form.save()
    for media_type in ('image', 'audio', 'video'):
        for prefix, is_answer in [('q', False), ('a', True)]:
            files = request.FILES.getlist(f'{prefix}_{media_type}')
            for idx, f in enumerate(files[:5]):
                QuestionMedia.objects.create(
                    question=question,
                    media_type=media_type,
                    file=f,
                    order=idx,
                    is_answer=is_answer,
                )
    if request.POST.get('next') == 'my_edit':
        return redirect('games:si_my_edit', category_id=question.category_id)
    return redirect('games:si_moderate_detail', category_id=question.category_id)


@login_required
@require_POST
def svoya_igra_media_delete_view(request, media_id):
    media = get_object_or_404(QuestionMedia, id=media_id)
    category_id = media.question.category_id
    is_owner_edit = (
        media.question.category.created_by == request.user and
        media.question.category.status == 'rejected'
    )
    if not (request.user.is_staff or is_owner_edit):
        return redirect('games:si_list')
    if media.file:
        media.file.delete(save=False)
    media.delete()
    if request.POST.get('next') == 'my_edit':
        return redirect('games:si_my_edit', category_id=category_id)
    return redirect('games:si_moderate_detail', category_id=category_id)


# ─── Своя игра: редактирование отклонённой темы (автор) ──────────────────────

@login_required
def svoya_igra_my_category_edit_view(request, category_id):
    category = get_object_or_404(Category, id=category_id, created_by=request.user)
    if category.status != 'rejected':
        return redirect('games:si_my')

    if request.method == 'POST' and 'resubmit' in request.POST:
        title = request.POST.get('title', '').strip()
        description = request.POST.get('description', '').strip()
        if title:
            category.title = title
            category.description = description
            category.status = 'pending'
            category.moderator_comment = ''
            category.save(update_fields=['title', 'description', 'status', 'moderator_comment', 'updated_at'])
        return redirect('games:si_my')

    questions = list(category.questions.prefetch_related('media_files').order_by('order', 'id'))
    questions_data = []
    for q in questions:
        media_files = list(q.media_files.all())
        questions_data.append({
            'question': q,
            'q_media': [m for m in media_files if not m.is_answer],
            'a_media': [m for m in media_files if m.is_answer],
            'edit_form': QuestionEditForm(instance=q),
        })
    return render(request, 'games/svoya_igra/my_edit.html', {
        'category': category,
        'questions_data': questions_data,
    })


# ─── Своя игра: управление паками (персонал) ─────────────────────────────────

@user_passes_test(_is_staff)
def svoya_igra_pack_manage_view(request):
    packs = (
        GamePack.objects
        .select_related('created_by')
        .prefetch_related('pack_categories__category')
        .order_by('-created_at')
    )
    return render(request, 'games/svoya_igra/pack_manage.html', {'packs': packs})


@user_passes_test(_is_staff)
@require_POST
def svoya_igra_pack_toggle_public_view(request, pack_id):
    pack = get_object_or_404(GamePack, id=pack_id)
    pack.is_public = not pack.is_public
    pack.save(update_fields=['is_public', 'updated_at'])
    return redirect('games:si_pack_manage')


# ─── Своя игра: создание пака ────────────────────────────────────────────────

@user_passes_test(_is_staff)
def svoya_igra_pack_create_view(request):
    approved_categories = (
        Category.objects
        .filter(status='approved')
        .prefetch_related('questions')
        .order_by('title')
    )

    if request.method == 'POST':
        pack_form = GamePackForm(request.POST)
        selected_ids = request.POST.getlist('category_ids')
        if pack_form.is_valid() and selected_ids:
            with transaction.atomic():
                pack = pack_form.save(commit=False)
                pack.created_by = request.user
                pack.save()
                for i, cat_id in enumerate(selected_ids):
                    try:
                        cat = approved_categories.get(id=int(cat_id))
                        GamePackCategory.objects.create(game_pack=pack, category=cat, order=i)
                    except (Category.DoesNotExist, ValueError):
                        pass
            return redirect('games:si_list')
    else:
        pack_form = GamePackForm()

    return render(request, 'games/svoya_igra/pack_create.html', {
        'pack_form': pack_form,
        'approved_categories': approved_categories,
    })
