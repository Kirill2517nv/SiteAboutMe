from .models import SharedSolution


def review_badge(request):
    """Разборы «Решений других» на проверке – бейдж в шапке. Считается только учителю."""
    user = getattr(request, 'user', None)
    if not (user and user.is_superuser):
        return {}
    return {'PENDING_NOTES': SharedSolution.objects.filter(review_status='pending').count()}
