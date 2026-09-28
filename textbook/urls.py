from django.urls import path

from . import views, views_feedback

app_name = 'textbook'

urlpatterns = [
    path('article/<slug:slug>/rate/', views_feedback.article_rate_view, name='article_rate'),
    path('block/<int:pk>/suggest/', views_feedback.block_suggest_view, name='block_suggest'),
    path('block/<int:pk>/preview/', views_feedback.block_preview_view, name='block_preview'),
    path('feedback/', views_feedback.feedback_view, name='feedback'),
    path('suggestions/', views_feedback.my_suggestions_view, name='suggestions'),
    path('feedback/<int:pk>/', views_feedback.suggestion_update_view, name='suggestion_update'),
    path('', views.textbook_home_view, name='home'),
    path('article/<slug:slug>/', views.article_detail_view, name='article_detail'),
    path('article/<slug:slug>/read/', views.mark_article_read_view, name='mark_read'),
    path('article/<slug:slug>/time/', views.track_reading_time_view, name='track_time'),
    path('block/<int:pk>/visibility/', views.block_visibility_toggle_view,
         name='block_visibility_toggle'),
    path('section/<slug:slug>/stats/', views.section_stats_view, name='section_stats'),
    path('section/<slug:slug>/stats/<int:user_id>/errors/', views.section_stats_errors_view,
         name='section_stats_errors'),
]
