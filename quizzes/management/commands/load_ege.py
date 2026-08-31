import json
import os
import re
import shutil
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from quizzes.ege_constants import EGE_CODE_TASKS
from quizzes.ege_scoring import normalize_output, outputs_match
from quizzes.models import (
    Quiz, Question, Choice, TestCase, QuestionImage, QuestionFile,
    UserAnswer, PracticeItem, CodeSubmission,
)

VALID_TYPES = {'choice', 'text', 'code'}
VALID_EGE_NUMBERS = set(range(1, 28))
VALID_DIFFICULTY = {1, 2, 3}
VALID_QUIZ_TYPES = {'exam', 'bank'}

# Парсер иногда теряет содержимое нижнего индекса: из «a₀» выходит «a0[sub:]»
# – цифра осталась в строке, маркер пустой. Пустой [sub:] фильтр не ловит
# (SUB_MARKER_RE требует непустое содержимое), и в задании 12 вся таблица МТ
# читалась как «q0[sub:]». Чинится однозначно: цифры перед пустым маркером и
# есть его содержимое.
EMPTY_SUB_RE = re.compile(r'([^\W\d_])(\d+)\[sub:\]')


def fix_empty_sub_markers(text):
    """«q0[sub:]» → «q[sub:0]». Возвращает текст без пустых маркеров индекса."""
    return EMPTY_SUB_RE.sub(r'\1[sub:\2]', text or '')


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


def _create_test_cases(question, q_data):
    """
    Тестовые примеры задачи на код: чем проверяется вывод программы.

    Дубли отсеиваются. Парсер кладёт в задания 17 и 26 два кейса на один и тот
    же вход – «2508 104796» и те же числа в столбик, – а раскладка чисел это
    ровно то, что outputs_match и так не проверяет. Второй кейс не проверяет
    ничего нового, зато на каждой отправке поднимает второй контейнер и гоняет
    решение по файлу данных ещё раз. Кейс с другим эталоном остаётся: одинаковым
    считается только то, что таким сочла бы сама проверка.
    """
    kept = []
    for tc in q_data.get('test_cases', []):
        input_data = tc.get('input_data', '')
        output_data = tc['output_data']
        if any(normalize_output(k.input_data) == normalize_output(input_data)
               and outputs_match(output_data, k.output_data) for k in kept):
            continue
        kept.append(TestCase.objects.create(
            question=question,
            input_data=input_data,
            output_data=output_data,
        ))


def question_is_used(question):
    """
    Есть ли по задаче следы работы учеников.

    Пересоздавать варианты ответа у такой задачи нельзя: UserAnswer.selected_choice
    висит на Choice каскадом, и удаление вариантов унесло бы ответы учеников вместе
    с ними. Тексты у такой задачи обновляем на месте, вложения не трогаем.
    """
    return (
        UserAnswer.objects.filter(question=question).exists()
        or PracticeItem.objects.filter(question=question).exists()
        or CodeSubmission.objects.filter(question=question).exists()
    )


