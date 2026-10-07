from django.urls import path
from .views import (
    quiz_detail_view,
    quiz_stats_view,
    user_attempts_view,
    attempt_detail_view,
    question_file_download_view,
    submit_code_view,
    submission_status_view,
    submission_stop_view,
    finish_quiz_view,
    question_hint_view,
    question_check_view,
)
from . import views_similarity, views_solutions

app_name = 'quizzes'

urlpatterns = [
    path('<int:quiz_id>/', quiz_detail_view, name='quiz_detail'),
    path('question-file/<int:file_id>/download/', question_file_download_view, name='question_file_download'),

    # Async code submission API
    path('<int:quiz_id>/question/<int:question_id>/submit/', submit_code_view, name='submit_code'),
    path('submission/<int:submission_id>/status/', submission_status_view, name='submission_status'),
    path('submission/<int:submission_id>/stop/', submission_stop_view, name='submission_stop'),
    path('<int:quiz_id>/finish/', finish_quiz_view, name='finish_quiz'),

    # Подсказка к задаче (открывается по правилам, см. textbook.services.hint_state)
    path('question/<int:question_id>/hint/', question_hint_view, name='question_hint'),

    # Проверка одного текстового ответа: вердикт без сохранения, балл ставит finish_quiz_view
    path('question/<int:question_id>/check/', question_check_view, name='question_check'),

    # «Решения других» – одна галерея для банка ЕГЭ, вариантов и практикума
    path('question/<int:question_id>/solutions/', views_solutions.solutions_view, name='solutions'),
    path('question/<int:question_id>/solutions/mine/', views_solutions.my_solution_view, name='my_solution'),
    path('solution/<int:solution_id>/like/', views_solutions.like_view, name='solution_like'),
    path('solution/<int:solution_id>/moderate/', views_solutions.moderate_view, name='solution_moderate'),
    path('solutions/review/', views_solutions.review_view, name='solutions_review'),
    path('solution/<int:solution_id>/review/', views_solutions.review_decide_view, name='solution_review_decide'),

    # Статистика
    path('<int:quiz_id>/stats/', quiz_stats_view, name='quiz_stats'),
    path('<int:quiz_id>/similar/', views_similarity.quiz_similar_view, name='quiz_similar'),
    path('<int:quiz_id>/stats/<int:user_id>/', user_attempts_view, name='user_attempts'),
    path('attempt/<int:result_id>/', attempt_detail_view, name='attempt_detail'),
]
