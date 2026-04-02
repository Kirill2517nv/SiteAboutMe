import re
from pathlib import Path
from django.conf import settings


def app_version(request):
    """Добавляет текущую версию из CHANGELOG.md в контекст всех шаблонов."""
    changelog_path = Path(settings.BASE_DIR) / 'CHANGELOG.md'
    version = '0.0.1'
    if changelog_path.exists():
        for line in changelog_path.read_text(encoding='utf-8').splitlines():
            m = re.match(r'^## \[(.+?)\]', line)
            if m:
                version = m.group(1)
                break
    return {'APP_VERSION': version}
