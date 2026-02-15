from django.urls import path
from . import views

app_name = 'ege'

urlpatterns = [
    path('', views.ege_list_view, name='ege_list'),
    path('<int:quiz_id>/', views.ege_detail_view, name='ege_detail'),
    path('<int:quiz_id>/check/', views.ege_check_answer_view, name='ege_check'),
    path('<int:quiz_id>/finish/', views.ege_finish_view, name='ege_finish'),
    path('<int:quiz_id>/result/', views.ege_result_view, name='ege_result'),
    path('<int:quiz_id>/save-time/', views.ege_save_time_view, name='ege_save_time'),
]
