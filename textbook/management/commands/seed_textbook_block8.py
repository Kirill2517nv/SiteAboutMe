"""Идемпотентный посев контента блока 8 «Строки в Python».

Статьи-заголовки уже созданы командой seed_textbook_structure. Здесь
наполняем их блоками (ArticleBlock) и тестами самопроверки — урок за уроком.
Добавляя новый урок, дописывайте seed_8_N() и вызывайте её из handle().
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from quizzes.models import Choice, Question, Quiz, UserAnswer
from textbook.models import Article, ArticleBlock, ArticleQuiz


from textbook.services import replace_blocks as _replace_blocks
from textbook.services import shuffle_choices as _shuffle_choices
from textbook.services import sync_question_texts as _sync_question_texts


def _self_check(slug, title, description, questions):
    """Создаёт (или переиспользует) тест самопроверки с вопросами."""
    quiz, _ = Quiz.objects.get_or_create(
        slug=slug,
        defaults={
            'title': title,
            'description': description,
            'is_self_check': True,
            'max_attempts': 0,
            'quiz_type': 'standard',
        },
    )
    if not quiz.is_self_check:
        quiz.is_self_check = True
        quiz.save(update_fields=['is_self_check'])

    # Тест ещё никто не решал — пересоздаём вопросы, чтобы до базы доехали
    # и правки формулировок, и перемешанный порядок вариантов ответа.
    if quiz.questions.exists() and not UserAnswer.objects.filter(question__quiz=quiz).exists():
        quiz.questions.all().delete()

    if quiz.questions.count() == 0:
        for q in questions:
            question = Question.objects.create(
                quiz=quiz,
                question_type=q['type'],
                text=q['text'],
                correct_text_answer=q.get('correct_text_answer', ''),
                points=1,
            )
            for choice_text, is_correct in _shuffle_choices(q['text'], q.get('choices', [])):
                Choice.objects.create(question=question, text=choice_text, is_correct=is_correct)
    # Правки формулировок должны доезжать и до тестов, которые уже решали:
    # пересоздать вопросы там нельзя — каскад унёс бы ответы учеников.
    _sync_question_texts(quiz, questions)
    return quiz


# Код, который трассирует виджет loop-trace в уроке 8.1: «замена» первой
# буквы на заглавную. Показывает главное свойство str — исходная строка
# на всех шагах одна и та же, результат строится рядом с нуля.
CAPITALIZE_CODE = [
    "text = 'привет'",
    "result = ''",
    'for i in range(len(text)):',
    '    if i == 0:',
    '        result = result + chr(ord(text[i]) - 32)',
    '    else:',
    '        result = result + text[i]',
    'print(result)',
]


def _capitalize_trace(word='привет'):
    """Пошаговая трасса сборки новой строки для виджета loop-trace.

    Виджет ничего не вычисляет сам — повторяем разбираемый алгоритм
    обычным циклом и складываем полное состояние на каждом шаге.
    Переменную text показываем в состоянии намеренно: смысл трассы в том,
    что её значение не меняется ни на одном шаге.
    """
    steps = []
    text = word
    result = None
    i = None
    ch = None

    def state():
        s = {'text': text}
        if i is not None:
            s['i'] = i
            s['text[i]'] = ch
        if result is not None:
            s['result'] = result
        return s

    steps.append(dict(
        line=1, vars=state(),
        note='Строка, которую надо «исправить». Дальше она не изменится ни разу.',
    ))
    result = ''
    steps.append(dict(
        line=2, vars=state(),
        note='Заводим пустую строку-накопитель: результат будем строить рядом, с нуля.',
    ))

    for pos in range(len(text)):
        i = pos
        ch = text[pos]
        steps.append(dict(
            line=3, vars=state(),
            note='Читаем символ на позиции {}: {!r}. Читать строку можно сколько '
                 'угодно — запрещено только записывать.'.format(pos, ch),
        ))
        first = (pos == 0)
        steps.append(dict(
            line=4, vars=state(), check=first,
            note=('Это первый символ — его и надо заменить.' if first
                  else 'Не первый символ — оставляем как есть.'),
        ))
        if first:
            upper = chr(ord(ch) - 32)
            result = result + upper
            steps.append(dict(
                line=5, vars=state(),
                note='ord({!r}) = {}, минус 32 даёт {} — это {!r}. Приклеили её к '
                     'накопителю.'.format(ch, ord(ch), ord(ch) - 32, upper),
            ))
        else:
            result = result + ch
            steps.append(dict(
                line=7, vars=state(),
                note='Приклеили {!r} к накопителю: получилось {!r}. Строго говоря, '
                     'здесь создалась новая строка, а предыдущая просто осталась '
                     'без имени.'.format(ch, result),
            ))

    i = None
    ch = None
    steps.append(dict(
        line=3, vars=state(),
        note='Позиции кончились — цикл завершён.',
    ))
    steps.append(dict(
        line=8, vars=state(), out=result,
        note='Печатаем результат. Обратите внимание на строку text: она такая же, '
             'какой была в первом шаге.',
    ))
    return steps


# Код, который трассирует loop-trace в уроке 8.2: цикл, повторяющий работу
# среза s[1:5:2]. Границы вписаны числами прямо в код — так в трассе видно,
# что stop сравнивается с i, а не участвует в вычислениях.
SLICE_CODE = [
    "s = 'Привет'",
    "result = ''",
    'i = 1                     # start',
    'while i < 5:              # stop',
    '    result = result + s[i]',
    '    i = i + 2             # step',
    'print(result)',
]


def _slice_trace(word='Привет', start=1, stop=5, step=2):
    """Пошаговая трасса цикла, эквивалентного срезу word[start:stop:step].

    Виджет ничего не считает сам — повторяем алгоритм обычным while и
    складываем полное состояние на каждом шаге. Главный кадр трассы —
    последняя проверка условия: i дошёл до stop, и символ на этой позиции
    в результат так и не попал.
    """
    steps = []
    s = word
    i = None
    result = None

    def state():
        st = {'s': s}
        if i is not None:
            st['i'] = i
            st['s[i]'] = s[i] if 0 <= i < len(s) else None
        if result is not None:
            st['result'] = result
        return st

    steps.append(dict(
        line=1, vars=state(),
        note='Строка, из которой будем брать срез.',
    ))
    result = ''
    steps.append(dict(
        line=2, vars=state(),
        note='Срез не вырезает символы из строки, а собирает рядом новую — '
             'вот накопитель для неё.',
    ))
    i = start
    steps.append(dict(
        line=3, vars=state(),
        note='i — текущая позиция. Начинаем с start = {}.'.format(start),
    ))

    while True:
        go = i < stop
        steps.append(dict(
            line=4, vars=state(), check=go,
            note=('i = {}, и {} < {} — истина: позицию берём.'.format(i, i, stop) if go
                  else 'i = {}, а {} < {} — ложь. Цикл закончился, и символ на позиции '
                       'stop = {} в результат так и не попал: правая граница не '
                       'включается.'.format(i, i, stop, stop)),
        ))
        if not go:
            break
        result = result + s[i]
        steps.append(dict(
            line=5, vars=state(),
            note='Взяли s[{}] = {!r} и приклеили к накопителю: {!r}.'.format(i, s[i], result),
        ))
        i = i + step
        steps.append(dict(
            line=6, vars=state(),
            note='Прибавили шаг {}: следующая позиция — {}.'.format(step, i),
        ))

    steps.append(dict(
        line=7, vars=state(), out=result,
        note='Ровно то же самое даёт одна короткая запись: '
             's[{}:{}:{}] — {!r}.'.format(start, stop, step, s[start:stop:step]),
    ))
    return steps


# Код, который трассирует loop-trace в уроке 8.3: наивный поиск подстроки
# перебором позиций. Показывает, что прячется за оператором in — окно длиной
# len(sub) едет вправо, пока срез не совпадёт с искомым куском.
SEARCH_CODE = [
    "text = 'информатика'",
    "sub = 'мат'",
    'i = 0',
    'found = False',
    'while i <= len(text) - len(sub):',
    '    if text[i:i + len(sub)] == sub:',
    '        found = True',
    '        break',
    '    i = i + 1',
    'print(found)',
]


def _substring_trace(text='информатика', sub='мат'):
    """Пошаговая трасса наивного поиска подстроки для виджета loop-trace.

    Виджет ничего не ищет сам — повторяем алгоритм обычным while и
    складываем полное состояние на каждом шаге. Главные кадры трассы:
    совпадение окна с искомым куском и break сразу после него.
    """
    steps = []
    i = None
    found = None
    window = 'text[i:i+{}]'.format(len(sub))
    limit = len(text) - len(sub)

    def state():
        st = {'text': text, 'sub': sub}
        if i is not None:
            st['i'] = i
            st[window] = text[i:i + len(sub)]
        if found is not None:
            st['found'] = found
        return st

    steps.append(dict(
        line=1, vars=state(),
        note='Строка, в которой ищем.',
    ))
    steps.append(dict(
        line=2, vars=state(),
        note='Кусок, который ищем. В нём {} символа — значит, и окно будет '
             'шириной {} символа.'.format(len(sub), len(sub)),
    ))
    i = 0
    steps.append(dict(
        line=3, vars=state(),
        note='i — позиция, к которой прикладываем окно. Начинаем с начала строки.',
    ))
    found = False
    steps.append(dict(
        line=4, vars=state(),
        note='Пока ничего не нашли.',
    ))

    while True:
        go = i <= limit
        steps.append(dict(
            line=5, vars=state(), check=go,
            note=('i = {}, и {} <= {} — истина: окно ещё помещается, '
                  'позицию проверяем.'.format(i, i, limit) if go
                  else 'i = {}, а {} <= {} — ложь: справа осталось меньше {} '
                       'символов, окно уже не поместится. Перебор '
                       'кончился.'.format(i, i, limit, len(sub))),
        ))
        if not go:
            break

        chunk = text[i:i + len(sub)]
        hit = chunk == sub
        steps.append(dict(
            line=6, vars=state(), check=hit,
            note=('В окне {!r} — это и есть искомый кусок.'.format(chunk) if hit
                  else 'В окне {!r}, а ищем {!r} — не совпало.'.format(chunk, sub)),
        ))
        if hit:
            found = True
            steps.append(dict(
                line=7, vars=state(),
                note='Ответ уже известен: кусок в строке есть.',
            ))
            steps.append(dict(
                line=8, vars=state(),
                note='break — дальше искать незачем. Позиции с {} по {} так и '
                     'останутся непроверенными.'.format(i + 1, limit),
            ))
            break

        i = i + 1
        steps.append(dict(
            line=9, vars=state(),
            note='Сдвигаем окно на один символ вправо.',
        ))

    steps.append(dict(
        line=10, vars=state(), out=str(found),
        note='Ровно то же самое даёт одна короткая запись: '
             '{!r} in {!r} — {}.'.format(sub, text, sub in text),
    ))
    return steps


# Код, который трассирует loop-trace в уроке 8.4: обход всех вхождений
# подстроки через find() со вторым параметром. Показывает то, чего не умеет
# ни один метод по отдельности: find() отдаёт одну позицию, count() — одно
# число, а «покажи все места» собирается из find(), который каждый раз
# стартует за прошлой находкой.
FIND_ALL_CODE = [
    "text = 'кот и кот и котлета'",
    "sub = 'кот'",
    'i = 0                     # откуда искать',
    'n = 0                     # сколько уже нашли',
    'pos = text.find(sub, i)',
    'while pos != -1:',
    '    print(pos)',
    '    n = n + 1',
    '    i = pos + len(sub)    # перепрыгиваем через найденное',
    '    pos = text.find(sub, i)',
    "print('всего:', n)",
]


def _find_all_trace(text='кот и кот и котлета', sub='кот'):
    """Пошаговая трасса обхода всех вхождений подстроки для loop-trace.

    Виджет ничего не ищет сам — повторяем алгоритм обычным while и
    складываем полное состояние на каждом шаге. Главные кадры трассы:
    прыжок i за найденное вхождение (та же логика, по которой count() не
    считает пересечения) и последний find(), вернувший -1, — именно он
    останавливает цикл, а не длина строки.
    """
    steps = []
    i = None
    n = None
    pos = None

    def state():
        st = {'text': text, 'sub': sub}
        if i is not None:
            st['i'] = i
        if pos is not None:
            st['pos'] = pos
        if n is not None:
            st['n'] = n
        return st

    steps.append(dict(
        line=1, vars=state(),
        note='Строка, в которой ищем. Вхождений в ней несколько — одного '
             'ответа find() тут не хватит.',
    ))
    steps.append(dict(
        line=2, vars=state(),
        note='Кусок, который ищем.',
    ))
    i = 0
    steps.append(dict(
        line=3, vars=state(),
        note='i — позиция, с которой начинать очередной поиск. В первый раз — '
             'с начала строки.',
    ))
    n = 0
    steps.append(dict(
        line=4, vars=state(),
        note='Счётчик находок.',
    ))
    pos = text.find(sub, i)
    steps.append(dict(
        line=5, vars=state(),
        note='find() просмотрел строку начиная с позиции {} и вернул {} — '
             'позицию первого вхождения.'.format(i, pos),
    ))

    while True:
        go = pos != -1
        steps.append(dict(
            line=6, vars=state(), check=go,
            note=('pos = {} — это не -1, значит вхождение нашлось и его надо '
                  'обработать.'.format(pos) if go
                  else 'pos = -1: find() больше ничего не нашёл. Вот что '
                       'останавливает цикл — не длина строки, а ответ '
                       '«не найдено».'),
        ))
        if not go:
            break

        steps.append(dict(
            line=7, vars=state(), out=str(pos),
            note='Печатаем позицию очередного вхождения.',
        ))
        n = n + 1
        steps.append(dict(
            line=8, vars=state(),
            note='Нашли уже {}.'.format(n),
        ))
        i = pos + len(sub)
        steps.append(dict(
            line=9, vars=state(),
            note='Следующий поиск начнём с позиции {}: {} + {} — это сразу за '
                 'найденным куском. Ровно так же перепрыгивает через находку '
                 'count(), поэтому он и не видит пересечений.'.format(
                     i, pos, len(sub)),
        ))
        pos = text.find(sub, i)
        steps.append(dict(
            line=10, vars=state(),
            note=('find() искал начиная с {} и вернул {}. Позиция считается в '
                  'исходной строке, а не от {}.'.format(i, pos, i) if pos != -1
                  else 'find() искал начиная с {} и вернул -1: правее вхождений '
                       'больше нет.'.format(i)),
        ))

    steps.append(dict(
        line=11, vars=state(), out='всего: {}'.format(n),
        note='Столько же вернул бы и text.count(sub) — {}. Только count() '
             'сообщил бы одно число, а цикл показал каждое место. Обратите '
             'внимание на последнее вхождение: оно внутри слова «котлета», и '
             'ни find(), ни count() этого не замечают.'.format(text.count(sub)),
    ))
    return steps


# Код, который трассирует виджет loop-trace в уроке 8.5: очистка строки —
# оставляем только буквы и сразу приводим их к нижнему регистру. Собирает
# вместе три темы урока (isalpha, lower и «строка строится рядом») и готовит
# задачу о палиндроме из урока 8.7.
CLEAN_LETTERS_CODE = [
    "text = 'А, роза!'",
    "clean = ''            # сюда собираем очищенную строку",
    'for c in text:',
    '    if c.isalpha():',
    '        clean = clean + c.lower()',
    'print(clean)',
]


def _clean_letters_trace(text='А, роза!'):
    """Пошаговая трасса очистки строки для loop-trace.

    Виджет ничего не выполняет сам — повторяем алгоритм обычным циклом и
    складываем полное состояние на каждом шаге. Главные кадры трассы: text
    на всех шагах один и тот же (строка неизменяема), а clean растёт рядом;
    условие isalpha() отсекает запятую, пробел и восклицательный знак.
    """
    steps = []
    c = None
    clean = None

    def state():
        st = {'text': text}
        if c is not None:
            st['c'] = c
        if clean is not None:
            st['clean'] = clean
        return st

    def name(ch):
        return 'пробел' if ch == ' ' else '«{}»'.format(ch)

    steps.append(dict(
        line=1, vars=state(),
        note='Исходная строка. В ней есть заглавная буква, запятая, пробел и '
             'восклицательный знак — всё то, что мешает сравнивать строки.',
    ))
    clean = ''
    steps.append(dict(
        line=2, vars=state(),
        note='Пустая строка-заготовка. Исходную мы не тронем — менять её '
             'нельзя (урок 8.1), поэтому результат строим рядом с нуля.',
    ))

    for ch in text:
        c = ch
        steps.append(dict(
            line=3, vars=state(),
            note='Очередной символ строки: {}.'.format(name(c)),
        ))
        ok = c.isalpha()
        steps.append(dict(
            line=4, vars=state(), check=ok,
            note=('{} — буква, значит символ идёт в результат.'.format(name(c))
                  if ok else
                  '{} — не буква, isalpha() вернул False, и тело if '
                  'пропускается. Символ просто не попадёт в '
                  'clean.'.format(name(c))),
        ))
        if ok:
            clean = clean + c.lower()
            steps.append(dict(
                line=5, vars=state(),
                note='Приклеили к clean букву в нижнем регистре: получилось '
                     '«{}». Обратите внимание на text — он на всех шагах один '
                     'и тот же.'.format(clean),
            ))

    steps.append(dict(
        line=6, vars=state(), out=clean,
        note='В clean остались только буквы и все — строчные. Такую строку уже '
             'можно сравнивать с другой без оглядки на регистр и знаки '
             'препинания. Ровно с этого шага начинается проверка на палиндром '
             'в уроке 8.7.',
    ))
    return steps


# Код, который трассирует loop-trace в уроке 8.6: ручное разрезание строки
# по разделителю через find() и срез — то, что делает split() одним вызовом.
# Показывает главное: разделитель не попадает ни в один кусок, а последний
# кусок берётся уже без find() — отсюда и «частей на одну больше, чем
# разделителей». Список в трассе намеренно не строится: части печатаются по
# одной, чтобы не тащить в урок блок 9 раньше времени.
SPLIT_CODE = [
    "s = '2026-08-01'",
    "sep = '-'",
    'start = 0                  # откуда искать очередной разделитель',
    'n = 0                      # сколько частей уже отрезали',
    'pos = s.find(sep, start)',
    'while pos != -1:',
    '    print(s[start:pos])    # кусок до разделителя',
    '    n = n + 1',
    '    start = pos + len(sep) # перепрыгиваем через разделитель',
    '    pos = s.find(sep, start)',
    'print(s[start:])           # хвост: справа разделителей больше нет',
    "print('частей:', n + 1)",
]


def _split_trace(text='2026-08-01', sep='-'):
    """Пошаговая трасса ручного split() для виджета loop-trace.

    Виджет ничего не режет сам — повторяем алгоритм обычным while и
    складываем полное состояние на каждом шаге. Главные кадры трассы: срез
    s[start:pos] не включает правую границу, поэтому разделитель теряется
    сам собой; и выход из цикла по -1, после которого хвост строки нужно
    забрать отдельной строкой кода.
    """
    steps = []
    start = None
    pos = None
    n = None

    def state():
        st = {'s': text, 'sep': sep}
        if start is not None:
            st['start'] = start
        if pos is not None:
            st['pos'] = pos
        if n is not None:
            st['n'] = n
        return st

    steps.append(dict(
        line=1, vars=state(),
        note='Строка, которую надо разрезать. Разделитель в ней встречается '
             '{} раза — значит, частей будет {}.'.format(
                 text.count(sep), text.count(sep) + 1),
    ))
    steps.append(dict(
        line=2, vars=state(),
        note='Разделитель. Его задача — только показать место разреза; в '
             'куски он попасть не должен.',
    ))
    start = 0
    steps.append(dict(
        line=3, vars=state(),
        note='start — начало очередного куска. Первый кусок начинается с '
             'начала строки.',
    ))
    n = 0
    steps.append(dict(
        line=4, vars=state(),
        note='Счётчик отрезанных кусков.',
    ))
    pos = text.find(sep, start)
    steps.append(dict(
        line=5, vars=state(),
        note='find() из урока 8.4 нашёл первый разделитель — он стоит на '
             'позиции {}.'.format(pos),
    ))

    while True:
        go = pos != -1
        steps.append(dict(
            line=6, vars=state(), check=go,
            note=('pos = {} — разделитель есть, значит слева от него есть и '
                  'кусок.'.format(pos) if go
                  else 'pos = -1: разделителей больше нет, и цикл на этом '
                       'закончился. А строка — нет: справа остался кусок, '
                       'который никто ещё не отрезал.'),
        ))
        if not go:
            break

        chunk = text[start:pos]
        steps.append(dict(
            line=7, vars=state(), out=chunk,
            note='Отрезали s[{}:{}] — это {!r}. Срез не включает правую '
                 'границу (урок 8.2), поэтому разделитель в кусок не '
                 'попал.'.format(start, pos, chunk),
        ))
        n = n + 1
        steps.append(dict(
            line=8, vars=state(),
            note='Кусков уже {}.'.format(n),
        ))
        start = pos + len(sep)
        steps.append(dict(
            line=9, vars=state(),
            note='Следующий кусок начинается сразу за разделителем — с '
                 'позиции {}.'.format(start),
        ))
        pos = text.find(sep, start)
        steps.append(dict(
            line=10, vars=state(),
            note=('Ищем следующий разделитель начиная с {} — нашёлся на '
                  'позиции {}.'.format(start, pos) if pos != -1
                  else 'Ищем следующий разделитель начиная с {} — find() '
                       'вернул -1, правее их нет.'.format(start)),
        ))

    tail = text[start:]
    steps.append(dict(
        line=11, vars=state(), out=tail,
        note='А вот и то, ради чего написана эта строка: справа от последнего '
             'разделителя остался кусок {!r}, и никакой find() его уже не '
             'найдёт. Его забираем срезом «до конца».'.format(tail),
    ))
    steps.append(dict(
        line=12, vars=state(), out='частей: {}'.format(n + 1),
        note='Разделителей было {}, а частей вышло {} — на одну больше. Ровно '
             'этот список и вернёт s.split(sep): {}.'.format(
                 n, n + 1, text.split(sep)),
    ))
    return steps


# Код, который трассирует loop-trace в уроке 8.7: поиск самой длинной цепочки
# одинаковых символов подряд. Главные кадры трассы: cur сбрасывается в 1 на
# границе цепочки, а сравнение с best идёт на каждом шаге — в том числе внутри
# цепочки, а не после её обрыва. Именно поэтому цепочка, упирающаяся в конец
# строки, не теряется.
CHAIN_CODE = [
    "s = 'ААБВВВВГ'",
    'best = 0                   # ответ для пустой строки уже готов',
    'cur = 0',
    'if len(s) > 0:',
    '    best = 1               # первый символ — цепочка длиной 1',
    '    cur = 1',
    'for i in range(1, len(s)):',
    '    if s[i] == s[i - 1]:',
    '        cur = cur + 1      # цепочка продолжается',
    '    else:',
    '        cur = 1            # началась новая',
    '    if cur > best:',
    '        best = cur',
    'print(best)',
]


def _max_chain_trace(text='ААБВВВВГ'):
    """Пошаговая трасса поиска самой длинной цепочки для loop-trace.

    Виджет ничего не считает сам — повторяем алгоритм обычным циклом и
    складываем полное состояние на каждом шаге.
    """
    steps = []
    i = None
    cur = None
    best = None

    def state():
        st = {'s': text}
        if i is not None:
            st['i'] = i
            st['s[i]'] = text[i]
        if cur is not None:
            st['cur'] = cur
        if best is not None:
            st['best'] = best
        return st

    steps.append(dict(
        line=1, vars=state(),
        note='Строка, в которой ищем самую длинную цепочку одинаковых символов '
             'подряд. Глазами ответ виден сразу — программе придётся пройти её '
             'до конца.',
    ))
    best = 0
    steps.append(dict(
        line=2, vars=state(),
        note='best — самая длинная цепочка из уже увиденных. Ноль здесь не '
             'формальность: для пустой строки это и есть готовый ответ.',
    ))
    cur = 0
    steps.append(dict(
        line=3, vars=state(),
        note='cur — длина цепочки, которая идёт прямо сейчас.',
    ))
    non_empty = len(text) > 0
    steps.append(dict(
        line=4, vars=state(), check=non_empty,
        note=('В строке есть символы, значит первая цепочка уже началась.'
              if non_empty else
              'Строка пустая — тело if пропускается, и ответом останется ноль.'),
    ))
    if non_empty:
        best = 1
        steps.append(dict(
            line=5, vars=state(),
            note='Первый символ ни с чем не сравнивали, но цепочка длиной 1 в '
                 'строке уж точно есть.',
        ))
        cur = 1
        steps.append(dict(
            line=6, vars=state(),
            note='Она же и есть текущая цепочка: пока в ней один символ {!r}.'
                 .format(text[0]),
        ))

    for pos in range(1, len(text)):
        i = pos
        steps.append(dict(
            line=7, vars=state(),
            note='Позиция {}: символ {!r}, предыдущий — {!r}.'.format(
                pos, text[pos], text[pos - 1]),
        ))
        same = text[pos] == text[pos - 1]
        steps.append(dict(
            line=8, vars=state(), check=same,
            note=('{!r} и {!r} — один и тот же символ.'.format(
                      text[pos], text[pos - 1]) if same else
                  '{!r} не равно {!r}: цепочка оборвалась.'.format(
                      text[pos], text[pos - 1])),
        ))
        if same:
            cur = cur + 1
            steps.append(dict(
                line=9, vars=state(),
                note='Цепочка продолжается, в ней уже {} символа.'.format(cur),
            ))
        else:
            cur = 1
            steps.append(dict(
                line=11, vars=state(),
                note='Начинаем считать заново — но не с нуля, а с единицы: сам '
                     'символ {!r} это уже цепочка длиной 1.'.format(text[pos]),
            ))
        better = cur > best
        steps.append(dict(
            line=12, vars=state(), check=better,
            note=('cur = {} больше рекорда {} — надо обновить.'.format(cur, best)
                  if better else
                  'cur = {}, а рекорд {} — обновлять нечего. Но спросили мы всё '
                  'равно, и это важнее, чем кажется.'.format(cur, best)),
        ))
        if better:
            best = cur
            steps.append(dict(
                line=13, vars=state(),
                note='Новый рекорд: {}. Обратите внимание, что он записан '
                     'внутри цепочки, а не после её обрыва.'.format(best),
            ))

    i = None
    steps.append(dict(
        line=7, vars=state(),
        note='Позиции кончились — цикл завершён.',
    ))
    steps.append(dict(
        line=14, vars=state(), out=str(best),
        note='Ответ {}. Проследите по трассе, на каком шаге best дорос до этого '
             'значения: не тогда, когда цепочка кончилась, а на её последнем '
             'символе. Поэтому цепочке и не обязательно обрываться — она может '
             'упираться прямо в конец строки.'.format(best),
    ))
    return steps


# Код, который трассирует loop-trace в уроке 8.7: проверка палиндрома двумя
# указателями. Строка на вход подаётся уже очищенной — очистку разбирал
# виджет урока 8.5. Главные кадры трассы: цикл не доходит до конца строки, а
# останавливается в середине, где указатели встречаются.
PALINDROME_CODE = [
    "s = 'заказ'          # строку уже очистили: только буквы, нижний регистр",
    'i = 0                # левый указатель',
    'j = len(s) - 1       # правый указатель',
    'ok = True',
    'while i < j:',
    '    if s[i] != s[j]:',
    '        ok = False',
    '        break        # первое же несовпадение решает всё',
    '    i = i + 1',
    '    j = j - 1',
    'print(ok)',
]


def _palindrome_trace(text='заказ'):
    """Пошаговая трасса проверки палиндрома двумя указателями."""
    steps = []
    i = None
    j = None
    ok = None

    def state():
        st = {'s': text}
        if i is not None:
            st['i'] = i
        if j is not None:
            st['j'] = j
        if ok is not None:
            st['ok'] = ok
        return st

    steps.append(dict(
        line=1, vars=state(),
        note='Очищенная строка: буквы и только буквы, все строчные. Пробелы и '
             'знаки препинания убраны заранее — иначе сравнивать нечестно.',
    ))
    i = 0
    steps.append(dict(
        line=2, vars=state(),
        note='Левый указатель стоит на первом символе {!r}.'.format(text[0]),
    ))
    j = len(text) - 1
    steps.append(dict(
        line=3, vars=state(),
        note='Правый — на последнем: {!r}. Обратите внимание на «минус один»: '
             'индексы идут с нуля, поэтому последний равен len(s) - 1 (урок '
             '8.2).'.format(text[-1]),
    ))
    ok = True
    steps.append(dict(
        line=4, vars=state(),
        note='Пока считаем строку палиндромом. Опровергнуть это может любая '
             'несовпавшая пара.',
    ))

    while True:
        go = i < j
        steps.append(dict(
            line=5, vars=state(), check=go,
            note=('i = {} левее j = {} — есть ещё непроверенная пара.'.format(i, j)
                  if go else
                  'i и j встретились на символе {!r} — он стоит ровно посередине, '
                  'и сравнивать его не с чем. Все пары уже проверены, работа '
                  'закончена, хотя цикл прошёл только полстроки.'.format(text[i])),
        ))
        if not go:
            break

        diff = text[i] != text[j]
        steps.append(dict(
            line=6, vars=state(), check=diff,
            note=('{!r} и {!r} — разные символы, дальше можно не смотреть.'.format(
                      text[i], text[j]) if diff else
                  'Крайние символы совпали: {!r} и {!r}.'.format(text[i], text[j])),
        ))
        if diff:
            ok = False
            steps.append(dict(
                line=7, vars=state(),
                note='Одной несовпавшей пары достаточно: это не палиндром.',
            ))
            steps.append(dict(
                line=8, vars=state(),
                note='break обрывает цикл — оставшиеся пары проверять бессмысленно.',
            ))
            break

        i = i + 1
        steps.append(dict(
            line=9, vars=state(),
            note='Левый указатель сдвинулся вправо, к центру.',
        ))
        j = j - 1
        steps.append(dict(
            line=10, vars=state(),
            note='Правый — влево, ему навстречу.',
        ))

    steps.append(dict(
        line=11, vars=state(), out=str(ok),
        note='Ответ {}. Сравнений вышло вдвое меньше, чем символов в строке: '
             'каждая пара проверяется один раз.'.format(ok),
    ))
    return steps


class Command(BaseCommand):
    help = "Наполняет статьи блока 8 контентом (уроки добавляются постепенно)."

    @transaction.atomic
    def handle(self, *args, **options):
        self.seed_8_1()
        self.seed_8_2()
        self.seed_8_3()
        self.seed_8_4()
        self.seed_8_5()
        self.seed_8_6()
        self.seed_8_7()
        self.stdout.write(self.style.SUCCESS('Готово: блок 8 обновлён.'))

    def seed_8_1(self):
        article = Article.objects.get(slug='8-1-stroka-kak-neizmenyaemaya-posledovatelnost')
        article.description = (
            'Строка как упорядоченная последовательность символов: индекс, '
            'len(), обход циклом. Символ — это строка длины 1, а ord() и chr() '
            'превращают буквы в числа и обратно. Почему s[0] = \'П\' падает с '
            'ошибкой, что на самом деле происходит при «изменении» строки и '
            'зачем языку такой запрет.'
        )
        article.save(update_fields=['description'])

        _replace_blocks(article, [
            dict(order=1, block_type='text', title='Букву поверх не напишешь', content=(
                'Слово набрали с ошибкой: получилось `\'привет\'` вместо '
                '`\'Привет\'`. Ошибка в одной-единственной букве, и в тетради '
                'её бы просто зачеркнули и написали поверх — на месте, не '
                'переписывая слово целиком.\n\n'
                'В программе первая буква строки доступна: прочитать её можно '
                'без всяких сложностей. А вот попытка записать на её место '
                'другую букву заканчивается ошибкой — Python отказывается '
                'наотрез.\n\n'
                'Это не мелкая придирка синтаксиса и не недоработка языка, а '
                'главное свойство типа `str`, ради которого и написан урок. '
                'Два вопроса на всё занятие: почему изменение запрещено и что '
                'же тогда происходит, когда мы «меняем» строку.'
            )),
            dict(order=2, block_type='text', title='Строка — последовательность, а не просто текст', content=(
                '> **Строка** (`str`) — упорядоченная последовательность '
                'символов. У каждого символа есть своё место в ней — '
                '**индекс**.\n\n'
                'Слово «упорядоченная» здесь не украшение: порядок — часть '
                'значения строки. `\'кот\'` и `\'ток\'` состоят из одних и тех '
                'же букв, но это две разные строки, и Python считает их '
                'неравными.\n\n'
                'Индексы нумеруются **с нуля** — как и всё остальное в Python. '
                'У строки `\'Привет\'` буква `П` стоит на месте 0, а `т` — на '
                'месте 5. Обращение записывается квадратными скобками: '
                '`s[0]`, `s[5]`.\n\n'
                'Длину строки даёт знакомая по уроку 7.3 функция `len()`. Из '
                'нумерации с нуля следует важное: последний допустимый индекс '
                'равен `len(s) - 1`, а обращение по индексу `len(s)` — это уже '
                'выход за границу и ошибка `IndexError`.\n\n'
                'Здесь мы берём ровно тот минимум, который нужен для сегодняшней '
                'темы. Обратные индексы и срезы — целиком в уроке 8.2.'
            )),
            dict(order=3, block_type='code', title='', code_language='python', content=(
                "s = 'Привет'\n"
                'print(s[0])          # П — первый символ, индекс 0\n'
                'print(s[5])          # т — последний символ\n'
                'print(len(s))        # 6 — символов в строке\n'
                'print(s[len(s) - 1]) # т — последний индекс на единицу меньше длины\n'
                '\n'
                'print(s[6])          # IndexError: string index out of range'
            )),
            dict(order=4, block_type='text', title='Отдельного типа «символ» в Python нет', content=(
                'Что именно возвращает `s[0]`? Кажется, что символ, — но '
                'отдельного типа для одиночного символа в Python не '
                'существует. `s[0]` — это **строка длины 1**: `type(s[0])` даёт '
                '`str`, `len(s[0])` даёт 1.\n\n'
                'В других языках это устроено иначе. В C и в Java есть '
                'отдельный тип `char`, и там `\'a\'` (символ) и `"a"` (строка) — '
                'принципиально разные вещи, которые даже кавычками пишутся '
                'по-разному. В Python одинарные и двойные кавычки '
                'взаимозаменяемы — мы знаем это ещё с урока 1.8, — и никакого '
                'отдельного типа под одиночный символ нет.\n\n'
                'Практическое следствие всплывёт уже через два блока: функция '
                '`ord()` принимает строку **ровно из одного символа** — ни '
                'пустую, ни из двух букв.'
            )),
            dict(order=5, block_type='text', title='Обход строки', content=(
                'Строка — **итерируемый** объект, о которых шла речь в уроке '
                '4.4. Значит, её можно поставить прямо в заголовок цикла '
                '`for`, и он выдаст символы по одному, слева направо. Это '
                'самый частый способ пройти строку целиком.\n\n'
                'Если нужен не только сам символ, но и его номер, берут '
                'привычный `range(len(text))` и обращаются к `text[i]` внутри '
                'цикла.\n\n'
                'Оба способа только **читают** строку — и с этим никаких '
                'проблем нет.'
            )),
            dict(order=6, block_type='code', title='', code_language='python', content=(
                "text = 'Привет'\n"
                '\n'
                '# по символам — когда номер не важен\n'
                'for ch in text:\n'
                "    print(ch, end=' ')      # П р и в е т\n"
                '\n'
                'print()\n'
                '\n'
                '# по индексам — когда нужен номер позиции\n'
                'for i in range(len(text)):\n'
                "    print(i, text[i])       # 0 П / 1 р / 2 и / ..."
            )),
            dict(order=7, block_type='text', title='ord() и chr(): от символа к номеру и обратно', content=(
                'В уроке 7.3 функции `ord()` и `chr()` были инструментом для '
                'разговора об устройстве Unicode: `ord()` выдаёт кодовую точку '
                'символа, `chr()` — обратно символ по номеру. Теперь они '
                'становятся рабочим инструментом.\n\n'
                'Работает это потому, что буквы алфавита лежат в таблице '
                '**подряд**, а значит, с ними можно считать:\n\n'
                '| Символы | Кодовые точки |\n'
                '|---|---|\n'
                '| `А`–`Я` | 1040–1071 |\n'
                '| `а`–`я` | 1072–1103 |\n'
                '| `A`–`Z` | 65–90 |\n'
                '| `a`–`z` | 97–122 |\n'
                '| `0`–`9` | 48–57 |\n\n'
                'Отсюда сразу два приёма, которые пригодятся не раз:\n\n'
                '- **смена регистра арифметикой.** И в кириллице, и в латинице '
                'строчная буква стоит ровно на 32 позиции дальше заглавной, '
                'поэтому `chr(ord(ch) - 32)` делает букву заглавной, а '
                '`+ 32` — строчной;\n'
                '- **цифра-символ в число.** `ord(c) - ord(\'0\')` превращает '
                'символ `\'7\'` в число 7: раз цифры идут подряд, разница '
                'кодов и есть значение цифры.\n\n'
                'И честная оговорка про букву `ё`. В таблицу её дописали '
                'отдельно, **вне** основного диапазона: `Ё` — это 1025, а '
                '`ё` — 1105. Разница между ними 80, а не 32, и правило '
                '«плюс-минус 32» на этой паре ломается. Готовые методы смены '
                'регистра, которые появятся в уроке 8.5, про такие исключения '
                'знают — а вот арифметика на кодах не знает ничего.'
            )),
            dict(order=8, block_type='code', title='', code_language='python', content=(
                "print(ord('А'), ord('а'))       # 1040 1072 — разница ровно 32\n"
                "print(ord('A'), ord('a'))       # 65 97 — и здесь тоже 32\n"
                '\n'
                "print(chr(ord('а') - 32))       # А — сделали букву заглавной\n"
                "print(chr(ord('П') + 32))       # п — и обратно, строчной\n"
                '\n'
                "print(ord('7') - ord('0'))      # 7 — из символа-цифры получили число\n"
                '\n'
                "print(ord('Ё'), ord('ё'))       # 1025 1105 — разница 80, правило не работает"
            )),
            dict(order=9, block_type='text', title='Главное: строку изменить нельзя', content=(
                'Теперь к тому, ради чего урок затевался.\n\n'
                '> Тип `str` — **неизменяемый** (immutable): у существующей '
                'строки нельзя заменить, вставить или удалить ни одного '
                'символа.\n\n'
                'Попытка присвоить что-нибудь по индексу заканчивается '
                'сообщением `TypeError: \'str\' object does not support item '
                'assignment` — «объект типа str не поддерживает присваивание по '
                'элементу». Читать `s[0]` можно, писать в `s[0]` — нельзя.\n\n'
                'Но ведь строки в программах меняются постоянно: к ним что-то '
                'дописывают, из них что-то вырезают. Как это уживается с '
                'запретом?\n\n'
                'Разгадка в том, что **все такие операции создают новую '
                'строку**, а имя переменной — всего лишь ярлык, который можно '
                'перевесить на другой объект. Запись `s = s + \'!\'` означает '
                'не «дописали восклицательный знак в конец `s`», а «собрали в '
                'памяти новую строку из старой и восклицательного знака и '
                'назвали её тем же именем `s`». Старая строка при этом '
                'осталась ровно такой, какой была; если на неё указывало ещё '
                'одно имя, там ничего не изменилось.\n\n'
                'Убедиться в этом помогает функция `id()` — она выдаёт номер, '
                'по которому объект лежит в памяти. Если после «изменения» '
                'номер стал другим, значит, объект перед нами уже не тот.'
            )),
            dict(order=10, block_type='code', title='', code_language='python', content=(
                "s = 'привет'\n"
                "s[0] = 'П'           # TypeError: 'str' object does not support item assignment\n"
                '\n'
                "# «изменение» строки — это на самом деле новая строка\n"
                "s = 'кот'\n"
                't = s                # второе имя для той же самой строки\n'
                "s = s + '!'          # собрали новую строку и перевесили на неё имя s\n"
                "print(s)             # кот!\n"
                "print(t)             # кот — старая строка не пострадала\n"
                '\n'
                "s = 'кот'\n"
                'print(id(s))         # например, 2158751223856\n'
                "s = s + '!'\n"
                'print(id(s))         # другое число — перед нами другой объект'
            )),
            dict(
                order=11, block_type='widget',
                title='Как на самом деле выглядит «замена буквы»',
                content=(
                    'Программа делает то, с чего начинался урок: превращает '
                    '«привет» в «Привет». Пройдите трассу по шагам и следите '
                    'за двумя переменными сразу. Исходная строка text не '
                    'меняется ни на одном шаге — результат строится рядом, '
                    'символ за символом.'
                ),
                widget_key='loop-trace',
                widget_config={
                    'code': CAPITALIZE_CODE,
                    'vars': ['text', 'i', 'text[i]', 'result'],
                    'steps': _capitalize_trace(),
                },
            ),
            # Иллюстрация: плоский минималистичный стиль, как в блоках 2, 5, 6, 7.
            # Две сцены рядом, разделённые вертикальной чертой, каждая
            # подписана строкой кода сверху.
            # Слева (подпись «s = 'привет'»): маленький прямоугольник-ярлык с
            # именем s, от него стрелка вправо к крупному прямоугольнику-объекту,
            # внутри которого посимвольно, по клеткам, лежит слово «привет».
            # Справа (подпись «s = 'П' + s[1:]»): тот же ярлык s, но стрелка от
            # него теперь идёт к НОВОМУ прямоугольнику со словом «Привет»;
            # старый прямоугольник «привет» никуда не делся — он нарисован
            # бледно-серым, и стрелок к нему больше нет.
            # Главный смысл картинки: старая строка не изменилась и не могла
            # измениться — построена вторая, а имя просто перевесили на неё.
            dict(order=12, block_type='image', title='', content=(
                'Слева: имя s указывает на строку «привет». Справа: после '
                '«изменения» рядом появилась новая строка «Привет», имя '
                'перевесили на неё, а исходная осталась нетронутой.'
            )),
            dict(order=13, block_type='text', title='Зачем языку такой запрет', content=(
                'Похоже на лишнее ограничение — но платят за него не зря. Вот '
                'что даёт неизменяемость.\n\n'
                '**Строку можно спокойно отдавать куда угодно.** Если значение '
                'нельзя изменить в принципе, то и испортить его со стороны '
                'невозможно: получив строку, ни один кусок программы не сможет '
                'переписать её так, чтобы это заметили все остальные. Целый '
                'класс ошибок вида «кто-то поменял мои данные, а я и не знал» '
                'просто не существует.\n\n'
                '**Одинаковые строки можно не хранить дважды.** Раз строка '
                'никогда не изменится, интерпретатор вправе держать один '
                'экземпляр повторяющегося текста и раздавать ссылку на него — '
                'память экономится сама собой, и ничего при этом не '
                'сломается.\n\n'
                '**Строка годится в качестве ключа.** Об этом подробно пойдёт '
                'речь в блоке 13, а пока достаточно идеи: чтобы быстро искать '
                'значение по ключу, ключ должен оставаться самим собой. '
                'Изменяемое значение для этого не подходит — а строка подходит '
                'идеально, поэтому ключами почти всегда служат именно '
                'строки.\n\n'
                'Решение это не экзотическое: в Java и C# строки тоже '
                'неизменяемы. А вот в C строка — обычный массив символов, '
                'править который на месте разрешено, и там правки в чужую '
                'строку — источник классических и очень неприятных ошибок.'
            )),
            dict(order=14, block_type='text', title='Цена неизменяемости', content=(
                'Обратная сторона у запрета тоже есть. Раз каждая склейка '
                'создаёт новую строку, то накопление результата в цикле — '
                '`result = result + ch` — каждый раз копирует всё уже '
                'накопленное заново. На слове из шести букв этого не заметит '
                'никто; на строке в миллион символов разница становится '
                'очень даже ощутимой.\n\n'
                'Посчитать её аккуратно мы сможем в блоке 10, когда появится '
                'язык для разговора о скорости алгоритмов, а правильный '
                'инструмент для сборки длинных строк — метод `join()` — '
                'разберём в уроке 8.6. Пока достаточно запомнить сам факт: '
                'склейка строк внутри длинного цикла — место, где стоит '
                'насторожиться.'
            )),
            dict(order=15, block_type='text', title='Итог и мостик к 8.2', content=(
                'Что стоит вынести из урока:\n\n'
                '- строка — **упорядоченная последовательность символов**; '
                'у каждого символа есть индекс, нумерация с нуля, длина — '
                '`len()`, последний индекс `len(s) - 1`, дальше `IndexError`;\n'
                '- отдельного типа «символ» нет: `s[0]` — это строка длины 1;\n'
                '- строка итерируема: `for ch in text` даёт символы по одному, '
                '`range(len(text))` — их номера;\n'
                '- `ord()` и `chr()` переводят символ в кодовую точку и '
                'обратно; буквы алфавита идут подряд, поэтому регистр '
                'меняется прибавлением 32, а цифра-символ превращается в '
                'число через `ord(c) - ord(\'0\')`; исключение — пара '
                '`Ё`/`ё`;\n'
                '- `str` **неизменяем**: `s[0] = ...` — это `TypeError`. Любое '
                '«изменение» строки создаёт новую, а имя переменной лишь '
                'перевешивается на неё.\n\n'
                'Вот и ответ на вопрос из начала урока: букву поверх не '
                'пишут — слово переписывают целиком. Просто делает это Python '
                'сам, и со стороны кажется, будто строка изменилась.\n\n'
                'А раз править строку нельзя, зато читать можно сколько '
                'угодно, — читать надо научиться как следует. Пока мы умеем '
                'доставать по одному символу за раз, и это неудобно: чтобы '
                'взять из даты `\'2026-08-01\'` год, придётся склеивать четыре '
                'символа вручную. В уроке 8.2 разберём обратную индексацию и '
                '**срезы** — способ достать любой кусок строки одной короткой '
                'записью.'
            )),
        ])

        quiz = _self_check(
            slug='self-check-stroka-neizmenyaemaya-posledovatelnost',
            title='Самопроверка: строка как неизменяемая последовательность',
            description='Три коротких вопроса по теме урока.',
            questions=[
                dict(
                    type='choice',
                    text=(
                        "Выполнили s = 'привет', а затем s[0] = 'П'. Что произойдёт?"
                    ),
                    choices=[
                        ('Ошибка TypeError: строку нельзя изменить по индексу', True),
                        ('Первая буква станет заглавной — получится «Привет»', False),
                        ('Ошибки не будет, но и строка не изменится', False),
                        ('Создастся новая строка «Привет», а старая удалится', False),
                    ],
                ),
                dict(
                    type='choice',
                    text=(
                        "Выполнили s = 'кот', затем t = s, затем s = s + '!'. "
                        'Что теперь хранится в t?'
                    ),
                    choices=[
                        ("'кот' — старая строка не менялась, имя s просто "
                         'перевесили на новую', True),
                        ("'кот!' — имя t указывает на ту же строку, что и s", False),
                        ('Пустая строка — значение перешло к s', False),
                        ('Ошибка: менять строку, на которую ссылаются два '
                         'имени, нельзя', False),
                    ],
                ),
                dict(
                    type='text',
                    text=(
                        "Известно, что ord('0') равен 48. Чему равно значение "
                        "выражения ord('7') - ord('0')? Впишите только число."
                    ),
                    correct_text_answer='7',
                ),
            ],
        )
        ArticleQuiz.objects.get_or_create(
            article=article, quiz=quiz,
            defaults={'label': 'Проверь себя', 'order': 1},
        )

    def seed_8_2(self):
        article = Article.objects.get(slug='8-2-indeksatsiya-i-srezy')
        article.description = (
            'Отрицательные индексы: счёт с конца, s[-1] вместо s[len(s) - 1]. '
            'Срез s[start:stop:step]: почему правая граница не включается, что '
            'подставляется вместо пропущенных границ, почему срез за границей '
            'строки не падает с ошибкой и как работает отрицательный шаг.'
        )
        article.save(update_fields=['description'])

        _replace_blocks(article, [
            dict(order=1, block_type='text', title='Год из даты', content=(
                'Дата записана строкой: `\'2026-08-01\'`. Задача простая — '
                'достать из неё отдельно год, месяц и день.\n\n'
                'Тем, что мы умеем после урока 8.1, это делается так: год — '
                'четыре обращения по индексу и три склейки, '
                '`s[0] + s[1] + s[2] + s[3]`. Работает, но читать такое '
                'невозможно, а если понадобится не год, а месяц, всё придётся '
                'переписывать заново.\n\n'
                'Второе неудобство из того же ряда: чтобы взять **последний** '
                'символ строки, приходится каждый раз писать `s[len(s) - 1]` — '
                'длинно, и длина строки нас, вообще-то, не интересовала.\n\n'
                'Обе неприятности решаются двумя приёмами, и им посвящён урок: '
                '**отрицательные индексы** — счёт позиций с конца, и '
                '**срезы** — способ достать целый кусок строки одной записью.'
            )),
            dict(order=2, block_type='text', title='Отрицательные индексы: счёт с конца', content=(
                '> Отрицательный индекс отсчитывает позицию **с конца** '
                'строки: `s[-1]` — последний символ, `s[-2]` — '
                'предпоследний, и так далее до `s[-len(s)]` — первого.\n\n'
                'Ничего нового здесь на самом деле не появилось: `s[-k]` — это '
                'ровно то же место, что `s[len(s) - k]`, просто записанное '
                'короче.\n\n'
                'Почему счёт с конца начинается с −1, а не с −0? Ноль уже '
                'занят: это первый символ. «Минус ноль» ничем от него не '
                'отличался бы, поэтому нумерация с конца стартует с '
                'единицы.\n\n'
                'Границы работают симметрично тому, что было в прошлом уроке. '
                'У строки длины 6 допустимы индексы от −6 до 5; `s[-7]` — это '
                'уже выход за границу и `IndexError`.\n\n'
                'Получается, у каждого символа два имени — прямое и с конца:\n\n'
                '| символ | П | р | и | в | е | т |\n'
                '|---|---|---|---|---|---|---|\n'
                '| индекс | 0 | 1 | 2 | 3 | 4 | 5 |\n'
                '| с конца | −6 | −5 | −4 | −3 | −2 | −1 |'
            )),
            dict(order=3, block_type='code', title='', code_language='python', content=(
                "s = 'Привет'\n"
                '\n'
                'print(s[-1])          # т — последний символ\n'
                'print(s[-2])          # е — предпоследний\n'
                'print(s[-6])          # П — он же s[0]\n'
                'print(s[len(s) - 1])  # т — то же, что s[-1], только длиннее\n'
                '\n'
                'print(s[-7])          # IndexError: string index out of range'
            )),
            # Иллюстрация: плоский минималистичный стиль, как в блоках 2, 5–7.
            # Одна строка «Привет», разложенная по шести клеткам в ряд.
            # НАД каждой клеткой — число прямого индекса (0, 1, 2, 3, 4, 5),
            # ПОД каждой клеткой — отрицательного (−6, −5, −4, −3, −2, −1).
            # Обе линейки одинаково выровнены по клеткам; полезно тонкими
            # вертикальными направляющими показать, что 2 и −4 указывают на
            # одну и ту же клетку «и».
            # Главный смысл картинки: это не два разных набора позиций, а два
            # способа назвать одно и то же место.
            dict(order=4, block_type='image', title='', content=(
                'Строка «Привет» с двумя линейками номеров: сверху прямые '
                'индексы 0–5, снизу отрицательные −6…−1. Обе линейки указывают '
                'на одни и те же символы.'
            )),
            dict(order=5, block_type='text', title='Срез: кусок строки одной записью', content=(
                '> **Срез** `s[start:stop]` — новая строка из символов, '
                'начиная с позиции `start` **включительно** и до позиции '
                '`stop` **не включая**.\n\n'
                'Главное, что придётся запомнить: правая граница в срез не '
                'входит. Поначалу это раздражает, но это не каприз языка — из '
                'такой договорённости следуют два свойства, которыми потом '
                'пользуешься постоянно:\n\n'
                '- длина среза равна `stop - start` (когда обе границы внутри '
                'строки, а шаг единичный) — считать ничего не надо;\n'
                '- `s[:i] + s[i:]` при любом `i` даёт исходную строку — куски '
                'стыкуются без нахлёста и без дырки.\n\n'
                'Вернёмся к дате. У строки `\'2026-08-01\'` длина 10, год стоит '
                'на позициях 0–3, месяц — на 5–6, день — на 8–9. Значит, год — '
                'это `s[0:4]`, месяц — `s[5:7]`, день — `s[8:10]`. Дефисы на '
                'позициях 4 и 7 не попадают ни в один срез сами собой.'
            )),
            dict(order=6, block_type='code', title='', code_language='python', content=(
                "s = '2026-08-01'      # len(s) == 10\n"
                '\n'
                'print(s[0:4])         # 2026 — символы 0, 1, 2, 3\n'
                'print(s[5:7])         # 08 — символы 5 и 6\n'
                'print(s[8:10])        # 01 — символы 8 и 9\n'
                '\n'
                'print(s[:4] + s[4:])  # 2026-08-01 — куски стыкуются без нахлёста'
            )),
            dict(order=7, block_type='text', title='Пропущенные границы', content=(
                'Любую границу можно не писать — тогда Python сам подставит '
                'край строки: `s[:n]` — от начала, `s[n:]` — до конца, '
                '`s[:]` — вся строка целиком. Дату это делает заметно короче: '
                'год `s[:4]`, день `s[8:]`.\n\n'
                'И отдельно — важное отличие среза от индекса.\n\n'
                '> **Срез никогда не падает с ошибкой из-за границ.** Индексу '
                'нужно, чтобы символ существовал; срезу — нет, он просто берёт '
                'то, что попало в диапазон.\n\n'
                'Поэтому `s[100:200]` у короткой строки — не `IndexError`, а '
                'пустая строка `\'\'`, а `s[:1000]` — вся строка. Практическое '
                'следствие: если нужны «первые три символа строки, которая '
                'может оказаться и короче» — срез справится сам, проверять '
                'длину заранее не нужно.'
            )),
            dict(order=8, block_type='code', title='', code_language='python', content=(
                "s = '2026-08-01'\n"
                '\n'
                'print(s[:4])       # 2026 — от начала\n'
                'print(s[8:])       # 01 — до конца\n'
                'print(s[:])        # 2026-08-01 — вся строка\n'
                '\n'
                '# срез за границей строки — не ошибка, в отличие от индекса\n'
                "print(s[100:200])  # '' — пустая строка\n"
                'print(s[:1000])    # 2026-08-01 — взял всё, что было\n'
                'print(s[100])      # IndexError: string index out of range'
            )),
            dict(order=9, block_type='text', title='Третий параметр: шаг', content=(
                'Полная форма среза — `s[start:stop:step]`.\n\n'
                '> **Шаг** `step` — через сколько позиций брать следующий '
                'символ. По умолчанию он равен 1, то есть символы берутся '
                'подряд.\n\n'
                'Отсюда `s[::2]` — каждый второй символ начиная с нулевого, '
                'а `s[1::2]` — каждый второй начиная с первого.\n\n'
                'Шаг может быть и **отрицательным** — тогда идём справа '
                'налево. Вместе с ним переворачивается смысл границ: `start` '
                'оказывается правее, чем `stop`, а пропущенные границы '
                'подставляются наоборот — `start` становится концом строки, '
                '`stop` уходит за её начало. Так получается самая известная '
                'идиома Python: `s[::-1]` — строка задом наперёд.\n\n'
                'И сразу ловушка, на которой спотыкаются все. Правило «правая '
                'граница не включается» при отрицательном шаге никуда не '
                'девается. Поэтому `s[5:0:-1]` дойдёт до позиции 1 и '
                'остановится — нулевой символ в срез не попадёт. Чтобы дойти '
                'до самого начала, границу надо **опустить**: `s[5::-1]`. '
                'Именно поэтому разворот строки пишут как `s[::-1]`, а не '
                'через явные числа.'
            )),
            dict(order=10, block_type='code', title='', code_language='python', content=(
                "s = 'Привет'\n"
                '\n'
                'print(s[::2])    # Пие — каждый второй начиная с нулевого\n'
                'print(s[1::2])   # рвт — каждый второй начиная с первого\n'
                'print(s[1:5:2])  # рв — от 1 до 5 (не включая), через один\n'
                '\n'
                'print(s[::-1])   # тевирП — вся строка задом наперёд\n'
                'print(s[5::-1])  # тевирП — то же самое, границы записаны явно\n'
                'print(s[5:0:-1]) # тевир — ловушка: позиция 0 не включается'
            )),
            dict(
                order=11, block_type='widget',
                title='Соберите срез сами',
                content=(
                    'Линейка индексов и живой срез над одной и той же строкой. '
                    'Меняйте `start`, `stop` и `step` — попавшие символы '
                    'подсвечиваются и нумеруются в том порядке, в каком '
                    'окажутся в результате, а клетка на позиции `stop` обведена '
                    'пунктиром: она не включается. Кнопка «пусто» у каждой '
                    'границы — это двоеточие без числа. Наведите на любой '
                    'символ, чтобы узнать оба его индекса и причину, по которой '
                    'он попал или не попал в срез.'
                ),
                widget_key='slice-ruler',
                widget_config={
                    'text': '2026-08-01',
                    'start': None,
                    'stop': 4,
                    'step': None,
                    'presets': [
                        {'title': 'год s[:4]', 'text': '2026-08-01', 'stop': 4,
                         'hint': 'start опущен — берём с начала строки'},
                        {'title': 'месяц s[5:7]', 'text': '2026-08-01', 'start': 5, 'stop': 7,
                         'hint': 'позиции 5 и 6; седьмая уже не входит'},
                        {'title': 'день s[8:]', 'text': '2026-08-01', 'start': 8,
                         'hint': 'stop опущен — берём до конца строки'},
                        {'title': 'без последнего s[:-1]', 'text': 'Привет', 'stop': -1,
                         'hint': 'граница с конца: −1 — это позиция 5'},
                        {'title': 'каждый второй s[::2]', 'text': 'Привет', 'step': 2,
                         'hint': 'позиции 0, 2, 4'},
                        {'title': 'задом наперёд s[::-1]', 'text': 'Привет', 'step': -1,
                         'hint': 'отрицательный шаг — идём справа налево'},
                        {'title': 'ловушка s[5:0:-1]', 'text': 'Привет', 'start': 5,
                         'stop': 0, 'step': -1,
                         'hint': 'позиция 0 не включается — первая буква потеряна'},
                        {'title': 'за границей s[100:200]', 'text': 'Привет', 'start': 100,
                         'stop': 200, 'hint': 'не ошибка, а пустая строка'},
                    ],
                },
            ),
            dict(
                order=12, block_type='widget',
                title='Что срез делает на самом деле',
                content=(
                    'Срез — не магия, а обычный проход по позициям. Программа '
                    'ниже делает руками ровно то же, что `s[1:5:2]`: начинает с '
                    '`start`, каждый раз прибавляет `step` и останавливается, '
                    'не дойдя до `stop`. Пройдите трассу по шагам и обратите '
                    'внимание на последнюю проверку условия — там видно, почему '
                    'символ на позиции `stop` в результат не попадает.'
                ),
                widget_key='loop-trace',
                widget_config={
                    'code': SLICE_CODE,
                    'vars': ['s', 'i', 's[i]', 'result'],
                    'steps': _slice_trace(),
                },
            ),
            dict(order=13, block_type='text', title='Срез — это всегда новая строка', content=(
                'Раз строку изменить нельзя (об этом весь урок 8.1), то срез '
                'ничего и не вырезает из исходной — он **строит рядом новую '
                'строку**. Запись `t = s[1:]` не укоротила `s`; чтобы «убрать» '
                'первый символ из самой `s`, придётся перевесить имя: '
                '`s = s[1:]` — и это снова новая строка, а не правка старой.\n\n'
                'По этой же причине в Python нет отдельной операции «удалить '
                'символ из строки» — вместо неё собирают новую строку из двух '
                'срезов. И вставки нет — она устроена так же:\n\n'
                '- удалить символ на позиции `i`: `s[:i] + s[i+1:]`;\n'
                '- вставить символ перед позицией `i`: `s[:i] + \'X\' + s[i:]`.\n\n'
                'Обе записи опираются ровно на то свойство полуинтервала, с '
                'которого мы начинали: куски стыкуются без нахлёста и без '
                'потерь.'
            )),
            dict(order=14, block_type='code', title='', code_language='python', content=(
                "s = 'Привет'\n"
                't = s[1:]\n'
                'print(s, t)          # Привет ривет — исходная строка цела\n'
                '\n'
                "# «удаление» символа на позиции 3 — это склейка двух срезов\n"
                "print(s[:3] + s[4:])  # Приет — буквы «в» больше нет\n"
                '\n'
                "# и «вставка» устроена так же\n"
                "print(s[:3] + '!' + s[3:])  # При!вет"
            )),
            dict(order=15, block_type='text', title='Шпаргалка типовых срезов', content=(
                'Эти записи встречаются так часто, что их проще запомнить '
                'целиком, чем каждый раз выводить заново:\n\n'
                '| Что нужно | Запись |\n'
                '|---|---|\n'
                '| последний символ | `s[-1]` |\n'
                '| всё, кроме последнего символа | `s[:-1]` |\n'
                '| первые `n` символов | `s[:n]` |\n'
                '| последние `n` символов | `s[-n:]` |\n'
                '| без первого и последнего | `s[1:-1]` |\n'
                '| каждый второй символ | `s[::2]` |\n'
                '| строка задом наперёд | `s[::-1]` |\n\n'
                'Последняя строка таблицы стоит дороже, чем кажется. '
                'Палиндром — слово, которое читается одинаково в обе стороны, — '
                'проверяется теперь целиком одним сравнением: `s == s[::-1]`. '
                'Подробно за такие задачи возьмёмся в уроке 8.7.'
            )),
            dict(order=16, block_type='text', title='Итог и мостик к 8.3', content=(
                'Что стоит вынести из урока:\n\n'
                '- **отрицательный индекс** считает позиции с конца: `s[-1]` — '
                'последний символ, `s[-k]` — то же место, что `s[len(s) - k]`; '
                'выход за границу — `IndexError`;\n'
                '- **срез** `s[start:stop]` берёт `start` включительно, а '
                '`stop` — не включая; отсюда длина `stop - start` и склейка '
                '`s[:i] + s[i:] == s`;\n'
                '- границы можно опускать: `s[:n]`, `s[n:]`, `s[:]`;\n'
                '- срез **не падает** при выходе за границы строки — в отличие '
                'от индекса, он просто вернёт меньше символов или пустую '
                'строку;\n'
                '- третий параметр — **шаг**; отрицательный шаг разворачивает '
                'направление обхода, `s[::-1]` даёт строку задом наперёд, а '
                'правая граница не включается и здесь;\n'
                '- срез всегда создаёт **новую** строку, исходная остаётся '
                'нетронутой.\n\n'
                'Вот и ответ на вопрос из начала урока: год из даты — это '
                '`s[:4]`, и никакой склейки по одному символу. А последний '
                'символ — `s[-1]`, и длина строки для этого не нужна.\n\n'
                'Читать строку мы теперь умеем как следует. Дальше начинаются '
                'действия над строками целиком: склеить две в одну, размножить '
                'повторением, проверить, есть ли внутри нужный кусок. Об этом — '
                'урок 8.3.'
            )),
        ])

        quiz = _self_check(
            slug='self-check-indeksatsiya-i-srezy',
            title='Самопроверка: индексация и срезы',
            description='Три коротких вопроса по теме урока.',
            questions=[
                dict(
                    type='choice',
                    text="`s = 'Привет'`. Что вернёт `s[-2]`?",
                    choices=[
                        ("'е' — второй символ с конца", True),
                        ("'т' — последний символ", False),
                        ("'р' — второй символ с начала", False),
                        ('Ошибку: отрицательных индексов не бывает', False),
                    ],
                ),
                dict(
                    type='choice',
                    text=(
                        's — строка из 6 символов. Что произойдёт при '
                        'вычислении s[100:200]?'
                    ),
                    choices=[
                        ('Получится пустая строка: срез за границами не ошибка', True),
                        ('IndexError: таких позиций в строке нет', False),
                        ('Вернётся вся строка целиком', False),
                        ('Вернутся последние символы строки', False),
                    ],
                ),
                dict(
                    type='text',
                    text=(
                        "`s = '2026-08-01'`. Сколько символов в срезе "
                        '`s[5:7]`? Впишите только число.'
                    ),
                    correct_text_answer='2',
                ),
            ],
        )
        ArticleQuiz.objects.get_or_create(
            article=article, quiz=quiz,
            defaults={'label': 'Проверь себя', 'order': 1},
        )

    def seed_8_3(self):
        article = Article.objects.get(slug='8-3-operatsii-so-strokami')
        article.description = (
            '+ и * уже знакомы по уроку 1.8 — здесь смотрим на них после '
            'разговора о неизменяемости: обе операции строят новую строку, '
            'длины складываются и умножаются, а ширину можно взять через '
            'len(). Новое — оператор in: что такое подстрока, чем in '
            'отличается от for ... in и какой перебор позиций за ним прячется. '
            'Плюс сравнение строк на равенство и по порядку кодов.'
        )
        article.save(update_fields=['description'])

        _replace_blocks(article, [
            dict(order=1, block_type='text', title='Есть ли внутри такой кусок', content=(
                'Три задачи на оформление вывода и проверку введённого: '
                'приклеить имя к приветствию, подчеркнуть заголовок линией '
                '**ровно по его ширине** и выяснить, есть ли в введённом '
                'адресе почты собака.\n\n'
                'Первое мы умеем с урока 1.8 — там `+` склеивал строки, а '
                '`*` размножал. Второе умеем почти: в 1.8 линия была из '
                'двадцати дефисов, вбитых числом, а ширина заголовка заранее '
                'не известна. А третья задача не решается ничем из '
                'пройденного: сравнивать искомый кусок с каждым местом строки '
                'вручную — это цикл на пол-экрана.\n\n'
                'Поэтому урок устроен так: одним блоком освежаем `+` и `*` — '
                'но уже зная про неизменяемость строк, про `len()` и срезы, '
                'отчего в обеих операциях видно то, чего в 1.8 видно не было, — '
                'и дальше занимаемся третьей операцией, проверкой вхождения.'
            )),
            dict(order=2, block_type='text', title='+ и * после уроков 8.1 и 8.2', content=(
                'Обе операции знакомы: `a + b` склеивает строки в одну '
                '(**конкатенация**), `s * n` повторяет строку `n` раз подряд '
                '(**дублирование**). Складывать строку с числом по-прежнему '
                'нельзя, для этого есть `str()` — всё это разбиралось в уроке '
                '1.8.\n\n'
                'Что к этому добавляют два последних урока:\n\n'
                '- **обе операции создают новую строку.** В 1.8 это было '
                'неважно, а после урока 8.1 — важно: `+` ничего не дописывает '
                'в существующую строку, а `*` ничего не размножает на месте. '
                'Обе строят результат рядом, исходные строки остаются '
                'нетронутыми. Знакомое `s = s + \'!\'` означает «собрали новую '
                'строку и перевесили на неё имя `s`»;\n'
                '- **длины считаются заранее.** `len(a + b)` всегда равно '
                '`len(a) + len(b)`, а `len(s * n)` — `len(s) * n`. Символы не '
                'появляются и не исчезают;\n'
                '- **пустая строка ничего не меняет.** `s + \'\'` — это тот же '
                '`s`, поэтому `\'\'` — естественная заготовка накопителя, с '
                'которой начинались циклы сборки в уроках 8.1 и 8.2;\n'
                '- **ноль и отрицательное число дают пустую строку.** '
                '`\'ab\' * 0` — это `\'\'`, и `\'ab\' * -3` — тоже `\'\'`, без '
                'всякой ошибки. Проверять «а вдруг число меньше нуля» перед '
                'дублированием не нужно;\n'
                '- **ширину можно взять из самой строки.** `\'=\' * len(title)` — '
                'линия ровно по длине заголовка, какой бы он ни был. В 1.8 '
                'такую запись было не из чего собрать: `len()` появился только '
                'в 8.1.'
            )),
            dict(order=3, block_type='code', title='', code_language='python', content=(
                "a = 'Аня'\n"
                "b = 'Иванова'\n"
                '\n'
                'print(len(a + b), len(a) + len(b))  # 10 10 — символы никуда не деваются\n'
                "print(a + '')                       # Аня — пустая строка ничего не меняет\n"
                '\n'
                "print('ab' * 0)                     # пустая строка\n"
                "print('ab' * -3)                    # тоже пустая — и это не ошибка\n"
                "print(len('ab' * 4))                # 8 — длина умножается\n"
                '\n'
                "title = input('Заголовок: ')\n"
                'print(title)\n'
                "print('=' * len(title))             # линия ровно по ширине заголовка\n"
                '\n'
                "s = 'Привет'\n"
                'print(s[:3] + s[4:])                # Приет — «удаление» это склейка срезов\n'
                '\n'
                'for i in range(1, 6):\n'
                "    print(' ' * (5 - i) + '*' * i)  # пирамидка без сборки по символу"
            )),
            dict(order=4, block_type='text', title='Оператор in: есть ли внутри такой кусок', content=(
                'Третья задача из начала урока. Формально искомый «кусок» '
                'называется так:\n\n'
                '> **Подстрока** — любой непрерывный кусок строки, то есть '
                'любой её срез с единичным шагом. `\'фор\'` — подстрока строки '
                '`\'информатика\'`, а `\'фока\'` — нет: буквы есть, но они не '
                'идут подряд.\n\n'
                'Проверяется вхождение оператором **`in`**:\n\n'
                '> `sub in s` — истина, если строка `sub` встречается внутри '
                '`s` хотя бы один раз, и ложь, если не встречается.\n\n'
                'Результат — логическое значение `True` или `False` из блока '
                '3, поэтому `in` ставят прямо в условие `if`, соединяют с '
                '`and`/`or`, присваивают в переменную. Есть и парный оператор '
                '`not in` — читается «не входит» и означает то же самое с '
                'обратным ответом.\n\n'
                'Три вещи, о которые спотыкаются:\n\n'
                '- **регистр важен.** `\'кот\' in \'Кот учёный\'` — ложь: `К` и '
                '`к` — разные символы с разными кодовыми точками (урок 8.1). '
                'Приводить строки к одному регистру научимся в уроке 8.5;\n'
                '- **пустая строка входит в любую.** `\'\' in s` — всегда '
                'истина, в том числе для пустой `s`. Это не курьёз, а '
                'следствие определения: пустой кусок есть в любом месте любой '
                'строки;\n'
                '- **проверка одного символа — частный случай.** '
                '`\'@\' in email` — та же самая операция, просто подстрока '
                'длины 1.\n\n'
                'И отдельно — про то же слово в другом месте. В заголовке '
                'цикла (`for ch in text` из урока 8.1) `in` ничего не '
                'проверяет: там оно часть синтаксиса `for` и означает '
                '«перебирай по одному». Одно слово в двух ролях, различает их '
                'контекст: `in` внутри выражения даёт ответ да/нет, `in` в '
                'строке с `for` — перебирает.'
            )),
            dict(order=5, block_type='code', title='', code_language='python', content=(
                "text = 'информатика'\n"
                '\n'
                "print('фор' in text)          # True — буквы идут подряд\n"
                "print('фока' in text)         # False — буквы есть, но не подряд\n"
                "print('кот' in 'Кот учёный')  # False — регистр важен\n"
                "print('' in text)             # True — пустая строка входит в любую\n"
                '\n'
                "email = input('Почта: ')\n"
                "if '@' in email:\n"
                "    print('Похоже на адрес')\n"
                'else:\n'
                "    print('Собаки нет — это не адрес')\n"
                '\n'
                "log = 'всё прошло успешно'\n"
                "print('ошибка' not in log)    # True"
            )),
            dict(order=6, block_type='text', title='Сравнение строк: == и порядок по кодам', content=(
                'Сравнение `==` мы уже применяли не задумываясь — в проверке '
                'палиндрома `s == s[::-1]` из урока 8.2. Стоит проговорить, '
                'как оно устроено.\n\n'
                '> Две строки **равны**, если у них одинаковая длина и '
                'совпадают все символы по порядку.\n\n'
                'Никакой «похожести» здесь нет: `\'Кот\'` и `\'кот\'` не равны, '
                '`\'кот \'` с пробелом на конце и `\'кот\'` — тоже.\n\n'
                'Строки можно сравнивать и на «больше-меньше» — знаками `<`, '
                '`>`, `<=`, `>=`. Сравнение идёт слева направо до первого '
                'расхождения, а расходящиеся символы сравниваются по своим '
                'кодовым точкам — тем самым, что выдаёт `ord()` из урока 8.1. '
                'Если одна строка оказалась началом другой, короткая считается '
                'меньшей: `\'кот\' < \'котёнок\'`.\n\n'
                'Отсюда `\'а\' < \'б\'` — буквы алфавита лежат в таблице '
                'подряд. Но отсюда же и `\'Я\' < \'а\'`: все заглавные '
                'кириллические буквы стоят в таблице раньше строчных '
                '(1040–1071 против 1072–1103). Значит, порядок получается не '
                'совсем словарный — сначала все слова с заглавной буквы, потом '
                'все со строчной. Помнить об этом придётся, когда в блоке 11 '
                'дойдёт дело до сортировки.'
            )),
            dict(order=7, block_type='code', title='', code_language='python', content=(
                "print('кот' == 'кот')       # True\n"
                "print('Кот' == 'кот')       # False — регистр\n"
                "print('кот ' == 'кот')      # False — пробел тоже символ\n"
                '\n'
                "print('а' < 'б')            # True — 1072 < 1073\n"
                "print('Я' < 'а')            # True — 1071 < 1072, заглавные идут раньше\n"
                "print('кот' < 'котёнок')    # True — короткая строка считается меньшей"
            )),
            dict(order=8, block_type='text', title='Что in делает на самом деле', content=(
                '`in` не заглядывает в строку волшебным образом — он '
                'перебирает позиции. Приложить искомый кусок к началу строки и '
                'сравнить; не совпало — сдвинуть на один символ вправо и '
                'сравнить снова; так до конца.\n\n'
                'Каждое «сравнить» — это сравнение срезов из урока 8.2 тем '
                'самым `==`, о котором шла речь выше: берём '
                '`text[i:i + len(sub)]` — кусок такой же длины, что и '
                'искомый, — и проверяем на равенство с `sub`. Как только '
                'совпало, ответ найден и дальше идти незачем: срабатывает '
                '`break` из урока 4.5.\n\n'
                'Отдельного внимания стоит граница перебора. Последняя '
                'позиция, на которой ещё имеет смысл прикладывать кусок, — это '
                '`len(text) - len(sub)`: дальше подстрока просто не '
                'поместится, справа не хватит символов. Если искомый кусок '
                'длиннее самой строки, перебор не сделает ни одного шага и '
                'честно ответит «нет».\n\n'
                'Внутри Python это устроено хитрее и работает быстрее, но '
                'отвечает на тот же вопрос и тем же способом. И вот что важно '
                'запомнить: **`in` отвечает только «да» или «нет»**. Он не '
                'говорит, на какой позиции нашлось и сколько раз встретилось.'
            )),
            # Иллюстрация: плоский минималистичный стиль, как в блоках 2, 5–8.
            # Сверху — строка «информатика», разложенная по клеткам, с номерами
            # позиций 0–10.
            # Ниже — несколько рядов, по одному на шаг перебора: в каждом ряду
            # рамка-«окно» шириной ровно 3 клетки, стоящая на позициях 0, 1,
            # 2 … и подписанная своим содержимым («инф», «нфо», «фор», …).
            # Несовпавшие окна — бледные, с крестиком справа; окно на позиции 5
            # («мат») — выделено цветом, с галочкой, и ряды ниже него не
            # рисуются вовсе (сработал break).
            # Главный смысл картинки: никакой магии — окно просто едет вправо
            # на один символ за шаг.
            dict(order=9, block_type='image', title='', content=(
                'Поиск подстроки «мат» в строке «информатика»: окно длиной три '
                'символа сдвигается слева направо, пока его содержимое не '
                'совпадёт с искомым куском.'
            )),
            dict(
                order=10, block_type='widget',
                title='Как ищется подстрока',
                content=(
                    'Программа делает руками то же, что `\'мат\' in '
                    '\'информатика\'`: прикладывает кусок к каждой позиции и '
                    'сравнивает срез с искомым. Пройдите трассу по шагам и '
                    'следите за строкой `text[i:i+3]` — это и есть окно, '
                    'которое едет вправо. Обратите внимание на две вещи: где '
                    'перебор останавливается после совпадения и почему `i` так '
                    'и не доходит до конца строки.'
                ),
                widget_key='loop-trace',
                widget_config={
                    'code': SEARCH_CODE,
                    'vars': ['text', 'sub', 'i', 'text[i:i+3]', 'found'],
                    'steps': _substring_trace(),
                },
            ),
            dict(order=11, block_type='text', title='Итог и мостик к 8.4', content=(
                'Что стоит вынести из урока:\n\n'
                '- `+` и `*` знакомы с урока 1.8, но обе операции **создают '
                'новую строку** — исходные не меняются, потому что `str` '
                'неизменяем;\n'
                '- длины предсказуемы: `len(a + b)` = `len(a) + len(b)`, '
                '`len(s * n)` = `len(s) * n`; `s + \'\'` ничего не меняет, '
                '`s * 0` и `s * -3` дают пустую строку;\n'
                '- ширину берут из самой строки: `\'-\' * len(title)` '
                'подстраивается под любой заголовок;\n'
                '- **подстрока** — непрерывный кусок строки; `sub in s` '
                'отвечает `True`/`False`, есть парный `not in`; регистр важен, '
                'пустая строка входит в любую, символ — частный случай;\n'
                '- строки сравниваются на равенство посимвольно, а на '
                '«больше-меньше» — по кодовым точкам до первого расхождения, '
                'поэтому `\'Я\' < \'а\'`;\n'
                '- за `in` прячется обычный перебор позиций со сравнением '
                'срезов, и отвечает он только «да/нет».\n\n'
                'Вот и три задачи из начала урока: приветствие собирается '
                'конкатенацией, линия — дублированием по `len()`, собака в '
                'адресе ищется одним `in`.\n\n'
                'Но `in` — инструмент с одним делением на шкале. Он скажет, '
                'что слово в тексте есть, и промолчит о том, где именно и '
                'сколько раз, — а нужно чаще всего именно это: заменить, '
                'посчитать, вырезать по найденному месту. В уроке 8.4 '
                'появятся методы `find()`, `rfind()`, `count()` и `replace()`, '
                'которые отвечают на все эти вопросы.'
            )),
        ])

        quiz = _self_check(
            slug='self-check-operatsii-so-strokami',
            title='Самопроверка: операции со строками',
            description='Три коротких вопроса по теме урока.',
            questions=[
                dict(
                    type='choice',
                    text="Что вернёт выражение 'фока' in 'информатика'?",
                    choices=[
                        ('False — эти буквы есть, но не идут подряд, а '
                         'подстрока — непрерывный кусок', True),
                        ('True — все четыре буквы в строке присутствуют', False),
                        ('True — порядок букв для in не важен', False),
                        ('TypeError — in проверяет только один символ', False),
                    ],
                ),
                dict(
                    type='choice',
                    text="Что вернёт выражение 'кот' in 'Кот учёный'?",
                    choices=[
                        ('False — регистр важен, «К» и «к» — разные символы', True),
                        ('True — буквы к, о, т идут подряд', False),
                        ('True — Python не различает заглавные и строчные буквы', False),
                        ('False — потому что перед «Кот» нет пробела', False),
                    ],
                ),
                dict(
                    type='text',
                    text=(
                        "Сколько символов будет в строке, которую даст "
                        "выражение 'ab' * 0? Впишите только число."
                    ),
                    correct_text_answer='0',
                ),
            ],
        )
        ArticleQuiz.objects.get_or_create(
            article=article, quiz=quiz,
            defaults={'label': 'Проверь себя', 'order': 1},
        )

    def seed_8_4(self):
        article = Article.objects.get(slug='8-4-metody-poiska-i-zameny')
        article.description = (
            'Оператор in из урока 8.3 отвечает только «да» или «нет», а нужно '
            'знать, где именно и сколько раз. Четыре метода на эти вопросы: '
            'find() и rfind() возвращают позицию (и -1, если не нашлось), '
            'count() считает непересекающиеся вхождения, replace() строит '
            'новую строку с заменой. Попутно — сама запись s.метод(): это '
            'первый урок, где действие вызывают у значения через точку.'
        )
        article.save(update_fields=['description'])

        _replace_blocks(article, [
            dict(order=1, block_type='text', title='Где именно и сколько раз', content=(
                'Три задачи, на которых прошлый урок останавливается:\n\n'
                '1. из адреса `ivanov@school.ru` вытащить логин — то, что '
                'стоит **до** собаки;\n'
                '2. из имени файла `отчёт.итог.docx` вытащить расширение. '
                'Точек здесь две, а нужна **последняя**;\n'
                '3. посчитать, сколько раз в тексте встречается слово, и '
                'заменить его на другое.\n\n'
                'Проверить, есть ли собака в адресе, мы умеем — это `in` из '
                'урока 8.3. Но чтобы отрезать логин, нужен срез, а срезу нужна '
                '**граница числом**: позиция собаки. `in` такого не сообщает: '
                'он отвечает «да» или «нет» и молчит о том, где нашлось.\n\n'
                'Всё это давно есть в любом текстовом редакторе: Ctrl+F '
                'подсвечивает найденное и пишет «3 из 7», а «Заменить всё» '
                'переделывает документ одной кнопкой. Редактор знает и место, '
                'и количество. В этом уроке тем же самым займётся программа.'
            )),
            dict(order=2, block_type='text', title='Новая форма записи: метод', content=(
                'Сначала — про точку, которая появится во всех примерах '
                'урока.\n\n'
                'До сих пор действие записывалось одинаково: имя, скобки, '
                'значение внутри — `len(s)`, `ord(c)`, `int(x)`. Дальше '
                'встретится другая запись: `s.find(\'@\')` — сначала строка, '
                'потом точка, потом название действия.\n\n'
                '> **Метод** — это действие, которое вызывают у конкретного '
                'значения, приписывая его имя через точку. `s.find(\'@\')` '
                'читается «у строки `s` найди собаку».\n\n'
                'Почему не как обычную функцию: `len()` умеет измерять что '
                'угодно, а поиск подстроки — работа именно со строкой, и она '
                '«принадлежит» строке. Есть и практическая выгода: набрав `s.`, '
                'вы увидите в редакторе список всего, что строка умеет, — '
                'ничего не нужно помнить наизусть.\n\n'
                'Вызывать метод можно не только у переменной, но и прямо у '
                'строки: `\'информатика\'.count(\'а\')` — законная запись.\n\n'
                'И главное, ради чего этот блок стоит раньше самих методов. '
                'Строка неизменяема (урок 8.1), поэтому **ни один метод строки '
                'её не трогает**. Метод либо отвечает на вопрос — числом или '
                '`True`/`False`, — либо строит рядом новую строку. Исходная '
                'остаётся ровно такой, какой была. Через несколько блоков это '
                'правило обернётся самой частой ошибкой урока.'
            )),
            dict(order=3, block_type='text', title='find(): позиция первого вхождения', content=(
                '> `s.find(sub)` возвращает индекс первого символа **первого** '
                'вхождения подстроки `sub` в строку `s`. Если вхождения нет — '
                'возвращает `-1`.\n\n'
                'Почему `-1`, а не ошибка? Позиции нумеруются с нуля и '
                'отрицательными не бывают, поэтому `-1` — заведомо невозможный '
                'ответ для «нашлось», и одно число служит сразу и результатом, '
                'и признаком неудачи. Аварийно останавливать программу тут было '
                'бы неудобно: не найти — это нормальный исход, а не поломка.\n\n'
                '**Главная ловушка урока.** Нельзя писать `if s.find(\'@\'):`. '
                'Если собака стоит в самом начале строки, `find()` вернёт `0`, '
                'а ноль — это ложь (блок 3), и условие не сработает при том, что '
                'подстрока на месте. Сравнивать надо явно: '
                '`if s.find(\'@\') != -1:`. А ещё честнее — спрашивать про '
                'наличие через `in` из урока 8.3, а `find()` звать тогда, когда '
                'нужна именно позиция.\n\n'
                '**Второй параметр — откуда искать.** `s.find(sub, start)` '
                'начинает просмотр с позиции `start` и всё, что левее, '
                'пропускает. Есть и третий параметр — граница справа. Важно: '
                'позиция возвращается **в исходной строке**, а не отсчитывается '
                'заново от `start`, — на этом спотыкаются сразу после первой '
                'ловушки.\n\n'
                'Найденную позицию почти всегда тут же подставляют в срез из '
                'урока 8.2: `s[:pos]` — то, что до неё, `s[pos + 1:]` — то, что '
                'после.'
            )),
            dict(order=4, block_type='code', title='', code_language='python', content=(
                "text = 'информатика'\n"
                '\n'
                "print(text.find('ма'))    # 5 — позиция первого символа куска\n"
                "print(text.find('а'))     # 6 — первая «а», хотя в слове их две\n"
                "print(text.find('кот'))   # -1 — такого куска здесь нет\n"
                '\n'
                "s = '@school.ru'\n"
                '\n'
                "if s.find('@'):           # так нельзя: find вернул 0, а 0 — ложь\n"
                "    print('собака есть')  # эта строка не выполнится!\n"
                '\n'
                "if s.find('@') != -1:     # а так правильно\n"
                "    print('собака есть')\n"
                '\n'
                "print(text.find('а', 7))  # 10 — искали с позиции 7, но ответ\n"
                '                          # всё равно в номерах исходной строки\n'
                '\n'
                "email = 'ivanov@school.ru'\n"
                "pos = email.find('@')\n"
                'print(pos)                # 6\n'
                'print(email[:pos])        # ivanov — задача 1 из начала урока\n'
                'print(email[pos + 1:])    # school.ru'
            )),
            dict(order=5, block_type='text', title='rfind(): та же работа, но справа', content=(
                '> `s.rfind(sub)` возвращает позицию **последнего** вхождения '
                'подстроки. Если вхождения нет — те же `-1`.\n\n'
                'Буква `r` — от английского right, «справа». Разница с `find()` '
                'заметна, только когда вхождений несколько: если оно одно или '
                'нет ни одного, оба метода дают одинаковый ответ.\n\n'
                'При этом `rfind()` **не переворачивает нумерацию**. Позиция '
                'по-прежнему считается слева, с нуля; метод лишь выбирает среди '
                'найденных мест самое правое.\n\n'
                'Зачем он нужен: типовая задача «отрезать хвост по последнему '
                'разделителю». Расширение файла — после последней точки, имя '
                'файла — после последнего слэша в пути. Это ровно вторая задача '
                'из начала урока: `find(\'.\')` наткнулся бы на точку из '
                'середины имени и выдал бы неверное расширение.\n\n'
                'Одной строкой, чтобы не удивляться при чтении чужого кода: у '
                'обоих методов есть парные `index()` и `rindex()`, которые '
                'вместо `-1` аварийно останавливают программу. Нам пока удобнее '
                '`-1` — программа продолжает работать, а решение, что делать '
                'дальше, остаётся за нами.'
            )),
            dict(order=6, block_type='code', title='', code_language='python', content=(
                "name = 'отчёт.итог.docx'\n"
                '\n'
                "print(name.find('.'))    # 5 — первая точка, из середины имени\n"
                "print(name.rfind('.'))   # 10 — последняя, та самая\n"
                '\n'
                "dot = name.rfind('.')\n"
                'print(name[dot + 1:])    # docx — задача 2 из начала урока\n'
                'print(name[:dot])        # отчёт.итог\n'
                '\n'
                "path = 'C:/Users/Аня/доклад.pdf'\n"
                "slash = path.rfind('/')\n"
                'print(path[slash + 1:])  # доклад.pdf — тот же приём для пути\n'
                '\n'
                "print('нет точки'.rfind('.'))  # -1 — как и у find\n"
                "print('информатика'.find('м'), 'информатика'.rfind('м'))  # 5 5\n"
                '                         # вхождение одно — ответы совпали'
            )),
            # Иллюстрация: плоский минималистичный стиль, как в блоках 2 и 5–8.
            # По центру — строка «отчёт.итог.docx», разложенная по клеткам, под
            # клетками номера позиций 0–14.
            # Сверху над лентой — зелёная стрелка слева направо, упирающаяся в
            # клетку с точкой на позиции 5, подпись «find('.') → 5».
            # Снизу под лентой — оранжевая стрелка справа налево, упирающаяся в
            # клетку с точкой на позиции 10, подпись «rfind('.') → 10».
            # Обе точки в ленте подсвечены своими цветами, остальные клетки
            # нейтральные.
            # Справа отдельной бледной плашкой — та же лента целиком серая,
            # без подсветки, и подпись «find('!') → -1, rfind('!') → -1»:
            # при неудаче ответ у обоих один и тот же.
            # Главный смысл: методы идут навстречу друг другу и оба
            # останавливаются на первом же совпадении со своей стороны.
            dict(order=7, block_type='image', title='', content=(
                '`find()` идёт по строке слева направо и останавливается на '
                'первом совпадении, `rfind()` — справа налево и '
                'останавливается на последнем. Если совпадений нет, обоим '
                'нечего вернуть, и ответ один и тот же: `-1`.'
            )),
            dict(order=8, block_type='text', title='count(): сколько раз встретилось', content=(
                '> `s.count(sub)` возвращает число вхождений подстроки `sub` в '
                'строку `s`.\n\n'
                'Если не нашлось ничего, ответ — `0`, а не `-1`. Никакого '
                'разнобоя тут нет: ноль — честный ответ на вопрос «сколько», а '
                'не признак сбоя. Границы `start` и `stop` работают так же, как '
                'у `find()`: можно считать не по всей строке, а по её куску.\n\n'
                '**Главная тонкость — пересечения.** Считаются только '
                '**непересекающиеся** вхождения, слева направо. В строке '
                '`\'ааа\'` подстрока `\'аа\'` на глаз встречается дважды — на '
                'позициях 0 и 1, — но `count()` вернёт `1`. Найдя вхождение на '
                'позициях 0–1, он продолжает поиск с позиции 2, а не с 1. '
                'Правило простое: нашли — перепрыгнули через находку целиком. К '
                'этому прыжку мы ещё вернёмся в трассировке.\n\n'
                'Курьёз, который прямо следует из определения подстроки в уроке '
                '8.3: `s.count(\'\')` даёт `len(s) + 1`. Пустая строка «стоит» '
                'в каждом промежутке между символами и по обоим краям.\n\n'
                'Заодно `count()` отвечает и на вопрос «есть ли вообще»: '
                '`count(sub) > 0` — то же самое, что `sub in s`. Но если нужен '
                'только ответ «да/нет», берите `in`: он точнее по смыслу и не '
                'пересчитывает всю строку до конца.'
            )),
            dict(order=9, block_type='code', title='', code_language='python', content=(
                "text = 'информатика'\n"
                '\n'
                "print(text.count('а'))    # 2\n"
                "print(text.count('и'))    # 2\n"
                "print(text.count('кот'))  # 0 — не -1: ноль это ответ, а не сбой\n"
                '\n'
                "print('ааа'.count('аа'))  # 1, а не 2! Вхождения не пересекаются:\n"
                '                          # нашли на 0–1 и продолжили с позиции 2\n'
                '\n'
                "print('абв'.count(''))    # 4 — это len(s) + 1\n"
                '\n'
                "line = 'кот и кот и кот'\n"
                "print(line.count('кот'))     # 3\n"
                "print(line.count('кот', 6))  # 2 — считаем только с позиции 6"
            )),
            dict(order=10, block_type='text', title='replace(): замена всех вхождений', content=(
                '> `s.replace(old, new)` возвращает **новую** строку, в которой '
                'каждое вхождение `old` заменено на `new`. Сама `s` при этом не '
                'меняется — и не может: строка неизменяема.\n\n'
                '**Самая частая ошибка во всём уроке.** Строка '
                '`s.replace(\'а\', \'о\')` сама по себе не делает ничего '
                'видимого: результат посчитан и тут же выброшен, потому что его '
                'некуда было записать. Нужно `s = s.replace(\'а\', \'о\')` — '
                'или сохранить в другое имя, если исходная строка ещё '
                'понадобится.\n\n'
                'Это тот же самый разговор, что был в уроке 8.1 про '
                '`s[0] = \'П\'`, только с важной разницей: там программа падала '
                'с ошибкой и сама показывала, что вы не правы, а здесь она '
                'молча продолжает работать со старой строкой. Тем и '
                'опаснее.\n\n'
                'Ещё три свойства:\n\n'
                '- **третий параметр — сколько заменять.** '
                '`s.replace(old, new, 1)` заменит только первое вхождение. Без '
                'него заменяются все;\n'
                '- **замена на пустую строку — это удаление.** '
                '`s.replace(\' \', \'\')` выбрасывает из строки все пробелы. '
                'Отдельный метод «удалить» для этого не нужен;\n'
                '- **метод не знает про слова.** Он работает с подстрокой, а не '
                'со смыслом: замена `\'кот\'` на `\'пёс\'` превратит «котлета» '
                'в «пёслета». Это не поломка, а прямое следствие определения '
                'подстроки из урока 8.3 — просто границы слов методу '
                'неизвестны.\n\n'
                'Вызовы можно ставить цепочкой: '
                '`s.replace(\'a\', \'b\').replace(\'c\', \'d\')` — второй метод '
                'вызывается уже у результата первого. Порядок при этом важен, '
                'если замены задевают одни и те же буквы.'
            )),
            dict(order=11, block_type='code', title='', code_language='python', content=(
                "s = 'привет'\n"
                '\n'
                "s.replace('и', 'ы')       # результат посчитан и выброшен\n"
                'print(s)                  # привет — строка не изменилась\n'
                '\n'
                "s = s.replace('и', 'ы')   # вот теперь сохранили\n"
                'print(s)                  # прывет\n'
                '\n'
                "line = 'кот и кот и котлета'\n"
                "print(line.count('кот'))                # 3 — задача 3 из начала урока\n"
                "print(line.replace('кот', 'пёс'))       # пёс и пёс и пёслета\n"
                "print(line.replace('кот', 'пёс', 1))    # пёс и кот и котлета\n"
                '\n'
                "print('  1 2 3  '.replace(' ', ''))     # 123 — замена на пустую\n"
                '                                        # строку это удаление\n'
                '\n'
                "print('abc'.replace('a', 'b').replace('b', 'c'))  # ccc, а не cbc:\n"
                '                                        # вторая замена работает\n'
                '                                        # с результатом первой'
            )),
            dict(
                order=12, block_type='widget',
                title='Все вхождения по очереди',
                content=(
                    'Этот цикл делает то, чего не умеет ни один метод по '
                    'отдельности: `find()` отдаёт одну позицию, `count()` — '
                    'одно число, а «покажи все места» собирается из `find()` со '
                    'вторым параметром — тем самым, что задаёт, откуда искать. '
                    'Именно это и происходит, когда в редакторе жмёшь Ctrl+F, а '
                    'потом «дальше». Пройдите трассу по шагам и посмотрите на '
                    'три вещи: как `i` каждый раз перескакивает за найденное '
                    'вхождение, что цикл заканчивается не по длине строки, а по '
                    'ответу `-1`, и что итоговое `n` совпало с тем, что вернул '
                    'бы `count()`, — по той же самой причине, по которой '
                    '`\'ааа\'.count(\'аа\')` равно `1`.'
                ),
                widget_key='loop-trace',
                widget_config={
                    'code': FIND_ALL_CODE,
                    'vars': ['text', 'sub', 'i', 'pos', 'n'],
                    'steps': _find_all_trace(),
                },
            ),
            dict(order=13, block_type='text', title='Границы: чего эти методы не умеют', content=(
                'Чтобы не ждать от них лишнего:\n\n'
                '- **не различают регистр.** `\'Кот и кот\'.count(\'кот\')` '
                'вернёт `1`, а не `2`: «К» и «к» — разные символы с разными '
                'кодовыми точками (урок 8.1). Приводить строку к одному '
                'регистру научимся в уроке 8.5;\n'
                '- **не знают границ слов.** Ни `count()`, ни `replace()` не '
                'отличают отдельное слово от куска другого слова — «котлета» '
                'тому примером;\n'
                '- **не видят пересечений** — `count()` перепрыгивает через '
                'найденное;\n'
                '- **работают с одним куском.** Разрезать строку сразу по всем '
                'разделителям они не умеют, для этого в уроке 8.6 появится '
                '`split()`.\n\n'
                'И общее. Под всеми четырьмя методами лежит тот же перебор '
                'окна, который мы разбирали в уроке 8.3 для `in`: приложить '
                'кусок к позиции, сравнить, сдвинуться. Отличаются они только '
                'тем, что делают, дойдя до совпадения. `find()` '
                'останавливается и сообщает позицию, `rfind()` идёт с другого '
                'конца, `count()` прибавляет единицу и едет дальше, '
                '`replace()` собирает по дороге новую строку. Один механизм — '
                'четыре разных ответа.'
            )),
            dict(order=14, block_type='text', title='Шпаргалка', content=(
                '| Запись | Что вернёт | Если не нашлось | Меняет `s`? |\n'
                '|---|---|---|---|\n'
                '| `sub in s` | `True` или `False` | `False` | нет |\n'
                '| `s.find(sub)` | позицию первого вхождения | `-1` | нет |\n'
                '| `s.rfind(sub)` | позицию последнего вхождения | `-1` | нет |\n'
                '| `s.count(sub)` | число вхождений | `0` | нет |\n'
                '| `s.replace(a, b)` | новую строку с заменой | копию без изменений | нет |\n\n'
                'Последний столбец везде одинаковый — и ради него таблица и '
                'нужна. Что бы вы ни вызвали у строки, исходная строка остаётся '
                'прежней, а ответ надо куда-то присвоить, иначе он просто '
                'пропадёт.'
            )),
            dict(order=15, block_type='text', title='Итог и мостик к 8.5', content=(
                'Три задачи из начала урока решаются в одну-две строки: логин '
                'из почты — `find(\'@\')` и срез, расширение файла — '
                '`rfind(\'.\')` и срез, посчитать и заменить — `count()` и '
                '`replace()`.\n\n'
                'Что стоит вынести:\n\n'
                '- метод вызывают **у значения** через точку: `s.find(...)`, а '
                'не `find(s, ...)`;\n'
                '- `find()` и `rfind()` дают позицию, а при неудаче `-1`, '
                'поэтому проверка всегда `!= -1`, а не «если истина» — иначе '
                'вхождение на позиции 0 будет потеряно;\n'
                '- второй параметр `find()` задаёт, откуда искать, но позиция '
                'возвращается в номерах исходной строки;\n'
                '- `count()` считает непересекающиеся вхождения и возвращает '
                '`0`, если ничего не нашёл;\n'
                '- `replace()` возвращает новую строку и без присваивания '
                'бесполезен; на пустую строку заменяют, чтобы удалить;\n'
                '- ни один из методов не знает ни про регистр, ни про границы '
                'слов.\n\n'
                'Вот регистр и остаётся главной дырой. Поиск `\'кот\'` не '
                'находит `\'Кот\'`, хотя человек считает это одним и тем же '
                'словом, — и любая проверка введённого ломается о заглавную '
                'букву в начале. В уроке 8.5 появятся `upper()` и `lower()`, '
                'проверки `isalpha()` и `isdigit()`, `strip()` для лишних '
                'пробелов — и главный приём: привести обе строки к одному '
                'регистру и только потом сравнивать.'
            )),
        ])

        quiz = _self_check(
            slug='self-check-metody-poiska-i-zameny',
            title='Самопроверка: методы поиска и замены',
            description='Три коротких вопроса по теме урока.',
            questions=[
                dict(
                    type='choice',
                    text=(
                        "Программа выполняет две строки:\n\n"
                        '```python\n'
                        "s = 'привет'\n"
                        "s.replace('и', 'ы')\n"
                        "print(s)\n"
                        '```\n\n'
                        "Что она напечатает?"
                    ),
                    choices=[
                        ('привет — replace вернул новую строку, но её никуда не '
                         'сохранили', True),
                        ('прывет — replace заменил букву прямо в строке s', False),
                        ('None — метод ничего не вернул', False),
                        ('Ошибку — строку нельзя изменять', False),
                    ],
                ),
                dict(
                    type='choice',
                    text="Что вернёт выражение `'ааа'.count('аа')`?",
                    choices=[
                        ('1 — вхождения считаются непересекающимися: найдя кусок '
                         'на позициях 0–1, count продолжает с позиции 2', True),
                        ('2 — подстрока «аа» видна на позициях 0 и 1', False),
                        ('3 — по числу букв «а» в строке', False),
                        ('0 — count работает только с одиночными символами', False),
                    ],
                ),
                dict(
                    type='text',
                    text=(
                        'Что вернёт метод find(), если подстрока в строке не '
                        'найдена? Впишите ответ числом.'
                    ),
                    correct_text_answer='-1',
                ),
            ],
        )
        ArticleQuiz.objects.get_or_create(
            article=article, quiz=quiz,
            defaults={'label': 'Проверь себя', 'order': 1},
        )

    def seed_8_5(self):
        article = Article.objects.get(slug='8-5-metody-registra-i-proverki')
        article.description = (
            'Регистр — та самая дыра, на которой остановился урок 8.4: поиск '
            '\'кот\' не находит \'Кот\', а введённый ответ не совпадает с '
            'эталоном из-за заглавной буквы и пары лишних пробелов. upper() и '
            'lower() приводят строки к одному виду, strip() срезает невидимый '
            'мусор по краям, а группа методов is...() отвечает «да/нет» на '
            'вопросы о содержимом строки.'
        )
        article.save(update_fields=['description'])

        _replace_blocks(article, [
            dict(order=1, block_type='text', title='Ответ правильный, а программа не согласна', content=(
                'Программа спрашивает столицу России и сравнивает введённое с '
                'эталоном `\'Москва\'`. Три ученика отвечают: `москва`, '
                '`МОСКВА` и `Москва ` — последний случайно задел пробел. Все '
                'трое знают правильный ответ, и всем троим программа говорит '
                '«неверно».\n\n'
                'Программа не придирается — она честно сравнивает строки '
                'символ за символом. А `\'м\'` и `\'М\'` — разные символы с '
                'разными кодовыми точками, мы знаем это с урока 8.1. Пробел — '
                'тоже полноценный символ, и строка с ним просто длиннее '
                'эталона.\n\n'
                'Тут же и незакрытый хвост прошлого урока: '
                '`\'Кот и кот\'.count(\'кот\')` вернул `1`, хотя человек видит '
                'два одинаковых слова.\n\n'
                'Значит, задача урока — не научить программу понимать смысл, а '
                'привести обе строки к одному виду **перед** сравнением. И '
                'заодно научиться заранее проверять, что вообще ввёл человек: '
                'цифры это или буквы, пусто или нет.'
            )),
            dict(order=2, block_type='text', title='upper() и lower(): один регистр для всех', content=(
                '> `s.upper()` возвращает **новую** строку, в которой все '
                'буквы заглавные. `s.lower()` — новую строку, в которой все '
                'буквы строчные. Сама `s` при этом не меняется.\n\n'
                'Правило из урока 8.4 действует без исключений: метод строит '
                'строку рядом, а результат надо куда-то присвоить, иначе он '
                'пропадёт.\n\n'
                'Что стоит знать про эти два метода:\n\n'
                '- **не-буквы они не трогают.** Цифры, пробелы и знаки '
                'препинания переезжают в результат как есть — у них просто нет '
                'регистра;\n'
                '- **русские буквы работают наравне с латинскими**, включая '
                r'`ё` $\leftrightarrow$ `Ё`. И вот это уже не само собой разумеется.' '\n\n'
                'В уроке 8.1 мы «поднимали» букву вручную: '
                '`chr(ord(c) - 32)`. Приём держится на устройстве таблицы — у '
                'латиницы заглавная и строчная стоят ровно через 32 позиции, у '
                'основных букв кириллицы (`А`–`Я` и `а`–`я`) тоже. А вот `ё` и '
                '`Ё` в таблицу Unicode попали отдельно от своего алфавита, и '
                'между ними уже 80 позиций: `chr(ord(\'ё\') - 32)` даёт не '
                '`\'Ё\'`, а постороннюю букву `\'б\'`. Метод `upper()` ничего '
                'не вычисляет — он смотрит в таблицу, где для каждой буквы '
                'прописана её пара, поэтому исключения его не смущают.\n\n'
                'Одной фразой, чтобы потом не удивляться: строка после '
                '`upper()` может стать **длиннее** исходной — немецкая `ß` '
                'превращается в `SS`. Для наших задач это неважно, но '
                'ожидание «длина точно не изменится» — неверное.'
            )),
            dict(order=3, block_type='code', title='', code_language='python', content=(
                "s = 'Привет, Мир!'\n"
                '\n'
                "print(s.upper())        # ПРИВЕТ, МИР!\n"
                "print(s.lower())        # привет, мир!\n"
                'print(s)                # Привет, Мир! — строка не изменилась\n'
                '\n'
                "print('дом 12, кв. 3'.upper())  # ДОМ 12, КВ. 3 — цифры и знаки\n"
                '                                # остались на месте\n'
                '\n'
                "print('ёжик'.upper())         # ЁЖИК — метод знает про ё\n"
                "print(chr(ord('ё') - 32))     # б — ручной приём из 8.1 здесь врёт:\n"
                "                              # между ё и Ё в таблице 80 позиций\n"
                '\n'
                "s = s.lower()           # вот так результат сохраняют\n"
                'print(s)                # привет, мир!'
            )),
            dict(order=4, block_type='text', title='Приём урока: сравнивать после приведения', content=(
                'Ради этого урок и написан.\n\n'
                'Проверка ответа выглядит так: `if answer.lower() == '
                '\'москва\':` — введённое приводим к нижнему регистру, а '
                'эталон **сразу пишем строчными**. Типичная ошибка — привести '
                'одну сторону и сравнить с эталоном `\'Москва\'`: тогда не '
                'совпадёт вообще ничего, даже правильно набранный ответ.\n\n'
                'Второе применение — поиск и подсчёт без учёта регистра: '
                '`text.lower().count(\'кот\')` закрывает ровно ту дыру, о '
                'которой предупреждал урок 8.4. Точно так же работает с '
                '`find()`, `in` и `replace()`: приводим строку, а ищем уже в '
                'приведённой. Позиции при этом не съезжают — `lower()` меняет '
                'буквы, а не их количество (кроме той самой `ß`, но в обычном '
                'тексте её не встретить).\n\n'
                'Почему обычно берут `lower()`, а не `upper()`: по сути '
                'разницы нет, просто эталон строчными писать привычнее и код '
                'читается спокойнее. Важно другое — не смешивать оба способа в '
                'одной программе.'
            )),
            dict(order=5, block_type='code', title='', code_language='python', content=(
                "answer = 'МОСКВА'\n"
                '\n'
                "if answer.lower() == 'москва':      # эталон сразу строчными\n"
                "    print('верно')                  # верно\n"
                '\n'
                "if answer.lower() == 'Москва':      # так не сработает никогда:\n"
                "    print('верно')                  # слева всё строчное,\n"
                '                                    # а справа заглавная М\n'
                '\n'
                "line = 'Кот и кот'\n"
                "print(line.count('кот'))            # 1 — заглавная К не подошла\n"
                "print(line.lower().count('кот'))    # 2 — вот теперь оба\n"
                '\n'
                "print(line.lower().find('кот'))     # 0 — ищем в приведённой строке,\n"
                '                                    # позиции остались прежними'
            )),
            dict(order=6, block_type='text', title='strip(): невидимый мусор по краям', content=(
                '> `s.strip()` возвращает новую строку без **пробельных** '
                'символов в начале и в конце.\n\n'
                'Пробельный — это не только пробел: табуляция `\\t` и перевод '
                'строки `\\n` тоже. Их не видно на экране, но в строке они '
                'есть и сравнению мешают.\n\n'
                'Что важно:\n\n'
                '- **середину метод не трогает.** `\'  а  б  \'.strip()` даёт '
                '`\'а  б\'` — два пробела внутри остались. Выбрасывать их — '
                'работа `replace()` из урока 8.4;\n'
                '- есть односторонние варианты: `lstrip()` срезает только '
                'слева, `rstrip()` — только справа;\n'
                '- **аргумент — это набор символов, а не подстрока.** '
                '`s.strip(\'.,!\')` срезает с краёв любые из перечисленных '
                'символов, в любом порядке и количестве, пока не встретит '
                'что-то другое.\n\n'
                'На последнем пункте спотыкаются все. '
                '`\'test.txt\'.strip(\'.txt\')` даёт `\'es\'`: метод не искал '
                'кусок `.txt`, он грыз края, пока попадались символы `.`, `t` '
                'и `x`, — и слева отгрыз первую `t`, и справа добрался до `t` '
                'в середине слова. Отрезать расширение по-честному — это '
                '`rfind(\'.\')` и срез из прошлого урока.\n\n'
                'Откуда мусор берётся вообще. `input()` сам перевод строки не '
                'отдаёт, но пробелы, которые человек случайно набрал, остаются '
                'полностью. А при чтении данных из файла (блок 19) в конце '
                'каждой строки будет `\\n` — там `strip()` станет обязательным '
                'ритуалом.\n\n'
                'Итоговая связка урока: сначала `strip()`, потом `lower()`, и '
                'только потом сравнение.'
            )),
            dict(order=7, block_type='code', title='', code_language='python', content=(
                "s = '  Москва  '\n"
                '\n'
                "print('[' + s + ']')            # [  Москва  ]\n"
                "print('[' + s.strip() + ']')    # [Москва]\n"
                "print('[' + s.lstrip() + ']')   # [Москва  ] — только слева\n"
                "print('[' + s.rstrip() + ']')   # [  Москва] — только справа\n"
                '\n'
                "print('[' + '  а  б  '.strip() + ']')   # [а  б] — середина цела\n"
                '\n'
                "print('...ответ!!!'.strip('.!'))        # ответ\n"
                "print('test.txt'.strip('.txt'))         # es, а не test!\n"
                '                                        # набор символов, а не кусок\n'
                '\n'
                "answer = ' Москва '\n"
                "print(answer.strip().lower() == 'москва')   # True — вся связка урока"
            )),
            # Иллюстрация: плоский минималистичный стиль, как в блоках 2 и 5–8.
            # Два ряда, один под другим.
            # Верхний ряд: строка «__Москва__город__» (подчёркивания — пробелы),
            # разложенная по клеткам; пробельные клетки помечены серым значком
            # пробела. Слева и справа — зелёные скобки-стрелки, направленные
            # внутрь строки, подпись над ними «strip() грызёт с краёв».
            # Два крайних пробела слева и два справа перечёркнуты (съедены),
            # два пробела в середине подсвечены другим цветом с подписью
            # «эти остаются — strip() до них не доходит».
            # Нижний ряд: то же для 'test.txt'.strip('.txt'). Слева отдельной
            # плашкой набор символов { '.', 't', 'x' } — именно как три
            # отдельных символа, не как слово. В ленте t-e-s-t-.-t-x-t
            # перечёркнуты по одному: слева первая t, справа t, x, t, точка
            # и ещё одна t; оставшееся «es» выделено рамкой.
            # Главный смысл: strip() работает только с краями и с отдельными
            # символами, а не с подстрокой целиком.
            dict(order=8, block_type='image', title='', content=(
                '`strip()` работает только с краями строки и останавливается '
                'на первом же символе, которого нет в наборе. Всё, что стоит '
                'между этими границами, метод не трогает — даже если это те же '
                'самые пробелы. А набор в скобках — это отдельные символы, а '
                'не кусок текста, поэтому `\'test.txt\'.strip(\'.txt\')` '
                'оставляет `\'es\'`.'
            )),
            dict(order=9, block_type='text', title='Методы-вопросы: isalpha(), isdigit() и остальные', content=(
                'Вторая группа методов ничего не строит — они отвечают `True` '
                'или `False`:\n\n'
                '- `s.isdigit()` — все ли символы строки цифры;\n'
                '- `s.isalpha()` — все ли буквы;\n'
                '- `s.isalnum()` — буквы или цифры;\n'
                '- `s.isspace()` — все ли пробельные;\n'
                '- `s.isupper()` и `s.islower()` — весь ли текст в одном '
                'регистре.\n\n'
                'Три вещи, из-за которых на них ошибаются:\n\n'
                '1. **Вопрос задаётся про всю строку целиком, а не про первый '
                'символ.** `\'123\'.isdigit()` → `True`, `\'12а\'.isdigit()` → '
                '`False`. Достаточно одного чужого символа, чтобы ответ стал '
                'ложным: `\'Привет!\'.isalpha()` — уже `False` из-за '
                'восклицательного знака, а `\'Привет мир\'.isalpha()` — из-за '
                'пробела.\n'
                '2. **Пустая строка даёт `False` у всех.** Утверждать «все '
                'символы — цифры» не о чем, если символов нет. Практический '
                'вывод: проверку «человек вообще что-то ввёл» этими методами '
                'не заменить.\n'
                '3. **`isdigit()` — это про цифры, а не про числа.** У `\'-5\'` '
                'есть минус, у `\'3.14\'` — точка, и обе строки дают `False`. '
                'Значит, такая проверка пропускает только неотрицательные '
                'целые; для остального её не хватит.\n\n'
                'Курьёз для внимательных: у `isdigit()` есть более строгий '
                'родственник `isdecimal()` — надстрочная `\'²\'` считается '
                'цифрой для первого и не считается для второго.\n\n'
                'Зачем всё это нужно: `int(x)` на нечисловой строке аварийно '
                'останавливает программу, а `if x.isdigit():` позволяет '
                'проверить заранее и вежливо попросить ввести число ещё раз.'
            )),
            dict(order=10, block_type='code', title='', code_language='python', content=(
                "print('123'.isdigit())      # True\n"
                "print('12а'.isdigit())      # False — одна буква всё портит\n"
                "print(''.isdigit())         # False — пустая строка всегда False\n"
                "print(' '.isdigit())        # False, а вот ' '.isspace() — True\n"
                '\n'
                "print('Привет'.isalpha())      # True — кириллица тоже буквы\n"
                "print('Привет!'.isalpha())     # False — знак не буква\n"
                "print('Привет мир'.isalpha())  # False — и пробел не буква\n"
                '\n'
                "print('-5'.isdigit())       # False — минус не цифра\n"
                "print('3.14'.isdigit())     # False — точка тоже\n"
                '\n'
                "age = input('Сколько вам лет? ')\n"
                '\n'
                'if age.isdigit():\n'
                '    print(int(age) + 1)             # тут int() уже безопасен\n'
                'else:\n'
                "    print('Это не похоже на число')"
            )),
            dict(
                order=11, block_type='widget',
                title='Оставить от строки только буквы',
                content=(
                    'Три темы урока в одном цикле. Программа идёт по строке '
                    'символ за символом, спрашивает у каждого `isalpha()` и '
                    'подходящие — сразу в нижнем регистре — приклеивает к '
                    'новой строке `clean`. Пройдите трассу по шагам и '
                    'посмотрите на две вещи: `text` на всех шагах остаётся '
                    'прежним, а результат растёт **рядом** с ним (правило из '
                    'урока 8.1 никуда не делось), и как условие отсеивает '
                    'запятую, пробел и восклицательный знак. Такая очистка — '
                    'обязательный первый шаг задачи о палиндроме, которая ждёт '
                    'в уроке 8.7.'
                ),
                widget_key='loop-trace',
                widget_config={
                    'code': CLEAN_LETTERS_CODE,
                    'vars': ['text', 'c', 'clean'],
                    'steps': _clean_letters_trace(),
                },
            ),
            dict(order=12, block_type='text', title='Ещё три метода регистра — чтобы узнавать в чужом коде', content=(
                'Коротким списком, без углубления:\n\n'
                '- `capitalize()` — первая буква строки заглавная, а все '
                'остальные **строчные**, а не «как было»: '
                '`\'пРИВЕТ\'.capitalize()` даёт `\'Привет\'`;\n'
                '- `title()` — с заглавной каждое слово. С предупреждением: '
                'границей слова метод считает любой не-буквенный символ, '
                'поэтому `\'мария-луиза\'` превращается в `\'Мария-Луиза\'`, а '
                '`"о\'нил"` — в `"О\'Нил"`. Иногда это ровно то, что нужно, а '
                'иногда — испорченная фамилия;\n'
                '- `swapcase()` — меняет регистр на противоположный. '
                'Встречается редко, но узнать в чужом коде полезно.\n\n'
                'И общая граница всей группы: ни один из этих методов не '
                'знает, что такое имя собственное, начало предложения или '
                'аббревиатура. Они работают с символами по таблице, а не со '
                'смыслом текста.'
            )),
            dict(order=13, block_type='text', title='Шпаргалка', content=(
                '| Запись | Что вернёт | Про что | Меняет `s`? |\n'
                '|---|---|---|---|\n'
                '| `s.upper()` | новую строку | все буквы заглавные | нет |\n'
                '| `s.lower()` | новую строку | все буквы строчные | нет |\n'
                '| `s.strip()` | новую строку | без пробельных по краям | нет |\n'
                '| `s.strip(chars)` | новую строку | без **любых** символов из набора по краям | нет |\n'
                '| `s.isdigit()` | `True` или `False` | все ли символы цифры | нет |\n'
                '| `s.isalpha()` | `True` или `False` | все ли символы буквы | нет |\n'
                '| `s.isspace()` | `True` или `False` | все ли символы пробельные | нет |\n\n'
                'Последний столбец снова весь одинаковый — ради него таблица и '
                'нужна. Верхняя половина возвращает строку, которую надо '
                'присвоить, иначе результат пропадёт. Нижняя отвечает «да/нет» '
                'про **всю** строку сразу, и на пустой строке этот ответ всегда '
                '`False`.'
            )),
            dict(order=14, block_type='text', title='Итог и мостик к 8.6', content=(
                'Все три ответа из начала урока проходят проверку '
                '`answer.strip().lower() == \'москва\'`: сначала срезали края, '
                'потом уравняли регистр, и только потом сравнили.\n\n'
                'Что стоит вынести:\n\n'
                '- `upper()` и `lower()` не меняют строку, а строят новую — как '
                'и всё в блоке 8;\n'
                '- приводить надо **обе** стороны сравнения, а эталон удобнее '
                'сразу писать строчными;\n'
                '- `strip()` работает только с краями и принимает набор '
                'символов, а не подстроку;\n'
                '- методы `is...()` спрашивают про всю строку целиком и на '
                'пустой строке дают `False`;\n'
                '- `isdigit()` не пропускает ни минус, ни точку.\n\n'
                'Теперь строку можно очистить и сравнить целиком. Но настоящие '
                'данные приходят не по одной штуке: дата `2026-08-01`, строка '
                'таблицы `Иванов;9А;5`, предложение из слов — это одна строка, '
                'внутри которой лежит несколько значений, разделённых одним и '
                'тем же символом. Резать её вручную через `find()` и срезы '
                'можно, но при пяти разделителях это превращается в мучение. В '
                'уроке 8.6 появится `split()`, который разрежет строку по '
                'разделителю за один вызов, `join()`, который соберёт её '
                'обратно, и f-строки — удобный способ подставлять значения в '
                'текст.'
            )),
        ])

        quiz = _self_check(
            slug='self-check-metody-registra-i-proverki',
            title='Самопроверка: методы регистра и проверки',
            description='Три коротких вопроса по теме урока.',
            questions=[
                dict(
                    type='choice',
                    text=(
                        "Программа выполняет три строки:\n\n"
                        '```python\n'
                        "s = ' Да '\n"
                        "s.strip()\n"
                        "print(s == 'Да')\n"
                        '```\n\n'
                        "Что она напечатает?"
                    ),
                    choices=[
                        ('False — strip() вернул новую строку, но её никуда не '
                         'сохранили, и в s по-прежнему пробелы', True),
                        ('True — strip() убрал пробелы прямо в строке s', False),
                        ('True — при сравнении Python сам не учитывает пробелы '
                         'по краям', False),
                        ('Ошибку — строку нельзя изменять', False),
                    ],
                ),
                dict(
                    type='choice',
                    text="Что вернёт выражение '3.14'.isdigit()?",
                    choices=[
                        ('False — точка не цифра, а метод требует, чтобы '
                         'цифрами были все символы строки', True),
                        ('True — это же число', False),
                        ('True — метод проверяет только первый символ', False),
                        ('Ошибку — метод работает только с одним символом', False),
                    ],
                ),
                dict(
                    type='text',
                    text=(
                        'Каким методом убрать пробелы в начале и в конце '
                        'строки? Впишите только имя метода, без точки и без '
                        'скобок.'
                    ),
                    correct_text_answer='strip',
                ),
            ],
        )
        ArticleQuiz.objects.get_or_create(
            article=article, quiz=quiz,
            defaults={'label': 'Проверь себя', 'order': 1},
        )

    def seed_8_6(self):
        article = Article.objects.get(slug='8-6-razbienie-i-sborka-split-i-join')
        article.description = (
            'Одна строка, внутри которой лежит несколько значений: дата '
            '2026-08-01, строка таблицы Иванов;9А;5, предложение из слов. '
            'split() разрезает её по разделителю за один вызов, join() '
            'собирает обратно, а f-строки подставляют готовые значения в '
            'текст без str() и плюсов.'
        )
        article.save(update_fields=['description'])

        _replace_blocks(article, [
            dict(order=1, block_type='text', title='Одна строка, а значений в ней несколько', content=(
                'Данные почти никогда не приходят по одной штуке. Дата — '
                '`\'2026-08-01\'`. Строка из школьной таблицы — '
                '`\'Иванов;9А;5\'`. Обычное предложение — `\'мама мыла '
                'раму\'`. Во всех трёх случаях перед нами **одна** строка, '
                'внутри которой лежит несколько значений, разделённых одним и '
                'тем же символом.\n\n'
                'Разобрать это тем, что уже есть, мы умеем: урок 8.4 дал '
                '`find()`, урок 8.2 — срезы. Для даты выходит терпимо — три '
                'среза. Но у строки таблицы разделителей уже два, а если полей '
                'семь, придётся найти шесть позиций подряд, каждый раз передавая '
                '`find()` новое начало, и ни разу не перепутать границы. Дело не '
                'в том, что это невозможно, — дело в том, что это одна и та же '
                'работа, которую приходится писать заново каждый раз.\n\n'
                'Отсюда два вопроса урока: как разрезать строку по разделителю '
                'одной командой — и как собрать её обратно, когда значения '
                'обработали.'
            )),
            dict(order=2, block_type='text', title='split(): разрезать по разделителю', content=(
                '> `s.split(sep)` возвращает **список** кусков строки `s`, '
                'разрезанной по разделителю `sep`. Сам разделитель ни в один '
                'кусок не попадает.\n\n'
                'Здесь появляется новый тип — **список** (`list`). Всерьёз мы '
                'займёмся им в блоке 9, а пока хватит трёх фактов, и все три '
                'уже знакомы по строкам:\n\n'
                '- список печатается в квадратных скобках: '
                '`[\'2026\', \'08\', \'01\']`;\n'
                '- к элементу обращаются по индексу с нуля — `parts[0]`, и '
                'отрицательные индексы работают так же: `parts[-1]` — '
                'последний;\n'
                '- длину даёт `len()`, а перебрать элементы можно циклом '
                '`for` — ровно как символы строки в уроке 8.1.\n\n'
                'Главное правило блока 8 никуда не делось: `split()` исходную '
                'строку не трогает, а строит результат рядом. Не присвоили — '
                'потеряли.\n\n'
                'И следствие, которое стоит запомнить сразу: **частей всегда '
                'на одну больше, чем разделителей.** Два дефиса в дате — три '
                'части. Это тот же счёт, что и «между n кусками n − 1 стыков», '
                'и к нему мы вернёмся, когда дойдём до `join()`.'
            )),
            dict(order=3, block_type='code', title='', code_language='python', content=(
                "s = '2026-08-01'\n"
                "parts = s.split('-')\n"
                '\n'
                "print(parts)           # ['2026', '08', '01'] — список из трёх строк\n"
                'print(parts[0])        # 2026 — первый элемент, индекс с нуля\n'
                'print(parts[-1])       # 01 — последний, как и у строки\n'
                'print(len(parts))      # 3 — столько частей получилось\n'
                '\n'
                "row = 'Иванов;9А;5'\n"
                "print(row.split(';'))  # ['Иванов', '9А', '5']\n"
                '\n'
                'print(s)               # 2026-08-01 — исходная строка не изменилась'
            )),
            dict(order=4, block_type='text', title='Два разных split()', content=(
                'Главная развилка урока: `split()` без аргумента и '
                '`split(sep)` — это **не одно и то же с умолчанием**, а два '
                'разных поведения.\n\n'
                '`s.split(sep)` — строгий. Режет по каждому вхождению `sep` и '
                'ничего не додумывает. Два разделителя подряд дают между собой '
                '**пустую строку**, разделитель в начале или в конце — пустую '
                'строку с краю. Это не недоразумение: в таблице пустое поле — '
                'тоже значение, и терять его нельзя.\n\n'
                '`s.split()` без аргумента — «человеческий». Разделителем '
                'считается любая цепочка пробельных символов (пробел, `\\t`, '
                '`\\n`), несколько подряд идут за один, а пробелы по краям '
                'просто отбрасываются. Пустых кусков в результате не бывает '
                'никогда. Это готовый инструмент «разбей предложение на слова», '
                'и для текста берут именно его.\n\n'
                'Контрольный пример, который стоит увидеть глазами: у строки '
                '`\'  мама  мыла   раму \'` вызов `.split()` даёт три слова, а '
                '`.split(\' \')` — девять элементов, шесть из которых пустые.'
            )),
            dict(order=5, block_type='code', title='', code_language='python', content=(
                "s = '  мама  мыла   раму '\n"
                '\n'
                "print(s.split())              # ['мама', 'мыла', 'раму']\n"
                'print(len(s.split()))         # 3 — цепочка пробелов идёт за один\n'
                '                              # разделитель, края отброшены\n'
                '\n'
                "print(s.split(' '))           # ['', '', 'мама', '', 'мыла', '', '', 'раму', '']\n"
                "print(len(s.split(' ')))      # 9 — режет каждый пробел, шесть кусков пустые\n"
                '\n'
                "print('a,,b'.split(','))      # ['a', '', 'b'] — между запятыми пустой кусок\n"
                "print(';Иванов;'.split(';'))  # ['', 'Иванов', ''] — и по краям тоже"
            )),
            # Иллюстрация: плоский минималистичный стиль, как в блоках 2, 5–8.
            # Два ряда, один под другим, слева от каждого подпись: сверху
            # `.split(' ')`, снизу `.split()`.
            # В обоих рядах — одна и та же лента '  мама  мыла   раму ',
            # разложенная по клеткам, пробельные клетки помечены серым значком
            # пробела.
            # Верхний ряд: вертикальные ножницы стоят у КАЖДОГО пробела; под
            # лентой — девять получившихся кусков, пустые нарисованы как пустые
            # рамки и подсвечены красноватым.
            # Нижний ряд: ножницы стоят по одному разу на КАЖДУЮ ЦЕПОЧКУ
            # пробелов, краевые пробелы затемнены как отброшенные; под лентой —
            # три куска «мама», «мыла», «раму».
            # Главный смысл картинки: разница не в количестве пробелов в строке,
            # а в том, что считать одним разделителем.
            dict(order=6, block_type='image', title='', content=(
                'Одна и та же строка, разрезанная двумя способами: '
                '`split(\' \')` режет по каждому пробелу и оставляет пустые '
                'куски, а `split()` без аргумента считает цепочку пробелов '
                'одним разделителем и отбрасывает краевые.'
            )),
            dict(order=7, block_type='text', title='Ограничение числа разрезов и чего split() не умеет', content=(
                'Третий полезный факт: второй параметр `s.split(sep, maxsplit)` '
                'ограничивает **число разрезов**, а не число кусков — весь '
                'остаток целиком уезжает в последний элемент. Пример по делу: '
                '`\'ivan@mail.ru\'.split(\'@\', 1)` даёт логин и всё '
                'остальное — даже если правее встретится ещё один `@`.\n\n'
                'Чего от `split()` ждать не надо:\n\n'
                '- **несколько разных разделителей за раз** — не умеет. Строку '
                '`\'Иванов, Петров; Сидоров\'` одним вызовом не разберёшь: '
                'сначала `replace()` из урока 8.4 приводит разделители к '
                'одному виду, и только потом `split()`;\n'
                '- **пробелы вокруг частей `split(sep)` не убирает** — '
                '`\'Иванов; 9А;5\'.split(\';\')` даёт кусок `\' 9А\'` вместе с '
                'пробелом. Отсюда обычная связка с уроком 8.5: разрезали — и к '
                'каждой части `strip()`;\n'
                '- **вложенности он не понимает.** В настоящем файле-таблице '
                'поле может быть взято в кавычки, а внутри кавычек стоять '
                'запятая; `split(\',\')` разрежет и её. Для таких файлов есть '
                'отдельные инструменты (блок 19), а `split()` хорош там, где '
                'разделитель честно один.'
            )),
            dict(
                order=8, block_type='widget',
                title='Что split() делает на самом деле',
                content=(
                    '`split()` — не отдельная магия, а тот же перебор, что в '
                    'уроках 8.3 и 8.4. Программа ищет очередной разделитель '
                    'через `find()`, отрезает срезом кусок до него и переносит '
                    'начало за разделитель. Пройдите трассу по шагам и '
                    'посмотрите на две вещи: разделитель не попадает ни в один '
                    'кусок — его съедает правая граница среза, — а последний '
                    'кусок берётся уже без всякого `find()`, просто «всё, что '
                    'осталось справа». Отсюда и правило «частей на одну больше, '
                    'чем разделителей».'
                ),
                widget_key='loop-trace',
                widget_config={
                    'code': SPLIT_CODE,
                    'vars': ['s', 'sep', 'start', 'pos', 'n'],
                    'steps': _split_trace(),
                },
            ),
            dict(order=9, block_type='text', title='join(): собрать обратно', content=(
                'Обратная операция.\n\n'
                '> `sep.join(parts)` возвращает **новую строку**: все элементы '
                '`parts` подряд, а между соседними — строка `sep`.\n\n'
                'И сразу странность синтаксиса, на которой спотыкаются все: '
                'метод вызывается **у разделителя**, а список идёт в скобки. '
                'Пишут `\'-\'.join(parts)`, а не `parts.join(\'-\')`.\n\n'
                'Выглядит вывернуто, но логика есть. `join()` — метод типа '
                '`str`, потому что результат у него строка, и главное решение '
                '(чем склеивать) принимает именно разделитель. А в скобках '
                'может оказаться что угодно, что перебирается по элементам: '
                'список сегодня, другие типы — в блоке 13. Один метод у строки '
                'покрывает их все.\n\n'
                'Второе правило, о которое спотыкаются не реже: **все элементы '
                'должны быть строками**. `\'-\'.join([\'a\', \'b\'])` работает, '
                'а `\'-\'.join([2026, 8, 1])` падает с `TypeError: sequence '
                'item 0: expected str instance, int found` — «ожидалась строка, '
                'получено целое». Числа перед сборкой приводят к строке через '
                '`str()`, знакомый по уроку 1.8.\n\n'
                'Частные случаи, которые пригодятся:\n\n'
                '- `\' \'.join(...)` — собрать слова в предложение;\n'
                '- `\'\'.join(...)` — склеить вообще без разделителя: пустая '
                'строка тоже полноценный разделитель;\n'
                '- если элемент один, разделитель не появится вообще, а пустой '
                'список даст пустую строку. Разделитель ставится **между**, а '
                'не после каждого.'
            )),
            dict(order=10, block_type='code', title='', code_language='python', content=(
                "print('-'.join(['2026', '08', '01']))      # 2026-08-01\n"
                "print(' '.join(['мама', 'мыла', 'раму']))  # мама мыла раму\n"
                "print(''.join(['м', 'и', 'р']))            # мир — пустой разделитель\n"
                '                                           # тоже разделитель\n'
                '\n'
                "print('-'.join(['одно']))                  # одно — разделителю негде\n"
                '                                           # появиться\n'
                '\n'
                "print('-'.join([2026, 8, 1]))\n"
                '# TypeError: sequence item 0: expected str instance, int found\n'
                "print('-'.join([str(2026), str(8), str(1)]))   # 2026-8-1 — вот так честно\n"
                '\n'
                "parts = ['2026', '08', '01']\n"
                "print(parts.join('-'))\n"
                "# AttributeError: 'list' object has no attribute 'join'"
            )),
            # Иллюстрация: плоский минималистичный стиль, как в блоках 2, 5–8.
            # В центре — три прямоугольника-куска «2026», «08», «01» в ряд,
            # между ними два кружка с символом «-», подписанные «стык 1» и
            # «стык 2». Справа от края последнего куска — перечёркнутый бледный
            # кружок с подписью «а здесь разделителя нет».
            # Под кусками — собранная лента «2026-08-01».
            # Сверху крупной подписью формула: «3 части → 2 разделителя».
            # Хорошо бы замкнуть цикл двумя тонкими стрелками сбоку: от ленты
            # вверх к кускам стрелка с подписью split('-'), от кусков вниз к
            # ленте — с подписью '-'.join(...).
            # Главный смысл картинки: join() кладёт разделитель в промежутки
            # между кусками, а их всегда на один меньше, чем самих кусков.
            dict(order=11, block_type='image', title='', content=(
                '`join()` ставит разделитель **между** кусками, а не после '
                'каждого: у трёх частей стыков всего два. Поэтому строка, '
                'разрезанная `split(\'-\')` и собранная `\'-\'.join(...)`, '
                'получается ровно такой же, какой была.'
            )),
            dict(order=12, block_type='text', title='split() → обработка → join()', content=(
                'Эти два метода почти всегда работают в паре: строку разрезали, '
                'с кусками что-то сделали, собрали обратно. Такой конвейер — '
                'основной способ обработки текста, и дальше в учебнике он будет '
                'встречаться постоянно.\n\n'
                'Здесь же отдадим долг из урока 8.1. Мы обещали, что правильный '
                'инструмент для сборки длинной строки — `join()`, а не склейка '
                '`result = result + ch` в цикле. Причина в неизменяемости: '
                'каждая склейка строит новую строку и копирует в неё всё уже '
                'накопленное, поэтому в длинном цикле работа растёт как снежный '
                'ком. `join()` знает все куски заранее, считает нужный размер '
                'один раз и собирает результат за один проход.\n\n'
                'На словах из шести букв разницы не увидеть, на сотнях тысяч '
                'кусков она принципиальная — измерить её мы сможем в блоке 10, '
                'когда появится язык для разговора о скорости. Пока достаточно '
                'правила: **если строка собирается в цикле — почти всегда её '
                'надо собирать `join()`-ом.**'
            )),
            dict(order=13, block_type='code', title='', code_language='python', content=(
                '# 1. переставить дату: 2026-08-01 -> 01.08.2026\n'
                "s = '2026-08-01'\n"
                "p = s.split('-')\n"
                "print('.'.join([p[2], p[1], p[0]]))   # 01.08.2026\n"
                '\n'
                '# 2. слова предложения задом наперёд\n'
                "text = 'мама мыла раму'\n"
                "print(' '.join(text.split()[::-1]))   # раму мыла мама\n"
                '                                      # срез с шагом -1 из урока 8.2\n'
                '                                      # работает и со списком: это\n'
                '                                      # тоже последовательность\n'
                '\n'
                '# 3. нормализация ввода: убрать все лишние пробелы разом\n'
                "dirty = '  мама  мыла   раму '\n"
                "print(' '.join(dirty.split()))        # мама мыла раму"
            )),
            dict(order=14, block_type='text', title='f-строки: подставить значение прямо в текст', content=(
                'Третья тема урока, и заходим в неё через собственную боль из '
                'урока 1.8. Там, чтобы напечатать «Тебе 16 лет», приходилось '
                'писать `\'Тебе \' + str(age) + \' лет\'`: не забыть `str()`, не '
                'потерять пробелы у краёв кусков, не запутаться в кавычках. '
                'Одно предложение так собрать можно, а строку отчёта из пяти '
                'значений — уже мучение, и читать её невозможно.\n\n'
                '> **f-строка** — строка, перед кавычкой которой стоит буква '
                '`f`. Внутри неё в фигурных скобках `{}` можно написать '
                'выражение — при выполнении на его место подставится '
                'значение.\n\n'
                'Что это даёт:\n\n'
                '- **`str()` не нужен** — в скобки можно поставить число, и оно '
                'превратится в текст само;\n'
                '- **в скобках любое выражение**, а не только имя переменной: '
                '`{a + b}`, `{name.upper()}`, `{parts[0]}`, `{len(s)}`;\n'
                '- **текст остаётся текстом** — пробелы и знаки препинания '
                'видно там же, где они окажутся в выводе.\n\n'
                'Отдельно — форматирование числа. После выражения можно '
                'поставить двоеточие и указать, как его печатать: '
                '`{x:.2f}` — вещественное с двумя знаками после запятой. Это '
                'ровно тот случай, ради которого стоит вспомнить урок 5.3: '
                '`0.1 + 0.2` печатается как `0.30000000000000004`, а нужны нам '
                'обычно не все эти цифры, а две.\n\n'
                'Две ловушки:\n\n'
                '- **забыли `f`** — ошибки не будет, программа честно напечатает '
                '`{age}` фигурными скобками. Симптом узнаваемый;\n'
                '- **нужна сама фигурная скобка в тексте** — её удваивают: '
                '`{{` и `}}`.\n\n'
                'И оговорка про чужой код: старые способы форматирования '
                '(`\'%d\'` и метод `.format()`) в нём встречаются, и знать об их '
                'существовании полезно, — но писать сегодня надо f-строки.'
            )),
            dict(order=15, block_type='code', title='', code_language='python', content=(
                'age = 16\n'
                "name = 'Иван'\n"
                '\n'
                "print('Тебе ' + str(age) + ' лет')   # Тебе 16 лет — способ из урока 1.8\n"
                "print(f'Тебе {age} лет')             # Тебе 16 лет — то же самое f-строкой\n"
                '\n'
                'a = 2\n'
                'b = 3\n'
                "print(f'{a} + {b} = {a + b}')        # 2 + 3 = 5 — в скобках выражение\n"
                "print(f'Привет, {name.upper()}!')    # Привет, ИВАН!\n"
                '\n'
                "print(f'{0.1 + 0.2}')                # 0.30000000000000004 — привет из 5.3\n"
                "print(f'{0.1 + 0.2:.2f}')            # 0.30 — два знака после запятой\n"
                '\n'
                "print('Тебе {age} лет')              # Тебе {age} лет — забыли f, и скобки\n"
                '                                     # напечатались как обычный текст\n'
                "print(f'{{это не подстановка}}')     # {это не подстановка}\n"
                '\n'
                "p = '2026-08-01'.split('-')\n"
                "print(f'{p[2]}.{p[1]}.{p[0]}')       # 01.08.2026 — и конвейер туда же"
            )),
            dict(order=16, block_type='text', title='Шпаргалка', content=(
                '| Запись | Что вернёт | На что смотреть |\n'
                '|---|---|---|\n'
                '| `s.split()` | список слов | цепочка пробелов = один разделитель, края отброшены, пустых кусков не бывает |\n'
                '| `s.split(sep)` | список кусков | режет каждое вхождение; подряд идущие `sep` дают пустые строки |\n'
                '| `s.split(sep, n)` | не больше `n + 1` куска | ограничивает число разрезов, остаток уезжает в последний кусок |\n'
                '| `sep.join(parts)` | новую строку | вызывается **у разделителя**; все элементы обязаны быть строками |\n'
                '| `f\'…{x}…\'` | новую строку | `str()` не нужен, в скобках любое выражение |\n'
                '| `f\'{x:.2f}\'` | новую строку | два знака после запятой |\n\n'
                'И то, что верно для всей таблицы и для всего блока 8: ни одна '
                'из этих записей исходную строку не меняет. Все шесть '
                'возвращают новое значение, и его надо куда-то присвоить — '
                'иначе оно просто пропадёт.'
            )),
            dict(order=17, block_type='text', title='Итог и мостик к 8.7', content=(
                'Все три примера из начала урока разбираются теперь в одну '
                'строку: дата — `split(\'-\')`, строка таблицы — '
                '`split(\';\')`, предложение — `split()` без аргумента.\n\n'
                'Что стоит вынести:\n\n'
                '- `split()` разрезает строку по разделителю и возвращает '
                '**список**; сам разделитель в куски не попадает, а частей '
                'всегда на одну больше, чем разделителей;\n'
                '- `split()` без аргумента и `split(sep)` — разные инструменты: '
                'первый для текста, второй для данных с точным разделителем, и '
                'только второй оставляет пустые куски;\n'
                '- `join()` вызывается **у разделителя**, а элементы обязаны '
                'быть строками; разделитель ставится между кусками, а не после '
                'каждого;\n'
                '- собирать строку в цикле склейкой не надо — для этого есть '
                '`join()`;\n'
                '- f-строка подставляет значение выражения прямо в текст, без '
                '`str()` и плюсов; забытая `f` не даёт ошибки, а печатает '
                'фигурные скобки.\n\n'
                'До сих пор каждый урок блока давал новый инструмент: индекс, '
                'срез, `in`, `find()`, `lower()`, теперь `split()` и `join()`. '
                'Инструментов накопилось достаточно, и в уроке 8.7 мы наконец '
                'перестанем их изучать и начнём ими **решать**: найдём самую '
                'длинную цепочку одинаковых символов, проверим строку на '
                'палиндром (очистка из виджета урока 8.5 — как раз первый шаг) '
                'и выясним, являются ли два слова анаграммами. Ни для одной из '
                'этих задач готового метода нет — придётся собирать своё из '
                'того, что уже есть.'
            )),
        ])

        quiz = _self_check(
            slug='self-check-razbienie-i-sborka',
            title='Самопроверка: разбиение и сборка',
            description='Три коротких вопроса по теме урока.',
            questions=[
                dict(
                    type='choice',
                    text="Что вернёт выражение `'a,,b'.split(',')`?",
                    choices=[
                        ("['a', '', 'b'] — три элемента: между двумя запятыми "
                         'подряд оказался пустой кусок', True),
                        ("['a', 'b'] — пустые куски split() пропускает", False),
                        ("['a', ',', 'b'] — разделитель попадает в результат", False),
                        ('Ошибку — два разделителя подряд недопустимы', False),
                    ],
                ),
                dict(
                    type='choice',
                    text=(
                        'Программа выполняет две строки:\n\n'
                        '```python\n'
                        "parts = ['2026', '08', '01']\n"
                        "print(parts.join('-'))\n"
                        '```\n\n'
                        'Что произойдёт?'
                    ),
                    choices=[
                        ('Ошибка AttributeError: join() — метод строки, и '
                         "вызывать его надо у разделителя: '-'.join(parts)", True),
                        ('Напечатает 2026-08-01 — порядок вызова не важен', False),
                        ("Напечатает ['2026', '08', '01'] — метод не сработает, "
                         'но и ошибки не будет', False),
                        ('Ошибка TypeError: элементы списка не строки', False),
                    ],
                ),
                dict(
                    type='text',
                    text=(
                        "Сколько элементов будет в списке `'2026-08-01'.split('-')`? "
                        'Впишите только число.'
                    ),
                    correct_text_answer='3',
                ),
            ],
        )
        ArticleQuiz.objects.get_or_create(
            article=article, quiz=quiz,
            defaults={'label': 'Проверь себя', 'order': 1},
        )

    def seed_8_7(self):
        article = Article.objects.get(slug='8-7-algoritmicheskie-zadachi-so-strokami')
        article.description = (
            'Три задачи, для которых готового метода нет: самая длинная '
            'цепочка одинаковых символов, палиндром и анаграмма. Ни одного '
            'нового инструмента — только те, что дал блок 8, плюс общая схема '
            '«нормализовать — пройти один раз — накопить ответ» и разбор краёв, '
            'на которых такие решения ломаются.'
        )
        article.save(update_fields=['description'])

        _replace_blocks(article, [
            dict(order=1, block_type='text', title='Готовых методов больше нет', content=(
                'Весь блок 8 был устроен одинаково: возникала задача — '
                'находился метод. «Найти подстроку» — `find()`. «Убрать '
                'пробелы по краям» — `strip()`. «Разрезать по разделителю» — '
                '`split()`. Этот урок схему ломает. Вот три задачи, для '
                'которых готового метода нет и не будет:\n\n'
                '- найти самую длинную цепочку одинаковых символов подряд: в '
                '`\'ААБВВВВГ\'` это 4;\n'
                '- проверить, палиндром ли строка: «А роза упала на лапу '
                'Азора» — да, хотя пробелы и заглавные буквы мешают увидеть '
                'это сразу;\n'
                '- проверить, анаграммы ли два слова: «апельсин» и '
                '«спаниель» — да.\n\n'
                'Инструменты кончились — начинается алгоритм. Но заметьте: ни '
                'одного нового инструмента в уроке не появится. Всё, чем мы '
                'будем решать, уже лежит в руках: индекс, срез, `in`, '
                '`count()`, `lower()`, `isalpha()` и обычный цикл.\n\n'
                'Прежде чем читать дальше, попробуйте объяснить словами: как '
                '**вы сами**, глазами, проверяете, палиндром перед вами или '
                'нет? Почти наверняка вы делаете два разных дела — сначала '
                'мысленно выбрасываете пробелы и запятые, а потом читаете с '
                'двух концов. Дальше в уроке эти два дела станут двумя частями '
                'программы.'
            )),
            dict(order=2, block_type='text', title='Общий приём: один проход и накопитель', content=(
                'Вернёмся к уроку 4.8. Там мы искали минимум и максимум в '
                'диапазоне чисел, не запоминая весь диапазон: держали одну '
                'переменную-накопитель и обновляли её на каждом шаге. Со '
                'строкой всё то же самое, только вместо чисел — символы.\n\n'
                'Схема, к которой сведутся все три задачи урока:\n\n'
                '1. **нормализовать** — привести строку к виду, в котором '
                'сравнение честное (регистр, лишние символы);\n'
                '2. **пройти один раз** слева направо;\n'
                '3. **накопить ответ** в переменных, которые живут между '
                'шагами цикла.\n\n'
                'Переменные-накопители — это память программы о том, что она '
                'уже видела. Строка неизменяема, возвращаться назад и '
                'перечитывать её заново не хочется, значит всё, что '
                'понадобится в конце, надо копить по дороге.\n\n'
                'И сразу честное предупреждение: почти вся сложность таких '
                'задач не в основной идее, а в **краях** — первом символе, '
                'последнем символе и пустой строке. Идею придумывают за '
                'минуту, а ломается решение всегда там.'
            )),
            dict(order=3, block_type='text', title='Задача 1. Самая длинная цепочка одинаковых символов', content=(
                'Постановка: дана строка, надо найти длину самой длинной '
                'группы одинаковых символов, идущих подряд. В `\'ААБВВВВГ\'` '
                'ответ 4 (четыре «В»), в `\'абвгд\'` — 1, в пустой строке — '
                '0.\n\n'
                'Идея. Идём по строке начиная со **второго** символа и на '
                'каждом шаге задаём один вопрос: «этот символ такой же, как '
                'предыдущий?»\n\n'
                '- **да** — текущая цепочка продолжается, её длина растёт на '
                '1;\n'
                '- **нет** — цепочка оборвалась, начинается новая, и в ней '
                'пока один символ.\n\n'
                'Отсюда две переменные:\n\n'
                '- `cur` — длина цепочки, которая идёт **прямо сейчас**;\n'
                '- `best` — самая длинная из всех, что уже встретились.\n\n'
                'Правило, которое стоит запомнить дословно: сначала обнови '
                '`cur`, а потом **сразу** сверь его с `best` — на каждом шаге, '
                'а не в момент обрыва цепочки. Почему именно так, разберём '
                'чуть ниже: это главная ловушка задачи.\n\n'
                'Сравнение соседей — это `s[i] == s[i - 1]`, и здесь работает '
                'ровно то, что дал урок 8.1: символ достаётся по индексу, '
                'строку при этом никто не меняет.'
            )),
            # Иллюстрация: плоский минималистичный стиль, как в блоках 2, 5–8.
            # Сверху лента строки 'ААБВВВВГ', разложенная по клеткам; каждая
            # цепочка одинаковых символов залита своим цветом (АА — один цвет,
            # Б — второй, ВВВВ — третий, Г — четвёртый), границы между
            # цепочками отмечены вертикальными разделителями.
            # Под лентой две дорожки-строки, подписанные слева именами
            # переменных, значения выровнены строго под клетками:
            #   cur :  1  2  1  1  2  3  4  1
            #   best:  1  2  2  2  2  3  4  4
            # Значения best, где он вырос, выделены (жирнее/ярче) — видно, что
            # это ступенька, которая только растёт и никогда не падает.
            # Справа от ленты крупная плашка «ответ 4».
            # Главный смысл картинки: cur живёт внутри одной цепочки и
            # сбрасывается на её границе, а best живёт над всей строкой.
            dict(order=4, block_type='image', title='', content=(
                'Строка разбита на цепочки одинаковых символов. `cur` растёт '
                'внутри цепочки и сбрасывается в 1 на её границе, а `best` '
                'запоминает лучшее из уже увиденного и никогда не '
                'уменьшается.'
            )),
            dict(order=5, block_type='code', title='', code_language='python', content=(
                "s = 'ААБВВВВГ'\n"
                '\n'
                'best = 0                   # ответ для пустой строки уже готов\n'
                'cur = 0\n'
                'if len(s) > 0:\n'
                '    best = 1               # первый символ — цепочка длиной 1\n'
                '    cur = 1\n'
                '\n'
                'for i in range(1, len(s)):  # со второго символа: у первого нет\n'
                '    if s[i] == s[i - 1]:    # предыдущего, сравнивать не с чем\n'
                '        cur = cur + 1      # цепочка продолжается\n'
                '    else:\n'
                '        cur = 1            # началась новая, в ней один символ\n'
                '    if cur > best:         # сверяем на каждом шаге, а не\n'
                '        best = cur         # в момент обрыва цепочки\n'
                '\n'
                'print(best)                # 4\n'
                '\n'
                '# та же программа на других строках:\n'
                "#   'абвгд'   -> 1   ни одна пара соседей не совпала\n"
                "#   'ААБВВВВ' -> 4   цепочка упирается в конец строки\n"
                "#   ''        -> 0   цикл не выполнился ни разу"
            )),
            dict(
                order=6, block_type='widget',
                title='Как накопители догоняют самую длинную цепочку',
                content=(
                    'Пройдите трассу по шагам и проследите за двумя вещами. '
                    'Первая — `best` никогда не уменьшается: он запоминает '
                    'рекорд, а не текущее состояние, и потому спокойно '
                    'переживает обрыв цепочки. Вторая — посмотрите, в какой '
                    'момент `best` дорастает до четвёрки: не тогда, когда '
                    'цепочка «В» обрывается буквой «Г», а ещё внутри неё, на '
                    'четвёртой «В». Именно поэтому цепочке необязательно '
                    'обрываться — она может упираться прямо в конец строки, и '
                    'решение её не потеряет.'
                ),
                widget_key='loop-trace',
                widget_config={
                    'code': CHAIN_CODE,
                    'vars': ['s', 'i', 's[i]', 'cur', 'best'],
                    'steps': _max_chain_trace(),
                },
            ),
            dict(order=7, block_type='text', title='Три края, на которых решение ломается', content=(
                'Идея заняла абзац, а вот три места, где её легко испортить.\n\n'
                '**1. Последняя цепочка.** Соблазн — обновлять `best` в момент '
                'обрыва цепочки: «кончилась — подвели итог». На `\'ААБВВВВГ\'` '
                'это ещё сработает, а на `\'ААБВВВВ\'` — нет: последняя '
                'цепочка ничем не обрывается, строка просто кончается, и итог '
                'по ней никто не подведёт. Программа ответит 2 вместо 4. '
                'Лечение — сверять на каждом шаге, тогда особого случая «конец '
                'строки» просто не существует.\n\n'
                '**2. Первый символ.** У него нет предыдущего. И `s[i - 1]` '
                'при `i = 0` даст не ошибку, а **последний символ строки** — '
                'отрицательный индекс из урока 8.2 сработает молча и испортит '
                'ответ: на строке `\'АБА\'` программа решит, что первая и '
                '«предыдущая» буквы совпали. Поэтому цикл начинается с 1, а '
                'первый символ учтён заранее как цепочка длиной 1.\n\n'
                '**3. Пустая строка.** Цикл не выполнится ни разу, и `best` '
                'останется тем, чем его назначили. Напишешь `best = 1` без '
                'проверки — программа сообщит о цепочке в строке, где нет ни '
                'одного символа.\n\n'
                'Общая мораль, которая пригодится и дальше: краевые случаи — '
                'не редкая экзотика, а обязательная часть проверки. Три '
                'вопроса к любой готовой программе: что будет на пустом входе, '
                'что на входе из одного элемента и что, если ответ лежит в '
                'самом конце.'
            )),
            dict(order=8, block_type='text', title='Задача 2. Палиндром', content=(
                '> **Палиндром** — текст, который читается одинаково слева '
                'направо и справа налево.\n\n'
                'Со словом `\'шалаш\'` всё просто. С «А роза упала на лапу '
                'Азора» — нет: там пробелы и две заглавные буквы. Для '
                'человека это не помеха, а для программы `\'А\' == \'а\'` — '
                'ложь: это два разных символа с разными кодами (уроки 8.1 и '
                '8.5).\n\n'
                'Поэтому решение делится на два независимых шага, и путать их '
                'не надо:\n\n'
                '1. **нормализация** — оставить только буквы и привести их к '
                'одному регистру;\n'
                '2. **проверка** — сравнить получившееся с самим собой '
                'наоборот.\n\n'
                'Первый шаг у нас уже написан: это ровно тот цикл, который '
                'трассировал виджет урока 8.5 — идём по символам, спрашиваем у '
                'каждого `isalpha()`, подходящие приклеиваем в нижнем регистре '
                'к новой строке.\n\n'
                'И честная оговорка. В уроке 8.6 мы сказали, что собирать '
                'строку в цикле склейкой не надо и правильный инструмент — '
                '`join()`. Это по-прежнему правда, но чтобы собрать для '
                '`join()` список кусков, нужен метод `append()`, а списками мы '
                'всерьёз займёмся в блоке 9. Так что сейчас собираем '
                'склейкой — сознательно и понимая, что это не окончательный '
                'вариант.'
            )),
            dict(order=9, block_type='code', title='', code_language='python', content=(
                "text = 'А роза упала на лапу Азора'\n"
                '\n'
                "clean = ''\n"
                'for c in text:\n'
                '    if c.isalpha():            # знаки и пробелы отбрасываем\n'
                '        clean = clean + c.lower()\n'
                '\n'
                'print(clean)                   # арозаупаланалапуазора\n'
                'print(clean[::-1])             # арозаупаланалапуазора — та же строка\n'
                'print(clean == clean[::-1])    # True\n'
                '\n'
                "print('привет' == 'привет'[::-1])   # False — тевирп это не привет\n"
                '\n'
                "print('' == ''[::-1])          # True — переворачивать нечего\n"
                "print('я' == 'я'[::-1])        # True — и в строке из одного символа тоже"
            )),
            dict(order=10, block_type='text', title='Второй способ: два конца навстречу', content=(
                'Разумный вопрос: если `clean == clean[::-1]` решает задачу '
                'одной строкой, зачем что-то ещё?\n\n'
                'Затем, что срез `[::-1]` **строит новую строку целиком** — '
                'копию всей исходной, до последнего символа, — и только потом '
                'сравнивает. Человек, проверяя палиндром глазами, так не '
                'делает: он берёт первую и последнюю буквы, сравнивает, '
                'сдвигается к центру и **останавливается на первом же '
                'несовпадении**. У слова `\'арбуз\'` первая буква «а», '
                'последняя «з» — ответ известен после одного сравнения, '
                'остальные три буквы можно не смотреть.\n\n'
                'Приём называется **два указателя**: переменная `i` идёт слева '
                'направо, `j` — справа налево, работа продолжается, пока '
                '`i < j`. Как только `s[i] != s[j]`, ответ `False` и `break`. '
                'Если указатели встретились — все пары совпали, ответ '
                '`True`.\n\n'
                'Два наблюдения, ради которых этот способ и стоит увидеть:\n\n'
                '- сравнений делается вдвое меньше, чем символов в строке: '
                'каждая пара проверяется один раз, а середина — точка встречи, '
                'а не место, до которого надо дойти;\n'
                '- на нечётной длине центральный символ не проверяется вообще, '
                'и это правильно: сравнивать его не с чем.\n\n'
                'Какой из двух способов писать в реальной программе? Обычно '
                'первый — он короче и читается мгновенно. Второй важен как '
                '**приём**, а не как код: «двумя концами навстречу» мы ещё '
                'вернёмся, когда дойдём до списков и сортировок.'
            )),
            dict(
                order=11, block_type='widget',
                title='Два указателя навстречу',
                content=(
                    'Та же проверка палиндрома, но без среза: два указателя '
                    'идут навстречу друг другу по уже очищенной строке. '
                    'Следите за тем, где цикл останавливается. Он не доходит '
                    'до конца строки — указатели встречаются в середине, и на '
                    'этом работа закончена: вторая половина строки уже '
                    'проверена, просто с другой стороны.'
                ),
                widget_key='loop-trace',
                widget_config={
                    'code': PALINDROME_CODE,
                    'vars': ['s', 'i', 'j', 'ok'],
                    'steps': _palindrome_trace(),
                },
            ),
            dict(order=12, block_type='text', title='Задача 3. Анаграмма', content=(
                '> **Анаграммы** — два слова, составленные из одних и тех же '
                'букв в одинаковом количестве, но в разном порядке.\n\n'
                '«Апельсин» и «спаниель» — анаграммы. «Апельсин» и '
                '«спаниели» — уже нет.\n\n'
                'Прежде чем писать решение, полезно разобрать две неверные '
                'идеи — обе выглядят убедительно.\n\n'
                '**Неверная идея 1: «проверим, что каждая буква первого слова '
                'есть во втором».** Ломается на паре «кот» и «коты»: каждая '
                'буква слова «кот» во втором слове есть, но анаграммами они не '
                'являются. Проверка по вхождению теряет **количество** — она '
                'не отличает «есть» от «столько же».\n\n'
                '**Неверная идея 2: «сравним длины».** У анаграмм длины '
                'действительно равны — но у «кот» и «кит» они тоже равны. '
                'Равенство длин необходимо, но недостаточно.\n\n'
                'Верный признак объединяет обе половины: слова — анаграммы, '
                'если **каждая буква встречается в них одинаковое число раз**. '
                'А считать вхождения мы умеем с урока 8.4 — это `count()`.\n\n'
                'Достаточно ли пройтись по буквам первого слова и сверить '
                'счётчики? Почти. Разберём «кот» и «коты» ещё раз: «к» — 1 и '
                '1, «о» — 1 и 1, «т» — 1 и 1, всё сошлось, а слова разные. '
                'Буква «ы» во втором слове есть, но в первом её нет, и цикл до '
                'неё просто не дошёл. Значит, проверка длин всё-таки нужна — '
                'не вместо счётчиков, а вместе с ними: она ловит лишние буквы, '
                'которых нет в первом слове.\n\n'
                'И нормализация никуда не делась: «Кот» и «ток» — анаграммы, '
                'но `\'К\'` и `\'к\'` для программы разные символы, поэтому '
                '`lower()` обязателен. Отдельная мелочь на будущее: «ё» и '
                '«е» — тоже разные символы, и решать, считать их одной буквой '
                'или нет, должен человек, а не программа.'
            )),
            dict(order=13, block_type='code', title='', code_language='python', content=(
                "a = 'Апельсин'.lower()\n"
                "b = 'Спаниель'.lower()\n"
                '\n'
                'ok = len(a) == len(b)          # разной длины — уже не анаграммы\n'
                '\n'
                'for c in a:\n'
                '    if a.count(c) != b.count(c):\n'
                '        ok = False             # эта буква встречается\n'
                '        break                  # разное число раз\n'
                '\n'
                'print(ok)                      # True\n'
                '\n'
                '# что даст та же программа на других парах:\n'
                "#   'кот'  / 'ток'  -> True\n"
                "#   'кот'  / 'кит'  -> False   счётчики о и и не сошлись\n"
                "#   'кот'  / 'коты' -> False   длины разные, и ok False с самого начала"
            )),
            dict(order=14, block_type='text', title='Почему это решение расточительное', content=(
                'Короткое, но честное замечание. Наше решение считает буквы '
                '**заново для каждого вхождения**. В слове «апельсин» все '
                'буквы разные, а вот в слове «колокол» буква «о» будет '
                'пересчитана три раза, и каждый `count()` — это ещё один '
                'полный проход по слову. На словах из восьми букв разницы не '
                'заметить, на текстах — уже да.\n\n'
                'Как делают правильно:\n\n'
                '- **отсортировать** обе строки и сравнить результаты: у '
                'анаграмм буквы, выстроенные по порядку, совпадут '
                'посимвольно. Функция `sorted()` появится в уроке 9.4, а как '
                'устроена сортировка внутри — это блок 11;\n'
                '- один раз посчитать все буквы в **словаре** «буква → сколько '
                'раз» и сравнить два словаря. Словари — блок 13.\n\n'
                'Оба способа проходят по слову фиксированное число раз, а не '
                'по разу на каждую букву. Мысль, которую стоит забрать: одна и '
                'та же задача почти всегда имеет несколько правильных решений, '
                'и различаются они не верностью ответа, а ценой. Язык для '
                'разговора об этой цене появится в блоке 10 — пока достаточно '
                'уметь замечать, что программа делает лишнюю работу.'
            )),
            dict(order=15, block_type='text', title='Что общего у трёх решений', content=(
                'Три разные задачи — одна схема:\n\n'
                '| Задача | Нормализация | Что копим по дороге | Ответ |\n'
                '|---|---|---|---|\n'
                '| Цепочка | не нужна | `cur` и `best` | значение `best` |\n'
                '| Палиндром | только буквы, нижний регистр | ничего — сравниваем целиком или парами | совпали ли все пары |\n'
                '| Анаграмма | нижний регистр | ничего — сверяем счётчики | сошлись ли все счётчики |\n\n'
                'Когда готового метода нет, задача решается не озарением, а '
                'разбором на три вопроса: что надо привести к общему виду '
                'перед сравнением, что нужно помнить между шагами цикла и на '
                'чём решение сломается по краям. Все три ответа собираются из '
                'инструментов, которые уже есть.'
            )),
            dict(order=16, block_type='text', title='Шпаргалка', content=(
                '| Задача | Идея в одну строку | Главная ловушка |\n'
                '|---|---|---|\n'
                '| Длина цепочки | сравнивай `s[i]` с `s[i-1]`, обновляй `cur`, сразу сверяй с `best` | обновлять `best` только при обрыве цепочки — теряется последняя |\n'
                '| Палиндром, коротко | `clean == clean[::-1]` | сравнивать без очистки — пробел и регистр всё портят |\n'
                '| Палиндром, приёмом | два указателя навстречу, пока `i < j` | забыть, что средний символ проверять не с чем |\n'
                '| Анаграмма | равные длины **и** `a.count(c) == b.count(c)` для всех букв `a` | проверять только счётчики — «кот» и «коты» пройдут |\n'
                '| Любая из них | — | не проверить края: пустую строку, один символ и ответ в самом конце |\n'
            )),
            dict(order=17, block_type='text', title='Итог урока и всего блока 8', content=(
                'Три задачи из начала урока решены, и ни для одной не нашлось '
                'готового метода — зато нашлись готовые кирпичи.\n\n'
                'Что стоит вынести:\n\n'
                '- накопитель — это память программы между шагами цикла; '
                '`cur` живёт внутри текущей цепочки, `best` — над всей '
                'строкой;\n'
                '- нормализация и сравнение — два разных шага, и смешивать их '
                'в одну кучу не надо;\n'
                '- срез `[::-1]` переворачивает строку целиком, а два '
                'указателя навстречу останавливаются на первом несовпадении: '
                'ответ один, цена разная;\n'
                '- равенство длин плюс совпадение счётчиков — полный признак '
                'анаграммы, по отдельности каждая половина ошибается;\n'
                '- любое готовое решение надо проверить на пустой строке, на '
                'строке из одного символа и на случае, когда ответ лежит в '
                'самом конце.\n\n'
                'И итог всего блока. Он начался с неожиданного факта: строку '
                'нельзя изменить, любая операция строит новую. Из этого '
                'выросло всё остальное — индексы и срезы, `in` и `find()`, '
                '`replace()` и `count()`, `upper()`, `lower()` и `strip()`, '
                '`split()`, `join()` и f-строки. Каждый урок добавлял '
                'инструмент, а последний показал, ради чего они собирались: из '
                'этого набора **уже можно составить собственный алгоритм** — '
                'такой, которого в языке нет и не будет, потому что задачи у '
                'всех разные, а кирпичи одни и те же.'
            )),
        ])

        quiz = _self_check(
            slug='self-check-algoritmicheskie-zadachi-so-strokami',
            title='Самопроверка: алгоритмические задачи со строками',
            description='Три коротких вопроса по теме урока.',
            questions=[
                dict(
                    type='choice',
                    text=(
                        'Программа ищет самую длинную цепочку одинаковых '
                        'символов, но обновляет best только в тот момент, '
                        'когда цепочка обрывается. Что она напечатает для '
                        "строки 'ААБВВВВ'?"
                    ),
                    choices=[
                        ('2 — цепочка из четырёх «В» ничем не обрывается, '
                         'строка просто кончается, и до best этот результат не '
                         'доходит', True),
                        ('4 — программа верна, ловушки здесь нет', False),
                        ('1 — best так и останется начальным значением', False),
                        ('Ошибку — индекс выйдет за границы строки', False),
                    ],
                ),
                dict(
                    type='choice',
                    text=(
                        'Почему проверки «каждая буква первого слова '
                        'встречается во втором» недостаточно, чтобы признать '
                        'слова анаграммами?'
                    ),
                    choices=[
                        ('Она не учитывает количество вхождений и лишние '
                         'буквы: пара «кот» и «коты» такую проверку пройдёт, '
                         'хотя анаграммами эти слова не являются', True),
                        ('Она не учитывает регистр, а больше ничего не '
                         'упускает', False),
                        ('Она работает только для слов одинаковой длины', False),
                        ('Она верна, просто работает слишком медленно', False),
                    ],
                ),
                dict(
                    type='text',
                    text=(
                        'Сколько символов останется от строки «А роза упала на '
                        'лапу Азора», если оставить в ней только буквы? '
                        'Впишите только число.'
                    ),
                    correct_text_answer='21',
                ),
            ],
        )
        ArticleQuiz.objects.get_or_create(
            article=article, quiz=quiz,
            defaults={'label': 'Проверь себя', 'order': 1},
        )
