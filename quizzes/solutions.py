"""
«Решения других»: кто их видит, как подписан автор, что показать.

Галерея одна на банк ЕГЭ, варианты и практикум учебника – решение живёт у
задачи (Question), откуда бы ученик её ни решал. Сюда же сходятся все, кому
нужно имя автора: галерея, таблица результатов варианта, лайки. Правило
«чьё имя показать этому зрителю» записано один раз – в name_visible(): пока оно
было разнесено по шаблонам, таблица варианта показывала всех поимённо, хотя
ученик просил его не называть.
"""
import hashlib
import hmac

from django.conf import settings
from django.db.models import Count, Exists, OuterRef, Q
from django.utils import timezone

from .models import (
    CodeSubmission, ExamTaskProgress, PracticeItem, SharedSolution, SolutionLike, UserAnswer,
)

SORTS = ('likes', 'cpu', 'memory')
LANGUAGE_LABELS = dict(CodeSubmission.LANGUAGE_CHOICES)


def solved_question_ids(user, question_ids):
    """
    Какие из задач ученик решил верно сам – только они открывают чужие решения.

    «Верно» – полный балл: частичный балл 26/27 и «Показать ответ» (gave_up)
    пишут is_correct=False, чужое решение – награда, а не подсказка. Источников
    четыре, потому что одна задача решается в разных местах: отправка кода,
    ответ теста (практикум, вариант), прогресс варианта, тренировка. Экзамен
    тренажёра проверяет текстовые ответы молча посреди сессии – его ответ
    открывает доступ только после завершения, иначе галерея стала бы подсказкой
    во время экзамена.
    """
    ids = set(question_ids)
    if not ids:
        return set()
    solved = set(CodeSubmission.objects.filter(
        user=user, question_id__in=ids, is_correct=True,
    ).values_list('question_id', flat=True))
    solved |= set(UserAnswer.objects.filter(
        user_result__user=user, question_id__in=ids, is_correct=True,
    ).values_list('question_id', flat=True))
    solved |= set(ExamTaskProgress.objects.filter(
        user=user, question_id__in=ids, is_solved=True,
    ).values_list('question_id', flat=True))
    solved |= set(PracticeItem.objects.filter(
        session__user=user, question_id__in=ids, is_correct=True,
    ).filter(
        Q(session__mode='study') | Q(session__finished_at__isnull=False),
    ).values_list('question_id', flat=True))
    return solved


def can_view(user, question):
    return user.is_superuser or question.id in solved_question_ids(user, [question.id])


def full_name(user):
    return f"{user.last_name} {user.first_name}".strip() or user.username


def _profile(user):
    # RelatedObjectDoesNotExist – наследник AttributeError, getattr его глотает.
    return getattr(user, 'profile', None)


def _group_id(user):
    profile = _profile(user)
    return profile.group_id if profile else None


def visibility(user, override=''):
    """Выбор автора: у решения – если задан, иначе из профиля; без профиля – аноним."""
    if override:
        return override
    profile = _profile(user)
    return profile.solution_name_visibility if profile else 'anon'


def name_visible(author, viewer, mode):
    """
    Видит ли зритель имя автора. Единственное место, где это решается.

    Учитель видит всех: он и так видит всё в статистике, анонимность – от
    одноклассников. «Только классу» без класса у кого-то из двоих – аноним:
    два ученика без группы одноклассниками не являются.
    """
    if viewer.is_superuser or author.pk == viewer.pk:
        return True
    if mode == 'all':
        return True
    if mode == 'class':
        group = _group_id(author)
        return group is not None and group == _group_id(viewer)
    return False


