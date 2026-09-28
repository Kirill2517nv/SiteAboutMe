from .models import Suggestion


def feedback_badge(request):
    """Число новых правок для бейджа в шапке. Считается только учителю."""
    user = getattr(request, 'user', None)
    if not (user and user.is_superuser):
        return {}
    return {'NEW_SUGGESTIONS': Suggestion.objects.filter(status='new').count()}
