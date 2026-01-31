from django.urls import path
from . import views

app_name = 'pages'

urlpatterns = [
    path('api/content/save/', views.content_save_api, name='content_save_api'),
    path('api/content/upload-image/', views.content_upload_image_api, name='content_upload_image_api'),
]