def pseudonyms(scope, user_ids, word='Ученик'):
    """
    {user_id: «Ученик №4821»} – постоянный внутри scope, разный между ними.

    Номер – HMAC от секрета, а не порядковый: «№1» выдал бы, кто решил первым,
    а одинаковый номер в разных задачах собирал бы по ним портрет автора.
    scope – задача ('q15') или вариант ('quiz3').
    """
    # ponytail: коллизии (≈5% на 30 авторов) разводятся сдвигом, и сдвигается
    # тот, у кого id больше, – то есть пришедший позже; старые номера стоят.
    key = settings.SECRET_KEY.encode()
    taken, out = set(), {}
    for uid in sorted(set(user_ids)):
        digest = hmac.new(key, f'{scope}:{uid}'.encode(), hashlib.sha256).digest()
        n = 1000 + int.from_bytes(digest[:4], 'big') % 9000
        while n in taken:
            n = n + 1 if n < 9999 else 1000
        taken.add(n)
        out[uid] = f'{word} №{n}'
    return out


def author_labels(authors, viewer, scope, overrides=None, word='Ученик'):
    """{user_id: (подпись, имя_видно)} для списка авторов – по name_visible()."""
    overrides = overrides or {}
    pseudo = pseudonyms(scope, [a.pk for a in authors], word)
    labels = {}
    for author in authors:
        named = name_visible(author, viewer, visibility(author, overrides.get(author.pk, '')))
        labels[author.pk] = (full_name(author) if named else pseudo[author.pk], named)
    return labels


def _version(code, language, cpu=None, memory=None, pk=None):
    return {'code': code, 'language': language, 'label': LANGUAGE_LABELS.get(language, language),
            'cpu': cpu, 'memory': memory, 'pk': pk}


def _code_by_author(question):
    """
    {user_id: [по языку: последняя верная версия + рекорды по времени и памяти]}.

    Рекорд показывается, только если это другая отправка: переписывая код,
    ученик бывает быстрее, но прожорливее, и лучшее время с лучшей памятью
    тогда живут в разных попытках. Ответы практикума без CodeSubmission
    (синхронная проверка) идут как Python без метрик.
    """
    # ponytail: все верные отправки задачи одним запросом – в школе это десятки
    # строк; при тысячах – Window(RowNumber) по (user, language).
    subs = (CodeSubmission.objects
            .filter(question=question, is_correct=True)
            .only('id', 'user_id', 'code', 'language', 'cpu_time_ms', 'memory_kb', 'created_at')
            .order_by('-created_at'))
    grouped = {}
    for sub in subs:
        grouped.setdefault(sub.user_id, {}).setdefault(sub.language, []).append(sub)

    legacy = (UserAnswer.objects
              .filter(question=question, is_correct=True, submission__isnull=True)
              .exclude(code_answer__isnull=True).exclude(code_answer='')
              .order_by('-user_result__date_completed')
              .values_list('user_result__user_id', 'code_answer'))
    result = {}
    for uid, code in legacy:
        if uid not in grouped and uid not in result:
            result[uid] = [{'latest': _version(code, 'python'), 'fastest': None, 'leanest': None}]

    for uid, by_lang in grouped.items():
        rows = []
        for language in ('python', 'cpp'):
            versions = by_lang.get(language)
            if not versions:
                continue
            latest = versions[0]
            timed = [s for s in versions if s.cpu_time_ms is not None]
            sized = [s for s in versions if s.memory_kb is not None]
            fastest = min(timed, key=lambda s: s.cpu_time_ms) if timed else None
            leanest = min(sized, key=lambda s: s.memory_kb) if sized else None
            as_version = lambda s: _version(s.code, s.language, s.cpu_time_ms, s.memory_kb, s.pk)
            rows.append({
                'latest': as_version(latest),
                'fastest': as_version(fastest) if fastest and fastest.pk != latest.pk else None,
                'leanest': (as_version(leanest)
                            if leanest and leanest.pk not in (latest.pk, getattr(fastest, 'pk', None))
                            else None),
                'best_cpu': fastest.cpu_time_ms if fastest else None,
                'best_memory': leanest.memory_kb if leanest else None,
            })
        result[uid] = rows
    return result


