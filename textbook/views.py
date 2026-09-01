from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.db.models import Count, F, Prefetch, Q, Sum
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.models import StudentGroup
from quizzes.models import Question, Quiz, UserAnswer, UserResult

from .models import Article, ArticleProgress, ArticleQuiz, Section
from .services import (
    attempted_quiz_ids,
    correct_answers_count,
    frontier_positions,
    personal_deadlines,
    quiz_state,
    section_deadline,
    section_is_closed,
    section_quiz_stats,
    visible_articles,
    visible_group_ids,
)


def _lesson_check_color(state, is_read):
    """
    Цвет галочки урока. Определяется результатом микротеста, а не прокруткой:
    прочитанный урок с несданным тестом — красный, потому что тема не проверена.
    Пустая строка — рисуем по статусу чтения (у урока нет теста либо он не начат).
    """
    if state and state != 'pending':
        return state
    if state == 'pending' and is_read:
        return 'red'
    return ''


def _article_quiz_states(user, articles):
    """
    {article_id: 'green'|'yellow'|'red'} — результат микротеста по каждой статье.

    Тем же цветом красится галочка в сайдбаре статьи и в списке уроков на главной,
    поэтому цвет считает общая функция `quiz_state`.
    """
    if not user.is_authenticated or not articles:
        return {}

    links = list(
        ArticleQuiz.objects.filter(article__in=articles)
        .annotate(n_questions=Count('quiz__questions', distinct=True))
        .values_list('article_id', 'quiz_id', 'n_questions')
    )
    if not links:
        return {}

    correct_by_quiz = dict(
        UserAnswer.objects
        .filter(user_result__user=user, user_result__quiz_id__in={ln[1] for ln in links},
                is_correct=True)
        .values('user_result__quiz_id')
        .annotate(n=Count('question_id', distinct=True))
        .values_list('user_result__quiz_id', 'n')
    )

    attempted = attempted_quiz_ids(user, {ln[1] for ln in links})

    states = {}
    for article_id, quiz_id, n_questions in links:
        state = quiz_state(min(correct_by_quiz.get(quiz_id, 0), n_questions), n_questions,
                           quiz_id in attempted)
        # 'pending' — тест у урока есть, но ученик его не сдавал: решение о цвете
        # принимает вызывающая сторона, ей известен статус чтения.
        states[article_id] = state or 'pending'
    return states


def _bar(done, total, url=''):
    """Данные одной шкалы прогресса для шаблона."""
    return {'done': done, 'total': total, 'url': url,
            'pct': round(done / total * 100) if total else 0}


def textbook_home_view(request):
    """Главная учебника с двумя вкладками: учебный материал (аккордеон по блокам) и теория ЕГЭ."""
    progress_map = {}
    quiz_stats = {}
    article_states = {}
    group_ids = visible_group_ids(request)
    frontier = frontier_positions(group_ids)
    # По умолчанию раскрыт блок, где стоит фишка самого зрителя: то же правило,
    # по которому учитель видит аватарки класса на маршруте, второй раз не считаем.
    # Метка «вы здесь» с карты курса сюда не годится намеренно: она уезжает по
    # дедлайну, а здесь ученика надо вернуть туда, где он на самом деле встал.
    # У учителя и у ученика без класса фишки нет — таким открываем первый блок.
    my_frontier = next(
        (article_id for article_id, students in frontier.items()
         if any(s.id == request.user.id for s in students)),
        None,
    )
    if request.user.is_authenticated:
        progress_map = dict(
            ArticleProgress.objects.filter(user=request.user, article__track='material')
            .values_list('article_id', 'status')
        )
        quiz_stats, article_states = section_quiz_stats(request.user)

    # Статьи всех блоков забираем одним prefetch: раньше на каждый блок и на
    # каждое задание ЕГЭ уходил свой запрос — под полсотни на главную.
    material_sections = []
    total_lessons = total_done = 0
    extensions = personal_deadlines(request.user)
    published_articles = Prefetch(
        'articles',
        queryset=Article.objects.filter(track='material', is_published=True),
        to_attr='published_articles',
    )
    for section in Section.objects.filter(is_published=True).prefetch_related(published_articles):
        items = []
        done = 0
        for art in section.published_articles:
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
                'quiz_state': _lesson_check_color(article_states.get(art.id, ''), is_done),
                'frontier': frontier.get(art.id, []),
            })
        total_lessons += len(items)
        total_done += done
        stats = quiz_stats.get(
            section.id, {'practicum': [0, 0], 'self_check': [0, 0], 'url': ''}
        )
        practicum = _bar(*stats['practicum'], url=stats['url'])
        material_sections.append({
            'section': section, 'items': items, 'done': done, 'total': len(items),
            'practicum': practicum,
            'self_check': _bar(*stats['self_check']),
            # Оценка выставляется по числу решённых задач практикума; пороги задаёт
            # учитель в админке, без них оценки за блок нет.
            'grade': section.grade_for(practicum['done']) if request.user.is_authenticated else None,
            'grade_scale': section.grade_scale(practicum['done']),
            'is_closed': section_is_closed(section, extensions.get(section.id)),
            # Продлённый ученик видит свою дату, а не общую «прошёл».
            'deadline': section_deadline(section, extensions.get(section.id)),
            'is_open': any(item['article'].id == my_frontier for item in items),
        })

    if material_sections and not any(row['is_open'] for row in material_sections):
        material_sections[0]['is_open'] = True

    context = {
        'material_sections': material_sections,
        # Панель фильтра классов — только учителю; ученик видит свой класс без выбора.
        'student_groups': (
            [{'group': g, 'checked': g.id in group_ids}
             for g in StudentGroup.objects.filter(graduation_year__isnull=True).order_by('name')]
            if request.user.is_superuser else []
        ),
        'total_lessons': total_lessons,
        'total_done': total_done,
        'progress_pct': round(total_done / total_lessons * 100) if total_lessons else 0,
    }
    return render(request, 'textbook/textbook_home.html', context)


