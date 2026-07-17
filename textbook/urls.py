from django.urls import path

from . import views

app_name = 'textbook'

urlpatterns = [
    path('', views.textbook_home_view, name='home'),
    path('article/<slug:slug>/', views.article_detail_view, name='article_detail'),
    path('article/<slug:slug>/read/', views.mark_article_read_view, name='mark_read'),
]