def gallery(question, viewer, sort='likes', language=None):
    """
    Карточки галереи задачи – по одной на автора.

    Автор попадает сюда, если у него есть верный код или разбор. У текстовой
    задачи ответ у всех один и тот же, поэтому там только разборы. Скрытое
    учителем ученик не видит (своё – видит, с пометкой); учитель видит всё.
    Записи SharedSolution создаются здесь же, лениво: лайку нужен id, и id
    записи, в отличие от user_id, автора не выдаёт.
    """
    code = _code_by_author(question) if question.question_type == 'code' else {}
    with_notes = set(
        SharedSolution.objects.filter(question=question)
        .filter(~Q(comment='') | ~Q(file='') & Q(file__isnull=False) | ~Q(image='') & Q(image__isnull=False))
        .values_list('user_id', flat=True)
    )
    author_ids = set(code) | with_notes
    if not author_ids:
        return [], {}

    existing = set(SharedSolution.objects.filter(question=question, user_id__in=author_ids)
                   .values_list('user_id', flat=True))
    SharedSolution.objects.bulk_create(
        [SharedSolution(user_id=uid, question=question) for uid in author_ids - existing],
        ignore_conflicts=True,
    )
    solutions = list(
        SharedSolution.objects.filter(question=question, user_id__in=author_ids)
        .select_related('user__profile')
        .annotate(
            like_count=Count('likes'),
            liked=Exists(SolutionLike.objects.filter(solution=OuterRef('pk'), user=viewer)),
        )
    )
    # Псевдонимы считаются по всем авторам, включая скрытых, – иначе у ученика
    # и у учителя номера разошлись бы на коллизии.
    labels = author_labels([s.user for s in solutions], viewer, f'q{question.id}',
                           overrides={s.user_id: s.name_visibility for s in solutions})
    pseudo = pseudonyms(f'q{question.id}', [s.user_id for s in solutions])

    # Фильтр по языку режет и версии внутри карточки: рекорды на C++ и Python
    # не сравниваются (best_code_metrics), и «быстрые» при выбранном Python
    # должны сортироваться по Python, а не по C++-версии того же автора.
    cards, counts = [], {}
    for solution in solutions:
        is_own = solution.user_id == viewer.pk
        if solution.hidden and not (viewer.is_superuser or is_own):
            continue
        languages = code.get(solution.user_id, [])
        for row in languages:
            counts[row['latest']['language']] = counts.get(row['latest']['language'], 0) + 1
        if language:
            languages = [row for row in languages if row['latest']['language'] == language]
            if not languages:
                continue
        name, named = labels[solution.user_id]
        cpu = [row['best_cpu'] for row in languages if row.get('best_cpu') is not None]
        memory = [row['best_memory'] for row in languages if row.get('best_memory') is not None]
        cards.append({
            'solution': solution,
            'name': name,
            'named': named,
            'pseudonym': pseudo[solution.user_id],  # превью своей карточки: как видят другие
            'is_own': is_own,
            'languages': languages,
            'best_cpu': min(cpu) if cpu else None,
            'best_memory': min(memory) if memory else None,
            'likes': solution.like_count,
            'liked': solution.liked,
            'show_notes': solution.has_notes and (not solution.notes_hidden or viewer.is_superuser or is_own),
        })

    if sort == 'cpu':
        cards.sort(key=lambda c: (c['best_cpu'] is None, c['best_cpu'] or 0))
    elif sort == 'memory':
        cards.sort(key=lambda c: (c['best_memory'] is None, c['best_memory'] or 0))
    else:
        cards.sort(key=lambda c: (-c['likes'], c['best_cpu'] is None, c['best_cpu'] or 0))
    # Своё решение – первым: от него и сравнивают.
    cards.sort(key=lambda c: not c['is_own'])
    return cards, counts


