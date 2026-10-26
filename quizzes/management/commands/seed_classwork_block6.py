"""Идемпотентный посев первой самостоятельной работы блока 6.

Работа «Побитовые операции» – банк из 20 задач: четыре темы по пять задач,
все решаются программой. В каждой теме три коротких задачи «посчитать и
напечатать» и две программы с вводом. Каждому ученику работа выдаёт 6 задач
из банка по темам (quizzes.classwork.pick), поэтому заголовки не нумеруются:
у соседей своя нумерация и свой порядок задач.

Вывод тестов руками не пишется: у задач с вводом он берётся прогоном эталона
на каждом входе, у задач без ввода – прогоном эталона один раз. Примера из
теста в условии нет – он выдал бы ответ; пример формата, если он нужен,
строится прогоном другой программы на других числах.
"""
import contextlib
import io
import re
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

# Эталоны коротких задач без ввода: программа печатает ответ, ученик пишет
# такую же. Тот же механизм тестов, что у задач с вводом, – один тест с
# пустым входом.
SIMPLE = {
    'Побитовое И': (
        "print(format(45, '08b'))\n"
        "print(format(27, '08b'))\n"
        "print(format(45 & 27, '08b'))"
    ),
    'Исключающее ИЛИ': (
        "print(format(52, '08b'))\n"
        "print(format(19, '08b'))\n"
        "print(format(52 ^ 19, '08b'))"
    ),
    'Побитовое НЕ': (
        "print(format(37, '08b'))\n"
        "print(format(~37 & 255, '08b'))"
    ),
    'Сдвиг влево': 'print(104 >> 3)',
    'Сдвиг вправо': (
        'count = 0\n'
        'for x in range(1000):\n'
        '    if x >> 3 == 25:\n'
        '        count += 1\n'
        'print(count)'
    ),
    'Единицы подряд': (
        'k = 0\n'
        'while (1 << k) - 1 <= 1000:\n'
        '    k += 1\n'
        'print(k)'
    ),
    'Маска разрядов': (
        'm = ((1 << 3) - 1) << 2\n'
        'print(m)\n'
        'print(bin(m))'
    ),
    'Младшие четыре бита': (
        'count = 0\n'
        'for x in range(256):\n'
        '    if x & 0b1111 == 5:\n'
        '        count += 1\n'
        'print(count)'
    ),
    'Выключить бит': (
        'd = 100 ^ 96\n'
        'k = 0\n'
        'while d > 1:\n'
        '    d = d >> 1\n'
        '    k += 1\n'
        'print(k)'
    ),
    'Остаток без деления': 'print(64 - 1)',
    'Погасить младшую единицу': (
        'x = 108\n'
        "print(format(x, '08b'))\n"
        'x = x & (x - 1)\n'
        'x = x & (x - 1)\n'
        "print(format(x, '08b'))"
    ),
    'Умножение сдвигом': (
        'for a in range(10):\n'
        '    for b in range(10):\n'
        '        if a > b and (1 << a) + (1 << b) == 40:\n'
        '            print(a, b)'
    ),
}

# Задачи, где ответ собирается столбиком из восьмизначных строк. format() в
# материале блоков 1–6 не встречался, поэтому подсказка объясняет его прямо в
# условии – и задачу можно решить, не заглядывая в другие статьи.
HINT_TASKS = ('Исключающее ИЛИ', 'Побитовое И', 'Побитовое НЕ',
              'Погасить младшую единицу')


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


def _format_hint():
    """
    Подсказка о `format(x, '08b')` – общий абзац задач столбиком.

    Пример вывода в ней тоже берётся прогоном: написанный руками разошёлся бы
    с Python молча, и ученик читал бы неверную подсказку.
    """
    sample = _run("print(format(5, '08b'))", '')
    return (
        "Подсказка: `format(x, '08b')` превращает число в двоичную запись "
        'ровно из 8 знаков – с ведущими нулями, без `0b`. Например, '
        f"`print(format(5, '08b'))` печатает `{sample}`: `8` – сколько "
        'знаков, `0` – чем дополнять слева, `b` – двоичная система. Так '
        'числа встают друг под другом разряд в разряд.'
    )


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


