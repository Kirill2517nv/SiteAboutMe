from django.urls import path
from . import views

app_name = 'spetskurs'

urlpatterns = [
    path('', views.landing_view, name='landing'),
    path('theory/', views.theory_list_view, name='theory_list'),
    path('theory/<slug:slug>/', views.theory_detail_view, name='theory_detail'),
    path('simulations/', views.simulation_list_view, name='simulation_list'),
    path('simulations/<slug:slug>/', views.simulation_detail_view, name='simulation_detail'),
]
