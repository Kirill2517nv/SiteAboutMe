from django.urls import path
from .views import ProfileView, join_view, notifications_view

app_name = 'accounts'

urlpatterns = [
    path('profile/', ProfileView.as_view(), name='profile'),
    # Профиль ученика — только для суперпользователя (проверка в ProfileView).
    path('profile/<int:user_id>/', ProfileView.as_view(), name='student_profile'),
    path('notifications/', notifications_view, name='notifications'),
    path('join/', join_view, name='join'),
]
