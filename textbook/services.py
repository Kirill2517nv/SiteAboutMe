"""Сервисные функции учебника, вызываемые из quizzes (хуки прогресса)."""
import hashlib
import random

from django.utils import timezone


def shuffle_choices(question_text, choices):
    """Тасует варианты ответа, чтобы правильный не стоял всегда первым.

    Сиды писались «правильный вариант — первым», и на сайте это видно:
    порядок вариантов = порядок создания Choice. Перемешиваем на посеве.

    Порядок детерминированный (зерно — хеш текста вопроса): при повторном
    прогоне seed_textbook_blockN ученик увидит тот же список, а не новый.
    """
    choices = list(choices)
    seed = int(hashlib.md5(question_text.encode('utf-8')).hexdigest()[:8], 16)
    random.Random(seed).shuffle(choices)
    return choices


def replace_blocks(article, blocks):
    """Пересоздаёт блоки статьи, сохраняя картинки, загруженные вручную.

    Файлы к image-блокам заливают через админку, а сиды блоков пересоздают
    содержимое статьи целиком — без переноса привязка `image` терялась бы при
    каждом прогоне seed_textbook_blockN.

    ponytail: картинки раздаются новым image-блокам по порядку следования.
    Если в статью вставили картинку в середину, сопоставление съедет — тогда
    поправить руками в админке.
    """
    from .models import ArticleBlock

    images = iter([
        b.image.name
        for b in article.blocks.filter(block_type='image').order_by('order')
        if b.image
    ])
    article.blocks.all().delete()
    for b in blocks:
        block = ArticleBlock.objects.create(article=article, **b)
        if block.block_type == 'image' and not block.image:
            name = next(images, '')
            if name:
                block.image.name = name
                block.save(update_fields=['image'])


def sync_question_texts(quiz, specs):
    """Переписывает формулировки вопросов на месте, не трогая ответы учеников.

    Сиды пересоздают вопросы только у тестов, которые ещё никто не решал:
    каскад унёс бы UserAnswer вместе с вопросами. Поэтому правку одних лишь
    условий (переезд на Markdown, опечатки) делаем обновлением text/title.
    Вопросы сопоставляются по порядку — в seed-файле и в базе он один и тот
    же; если количество разошлось, набор задач менялся руками и трогать его
    нельзя.
    """
    from quizzes.models import Question

    existing = list(quiz.questions.order_by('id'))
    if len(existing) != len(specs):
        return 0

    changed = []
    for question, spec in zip(existing, specs):
        title, hint = spec.get('title', ''), spec.get('hint', '')
        if question.text != spec['text'] or question.title != title or question.hint != hint:
            question.text, question.title, question.hint = spec['text'], title, hint
            changed.append(question)
    Question.objects.bulk_update(changed, ['text', 'title', 'hint'])
    return len(changed)


def section_for_quiz(quiz):
    """
    Блок учебника, которому принадлежит тест: практикум блока или самопроверка
    его статьи. Для тестов вне учебника — None.
    """
    from .models import ArticleQuiz, Section

    section = Section.objects.filter(practicum_quiz=quiz).first()
    if section:
        return section

    link = (
        ArticleQuiz.objects.filter(quiz=quiz)
        .select_related('article__section').first()
    )
    return link.article.section if link and link.article.section_id else None


def personal_deadlines(user):
    """{section_id: личный дедлайн} – все продления одного ученика, одним запросом.

    Берётся один раз на страницу: и главная, и учебник, и профиль перебирают
    все блоки сразу, а спрашивать продление в цикле – это +14 запросов на
    страницу ради строк, которых у большинства учеников нет вовсе.
    """
    from .models import SectionExtension

    if not getattr(user, 'is_authenticated', False):
        return {}
    return dict(
        SectionExtension.objects.filter(user=user).values_list('section_id', 'deadline')
    )


def section_deadline(section, personal=None):
    """Дедлайн блока глазами конкретного ученика: общий или его продление.

    `personal` – дата из `personal_deadlines()`. Продление только отодвигает:
    у блока без общего дедлайна продлевать нечего (иначе личная дата завела бы
    срок там, где его не было), а дата раньше общей игнорируется.
    """
    if not section.deadline:
        return None
    return max(section.deadline, personal) if personal else section.deadline


