import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

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
