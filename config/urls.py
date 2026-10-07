"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth.views import LoginView
from accounts.views import AlumniView, LoginForm
from pages.sitemaps import SITEMAPS
from pages.views import home_page_view, about_page_view

urlpatterns = [
    path('admin/', admin.site.urls),
    # Вход со своей формой – раньше стандартных урлов, имя 'login' то же
    path('accounts/login/', LoginView.as_view(authentication_form=LoginForm), name='login'),
    path('accounts/', include('django.contrib.auth.urls')),
    path('accounts/', include('accounts.urls')),
    path('quizzes/', include('quizzes.urls')),
    path('ege/', include('quizzes.urls_ege')),
    path('pages/', include('pages.urls')),
    path('spetskurs/', include('spetskurs.urls')),
    path('games/', include('games.urls')),
    path('textbook/', include('textbook.urls')),
    path('', home_page_view, name='home'),
    path('about/', about_page_view, name='about'),
    path('alumni/', AlumniView.as_view(), name='alumni'),
    path('sitemap.xml', sitemap, {'sitemaps': SITEMAPS}, name='sitemap'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