def section_is_closed(section, personal=None):
    """Закрыт ли блок для этого ученика: приём решений по его дедлайну."""
    deadline = section_deadline(section, personal)
    return bool(deadline and timezone.now() > deadline)


def quiz_is_locked(quiz, user=None):
    """Прошёл ли дедлайн блока, к которому относится тест, для этого ученика.

    Без `user` отвечает по общему дедлайну – так спрашивает код, у которого
    ученика под рукой нет. Все три точки приёма решений передают его.
    """
    section = section_for_quiz(quiz)
    if not section:
        return False
    if user is None or not section.is_closed:
        # Общий дедлайн ещё не прошёл – продлевать нечего, запрос не делаем.
        return section.is_closed
    return section_is_closed(section, personal_deadlines(user).get(section.id))


def quiz_is_hidden(quiz):
    """Относится ли тест к спрятанному блоку учебника.

    Самопроверки и практикумы учебника открыты любому ученику без назначения
    на группу, поэтому единственный гейт для них — публикация блока.
    """
    section = section_for_quiz(quiz)
    return bool(section and not section.is_published)


def visible_articles(user=None):
    """Статьи, доступные ученику: опубликованные и не из спрятанного блока.

    Блок скрывают целиком (`Section.is_published`), когда его контент ещё не
    готов к показу. Без этого фильтра статья спрятанного блока открывалась бы
    по прямой ссылке: на главной её нет, но URL предсказуем. Статьи ЕГЭ живут
    без блока — отсекать их нечем и незачем.

    Учителю отдаём и спрятанное: вычитывать блок перед публикацией он должен
    на том же сайте, а не в админке.
    """
    from django.db.models import Q

    from .models import Article

    published = Article.objects.filter(is_published=True)
    if user is not None and user.is_superuser:
        return published
    return published.filter(Q(section__isnull=True) | Q(section__is_published=True))


# Подсказка закрыта, пока ученик не упрётся в задачу сам: три неудачные
# попытки, последние дни перед дедлайном блока или рубильник учителя.
HINT_AFTER_FAILURES = 3
HINT_DAYS_BEFORE_DEADLINE = 3


def _section_unlock(quiz):
    """Открыты ли подсказки всему блоку сразу: рубильник учителя или близкий дедлайн."""
    from datetime import timedelta

    section = section_for_quiz(quiz)
    if not section:
        return False
    if section.hints_open:
        return True
    return bool(
        section.deadline
        and section.deadline - timezone.now() <= timedelta(days=HINT_DAYS_BEFORE_DEADLINE)
    )


def _hint_unlocked(user, question):
    from quizzes.models import CodeSubmission, UserAnswer

    if _section_unlock(question.quiz):
        return True

    if question.question_type == 'code':
        failures = CodeSubmission.objects.filter(
            user=user, question=question, status='failed'
        ).count()
    else:
        # ponytail: неверные ответы считаем по всем попыткам теста — отдельного
        # счётчика попыток по задаче у обычных тестов нет.
        failures = UserAnswer.objects.filter(
            user_result__user=user, question=question, is_correct=False
        ).count()
    return failures >= HINT_AFTER_FAILURES


def hint_state(user, question):
    """Состояние подсказки для ученика.

    None — закрыта (ученик не должен знать, что она вообще есть),
    'offer' — открылась, но выбор ещё не сделан,
    'declined' — отказался решать с подсказкой,
    'taken' — открыл текст.
    """
    from quizzes.models import HintChoice

    if not question.hint or not user.is_authenticated:
        return None
    choice = HintChoice.objects.filter(user=user, question=question).first()
    if choice:
        return 'taken' if choice.accepted else 'declined'
    return 'offer' if _hint_unlocked(user, question) else None


