"""
Докачивает картинки, которые внешний парсер потерял при импорте с kompege.ru.

Парсер теряет два вида картинок: встроенные `data:image/...;base64` (выбрасывает
вместе с местом в тексте) и лежащие на чужом хосте (маркер `[img:N]` ставит, а
файл не скачивает). У задания 12 так пропадала программа машины Тьюринга –
единственное, без чего задачу не решить.

Перезалив исправленного JSON не помогает: `load_ege` не трогает вложения
задачи, по которой уже есть ответы учеников. Поэтому команда дописывает
картинки в существующие вопросы, а потерянный маркер ставит сразу после фразы,
которая в оригинале стоит перед картинкой.

    python manage.py kompege_images 12 --dry-run
    python manage.py kompege_images 12
"""
import base64
import html
import re

import requests
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand
from django.db import transaction

from quizzes.models import Question, QuestionImage

API = 'https://kompege.ru/api/v1/task/{}'
IMG_RE = re.compile(r'<img[^>]*\bsrc="([^"]+)"', re.I)
MARKER_RE = re.compile(r'\[img:(\d+)\]')
EXT = {'image/gif': 'gif', 'image/png': 'png', 'image/jpeg': 'jpg', 'image/svg+xml': 'svg'}


def plain(fragment):
    """HTML → текст, как его видит парсер: теги долой, nbsp = пробел."""
    text = re.sub(r'<br\s*/?>|</p>', '\n', fragment, flags=re.I)
    return html.unescape(re.sub(r'<[^>]+>', '', text)).replace('\xa0', ' ')


def download(src):
    """(байты, расширение) картинки из data-URI или по ссылке."""
    if src.startswith('data:'):
        head, data = src.split(',', 1)
        mime = head[5:].split(';')[0]
        return base64.b64decode(data), EXT.get(mime, 'png')
    resp = requests.get(src, timeout=20)
    resp.raise_for_status()
    ext = src.rsplit('.', 1)[-1].lower()
    return resp.content, ext if ext in EXT.values() else 'png'


class Command(BaseCommand):
    help = 'Докачать картинки задач kompege.ru, потерянные парсером'

    def add_arguments(self, parser):
        parser.add_argument('ege_number', type=int)
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, ege_number, dry_run, **opts):
        qs = (Question.objects.filter(ege_number=ege_number, external_id__startswith='kompege-')
              .select_related('quiz').prefetch_related('images').order_by('id'))
        fixed = 0
        for q in qs:
            task_id = q.external_id.rsplit('-', 1)[-1]
            source = requests.get(API.format(task_id), timeout=20).json()['text']
            srcs = [(m.start(), m.group(1)) for m in IMG_RE.finditer(source)]
            have = len(q.images.all())
            if len(srcs) <= have:
                continue

            text = q.text
            markers = MARKER_RE.findall(text)
            if not markers:
                # Маркеров нет совсем – ставим каждый после фразы, которая в
                # оригинале стоит прямо перед картинкой.
                for k, (pos, _) in reversed(list(enumerate(srcs, 1))):
                    before = plain(source[:pos]).rstrip()
                    anchor = before.splitlines()[-1].strip()[-40:] if before else ''
                    at = text.replace('\xa0', ' ').rfind(anchor) if anchor else -1
                    if at < 0:
                        self.stderr.write(f'#{q.id} {q.external_id}: не нашёл, куда поставить [img:{k}] '
                                          f'(перед картинкой в оригинале: «{anchor}»)')
                        break
                    at += len(anchor)
                    text = f'{text[:at].rstrip()}\n\n[img:{k}]\n\n{text[at:].lstrip()}'
                else:
                    markers = [str(k) for k in range(1, len(srcs) + 1)]
                if not markers:
                    continue

            self.stdout.write(f'#{q.id} {q.external_id}: картинок {have} → {len(srcs)}'
                              f'{", маркеры расставлены" if text != q.text else ""}')
            fixed += 1
            if dry_run:
                continue
            with transaction.atomic():
                for k, (_, src) in enumerate(srcs[have:], have + 1):
                    data, ext = download(src)
                    # Туда же и под тем же именем, что кладёт load_ege: upload_to
                    # банка увёл бы файл в общий question_images/.
                    slug = q.quiz.slug or f'bank-{ege_number}'
                    name = default_storage.save(
                        f'ege/{slug}/images/{slug}_{task_id}_{ege_number}_{k}.{ext}', ContentFile(data))
                    QuestionImage.objects.create(question=q, image=name, order=k - 1)
                if text != q.text:
                    q.text = text
                    q.save(update_fields=['text'])
        self.stdout.write(self.style.SUCCESS(
            f'{"Нашёл" if dry_run else "Исправлено"}: {fixed} из {qs.count()}'))
