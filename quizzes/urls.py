from django.urls import path
from .views import (
    quiz_detail_view,
    quiz_stats_view,
    user_attempts_view,
    attempt_detail_view,
    question_file_download_view,
    submit_code_view,
    submission_status_view,
    finish_quiz_view,
    question_hint_view,
    question_check_view,
)

app_name = 'quizzes'

urlpatterns = [
    path('<int:quiz_id>/', quiz_detail_view, name='quiz_detail'),
    path('question-file/<int:file_id>/download/', question_file_download_view, name='question_file_download'),

    # Async code submission API
    path('<int:quiz_id>/question/<int:question_id>/submit/', submit_code_view, name='submit_code'),
    path('submission/<int:submission_id>/status/', submission_status_view, name='submission_status'),
    path('<int:quiz_id>/finish/', finish_quiz_view, name='finish_quiz'),

    # Подсказка к задаче (открывается по правилам, см. textbook.services.hint_state)
    path('question/<int:question_id>/hint/', question_hint_view, name='question_hint'),

    # Проверка одного текстового ответа: вердикт без сохранения, балл ставит finish_quiz_view
    path('question/<int:question_id>/check/', question_check_view, name='question_check'),

    # Статистика
    path('<int:quiz_id>/stats/', quiz_stats_view, name='quiz_stats'),
    path('<int:quiz_id>/stats/<int:user_id>/', user_attempts_view, name='user_attempts'),
    path('attempt/<int:result_id>/', attempt_detail_view, name='attempt_detail'),
]
