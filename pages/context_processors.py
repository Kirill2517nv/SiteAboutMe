import re
from pathlib import Path
from django.conf import settings


def app_version(request):
    """
    Добавляет текущую версию из CHANGELOG.md в контекст всех шаблонов.

    Берём первый заголовок, который начинается с цифры. По формату Keep a
    Changelog самой верхней секцией стоит «Не выпущено» – накопитель для
    ещё не вышедших правок, – и она тоже заголовок вида `## [...]`.
    Пока условие было просто «первый `## [...]`», в шапке сайта висело
    «vНе выпущено» вместо номера.
    """
    changelog_path = Path(settings.BASE_DIR) / 'CHANGELOG.md'
    version = '0.0.1'
    if changelog_path.exists():
        for line in changelog_path.read_text(encoding='utf-8').splitlines():
            m = re.match(r'^## \[(\d[^\]]*)\]', line)
            if m:
                version = m.group(1)
                break
    return {'APP_VERSION': version}


def yandex_metrika(request):
    """Номер счётчика Метрики для `_yandex_metrika.html` (пусто – счётчика нет)."""
    return {'YANDEX_METRIKA_ID': settings.YANDEX_METRIKA_ID}
