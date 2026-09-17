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
