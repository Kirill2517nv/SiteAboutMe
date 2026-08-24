"""Прикрепляет к image-блокам статей картинки из папки статьи.

Файлы ищутся по порядковому номеру image-блока внутри статьи:
media/textbook/articles/<slug>/1.webp, 2.webp, ...
Исходники в PNG/JPG конвертируются в WebP на месте – в базу уходит .webp.
"""
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from PIL import Image

from textbook.models import Article

# .webp первым: если он уже есть, конвертировать нечего
SOURCES = ('.webp', '.png', '.jpg', '.jpeg')


class Command(BaseCommand):
    help = 'Привязывает картинки из media/textbook/articles/<slug>/ к image-блокам'

    def add_arguments(self, parser):
        parser.add_argument('--block', type=int, help='Только этот блок учебника')
        parser.add_argument('--quality', type=int, default=90,
                            help='Качество WebP при конвертации (по умолчанию 90)')

    def handle(self, *args, **options):
        articles = Article.objects.all()
        if options['block']:
            articles = articles.filter(section__slug=f'blok-{options["block"]}')

        attached = converted = missing = 0
        for article in articles.order_by('section__order', 'order'):
            blocks = list(article.blocks.filter(block_type='image').order_by('order'))
            folder = Path(settings.MEDIA_ROOT) / 'textbook' / 'articles' / article.slug
            for number, block in enumerate(blocks, 1):
                source = next(
                    (folder / f'{number}{ext}' for ext in SOURCES
                     if (folder / f'{number}{ext}').exists()), None)
                if source is None:
                    missing += 1
                    self.stderr.write(f'нет файла: {article.slug}/{number}.*')
                    continue

                webp = folder / f'{number}.webp'
                if source != webp:
                    with Image.open(source) as img:
                        img.save(webp, 'WEBP', quality=options['quality'], method=6)
                    converted += 1
                    self.stdout.write(
                        f'{article.slug}/{webp.name}: '
                        f'{source.stat().st_size // 1024} КБ -> {webp.stat().st_size // 1024} КБ')

                name = f'textbook/articles/{article.slug}/{webp.name}'
                if block.image.name != name:
                    block.image.name = name
                    block.save(update_fields=['image'])
                    attached += 1

        self.stdout.write(self.style.SUCCESS(
            f'Готово: сконвертировано {converted}, привязано {attached}, '
            f'без файла {missing}.'))
