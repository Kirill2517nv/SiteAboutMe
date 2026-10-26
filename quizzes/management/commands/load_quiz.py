import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from quizzes.models import Quiz, Question, Choice, TestCase, QuestionImage, QuestionFile

VALID_TYPES = {'choice', 'text', 'code'}


def _classwork_size(quiz_data):
    """
    «Задач каждому» из JSON – только если ключ вообще есть.

    Пустое или нечисловое значение значит «все задачи»: формат общий с
    load_quiz, и мусор в необязательном поле не должен ронять импорт.
    """
    if 'classwork_size' not in quiz_data:
        return None
    value = str(quiz_data.get('classwork_size') or '').strip()
    if not value.isdigit():
        return None
    number = int(value)
    return number if 1 <= number <= 32767 else None


def _question_extra(q_data):
    """
    Необязательные topic/points задачи, если ключ есть в JSON.

    Отдаём словарём и подмешиваем в create: обычный load_quiz этих ключей не
    пишет, и его задачи создаются ровно как раньше.
    """
    extra = {}
    if 'topic' in q_data:
        extra['topic'] = str(q_data.get('topic') or '').strip()[:200]
    if 'points' in q_data:
        try:
            points = int(q_data.get('points'))
        except (TypeError, ValueError):
            points = 1
        extra['points'] = max(1, points)
    return extra


def load_quiz_from_data(data):
    quiz_data = data["quiz"]
    questions_data = data["questions"]

    with transaction.atomic():
        quiz = Quiz.objects.create(
            title=quiz_data["title"],
            description=quiz_data.get("description", ""),
            max_attempts=quiz_data.get("max_attempts", 3),
            start_date=quiz_data.get("start_date"),
            end_date=quiz_data.get("end_date"),
            # Необязательное поле самостоятельной: сколько задач банка
            # получает каждый ученик. Обычный load_quiz его не пишет.
            classwork_size=_classwork_size(quiz_data),
        )

        for q_data in questions_data:
            q_type = q_data["question_type"]
            if q_type not in VALID_TYPES:
                raise CommandError(f'Неизвестный тип вопроса: "{q_type}"')

            question = Question.objects.create(
                quiz=quiz,
                title=q_data.get("title", ""),
                text=q_data["text"],
                question_type=q_type,
                correct_text_answer=q_data.get("correct_text_answer"),
                **_question_extra(q_data),
            )

            # Изображения
            for i, img_data in enumerate(q_data.get("images", [])):
                QuestionImage.objects.create(
                    question=question,
                    image=img_data["image"],
                    alt_text=img_data.get("alt_text", ""),
                    order=img_data.get("order", i),
                )

            # Файлы
            for i, file_data in enumerate(q_data.get("files", [])):
                QuestionFile.objects.create(
                    question=question,
                    file=file_data["file"],
                    description=file_data.get("description", ""),
                    order=file_data.get("order", i),
                )

            if q_type == "choice":
                for ch in q_data.get("choices", []):
                    Choice.objects.create(
                        question=question,
                        text=ch["text"],
                        is_correct=ch.get("is_correct", False),
                    )

            elif q_type == "code":
                for tc in q_data.get("test_cases", []):
                    TestCase.objects.create(
                        question=question,
                        input_data=tc.get("input_data", ""),
                        output_data=tc["output_data"],
                    )

    return quiz


class Command(BaseCommand):
    help = 'Загружает тест из JSON-файла (формат fixtures/quiz_template.json)'

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

        quiz = load_quiz_from_data(data)

        if quiz:
            self.stdout.write(self.style.SUCCESS(
                f'Тест "{quiz.title}" загружен: '
                f'{quiz.questions.count()} вопросов'
            ))
        else:
            raise CommandError('Не удалось загрузить тест')