def article_detail_view(request, slug):
    """Детальная статья: блоки контента + самопроверки. Открытие фиксирует прогресс."""
    article = get_object_or_404(
        visible_articles(request.user).select_related(
            'section', 'section__practicum_quiz', 'ege_task',
        ).prefetch_related('blocks', 'self_check_quizzes__quiz'),
        slug=slug,
    )
    blocks = article.blocks.all()

    # Микротест ничего не блокирует — он лишь показывает ученику, как он ответил:
    # зелёный (все верно), жёлтый (половина и больше), красный (меньше половины).
    self_checks = []
    for sc in article.self_check_quizzes.all():
        total = sc.quiz.questions.count()
        done = correct_answers_count(request.user, sc.quiz) if request.user.is_authenticated else 0
        attempted = bool(
            request.user.is_authenticated
            and attempted_quiz_ids(request.user, [sc.quiz_id])
        )
        self_checks.append({
            'link': sc, 'total': total, 'done': done,
            'state': quiz_state(done, total, attempted),
        })

    # Соседние статьи для сайдбара и prev/next: тот же блок (material) или то же задание ЕГЭ.
    if article.track == 'ege' and article.ege_task_id:
        siblings = list(article.ege_task.articles.filter(track='ege', is_published=True))
        group_title = f'Задание {article.ege_task.number}. {article.ege_task.title}'
        article_number = ''
        # Назад – на карточку своего задания: там же и задачи по этой теме.
        # Прежняя вкладка «Теория» на /ege/ упразднена.
        back_url = reverse('ege:ege_task', kwargs={'number': article.ege_task.number})
        back_label = f'Задание {article.ege_task.number}'
    elif article.section_id:
        siblings = list(article.section.articles.filter(track='material', is_published=True))
        group_title = article.section.title
        article_number = f'{article.section.order}.{article.order}'
        back_url = reverse('textbook:home')
        back_label = 'Учебник'
    else:
        siblings = [article]
        group_title = ''
        article_number = ''
        back_url = reverse('textbook:home')
        back_label = 'Учебник'

    progress_map = {}
    if request.user.is_authenticated and siblings:
        progress_map = dict(
            ArticleProgress.objects.filter(user=request.user, article__in=siblings)
            .values_list('article_id', 'status')
        )
    # Номер вида «1.4» показываем только для учебного материала: у статей ЕГЭ
    # сквозной нумерации нет.
    quiz_states = _article_quiz_states(request.user, siblings)
    sidebar_items = [
        {
            'article': sib,
            'status': progress_map.get(sib.id, 'not_started'),
            'num_label': f'{article.section.order}.{sib.order}' if article.section_id and article.track == 'material' else '',
            'quiz_state': _lesson_check_color(
                quiz_states.get(sib.id, ''),
                progress_map.get(sib.id) in ('read', 'mastered'),
            ),
        }
        for sib in siblings
    ]

    # Практикум блока — не статья, а отдельная страница задач. Показываем его в
    # сайдбаре карточкой под списком уроков, чтобы попасть к задачам из любого урока.
    practicum = None
    practicum_quiz = article.section.practicum_quiz if article.section_id else None
    if practicum_quiz:
        total = practicum_quiz.questions.count()
        done = (min(correct_answers_count(request.user, practicum_quiz), total)
                if request.user.is_authenticated else 0)
        practicum = {
            'url': reverse('quizzes:quiz_detail', kwargs={'quiz_id': practicum_quiz.id}),
            'done': done, 'total': total,
            'pct': round(done / total * 100) if total else 0,
            'grade_scale': article.section.grade_scale(done),
        }

    current_index = siblings.index(article) if article in siblings else 0
    prev_article = siblings[current_index - 1] if current_index > 0 else None
    next_article = siblings[current_index + 1] if current_index < len(siblings) - 1 else None

    progress = None
    if request.user.is_authenticated:
        progress, _ = ArticleProgress.objects.get_or_create(
            user=request.user, article=article,
        )

    # Те же фишки одноклассников, что и в списке уроков на главной учебника:
    # у кого маршрут остановился ровно на этой статье. Аноним не видит никого –
    # правило то же, что в `visible_group_ids`.
    frontier_here = frontier_positions(visible_group_ids(request)).get(article.id, [])

    context = {
        'article': article,
        'blocks': blocks,
        'self_checks': self_checks,
        'progress': progress,
        'frontier': frontier_here,
        'sidebar_items': sidebar_items,
        'practicum': practicum,
        'group_title': group_title,
        'article_number': article_number,
        'back_url': back_url,
        'back_label': back_label,
        'prev_article': prev_article,
        'next_article': next_article,
    }
    return render(request, 'textbook/article_detail.html', context)


