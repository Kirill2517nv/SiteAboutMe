import json
import os
import re
import shutil
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from quizzes.models import Quiz, Question, Choice, TestCase, QuestionImage, QuestionFile

VALID_TYPES = {'choice', 'text', 'code'}
VALID_EGE_NUMBERS = set(range(1, 28))


def generate_slug(quiz_data):
    """Генерирует slug из JSON: явный slug > ID из description > None."""
    if quiz_data.get('slug'):
        return quiz_data['slug']
    desc = quiz_data.get('description', '')
    match = re.search(r'ID:\s*(\d+)', desc)
    if match:
        return f'variant-{match.group(1)}'
    return None


def transform_media_path(old_path, slug, media_type):
    """Трансформирует путь медиа-файла для EGE-варианта.

    media_type: 'images' или 'files'
    """
    if not slug:
        return old_path
    filename = os.path.basename(old_path)
    return f'ege/{slug}/{media_type}/{filename}'


def ensure_media_file(old_path, new_path, media_root):
    """Если файл лежит по старому пути, перемещает в новый."""
    if old_path == new_path:
        return
    old_abs = os.path.join(media_root, old_path)
    new_abs = os.path.join(media_root, new_path)
    if os.path.exists(old_abs) and not os.path.exists(new_abs):
        os.makedirs(os.path.dirname(new_abs), exist_ok=True)
        shutil.move(old_abs, new_abs)


class Command(BaseCommand):
    help = 'Загружает вариант ЕГЭ из JSON-файла (формат fixtures/ege_template.json)'

    def add_arguments(self, parser):
        parser.add_argument('json_file', type=str, help='Путь к JSON-файлу')

    def handle(self, *args, **options):
        json_path = Path(options['json_file'])

        if not json_path.exists():
            raise CommandError(f'Файл не найден: {json_path}')

        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        if 'quiz' not in data or 'questions' not in data:
            raise CommandError('JSON должен содержать ключи "quiz" и "questions"')

        quiz_data = data['quiz']

        if not quiz_data.get('title'):
            raise CommandError('Поле quiz.title обязательно')

        if quiz_data.get('exam_mode') not in ('exam', 'practice'):
            raise CommandError('Поле quiz.exam_mode должно быть "exam" или "practice"')

        questions_data = data['questions']
        if not questions_data:
            raise CommandError('Список вопросов пуст')

        slug = generate_slug(quiz_data)
        if slug and Quiz.objects.filter(slug=slug).exists():
            raise CommandError(
                f'Вариант с slug "{slug}" уже существует. '
                f'Удалите существующий вариант или укажите другой slug в JSON.'
            )
        media_root = settings.MEDIA_ROOT

        with transaction.atomic():
            quiz = Quiz.objects.create(
                title=quiz_data['title'],
                description=quiz_data.get('description', ''),
                max_attempts=quiz_data.get('max_attempts', 0),
                start_date=quiz_data.get('start_date'),
                end_date=quiz_data.get('end_date'),
                quiz_type='exam',
                exam_mode=quiz_data['exam_mode'],
                is_public=quiz_data.get('is_public', True),
                slug=slug,
            )

            if not slug:
                slug = f'ege-{quiz.pk}'
                quiz.slug = slug
                quiz.save(update_fields=['slug'])

            total_points = 0

            for i, q_data in enumerate(questions_data, 1):
                q_type = q_data.get('question_type', 'text')
                if q_type not in VALID_TYPES:
                    raise CommandError(f'Вопрос #{i}: неизвестный тип "{q_type}"')

                ege_number = q_data.get('ege_number')
                if ege_number is not None and ege_number not in VALID_EGE_NUMBERS:
                    raise CommandError(f'Вопрос #{i}: ege_number должен быть от 1 до 27, получено {ege_number}')

                points = q_data.get('points', 1)
                total_points += points

                question = Question.objects.create(
                    quiz=quiz,
                    title=q_data.get('title', ''),
                    text=q_data['text'],
                    question_type=q_type,
                    correct_text_answer=q_data.get('correct_text_answer'),
                    ege_number=ege_number,
                    topic=q_data.get('topic', ''),
                    points=points,
                    alternative_answers=q_data.get('alternative_answers'),
                )

                for j, img_data in enumerate(q_data.get('images', [])):
                    old_path = img_data['image']
                    new_path = transform_media_path(old_path, slug, 'images')
                    ensure_media_file(old_path, new_path, media_root)
                    QuestionImage.objects.create(
                        question=question,
                        image=new_path,
                        alt_text=img_data.get('alt_text', ''),
                        order=img_data.get('order', j),
                    )

                for j, file_data in enumerate(q_data.get('files', [])):
                    old_path = file_data['file']
                    new_path = transform_media_path(old_path, slug, 'files')
                    ensure_media_file(old_path, new_path, media_root)
                    QuestionFile.objects.create(
                        question=question,
                        file=new_path,
                        description=file_data.get('description', ''),
                        order=file_data.get('order', j),
                    )

                if q_type == 'choice':
                    for ch in q_data.get('choices', []):
                        Choice.objects.create(
                            question=question,
                            text=ch['text'],
                            is_correct=ch.get('is_correct', False),
                        )

                elif q_type == 'code':
                    for tc in q_data.get('test_cases', []):
                        TestCase.objects.create(
                            question=question,
                            input_data=tc.get('input_data', ''),
                            output_data=tc['output_data'],
                        )

        self.stdout.write(self.style.SUCCESS(
            f'Вариант ЕГЭ "{quiz.title}" загружен (slug={slug}): '
            f'{quiz.questions.count()} вопросов, {total_points} баллов'
        ))
