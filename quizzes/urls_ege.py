from django.urls import path
from . import views

app_name = 'ege'

urlpatterns = [
    path('', views.ege_list_view, name='ege_list'),
]
