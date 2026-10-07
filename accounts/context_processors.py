from .models import JoinRequest, Notification


def notifications_badge(request):
    """Непрочитанные уведомления – число на колокольчике в шапке."""
    user = getattr(request, 'user', None)
    if not (user and user.is_authenticated) or user.is_superuser:
        return {}
    return {'UNREAD_NOTIFICATIONS': Notification.objects.filter(user=user, read_at__isnull=True).count()}


def join_badge(request):
    """Заявки по коду класса – бейдж в шапке учителя. Иконки нет, пока заявок нет:
    они бывают в начале года, а место в шапке нужно всегда."""
    user = getattr(request, 'user', None)
    if not (user and user.is_superuser):
        return {}
    return {'PENDING_JOINS': JoinRequest.pending().count()}
