"""Темы проектов второго семестра – /spetskurs/projects/.

Текст – spetskurs/project_topics_data.py (собран из
conference/temy-proektov-2026.md), иллюстрации – spetskurs/seed_media/projects/,
файлы с Wikimedia Commons. Картинки лежат в репозитории и копируются в
хранилище самой командой: так выкатка не зависит от того, успел ли кто-то
перенести media на прод до прогона (на этом уже пропадали картинки учебника).

is_published стоит в create_defaults: повторный прогон обновляет текст, но не
возвращает на сайт тему, которую учитель снял в админке.

Прогон: python manage.py seed_spetskurs_projects
"""
from pathlib import Path

from django.core.files import File
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from spetskurs.models import ProjectImage, ProjectTopic
from spetskurs.project_topics_data import STEPS, TOPICS

MEDIA_DIR = Path(__file__).resolve().parents[2] / 'seed_media' / 'projects'
TEXT_FIELDS = ('number', 'title', 'group', 'difficulty', 'teaser', 'phenomenon',
               'where', 'research', 'result', 'teacher_notes')


class Command(BaseCommand):
    help = 'Темы проектов спецкурса: текст, этапы работы, иллюстрации'

    @transaction.atomic
    def handle(self, *args, **options):
        # Удаление файлов ниже транзакцией не откатывается: упади команда на
        # недостающей картинке посреди прогона – база вернётся, а файлы уже
        # стёрты, и на сайте битые иллюстрации. Поэтому все исходники – до записи.
        missing = [img['file'] for t in TOPICS for img in t['images']
                   if not (MEDIA_DIR / img['file']).is_file()]
        if missing:
            raise CommandError(f'Нет файлов в {MEDIA_DIR}: {", ".join(missing)}')
        images = 0
        for data in TOPICS:
            topic, _ = ProjectTopic.objects.update_or_create(
                slug=data['slug'],
                defaults={**{f: data[f] for f in TEXT_FIELDS}, 'steps': STEPS[data['slug']]},
                create_defaults={**{f: data[f] for f in TEXT_FIELDS},
                                 'steps': STEPS[data['slug']], 'is_published': True},
            )
            # Картинки пересоздаются целиком, а старые файлы удаляются из
            # хранилища: иначе каждый прогон оставлял бы в media копию с
            # суффиксом от storage.
            for old in topic.images.all():
                old.image.delete(save=False)
            topic.images.all().delete()
            for order, img in enumerate(data['images']):
                pi = ProjectImage(topic=topic, order=order, caption=img['caption'],
                                  author=img['author'], license=img['license'],
                                  source_url=img['source_url'])
                with open(MEDIA_DIR / img['file'], 'rb') as fh:
                    pi.image.save(img['file'], File(fh), save=True)
                images += 1
        self.stdout.write(self.style.SUCCESS(
            f'Готово: {len(TOPICS)} тем, {images} иллюстраций'))