class Command(BaseCommand):
    help = (
        'Загружает вариант ЕГЭ или банк задач из JSON-файла '
        '(формат fixtures/ege_template.json)'
    )

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

        quiz_type = quiz_data.get('quiz_type', 'exam')
        if quiz_type not in VALID_QUIZ_TYPES:
            raise CommandError(
                f'Поле quiz.quiz_type должно быть "exam" или "bank", получено "{quiz_type}"'
            )

        is_bank = quiz_type == 'bank'

        # У банка нет режима прохождения: его никто не решает целиком.
        if not is_bank and quiz_data.get('exam_mode') not in ('exam', 'practice'):
            raise CommandError('Поле quiz.exam_mode должно быть "exam" или "practice"')

        questions_data = data['questions']
        if not questions_data:
            raise CommandError('Список вопросов пуст')

        slug = generate_slug(quiz_data)

        # Банк пополняется повторными импортами, поэтому его slug должен быть
        # стабильным и заданным явно. Без него каждый запуск плодил бы новый банк.
        if is_bank and not slug:
            raise CommandError('Для банка задач обязателен явный quiz.slug – по нему идёт пополнение')

        existing = Quiz.objects.filter(slug=slug).first() if slug else None
        if existing and not (is_bank and existing.quiz_type == 'bank'):
            raise CommandError(
                f'Вариант с slug "{slug}" уже существует. '
                f'Удалите существующий вариант или укажите другой slug в JSON.'
            )

        media_root = settings.MEDIA_ROOT
        stats = {'created': 0, 'updated': 0, 'locked': 0}

        with transaction.atomic():
            if existing:
                quiz = existing
                quiz.title = quiz_data['title']
                quiz.description = quiz_data.get('description', quiz.description)
                quiz.save(update_fields=['title', 'description'])
            else:
                quiz = Quiz.objects.create(
                    title=quiz_data['title'],
                    description=quiz_data.get('description', ''),
                    max_attempts=quiz_data.get('max_attempts', 0),
                    start_date=quiz_data.get('start_date'),
                    end_date=quiz_data.get('end_date'),
                    quiz_type=quiz_type,
                    # Банк помечается публичной тренировкой намеренно: так задачи
                    # проходят проверку доступа в submit_code_view без назначения
                    # на группу и допускают переотправку кода. В список вариантов
                    # он всё равно не попадёт – там фильтр по quiz_type='exam'.
                    exam_mode='practice' if is_bank else quiz_data['exam_mode'],
                    is_public=True if is_bank else quiz_data.get('is_public', True),
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

                # Предупреждение, а не ошибка: банк с проверкой кода там, где на
                # экзамене вводится число, импортируется молча и всплывает уже у
                # ученика – он видит редактор кода вместо поля ответа.
                if q_type == 'code' and ege_number not in EGE_CODE_TASKS:
                    self.stdout.write(self.style.WARNING(
                        f'Вопрос #{i}: тип "code" на задании {ege_number}. '
                        f'Программу пишут только в заданиях '
                        f'{", ".join(str(n) for n in sorted(EGE_CODE_TASKS))} – '
                        f'проверьте, не должен ли это быть "text".'
                    ))

                difficulty = q_data.get('difficulty', 1)
                if difficulty not in VALID_DIFFICULTY:
                    raise CommandError(
                        f'Вопрос #{i}: difficulty должен быть 1, 2 или 3, получено {difficulty}'
                    )

                external_id = str(q_data.get('external_id', '') or '')
                points = q_data.get('points', 1)
                total_points += points

                fields = dict(
                    title=q_data.get('title', ''),
                    text=fix_empty_sub_markers(q_data['text']),
                    question_type=q_type,
                    correct_text_answer=q_data.get('correct_text_answer'),
                    ege_number=ege_number,
                    topic=q_data.get('topic', ''),
                    points=points,
                    alternative_answers=q_data.get('alternative_answers'),
                    difficulty=difficulty,
                    external_id=external_id,
                    source_url=q_data.get('source_url', ''),
                    # Связка: задачи с общим group_id выдаются только вместе.
                    # Потеряв эти поля, банк 19–21 рассыпался бы на 90 задач,
                    # и 20-е выдавалось бы со ссылкой на игру, которой ученик
                    # не видел.
                    group_id=str(q_data.get('group_id', '') or ''),
                    group_order=q_data.get('group_order', 0) or 0,
                )

                # Дедупликация идёт по всем задачам ЕГЭ, а не только по этому квизу:
                # одна и та же задача с kompege может прийти и в составе варианта,
                # и в тематической подборке. Второй раз её заводить незачем.
                found = None
                if external_id:
                    found = Question.objects.filter(
                        external_id=external_id,
                        quiz__quiz_type__in=('exam', 'bank'),
                    ).first()

                if found:
                    for key, value in fields.items():
                        setattr(found, key, value)
                    found.save(update_fields=list(fields))
                    question = found
                    if question_is_used(question):
                        # Вложения и варианты ответа оставляем как есть – по ним
                        # уже висят ответы учеников. Тесты – исключение: на
                        # TestCase не ссылается ничего из их работ (CodeSubmission
                        # знает задачу, а не тест), зато без тестов задача на код
                        # становится непроверяемой. Так текстовый банк можно
                        # перевести в код перезаливом.
                        stats['locked'] += 1
                        if q_type == 'code':
                            question.test_cases.all().delete()
                            _create_test_cases(question, q_data)
                        continue
                    stats['updated'] += 1
                    question.images.all().delete()
                    question.files.all().delete()
                    question.choices.all().delete()
                    question.test_cases.all().delete()
                else:
                    question = Question.objects.create(quiz=quiz, **fields)
                    stats['created'] += 1

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
                    _create_test_cases(question, q_data)

        label = 'Банк задач' if is_bank else 'Вариант ЕГЭ'
        summary = f'создано {stats["created"]}, обновлено {stats["updated"]}'
        if stats['locked']:
            summary += f', {stats["locked"]} обновлено без вложений (есть ответы учеников)'

        self.stdout.write(self.style.SUCCESS(
            f'{label} "{quiz.title}" загружен (slug={slug}): {summary}. '
            f'Всего в квизе {quiz.questions.count()} задач, {total_points} баллов в файле'
        ))
