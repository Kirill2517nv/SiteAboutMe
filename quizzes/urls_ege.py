from django.urls import path
from . import views, views_practice

app_name = 'ege'

urlpatterns = [
    path('', views.ege_list_view, name='ege_list'),

    # Тренажёр по темам. Идут раньше '<int:quiz_id>/', чтобы префиксы
    # task/ и practice/ разбирались до попытки прочитать их как id варианта.
    # Таблица класса. Тоже до '<int:quiz_id>/' – 'class' не число, но пусть
    # учительские страницы лежат рядом с остальными префиксами.
    path('class/', views.ege_class_view, name='ege_class'),
    path('student/<int:user_id>/mistakes/', views.ege_student_mistakes_view,
         name='ege_student_mistakes'),
    path('task/<int:number>/', views_practice.ege_task_view, name='ege_task'),
    path('task/<int:number>/classroom/', views_practice.classroom_toggle_view,
         name='ege_classroom_toggle'),
    path('task/<int:number>/solved/', views_practice.ege_solved_view, name='ege_solved'),
    path('task/<int:number>/bank/', views_practice.ege_bank_view, name='ege_bank'),
    path('practice/retry/<int:question_id>/', views_practice.practice_retry_view,
         name='ege_practice_retry'),
    path('practice/start/', views_practice.practice_start_view, name='ege_practice_start'),
    path('practice/<int:pk>/', views_practice.practice_view, name='ege_practice'),
    path('practice/<int:pk>/answer/', views_practice.practice_answer_view, name='ege_practice_answer'),
    path('practice/<int:pk>/reveal/', views_practice.practice_reveal_view, name='ege_practice_reveal'),
    path('practice/<int:pk>/time/', views_practice.practice_time_view, name='ege_practice_time'),
    path('practice/<int:pk>/finish/', views_practice.practice_finish_view, name='ege_practice_finish'),
    path('practice/<int:pk>/result/', views_practice.practice_result_view, name='ege_practice_result'),

    path('<int:quiz_id>/', views.ege_detail_view, name='ege_detail'),
    path('<int:quiz_id>/check/', views.ege_check_answer_view, name='ege_check'),
    path('<int:quiz_id>/finish/', views.ege_finish_view, name='ege_finish'),
    path('<int:quiz_id>/result/', views.ege_result_view, name='ege_result'),
    path('<int:quiz_id>/results/', views.ege_results_view, name='ege_results'),
    path('<int:quiz_id>/save-time/', views.ege_save_time_view, name='ege_save_time'),
    path('<int:quiz_id>/task/<int:ege_number>/upload-attachment/', views.ege_upload_attachment_view, name='ege_upload_attachment'),
    path('<int:quiz_id>/task/<int:ege_number>/solution/<int:user_id>/', views.ege_solution_detail_view, name='ege_user_solution'),
    path('solutions/<int:answer_id>/like/', views.ege_toggle_like_view, name='ege_toggle_like'),
    path('<int:quiz_id>/results/student/<int:user_id>/', views.ege_student_stats_view, name='ege_student_stats'),
]
