from django.urls import path
from .views import (
    quiz_list_view,
    quiz_detail_view,
    quiz_stats_view,
    user_attempts_view,
    attempt_detail_view,
    question_data_file_download_view,
    submit_code_view,
    submission_status_view,
    finish_quiz_view,
    help_request_view,
    help_requests_list_view,
    help_request_review_view,
    help_request_reply_view,
    help_request_resolve_view,
    help_unread_count_view,
    help_my_notifications_view,
)

app_name = 'quizzes'

urlpatterns = [
    path('', quiz_list_view, name='quiz_list'),
    path('<int:quiz_id>/', quiz_detail_view, name='quiz_detail'),
    path('question/<int:question_id>/data-file/', question_data_file_download_view, name='question_data_file_download'),

    # Async code submission API
    path('<int:quiz_id>/question/<int:question_id>/submit/', submit_code_view, name='submit_code'),
    path('submission/<int:submission_id>/status/', submission_status_view, name='submission_status'),
    path('<int:quiz_id>/finish/', finish_quiz_view, name='finish_quiz'),

    # Статистика
    path('<int:quiz_id>/stats/', quiz_stats_view, name='quiz_stats'),
    path('<int:quiz_id>/stats/<int:user_id>/', user_attempts_view, name='user_attempts'),
    path('attempt/<int:result_id>/', attempt_detail_view, name='attempt_detail'),

    # Help Request System
    path('<int:quiz_id>/question/<int:question_id>/help/', help_request_view, name='help_request'),
    path('help-requests/', help_requests_list_view, name='help_requests_list'),
    path('help-requests/unread-count/', help_unread_count_view, name='help_unread_count'),
    path('help-requests/my-notifications/', help_my_notifications_view, name='help_my_notifications'),
    path('help-requests/<int:help_request_id>/', help_request_review_view, name='help_request_review'),
    path('help-requests/<int:help_request_id>/reply/', help_request_reply_view, name='help_request_reply'),
    path('help-requests/<int:help_request_id>/resolve/', help_request_resolve_view, name='help_request_resolve'),
]