def hint_states(user, quiz, questions):
    """{question_id: состояние} для всех задач теста разом — только не-None.

    Поштучный `hint_state` в цикле по задачам давал два-три запроса на задачу;
    на практикуме из двадцати это полсотни запросов на рендер страницы теста.
    Здесь их четыре независимо от числа задач: блок у всех задач теста общий,
    а выборы и счётчики неудач берутся агрегатами.
    """
    from django.db.models import Count

    from quizzes.models import CodeSubmission, HintChoice, UserAnswer

    with_hint = [q for q in questions if q.hint]
    if not with_hint or not user.is_authenticated:
        return {}
    ids = [q.id for q in with_hint]

    chosen = dict(
        HintChoice.objects.filter(user=user, question_id__in=ids)
        .values_list('question_id', 'accepted')
    )
    section_open = _section_unlock(quiz)

    # Считаем неудачи только там, где исход ещё не решён: выбор уже сделан или
    # блок открыт целиком — счётчик ничего не меняет.
    failures = {}
    if not section_open:
        pending = [q for q in with_hint if q.id not in chosen]
        code_ids = [q.id for q in pending if q.question_type == 'code']
        other_ids = [q.id for q in pending if q.question_type != 'code']
        if code_ids:
            failures.update(
                CodeSubmission.objects
                .filter(user=user, question_id__in=code_ids, status='failed')
                .values('question_id').annotate(n=Count('id'))
                .values_list('question_id', 'n')
            )
        if other_ids:
            failures.update(
                UserAnswer.objects
                .filter(user_result__user=user, question_id__in=other_ids, is_correct=False)
                .values('question_id').annotate(n=Count('id'))
                .values_list('question_id', 'n')
            )

    states = {}
    for q in with_hint:
        if q.id in chosen:
            states[q.id] = 'taken' if chosen[q.id] else 'declined'
        elif section_open or failures.get(q.id, 0) >= HINT_AFTER_FAILURES:
            states[q.id] = 'offer'
    return states


def textbook_link_for_quiz(quiz):
    """
    Куда возвращать ученика со страницы теста учебника.

    Возвращает (url, подпись кнопки, url после сдачи). Практикум ведёт в учебник —
    своей статьи у него нет; самопроверка — в статью, к карточке результата.
    Для тестов вне учебника — (None, None, None).
    """
    from django.urls import reverse

    from .models import ArticleQuiz, Section

    if Section.objects.filter(practicum_quiz=quiz).exists():
        url = reverse('textbook:home')
        return url, 'Вернуться в учебник', url

    link = ArticleQuiz.objects.filter(quiz=quiz).select_related('article').first()
    if link:
        url = link.article.get_absolute_url()
        return url, 'Вернуться к статье', f'{url}#self-check'

    return None, None, None


def quiz_state(done, total, attempted=False):
    """
    Цвет результата теста: зелёный — всё верно, жёлтый — половина и больше,
    красный — меньше половины.

    `attempted` отличает «не решал» (цвета нет) от «решал и не ответил верно ни
    разу» — второе должно быть красным, иначе галочка урока останется зелёной
    по факту прочтения и разойдётся с бейджем в статье.
    """
    if not done:
        return 'red' if attempted else ''
    return 'green' if done >= total else ('yellow' if done * 2 >= total else 'red')


def attempted_quiz_ids(user, quiz_ids):
    """Тесты из списка, по которым у ученика есть хотя бы одна сданная попытка."""
    from quizzes.models import UserResult

    if not quiz_ids:
        return set()
    return set(
        UserResult.objects.filter(user=user, quiz_id__in=quiz_ids)
        .values_list('quiz_id', flat=True).distinct()
    )


