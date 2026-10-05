from .models import Notification


def notifications_badge(request):
    """Непрочитанные уведомления – число на колокольчике в шапке."""
    user = getattr(request, 'user', None)
    if not (user and user.is_authenticated) or user.is_superuser:
        return {}
    return {'UNREAD_NOTIFICATIONS': Notification.objects.filter(user=user, read_at__isnull=True).count()}
