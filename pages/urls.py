from django.urls import path

from . import views

app_name = 'pages'

urlpatterns = [
    path('changelog/', views.changelog_view, name='changelog'),
]
