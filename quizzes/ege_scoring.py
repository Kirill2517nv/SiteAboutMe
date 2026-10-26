"""
Частичный балл за задания 26 и 27.

Все остальные задания ЕГЭ оцениваются «верно/неверно», а эти два – по шкале
0/1/2, и с 2027 года правило у них общее: ответ – два числа в ячейках таблицы,
1 балл ставится, если числа перепутаны местами ИЛИ верно только одно из них
(второе неверно или отсутствует).

До 2027 года ответом на 27-е были две пары чисел, каждая своей строкой, и
правило частичного балла было отдельным. ФИПИ убрал эту форму: «в 2027 г.
участнику экзамена нужно будет записать в ответе строку из двух чисел вместо
двух строк по два числа» (спецификация, раздел 11).

Сравниваются именно числа, а не текст вывода: программа ученика может печатать
пару через пробел или через перевод строки, и придираться к раскладке значит
проверять форматирование вместо алгоритма. Порядок при этом сохраняется – в нём
и заключается разница между 2 баллами и 1.
"""
import re

# Задания с частичным баллом. Список короткий и меняется вместе с ФИПИ, поэтому
# живёт здесь, а не в базе.
PARTIAL_TASKS = (26, 27)

NUMBER_RE = re.compile(r'-?\d+')

# Вывод, в котором нет ничего кроме чисел, пробелов и переводов строк. Только
# такой сравнивается по числам: если программа печатает «Ответ: 12», это уже
# не тот формат, который спрашивают в бланке, и придираться к нему честно.
NUMBERS_ONLY_RE = re.compile(r'^[\s\d-]*$')

# Целое число в выводе программы: «13», «-5», а также «13.0» – так печатает
# целое значение, посчитанное через `/`. По смыслу это то же 13, и снимать за
# него балл значит проверять не задачу, а тип переменной. «13.5» сюда не
# подходит: это другое число.
INTEGER_TOKEN_RE = re.compile(r'-?\d+(?:\.0+)?')


def normalize_output(text):
    """Вывод программы без хвостовых пробелов и пустых краёв."""
    if not text:
        return ''
    return '\n'.join(line.rstrip() for line in text.strip().splitlines())


def outputs_match(output, expected):
    """
    Совпал ли вывод программы с эталоном теста.

    Если и эталон, и ответ состоят только из чисел, сравниваются сами числа
    по порядку: у задания 20 ответ – два числа, и «98 293» в одну строку и те
    же два числа в две строки одинаково верны. Раскладка вывода – не то, что
    проверяет задача.

    Порядок при этом важен: «293 98» останется неверным ответом. Целое,
    напечатанное с нулевой дробной частью («13.0»), считается тем же числом.
    Всё, что содержит хоть что-то кроме чисел, сравнивается как текст.
    """
    expected, output = expected or '', output or ''
    if NUMBERS_ONLY_RE.match(expected):
        got = _integers(output)
        if got is not None:
            return got == _numbers(expected)
    return normalize_output(output) == normalize_output(expected)


def _integers(text):
    """Целые числа вывода по порядку или None, если в выводе есть что-то ещё."""
    tokens = (text or '').split()
    if not all(INTEGER_TOKEN_RE.fullmatch(token) for token in tokens):
        return None
    return [int(token.split('.')[0]) for token in tokens]


def is_partial_task(question):
    """Задача оценивается по шкале 0/1/2, а не «верно/неверно»?"""
    return question.ege_number in PARTIAL_TASKS and (question.points or 0) >= 2


def _numbers(text):
    """Все числа вывода по порядку. Раскладка по строкам роли не играет."""
    return [int(n) for n in NUMBER_RE.findall(text or '')]


def grade(question, output, expected):
    """
    Балл за вывод программы: 0..question.points.

    None означает «частичного балла у задачи нет» – такие задачи проверяются
    как раньше, точным совпадением вывода.
    """
    if not is_partial_task(question):
        return None

    return _grade_pair(_numbers(expected), _numbers(output), question.points)


def _grade_pair(expected, got, full):
    if len(expected) != 2:
        # Эталон не по формату задания – оценить частично нечем, остаётся
        # обычное сравнение целиком. Сюда попадают задачи 27, импортированные
        # до 2027 года: у них эталон из четырёх чисел (две пары в две строки).
        # Полный балл за точный ответ такие задачи по-прежнему дают, частичного
        # у них нет – он вернётся с переимпортом банка в формате 2027 года.
        return full if got == expected else 0

    hits = sum(1 for i, value in enumerate(expected) if i < len(got) and got[i] == value)
    if hits == 2:
        return full
    if hits == 1:
        return 1
    # Оба числа найдены, но стоят не в своих ячейках.
    if sorted(got[:2]) == sorted(expected) and len(got) >= 2:
        return 1
    return 0


def expected_answer(question):
    """
    Эталон ответа задачи – то, что ученик должен вписать в бланк.

    У текстовой задачи это correct_text_answer, у задачи с кодом – вывод её
    теста: код теперь только инструмент, и оценивается ответ в поле, как на
    экзамене. Тест у задач банка ЕГЭ один и без stdin.
    """
    if question.question_type == 'code':
        test = next(iter(question.test_cases.all()), None)
        return test.output_data if test else ''
    return question.correct_text_answer or ''


def answer_shape(question):
    """
    Размер таблицы ответа [строк, столбцов] или None – хватит одного поля.

    Считается по эталону: таблица нужна, когда в нём несколько чисел (17, 18,
    20, 25–27). В браузер уходит только форма – на экзамене её тоже видно, – а
    сами числа остаются на сервере.
    """
    expected = expected_answer(question).strip()
    if not NUMBERS_ONLY_RE.match(expected) or len(_numbers(expected)) < 2:
        return None
    lines = [line for line in expected.splitlines() if line.strip()]
    return [len(lines), max(len(NUMBER_RE.findall(line)) for line in lines)]


def check_answer(question, answer):
    """
    Сверяет ответ из поля или таблицы с эталоном: (верно?, балл).

    Балл – не None только у заданий 26 и 27 (шкала 0/1/2). Таблица приходит
    строками через перевод строки, ячейки через пробел, поэтому несколько чисел
    сравниваются как числа по порядку. Одно число у текстовой задачи – по
    старому правилу check_text_answer (с альтернативными ответами).
    """
    from .models import normalize_text_answer

    expected = expected_answer(question)
    score = grade(question, answer, expected)
    if score is not None:
        return score >= question.points, score
    if normalize_text_answer(answer) == normalize_text_answer(expected):
        return True, None
    if question.question_type == 'text':
        if question.check_text_answer(answer):
            return True, None
        # Числа по порядку – только для таблицы: у одного числа outputs_match
        # сравнил бы int'ы и засчитал «0» вместо «00».
        return answer_shape(question) is not None and outputs_match(answer, expected), None
    return outputs_match(answer, expected), None
