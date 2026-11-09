from .models import SharedSolution


def review_badge(request):
    """Разборы «Решений других» на проверке – бейдж в шапке. Считается только учителю."""
    user = getattr(request, 'user', None)
    if not (user and user.is_superuser):
        return {}
    return {'PENDING_NOTES': SharedSolution.objects.filter(review_status='pending').count()}


def mock_exam(request):
    """Окно пробника: вопрос об участии, напоминание и кнопка на вариант."""
    from .mock_exam import mock_context
    return mock_context(getattr(request, 'user', None))
