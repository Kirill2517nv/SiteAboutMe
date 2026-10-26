"""Идемпотентный посев первой самостоятельной работы блока 6.

Работа «Побитовые операции» – банк из 20 задач: четыре темы по пять задач,
в каждой теме три задачи с ответом и две с кодом. Каждому ученику работа
выдаёт 6 задач из банка по темам (quizzes.classwork.pick), поэтому заголовки
не нумеруются: у соседей своя нумерация и свой порядок задач.

Ответы текстовых задач считаются выражением прямо здесь, эталоны кода
прогоняются на тестах: output_data руками не пишется, а берётся из вывода
эталонной программы. Пример ввода/вывода в условии собирается из первого
теста тем же прогоном.
"""
import contextlib
import io
import sys

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from quizzes import classwork
from quizzes.models import Question, Quiz, TestCase
from textbook.models import Section

SLUG = 'classwork-blok-6'
SECTION_SLUG = 'blok-6'
TOPICS = ('AND, OR, XOR, NOT', 'Сдвиги', 'Маски', 'Быстрые вычисления')

# Эталоны задач с кодом. По ним же считаются ожидаемые выводы тестов: если
# эталон и тест разойдутся, разойдётся и прогон сида, а не страница ученика.
CODE = {
    'Общие флаги': (
        'n = int(input())\n'
        'total = int(input())\n'
        'i = 1\n'
        'while i < n:\n'
        '    total = total & int(input())\n'
        '    i += 1\n'
        'print(total)'
    ),
    'Флаги не у всех': (
        'n = int(input())\n'
        'value = int(input())\n'
        'and_all = value\n'
        'or_all = value\n'
        'i = 1\n'
        'while i < n:\n'
        '    value = int(input())\n'
        '    and_all = and_all & value\n'
        '    or_all = or_all | value\n'
        '    i += 1\n'
        'print(or_all & ~and_all)'
    ),
    'Деление с округлением вверх': (
        'n = int(input())\n'
        'k = int(input())\n'
        'print((n + (1 << k) - 1) >> k)'
    ),
    'Циклический сдвиг байта': (
        'x = int(input())\n'
        'k = int(input())\n'
        'print(((x << k) | (x >> (8 - k))) & 255)'
    ),
    'Вырезать поле': (
        'x = int(input())\n'
        'i = int(input())\n'
        'j = int(input())\n'
        'print((x >> i) & ((1 << (j - i + 1)) - 1))'
    ),
    'Записать по маске': (
        'x = int(input())\n'
        'm = int(input())\n'
        'v = int(input())\n'
        'print((x & ~m) | (v & m))'
    ),
    'Степень двойки сверху': (
        'n = int(input())\n'
        'p = 1\n'
        'while p < n:\n'
        '    p = p << 1\n'
        'print(p)'
    ),
    'Разложение по степеням двойки': (
        'n = int(input())\n'
        'k = 0\n'
        'while n:\n'
        '    if n & 1:\n'
        '        print(k)\n'
        '    n >>= 1\n'
        '    k += 1'
    ),
}


def _run(code, stdin):
    """Вывод эталона на данном входе – без хвостового перевода строки."""
    old_stdin = sys.stdin
    buffer = io.StringIO()
    sys.stdin = io.StringIO(stdin)
    try:
        with contextlib.redirect_stdout(buffer):
            exec(code, {})
    finally:
        sys.stdin = old_stdin
    return buffer.getvalue().rstrip('\n')


def _code_text(lead, input_line, output_line, stdin, stdout):
    """Условие задачи с кодом: Markdown, пример из первого теста."""
    example_input = stdin.rstrip('\n')
    return (
        f'{lead}\n'
        '\n'
        f'**Ввод:** {input_line}\n'
        f'**Вывод:** {output_line}\n'
        '\n'
        '###### Пример ввода\n'
        '\n'
        '```text\n'
        f'{example_input}\n'
        '```\n'
        '\n'
        '###### Пример вывода\n'
        '\n'
        '```text\n'
        f'{stdout}\n'
        '```\n'
        '\n'
        'Помните: `input()` без текста-подсказки, ничего кроме ответа '
        'программа печатать не должна.'
    )


