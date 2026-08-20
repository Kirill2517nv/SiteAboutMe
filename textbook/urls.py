from django.urls import path

from . import views

app_name = 'textbook'

urlpatterns = [
    path('', views.textbook_home_view, name='home'),
    path('article/<slug:slug>/', views.article_detail_view, name='article_detail'),
    path('article/<slug:slug>/read/', views.mark_article_read_view, name='mark_read'),
    path('article/<slug:slug>/time/', views.track_reading_time_view, name='track_time'),
    path('section/<slug:slug>/stats/', views.section_stats_view, name='section_stats'),
    path('section/<slug:slug>/stats/<int:user_id>/errors/', views.section_stats_errors_view,
         name='section_stats_errors'),
]