# При сдаче теста UserAnswer создаётся и для вопросов, которых ученик не касался,
# — считать их ошибками нельзя, иначе один сданный тест сразу даёт «17 ошибок».
ATTEMPTED = (
    Q(selected_choice__isnull=False)
    | Q(text_answer__isnull=False) & ~Q(text_answer='')
    | Q(code_answer__isnull=False) & ~Q(code_answer='')
)


def _section_quiz_ids(section):
    """Тесты блока: практикум и все микротесты его статей."""
    self_check_ids = list(
        ArticleQuiz.objects.filter(article__section=section).values_list('quiz_id', flat=True)
    )
    return section.practicum_quiz_id, self_check_ids


@user_passes_test(lambda u: u.is_superuser)
def section_stats_view(request, slug):
    """Отчёт учителя по блоку: таблица учеников по группам."""
    section = get_object_or_404(Section, slug=slug)
    practicum_id, self_check_ids = _section_quiz_ids(section)
    all_quiz_ids = [q for q in ([practicum_id] + self_check_ids) if q]

    practicum_total = (
        Quiz.objects.filter(id=practicum_id).annotate(n=Count('questions')).values_list('n', flat=True).first()
        if practicum_id else 0
    ) or 0
    self_check_total = Question.objects.filter(quiz_id__in=self_check_ids).count()

    # Агрегаты по всем ученикам сразу: по запросу на метрику, а не на ученика.
    def answer_stats(quiz_ids):
        rows = (
            UserAnswer.objects.filter(user_result__quiz_id__in=quiz_ids)
            .values('user_result__user_id')
            .annotate(
                correct=Count('question_id', distinct=True, filter=Q(is_correct=True)),
                errors=Count('id', filter=Q(is_correct=False) & ATTEMPTED),
            )
        )
        return {r['user_result__user_id']: r for r in rows}

    practicum_stats = answer_stats([practicum_id]) if practicum_id else {}
    self_check_stats = answer_stats(self_check_ids) if self_check_ids else {}

    read_time = dict(
        ArticleProgress.objects.filter(article__section=section)
        .values('user_id').annotate(t=Sum('time_spent_seconds'))
        .values_list('user_id', 't')
    )
    solve_time = dict(
        UserResult.objects.filter(quiz_id__in=all_quiz_ids)
        .values('user_id').annotate(t=Sum('duration'))
        .values_list('user_id', 't')
    ) if all_quiz_ids else {}
    articles_read = dict(
        ArticleProgress.objects.filter(article__section=section, status__in=('read', 'mastered'))
        .values('user_id').annotate(n=Count('id')).values_list('user_id', 'n')
    )

    def row_for(user):
        practicum = practicum_stats.get(user.id, {})
        self_check = self_check_stats.get(user.id, {})
        errors = practicum.get('errors', 0) + self_check.get('errors', 0)
        practicum_done = min(practicum.get('correct', 0), practicum_total)
        return {
            'user': user,
            'grade': section.grade_for(practicum_done),
            'practicum_done': practicum_done,
            'self_check_done': min(self_check.get('correct', 0), self_check_total),
            'articles_read': articles_read.get(user.id, 0),
            'read_time': read_time.get(user.id) or 0,
            'solve_time': int((solve_time.get(user.id) or timezone.timedelta()).total_seconds()),
            'errors': errors,
            'errors_url': reverse('textbook:section_stats_errors',
                                  kwargs={'slug': section.slug, 'user_id': user.id}),
        }

    groups = []
    for group in (StudentGroup.objects.filter(graduation_year__isnull=True)
                  .prefetch_related('students__user').order_by('name')):
        students = [p.user for p in group.students.all()]
        if students:
            groups.append({'name': group.name, 'rows': [row_for(u) for u in students]})

    # select_related('profile') — в таблице у каждого ученика показывается аватар
    ungrouped = (User.objects.filter(profile__group__isnull=True, is_superuser=False)
                 .select_related('profile').order_by('username'))
    if ungrouped:
        groups.append({'name': 'Без группы', 'rows': [row_for(u) for u in ungrouped]})

    return render(request, 'textbook/section_stats.html', {
        'section': section,
        'groups': groups,
        'practicum_total': practicum_total,
        'self_check_total': self_check_total,
        'articles_total': section.articles.filter(track='material', is_published=True).count(),
    })