# --- Модерация разборов --------------------------------------------------
#
# Разбор (комментарий, картинка, файл) видят все решившие, поэтому новое
# содержимое сначала смотрит учитель. Одобренная версия – comment/file/image,
# черновик – draft_*. Убрать своё (стереть текст, снять картинку или файл)
# можно сразу: проверять в удалении нечего.


def _drop(field):
    """Стереть файл с диска и обнулить поле. Без этого отклонённые и заменённые
    фото копились бы в media навсегда."""
    if field:
        field.storage.delete(field.name)
    field.name = None


def draft_view(solution):
    """Что ученик прислал (или что у него в форме): черновик поверх одобренного."""
    in_review = solution.review_status in ('pending', 'rejected')
    return {
        'comment': solution.draft_comment if in_review else solution.comment,
        'image': solution.draft_image or solution.image,
        'file': solution.draft_file or solution.file,
    }


def submit_notes(solution, comment, upload=None, image=None, remove_file=False, remove_image=False):
    """
    Ученик сохранил разбор. Возвращает True, если что-то ушло на проверку.

    Удаление применяется сразу – и к одобренному, и к черновику. Новый текст или
    файл – в черновик со статусом «на проверке». Текст, совпавший с одобренным,
    и пустой текст на проверку не идут: первое ничего не меняет, второе – удаление.
    """
    if remove_file:
        _drop(solution.file)
        _drop(solution.draft_file)
    if remove_image:
        _drop(solution.image)
        _drop(solution.draft_image)
    if not comment:
        solution.comment = ''
    if upload:
        _drop(solution.draft_file)
        solution.draft_file = upload
    if image:
        _drop(solution.draft_image)
        solution.draft_image = image

    solution.draft_comment = comment
    changed = (comment and comment != solution.comment) or solution.draft_file or solution.draft_image
    if changed:
        if solution.review_status != 'pending':
            solution.submitted_at = timezone.now()
        solution.review_status = 'pending'
        solution.review_note = ''
    else:
        solution.draft_comment = ''
        if solution.review_status in ('pending', 'rejected'):
            solution.review_status = ''
    solution.save()
    return bool(changed)


def approve_notes(solution, comment, drop_image=False, drop_file=False, note=''):
    """
    Учитель принял черновик – как есть или поправив. Правкой считается и
    изменённый текст, и снятая картинка или файл: автор увидит «принят с
    правками» и слово учителя.
    """
    edited = comment != solution.draft_comment or drop_image or drop_file
    solution.comment = comment
    if solution.draft_image:
        if drop_image:
            _drop(solution.draft_image)
        else:
            _drop(solution.image)
            solution.image = solution.draft_image.name  # имя, не объект: у FieldFile своё поле
            solution.draft_image = None
    elif drop_image:
        _drop(solution.image)
    if solution.draft_file:
        if drop_file:
            _drop(solution.draft_file)
        else:
            _drop(solution.file)
            solution.file = solution.draft_file.name
            solution.draft_file = None
    elif drop_file:
        _drop(solution.file)
    solution.draft_comment = ''
    solution.review_status = 'edited' if edited else 'approved'
    solution.review_note = note
    solution.save()
    verdict = 'опубликован с правками учителя' if edited else 'принят и опубликован'
    _notify_author(solution, f'Ваш разбор к задаче «{solution.question.get_title()}» {verdict}', note, 'accepted')


def reject_notes(solution, note=''):
    """Учитель отклонил: одобренное остаётся, новые файлы стираются, текст –
    у автора в форме, чтобы поправить и отправить снова."""
    _drop(solution.draft_image)
    _drop(solution.draft_file)
    solution.review_status = 'rejected'
    solution.review_note = note
    solution.save()
    _notify_author(solution, f'Учитель отклонил ваш разбор к задаче «{solution.question.get_title()}»', note, 'rejected')


def _notify_author(solution, text, note, status):
    from accounts.models import notify
    from django.urls import reverse

    notify(solution.user, 'solution', f'{text}: «{note}»' if note else text,
           reverse('quizzes:solutions', args=[solution.question_id]), status)
