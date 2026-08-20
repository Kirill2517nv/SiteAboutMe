from django.urls import path
from .views import ProfileView

app_name = 'accounts'

urlpatterns = [
    path('profile/', ProfileView.as_view(), name='profile'),
    # Профиль ученика — только для суперпользователя (проверка в ProfileView).
    path('profile/<int:user_id>/', ProfileView.as_view(), name='student_profile'),
]