def section_quiz_stats(user):
    """
    Возвращает (stats, article_states).

    stats: {section_id: {'practicum': [решено, всего], 'self_check': [верно, всего],
    'url': ссылка на практикум}} — практикум и микротесты считаются раздельно:
    первый определяет, пройден ли блок, второй — просто индикатор для ученика.

    article_states: {article_id: 'green'|'yellow'|'red'} — результат микротеста
    статьи, им красится галочка в списке уроков.

    Всё собирается тремя запросами на страницу, а не по запросу на блок.
    """
    from django.db.models import Count
    from django.urls import reverse

    from quizzes.models import UserAnswer

    from .models import ArticleQuiz, Section

    self_check_links = list(
        ArticleQuiz.objects
        .filter(article__track='material', article__is_published=True,
                article__section__isnull=False)
        .annotate(n_questions=Count('quiz__questions', distinct=True))
        .values_list('article__section_id', 'quiz_id', 'n_questions', 'article_id')
    )
    practicum_links = list(
        Section.objects.filter(practicum_quiz__isnull=False)
        .annotate(n_questions=Count('practicum_quiz__questions', distinct=True))
        .values_list('id', 'practicum_quiz_id', 'n_questions')
    )

    quiz_ids = {ln[1] for ln in self_check_links} | {ln[1] for ln in practicum_links}
    if not quiz_ids:
        return {}, {}

    correct_by_quiz = dict(
        UserAnswer.objects
        .filter(user_result__user=user, user_result__quiz_id__in=quiz_ids, is_correct=True)
        .values('user_result__quiz_id')
        .annotate(n=Count('question_id', distinct=True))
        .values_list('user_result__quiz_id', 'n')
    )

    def bucket_for(section_id):
        return stats.setdefault(
            section_id, {'practicum': [0, 0], 'self_check': [0, 0], 'url': ''}
        )

    attempted = attempted_quiz_ids(user, quiz_ids)

    stats = {}
    article_states = {}
    for section_id, quiz_id, n_questions, article_id in self_check_links:
        done = min(correct_by_quiz.get(quiz_id, 0), n_questions)
        bucket = bucket_for(section_id)
        bucket['self_check'][0] += done
        bucket['self_check'][1] += n_questions
        article_states[article_id] = quiz_state(done, n_questions, quiz_id in attempted) or 'pending'
    for section_id, quiz_id, n_questions in practicum_links:
        bucket = bucket_for(section_id)
        bucket['practicum'] = [min(correct_by_quiz.get(quiz_id, 0), n_questions), n_questions]
        bucket['url'] = reverse('quizzes:quiz_detail', kwargs={'quiz_id': quiz_id})
    return stats, article_states


def frontier_positions(group_ids):
    """
    {article_id: [ученики]} — где у каждого ученика стоит аватарка на маршруте.

    Позиция — первая «невзятая» статья при чтении подряд от начала учебника.
    Перепрыгнувший вперёд ученик получает свои баллы в статистику (её считают
    другие функции), но фишка остаётся на первой пропущенной теме: маршрут
    непрерывный.

    «Взята» — самопроверка решена больше чем наполовину: та же граница, что у
    жёлтого уровня в `quiz_state`. У статьи без самопроверки проверять нечего,
    для неё критерий — прочитана, иначе первый же урок без теста остановил бы
    весь класс навсегда.

    ponytail: маршрут прогоняется в питоне (ученики × статьи). При 60 учениках
    и 150 статьях это 9000 сравнений по словарям — дешевле, чем ещё один запрос.
    """
    from collections import defaultdict

    from django.contrib.auth.models import User
    from django.db.models import Count

    from quizzes.models import UserAnswer

    from .models import Article, ArticleProgress, ArticleQuiz

    if not group_ids:
        return {}

    students = list(
        User.objects.filter(is_superuser=False, profile__group_id__in=group_ids)
        .select_related('profile')
        .order_by('last_name', 'first_name', 'username')
    )
    if not students:
        return {}
    student_ids = [s.id for s in students]

    # Порядок тот же, что на главной: блоки по (order, title), статьи внутри — тоже.
    route = list(
        Article.objects
        .filter(track='material', is_published=True, section__is_published=True)
        .order_by('section__order', 'section__title', 'order', 'title')
        .values_list('id', flat=True)
    )
    if not route:
        return {}

    checks = defaultdict(list)  # article_id -> [(quiz_id, число вопросов)]
    for article_id, quiz_id, n_questions in (
        ArticleQuiz.objects.filter(article_id__in=route)
        .annotate(n=Count('quiz__questions', distinct=True))
        .values_list('article_id', 'quiz_id', 'n')
    ):
        checks[article_id].append((quiz_id, n_questions))

    correct = {}  # (user_id, quiz_id) -> верно решённых вопросов
    quiz_ids = {q for links in checks.values() for q, _ in links}
    if quiz_ids:
        correct = {
            (r['user_result__user_id'], r['user_result__quiz_id']): r['n']
            for r in UserAnswer.objects
            .filter(user_result__user_id__in=student_ids,
                    user_result__quiz_id__in=quiz_ids, is_correct=True)
            .values('user_result__user_id', 'user_result__quiz_id')
            .annotate(n=Count('question_id', distinct=True))
        }

    read = set(
        ArticleProgress.objects
        .filter(user_id__in=student_ids, article_id__in=route,
                status__in=('read', 'mastered'))
        .values_list('user_id', 'article_id')
    )

    def is_taken(user_id, article_id):
        links = checks.get(article_id, [])
        total = sum(n for _, n in links)
        if not total:
            return (user_id, article_id) in read
        done = sum(min(correct.get((user_id, quiz_id), 0), n) for quiz_id, n in links)
        return done * 2 >= total

    positions = defaultdict(list)
    for student in students:
        # Дошёл до конца маршрута — фишку ставить некуда, ученик закончил учебник.
        for article_id in route:
            if not is_taken(student.id, article_id):
                positions[article_id].append(student)
                break
    return dict(positions)


