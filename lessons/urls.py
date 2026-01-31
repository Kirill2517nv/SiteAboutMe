from django.urls import path
from . import views

app_name = 'lessons'

urlpatterns = [
    path('', views.lesson_list_view, name='lesson_list'),
    path('<int:lesson_id>/', views.lesson_detail_view, name='lesson_detail'),
    path('<int:lesson_id>/file/', views.lesson_file_download_view, name='lesson_file_download'),
    path('api/<int:lesson_id>/save/', views.lesson_save_api, name='lesson_save_api'),
    path('api/<int:lesson_id>/upload-image/', views.lesson_upload_image_api, name='lesson_upload_image_api'),
]
