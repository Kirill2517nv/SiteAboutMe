from django.urls import path

from . import views

app_name = 'spetskurs'

urlpatterns = [
    path('', views.landing_view, name='landing'),
    path('tasks/', views.task_list_view, name='task_list'),
    path('task/<slug:slug>/', views.task_detail_view, name='task_detail'),
    path('basics/', views.basics_view, name='basics'),
]