def profile_textbook_stats(user):
    """
    Сводка по учебнику для профиля: блоки с оценками, прогресс, что подтянуть.

    Оценка за блок выставляется по числу решённых задач практикума
    (`Section.grade_for`), поэтому средний балл считаем только по блокам, где
    оценка вообще предусмотрена И ученик к ним приступал: иначе в начале года
    средний балл у всех был бы «2» по двадцати нетронутым блокам. Блок с
    прошедшим дедлайном идёт в средний балл всегда — там оценка уже финальная.
    """
    from django.db.models import Count, Sum

    from .models import Article, ArticleProgress, Section

    stats, _ = section_quiz_stats(user)
    extensions = personal_deadlines(user)

    lessons_total = dict(
        Article.objects
        .filter(track='material', is_published=True, section__isnull=False)
        .values('section_id').annotate(n=Count('id'))
        .values_list('section_id', 'n')
    )
    lessons_done = dict(
        ArticleProgress.objects
        .filter(user=user, status__in=('read', 'mastered'),
                article__track='material', article__is_published=True)
        .values('article__section_id').annotate(n=Count('id'))
        .values_list('article__section_id', 'n')
    )

    sections = []
    totals = {'lessons_done': 0, 'lessons_total': 0, 'practicum_done': 0, 'practicum_total': 0}
    grades = []
    for section in Section.objects.filter(is_published=True):
        bucket = stats.get(section.id, {'practicum': [0, 0], 'self_check': [0, 0], 'url': ''})
        practicum_done, practicum_total = bucket['practicum']
        done, total = lessons_done.get(section.id, 0), lessons_total.get(section.id, 0)
        started = bool(done or practicum_done)
        grade = section.grade_for(practicum_done)
        is_closed = section_is_closed(section, extensions.get(section.id))

        # Ближайшая невзятая ступень: ученику важнее «до 4 осталось 2 задачи»,
        # чем сама шкала целиком.
        scale = section.grade_scale(practicum_done)
        next_step = next(
            ({'grade': step['grade'], 'left': step['need'] - practicum_done}
             for step in reversed(scale) if not step['reached']),
            None,
        )

        # Продлённый блок в средний балл не тащим: у ученика оценка ещё не
        # финальная, он как раз досдаёт.
        if grade is not None and (started or is_closed):
            grades.append(grade)
        totals['lessons_done'] += done
        totals['lessons_total'] += total
        totals['practicum_done'] += practicum_done
        totals['practicum_total'] += practicum_total

        sections.append({
            'section': section,
            'lessons_done': done,
            'lessons_total': total,
            'lessons_pct': round(done / total * 100) if total else 0,
            'practicum_done': practicum_done,
            'practicum_total': practicum_total,
            'practicum_url': bucket['url'],
            'self_check_done': bucket['self_check'][0],
            'self_check_total': bucket['self_check'][1],
            'grade': grade,
            'next_step': next_step,
            'started': started,
            'is_closed': is_closed,
            # Дата, которую видит этот ученик: своя, если блок ему продлили.
            'deadline': section_deadline(section, extensions.get(section.id)),
        })

    # Что подтянуть: начатые блоки с нерешёнными задачами практикума. Блоки с
    # дедлайном идут первыми — там время ограничено.
    # `no_deadline` — заглушка для сравнения: блоки без дедлайна уже отделены
    # первым элементом ключа, между собой они сортируются по числу задач.
    no_deadline = timezone.now()
    focus = sorted(
        (s for s in sections
         if s['started'] and not s['is_closed'] and s['practicum_done'] < s['practicum_total']),
        key=lambda s: (
            s['deadline'] is None,
            s['deadline'] or no_deadline,
            -(s['practicum_total'] - s['practicum_done']),
        ),
    )[:3]

    return {
        **totals,
        'sections': sections,
        'focus': focus,
        'lessons_pct': round(totals['lessons_done'] / totals['lessons_total'] * 100)
                       if totals['lessons_total'] else 0,
        'practicum_pct': round(totals['practicum_done'] / totals['practicum_total'] * 100)
                         if totals['practicum_total'] else 0,
        'avg_grade': round(sum(grades) / len(grades), 1) if grades else None,
        'graded_count': len(grades),
        # Только учебный материал: статьи вкладки «Теория ЕГЭ» считаются
        # в своём блоке профиля, иначе их время утечёт сюда.
        'read_seconds': ArticleProgress.objects.filter(user=user, article__track='material')
                        .aggregate(t=Sum('time_spent_seconds'))['t'] or 0,
        'solve_seconds': _solve_seconds(user),
    }


