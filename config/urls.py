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
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from pages.views import home_page_view, about_page_view

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('django.contrib.auth.urls')),
    path('accounts/', include('accounts.urls')),
    path('quizzes/', include('quizzes.urls')),
    path('ege/', include('quizzes.urls_ege')),
    path('pages/', include('pages.urls')),
    path('lessons/', include('lessons.urls')),
    path('', home_page_view, name='home'),
    path('about/', about_page_view, name='about'),
]

if settings.DEBUG:
    import os
    from django.views.static import serve as _static_serve

    def _media_serve(request, path=''):
        """Serve media with directory index.html fallback (dev only)."""
        full = os.path.join(settings.MEDIA_ROOT, path)
        if os.path.isdir(full) and os.path.isfile(os.path.join(full, 'index.html')):
            path = path.rstrip('/') + '/index.html'
        return _static_serve(request, path, document_root=settings.MEDIA_ROOT)

    from django.urls import re_path
    urlpatterns += [re_path(r'^media/(?P<path>.*)$', _media_serve)]
