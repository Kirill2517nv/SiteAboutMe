from django.urls import path
from . import views

app_name = 'lessons'

urlpatterns = [
    path('', views.lesson_list_view, name='lesson_list'),
    path('<int:lesson_id>/', views.lesson_detail_view, name='lesson_detail'),
    path('<int:lesson_id>/file/<int:attachment_id>/', views.lesson_file_download_view, name='lesson_file_download'),
    path('<int:lesson_id>/presentation-pdf/', views.presentation_pdf_download_view, name='presentation_pdf_download'),
]