def _solve_seconds(user):
    """
    Время ученика над задачами учебника: практикумы блоков + самопроверки уроков.

    Считается по всем попыткам — вопрос «сколько времени потратил», а не
    «за сколько сдал». Тесты ЕГЭ сюда не входят: у них свой блок в профиле.

    Список тестов приходится собирать явно: у `Section.practicum_quiz` и
    `ArticleQuiz.quiz` стоит `related_name='+'`, обратного пути от Quiz нет.
    """
    from django.db.models import Sum

    from quizzes.models import UserResult

    from .models import ArticleQuiz, Section

    quiz_ids = set(
        Section.objects.filter(practicum_quiz__isnull=False)
        .values_list('practicum_quiz_id', flat=True)
    ) | set(
        ArticleQuiz.objects.filter(article__track='material')
        .values_list('quiz_id', flat=True)
    )
    if not quiz_ids:
        return 0

    total = UserResult.objects.filter(user=user, quiz_id__in=quiz_ids).aggregate(
        t=Sum('duration')
    )['t']
    return int(total.total_seconds()) if total else 0


def correct_answers_count(user, quiz):
    """Число уникальных верно решённых вопросов теста (баллы копятся между попытками)."""
    from quizzes.models import UserAnswer

    return (
        UserAnswer.objects.filter(
            user_result__user=user,
            user_result__quiz=quiz,
            is_correct=True,
        )
        .values('question_id')
        .distinct()
        .count()
    )


def quiz_is_passed(user, quiz):
    """
    Считается ли тест пройденным для ученика: решены все вопросы.

    Процентного порога нет — микротесты после уроков ничего не блокируют,
    они лишь подсвечивают ученику его результат. Условие «блок пройден» —
    задачи практикума в конце блока.
    """
    total_questions = quiz.questions.count()
    if total_questions == 0:
        return False

    return correct_answers_count(user, quiz) >= total_questions


def update_article_mastery(user, quiz):
    """
    Хук после сабмита теста. Если quiz — самопроверка статьи и ученик её
    прошёл, помечает связанные статьи статусом «освоено» (mastered).

    Безопасен к вызову для любого теста: для не-самопроверок сразу выходит.
    """
    if not getattr(quiz, 'is_self_check', False):
        return

    from .models import ArticleProgress, ArticleQuiz

    links = list(ArticleQuiz.objects.filter(quiz=quiz).select_related('article'))
    if not links:
        return

    if not quiz_is_passed(user, quiz):
        return

    now = timezone.now()
    for link in links:
        progress, _ = ArticleProgress.objects.get_or_create(user=user, article=link.article)
        if progress.status != 'mastered':
            progress.status = 'mastered'
            progress.mastered_at = now
            if progress.read_at is None:
                progress.read_at = now
            progress.save(update_fields=['status', 'mastered_at', 'read_at', 'updated_at'])


