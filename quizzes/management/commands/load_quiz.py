import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from quizzes.models import Quiz, Question, Choice, TestCase

VALID_TYPES = {'choice', 'text', 'code'}


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
                data_file=q_data.get("data_file", ""),
                correct_text_answer=q_data.get("correct_text_answer"),
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
