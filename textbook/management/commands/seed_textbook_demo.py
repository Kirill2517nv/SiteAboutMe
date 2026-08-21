"""Идемпотентный посев демо-статьи учебника со всеми типами блоков и самопроверкой."""
from django.core.management.base import BaseCommand
from django.db import transaction

from quizzes.models import Choice, Question, Quiz
from textbook.models import Article, ArticleBlock, ArticleQuiz, Section


class Command(BaseCommand):
    help = "Создаёт демо-блок, статью со всеми типами блоков и тест самопроверки."

    @transaction.atomic
    def handle(self, *args, **options):
        section, _ = Section.objects.get_or_create(
            slug='predstavlenie-chisel',
            defaults={
                'title': 'Блок 5. Представление чисел в памяти',
                'description': 'Как числа хранятся в памяти компьютера.',
                'order': 5,
                'is_published': True,
            },
        )

        article, _ = Article.objects.get_or_create(
            slug='celye-chisla-v-pamyati',
            defaults={
                'track': 'material',
                'section': section,
                'title': 'Целые числа в памяти',
                'description': 'Биты, байты и беззнаковое представление целых чисел.',
                'order': 2,
                'is_published': True,
            },
        )

        # Пересобираем блоки идемпотентно
        article.blocks.all().delete()
        blocks = [
            dict(order=1, block_type='text', title='Зачем это знать',
                 content='Компьютер хранит любое число как набор **битов** – нулей и '
                         'единиц. Один байт – это 8 бит. Разберёмся, как из битов '
                         'складывается привычное десятичное число.\n\n'
                         '- бит – минимальная единица информации;\n'
                         '- байт – 8 бит;\n'
                         '- 8 бит кодируют числа от 0 до 255.'),
            dict(order=2, block_type='formula', title='Информационный вес',
                 content='N = 2^{b}'),
            dict(order=3, block_type='code', title='Проверка на Python', code_language='python',
                 content='value = 42\n'
                         'print(bin(value))   # 0b101010\n'
                         'print(f"{value:08b}")  # 00101010'),
            dict(order=4, block_type='widget', title='Поиграйте с битами',
                 widget_key='bits-viewer', widget_config={'value': 42, 'bits': 8},
                 content=''),
        ]
        for b in blocks:
            ArticleBlock.objects.create(article=article, **b)

        # Тест самопроверки (is_self_check)
        quiz, _ = Quiz.objects.get_or_create(
            slug='self-check-celye-chisla',
            defaults={
                'title': 'Самопроверка: целые числа в памяти',
                'description': 'Короткая проверка по теме.',
                'is_self_check': True,
                'max_attempts': 0,
                'quiz_type': 'standard',
            },
        )
        # гарантируем флаг, даже если тест уже существовал
        if not quiz.is_self_check:
            quiz.is_self_check = True
            quiz.save(update_fields=['is_self_check'])

        if quiz.questions.count() == 0:
            q1 = Question.objects.create(
                quiz=quiz, question_type='choice',
                text='Сколько бит в одном байте?', points=1,
            )
            for txt, correct in [('4', False), ('8', True), ('16', False), ('32', False)]:
                Choice.objects.create(question=q1, text=txt, is_correct=correct)

            Question.objects.create(
                quiz=quiz, question_type='text',
                text='Сколько различных значений кодирует 8 бит?',
                correct_text_answer='256', points=1,
            )

        ArticleQuiz.objects.get_or_create(
            article=article, quiz=quiz,
            defaults={'label': 'Проверь себя', 'order': 1},
        )

        self.stdout.write(self.style.SUCCESS(
            f'Готово. Статья: /textbook/article/{article.slug}/ '
            f'(блоков: {article.blocks.count()}, самопроверок: {article.self_check_quizzes.count()})'
        ))