def _text(title, text, answer):
    return {
        'title': title,
        'question_type': 'text',
        'points': 1,
        'text': text,
        'correct_text_answer': str(answer),
    }


def _code(title, lead, input_line, output_line, inputs):
    code = CODE[title]
    tests = [(stdin, _run(code, stdin)) for stdin in inputs]
    return {
        'title': title,
        'question_type': 'code',
        'points': 2,
        'text': _code_text(lead, input_line, output_line,
                           inputs[0], tests[0][1]),
        'test_cases': tests,
    }


def _bank():
    """20 задач: четыре темы, в каждой три с ответом и две с кодом."""
    return [
        (TOPICS[0], [
            _text(
                'Побитовое И',
                'Чему равно значение выражения `45 & 27` в Python? '
                'Ответ запишите десятичным числом.',
                45 & 27,
            ),
            _text(
                'Исключающее ИЛИ',
                'Вычислите значение выражения `52 ^ 19` в Python. '
                'В ответ запишите одно десятичное число.',
                52 ^ 19,
            ),
            _text(
                'Побитовое НЕ',
                'Чему равно значение выражения `~37` в Python? У целых чисел '
                'в Python нет фиксированной разрядности, поэтому ответ – '
                'обычное целое число, возможно отрицательное. Запишите его '
                'десятичным числом.',
                ~37,
            ),
            _code(
                'Общие флаги',
                'В настройках флаги часто хранят одним числом: каждый разряд – '
                'отдельный флаг. Дано несколько наборов флагов. Выведите '
                'число, в котором единицы стоят ровно там, где они есть во '
                'всех наборах одновременно.',
                'сначала `n` – количество наборов, затем `n` неотрицательных '
                'чисел, каждое на отдельной строке.',
                'одно число – разряды, единичные во всех наборах.',
                ['3\n7\n5\n6\n', '1\n9\n', '2\n8\n7\n', '4\n15\n15\n9\n3\n'],
            ),
            _code(
                'Флаги не у всех',
                'Теперь нужны разряды, где единица есть хотя бы у одного '
                'набора, но не у всех: именно они различают настройки. '
                'Выведите такое число.',
                'сначала `n` – количество наборов, затем `n` чисел, каждое на '
                'отдельной строке.',
                'одно число – разряды, которые есть не у всех.',
                ['3\n7\n5\n6\n', '1\n9\n', '3\n5\n5\n5\n', '4\n1\n2\n4\n8\n'],
            ),
        ]),
        (TOPICS[1], [
            _text(
                'Сдвиг влево',
                'Чему равно значение выражения `13 << 3` в Python? '
                'Ответ запишите десятичным числом.',
                13 << 3,
            ),
            _text(
                'Сдвиг вправо',
                'Вычислите `200 >> 3` в Python и запишите результат '
                'десятичным числом.',
                200 >> 3,
            ),
            _text(
                'Единицы подряд',
                'Чему равно значение выражения `(1 << 10) - 1` в Python? '
                'Ответ запишите десятичным числом.',
                (1 << 10) - 1,
            ),
            _code(
                'Деление с округлением вверх',
                'Сдвиг вправо отбрасывает остаток, поэтому деление сдвигом '
                'округляет вниз. Напишите программу, которая делит `n` на '
                '$2^k$ с округлением вверх, не используя `/`, `//`, `*` и '
                '`%`: обойдитесь сдвигами и сложением.',
                'два целых числа, каждое на отдельной строке: `n` и `k` '
                '(`n >= 0`, `k >= 0`).',
                'одно число – частное, округлённое вверх.',
                ['10\n2\n', '0\n5\n', '7\n0\n', '16\n2\n'],
            ),
            _code(
                'Циклический сдвиг байта',
                'При обычном сдвиге биты, ушедшие за край, теряются. '
                'Циклический сдвиг возвращает их с другой стороны. Сдвиньте '
                'восьмибитное число `x` влево на `k`, считая разрядность '
                'ровно восемь: вытолкнутые слева биты должны появиться '
                'справа.',
                'два целых числа, каждое на отдельной строке: `x` '
                '(`0 <= x <= 255`) и `k` (`0 <= k <= 7`).',
                'одно число – результат циклического сдвига.',
                ['128\n1\n', '255\n3\n', '1\n0\n', '13\n4\n'],
            ),
        ]),
        (TOPICS[2], [
            _text(
                'Маска разрядов',
                'Какое десятичное число – маска, в которой единицы стоят '
                'ровно в разрядах 2, 3 и 4 (нумерация с нуля от младшего)? '
                'Ответ запишите десятичным числом.',
                ((1 << 3) - 1) << 2,
            ),
            _text(
                'Младшие четыре бита',
                'Чему равно значение выражения `181 & 0b1111` в Python? '
                'Ответ запишите десятичным числом.',
                181 & 0b1111,
            ),
            _text(
                'Выключить бит',
                'Чему равно значение выражения `100 & ~(1 << 2)` в Python? '
                'Запишите ответ десятичным числом.',
                100 & ~(1 << 2),
            ),
            _code(
                'Вырезать поле',
                'Из числа часто нужно достать не все биты, а несколько '
                'подряд. Выведите число, составленное из битов `x` с `i`-го '
                'по `j`-й включительно: бит `i` становится младшим разрядом '
                'ответа.',
                'три целых числа, каждое на отдельной строке: `x`, `i` и `j` '
                '(`0 <= i <= j`).',
                'одно число – вырезанное поле.',
                ['181\n2\n4\n', '181\n2\n2\n', '181\n0\n3\n', '255\n0\n7\n'],
            ),
            _code(
                'Записать по маске',
                'Маска говорит, какие разряды менять. В разрядах, где у `m` '
                'единица, поставьте биты числа `v`, а остальные биты `x` '
                'оставьте как были.',
                'три целых числа, каждое на отдельной строке: `x`, `m` и `v`.',
                'одно число – результат.',
                ['165\n0\n255\n', '165\n255\n90\n', '181\n15\n2\n',
                 '255\n170\n85\n'],
            ),
        ]),
        (TOPICS[3], [
            _text(
                'Остаток без деления',
                'Чему равен остаток от деления 1000 на 16? Делить не нужно: '
                'остаток от деления на степень двойки даёт побитовое И с '
                'подходящей маской. Ответ запишите десятичным числом.',
                1000 & 15,
            ),
            _text(
                'Погасить младшую единицу',
                'Чему равно значение выражения `96 & (96 - 1)` в Python? '
                'Ответ запишите десятичным числом.',
                96 & (96 - 1),
            ),
            _text(
                'Умножение сдвигом',
                'Чему равно значение выражения `(7 << 4) + 7` в Python? '
                'Так быстро умножают на 17. Ответ запишите десятичным числом.',
                (7 << 4) + 7,
            ),
            _code(
                'Степень двойки сверху',
                'Наименьшая степень двойки, не меньшая `n`, пригодится при '
                'выборе размера буфера или блока памяти. Найдите её циклом '
                'со сдвигом влево.',
                'одно целое число `n` (`n >= 1`).',
                'одно число – наименьшая степень двойки, не меньшая `n`.',
                ['1\n', '16\n', '17\n', '1000\n'],
            ),
            _code(
                'Разложение по степеням двойки',
                'Любое число единственным образом раскладывается в сумму '
                'степеней двойки. Выведите по возрастанию все `k`, для '
                'которых $2^k$ входит в двоичную запись `n`.',
                'одно целое число `n` (`n >= 1`).',
                'показатели `k`, каждый на отдельной строке, по возрастанию.',
                ['1\n', '1024\n', '255\n', '13\n'],
            ),
        ]),
    ]