def visible_group_ids(request):
    """
    Чьи аватарки видит зритель: свой класс, у суперюзера — выбранные галочками.

    Аноним не видит никого: фамилии и фото школьников не должны утекать в
    открытый интернет. Пустой выбор у суперюзера означает «все классы» — это
    состояние формы по умолчанию, до первого клика.
    """
    from accounts.models import StudentGroup

    if not request.user.is_authenticated:
        return []
    if request.user.is_superuser:
        # Выпускные классы живут в архиве и в активную статистику не попадают.
        all_ids = list(StudentGroup.objects.filter(graduation_year__isnull=True)
                       .values_list('id', flat=True))
        chosen = {int(g) for g in request.GET.getlist('group') if g.isdigit()}
        return [g for g in all_ids if g in chosen] or all_ids
    # RelatedObjectDoesNotExist наследуется от AttributeError — getattr отработает
    # и для пользователя без профиля.
    group_id = getattr(getattr(request.user, 'profile', None), 'group_id', None)
    return [group_id] if group_id else []


def _section_entry_article(lessons, progress):
    """
    Статья, на которую ведёт карточка блока с главной.

    Приоритет: последняя прочитанная (по `read_at`), затем та, что читается
    сейчас (по `updated_at`), иначе первый урок блока. Промежуточная ступень
    нужна, потому что `read_at` ставится только когда статью долистали до
    конца: у брошенной на середине его нет, но вернуть ученика надо именно
    туда, а не в начало блока.
    """
    last_read = last_reading = None
    for art in lessons:
        status, read_at, updated_at = progress.get(art.id, (None, None, None))
        if status in ('read', 'mastered') and read_at:
            if last_read is None or read_at > last_read[0]:
                last_read = (read_at, art)
        elif status == 'reading' and updated_at:
            if last_reading is None or updated_at > last_reading[0]:
                last_reading = (updated_at, art)

    if last_read:
        return last_read[1]
    if last_reading:
        return last_reading[1]
    return lessons[0] if lessons else None


def course_map(user):
    """
    Строки карты курса для главной страницы: по строке на каждый блок учебника.

    Отличие от `textbook_home_view`: сюда попадают и неопубликованные блоки.
    На карте они рисуются как «скоро» – без них маршрут обрывался бы на
    середине, а именно непрерывность маршрута и есть смысл карты.

    Блок считается пройденным, если сдан практикум. У блока без практикума
    критерий тот же, что у `frontier_positions`: все уроки прочитаны, иначе
    первый же блок без задач останавливал бы метку «вы здесь» навсегда.
    """
    from django.db.models import Prefetch
    from django.urls import reverse

    from .models import Article, ArticleProgress, Section

    stats = {}
    progress = {}
    extensions = personal_deadlines(user)
    if user.is_authenticated:
        stats, _ = section_quiz_stats(user)
        # Одним запросом: статус плюс обе отметки времени. read_at ставится,
        # когда статью долистали, updated_at обновляется на любом сохранении –
        # по ним и выбирается статья, на которую ведёт карточка блока.
        progress = {
            art_id: (status, read_at, updated_at)
            for art_id, status, read_at, updated_at in (
                ArticleProgress.objects
                .filter(user=user, article__track='material')
                .values_list('article_id', 'status', 'read_at', 'updated_at')
            )
        }

    published = Prefetch(
        'articles',
        queryset=(Article.objects.filter(track='material', is_published=True)
                  .only('id', 'section_id', 'slug', 'order', 'title')
                  .order_by('order')),
        to_attr='published_articles',
    )

    rows = []
    for section in Section.objects.prefetch_related(published):
        bucket = stats.get(
            section.id, {'practicum': [0, 0], 'self_check': [0, 0], 'url': ''}
        )
        prac_done, prac_total = bucket['practicum']
        self_done, self_total = bucket['self_check']
        lessons = section.published_articles
        is_closed = section_is_closed(section, extensions.get(section.id))
        lessons_done = sum(
            1 for a in lessons
            if progress.get(a.id, (None,))[0] in ('read', 'mastered')
        )
        entry = _section_entry_article(lessons, progress)

        if prac_total:
            is_done = prac_done >= prac_total
        else:
            is_done = bool(lessons) and lessons_done == len(lessons)

        grade = section.grade_for(prac_done) if user.is_authenticated else None

        # «Блок закрыт» для метки «вы здесь» – не то же, что «пройден».
        # Достаточно сдать практикум на тройку; полное решение не требуется.
        # Порогов оценок у блока может не быть – тогда критерий «все задачи»,
        # а у блока без практикума – «все уроки прочитаны», иначе метка
        # застряла бы на первом же блоке без задач.
        if grade is not None:
            cleared = grade >= 3
        else:
            cleared = is_done

        rows.append({
            'section': section,
            'lessons': len(lessons),
            'lessons_done': lessons_done,
            # Список уроков для оборотной стороны карточки на главной.
            'lesson_items': [
                {
                    'article': a,
                    'num_label': f'{section.order}.{a.order}',
                    'url': a.get_absolute_url(),
                    'is_read': progress.get(a.id, (None,))[0] in ('read', 'mastered'),
                }
                for a in lessons
            ],
            # Куда ведёт карточка блока. Пустой блок статей не имеет – ведём
            # в оглавление учебника, чтобы ссылка не упиралась в 404.
            'entry_url': entry.get_absolute_url() if entry else reverse('textbook:home'),
            'practicum': {'done': prac_done, 'total': prac_total, 'url': bucket['url'],
                          'pct': round(prac_done / prac_total * 100) if prac_total else 0},
            'self_check': {'done': self_done, 'total': self_total,
                           'pct': round(self_done / self_total * 100) if self_total else 0},
            'grade': grade,
            'grade_scale': section.grade_scale(prac_done),
            'is_done': is_done,
            'is_closed': is_closed,
            'deadline': section_deadline(section, extensions.get(section.id)),
            'is_current': False,
            'is_soon': not section.is_published,
            'cleared': cleared,
            # «Начато чтение» – у статьи есть строка прогресса. Она заводится
            # при первом открытии статьи, поэтому годится как признак того,
            # что ученик до блока добрался.
            'started': any(a.id in progress for a in lessons),
        })

    # Метка «вы здесь» – первый опубликованный блок, который ещё не отпущен.
    # Блок отпускает метку в двух случаях:
    #   1. практикум сдан минимум на тройку И в следующем блоке открыта хотя
    #      бы одна статья. Без второго условия метка убегала бы вперёд по
    #      блоку, которого ученик ещё не открывал;
    #   2. дедлайн блока прошёл – задачи больше не принимаются, держать на нём
    #      метку незачем, двигаем независимо от прогресса.
    # Переезжать некуда, если следующего блока нет или он не опубликован:
    # тогда метка остаётся здесь даже после дедлайна.
    # У гостя текущего блока нет: считать его прогресс не по чему.
    if user.is_authenticated:
        for i, row in enumerate(rows):
            if row['is_soon']:
                continue
            nxt = rows[i + 1] if i + 1 < len(rows) else None
            if nxt and not nxt['is_soon']:
                if (row['cleared'] and nxt['started']) or row['is_closed']:
                    continue
            row['is_current'] = True
            break
    return rows