@user_passes_test(lambda u: u.is_superuser)
def section_stats_errors_view(request, slug, user_id):
    """Детализация ошибок одного ученика по блоку: где именно ошибся."""
    section = get_object_or_404(Section, slug=slug)
    student = get_object_or_404(User, id=user_id)
    practicum_id, self_check_ids = _section_quiz_ids(section)
    all_quiz_ids = [q for q in ([practicum_id] + self_check_ids) if q]

    wrong = list(
        UserAnswer.objects.filter(
            ATTEMPTED,
            user_result__user=student, user_result__quiz_id__in=all_quiz_ids, is_correct=False,
        )
        .select_related('question', 'question__quiz', 'selected_choice', 'user_result')
        .order_by('question__quiz_id', 'question_id', '-user_result__date_completed')
    )

    # Группируем по вопросу: важно не «сколько раз ошибся», а «на чём спотыкается».
    by_question = {}
    for answer in wrong:
        entry = by_question.setdefault(answer.question_id, {
            'question': answer.question,
            'is_practicum': answer.question.quiz_id == practicum_id,
            'attempts': [],
            'solved_later': False,
        })
        entry['attempts'].append(answer)

    solved_ids = set(
        UserAnswer.objects.filter(
            user_result__user=student, user_result__quiz_id__in=all_quiz_ids, is_correct=True,
        ).values_list('question_id', flat=True)
    )
    for question_id, entry in by_question.items():
        entry['solved_later'] = question_id in solved_ids

    items = sorted(by_question.values(),
                   key=lambda e: (not e['is_practicum'], e['question'].get_title()))

    return render(request, 'textbook/section_stats_errors.html', {
        'section': section,
        'student': student,
        'items': items,
        'total_errors': len(wrong),
    })


@login_required
@require_POST
def track_reading_time_view(request, slug):
    """
    Копит время чтения статьи. JS присылает пачками по несколько десятков секунд,
    только пока вкладка активна.

    Порция ограничена сверху: браузер может прислать что угодно, а показания
    времени идут в отчёт учителю.
    """
    article = get_object_or_404(visible_articles(request.user), slug=slug)
    try:
        seconds = int(request.POST.get('seconds', 0))
    except (TypeError, ValueError):
        seconds = 0

    now = timezone.now()
    progress, created = ArticleProgress.objects.get_or_create(user=request.user, article=article)
    # Начитать можно не больше, чем прошло с прошлой порции: клиентский таймер
    # подкручивается, серверные часы — нет. Иначе цикл POST'ов с seconds=300
    # рисует в отчёт учителю любое время чтения.
    budget = 300 if created else int((now - progress.updated_at).total_seconds())
    seconds = max(0, min(seconds, budget, 300))

    if seconds:
        ArticleProgress.objects.filter(pk=progress.pk).update(
            time_spent_seconds=F('time_spent_seconds') + seconds, updated_at=now,
        )
    from django.http import JsonResponse
    return JsonResponse({'ok': True})


@login_required
@require_POST
def mark_article_read_view(request, slug):
    """Отметить статью прочитанной (ученик долистал до конца). Вызывается из JS."""
    article = get_object_or_404(visible_articles(request.user), slug=slug)
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