def _check(quiz, bank):
    """Проверка собранного банка: 20 задач, 4 темы, тексты и тесты на месте.

    Считаем только задачи сида: учитель мог добавить свою задачу на странице
    «Задачи», и повторный прогон не должен из-за неё падать.
    """
    seeded = {row['title']: row for _, rows in bank for row in rows}
    questions = list(quiz.questions.filter(title__in=seeded))
    errors = []
    if len(questions) != len(seeded):
        errors.append(f'задач сида {len(questions)}, а нужно {len(seeded)}')

    titles = [question.title for question in questions]
    if len(set(titles)) != len(titles):
        errors.append('заголовки повторяются')

    for topic in TOPICS:
        rows = [question for question in questions if question.topic == topic]
        if len(rows) != 5:
            errors.append(f'тема «{topic}»: задач {len(rows)}, а нужно 5')
        text_count = sum(question.question_type == 'text' for question in rows)
        code_count = sum(question.question_type == 'code' for question in rows)
        if text_count != 3 or code_count != 2:
            errors.append(f'тема «{topic}»: {text_count} text и {code_count} code')

    for question in questions:
        row = seeded[question.title]
        if question.question_type != row['question_type']:
            errors.append(f'«{question.title}»: не тот тип задачи')
        if question.question_type == 'code':
            count = question.test_cases.count()
            if count != 4:
                errors.append(f'«{question.title}»: тестов {count}, а нужно 4')
        elif question.question_type == 'text':
            try:
                int(question.correct_text_answer)
            except (TypeError, ValueError):
                errors.append(f'«{question.title}»: ответ не целое число')

    if errors:
        raise CommandError('Проверка банка не сошлась: ' + '; '.join(errors))