def _simple(title, lead, example=None):
    """Задача без ввода: программа печатает ответ, условие – формат вывода.

    Примера из теста в условии нет – он показал бы ответ. Пример формата,
    если он нужен, строится прогоном другой программы на других числах.
    """
    code = SIMPLE[title]
    text = lead.rstrip()
    if example:
        example_code, note = example
        text += (f'\n\n###### {note}\n\n'
                 f'```text\n{_run(example_code, "")}\n```')
    return {
        'title': title,
        'question_type': 'code',
        'points': 1,
        'text': text,
        'correct_text_answer': None,
        'alternative_answers': None,
        'test_cases': [('', _run(code, ''))],
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
    """20 задач с кодом: четыре темы, в каждой три без ввода и две с вводом."""
    return [
        (TOPICS[0], [
            _simple(
                'Побитовое И',
                'Напишите программу, которая печатает в трёх строках двоичные '
                'записи: число 45, под ним число 27, под ними результат '
                '`45 & 27` – каждое ровно восемью знаками. Получится столбик, '
                'в котором видно, как операция работает в каждом разряде. '
                'Перед тем как запускать, распишите столбик на бумаге сами – '
                'потом сверьтесь.\n'
                '\n'
                'Программа ничего не вводит.\n'
                '\n'
                + _format_hint(),
                ("print(format(12, '08b'))\n"
                 "print(format(10, '08b'))\n"
                 "print(format(12 & 10, '08b'))",
                 'Пример формата для `12 & 10`'),
            ),
            _simple(
                'Исключающее ИЛИ',
                'Напишите программу, которая печатает в трёх строках двоичные '
                'записи: число 52, под ним число 19, под ними результат '
                '`52 ^ 19` – каждое ровно восемью знаками. Получится столбик, '
                'в котором видно, как операция работает в каждом разряде. '
                'Перед тем как запускать, распишите столбик на бумаге сами – '
                'потом сверьтесь.\n'
                '\n'
                'Программа ничего не вводит.\n'
                '\n'
                + _format_hint(),
                ("print(format(12, '08b'))\n"
                 "print(format(10, '08b'))\n"
                 "print(format(12 ^ 10, '08b'))",
                 'Пример формата для `12 ^ 10`'),
            ),
            _simple(
                'Побитовое НЕ',
                'Напишите программу, которая печатает в двух строках '
                'восемью знаками: число 37 и под ним его инверсию в пределах '
                'байта `~37 & 255`.\n'
                '\n'
                '`~` у целых чисел Python уходит в отрицательные числа, а '
                '`& 255` оставляет младшие восемь разрядов – это и есть '
                'пределы одного байта.\n'
                '\n'
                'Программа ничего не вводит.\n'
                '\n'
                + _format_hint(),
                ("print(format(12, '08b'))\n"
                 "print(format(~12 & 255, '08b'))",
                 'Пример формата для числа 12'),
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
                'В настройках флаги часто хранят одним числом: каждый разряд – '
                'отдельный флаг, 1 – флаг включён, 0 – выключен. Дано '
                'несколько наборов флагов. Выведите число, в котором единицы '
                'стоят ровно в тех разрядах, где флаг включён хотя бы в одном '
                'наборе, но не во всех; остальные разряды – нули.\n'
                '\n'
                'Разберём первый пример поразрядно: `7 = 111`, `5 = 101`, '
                '`6 = 110`. Младший разряд есть у 7 и 5, но не у 6 – входит в '
                'ответ. Средний – у 7 и 6, но не у 5 – входит. Старший – у '
                'всех трёх – не входит. Ответ: `011`, то есть 3.',
                'сначала `n` – количество наборов, затем `n` чисел, каждое на '
                'отдельной строке.',
                'одно число – разряды, которые есть не у всех.',
                ['3\n7\n5\n6\n', '1\n9\n', '3\n5\n5\n5\n', '4\n1\n2\n4\n8\n'],
            ),
        ]),
        (TOPICS[1], [
            _simple(
                'Сдвиг влево',
                'Известно, что `x << 3` равно 104. Напишите программу, которая '
                'находит и печатает `x` – одно десятичное число.\n'
                '\n'
                'Программа ничего не вводит.',
            ),
            _simple(
                'Сдвиг вправо',
                'Сколько существует неотрицательных целых `x`, для которых '
                '`x >> 3` равно 25? Напишите программу, которая считает их '
                'перебором и печатает одно число – количество.\n'
                '\n'
                'Программа ничего не вводит.',
            ),
            _simple(
                'Единицы подряд',
                'Найдите наименьшее `k`, при котором `(1 << k) - 1` больше '
                '1000. Напишите программу, которая ищет его циклом `while` и '
                'печатает `k` – одно десятичное число.\n'
                '\n'
                'Программа ничего не вводит.',
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
            _simple(
                'Маска разрядов',
                'Напишите программу, которая строит маску с единицами ровно в '
                'разрядах 2, 3 и 4 (нумерация с нуля от младшего) и печатает '
                'её в двух строках: в первой – десятичное число, во второй – '
                '`bin()` от него.\n'
                '\n'
                'Программа ничего не вводит.',
            ),
            _simple(
                'Младшие четыре бита',
                'Сколько чисел `x` от 0 до 255 включительно удовлетворяют '
                'условию `x & 0b1111 == 5`? Напишите программу, которая '
                'перебирает числа и печатает одно число – количество.\n'
                '\n'
                'Программа ничего не вводит.',
            ),
            _simple(
                'Выключить бит',
                'Из числа 100 выключили один бит и получили 96. Напишите '
                'программу, которая находит номер этого разряда (нумерация с '
                'нуля от младшего) и печатает его – одно число.\n'
                '\n'
                'Программа ничего не вводит.',
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
            _simple(
                'Остаток без деления',
                'Для любого неотрицательного `x` выражение `x & m` равно '
                'остатку от деления `x` на 64. Напишите программу, которая '
                'находит `m` и печатает его – одно число.\n'
                '\n'
                'Программа ничего не вводит.',
            ),
            _simple(
                'Погасить младшую единицу',
                'К числу `x = 108` два раза подряд применяют '
                '`x = x & (x - 1)`. Напишите программу, которая печатает в '
                'двух строках восемью знаками: каким `x` было в начале и '
                'каким стало после двух применений. Сравните строки: какие '
                'единицы пропали?\n'
                '\n'
                'Программа ничего не вводит.\n'
                '\n'
                + _format_hint(),
                ('x = 12\n'
                 "print(format(x, '08b'))\n"
                 'x = x & (x - 1)\n'
                 "print(format(x, '08b'))",
                 'Пример формата для числа 12 и одного применения'),
            ),
            _simple(
                'Умножение сдвигом',
                'При любом `x` выражение `(x << a) + (x << b)` равно `x * 40`, '
                'причём `a > b`. Напишите программу, которая перебирает `a` и '
                '`b` и печатает их через пробел: сначала `a`, потом `b`.\n'
                '\n'
                'Программа ничего не вводит.',
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
    """Проверка собранного банка: 20 задач с кодом, тесты, баллы, утечки.

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

    for question in questions:
        row = seeded[question.title]
        if question.question_type != row['question_type']:
            errors.append(f'«{question.title}»: не тот тип задачи')
        if question.question_type != 'code':
            errors.append(f'«{question.title}»: задача не с кодом')
            continue
        tests = list(question.test_cases.order_by('id'))
        if question.title in SIMPLE:
            if len(tests) != 1 or tests[0].input_data != '':
                errors.append(f'«{question.title}»: нужен один тест без ввода')
                continue
            # Условие не должно выдавать ответ: иначе подсказка становится
            # решением. Проверяем по границам числа: «10» внутри «1000» –
            # совпадение цифр, а не подсказка.
            pattern = r'(?<!\d)' + re.escape(tests[0].output_data) + r'(?!\d)'
            if re.search(pattern, question.text):
                errors.append(f'«{question.title}»: вывод эталона есть в условии')
            if 'Программа ничего не вводит.' not in question.text:
                errors.append(
                    f'«{question.title}»: нет «Программа ничего не вводит.»')
            if (question.title in HINT_TASKS
                    and "format(x, '08b')" not in question.text):
                errors.append(
                    f'«{question.title}»: в подсказке нет format(x, \'08b\')')
        elif len(tests) != 4:
            errors.append(f'«{question.title}»: тестов {len(tests)}, а нужно 4')

    # Пример в условии «Флагов не у всех» разбирает 7, 5 и 6 – это первый
    # тест. Разойдись вывод с разбором, и условие учило бы неверному ответу.
    flags = next((question for question in questions
                  if question.title == 'Флаги не у всех'), None)
    if flags is not None:
        first = flags.test_cases.order_by('id').first()
        if first is None or first.output_data != '3':
            errors.append('«Флаги не у всех»: первый тест даёт не 3 – '
                          'разбор примера в условии разошёлся с тестом')

    total = sum(question.points for question in questions)
    if total != 28:
        errors.append(f'сумма баллов {total}, а нужно 28')

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
                                'блока, все решаются программой.'),
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
        kept = []
        with transaction.atomic():
            for topic, rows in bank:
                for row in rows:
                    question = Question.objects.filter(
                        quiz=quiz, title=row['title']).first()
                    answer = row.get('correct_text_answer')
                    alternatives = row.get('alternative_answers')
                    if question is None:
                        question = Question.objects.create(
                            quiz=quiz,
                            title=row['title'],
                            question_type=row['question_type'],
                            topic=topic,
                            points=row['points'],
                            text=row['text'],
                            correct_text_answer=answer,
                            alternative_answers=alternatives,
                        )
                        created += 1
                    else:
                        question.question_type = row['question_type']
                        question.topic = topic
                        question.points = row['points']
                        question.text = row['text']
                        question.correct_text_answer = answer
                        question.alternative_answers = alternatives
                        question.save(update_fields=[
                            'question_type', 'topic', 'points', 'text',
                            'correct_text_answer', 'alternative_answers',
                        ])
                        updated += 1

                    tests = row.get('test_cases')
                    if tests is None:
                        continue
                    # Работу уже писали и тесты у задачи есть – оставляем:
                    # пересоздание каскадом трогало бы чужие ответы и попытки.
                    # Задача без тестов (бывшая текстовая стала кодом)
                    # пересоздаётся всегда, иначе осталась бы без проверки.
                    if written and question.test_cases.exists():
                        kept.append(question.title)
                        continue
                    question.test_cases.all().delete()
                    TestCase.objects.bulk_create([
                        TestCase(question=question, input_data=stdin,
                                 output_data=stdout)
                        for stdin, stdout in tests
                    ])

        _check(quiz, bank)
        self.stdout.write(f'Создано {created}, обновлено {updated}.')
        if kept:
            self.stdout.write(self.style.WARNING(
                'Тесты оставлены, работу уже писали: ' + ', '.join(kept) + '.'))
