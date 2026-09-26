"""
Карта сайта для поисковиков: только то, что открывается гостю.

Страница за логином в карте – это страница входа в выдаче вместо контента
(так Яндекс и проиндексировал «Вход на сайт»), поэтому статьи берутся тем же
`visible_articles`, который решает, что гостю показать.
"""
from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from quizzes import ege_stats
from spetskurs.models import CourseTask
from textbook.models import EgeTask
from textbook.services import visible_articles


class _Https(Sitemap):
    # За Nginx запрос приходит в Django по http, и без этого карта
    # отдавала бы адреса, которые сразу редиректят.
    protocol = 'https'


class StaticSitemap(_Https):
    def items(self):
        return ['home', 'textbook:home', 'ege:ege_list', 'spetskurs:landing',
                'spetskurs:task_list', 'spetskurs:basics', 'about']

    def location(self, name):
        return reverse(name)


class ArticleSitemap(_Https):
    def items(self):
        return visible_articles(None).order_by('pk')

    def lastmod(self, article):
        return article.updated_at


class EgeTaskSitemap(_Https):
    def items(self):
        # 20 и 21 редиректят на 19 – в карте только сама страница связки.
        linked = ege_stats.linked_numbers()
        return [n for n in EgeTask.objects.order_by('number').values_list('number', flat=True)
                if n not in linked or n == min(linked)]

    def location(self, number):
        return reverse('ege:ege_task', args=[number])


class CourseTaskSitemap(_Https):
    def items(self):
        return CourseTask.objects.filter(is_published=True).order_by('pk')


SITEMAPS = {
    'pages': StaticSitemap,
    'articles': ArticleSitemap,
    'ege': EgeTaskSitemap,
    'spetskurs': CourseTaskSitemap,
}