def frontier_by_section(positions):
    """
    {section_id: [ученики]} из {article_id: [ученики]}, который отдаёт
    `frontier_positions`.

    На карте курса карточка соответствует блоку, поэтому позиции с точностью
    до статьи схлопываются до блока. Ученики внутри блока идут в порядке своих
    статей: сначала те, кто дальше не продвинулся.

    Принимает готовые позиции, а не список групп: главная показывает фишки и
    по блокам, и по отдельным урокам на обороте карточки, а маршрут стоит
    прогонять один раз.
    """
    from .models import Article

    if not positions:
        return {}

    order = dict(
        Article.objects.filter(id__in=positions)
        .values_list('id', 'section_id')
    )
    by_section = {}
    for article_id in sorted(positions, key=lambda a: (order.get(a) or 0, a)):
        section_id = order.get(article_id)
        if section_id:
            by_section.setdefault(section_id, []).extend(positions[article_id])
    return by_section


def ege_theory_groups():
    """
    Теория ЕГЭ, сгруппированная по заданиям: [{'task': EgeTask, 'articles': [...]}].

    Живёт в сервисах, потому что раздел переехал с главной учебника на страницу
    тренажёра ЕГЭ, а статьи по-прежнему принадлежат приложению textbook.
    Задания без опубликованных статей не показываем – пустой заголовок только
    сбивает с толку.
    """
    from django.db.models import Prefetch

    from .models import Article, EgeTask

    published = Prefetch(
        'articles',
        queryset=Article.objects.filter(track='ege', is_published=True),
        to_attr='published_articles',
    )
    return [
        {'task': task, 'articles': task.published_articles}
        for task in EgeTask.objects.prefetch_related(published)
        if task.published_articles
    ]