class Command(BaseCommand):
    help = 'Самостоятельная блока 6 «Побитовые операции»: банк из 20 задач.'

    def handle(self, *args, **options):
        try:
            section = Section.objects.get(slug=SECTION_SLUG)
        except Section.DoesNotExist as exc:
            raise CommandError(
                f'Нет блока учебника {SECTION_SLUG}. '
                'Сначала seed_textbook_structure.') from exc

        quiz, _ = Quiz.objects.update_or_create(
            slug=SLUG,
            defaults={
                'title': 'Самостоятельная: побитовые операции',
                'description': ('Каждому – 6 задач из банка в 20: по темам '
                                'блока, с ответом и с кодом.'),
                'quiz_type': 'classwork',
                'section': section,
                'check_minutes': 30,
                'classwork_size': 6,
                'max_attempts': 1,
            },
        )

        written = classwork.has_answers(quiz)
        bank = _bank()
        created = updated = 0
        with transaction.atomic():
            for topic, rows in bank:
                for row in rows:
                    question = Question.objects.filter(
                        quiz=quiz, title=row['title']).first()
                    answer = row.get('correct_text_answer')
                    if question is None:
                        question = Question.objects.create(
                            quiz=quiz,
                            title=row['title'],
                            question_type=row['question_type'],
                            topic=topic,
                            points=row['points'],
                            text=row['text'],
                            correct_text_answer=answer,
                        )
                        created += 1
                    else:
                        question.question_type = row['question_type']
                        question.topic = topic
                        question.points = row['points']
                        question.text = row['text']
                        question.correct_text_answer = answer
                        question.save(update_fields=[
                            'question_type', 'topic', 'points', 'text',
                            'correct_text_answer',
                        ])
                        updated += 1

                    tests = row.get('test_cases')
                    if tests is None:
                        continue
                    # Работу уже писали – старые тесты остаются: пересоздание
                    # каскадом не должно трогать чужие ответы и попытки.
                    if written and question.test_cases.exists():
                        continue
                    question.test_cases.all().delete()
                    TestCase.objects.bulk_create([
                        TestCase(question=question, input_data=stdin,
                                 output_data=stdout)
                        for stdin, stdout in tests
                    ])

        _check(quiz, bank)
        tests_note = 'оставлены' if written else 'пересозданы'
        self.stdout.write(
            f'Создано {created}, обновлено {updated}, тесты {tests_note}.')
