from django.urls import path

from . import views_classwork

app_name = 'classwork'

urlpatterns = [
    path('', views_classwork.list_view, name='list'),
    path('<int:quiz_id>/', views_classwork.intro_view, name='intro'),
    path('<int:quiz_id>/panel/', views_classwork.panel_view, name='panel'),
    path('<int:quiz_id>/rows/', views_classwork.rows_view, name='rows'),
    path('<int:quiz_id>/start/', views_classwork.start_view, name='start'),
    path('<int:quiz_id>/control/', views_classwork.control_view, name='control'),
    path('a/<int:pk>/', views_classwork.work_view, name='work'),
    path('a/<int:pk>/result/', views_classwork.result_view, name='result'),
    path('a/<int:pk>/save/', views_classwork.save_view, name='save'),
    path('a/<int:pk>/event/', views_classwork.event_view, name='event'),
    path('a/<int:pk>/state/', views_classwork.state_view, name='state'),
    path('a/<int:pk>/finish/', views_classwork.finish_view, name='finish'),
    path('a/<int:pk>/score/', views_classwork.score_view, name='score'),
    path('a/<int:pk>/unfreeze/', views_classwork.unfreeze_view, name='unfreeze'),
    path('a/<int:pk>/grade/', views_classwork.grade_view, name='grade'),
]
