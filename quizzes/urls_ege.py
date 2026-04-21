from django.urls import path
from . import views

app_name = 'ege'

urlpatterns = [
    path('', views.ege_list_view, name='ege_list'),
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
