"""
Пробник ЕГЭ: окно записи и статистика «кто придёт».

Пробник – обычный вариант (`Quiz.exam_mode='exam'`), у которого заполнено
`signup_text`. Окно записи видят только ученики класса-ключа (`signup_group` –
тот, куда вступают по коду «ЕГЭ»); вопрос «Буду / Не смогу» задаётся и им:
в классе-ключе тоже можно заболеть, а счётчик компьютеров считает только
ответивших «Буду».
"""
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils import timezone

from .models import Quiz, UserResult

User = get_user_model()


def _name(user):
    return f"{user.last_name} {user.first_name}".strip() or user.username


def active_mock(user):
    """Пробник для окна или None.

    Окно видят только ученики класса-ключа: пробник для них и объявлен.
    Не показываем тому, кто уже написал вариант или ответил «не смогу», и
    учителю.
    """
    if not user.is_authenticated or user.is_superuser:
        return None
    group_id = getattr(getattr(user, 'profile', None), 'group_id', None)
    if not group_id:
        return None
    now = timezone.now()
    quizzes = (Quiz.objects.filter(quiz_type='exam', is_public=True, signup_text__gt='',
                                   signup_group_id=group_id)
               .filter(Q(end_date__isnull=True) | Q(end_date__gt=now))
               .order_by('start_date', 'id'))
    for quiz in quizzes:
        if UserResult.objects.filter(user=user, quiz=quiz).exists():
            continue
        signup = quiz.signups.filter(user=user).first()
        if signup and signup.answer == 'no':
            continue
        return quiz
    return None


def mock_context(user):
    """Данные модалки для контекст-процессора."""
    if user is None:
        return {}
    quiz = active_mock(user)
    if quiz is None:
        return {}
    signup = quiz.signups.filter(user=user).first()
    return {'MOCK_EXAM': {
        'quiz': quiz,
        'answer': signup.answer if signup else '',
        'is_open': quiz.window_open(user),
        'opens_at': quiz.start_date,
    }}


def admin_data(quiz):
    """Таблица «кто придёт» и три счётчика: будут / не ответили / не будут.

    «Будут» – только ответ «буду»: не ответивший не считается пришедшим, иначе
    обещанное число компьютеров было бы завышено.
    """
    key_group = quiz.signup_group
    rows = {}
    if key_group:
        answers = dict(quiz.signups.filter(user__profile__group=key_group)
                       .values_list('user_id', 'answer'))
        members = (User.objects.filter(profile__group=key_group, is_active=True)
                   .select_related('profile')
                   .order_by('last_name', 'first_name', 'username'))
        for user in members:
            rows[user.id] = {'user': user, 'name': _name(user),
                             'class_name': key_group.name,
                             'answer': answers.get(user.id, 'none')}
    for signup in quiz.signups.select_related('user', 'user__profile__group'):
        if signup.user_id in rows:
            continue
        group = getattr(getattr(signup.user, 'profile', None), 'group', None)
        rows[signup.user_id] = {'user': signup.user, 'name': _name(signup.user),
                                'class_name': group.name if group else '–',
                                'answer': signup.answer}
    items = sorted(rows.values(),
                   key=lambda r: (r['class_name'], r['user'].last_name,
                                  r['user'].first_name, r['user'].username))
    will = sum(1 for r in items if r['answer'] == 'yes')
    wont = sum(1 for r in items if r['answer'] == 'no')
    return {'will': will, 'wont': wont, 'pending': len(items) - will - wont, 'rows': items}
