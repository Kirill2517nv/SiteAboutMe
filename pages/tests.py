import re
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings

from .context_processors import app_version


class AppVersionTests(SimpleTestCase):
    """
    Версия в шапке – номер релиза, а не название секции CHANGELOG.

    Первой секцией по формату Keep a Changelog стоит «Не выпущено», и она
    такой же заголовок `## [...]`, как и релиз. Пока парсер брал просто
    первый заголовок, в шапке сайта висело «vНе выпущено».
    """

    def test_version_is_a_number(self):
        version = app_version(None)['APP_VERSION']
        self.assertRegex(version, r'^\d+\.\d+\.\d+$')

    def test_matches_first_release_in_changelog(self):
        path = Path(settings.BASE_DIR) / 'CHANGELOG.md'
        releases = re.findall(r'^## \[(\d[^\]]*)\]', path.read_text(encoding='utf-8'),
                              re.MULTILINE)
        self.assertEqual(app_version(None)['APP_VERSION'], releases[0])


class YandexMetrikaTests(TestCase):
    """Счётчик выводится только с номером из .env и метит визит ролью, а не пользователем."""

    url = '/pages/changelog/'

    def test_no_counter_without_id(self):
        with self.settings(YANDEX_METRIKA_ID=''):
            self.assertNotContains(self.client.get(self.url), 'mc.yandex.ru')

    @override_settings(YANDEX_METRIKA_ID='12345')
    def test_roles(self):
        User = get_user_model()
        self.assertContains(self.client.get(self.url), 'auth: "guest"')

        student = User.objects.create_user('student', password='x')
        self.client.force_login(student)
        response = self.client.get(self.url)
        self.assertContains(response, 'auth: "user"')
        self.assertContains(response, 'ym(12345, "init"')
        self.assertNotContains(response, f'"{student.pk}"')

        # У учителя в заголовках страниц имена учеников – счётчика нет вовсе.
        self.client.force_login(User.objects.create_superuser('boss', password='x'))
        self.assertNotContains(self.client.get(self.url), 'mc.yandex.ru')


class SearchEngineFilesTests(TestCase):
    """
    Что видит поисковый робот: корневые robots.txt / favicon.ico и карта сайта.

    Первые два лежат в `public/` и отдаются WhiteNoise из корня домена –
    робот иконок Яндекса идёт за /favicon.ico, не читая <head>. В карте –
    только то, что открывается гостю: страница за логином попала бы в выдачу
    как «Вход на сайт».
    """

    def test_root_files_served(self):
        robots = self.client.get('/robots.txt')
        self.assertEqual(robots.status_code, 200)
        self.assertIn(b'Sitemap: https://kirill-lab.ru/sitemap.xml', b''.join(robots.streaming_content))
        self.assertEqual(self.client.get('/favicon.ico').status_code, 200)

    def test_sitemap_lists_published_articles_only(self):
        from textbook.models import Article, Section

        shown = Section.objects.create(title='Блок', slug='b-open', order=1, is_published=True)
        hidden = Section.objects.create(title='Скрыт', slug='b-hidden', order=2, is_published=False)
        Article.objects.create(track='material', section=shown, slug='open-art', title='Открыта',
                               is_published=True)
        Article.objects.create(track='material', section=shown, slug='draft-art', title='Черновик')
        Article.objects.create(track='material', section=hidden, slug='hidden-art', title='В скрытом',
                               is_published=True)

        body = self.client.get('/sitemap.xml').content.decode()
        self.assertIn('https://testserver/textbook/article/open-art/', body)
        self.assertNotIn('draft-art', body)
        self.assertNotIn('hidden-art', body)
