"""Идемпотентный посев контента блока 8 «Строки, файлы и регулярные выражения».

Статьи-заголовки уже созданы командой seed_textbook_structure. Здесь
наполняем их блоками (ArticleBlock) и тестами самопроверки – урок за уроком.
Добавляя новый урок, дописывайте seed_8_N() и вызывайте её из handle().
"""
import random

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand
from django.db import transaction

from quizzes.models import (
    Choice, Question, QuestionFile, Quiz, TestCase, UserAnswer, UserResult,
)
from textbook.models import Article, ArticleBlock, ArticleProgress, ArticleQuiz, Section


from textbook.services import replace_blocks as _replace_blocks
from textbook.services import shuffle_choices as _shuffle_choices
from textbook.services import sync_question_texts as _sync_question_texts


def _self_check(slug, title, description, questions):
    """Создаёт (или обновляет) тест самопроверки с вопросами.

    Поддерживаемые ключи вопроса: type, text, title, choices,
    correct_text_answer, alternative_answers, hint,
    test_cases [(stdin, stdout)], files [(имя, содержимое)].
    """
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
    if not quiz.is_self_check or quiz.title != title or quiz.description != description:
        quiz.title, quiz.description, quiz.is_self_check = title, description, True
        quiz.save(update_fields=['title', 'description', 'is_self_check'])

    # Тест ещё никто не решал – пересоздаём вопросы, чтобы до базы доехали
    # и правки формулировок, и перемешанный порядок вариантов ответа.
    if quiz.questions.exists() and not UserAnswer.objects.filter(question__quiz=quiz).exists():
        quiz.questions.all().delete()

    if quiz.questions.count() == 0:
        for q in questions:
            question = Question.objects.create(
                quiz=quiz,
                question_type=q['type'],
                title=q.get('title', ''),
                text=q['text'],
                correct_text_answer=q.get('correct_text_answer', ''),
                alternative_answers=q.get('alternative_answers'),
                hint=q.get('hint', ''),
                points=1,
            )
            for choice_text, is_correct in _shuffle_choices(q['text'], q.get('choices', [])):
                Choice.objects.create(question=question, text=choice_text, is_correct=is_correct)
            for stdin, stdout in q.get('test_cases', []):
                TestCase.objects.create(question=question, input_data=stdin, output_data=stdout)
            for name, content in q.get('files', []):
                _attach_file(question, name, content)
    # Правки формулировок должны доезжать и до тестов, которые уже решали:
    # пересоздать вопросы там нельзя – каскад унёс бы ответы учеников.
    _sync_question_texts(quiz, questions)
    return quiz


def _attach_file(question, name, content):
    """Кладёт файл к задаче под точно тем именем, которое названо в условии.

    Имя обязано сохраниться: в контейнер файл попадает как
    `os.path.basename(qf.file.name)` (quizzes/tasks.py), и программа ученика
    открывает его по имени из условия. Django на коллизии дописывает суффикс
    (`chain_a_kT3x9.txt`), а старый файл при удалении вопроса остаётся на
    диске – то есть со второго прогона seed-команды имя разъехалось бы с
    условием, и у всех решений разом стало бы FileNotFoundError. Поэтому
    прошлый файл сносим из хранилища сами.
    """
    path = f'question_files/{name}'
    if default_storage.exists(path):
        default_storage.delete(path)
    # description пустое: шаблон печатает ссылку как «имя – описание», и
    # описание, равное имени, давало «chain_a.txt – chain_a.txt».
    QuestionFile.objects.create(
        question=question,
        file=ContentFile(content.encode('utf-8'), name=name),
    )


# Старые статьи блока: тема разбита иначе, слаги сменились. Пустых сирот
# подчищает seed_textbook_structure, но эти – с контентом, и он их намеренно
# не трогает. Чей-то прогресс чтения тут важнее нашей чистоты: если статью
# уже читали, снимаем с публикации и оставляем данные учителю.
_OBSOLETE = [
    '8-1-stroka-kak-neizmenyaemaya-posledovatelnost',
    '8-2-indeksatsiya-i-srezy',
    '8-3-operatsii-so-strokami',
    '8-4-metody-poiska-i-zameny',
    '8-5-metody-registra-i-proverki',
    '8-6-razbienie-i-sborka-split-i-join',
    '8-7-algoritmicheskie-zadachi-so-strokami',
]

_OBSOLETE_QUIZZES = [
    'self-check-stroka-neizmenyaemaya-posledovatelnost',
    'self-check-indeksatsiya-i-srezy',
    'self-check-operatsii-so-strokami',
    'self-check-metody-poiska-i-zameny',
    'self-check-metody-registra-i-proverki',
    'self-check-razbienie-i-sborka',
    'self-check-algoritmicheskie-zadachi-so-strokami',
]


def _retire_old_articles(stdout=None):
    kept = []
    for article in Article.objects.filter(slug__in=_OBSOLETE):
        if ArticleProgress.objects.filter(article=article).exists():
            if article.is_published:
                article.is_published = False
                article.save(update_fields=['is_published'])
            kept.append(article.slug)
        else:
            article.delete()
    for quiz in Quiz.objects.filter(slug__in=_OBSOLETE_QUIZZES):
        if not UserResult.objects.filter(quiz=quiz).exists():
            quiz.delete()
    if kept and stdout:
        stdout.write('Старые статьи с прогрессом чтения сняты с публикации, '
                     'но не удалены: ' + ', '.join(kept))


# Код, который трассирует loop-trace в уроке 8.2: обход всех вхождений
# подстроки через find() со вторым параметром. Показывает то, чего не умеет
# ни один метод по отдельности: find() отдаёт одну позицию, count() – одно
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

    Виджет ничего не ищет сам – повторяем алгоритм обычным while и
    складываем полное состояние на каждом шаге. Главные кадры трассы:
    прыжок i за найденное вхождение (та же логика, по которой count() не
    считает пересечения) и последний find(), вернувший -1, – именно он
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
        note='Строка, в которой ищем. Вхождений в ней несколько – одного '
             'ответа find() тут не хватит.',
    ))
    steps.append(dict(
        line=2, vars=state(),
        note='Кусок, который ищем.',
    ))
    i = 0
    steps.append(dict(
        line=3, vars=state(),
        note='i – позиция, с которой начинать очередной поиск. В первый раз – '
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
        note='find() просмотрел строку начиная с позиции {} и вернул {} – '
             'позицию первого вхождения.'.format(i, pos),
    ))

    while True:
        go = pos != -1
        steps.append(dict(
            line=6, vars=state(), check=go,
            note=('pos = {} – это не -1, значит вхождение нашлось и его надо '
                  'обработать.'.format(pos) if go
                  else 'pos = -1: find() больше ничего не нашёл. Вот что '
                       'останавливает цикл – не длина строки, а ответ '
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
            note='Следующий поиск начнём с позиции {}: {} + {} – это сразу за '
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
        note='Столько же вернул бы и text.count(sub) – {}. Только count() '
             'сообщил бы одно число, а цикл показал каждое место. Обратите '
             'внимание на последнее вхождение: оно внутри слова «котлета», и '
             'ни find(), ни count() этого не замечают.'.format(text.count(sub)),
    ))
    return steps
# Код, который трассирует loop-trace в уроке 8.2: ручное разрезание строки
# по разделителю через find() и срез – то, что делает split() одним вызовом.
# Показывает главное: разделитель не попадает ни в один кусок, а последний
# кусок берётся уже без find() – отсюда и «частей на одну больше, чем
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

    Виджет ничего не режет сам – повторяем алгоритм обычным while и
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
             '{} раза – значит, частей будет {}.'.format(
                 text.count(sep), text.count(sep) + 1),
    ))
    steps.append(dict(
        line=2, vars=state(),
        note='Разделитель. Его задача – только показать место разреза; в '
             'куски он попасть не должен.',
    ))
    start = 0
    steps.append(dict(
        line=3, vars=state(),
        note='start – начало очередного куска. Первый кусок начинается с '
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
        note='find() из урока 8.2 нашёл первый разделитель – он стоит на '
             'позиции {}.'.format(pos),
    ))

    while True:
        go = pos != -1
        steps.append(dict(
            line=6, vars=state(), check=go,
            note=('pos = {} – разделитель есть, значит слева от него есть и '
                  'кусок.'.format(pos) if go
                  else 'pos = -1: разделителей больше нет, и цикл на этом '
                       'закончился. А строка – нет: справа остался кусок, '
                       'который никто ещё не отрезал.'),
        ))
        if not go:
            break

        chunk = text[start:pos]
        steps.append(dict(
            line=7, vars=state(), out=chunk,
            note='Отрезали s[{}:{}] – это {!r}. Срез не включает правую '
                 'границу (урок 8.1), поэтому разделитель в кусок не '
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
            note='Следующий кусок начинается сразу за разделителем – с '
                 'позиции {}.'.format(start),
        ))
        pos = text.find(sep, start)
        steps.append(dict(
            line=10, vars=state(),
            note=('Ищем следующий разделитель начиная с {} – нашёлся на '
                  'позиции {}.'.format(start, pos) if pos != -1
                  else 'Ищем следующий разделитель начиная с {} – find() '
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
        note='Разделителей было {}, а частей вышло {} – на одну больше. Ровно '
             'этот список и вернёт s.split(sep): {}.'.format(
                 n, n + 1, text.split(sep)),
    ))
    return steps


# Код, который трассирует loop-trace в уроке 8.3: поиск самой длинной цепочки
# одинаковых символов подряд. Главные кадры трассы: cur сбрасывается в 1 на
# границе цепочки, а сравнение с best идёт на каждом шаге – в том числе внутри
# цепочки, а не после её обрыва. Именно поэтому цепочка, упирающаяся в конец
# строки, не теряется.
CHAIN_CODE = [
    "s = 'ААБВВВВГ'",
    'best = 0                   # ответ для пустой строки уже готов',
    'cur = 0',
    'if len(s) > 0:',
    '    best = 1               # первый символ – цепочка длиной 1',
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

    Виджет ничего не считает сам – повторяем алгоритм обычным циклом и
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
             'подряд. Глазами ответ виден сразу – программе придётся пройти её '
             'до конца.',
    ))
    best = 0
    steps.append(dict(
        line=2, vars=state(),
        note='best – самая длинная цепочка из уже увиденных. Ноль здесь не '
             'формальность: для пустой строки это и есть готовый ответ.',
    ))
    cur = 0
    steps.append(dict(
        line=3, vars=state(),
        note='cur – длина цепочки, которая идёт прямо сейчас.',
    ))
    non_empty = len(text) > 0
    steps.append(dict(
        line=4, vars=state(), check=non_empty,
        note=('В строке есть символы, значит первая цепочка уже началась.'
              if non_empty else
              'Строка пустая – тело if пропускается, и ответом останется ноль.'),
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
            note='Позиция {}: символ {!r}, предыдущий – {!r}.'.format(
                pos, text[pos], text[pos - 1]),
        ))
        same = text[pos] == text[pos - 1]
        steps.append(dict(
            line=8, vars=state(), check=same,
            note=('{!r} и {!r} – один и тот же символ.'.format(
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
                note='Начинаем считать заново – но не с нуля, а с единицы: сам '
                     'символ {!r} это уже цепочка длиной 1.'.format(text[pos]),
            ))
        better = cur > best
        steps.append(dict(
            line=12, vars=state(), check=better,
            note=('cur = {} больше рекорда {} – надо обновить.'.format(cur, best)
                  if better else
                  'cur = {}, а рекорд {} – обновлять нечего. Но спросили мы всё '
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
        note='Позиции кончились – цикл завершён.',
    ))
    steps.append(dict(
        line=14, vars=state(), out=str(best),
        note='Ответ {}. Проследите по трассе, на каком шаге best дорос до этого '
             'значения: не тогда, когда цепочка кончилась, а на её последнем '
             'символе. Поэтому цепочке и не обязательно обрываться – она может '
             'упираться прямо в конец строки.'.format(best),
    ))
    return steps


# Код, который трассирует loop-trace в уроке 8.3: проверка палиндрома двумя
# указателями. Строка на вход подаётся уже очищенной – очистку разбирал
# виджет того же урока. Главные кадры трассы: цикл не доходит до конца строки, а
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
             'знаки препинания убраны заранее – иначе сравнивать нечестно.',
    ))
    i = 0
    steps.append(dict(
        line=2, vars=state(),
        note='Левый указатель стоит на первом символе {!r}.'.format(text[0]),
    ))
    j = len(text) - 1
    steps.append(dict(
        line=3, vars=state(),
        note='Правый – на последнем: {!r}. Обратите внимание на «минус один»: '
             'индексы идут с нуля, поэтому последний равен len(s) - 1 (урок '
             '8.1).'.format(text[-1]),
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
            note=('i = {} левее j = {} – есть ещё непроверенная пара.'.format(i, j)
                  if go else
                  'i и j встретились на символе {!r} – он стоит ровно посередине, '
                  'и сравнивать его не с чем. Все пары уже проверены, работа '
                  'закончена, хотя цикл прошёл только полстроки.'.format(text[i])),
        ))
        if not go:
            break

        diff = text[i] != text[j]
        steps.append(dict(
            line=6, vars=state(), check=diff,
            note=('{!r} и {!r} – разные символы, дальше можно не смотреть.'.format(
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
                note='break обрывает цикл – оставшиеся пары проверять бессмысленно.',
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
            note='Правый – влево, ему навстречу.',
        ))

    steps.append(dict(
        line=11, vars=state(), out=str(ok),
        note='Ответ {}. Сравнений вышло вдвое меньше, чем символов в строке: '
             'каждая пара проверяется один раз.'.format(ok),
    ))
    return steps


# Код, который трассирует loop-trace в уроке 8.4: чтение файла построчно и
# подсчёт суммы. Главный кадр трассы – значение line сразу после того, как
# его выдал цикл: перевод строки \n на конце виден только здесь, дальше его
# снимает strip().
FILE_SUM_CODE = [
    'total = 0',
    "with open('numbers.txt', encoding='utf-8') as f:",
    '    for line in f:',
    '        line = line.strip()        # снимаем \\n с конца',
    '        total = total + int(line)',
    'print(total)',
]


def _file_sum_trace(content='12\n7\n100\n'):
    """Пошаговая трасса чтения файла и подсчёта суммы для loop-trace.

    Виджет в файлы не заглядывает – повторяем разбираемый алгоритм обычным
    циклом, а содержимое файла держим строкой: `for line in f` отдаёт строки
    ровно так же, вместе с переводом строки на конце.
    """
    steps = []
    total = None
    line = None

    def shown(s):
        # Строку показываем в питоновской записи: так виден невидимый \n.
        return {'__raw': repr(s)}

    def state():
        return {
            'line': None if line is None else shown(line),
            'total': total,
        }

    total = 0
    steps.append(dict(
        line=1, vars=state(),
        note='total – накопитель, та же идея, что в блоке 4: одно число, '
             'которое растёт по дороге. До чтения файла он не видел ничего, '
             'поэтому ноль.',
    ))
    steps.append(dict(
        line=2, vars=state(),
        note="Файл открыт на чтение: режим 'r' не написан, потому что он и "
             "есть режим по умолчанию. encoding='utf-8' назван явно – без "
             'него Python взял бы кодировку системы, и на Windows русский '
             'текст превратился бы в нечитаемые символы. with закроет файл '
             'сам, как только кончится блок.',
    ))

    for raw in content.splitlines(keepends=True):
        line = raw
        steps.append(dict(
            line=3, vars=state(),
            note='Цикл взял из файла следующую строку. Посмотрите на её '
                 'значение: на конце сидит перевод строки \\n – невидимый '
                 'символ, который в файле и разделял строки. Для программы '
                 'он такой же символ, как и цифры.',
        ))
        line = raw.strip()
        steps.append(dict(
            line=4, vars=state(),
            note='strip() снял перевод строки с конца – осталось {!r}. Число '
                 'из такой строки int() прочёл бы и без strip(), а вот '
                 'сравнение с эталоном на этом месте уже не сработало '
                 'бы.'.format(line),
        ))
        total = total + int(line)
        steps.append(dict(
            line=5, vars=state(),
            note='int(line) перевёл строку в число, и накопитель вырос: '
                 '{} + {} = {}.'.format(total - int(line), int(line), total),
        ))

    steps.append(dict(
        line=3, vars=state(),
        note='Строки в файле кончились – цикл завершился. Последняя '
             'прочитанная строка так и осталась в переменной line, но '
             'работать с ней уже не нужно.',
    ))
    steps.append(dict(
        line=6, vars=state(), out=str(total),
        note='Ответ {}. Ни одно число не вводили руками и ни одну строку не '
             'держали в памяти: файл прочитан построчно, а к концу цикла в '
             'накопителе уже лежала сумма. Так же он прочитается и на '
             'тысяче строк.'.format(total),
    ))
    return steps


# Шаблоны и тексты виджетов regex-lab в уроке 8.6. Живут отдельными
# константами, а не строками внутри seed_8_6, потому что по ним же сверяют
# виджет с настоящим `re`: шаблон в конфиге и шаблон в проверке – это одна и
# та же строка, разъехаться они не могут. И всё сырыми строками: в обычной
# строке `\b` – уже не граница слова, а невидимый символ забоя.
REGEX_LAB_PATTERN = r'\d+'
REGEX_LAB_TEXT = 'В 2026 году кот Васька поймал 3 мыши и 12 бабочек.'
REGEX_DATE_PATTERN = r'\d{2}\.\d{2}\.\d{4}'
REGEX_DATE_TEXT = (
    'Задача сдана 03.09.2026, проверена 14.09.2026. '
    'Черновик 1.1.26 не считается.'
)
# Шаблон и текст виджета regex-lab в уроке 8.7. Здесь в шаблоне две группы, и
# весь урок про них: список под текстом меняется от одних только скобок.
REGEX_GROUP_PATTERN = r'(\d{2})\.(\d{2})\.(\d{4})'
REGEX_GROUP_TEXT = (
    'Сдано 03.09.2026, проверено 14.09.2026, пересдача 28.09.2026.'
)


# ─────────────────────────────────────────────────────────────────────
# Задачи практикума с приложенным файлом (18–20).
#
# Файл кладётся к задаче через QuestionFile и попадает в песочницу под тем
# же именем (quizzes/tasks.py), поэтому программа ученика открывает его по
# имени из условия. Файлы у вопроса общие для всех тестов – один файл дал бы
# один-единственный тест, а его ответ достаточно вписать в print. Поэтому
# файлов три, а имя нужного подаётся на вход: тесты различаются именем.
#
# Содержимое генерируется здесь же, а ожидаемые ответы считаются по этому же
# содержимому эталонными функциями ниже. Разъехаться файл и ответ не могут:
# это буквально одни и те же данные. Сами эталоны сверены полным перебором
# (scratchpad/window_check.py и check_file_tasks.py).
# ─────────────────────────────────────────────────────────────────────
def _runs_text(seed, size, alphabet='ABCDEF', max_run=7):
    """Текст из цепочек одинаковых букв: длина цепочки от 1 до max_run."""
    rnd = random.Random(seed)
    out = []
    total = 0
    while total < size:
        letter = rnd.choice(alphabet)
        run = rnd.randint(1, max_run)
        out.append(letter * run)
        total += run
    return ''.join(out)[:size]


def _letters_text(seed, size, alphabet, weights):
    rnd = random.Random(seed)
    return ''.join(rnd.choices(alphabet, weights=weights, k=size))


def _longest_run(text):
    """Длина самой длинной цепочки одинаковых символов подряд."""
    best = 0
    run = 0
    prev = ''
    for ch in text:
        run = run + 1 if ch == prev else 1
        prev = ch
        if run > best:
            best = run
    return best


def _min_window_exact(text, letter, k):
    """Минимальная длина куска, где letter встречается ровно k раз."""
    left = 0
    count = 0
    best = -1
    for right in range(len(text)):
        if text[right] == letter:
            count += 1
        while count == k:
            length = right - left + 1
            if best == -1 or length < best:
                best = length
            if text[left] == letter:
                count -= 1
            left += 1
    return best


def _max_window_pairs(text, pair, n):
    """Максимальная длина куска, где пара pair встречается ровно n раз.

    Вхождение пары «принадлежит» куску, если внутрь попали оба её символа,
    поэтому пара, начавшаяся на левой границе, считается только пока левая
    граница не сдвинулась дальше неё.
    """
    left = 0
    count = 0
    best = -1
    for right in range(len(text)):
        if right > 0 and text[right - 1:right + 1] == pair:
            count += 1
        while count > n:
            if text[left:left + 2] == pair:
                count -= 1
            left += 1
        if count == n:
            length = right - left + 1
            if length > best:
                best = length
    return best


CHAIN_FILES = [
    ('chain_a.txt', _runs_text(801, 30000)),
    ('chain_b.txt', _runs_text(802, 30000)),
    ('chain_c.txt', _runs_text(803, 30000)),
]

ZONE_K = 40
ZONE_FILES = [
    ('zone_a.txt', _letters_text(811, 20000, 'ABZ', [5, 4, 1])),
    ('zone_b.txt', _letters_text(812, 20000, 'ABZ', [5, 4, 1])),
    ('zone_c.txt', _letters_text(813, 20000, 'ABZ', [5, 4, 1])),
]

PAIR_N = 25
PAIR_FILES = [
    ('pair_a.txt', _letters_text(821, 20000, 'ABC', [2, 1, 1])),
    ('pair_b.txt', _letters_text(822, 20000, 'ABC', [2, 1, 1])),
    ('pair_c.txt', _letters_text(823, 20000, 'ABC', [2, 1, 1])),
]


class Command(BaseCommand):
    help = "Наполняет статьи блока 8 контентом (уроки добавляются постепенно)."

    @transaction.atomic
    def handle(self, *args, **options):
        _retire_old_articles(self.stdout)
        self.seed_8_1()
        self.seed_8_2()
        self.seed_8_3()
        self.seed_8_4()
        self.seed_8_5()
        self.seed_8_6()
        self.seed_8_7()
        self.seed_8_8()
        self.stdout.write(self.style.SUCCESS('Готово: блок 8 обновлён.'))

    def seed_8_1(self):
        article = Article.objects.get(slug='8-1-stroki-simvoly-indeksy-i-srezy')
        article.description = (
            'Строка как упорядоченная последовательность символов: индекс, '
            'len(), обход циклом, отрицательные индексы и срезы с '
            'пропущенными границами и шагом. Почему строку нельзя изменить, '
            'что на самом деле происходит при «изменении» и зачем языку такой '
            'запрет.'
        )
        article.save(update_fields=['description'])

        _replace_blocks(article, [
            dict(order=1, block_type='text', title='О чём этот урок', content=(
                'В строке `\'2026-08-01\'` записана дата, и из неё нужно '
                'достать год – четыре первых символа. Пока строка умеет '
                'отдавать символы только по одному, задача решается циклом: '
                'завести пустую строку-накопитель, отсчитать первые четыре '
                'позиции, приклеить символы по одному. Работает – но стоит '
                'понадобиться не году, а месяцу или куску между дефисами, и '
                'цикл придётся переписывать заново.\n\n'
                '**В этом уроке:** из чего состоит строка; как обратиться к '
                'одному символу по индексу – прямому и отрицательному; как '
                'вырезать кусок строки одной короткой записью; почему строку '
                'нельзя изменить и что делают вместо изменения; зачем языку '
                'такой запрет.'
            )),
            dict(order=2, block_type='text', title='Строка – последовательность символов', content=(
                '> **Строка** (`str`) – упорядоченная последовательность '
                'символов. У каждого символа есть своё место в ней – '
                '**индекс**.\n\n'
                'Слово «упорядоченная» здесь не украшение: порядок – часть '
                'значения. `\'кот\'` и `\'ток\'` состоят из одних и тех же '
                'букв, но это две разные строки, и Python считает их '
                'неравными.\n\n'
                'Длину строки даёт `len()`:\n\n'
                '```python\n'
                "s = 'Привет'\n"
                'print(len(s))       # 6 – символов в строке\n'
                'print(len(s[0]))    # 1 – символ это тоже строка\n'
                '```\n\n'
                'Отдельного типа «символ» в Python нет: то, что возвращает '
                '`s[0]`, – **строка длины 1**, у неё и `type()` даст `str`, и '
                '`len()` – единицу. В C и Java для одиночного символа есть '
                'свой тип `char`, и там `\'a\'` и `"a"` – вещи принципиально '
                'разные; в Python кавычки взаимозаменяемы, и отдельного типа '
                'под один символ не завелось. Практическое следствие: функция '
                '`ord()` из урока 7.3 принимает строку **ровно из одного '
                'символа** – ни пустую, ни из двух букв.\n\n'
                'Числовые коды символов здесь больше не понадобятся, но если '
                'нужно освежить: `ord()` и `chr()` разобраны в уроке 7.3, а '
                'устройство кодовых таблиц – почему буквы и цифры лежат '
                'подряд и почему регистр отличается на 32 – в уроке 7.2.\n\n'
                'Строка **итерируема**: её можно поставить прямо в заголовок '
                '`for`, и цикл выдаст символы по одному, слева направо. Если '
                'нужен ещё и номер позиции, берут `range(len(s))` и '
                'обращаются к `s[i]` внутри цикла.'
            )),
            dict(order=3, block_type='code', title='', code_language='python', content=(
                "text = 'Привет'\n"
                '\n'
                '# по символам – когда номер не важен\n'
                'for ch in text:\n'
                "    print(ch, end=' ')      # П р и в е т\n"
                '\n'
                'print()\n'
                '\n'
                '# по индексам – когда нужен номер позиции\n'
                'for i in range(len(text)):\n'
                "    print(i, text[i])       # 0 П / 1 р / 2 и / ..."
            )),
            dict(order=4, block_type='text', title='Индекс: номер символа', content=(
                'Индекс – это номер места символа в строке. Нумерация начинается '
                'с нуля, как и везде в Python: у строки `\'Привет\'` буква `П` '
                'стоит на позиции 0, а `т` – на позиции 5. Обращение '
                'записывается квадратными скобками: `s[0]`, `s[5]`.\n\n'
                'Из нумерации с нуля следует важное: последний допустимый '
                'индекс равен `len(s) - 1`. Обращение по индексу `len(s)` – уже '
                'выход за границу, и программа останавливается с ошибкой '
                '`IndexError: string index out of range`. Читается она просто: '
                'попросили позицию, которой в строке нет.\n\n'
                'Считать от конца удобнее особой записью:\n\n'
                '> **Отрицательный индекс** отсчитывает позицию с конца '
                'строки: `s[-1]` – последний символ, `s[-2]` – предпоследний, '
                '`s[-len(s)]` – первый.\n\n'
                'Нового здесь, по сути, ничего: `s[-k]` – ровно то же место, '
                'что `s[len(s) - k]`, просто записанное короче. Счёт с конца '
                'начинается с −1, потому что ноль уже занят первым символом, а '
                '«минус ноль» от него ничем не отличался бы. Границы те же: у '
                'строки длины 6 допустимы индексы от −6 до 5, а `s[-7]` – такой '
                'же `IndexError`, как `s[6]`.\n\n'
                '| Символ | П | р | и | в | е | т |\n'
                '|---|---|---|---|---|---|---|\n'
                '| прямой индекс | 0 | 1 | 2 | 3 | 4 | 5 |\n'
                '| с конца | −6 | −5 | −4 | −3 | −2 | −1 |'
            )),
            dict(order=5, block_type='code', title='', code_language='python', content=(
                "s = 'Привет'\n"
                'print(s[0])           # П – первый символ, индекс 0\n'
                'print(s[5])           # т – последний, он же len(s) - 1\n'
                'print(s[-1])          # т – то же самое, только короче\n'
                'print(s[-2])          # е – предпоследний\n'
                '\n'
                'print(s[6])           # IndexError: string index out of range\n'
                'print(s[-7])          # IndexError: string index out of range'
            )),
            dict(order=6, block_type='text', title='Срез: кусок строки одной записью', content=(
                '> **Срез** `s[start:stop]` – новая строка из символов, начиная '
                'с позиции `start` **включительно** и до позиции `stop` '
                '**не включая**.\n\n'
                'Правая граница в срез не входит – это главное, что придётся '
                'запомнить. Поначалу раздражает, но из такой договорённости '
                'следуют два свойства, которыми потом пользуются постоянно:\n\n'
                '- длина среза равна `stop - start` (когда обе границы внутри '
                'строки, а шаг единичный) – считать ничего не надо;\n'
                '- `s[:i] + s[i:]` при любом `i` даёт исходную строку – куски '
                'стыкуются без нахлёста и без дырки.\n\n'
                'Второе свойство и объясняет, почему границу не включают: '
                'вторая половина начинается ровно там, где кончилась первая, и '
                'один и тот же символ не попадает в обе.'
            )),
            dict(order=7, block_type='code', title='', code_language='python', content=(
                "s = '2026-08-01'      # len(s) == 10\n"
                '\n'
                'print(s[0:4])         # 2026 – символы 0, 1, 2, 3\n'
                'print(s[5:7])         # 08 – символы 5 и 6\n'
                'print(s[8:10])        # 01 – символы 8 и 9\n'
                '# дефисы стоят на позициях 4 и 7 – ни в один срез они не попали\n'
                'print(s[0:4] + s[4:]) # 2026-08-01 – куски стыкуются без нахлёста'
            )),
            dict(order=8, block_type='text', title='Пропущенные границы и шаг', content=(
                'Любую границу можно не писать – тогда Python подставит край '
                'строки: `s[:n]` – от начала, `s[n:]` – до конца, `s[:]` – вся '
                'строка целиком. Дату это делает заметно короче: год `s[:4]`, '
                'день `s[8:]`.\n\n'
                'Полная форма среза – `s[start:stop:step]`.\n\n'
                '> **Шаг** `step` – через сколько позиций брать следующий '
                'символ. По умолчанию он равен 1, то есть символы берутся '
                'подряд.\n\n'
                'Отсюда `s[::2]` – каждый второй символ начиная с нулевого, а '
                '`s[1::2]` – каждый второй начиная с первого. Шаг бывает и '
                '**отрицательным**: тогда обход идёт справа налево, а '
                'пропущенные границы подставляются наоборот. Так получается '
                'самая известная идиома Python: `s[::-1]` – строка задом '
                'наперёд. Правило про правую границу при этом не отменяется: '
                '`s[5:0:-1]` дойдёт до позиции 1 и остановится, потому что '
                'нулевой символ в границу не входит. Чтобы дойти до самого '
                'начала, границу опускают: `s[5::-1]`.\n\n'
                'И отдельно – важное отличие среза от индекса.\n\n'
                '> **Срез никогда не падает из-за границ.** Индексу нужно, '
                'чтобы символ существовал; срезу – нет, он просто берёт то, '
                'что попало в диапазон.\n\n'
                'Поэтому `s[100:200]` у короткой строки – не `IndexError`, а '
                'пустая строка `\'\'`, а `s[:1000]` – вся строка. '
                'Практическое следствие: если нужны «первые три символа '
                'строки, которая может оказаться и короче» – срез справится '
                'сам, проверять длину заранее не нужно.'
            )),
            dict(order=9, block_type='code', title='', code_language='python', content=(
                "s = '2026-08-01'\n"
                'print(s[:4])       # 2026 – от начала\n'
                'print(s[8:])       # 01 – до конца\n'
                'print(s[:])        # 2026-08-01 – вся строка\n'
                '\n'
                "t = 'Привет'\n"
                'print(t[::2])      # Пие – каждый второй начиная с нулевого\n'
                'print(t[1::2])     # рвт – каждый второй начиная с первого\n'
                'print(t[1:5:2])    # рв – от 1 до 5 (не включая), через один\n'
                '\n'
                'print(t[::-1])     # тевирП – вся строка задом наперёд\n'
                'print(t[5::-1])    # тевирП – то же самое, границы записаны явно\n'
                'print(t[5:0:-1])   # тевир – ловушка: позиция 0 не включается\n'
                '\n'
                '# срез за границей строки – не ошибка, в отличие от индекса\n'
                "print(t[100:200])  # '' – пустая строка\n"
                'print(t[:1000])    # Привет – взял всё, что было\n'
                'print(t[100])      # IndexError: string index out of range'
            )),
            dict(
                order=10, block_type='widget',
                title='Соберите срез сами',
                content=(
                    'Линейка индексов и живой срез над одной и той же строкой. '
                    'Меняйте `start`, `stop` и `step` – попавшие символы '
                    'подсвечиваются и нумеруются в том порядке, в каком '
                    'окажутся в результате, а клетка на позиции `stop` обведена '
                    'пунктиром: она не включается. Кнопка «пусто» у каждой '
                    'границы – это двоеточие без числа. Наведите на любой '
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
                         'hint': 'start опущен – берём с начала строки'},
                        {'title': 'месяц s[5:7]', 'text': '2026-08-01', 'start': 5, 'stop': 7,
                         'hint': 'позиции 5 и 6; седьмая уже не входит'},
                        {'title': 'день s[8:]', 'text': '2026-08-01', 'start': 8,
                         'hint': 'stop опущен – берём до конца строки'},
                        {'title': 'без последнего s[:-1]', 'text': 'Привет', 'stop': -1,
                         'hint': 'граница с конца: −1 – это позиция 5'},
                        {'title': 'каждый второй s[::2]', 'text': 'Привет', 'step': 2,
                         'hint': 'позиции 0, 2, 4'},
                        {'title': 'задом наперёд s[::-1]', 'text': 'Привет', 'step': -1,
                         'hint': 'отрицательный шаг – идём справа налево'},
                        {'title': 'ловушка s[5:0:-1]', 'text': 'Привет', 'start': 5,
                         'stop': 0, 'step': -1,
                         'hint': 'позиция 0 не включается – первая буква потеряна'},
                        {'title': 'за границей s[100:200]', 'text': 'Привет', 'start': 100,
                         'stop': 200, 'hint': 'не ошибка, а пустая строка'},
                    ],
                },
            ),
            dict(order=11, block_type='text', title='Шпаргалка типовых срезов', content=(
                'Эти записи встречаются так часто, что их проще запомнить '
                'целиком, чем каждый раз выводить заново:\n\n'
                '| Запись | Что даёт | Пример при `s = \'Привет\'` |\n'
                '|---|---|---|\n'
                '| `s[-1]` | последний символ | `\'т\'` |\n'
                '| `s[:-1]` | всё, кроме последнего | `\'Приве\'` |\n'
                '| `s[:3]` | первые три символа | `\'При\'` |\n'
                '| `s[-3:]` | последние три символа | `\'вет\'` |\n'
                '| `s[1:-1]` | без первого и последнего | `\'риве\'` |\n'
                '| `s[1:4]` | от позиции 1 до 4, не включая 4 | `\'рив\'` |\n'
                '| `s[::2]` | каждый второй символ | `\'Пие\'` |\n'
                '| `s[::-1]` | строка задом наперёд | `\'тевирП\'` |\n\n'
            )),
            dict(order=12, block_type='text', title='Строку изменить нельзя', content=(
                '> Тип `str` – **неизменяемый** (immutable): у существующей '
                'строки нельзя заменить, вставить или удалить ни одного '
                'символа.\n\n'
                'Попытка присвоить что-нибудь по индексу заканчивается '
                'сообщением `TypeError: \'str\' object does not support item '
                'assignment` – «объект типа str не поддерживает присваивание по '
                'элементу». Читать `s[0]` можно, писать в `s[0]` – нельзя.\n\n'
                'А ведь строки в программах меняются постоянно: к ним что-то '
                'дописывают, из них что-то вырезают. Как это уживается с '
                'запретом? Все такие операции **создают новую строку**, а имя '
                'переменной – всего лишь ярлык, который можно перевесить на '
                'другой объект. Запись `s = s + \'!\'` означает не «дописали '
                'восклицательный знак в конец `s`», а «собрали в памяти новую '
                'строку из старой и восклицательного знака и назвали её тем же '
                'именем `s`». Старая строка осталась ровно такой, какой была: '
                'если на неё указывало ещё одно имя, там ничего не '
                'изменилось.\n\n'
                'Срез устроен так же: `t = s[1:]` не укорачивает `s`, а строит '
                'рядом новую строку. Отдельной операции «удалить символ из '
                'строки» в Python поэтому нет – её собирают из двух срезов: '
                'удалить символ на позиции `i` – это `s[:i] + s[i+1:]`, а '
                'вставить перед позицией `i` – `s[:i] + \'X\' + s[i:]`.\n\n'
                'Убедиться, что перед нами уже другой объект, помогает функция '
                '`id()` – она выдаёт номер, по которому объект лежит в памяти. '
                'Если после «изменения» номер стал другим, прежнего объекта '
                'перед нами нет.\n\n'
                'Правило, которое стоит запомнить на всю оставшуюся работу со '
                'строками: **не присвоил – потерял**. Пока новая строка не '
                'записана в переменную, её никто не хранит.'
            )),
            dict(order=13, block_type='code', title='', code_language='python', content=(
                "s = 'привет'\n"
                "s[0] = 'П'           # TypeError: 'str' object does not support item assignment\n"
                '\n'
                '# «изменение» строки – это на самом деле новая строка\n'
                "s = 'кот'\n"
                't = s                # второе имя для той же самой строки\n'
                "s = s + '!'          # собрали новую строку и перевесили на неё имя s\n"
                "print(s)             # кот!\n"
                "print(t)             # кот – старая строка не пострадала\n"
                '\n'
                "s = 'Привет'\n"
                '# «удаление» символа на позиции 3 – склейка двух срезов\n'
                "print(s[:3] + s[4:]) # Приет – буквы «в» больше нет\n"
                '# «вставка» устроена так же\n'
                "print(s[:3] + '!' + s[3:])  # При!вет\n"
                '\n'
                "s = 'кот'\n"
                'print(id(s))         # например, 2158751223856\n'
                "s = s + '!'\n"
                'print(id(s))         # другое число – перед нами другой объект'
            )),
            dict(order=14, block_type='text', title='Зачем языку такой запрет', content=(
                'Неизменяемость – не придирка синтаксиса, а свойство, за '
                'которое платят удобством: строку можно спокойно отдавать куда '
                'угодно – раз значение нельзя изменить в принципе, ни один '
                'кусок программы не перепишет его так, чтобы это заметили '
                'остальные, и целого класса ошибок «кто-то поменял мои данные, '
                'а я и не знал» просто не существует; одинаковые строки можно '
                'не хранить дважды; а в качестве ключа словаря строка годится '
                'потому, что хеш такого значения достаточно посчитать один раз '
                '– он уже не устареет.\n\n'
                'Обратная сторона у запрета тоже есть: '
                'каждая склейка создаёт новую строку, поэтому накопление '
                'результата в цикле – `result = result + ch` – каждый раз '
                'копирует всё уже накопленное заново. На слове из шести букв '
                'этого не заметит никто, а на строке в миллион символов разница '
                'станет ощутимой.'
            )),
            dict(order=15, block_type='text', title='Коротко', content=(
                '- Строка – **упорядоченная последовательность символов**; '
                'отдельного типа «символ» нет, `s[0]` – это строка длины 1.\n'
                '- Индексы нумеруются с нуля, последний равен `len(s) - 1`; '
                '`s[-1]` – тот же последний символ, названный с конца. Выход '
                'за границу – `IndexError`.\n'
                '- **Срез** `s[start:stop:step]` берёт `start` включительно, '
                '`stop` – не включая, а `step` задаёт, через сколько символов '
                'брать следующий (по умолчанию 1). Отсюда длина `stop - start` '
                'и склейка `s[:i] + s[i:]`, равная исходной строке; любую '
                'границу можно опустить (`s[:n]`, `s[n:]`, `s[:]`), а '
                'отрицательный шаг разворачивает строку: `s[::-1]`. Срез не '
                'падает при выходе за границы – он вернёт меньше символов или '
                'пустую строку.\n'
                '- `str` **неизменяем**: `s[0] = \'A\'` – это `TypeError`. '
                'Любое «изменение» собирает новую строку, а имя переменной '
                'лишь перевешивается на неё; срез тоже создаёт новую строку, '
                'а не укорачивает исходную.'
            )),
            dict(order=16, block_type='text', title='Что нас ждёт в этом блоке', content=(
                'Читать строку мы теперь умеем: достать символ по индексу и '
                'вырезать кусок срезом. Дальше в блоке:\n\n'
                '- **8.2. Методы строк: поиск, замена, разбиение** – готовые '
                'операции над строкой целиком: `find()`, `replace()`, '
                '`split()`, смена регистра и проверки вроде `isalpha()`. Та '
                'самая `join()`, которой собирают длинные строки без '
                'копирования на каждом шаге, – тоже там;\n'
                '- **8.3. Алгоритмические задачи со строками** – перебор, '
                'подсчёт, поиск подстроки своими руками: что именно прячется '
                'за оператором `in`;\n'
                '- **8.4. Файлы: чтение и запись** – как прочитать текст из '
                'файла на диске и записать результат обратно;\n'
                '- **8.5. Модули и библиотеки: import** – как подключать чужие '
                'готовые функции;\n'
                '- **8.6–8.7. Регулярные выражения** – язык шаблонов для '
                'поиска по образцу: одна короткая запись вместо десятка '
                'условий;\n'
                '- **Практикум блока** – страница обязательных задач с '
                'автопроверкой. Именно он определяет, пройден блок или нет: '
                'самопроверки после уроков ничего не блокируют, а задачи '
                'практикума нужно решить.'
            )),
        ])

        quiz = _self_check(
            slug='self-check-stroki-simvoly-indeksy-i-srezy',
            title='Самопроверка: символы, индексы и срезы',
            description='Пять вопросов по теме урока.',
            questions=[
                dict(
                    type='choice',
                    text="`s = 'Привет'`. Что выведет `print(s[1:4])`?",
                    choices=[
                        ("'рив' – символы с 1-го по 3-й, четвёртый не "
                         'включается', True),
                        ("'риве' – с 1-го по 4-й включительно", False),
                        ("'Прив' – первые четыре символа", False),
                        ("'ри' – обе границы среза не включаются", False),
                    ],
                ),
                dict(
                    type='choice',
                    text=(
                        'Строка s состоит из 6 символов. Что произойдёт при '
                        'вычислении s[6]?'
                    ),
                    choices=[
                        ('IndexError: последний допустимый индекс на единицу '
                         'меньше длины', True),
                        ('Вернётся последний символ строки', False),
                        ('Вернётся пустая строка', False),
                        ('Вернётся первый символ – счёт пойдёт по кругу', False),
                    ],
                ),
                dict(
                    type='choice',
                    text=(
                        "Выполнили s = 'привет', а затем s[0] = 'П'. Что "
                        'произойдёт?'
                    ),
                    choices=[
                        ('Ошибка TypeError: строку нельзя изменить по индексу',
                         True),
                        ('Первая буква станет заглавной – получится «Привет»',
                         False),
                        ('Ошибки не будет, но и строка не изменится', False),
                        ('Создастся новая строка «Привет», а старая удалится',
                         False),
                    ],
                ),
                dict(
                    type='choice',
                    text=(
                        'В программе три строки: `s = \'кот\'`, затем '
                        '`s + \'!\'`, затем `print(s)`. Вывелось «кот», без '
                        'восклицательного знака. Почему?'
                    ),
                    choices=[
                        ('Склейка создала новую строку, но её никуда не '
                         'присвоили – имя s осталось на прежней', True),
                        ('Строка изменилась, но `print` показывает её '
                         'прежнее значение', False),
                        ('Строки неизменяемы, поэтому `s + \'!\'` вообще '
                         'ничего не создаёт', False),
                        ('Приклеить знак можно только через `s += \'!\'` – '
                         'обычный плюс со строками не работает', False),
                    ],
                ),
                dict(
                    type='text',
                    text=(
                        "`s = 'Привет'`. Сколько символов вернёт срез "
                        '`s[2:5]`? Впишите только число.'
                    ),
                    correct_text_answer='3',
                ),
            ],
        )
        ArticleQuiz.objects.get_or_create(
            article=article, quiz=quiz,
            defaults={'label': 'Проверь себя', 'order': 1},
        )

    def seed_8_2(self):
        article = Article.objects.get(
            slug='8-2-metody-strok-poisk-zamena-razbienie')
        article.description = (
            'Урок-объединение: операции +, * и in, методы поиска и замены '
            '(find, rfind, count, replace), регистр и strip(), разбиение '
            'строки split() и сборка join(), f-строки. Каждый инструмент '
            'описан один раз и коротко, в конце – общая шпаргалка по всем '
            'операциям урока и пять вопросов самопроверки.'
        )
        article.save(update_fields=['description'])

        _replace_blocks(article, [
            dict(order=1, block_type='text', title='О чём этот урок', content=(
                'Из школьного журнала пришла строка `\'  Иванов;9А;5  \'`. '
                'Нужно убрать лишние пробелы по краям, выяснить, есть ли '
                'внутри точка с запятой, найти, на какой позиции она стоит, '
                'и разрезать строку на три поля: фамилию, класс и оценку.\n\n'
                'Циклом из урока 8.1 это решается: пройти по символам, '
                'накопить куски до разделителя, хвост забрать отдельно. '
                'Работает – но ровно этот же перебор приходится писать '
                'заново для каждой следующей задачи. А у строки почти на '
                'каждый вопрос уже есть готовая операция, и вызывается она '
                'одной короткой записью через точку.\n\n'
                '**В этом уроке:** как записывается вызов метода и почему он '
                'никогда не меняет исходную строку; склейка `+`, повтор `*` и '
                'проверка вхождения `in`; `find()` и `rfind()` – на какой '
                'позиции стоит кусок; `count()` – сколько раз он встретился; '
                '`replace()` – как заменить одно на другое; `upper()`, '
                '`lower()` и `strip()` – как привести строку к одному виду и '
                'снять невидимый мусор по краям; методы-вопросы вроде '
                '`isdigit()`; `split()` и `join()` – разрезать строку по '
                'разделителю и собрать обратно; f-строки – как подставить '
                'значение прямо в текст.'
            )),
            dict(order=2, block_type='text', title='Метод: запись через точку', content=(
                'Действие до сих пор записывалось одинаково: имя, скобки, '
                'значение внутри – `len(s)`, `ord(c)`, `int(x)`. У строки для '
                'её собственных действий есть другая запись: `s.upper()` – '
                'сначала строка, потом точка, потом название действия.\n\n'
                '> **Метод** – это действие, которое вызывают у конкретного '
                'значения, приписывая его имя через точку. `s.find(\'@\')` '
                'читается «у строки `s` найди собаку».\n\n'
                'Вызвать метод можно и прямо у строки, не заводя переменную: '
                '`\'информатика\'.count(\'а\')` – законная запись.\n\n'
                'Зачем вторая форма, если есть `len()` и `ord()`. Разница в '
                'том, чьё это действие. `len()` умеет измерять что угодно – '
                'строку, список, файл, – поэтому стоит особняком. А поиск '
                'подстроки, смена регистра или разрезание – работа именно со '
                'строкой, и она «принадлежит» строке. Практическая выгода: '
                'набрав `s.`, вы увидите в редакторе список всего, что строка '
                'умеет, – помнить наизусть ничего не нужно.\n\n'
                'И главное правило всего урока. Строка неизменяема (урок '
                '8.1), поэтому **ни один метод строки её не трогает**. Метод '
                'либо отвечает на вопрос – числом, строкой или `True`/`False` '
                '– либо строит рядом **новую** строку. Запись '
                '`s = s.replace(\'а\', \'о\')` означает «собрали новую строку '
                'и перевесили на неё имя `s`», а не «поправили строку на '
                'месте».\n\n'
                'Отсюда ошибка, которая встретится в уроке ещё не раз: '
                '`s.upper()` без присваивания не делает ничего видимого – '
                'результат посчитан и выброшен. **Не присвоил – потерял.**'
            )),
            dict(order=3, block_type='text', title='Склейка, повтор и оператор `in`', content=(
                '`a + b` склеивает две строки в одну (**конкатенация**), '
                '`s * n` повторяет строку `n` раз подряд (**дублирование**). '
                'Обе операции знакомы с урока 1.8, и обе после разговора о '
                'неизменяемости видны в новом свете: **они создают новую '
                'строку**, а исходные остаются нетронутыми.\n\n'
                'Что здесь стоит помнить:\n\n'
                '- строка складывается **только со строкой**: `\'возраст: \' + '
                '16` останавливает программу с `TypeError`. Число превращают '
                'в текст функцией `str()`: `\'возраст: \' + str(16)`;\n'
                '- длины предсказуемы: `len(a + b)` равно `len(a) + len(b)`, а '
                '`len(s * n)` – это `len(s) * n`. Символы никуда не деваются;\n'
                '- `s + \'\'` – та же строка: пустая строка ничего не меняет. '
                'А `s * 0` и `s * -3` дают пустую строку, и это не ошибка – '
                'проверять знак заранее не нужно;\n'
                '- ширину удобно брать из самой строки: `\'=\' * len(title)` – '
                'линия ровно по длине заголовка, какой бы он ни был.\n\n'
                'Оператор **`in`** отвечает, есть ли внутри строки такой '
                'кусок:\n\n'
                '> **Подстрока** – любой непрерывный кусок строки. `sub in s` '
                'истинно, если `sub` встречается внутри `s` хотя бы один раз; '
                'парный `not in` даёт обратный ответ.\n\n'
                'Результат – `True` или `False`, поэтому `in` ставят прямо в '
                'условие `if`. Три вещи, о которые спотыкаются:\n\n'
                '- **регистр важен.** `\'кот\' in \'Кот учёный\'` – ложь: `К` и '
                '`к` – разные символы с разными кодовыми точками (урок 7.3). '
                'Как это вылечить, разберём ниже в этом же уроке;\n'
                '- **пустая строка входит в любую**, даже в пустую: '
                '`\'\' in s` – всегда истина. Так выходит из определения: '
                'пустой кусок есть в любом месте любой строки;\n'
                '- **один символ – частный случай.** `\'@\' in email` – та же '
                'операция, просто подстрока длины 1.\n\n'
                'Отдельно – про то же слово в другом месте. В заголовке цикла '
                '(`for ch in text`) `in` ничего не проверяет: там оно часть '
                'синтаксиса `for` и означает «перебирай по одному».\n\n'
                'Сравнение `==` тоже идёт посимвольно: строки равны, если '
                'совпадают длина и все символы по порядку. `\'Кот\'` и '
                '`\'кот\'` не равны, `\'кот \'` и `\'кот\'` – тоже: пробел '
                'такой же символ, как любой другой. Знаки `<` и `>` сравнивают '
                'строки по кодовым точкам до первого расхождения, а если одна '
                'строка – начало другой, короткая считается меньшей: '
                '`\'кот\' < \'котёнок\'`. Отсюда и порядок по алфавиту: '
                '`\'а\' < \'б\'`. И отсюда же неожиданное `\'Я\' < \'а\'` – '
                'заглавные кириллические буквы стоят в таблице раньше '
                'строчных.'
            )),
            dict(order=4, block_type='code', title='', code_language='python', content=(
                "a = 'Аня'\n"
                "b = 'Иванова'\n"
                '\n'
                'print(len(a + b), len(a) + len(b))  # 10 10 – символы не деваются\n'
                "print(a + '')                       # Аня – пустая строка не меняет\n"
                '\n'
                "print('ab' * 0)                     # пустая строка\n"
                "print('ab' * -3)                    # тоже пустая – и не ошибка\n"
                "print(len('ab' * 4))                # 8 – длина умножается\n"
                '\n'
                "title = 'Методы строк'\n"
                "print('=' * len(title))             # линия ровно по ширине\n"
                '\n'
                "text = 'информатика'\n"
                "print('фор' in text)                # True – буквы идут подряд\n"
                "print('фока' in text)               # False – буквы есть, но не подряд\n"
                "print('кот' in 'Кот учёный')        # False – регистр важен\n"
                "print('' in text)                   # True – пустая входит в любую\n"
                '\n'
                "print('кот' == 'кот')               # True\n"
                "print('Кот' == 'кот')               # False – регистр\n"
                "print('а' < 'б')                    # True – 1072 < 1073\n"
                "print('Я' < 'а')                    # True – заглавные идут раньше\n"
                "print('кот' < 'котёнок')            # True – короткая строка меньшая"
            )),
            dict(order=5, block_type='text', title='`find()` и `rfind()`: где именно стоит кусок', content=(
                '> `s.find(sub)` возвращает индекс первого символа **первого** '
                'вхождения подстроки `sub`. Если вхождения нет – возвращает '
                '`-1`. `s.rfind(sub)` ищет с правого конца и даёт позицию '
                '**последнего** вхождения; буква `r` – от английского right.\n\n'
                'Почему `-1`, а не ошибка: позиции нумеруются с нуля и '
                'отрицательными не бывают, поэтому `-1` – заведомо невозможный '
                'ответ для «нашлось». Одно число служит сразу и результатом, и '
                'признаком неудачи. Не найти – нормальный исход, а не поломка '
                'программы, и останавливать её из-за этого незачем.\n\n'
                '**Ловушка, на которой спотыкаются все.** Писать '
                '`if s.find(\'@\'):` нельзя. Если собака стоит в самом начале '
                'строки, `find()` вернёт `0`, а ноль – это ложь, и условие не '
                'сработает при том, что подстрока на месте. Сравнивать надо '
                'явно: `if s.find(\'@\') != -1:`. А если нужен только ответ '
                '«есть или нет» – берите `in` и не зовите `find()` напрасно.\n\n'
                '**Второй параметр – откуда искать.** `s.find(sub, start)` '
                'начинает просмотр с позиции `start`, а всё, что левее, '
                'пропускает. Позиция при этом возвращается **в номерах '
                'исходной строки**, а не отсчитывается заново от `start`.\n\n'
                '`rfind()` нумерацию не переворачивает: позиция по-прежнему '
                'считается слева с нуля, метод лишь выбирает среди найденных '
                'мест самое правое. Нужен он там, где важен именно '
                '**последний** разделитель: расширение файла стоит после '
                'последней точки, имя файла в пути – после последнего слэша. '
                'При неудаче оба метода дают `-1`, а если вхождение в строке '
                'одно – ответы у них совпадают.\n\n'
                'Найденную позицию почти всегда тут же подставляют в срез: '
                '`s[:pos]` – то, что до неё, `s[pos + 1:]` – то, что после '
                '(сам разделитель в срезы не входит). И одной строкой, чтобы '
                'не удивляться в чужом коде: у обоих методов есть парные '
                '`index()` и `rindex()`, которые вместо `-1` аварийно '
                'останавливают программу.'
            )),
            dict(order=6, block_type='text', title='`count()`: сколько раз встретилось', content=(
                '> `s.count(sub)` возвращает число вхождений подстроки `sub` в '
                'строку `s`. Если не нашлось ничего, ответ – `0`.\n\n'
                '**Главная тонкость – пересечения.** Считаются только '
                '**непересекающиеся** вхождения, слева направо. В строке '
                '`\'ААА\'` подстрока `\'АА\'` на глаз встречается дважды – на '
                'позициях 0 и 1, – но `count()` вернёт `1`: найдя кусок на '
                'позициях 0–1, он продолжает поиск с позиции 2, а не с 1. '
                'Правило простое: нашли – перепрыгнули через находку целиком.\n\n'
                'Кому нужны перекрытия, тот собирает счёт сам: ищет все '
                'вхождения циклом через `find()` и сдвигает начало на **один** '
                'символ, а не на длину находки. Ровно этим занята трассировка '
                'ниже – и именно поэтому её итог совпадает с `count()`, а не с '
                'числом кусков, видимых глазом.\n\n'
                'Курьёз, который прямо следует из определения подстроки: '
                '`s.count(\'\')` даёт `len(s) + 1` – пустая строка «стоит» в '
                'каждом промежутке между символами и по обоим краям. А ещё '
                '`count(sub) > 0` – это то же самое, что `sub in s`; если нужен '
                'только ответ «да/нет», берите `in`, он не пересчитывает строку '
                'до конца.'
            )),
            dict(order=7, block_type='code', title='', code_language='python', content=(
                "text = 'информатика'\n"
                '\n'
                "print(text.find('ма'))    # 5 – позиция первого символа куска\n"
                "print(text.find('а'))     # 6 – первая «а», хотя в слове их две\n"
                "print(text.find('кот'))   # -1 – такого куска здесь нет\n"
                "print(text.find('а', 7))  # 10 – искали с 7, ответ в номерах строки\n"
                '\n'
                "s = '@school.ru'\n"
                "if s.find('@'):           # так нельзя: find вернул 0, а 0 – ложь\n"
                "    print('собака есть')  # эта строка не выполнится!\n"
                "if s.find('@') != -1:     # а так правильно\n"
                "    print('собака есть')\n"
                '\n'
                "email = 'ivanov@school.ru'\n"
                "pos = email.find('@')\n"
                'print(email[:pos])        # ivanov – всё, что до собаки\n'
                'print(email[pos + 1:])    # school.ru – и всё, что после\n'
                '\n'
                "name = 'отчёт.итог.docx'\n"
                "print(name.find('.'))     # 5 – первая точка, из середины имени\n"
                "print(name.rfind('.'))    # 10 – последняя, та самая\n"
                "dot = name.rfind('.')\n"
                'print(name[dot + 1:])     # docx – расширение\n'
                "print('нет точки'.rfind('.'))   # -1 – как и у find\n"
                '\n'
                "print(text.count('а'))    # 2\n"
                "print(text.count('кот'))  # 0 – ноль это ответ, а не сбой\n"
                "print('ААА'.count('АА'))  # 1, а не 2! Вхождения не пересекаются:\n"
                '                          # нашли на 0–1 и продолжили с позиции 2\n'
                "print('кот и кот и кот'.count('кот', 6))   # 2 – считаем с позиции 6"
            )),
            dict(
                order=8, block_type='widget',
                title='Все вхождения по очереди',
                content=(
                    'Этот цикл делает то, чего не умеет ни один метод по '
                    'отдельности: `find()` отдаёт одну позицию, `count()` – '
                    'одно число, а «покажи все места» собирается из `find()` '
                    'со вторым параметром – тем самым, что задаёт, откуда '
                    'искать. Именно это происходит, когда в редакторе жмёшь '
                    'Ctrl+F, а потом «дальше». Пройдите трассу по шагам и '
                    'посмотрите на три вещи: как `i` каждый раз перескакивает '
                    'за найденное вхождение, что цикл заканчивается не по '
                    'длине строки, а по ответу `-1`, и что итоговое `n` '
                    'совпало с тем, что вернул бы `count()`, – по той же самой '
                    'причине, по которой `\'ААА\'.count(\'АА\')` равно 1.'
                ),
                widget_key='loop-trace',
                widget_config={
                    'code': FIND_ALL_CODE,
                    'vars': ['text', 'sub', 'i', 'pos', 'n'],
                    'steps': _find_all_trace(),
                },
            ),
            dict(order=9, block_type='text', title='`replace()`: замена всех вхождений', content=(
                '> `s.replace(old, new)` возвращает **новую** строку, в которой '
                'каждое вхождение `old` заменено на `new`. Сама `s` не меняется '
                '– и не может: строка неизменяема.\n\n'
                '**Самая частая ошибка урока.** Строка `s.replace(\'а\', \'о\')` '
                'сама по себе не делает ничего видимого: результат посчитан и '
                'тут же выброшен, потому что его некуда было записать. Нужно '
                '`s = s.replace(\'а\', \'о\')` – или другое имя, если исходная '
                'строка ещё понадобится.\n\n'
                'Ещё три свойства:\n\n'
                '- **третий параметр – сколько заменять.** '
                '`s.replace(old, new, 1)` заменит только первое вхождение; без '
                'него заменяются все;\n'
                '- **замена на пустую строку – это удаление.** '
                '`s.replace(\' \', \'\')` выбрасывает из строки все пробелы; '
                'отдельного метода «удалить» для этого не нужно;\n'
                '- **метод не знает про слова.** Он работает с подстрокой, а не '
                'со смыслом: замена `\'кот\'` на `\'пёс\'` превратит «котлета» '
                'в «пёслета». Это не поломка, а прямое следствие определения '
                'подстроки – границы слов методу неизвестны.\n\n'
                'Вызовы можно ставить цепочкой: '
                '`s.replace(\'a\', \'b\').replace(\'c\', \'d\')` – второй метод '
                'вызывается уже у результата первого. Исходная строка при этом '
                'тоже не меняется, а вот порядок замен становится важен, если '
                'они задевают одни и те же буквы.'
            )),
            dict(order=10, block_type='code', title='', code_language='python', content=(
                "s = 'привет'\n"
                '\n'
                "s.replace('и', 'ы')       # результат посчитан и выброшен\n"
                'print(s)                  # привет – строка не изменилась\n'
                '\n'
                "s = s.replace('и', 'ы')   # вот теперь сохранили\n"
                'print(s)                  # прывет\n'
                '\n'
                "line = 'кот и кот и котлета'\n"
                "print(line.count('кот'))                # 3\n"
                "print(line.replace('кот', 'пёс'))       # пёс и пёс и пёслета\n"
                "print(line.replace('кот', 'пёс', 1))    # пёс и кот и котлета\n"
                '\n'
                "print('  1 2 3  '.replace(' ', ''))     # 123 – замена на пустую\n"
                '                                        # строку это удаление\n'
                "print('abc'.replace('a', 'b').replace('b', 'c'))  # ccc, а не cbc:\n"
                '                                        # вторая замена работает\n'
                '                                        # с результатом первой'
            )),
            dict(order=11, block_type='text', title='Регистр и невидимый мусор по краям', content=(
                'Программа спрашивает столицу России и сравнивает ответ с '
                'эталоном `\'Москва\'`. В ответ ввели `москва ` – верно и по '
                'смыслу, и почти по буквам, а программа говорит «неверно»: '
                '`\'м\'` и `\'М\'` – разные символы с разными кодовыми точками, '
                'а пробел на конце делает строку длиннее эталона. Задача не в '
                'том, чтобы научить программу понимать смысл, а в том, чтобы '
                '**привести обе строки к одному виду перед сравнением**.\n\n'
                '> `s.upper()` возвращает новую строку со всеми заглавными '
                'буквами, `s.lower()` – со всеми строчными. Не-букв метод не '
                'трогает: цифры, пробелы и знаки препинания переезжают в '
                'результат как есть – регистра у них нет.\n\n'
                'Что стоит знать про эту пару:\n\n'
                '- русские буквы работают наравне с латинскими, **включая '
                '`ё`**. Арифметика кодов из урока 7.2 (`chr(ord(c) - 32)`) на этой '
                'паре ломается: между `ё` и `Ё` в таблице 80 позиций, а не 32. '
                'Метод ничего не вычисляет – он смотрит в таблицу, где для '
                'каждой буквы прописана её пара, и исключения его не смущают;\n'
                '- **главный приём урока – сравнивать после приведения.** '
                '`if answer.lower() == \'москва\':` – введённое приводим к '
                'нижнему регистру, а эталон сразу пишем строчными. Привести '
                'одну сторону и сравнить с `\'Москва\'` – типичная ошибка: '
                'тогда не совпадёт вообще ничего, даже правильно набранный '
                'ответ. Тем же способом закрывается дыра в поиске: '
                '`text.lower().count(\'кот\')` считает и `\'Кот\'`, и '
                '`\'кот\'`. Позиции при этом не съезжают – `lower()` меняет '
                'буквы, а не их количество;\n'
                '- берут обычно `lower()`, а не `upper()`: разницы по сути нет, '
                'просто эталон строчными писать привычнее. Важно другое – не '
                'смешивать оба способа в одной программе.\n\n'
                'Второй вид мусора невидим: это не только пробел, но и '
                'табуляция `\\t`, и перевод строки `\\n`. На экране их нет, а в '
                'строке они есть и сравнению мешают.\n\n'
                '> `s.strip()` возвращает новую строку без **пробельных** '
                'символов в начале и в конце. `lstrip()` срезает только слева, '
                '`rstrip()` – только справа.\n\n'
                '- **середину метод не трогает.** `\'  а  б  \'.strip()` даёт '
                '`\'а  б\'`: два пробела внутри остались. Выбрасывать их – '
                'работа `replace()`;\n'
                '- **аргумент – это набор символов, а не подстрока.** '
                '`s.strip(\'.,!\')` срезает с краёв любые из перечисленных '
                'символов, в любом порядке и количестве, пока не встретит '
                'что-то другое. `\'test.txt\'.strip(\'.txt\')` даёт `\'es\'`: '
                'метод не искал кусок `.txt`, он грыз края, пока попадались '
                'символы `.`, `t` и `x`. Отрезать расширение по-честному – это '
                '`rfind(\'.\')` и срез;\n'
                '- откуда мусор берётся. `input()` перевод строки не отдаёт, но '
                'случайно набранные пробелы остаются полностью. А при чтении '
                'данных из файла в конце каждой строки будет `\\n` – там '
                '`strip()` станет обязательным ритуалом.\n\n'
                'Итоговая связка урока: сначала `strip()`, потом `lower()`, и '
                'только потом сравнение.'
            )),
            dict(order=12, block_type='code', title='', code_language='python', content=(
                "s = 'Привет, Мир!'\n"
                '\n'
                "print(s.upper())        # ПРИВЕТ, МИР!\n"
                "print(s.lower())        # привет, мир!\n"
                'print(s)                # Привет, Мир! – строка не изменилась\n'
                '\n'
                "print('ёжик'.upper())         # ЁЖИК – метод знает про ё\n"
                "print(chr(ord('ё') - 32))     # б – арифметика кодов здесь\n"
                '                              # врёт: между ё и Ё 80 позиций\n'
                '\n'
                "answer = 'МОСКВА'\n"
                "if answer.lower() == 'москва':      # эталон сразу строчными\n"
                "    print('верно')                  # верно\n"
                '\n'
                "line = 'Кот и кот'\n"
                "print(line.count('кот'))            # 1 – заглавная К не подошла\n"
                "print(line.lower().count('кот'))    # 2 – вот теперь оба\n"
                "print(line.lower().find('кот'))     # 0 – ищем в приведённой\n"
                '                                    # строке, позиции прежние\n'
                '\n'
                "t = '  Москва  '\n"
                "print('[' + t.strip() + ']')        # [Москва]\n"
                "print('[' + t.lstrip() + ']')       # [Москва  ] – только слева\n"
                "print('[' + t.rstrip() + ']')       # [  Москва] – только справа\n"
                "print('[' + '  а  б  '.strip() + ']')   # [а  б] – середина цела\n"
                '\n'
                "print('test.txt'.strip('.txt'))     # es, а не test: набор\n"
                '                                    # символов, а не кусок\n'
                '\n'
                "print(' Москва '.strip().lower() == 'москва')   # True – вся связка"
            )),
            dict(order=13, block_type='text', title='Методы-вопросы: `isdigit()`, `isalpha()` и остальные', content=(
                'Вторая группа методов ничего не строит – они отвечают `True` '
                'или `False`:\n\n'
                '| Метод | Отвечает `True`, если |\n'
                '|---|---|\n'
                '| `s.isdigit()` | все символы – цифры |\n'
                '| `s.isalpha()` | все символы – буквы |\n'
                '| `s.isalnum()` | все символы – буквы или цифры |\n'
                '| `s.isspace()` | все символы – пробельные |\n'
                '| `s.isupper()` | все буквы заглавные |\n'
                '| `s.islower()` | все буквы строчные |\n\n'
                'Три вещи, из-за которых на них ошибаются:\n\n'
                '- **вопрос задаётся про всю строку целиком, а не про первый '
                'символ.** `\'123\'.isdigit()` – `True`, `\'12а\'.isdigit()` – '
                '`False`: одного чужого символа достаточно, чтобы ответ стал '
                'ложным. `\'Привет!\'.isalpha()` – тоже `False`, из-за '
                'восклицательного знака, а `\'Привет мир\'.isalpha()` – из-за '
                'пробела;\n'
                '- **пустая строка даёт `False` у всех.** Утверждать «все '
                'символы – цифры» не о чем, если символов нет. Практический '
                'вывод: проверку «человек вообще что-то ввёл» этими методами '
                'не заменить;\n'
                '- **`isdigit()` – это про цифры, а не про числа.** У `\'-5\'` '
                'есть минус, у `\'3.14\'` – точка, и обе строки дают `False`. '
                'Значит, такая проверка пропускает только неотрицательные '
                'целые; для остального её не хватит.\n\n'
                'Зачем всё это нужно: `int(x)` на нечисловой строке аварийно '
                'останавливает программу, а `if x.isdigit():` позволяет '
                'проверить заранее и вежливо попросить ввести число ещё раз.\n\n'
                'И коротко про несколько методов: '
                '`capitalize()` делает заглавной первую букву, а все остальные – '
                'строчными (`\'пРИВЕТ\'` → `\'Привет\'`); `title()` – с '
                'заглавной каждое слово, причём границей слова считает любой '
                'не-буквенный символ, поэтому `\'мария-луиза\'` превращается в '
                '`\'Мария-Луиза\'`; `swapcase()` меняет регистр на '
                'противоположный. Ни один из них не знает, что такое имя '
                'собственное или начало предложения: они работают с символами '
                'по таблице, а не со смыслом текста.'
            )),
            dict(order=14, block_type='text', title='`split()`: разрезать по разделителю', content=(
                '> `s.split(sep)` возвращает **список** кусков строки `s`, '
                'разрезанной по разделителю `sep`. Сам разделитель ни в один '
                'кусок не попадает.\n\n'
                'Здесь появляется новый тип – **список** (`list`). Всерьёз им '
                'займёмся в блоке 9, а пока хватит трёх фактов, и все три уже '
                'знакомы по строкам: список печатается в квадратных скобках – '
                '`[\'2026\', \'08\', \'01\']`; к элементу обращаются по индексу '
                'с нуля (`parts[0]`, работает и `parts[-1]`); длину даёт '
                '`len()`, а перебрать элементы можно циклом `for` – ровно как '
                'символы строки в уроке 8.1.\n\n'
                'Главное правило блока никуда не делось: `split()` исходную '
                'строку не трогает, а строит результат рядом. Не присвоили – '
                'потеряли. И следствие, которое стоит запомнить сразу: '
                '**частей всегда на одну больше, чем разделителей.** Два дефиса '
                'в дате – три части.\n\n'
                'Дальше главная развилка: `split()` без аргумента и '
                '`split(sep)` – это **не одно и то же с умолчанием**, а два '
                'разных поведения.\n\n'
                '- `s.split(sep)` – строгий. Режет по каждому вхождению `sep` и '
                'ничего не додумывает: два разделителя подряд дают между собой '
                '**пустую строку**, разделитель в начале или в конце – пустую '
                'строку с краю. Это не недоразумение: в таблице пустое поле – '
                'тоже значение, и терять его нельзя;\n'
                '- `s.split()` без аргумента – «человеческий». Разделителем '
                'считается любая цепочка пробельных символов (пробел, `\\t`, '
                '`\\n`), несколько подряд идут за один, а пробелы по краям '
                'отбрасываются. Пустых кусков в результате не бывает никогда. '
                'Это готовый инструмент «разбей предложение на слова», и для '
                'текста берут именно его.\n\n'
                'Контрольный пример, который стоит увидеть глазами: у строки '
                '`\'  мама  мыла   раму \'` вызов `.split()` даёт три слова, а '
                '`.split(\' \')` – девять элементов, шесть из которых пустые.\n\n'
                'Третий полезный факт: второй параметр `s.split(sep, maxsplit)` '
                'ограничивает **число разрезов**, а не число кусков, – весь '
                'остаток целиком уезжает в последний элемент. '
                '`\'ivan@mail.ru\'.split(\'@\', 1)` даёт логин и всё остальное, '
                'даже если правее встретится ещё одна собака.\n\n'
                'Чего от `split()` ждать не надо: несколько **разных** '
                'разделителей за раз он не умеет – строку '
                '`\'Иванов, Петров; Сидоров\'` сначала приводят к одному '
                'разделителю через `replace()`, и только потом режут. И '
                'пробелы вокруг частей `split(sep)` не убирает: '
                '`\'Иванов; 9А\'.split(\';\')` даёт кусок `\' 9А\'` вместе с '
                'пробелом, поэтому обычная связка – разрезали и к каждой части '
                '`strip()`.'
            )),
            dict(order=15, block_type='code', title='', code_language='python', content=(
                "s = '2026-08-01'\n"
                "parts = s.split('-')\n"
                '\n'
                "print(parts)           # ['2026', '08', '01'] – список из трёх строк\n"
                'print(parts[0])        # 2026 – первый элемент, индекс с нуля\n'
                'print(parts[-1])       # 01 – последний, как и у строки\n'
                'print(len(parts))      # 3 – столько частей получилось\n'
                'print(s)               # 2026-08-01 – исходная не изменилась\n'
                '\n'
                "row = '  Иванов;9А;5  '\n"
                "print(row.strip().split(';'))   # ['Иванов', '9А', '5'] – задача\n"
                '                                # из начала урока\n'
                '\n'
                "dirty = '  мама  мыла   раму '\n"
                "print(dirty.split())            # ['мама', 'мыла', 'раму']\n"
                'print(len(dirty.split()))       # 3 – цепочка пробелов идёт\n'
                '                                # за один разделитель\n'
                "print(dirty.split(' '))         # ['', '', 'мама', '', 'мыла',\n"
                "                                #  '', '', 'раму', '']\n"
                "print(len(dirty.split(' ')))    # 9 – режет каждый пробел,\n"
                '                                # шесть кусков пустые\n'
                '\n'
                "print('a,,b'.split(','))        # ['a', '', 'b'] – между запятыми\n"
                '                                # пустой кусок\n'
                "print(';Иванов;'.split(';'))    # ['', 'Иванов', ''] – и по краям\n"
                '\n'
                "print('ivan@mail.ru'.split('@', 1))   # ['ivan', 'mail.ru'] – один\n"
                '                                      # разрез, остаток целиком\n'
                '                                      # в последний кусок'
            )),
            dict(
                order=16, block_type='widget',
                title='Что split() делает на самом деле',
                content=(
                    '`split()` – не отдельная магия, а тот же перебор, что и в '
                    'ручном поиске выше. Программа ищет очередной разделитель '
                    'через `find()`, отрезает срезом кусок до него и переносит '
                    'начало за разделитель. Пройдите трассу по шагам и '
                    'посмотрите на две вещи: разделитель не попадает ни в один '
                    'кусок – его съедает правая граница среза, – а последний '
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
            dict(order=17, block_type='text', title='`join()`: собрать обратно', content=(
                'Обратная операция.\n\n'
                '> `sep.join(parts)` возвращает **новую строку**: все элементы '
                '`parts` подряд, а между соседними – строка `sep`.\n\n'
                'И сразу странность синтаксиса, на которой спотыкаются все: '
                'метод вызывается **у разделителя**, а список идёт в скобки. '
                'Пишут `\'-\'.join(parts)`, а не `parts.join(\'-\')`. Выглядит '
                'вывернуто, но логика есть: результат – строка, поэтому и метод '
                'принадлежит строке-разделителю, а главное решение (чем '
                'склеивать) принимает именно он. В скобках при этом может '
                'оказаться что угодно перебираемое – список сегодня, другие '
                'типы позже.\n\n'
                'Второе правило, о которое спотыкаются не реже: **все элементы '
                'должны быть строками.** `\'-\'.join([\'a\', \'b\'])` работает, '
                'а `\'-\'.join([2026, 8, 1])` падает с `TypeError: sequence item '
                '0: expected str instance, int found` – «ожидалась строка, '
                'получено целое». Числа перед сборкой приводят к строке через '
                '`str()`.\n\n'
                'Частные случаи, которые пригодятся: `\' \'.join(...)` собирает '
                'слова в предложение; `\'\'.join(...)` склеивает вообще без '
                'разделителя – пустая строка тоже полноценный разделитель; если '
                'элемент один, разделитель не появится вообще, а пустой список '
                'даст пустую строку. Разделитель ставится **между** кусками, а '
                'не после каждого, – у трёх частей стыков всего два.\n\n'
                'И наконец, почему длинную строку собирают `join()`-ом, а не '
                'склейкой в цикле. Каждая склейка `result = result + ch` строит '
                'новую строку и копирует в неё всё уже накопленное, поэтому в '
                'длинном цикле работа растёт как снежный ком. `join()` знает '
                'все куски заранее, считает нужный размер один раз и собирает '
                'результат за один проход. На слове из шести букв разницы не '
                'увидеть, на сотнях тысяч кусков она принципиальная – измерить '
                'её можно будет, когда появится язык для разговора о скорости. '
                'Правило простое: **если строка собирается в цикле – собирайте '
                'её через `join()`.**'
            )),
            dict(order=18, block_type='code', title='', code_language='python', content=(
                '# 1. переставить дату: 2026-08-01 -> 01.08.2026\n'
                "s = '2026-08-01'\n"
                "p = s.split('-')\n"
                "print('.'.join([p[2], p[1], p[0]]))   # 01.08.2026\n"
                '\n'
                '# 2. слова предложения задом наперёд\n'
                "text = 'мама мыла раму'\n"
                "print(' '.join(text.split()[::-1]))   # раму мыла мама\n"
                '                                      # срез с шагом -1 работает\n'
                '                                      # и со списком: это тоже\n'
                '                                      # последовательность\n'
                '\n'
                '# 3. нормализация ввода: убрать лишние пробелы разом\n'
                "dirty = '  мама  мыла   раму '\n"
                "print(' '.join(dirty.split()))        # мама мыла раму\n"
                '\n'
                "print('-'.join(['одно']))             # одно – разделителю\n"
                '                                      # негде появиться\n'
                "print('-'.join([2026, 8, 1]))\n"
                '# TypeError: sequence item 0: expected str instance, int found\n'
                "print('-'.join([str(2026), str(8), str(1)]))   # 2026-8-1 – вот так"
            )),
            dict(order=19, block_type='text', title='f-строки: подставить значение прямо в текст', content=(
                'Заходим в тему через боль из урока 1.8: чтобы напечатать «Тебе '
                '16 лет», приходилось писать `\'Тебе \' + str(age) + \' лет\'` '
                '– не забыть `str()`, не потерять пробелы у краёв кусков, не '
                'запутаться в кавычках. Одно предложение так собрать можно, а '
                'строку отчёта из пяти значений – уже мучение.\n\n'
                '> **f-строка** – строка, перед кавычкой которой стоит буква '
                '`f`. Внутри неё в фигурных скобках `{}` можно написать '
                'выражение – при выполнении на его место подставится '
                'значение.\n\n'
                '```python\n'
                'age = 16\n'
                "print(f'Тебе {age} лет')        # Тебе 16 лет\n"
                '\n'
                'a = 2\n'
                'b = 3\n'
                "print(f'{a} + {b} = {a + b}')   # 2 + 3 = 5 – в скобках выражение\n"
                "print(f'{0.1 + 0.2}')          # 0.30000000000000004\n"
                "print(f'{0.1 + 0.2:.2f}')      # 0.30 – два знака после запятой\n"
                '```\n\n'
                'Что это даёт: **`str()` не нужен** – число превратится в текст '
                'само; **в скобках любое выражение**, а не только имя '
                'переменной (`{a + b}`, `{name.upper()}`, `{parts[0]}`, '
                '`{len(s)}`); **текст остаётся текстом** – пробелы и знаки '
                'препинания видно там же, где они окажутся в выводе.\n\n'
                'Отдельно про форматирование числа. После выражения можно '
                'поставить двоеточие и указать, как его печатать: `{x:.2f}` – '
                'вещественное с двумя знаками после запятой. Это ровно тот '
                'случай, ради которого стоит вспомнить про точность `float`: '
                '`0.1 + 0.2` печатается как `0.30000000000000004`, а нужны нам '
                'обычно две цифры, а не все семнадцать.\n\n'
                'Две ловушки. **Забыли `f`** – ошибки не будет, программа честно '
                'напечатает `{age}` фигурными скобками; симптом узнаваемый. И '
                '**нужна сама фигурная скобка в тексте** – её удваивают: `{{` и '
                '`}}`. Оговорка про чужой код: старые способы форматирования '
                '(`\'%d\'` и метод `.format()`) в нём встречаются, и знать об их '
                'существовании полезно, – но писать сегодня надо f-строки.'
            )),
            dict(order=20, block_type='text', title='Шпаргалка', content=(
                'Одна таблица на весь урок – каждая операция встречается здесь '
                'ровно один раз:\n\n'
                '| Операция | Что делает | Пример | Результат |\n'
                '|---|---|---|---|\n'
                '| `a + b` | склеивает две строки | `\'Ива\' + \'нов\'` | '
                '`\'Иванов\'` |\n'
                '| `s * n` | повторяет строку `n` раз | `\'ab\' * 3` | '
                '`\'ababab\'` |\n'
                '| `sub in s` | отвечает, есть ли подстрока | `\'фор\' in '
                '\'информатика\'` | `True` |\n'
                '| `s == t` | сравнивает посимвольно | `\'Кот\' == \'кот\'` | '
                '`False` |\n'
                '| `s.find(sub)` | позиция первого вхождения | '
                '`\'информатика\'.find(\'ма\')` | `5` |\n'
                '| `s.rfind(sub)` | позиция последнего вхождения | '
                '`\'отчёт.итог.docx\'.rfind(\'.\')` | `10` |\n'
                '| `s.count(sub)` | число непересекающихся вхождений | '
                '`\'ААА\'.count(\'АА\')` | `1` |\n'
                '| `s.replace(a, b)` | заменяет все вхождения | '
                '`\'кот и кот\'.replace(\'кот\', \'пёс\')` | `\'пёс и пёс\'` |\n'
                '| `s.replace(a, b, n)` | заменяет первые `n` вхождений | '
                '`\'кот и кот\'.replace(\'кот\', \'пёс\', 1)` | `\'пёс и кот\'` |\n'
                '| `s.upper()` / `s.lower()` | приводит к одному регистру | '
                '`\'Москва\'.lower()` | `\'москва\'` |\n'
                '| `s.strip()` | убирает пробельные по краям | '
                '`\'  да  \'.strip()` | `\'да\'` |\n'
                '| `s.isdigit()` | все ли символы цифры | `\'-5\'.isdigit()` | '
                '`False` |\n'
                '| `s.split(sep)` | режет по разделителю | '
                '`\'Иванов;9А;5\'.split(\';\')` | `[\'Иванов\', \'9А\', \'5\']` |\n'
                '| `s.split()` | режет текст на слова | `\'мама мыла\'.split()` | '
                '`[\'мама\', \'мыла\']` |\n'
                '| `sep.join(parts)` | собирает строку из списка | '
                '`\'-\'.join([\'2026\', \'08\', \'01\'])` | `\'2026-08-01\'` |\n'
                '| `f\'{x}\'` | подставляет значение в текст | '
                '`f\'Тебе {age} лет\'` | `\'Тебе 16 лет\'` |\n\n'
                'И одно правило, верное для каждой строки таблицы: **ни одна из '
                'этих операций не меняет исходную строку.** Любая возвращает '
                'новое значение – строку, число или `True`/`False`, – и если это '
                'строка, её надо куда-то присвоить, иначе она просто пропадёт.'
            )),
            dict(order=21, block_type='text', title='Коротко', content=(
                '- **Метод вызывается у значения через точку**: `s.upper()`, '
                '`s.split(\';\')`. И ни один метод строки не меняет саму строку – '
                'он либо отвечает на вопрос, либо строит новую. Не присвоил – '
                'потерял.\n'
                '- `+` склеивает строки (только строка со строкой, иначе '
                '`TypeError` и `str()`), `*` повторяет, `in` отвечает «есть ли '
                'кусок», `==` сравнивает посимвольно, а `<` и `>` – по кодовым '
                'точкам, отсюда `\'Я\' < \'а\'`.\n'
                '- `find()` и `rfind()` дают позицию первого и последнего '
                'вхождения, а при неудаче `-1`, поэтому проверка всегда '
                '`!= -1`. `count()` считает **непересекающиеся** вхождения: в '
                '`\'ААА\'` кусок `\'АА\'` находится один раз.\n'
                '- `replace()` заменяет все вхождения, третий параметр '
                'ограничивает их число, а замена на пустую строку – это '
                'удаление.\n'
                '- Приводить строки к одному виду перед сравнением: сначала '
                '`strip()` – снять невидимые пробелы и переводы строки по '
                'краям, потом `lower()` – и только потом `==`. Методы-вопросы '
                '(`isdigit()`, `isalpha()`) спрашивают про **всю** строку, на '
                'пустой дают `False`, а минус и точку цифрами не считают.\n'
                '- `split()` режет строку по разделителю и возвращает список; '
                'частей всегда на одну больше, чем разделителей. Без аргумента '
                'он делит текст на слова и пустых кусков не оставляет, с '
                'аргументом – режет строго и пустые куски сохраняет.\n'
                '- `join()` вызывается **у разделителя** (`\'-\'.join(parts)`), '
                'элементы обязаны быть строками, а разделитель ставится между '
                'кусками. Собирать длинную строку в цикле склейкой не надо – '
                'для этого есть `join()`. А f-строка (`f\'Тебе {age} лет\'`) '
                'подставляет значение выражения прямо в текст.'
            )),
        ])

        quiz = _self_check(
            slug='self-check-metody-strok',
            title='Самопроверка: методы строк',
            description='Пять вопросов по теме урока.',
            questions=[
                dict(
                    type='choice',
                    text=(
                        'Программа выполняет три строки:\n\n'
                        '```python\n'
                        "row = 'Иванов;9А;5'\n"
                        "parts = row.split(';')\n"
                        'print(parts[1])\n'
                        '```\n\n'
                        'Что она напечатает?'
                    ),
                    choices=[
                        ('9А – второй элемент списка: индексы начинаются с нуля',
                         True),
                        ('Иванов – первый элемент списка', False),
                        ('9А;5 – всё, что стоит правее первой точки с запятой',
                         False),
                        ('Ошибку – к элементу списка нельзя обращаться по '
                         'индексу', False),
                    ],
                ),
                dict(
                    type='choice',
                    text="Что вернёт выражение `'ААА'.count('АА')`?",
                    choices=[
                        ('1 – вхождения считаются непересекающимися: найдя кусок '
                         'на позициях 0–1, count продолжает с позиции 2', True),
                        ('2 – подстрока «АА» видна на позициях 0 и 1', False),
                        ('3 – по числу букв «А» в строке', False),
                        ('0 – count работает только с одиночными символами',
                         False),
                    ],
                ),
                dict(
                    type='choice',
                    text=(
                        'Программа выполняет три строки:\n\n'
                        '```python\n'
                        "s = 'кот и кот'\n"
                        "s.replace('кот', 'пёс')\n"
                        'print(s)\n'
                        '```\n\n'
                        'Что она напечатает?'
                    ),
                    choices=[
                        ('кот и кот – replace вернул новую строку, но её никуда '
                         'не сохранили', True),
                        ('пёс и пёс – replace заменил слова прямо в строке s',
                         False),
                        ('None – метод ничего не вернул', False),
                        ('Ошибку – строку нельзя изменять', False),
                    ],
                ),
                dict(
                    type='choice',
                    text=(
                        'Программа читает файл построчно и сравнивает каждую '
                        "строку с эталоном: `if line == 'да':`. Ответ «да» "
                        'срабатывает не всегда – в конце строки из файла '
                        'остаётся символ `\\n`. Что нужно сделать со строкой '
                        'перед сравнением?'
                    ),
                    choices=[
                        ('Вызвать strip() и срезать перевод строки по краям',
                         True),
                        ('Заменить `==` на `in` – тогда лишний символ не '
                         'помешает', False),
                        ('Привести строку к верхнему регистру через upper()',
                         False),
                        ('Ничего: перевод строки при чтении файла Python '
                         'отбрасывает сам', False),
                    ],
                ),
                dict(
                    type='text',
                    text=(
                        "Сколько элементов будет в списке `'мама мыла "
                        "раму'.split()`? Впишите только число."
                    ),
                    correct_text_answer='3',
                ),
            ],
        )
        ArticleQuiz.objects.get_or_create(
            article=article, quiz=quiz,
            defaults={'label': 'Проверь себя', 'order': 1},
        )

    def seed_8_3(self):
        article = Article.objects.get(slug='8-3-algoritmicheskie-zadachi-so-strokami')
        article.description = (
            'Три задачи, для которых готового метода нет: самая длинная '
            'цепочка одинаковых символов подряд, палиндром двумя способами и '
            'поиск самого короткого отрезка с заданным числом нужных букв. '
            'Общая схема «нормализовать – пройти один раз – накопить ответ», '
            'приём «окно» из двух границ, идущих только вперёд, и разбор '
            'краёв, на которых такие решения ломаются.'
        )
        article.save(update_fields=['description'])

        _replace_blocks(article, [
            dict(order=1, block_type='text', title='О чём этот урок', content=(
                'У строки есть готовый метод почти на любой вопрос. Найти '
                'кусок – `find()`, заменить – `replace()`, разрезать по '
                'разделителю – `split()`, снять пробелы по краям – `strip()`. '
                'Пока вопрос звучит как «где», «сколько раз» или «на что '
                'заменить», ответ за нас уже написан.\n\n'
                'Но стоит спросить иначе – «какая цепочка самая длинная», '
                '«сколько одинаковых символов идёт подряд», «есть ли кусок, в '
                'котором ровно `k` таких букв», – и готового метода не '
                'находится. Общее у таких вопросов одно: ответ зависит не от '
                'всей строки разом, а от **куска** строки, а кусков в строке '
                'много и годятся из них не все. Язык не знает, какой кусок '
                'нужен вам, – и строку приходится проходить самому.\n\n'
                '**В этом уроке:** общий приём, на котором держатся все такие '
                'задачи, – один проход по строке и переменные-накопители; '
                'самая длинная цепочка одинаковых символов подряд; проверка '
                'строки на палиндром двумя способами – срезом и двумя '
                'указателями; поиск самого короткого отрезка с заданным числом '
                'нужных букв, где впервые появляется приём «окно». Нового '
                'инструмента не будет ни одного: всё уже в руках – индекс, '
                'срез, `in`, `count()`, `lower()`, `isalpha()` и обычный цикл.'
            )),
            dict(order=2, block_type='text', title='Общий приём: один проход и накопитель', content=(
                'Задачи этого урока решаются не озарением, а одной общей '
                'схемой:\n\n'
                '1. **нормализовать** – привести строку к виду, в котором '
                'сравнение честное (регистр, лишние символы);\n'
                '2. **пройти один раз** слева направо;\n'
                '3. **накопить ответ** в переменных, которые живут между '
                'шагами цикла.\n\n'
                'Переменные-накопители – та же идея, что в поиске минимума и '
                'максимума (блок 4): не хранить все увиденные значения, а '
                'держать одно, самое нужное, и обновлять его по дороге. Здесь '
                'вместо чисел – символы и их счётчики. Это и есть память '
                'программы о том, что она уже видела.\n\n'
                'Почему «один проход», а не «пройти столько раз, сколько '
                'понадобится»? Потому что строка неизменяема: лишний проход – '
                'это лишняя работа, символы придётся перечитывать с самого '
                'начала. Всё, что понадобится в конце, надо копить по дороге.\n\n'
                'И сразу честное предупреждение: почти вся сложность таких '
                'задач не в основной идее, а в **краях** – первом символе, '
                'последнем символе и пустой строке. Идею придумывают за '
                'минуту, а ломается решение всегда там.'
            )),
            dict(order=3, block_type='text', title='Задача 1. Самая длинная цепочка одинаковых символов', content=(
                'Постановка: дана строка, надо найти длину самой длинной '
                'группы одинаковых символов, идущих подряд. В `\'ААБВВВВГ\'` '
                'ответ 4 (четыре «В»), в `\'абвгд\'` – 1, в пустой строке – '
                '0.\n\n'
                'Идея. Идём по строке начиная со **второго** символа и на '
                'каждом шаге задаём один вопрос: «этот символ такой же, как '
                'предыдущий?»\n\n'
                '- **да** – текущая цепочка продолжается, её длина растёт на '
                '1;\n'
                '- **нет** – цепочка оборвалась, начинается новая, и в ней '
                'пока один символ.\n\n'
                'Отсюда две переменные:\n\n'
                '- `cur` – длина цепочки, которая идёт **прямо сейчас**;\n'
                '- `best` – самая длинная из всех, что уже встретились.\n\n'
                'Правило, которое стоит запомнить дословно: сначала обнови '
                '`cur`, а потом **сразу** сверь его с `best` – на каждом шаге, '
                'а не в момент обрыва цепочки. Почему именно так, разберём '
                'чуть ниже: это главная ловушка задачи.\n\n'
                'Сравнение соседей – это `s[i] == s[i - 1]`, и здесь работает '
                'ровно то, что дал урок 8.1: символ достаётся по индексу, '
                'строку при этом никто не меняет.'
            )),
            # Иллюстрация: плоский минималистичный стиль, как в блоках 2, 5–8.
            # Сверху лента строки 'ААБВВВВГ', разложенная по клеткам; каждая
            # цепочка одинаковых символов залита своим цветом (АА – один цвет,
            # Б – второй, ВВВВ – третий, Г – четвёртый), границы между
            # цепочками отмечены вертикальными разделителями.
            # Под лентой две дорожки-строки, подписанные слева именами
            # переменных, значения выровнены строго под клетками:
            #   cur :  1  2  1  1  2  3  4  1
            #   best:  1  2  2  2  2  3  4  4
            # Значения best, где он вырос, выделены (жирнее/ярче) – видно, что
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
                '    best = 1               # первый символ – цепочка длиной 1\n'
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
                    'Первая – `best` никогда не уменьшается: он запоминает '
                    'рекорд, а не текущее состояние, и потому спокойно '
                    'переживает обрыв цепочки. Вторая – посмотрите, в какой '
                    'момент `best` дорастает до четвёрки: не тогда, когда '
                    'цепочка «В» обрывается буквой «Г», а ещё внутри неё, на '
                    'четвёртой «В». Именно поэтому цепочке необязательно '
                    'обрываться – она может упираться прямо в конец строки, и '
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
                '**1. Последняя цепочка.** Соблазн – обновлять `best` в момент '
                'обрыва цепочки: «кончилась – подвели итог». На `\'ААБВВВВГ\'` '
                'это ещё сработает, а на `\'ААБВВВВ\'` – нет: последняя '
                'цепочка ничем не обрывается, строка просто кончается, и итог '
                'по ней никто не подведёт. Программа ответит 2 вместо 4. '
                'Лечение – сверять на каждом шаге, тогда особого случая «конец '
                'строки» просто не существует.\n\n'
                '**2. Первый символ.** У него нет предыдущего. И `s[i - 1]` '
                'при `i = 0` даст не ошибку, а **последний символ строки** – '
                'отрицательный индекс из урока 8.1 сработает молча и испортит '
                'ответ: на строке `\'АБА\'` программа решит, что первая и '
                '«предыдущая» буквы совпали. Поэтому цикл начинается с 1, а '
                'первый символ учтён заранее как цепочка длиной 1.\n\n'
                '**3. Пустая строка.** Цикл не выполнится ни разу, и `best` '
                'останется тем, чем его назначили. Напишешь `best = 1` без '
                'проверки – программа сообщит о цепочке в строке, где нет ни '
                'одного символа.\n\n'
                'Общая мораль, которая пригодится и дальше: краевые случаи – '
                'не редкая экзотика, а обязательная часть проверки. Три '
                'вопроса к любой готовой программе: что будет на пустом входе, '
                'что на входе из одного элемента и что, если ответ лежит в '
                'самом конце.'
            )),
            dict(order=8, block_type='text', title='Задача 2. Палиндром', content=(
                '> **Палиндром** – текст, который читается одинаково слева '
                'направо и справа налево.\n\n'
                'Со словом `\'шалаш\'` всё просто. С «А роза упала на лапу '
                'Азора» – нет: там пробелы и две заглавные буквы. Для '
                'человека это не помеха, а для программы `\'А\' == \'а\'` – '
                'ложь: это два разных символа с разными кодовыми точками '
                '(уроки 8.1 и 8.2).\n\n'
                'Поэтому решение делится на два независимых шага, и путать их '
                'не надо:\n\n'
                '1. **нормализация** – оставить только буквы и привести их к '
                'одному регистру;\n'
                '2. **проверка** – сравнить получившееся с самим собой '
                'наоборот.\n\n'
                'Первый шаг – ровно тот цикл, что собирал очищенную строку в '
                'уроке 8.2: идём по символам, спрашиваем у каждого '
                '`isalpha()`, подходящие приклеиваем в нижнем регистре к новой '
                'строке. Второй шаг после этого – одно сравнение:\n\n'
                '```python\n'
                'clean == clean[::-1]\n'
                '```\n\n'
                'Срез `[::-1]` разворачивает строку целиком, а палиндром от '
                'не-палиндрома отличает ровно то, что перевёрнутая строка '
                'равна исходной. Длина при развороте не меняется, так что '
                'сравнение всегда честное. Края разбираются сами собой: '
                'пустая строка и строка из одного символа – палиндромы, '
                'потому что переворачивать в них нечего.\n\n'
                'И честная оговорка. В уроке 8.2 сказано, что собирать строку '
                'в цикле склейкой не надо и правильный инструмент – `join()`. '
                'Это по-прежнему правда, но чтобы отдать `join()` куски, нужен '
                'список и метод `append()`, а списками мы займёмся в блоке 9. '
                'Так что сейчас собираем склейкой – сознательно и понимая, что '
                'это не окончательный вариант.\n\n'
                'Второй способ – **два указателя**. Разумный вопрос: если '
                'одной строки хватает, зачем что-то ещё? Затем, что срез '
                '`[::-1]` **строит новую строку целиком** – копию всей '
                'исходной, до последнего символа, – и только потом сравнивает. '
                'Человек, проверяя палиндром глазами, так не делает: он берёт '
                'первую и последнюю буквы, сравнивает и **останавливается на '
                'первом же несовпадении**. У слова `\'арбуз\'` первая буква '
                '«а», последняя «з» – ответ известен после одного сравнения, '
                'остальные буквы можно не смотреть.\n\n'
                'Приём называется **два указателя**: переменная `i` идёт слева '
                'направо, `j` – справа налево, работа продолжается, пока '
                '`i < j`. Как только `s[i] != s[j]`, ответ `False` и `break`; '
                'если указатели встретились – все пары совпали, ответ `True`. '
                'Сравнений выходит вдвое меньше, чем символов в строке, а на '
                'нечётной длине центральный символ не проверяется вообще – '
                'сравнивать его не с чем.\n\n'
                'Ответ у обоих способов один и тот же, различаются они ценой: '
                'один строит копию всей строки, второй обходится двумя '
                'переменными. Что писать в реальной программе – обычно первый, '
                'он короче и читается мгновенно; второй важен как **приём**, и '
                '«двумя концами навстречу» мы ещё вернёмся, когда дойдём до '
                'списков и сортировок.'
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
                'print(clean[::-1])             # арозаупаланалапуазора – та же строка\n'
                'print(clean == clean[::-1])    # True\n'
                '\n'
                "print('привет' == 'привет'[::-1])   # False – тевирп это не привет\n"
                '\n'
                "print('' == ''[::-1])          # True – переворачивать нечего\n"
                "print('я' == 'я'[::-1])        # True – и в строке из одного символа тоже"
            )),
            dict(
                order=10, block_type='widget',
                title='Два указателя навстречу',
                content=(
                    'Та же проверка палиндрома, но без среза: два указателя '
                    'идут навстречу друг другу по уже очищенной строке. '
                    'Следите за тем, где цикл останавливается. Он не доходит '
                    'до конца строки – указатели встречаются в середине, и на '
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
            dict(order=11, block_type='text', title='Задача 3. Отрезок с заданным свойством', content=(
                'Постановка. Дана строка из букв и число `k`. Нужно найти '
                '**минимальную длину непрерывного куска**, внутри которого '
                'буква `X` встречается ровно `k` раз.\n\n'
                'В строке `\'AXBXCX\'` буква `X` стоит на позициях 1, 3 и 5. '
                'При `k = 2` подойдёт кусок `\'XBX\'` длиной 3; кусок '
                '`\'AXBXC\'` тоже содержит две `X`, но он длиннее. Если букв '
                '`X` в строке меньше, чем `k`, подходящего куска нет вовсе.\n\n'
                'Перебрать все пары границ – начало куска и конец – можно, но '
                'пар слишком много: на строке в миллион символов такой перебор '
                'не досчитает.\n\n'
                'Идея окна. Держим не пару границ, а **окно** – кусок между '
                'левой и правой границей, – и обе двигаем только вперёд. '
                'Правую двигаем шаг за шагом, пока внутри не наберётся ровно '
                '`k` букв `X`. Как только набралось – подтягиваем левую, пока '
                'букв внутри всё ещё `k`, и запоминаем длину. Выбрасывать '
                'стало нечего – снова двигаем правую.'
            )),
            dict(order=12, block_type='code', title='', code_language='python', content=(
                "s = 'AXBXCX'\n"
                'k = 2                   # сколько букв X должно быть внутри куска\n'
                '\n'
                'left = 0                # левая граница окна\n'
                'count = 0               # сколько X внутри окна прямо сейчас\n'
                'best = -1               # длина самого короткого подходящего куска\n'
                '\n'
                'for right in range(len(s)):\n'
                '    if s[right] == \'X\':\n'
                '        count = count + 1\n'
                '\n'
                '    # справа набралось ровно k букв X – окно можно подтягивать\n'
                '    while count == k:\n'
                '        length = right - left + 1\n'
                '        if best == -1 or length < best:\n'
                '            best = length       # запомнили, пока окно подходит\n'
                '        if s[left] == \'X\':\n'
                '            count = count - 1   # отпустили X: внутри осталось k - 1\n'
                '        left = left + 1         # левая граница шагнула вправо\n'
                '\n'
                "print(best)             # 3 – самый короткий кусок 'XBX'\n"
                '\n'
                '# та же программа на других строках:\n'
                "#   'XXABX', k = 2  ->  2   кусок 'XX'\n"
                "#   'AXB',   k = 2  -> -1   двух X в строке нет"
            )),
            dict(order=13, block_type='text', title='Почему окно вообще работает', content=(
                'Левую границу никогда не приходится возвращать назад. Пока '
                'внутри меньше `k` букв `X`, окно может расти только справа. '
                'Как только их ровно `k`, левую двигают вперёд – символы, '
                'которые из окна ушли, ответ короче уже не сделают.\n\n'
                'И ни один подходящий кусок не теряется: для каждой правой '
                'границы записан самый короткий кусок, который именно на ней '
                'заканчивается. Кусок, который кончается левее, был проверен '
                'раньше – тогда его правая точка и была границей.'
            )),
            dict(order=14, block_type='text', title='Что общего у трёх решений', content=(
                'Три разные задачи – одна схема:\n\n'
                '| Задача | Нормализация | Что копим по дороге | Ответ |\n'
                '|---|---|---|---|\n'
                '| Цепочка | не нужна | `cur` и `best` | значение `best` |\n'
                '| Палиндром | только буквы, нижний регистр | ничего – сравниваем целиком или парами | сошлись ли все пары |\n'
                '| Отрезок | не нужна | `left`, `count` и `best` | значение `best` |\n\n'
                'Третья задача устроена иначе, и это стоит заметить. В цепочке '
                'и палиндроме накопитель отвечал на вопрос «что уже было»; в '
                'задаче про отрезок копится ещё и **место**, до которого '
                'просмотрена строка, – левая граница. Именно она и делает окно '
                'окном: без неё пришлось бы возвращаться назад, а возвращаться '
                'по строке назад – это ровно тот перебор всех пар границ, от '
                'которого мы уходили.\n\n'
                'Общее у всех трёх – не приём, а порядок работы. Когда готового '
                'метода нет, задача решается не озарением, а разбором на три '
                'вопроса: что надо привести к общему виду перед сравнением, '
                'что нужно помнить между шагами цикла и на чём решение '
                'сломается по краям. Все три ответа собираются из инструментов, '
                'которые уже есть.'
            )),
            dict(order=15, block_type='text', title='Коротко', content=(
                '- Готового метода у задач этого урока нет, но и нового '
                'инструмента не нужно: всё решается индексом, срезом, '
                '`count()`, `lower()` и обычным циклом.\n'
                '- Общая схема: **нормализовать – пройти один раз – накопить '
                'ответ**. Накопитель – это память программы между шагами '
                'цикла: строка неизменяема, перечитать её заново дёшево не '
                'выйдет.\n'
                '- Самая длинная цепочка: `cur` живёт внутри текущей серии, '
                '`best` – над всей строкой. Сверять их надо **на каждом '
                'шаге**, а не в момент обрыва, иначе цепочка, упёршаяся в '
                'конец строки, потеряется. Первый символ учитывается отдельно, '
                'пустая строка даёт 0.\n'
                '- Палиндром делится на два независимых шага: **нормализация** '
                '(только буквы, один регистр) и **проверка**. Проверка – либо '
                '`clean == clean[::-1]` (коротко, но строит копию строки), '
                'либо два указателя навстречу (сравнений вдвое меньше, '
                'останавливаются на первом несовпадении).\n'
                '- Отрезок с заданным числом букв `X` ищется **окном**: правая '
                'граница расширяет окно, левая подтягивает его, когда внутри '
                'стало ровно `k`. Обе границы идут только вперёд – по строке '
                'не приходится возвращаться.\n'
                '- Любое готовое решение проверяют на краях: пустая строка, '
                'строка из одного символа и ответ, который лежит в самом '
                'конце.'
            )),
        ])

        quiz = _self_check(
            slug='self-check-algoritmicheskie-zadachi-so-strokami',
            title='Самопроверка: алгоритмические задачи со строками',
            description='Пять вопросов по теме урока.',
            questions=[
                dict(
                    type='choice',
                    text=(
                        'Программа из урока ищет самую длинную цепочку '
                        'одинаковых символов:\n\n'
                        '```python\n'
                        "s = 'АБББА'\n"
                        'best = 0\n'
                        'cur = 0\n'
                        'if len(s) > 0:\n'
                        '    best = 1\n'
                        '    cur = 1\n'
                        'for i in range(1, len(s)):\n'
                        '    if s[i] == s[i - 1]:\n'
                        '        cur = cur + 1\n'
                        '    else:\n'
                        '        cur = 1\n'
                        '    if cur > best:\n'
                        '        best = cur\n'
                        'print(best)\n'
                        '```\n\n'
                        'Что она напечатает?'
                    ),
                    choices=[
                        ('3 – самая длинная цепочка здесь «БББ»', True),
                        ('1 – все соседние символы разные', False),
                        ('4 – столько пар соседей проверяет цикл', False),
                        ('2 – так ответит программа, которая обновляет рекорд '
                         'только при обрыве цепочки', False),
                    ],
                ),
                dict(
                    type='choice',
                    text=(
                        'Программа проверяет палиндром одной строкой:\n\n'
                        '```python\n'
                        "s = 'А роза упала на лапу Азора'\n"
                        'print(s == s[::-1])\n'
                        '```\n\n'
                        'Она печатает `False`, хотя фраза – палиндром. В чём '
                        'дело?'
                    ),
                    choices=[
                        ('Сравнивается сырая строка: пробелы стоят не '
                         'симметрично, а заглавная «А» не равна строчной. '
                         'Перед проверкой строку нужно привести к одному виду',
                         True),
                        ('Срез `[::-1]` разворачивает только латиницу, '
                         'кириллицу он оставляет как есть', False),
                        ('`[::-1]` строит новую строку, а две разные строки '
                         'оператор `==` всегда считает неравными', False),
                        ('Строку с пробелами нужно сравнивать посимвольно в '
                         'цикле: оператор `==` работает только с одним словом',
                         False),
                    ],
                ),
                dict(
                    type='choice',
                    text=(
                        'Чем проверка `clean == clean[::-1]` отличается от '
                        'сравнения двумя указателями навстречу?'
                    ),
                    choices=[
                        ('Ответ у них один и тот же. Разница в работе: срез '
                         'строит копию всей строки, а указатели обходятся '
                         'двумя переменными и останавливаются на первом же '
                         'несовпадении', True),
                        ('Указатели требуют, чтобы строка была заранее '
                         'приведена к одному регистру, а срезу это не нужно',
                         False),
                        ('Указатели дают неверный ответ на строке нечётной '
                         'длины: средний символ не с чем сравнивать', False),
                        ('Срез годится только для латиницы, а указатели '
                         'работают с любыми буквами', False),
                    ],
                ),
                dict(
                    type='choice',
                    text=(
                        'Окно дошло до состояния, когда внутри ровно `k` букв '
                        '`X`. Что программа делает следующим шагом?'
                    ),
                    choices=[
                        ('Запоминает длину окна и двигает левую границу '
                         'вперёд – вдруг тот же кусок получится короче', True),
                        ('Заканчивает работу: первый подходящий кусок и есть '
                         'самый короткий', False),
                        ('Двигает правую границу дальше, пока букв не станет '
                         '`k + 1`', False),
                        ('Возвращает левую границу в начало строки и набирает '
                         'окно заново', False),
                    ],
                ),
                dict(
                    type='text',
                    text=(
                        'В строке `\'AXXBXA\'` нужно найти самый короткий '
                        'непрерывный кусок, внутри которого ровно три буквы '
                        '`X`. Сколько символов в нём? Впишите только число.'
                    ),
                    correct_text_answer='4',
                ),
            ],
        )
        ArticleQuiz.objects.get_or_create(
            article=article, quiz=quiz,
            defaults={'label': 'Проверь себя', 'order': 1},
        )

    def seed_8_4(self):
        article = Article.objects.get(slug='8-4-fayly-chtenie-i-zapis')
        article.description = (
            'Файлы: зачем данные хранят на диске и как их оттуда достать. '
            'open() и три режима – чтение, запись и дописывание; with и '
            'закрытие файла; чтение построчно и ловушка с переводом строки в '
            'конце каждой строки; запись без перевода строки и str() для '
            'чисел; FileNotFoundError и рабочая папка программы.'
        )
        article.save(update_fields=['description'])

        _replace_blocks(article, [
            dict(order=1, block_type='text', title='О чём этот урок', content=(
                'Программа складывает числа – и после каждого запуска просит '
                'ввести их заново. Закрылось окно, и данные вместе с ним: '
                'переменные жили только в памяти, пока программа работала. '
                'Запустишь её второй раз – она снова спросит те же числа, а '
                'если числа были посчитаны час назад, этот час придётся '
                'потратить ещё раз.\n\n'
                'Обратная беда: данных слишком много. Пока строк десять, их '
                'наберёшь руками; когда их десять тысяч, вводить их с '
                'клавиатуры не станет никто. А между тем это обычный вход '
                'задачи – файл, который лежит рядом с программой.\n\n'
                'И то и другое решается одинаково: данные кладут в файл на '
                'диске. В файле они переживают закрытие окна, и оттуда их '
                'можно прочитать сколько угодно раз – не набирая заново.\n\n'
                '**В этом уроке:** что такое файл для программы и зачем ему '
                'кодировка; как открыть файл функцией `open()` и что делает '
                'каждый из режимов `\'r\'`, `\'w\'` и `\'a\'`; почему '
                'закрывать файл доверяют `with`; способы прочитать файл; '
                'главная ловушка – перевод строки `\\n` в конце каждой '
                'строки; как записать результат в файл и как дописать его в '
                'конец; где программа ищет файл и что значит '
                '`FileNotFoundError`.'
            )),
            dict(order=2, block_type='text', title='Файл глазами программы', content=(
                'Всё, что программа знает, живёт в переменных, а переменные '
                'живут, пока работает программа.\n\n'
                '> **Файл** – данные на диске, у которых есть имя. Программа '
                'открывает их по этому имени, читает и пишет, а после её '
                'завершения они остаются на месте.\n\n'
                'Имя файла – это на самом деле **путь**, то есть адрес, по '
                'которому его искать. Короткое имя `data.txt` адресует файл '
                'рядом с программой, полное – конкретное место на диске; об '
                'этом ниже, в отдельном блоке.\n\n'
                'Дальше важная подробность: на диске текст лежит **не** '
                'символами, а байтами, а кодировка – то самое правило перевода '
                'одного в другое, которым занят весь блок 7. Поэтому при '
                'чтении файла мало сказать, что открыть, – надо ещё указать, в '
                'какой кодировке написан текст, иначе получатся кракозябры из '
                'урока 7.2. Проще всего её не угадывать, а договориться заранее: '
                'файлы пишут в UTF-8, и её же используют при открытии.\n\n'
                'И ещё одно, что неочевидно: для программы текстовый файл – '
                'это **одна длинная последовательность символов**, разбитая '
                'на строки переводом строки. Никаких отдельных «записей» и '
                '«ячеек» там нет: строка кончается там, где стоит `\\n`. '
                'Сколько их в файле, программа заранее не знает – она '
                'читает, пока строки не кончатся.'
            )),
            dict(order=3, block_type='text', title='`open()`: три вещи в одной строке', content=(
                'Открывает файл встроенная функция `open()`:\n\n'
                '```python\n'
                "f = open('numbers.txt', 'r', encoding='utf-8')\n"
                '...\n'
                'f.close()\n'
                '```\n\n'
                '> **`open(путь, режим, encoding=\'utf-8\')`** – открывает '
                'файл и возвращает **объект файла**: то, через что дальше '
                'идёт вся работа – чтение, запись, закрытие.\n\n'
                'В строке названы три вещи: что открыть (путь), как открыть '
                '(режим) и в какой кодировке читать написанное.\n\n'
                '**`encoding=\'utf-8\'` указывают всегда.** Не «когда '
                'понадобится», не «если в файле русские буквы», а в каждом '
                '`open()`, даже если сегодня файл читается правильно. Без '
                'этого аргумента Python берёт **кодировку системы**. На '
                'Windows это не UTF-8, поэтому файл с русским текстом либо '
                'прочитается как набор нечитаемых символов, либо чтение '
                'упадёт с `UnicodeDecodeError`. Это не теоретическая '
                'придирка, а первая ошибка, с которой сталкиваются все, кто '
                'начинает читать файлы: на одном компьютере программа '
                'работает, на другом выдаёт вместо текста мусор.\n\n'
                'Режим отвечает на вопрос, **что программа собирается делать '
                'с файлом**. Режимов три:\n\n'
                '| Режим | Что делает | Файла нет | Файл есть |\n'
                '|---|---|---|---|\n'
                "| `'r'` | чтение, режим по умолчанию | ошибка "
                '`FileNotFoundError` | читает с начала |\n'
                "| `'w'` | запись | создаст | **сотрёт содержимое сразу при "
                'открытии** |\n'
                "| `'a'` | дописывание в конец | создаст | оставит "
                'содержимое, добавит в конец |\n\n'
                "**Режим `'w'` стирает содержимое сразу при открытии – ещё "
                'до первой записи.** Не тогда, когда программа что-то '
                'запишет, а в тот момент, когда `open()` вернул объект '
                'файла.\n\n'
                "Режим `'r'` в записи обычно опускают: он и так по "
                'умолчанию. Но именно он объясняет, почему чтение '
                'несуществующего файла падает: читать нечего, и '
                '`FileNotFoundError` – честный ответ.'
            )),
            dict(order=4, block_type='text', title='`with`: файл закрывается сам', content=(
                'Открытый файл – ресурс, который система отдаёт программе на '
                'время. Взял – верни. Дело не в аккуратности: `write()` не '
                'пишет на диск сразу, а складывает данные в буфер, и в файл их '
                'переносит закрытие.\n\n'
                'Отсюда ловушка, на которую натыкаются в первой же задаче с '
                'файлами: программа записала строки, тут же открыла тот же '
                'файл на чтение – и прочитала пустоту. Данные всё ещё в '
                'буфере, до файла они не дошли:\n\n'
                '```python\n'
                "f = open('lines.txt', 'w', encoding='utf-8')\n"
                "f.write('первая\\n')\n"
                "print(open('lines.txt', encoding='utf-8').read())   # пусто!\n"
                '```\n\n'
                'Ради честности: если программа доработает до конца и '
                'завершится нормально, Python закроет забытый файл сам, и '
                'строки в него всё-таки попадут. Но рассчитывать на это '
                'нельзя – программа, оборванная аварийно, теряет буфер молча, '
                'а прочитать свой же файл раньше времени, как выше, можно и в '
                'совершенно исправной программе.\n\n'
                'У файла, открытого **на чтение**, терять нечего, но и он '
                'остаётся занятым: пока программа его держит, на Windows такой '
                'файл нельзя удалить или переименовать, а несколько тысяч '
                'незакрытых файлов упрутся в лимит системы.\n\n'
                '> **`with open(путь, режим, encoding=\'utf-8\') as f:`** – '
                'открывает файл и **закрывает его сам**, когда блок '
                'кончился.\n\n'
                '«Сам» здесь значит буквально сам: закрытие произойдёт и при '
                'обычном выходе из блока, и если внутри случилась ошибка – '
                '`with` закроет файл раньше, чем ошибка полетит дальше. '
                'Разница видна рядом:\n\n'
                '```python\n'
                '# закрывать руками: до строки f.close() файл открыт,\n'
                '# а если посередине случится ошибка – не закроется вовсе\n'
                "f = open('numbers.txt', encoding='utf-8')\n"
                'text = f.read()\n'
                'f.close()\n'
                '\n'
                '# закрытие устроено языком, а не программистом\n'
                "with open('numbers.txt', encoding='utf-8') as f:\n"
                '    text = f.read()\n'
                '```\n\n'
                'Без `with` пришлось бы звать `f.close()` руками – и следить '
                'за тем, чтобы он вызвался на всех путях, включая путь с '
                'ошибкой. `with` снимает эту заботу целиком, поэтому в нём '
                'открывают почти все файлы: лишней работы он не делает, а '
                'забыть закрыть файл просто не даёт.'
            )),
            dict(order=5, block_type='code', title='', code_language='python', content=(
                '# в файле numbers.txt записаны три строки:\n'
                '#   12\n'
                '#   7\n'
                '#   100\n'
                '\n'
                "with open('numbers.txt', encoding='utf-8') as f:\n"
                '    text = f.read()        # весь файл одной строкой\n'
                '\n'
                'print(text)\n'
                '# 12\n'
                '# 7\n'
                '# 100\n'
                '# print() печатает строку как она есть, вместе со всеми\n'
                '# переводами строк – поэтому каждая строка встала на своё\n'
                '# место, хотя в переменной лежит одна длинная строка\n'
            )),
            dict(order=6, block_type='text', title='Три способа прочитать', content=(
                'Читают файл по-разному, и разница не в удобстве, а в том, '
                'что окажется в переменной и сколько памяти это займёт.\n\n'
                '| Способ | Что возвращает | Когда брать |\n'
                '|---|---|---|\n'
                '| `f.read()` | весь файл одной строкой, вместе со всеми '
                '`\\n` внутри | файл небольшой и нужен целиком |\n'
                '| `f.readline()` | одну строку, вместе с `\\n` в конце | '
                'строки разбирают по одной и строго по порядку |\n'
                '| `for line in f:` | ничего: строку за строкой отдаёт цикл | '
                '**обычный случай** – файл любого размера, в памяти живёт '
                'одна строка |\n'
                '| `f.readlines()` | список всех строк сразу | нужен доступ к '
                'строкам по номеру (что такое список – блок 9) |\n\n'
                'Способов, если считать строго, три с половиной: '
                '`readlines()` – это весь файл, разложенный в список строк. '
                'Работа та же, что у `read()`, и память та же; отличается '
                'только вид результата.\n\n'
                'Почему цикл называют обычным случаем. `read()` держит в '
                'памяти **весь** файл сразу, а `for line in f` – одну строку '
                'за раз. Файл на сто тысяч строк `read()` прочитает только '
                'на машине с достаточной памятью, а цикл – на любой: он не '
                'хранит прочитанное, а обрабатывает и забывает.\n\n'
                'И деталь, из-за которой примеры ниже открывают файл заново. '
                'Объект файла **помнит, где остановился**: после `read()` '
                'следующий `read()` вернёт пустую строку, а после '
                '`readline()` следующий вернёт уже вторую строку. Файл не '
                'перематывается к началу сам, поэтому второй проход '
                'начинают новым `open()`.'
            )),
            dict(order=7, block_type='code', title='', code_language='python', content=(
                '# numbers.txt: 12, 7, 100 – три строки, каждая с \\n на конце\n'
                '\n'
                '# 1. весь файл одной строкой\n'
                "with open('numbers.txt', encoding='utf-8') as f:\n"
                '    text = f.read()\n'
                "print(text.count('\\n'))   # 3 – столько в файле переводов строки\n"
                'print(text)                # 12 / 7 / 100 – три строки на экране\n'
                '\n'
                '# 2. по одной строке вручную\n'
                "with open('numbers.txt', encoding='utf-8') as f:\n"
                "    line1 = f.readline()   # '12\\n' – перевод строки внутри\n"
                "    line2 = f.readline()   # '7\\n'\n"
                "    line3 = f.readline()   # '100\\n'\n"
                "    line4 = f.readline()   # '' – пустая строка: файл кончился\n"
                'print(line1 + line2 + line3)   # 12 / 7 / 100\n'
                '\n'
                '# 3. циклом – обычный случай\n'
                "with open('numbers.txt', encoding='utf-8') as f:\n"
                '    for line in f:\n'
                "        print(line, end='')    # end='' не добавляет свой перевод\n"
                '\n'
                '# 3 с половиной: весь файл списком строк\n'
                "with open('numbers.txt', encoding='utf-8') as f:\n"
                '    lines = f.readlines()\n'
                "print(lines)               # ['12\\n', '7\\n', '100\\n']\n"
                'print(len(lines))          # 3 – столько строк в файле'
            )),
            dict(order=8, block_type='text', title='Ловушка: `\\n` в конце каждой строки', content=(
                '> **`\\n`** – служебный символ «перевод строки». Он и '
                'разделяет строки в файле: всё, что стоит до него, – одна '
                'строка, всё, что после, – следующая. В коде он записывается '
                'двумя знаками, а сам занимает один символ.\n\n'
                'Читая файл построчно, программист смотрит на строку глазами '
                'и никакого `\\n` не видит – его в файле и не видно. А '
                'программа видит: каждая прочитанная строка приходит '
                '**вместе с переводом строки на конце** (кроме, возможно, '
                'самой последней – её в файле могло и не быть).\n\n'
                'Лечится это снятием перевода строки:\n\n'
                '- `line.strip()` – убирает пробельные символы **с обоих '
                'концов**, и не только `\\n`: пробелы и табуляцию тоже (урок '
                '8.2);\n'
                '- `line.rstrip(\'\\n\')` – убирает **только перевод строки** '
                'и **только справа**: пробелы по краям остаются, а если '
                '`\\n` нет, строка не меняется.\n\n'
                'Разница между ними ровно одна: `strip()` чистит шире, '
                '`rstrip(\'\\n\')` – строго то, что просили.'
            )),
            dict(order=9, block_type='code', title='', code_language='python', content=(
                '# numbers.txt: 12, 7, 100 – по одному числу в строке\n'
                '\n'
                'total = 0\n'
                "with open('numbers.txt', encoding='utf-8') as f:\n"
                '    for line in f:\n'
                '        line = line.strip()        # снимаем перевод строки\n'
                '        total = total + int(line)\n'
                '\n'
                'print(total)                       # 119\n'
            )),
            dict(
                order=10, block_type='widget',
                title='Как читается файл и растёт сумма',
                content=(
                    'Перед вами тот же подсчёт суммы, разложенный по шагам. '
                    'Следите за строкой: из файла она приходит не такой, '
                    'какой записана в файле, – на конце сидит перевод '
                    'строки, и видно это ровно на одном шаге. Про следующий '
                    'шаг переменная уже чистая, а накопитель растёт на '
                    'третьем шаге каждой строки. И посчитайте, сколько раз '
                    'повторится тело цикла: файл кончается сам, никакого '
                    'счётчика строк в программе нет.'
                ),
                widget_key='loop-trace',
                widget_config={
                    'code': FILE_SUM_CODE,
                    'vars': ['line', 'total'],
                    'steps': _file_sum_trace(),
                },
            ),
            dict(order=11, block_type='text', title='Запись в файл', content=(
                'Чтение – половина работы. Вторая – сохранить полученное.\n\n'
                'Записывает строку в файл метод `write()`:\n\n'
                '```python\n'
                "with open('result.txt', 'w', encoding='utf-8') as f:\n"
                "    f.write('сумма: ')\n"
                '    f.write(str(119))\n'
                '```\n\n'
                '- **`write()` не добавляет перевод строки.** Записал строку '
                '– она легла вплотную к предыдущей. Нужна новая строка – '
                'поставьте `\\n` сами: `f.write(s + \'\\n\')`. Без этого две '
                'записи подряд дадут одну длинную строку.\n'
                '- **`write()` ждёт строку.** Число перед записью переводят в '
                'строку: `f.write(str(119))`, `f.write(\'сумма: \' + '
                'str(total))`. Вызов `f.write(119)` падает с `TypeError`: '
                'метод не догадывается, что число нужно превратить в текст.\n'
                '- **`write()` возвращает число записанных символов** – '
                'сколько символов легло в файл. Чаще всего возвращённое '
                'значение просто не смотрят, но иногда оно нужно: по нему '
                'видно, сколько ушло из строки.\n'
                '- Есть и второй способ печати в файл – `print(..., file=f)`: '
                'он переводит значения в строку сам и **добавляет перевод '
                'строки**, как обычный `print()` на экране. Файл при этом '
                'обязан быть открыт на запись: в файл, открытый на чтение, и '
                '`print(..., file=f)`, и `write()` падают с '
                '`io.UnsupportedOperation: not writable`.\n\n'
                "Режим `'w'` при этом работает как сказано выше: файл открыт "
                'на запись – старое содержимое стёрто ещё до первой строки. '
                'Если нужен не новый файл, а продолжение старого, режим '
                'другой.'
            )),
            dict(order=12, block_type='code', title='', code_language='python', content=(
                'total = 12 + 7 + 100\n'
                '\n'
                "with open('result.txt', 'w', encoding='utf-8') as f:\n"
                "    n = f.write('сумма: ' + str(total) + '\\n')\n"
                "    f.write('проверено\\n')\n"
                '\n'
                'print(n)        # 11 – столько символов записала первая строка:\n'
                '#                 7 букв, 3 цифры и один перевод строки\n'
                '\n'
                '# в result.txt теперь две строки:\n'
                '#   сумма: 119\n'
                '#   проверено\n'
                '#\n'
                "# каждый запуск начинается с пустого файла: режим 'w' стёр\n"
                '# прошлый результат'
            )),
            dict(order=13, block_type='text', title='Режим `\'a\'`: дописать, а не затереть', content=(
                'Режим `\'w\'` стирает содержимое файла – это удобно, когда '
                'отчёт пишут заново, и губительно, когда записи копят. Для '
                'второго случая есть режим `\'a\'` – от английского append, '
                '«дописать».\n\n'
                '> В режиме `\'a\'` запись идёт **в конец файла**: старое '
                'содержимое остаётся на месте, а новое добавляется после '
                'него.\n\n'
                'Файла нет – `\'a\'` его создаст, как и `\'w\'`. Файл есть – '
                '`\'a\'` не тронет в нём ни символа и допишет новое в конец.\n\n'
                'Так делают **журналы** – файлы, которые растут от запуска к '
                'запуску: программа работает раз в день и дописывает строку '
                'с результатом, а за месяц в файле набирается тридцать строк, '
                'и все на месте. В режиме `\'w\'` после каждого запуска в '
                'файле оставалась бы ровно одна строка – последняя.\n\n'
                'Разницу стоит проговорить: `\'w\'` отвечает на вопрос «что '
                'должно быть в файле», `\'a\'` – «что к нему добавить». '
                'Первый режим заменяет содержимое, второй накапливает.'
            )),
            dict(order=14, block_type='code', title='', code_language='python', content=(
                '# журнал: каждый запуск дописывает свою строку\n'
                '\n'
                'total = 12 + 7 + 100\n'
                '\n'
                "with open('journal.txt', 'a', encoding='utf-8') as f:\n"
                "    f.write('сумма: ' + str(total) + '\\n')\n"
                '\n'
                '# перечитываем файл целиком\n'
                "with open('journal.txt', encoding='utf-8') as f:\n"
                '    print(f.read())\n'
                '\n'
                '# первый запуск программы печатает одну строку:\n'
                '#   сумма: 119\n'
                '# второй – уже две, третий – три\n'
                "# режим 'w' оставил бы в файле только последнюю"
            )),
            dict(order=15, block_type='text', title='Где лежит файл', content=(
                'Короткое имя `data.txt` означает не «где-то на диске», а '
                '**файл в рабочей папке программы** – той, из которой '
                'программу запустили. Полный путь называют целиком: '
                '`C:\\Учёба\\data.txt`. Это может быть один и тот же файл – '
                'разница только в том, откуда программа его ищет.\n\n'
                'Отсюда и самая частая причина `FileNotFoundError`: файл на '
                'диске есть, а программа ищет его не там. Что проверить, '
                'если чтение упало:\n\n'
                '1. **Лежит ли файл рядом с программой** – то есть в той же '
                'папке, из которой она запущена.\n'
                '2. **Совпадает ли имя** – до последнего символа. Windows по '
                'умолчанию прячет расширения, и файл `data.txt` в проводнике '
                'выглядит как `data`; созданный в блокноте документ легко '
                'превращается в `data.txt.txt`.\n'
                '3. **Не открыт ли файл другой программой** – это уже не про '
                '`FileNotFoundError`, а про доступ, но проверяют это там же.\n\n'
                'И полезная деталь о самих режимах: `FileNotFoundError` '
                'приходит в основном от чтения – режимы `\'w\'` и `\'a\'` '
                'отсутствующий файл не ищут, а создают. Поэтому опечатка в '
                'имени файла при записи не падает, а тихо заводит новый файл '
                'с неправильным именем, в то время как нужные данные лежат '
                'себе нетронутыми. Это ошибка, которую замечают не сразу.'
            )),
            dict(order=16, block_type='text', title='Файл как вход задачи', content=(
                'Данные переживают запуск программы – это первое, зачем нужен '
                'файл. Второе: вход задачи может быть больше того, что '
                'реально ввести руками. Тысячу чисел ещё наберёшь, сто тысяч '
                'строк – уже никак.\n\n'
                'Поэтому в задачах с файлом условие обычно звучит так: «дан '
                'текстовый файл, найдите…». Программу это не меняет: сначала '
                'файл читают целиком одной строкой, а дальше работают с ним '
                'теми же приёмами, что и с любой другой строкой.\n\n'
                '```python\n'
                "with open('input.txt', encoding='utf-8') as f:\n"
                '    s = f.read()\n'
                '\n'
                'print(len(s))          # сколько всего символов\n'
                'print(s[0], s[-1])     # первый и последний – индексы из урока 8.1\n'
                "print(s.count('X'))    # сколько раз встретилась буква\n"
                '```\n\n'
                'Всё остальное – из уроков 8.1–8.3: `len(s)` даёт длину, '
                '`s[i]` – символ по индексу, срез – кусок строки, `for c in '
                's` – проход по символам, а `find()`, `count()`, `split()` и '
                '`strip()` работают с прочитанным точно так же, как с любой '
                'строкой в переменной. Именно так устроены задачи, где на '
                'вход дают текстовый файл на сотни тысяч символов: `read()` '
                'приносит содержимое, а дальше начинается обычная работа со '
                'строкой.\n\n'
                'Одна оговорка о размере. `read()` держит в памяти **весь '
                'файл** сразу: миллион символов – это 1–2 Мбайт, и это '
                'нормально, а вот гигабайтный файл так читать не стоит. Если '
                'данные в файле построчные и нужна только сумма или счётчик, '
                'читают циклом `for line in f` – тогда в памяти живёт одна '
                'строка за раз, сколько бы их ни было в файле.'
            )),
            dict(order=17, block_type='text', title='Шпаргалка', content=(
                '| Что | Что делает |\n'
                '|---|---|\n'
                "| `open(путь, \'r\', encoding=\'utf-8\')` | открывает файл на "
                'чтение; режим по умолчанию, его обычно не пишут |\n'
                "| `open(путь, \'w\', encoding=\'utf-8\')` | открывает на "
                'запись: файла нет – создаст, файл есть – сотрёт содержимое '
                'сразу при открытии |\n'
                "| `open(путь, \'a\', encoding=\'utf-8\')` | открывает на "
                'дописывание: файла нет – создаст, файл есть – оставит '
                'содержимое и допишет в конец |\n'
                "| `with open(...) as f:` | закрывает файл сам в конце блока, "
                'даже если внутри случилась ошибка |\n'
                '| `f.read()` | весь файл одной строкой, вместе с `\\n` '
                'внутри |\n'
                '| `f.readline()` | одну строку, вместе с `\\n` на конце |\n'
                '| `f.readlines()` | список всех строк (что это – блок 9) |\n'
                '| `for line in f:` | по строке за раз; годится для файла '
                'любого размера |\n'
                '| `f.write(s)` | записывает строку с текущей позиции, '
                'перевода строки не добавляет, возвращает число записанных '
                'символов |\n'
                '| `print(..., file=f)` | печатает в файл, переводя значения в '
                'строку и добавляя `\\n` |\n'
                '| `f.close()` | закрывает файл; при `with` не нужен |'
            )),
            dict(order=18, block_type='text', title='Коротко', content=(
                '- **Файл** – данные на диске, у которых есть имя. Они '
                'переживают запуск программы, поэтому в файл кладут то, что '
                'должно остаться, и то, что слишком велико для ввода с '
                'клавиатуры.\n'
                '- Открывают файл функцией `open(путь, режим, '
                "encoding='utf-8')`, и **`encoding='utf-8'` указывают "
                'всегда**: без него Python берёт кодировку системы, а на '
                'Windows это не UTF-8 – русский текст превращается в мусор '
                'или падает с `UnicodeDecodeError`.\n'
                "- Режимы: `'r'` – чтение (по умолчанию, файла нет – "
                '`FileNotFoundError`), `\'w\'` – запись (создаёт и **стирает '
                'содержимое сразу при открытии**), `\'a\'` – дописывание в '
                'конец.\n'
                '- `with open(...) as f:` закрывает файл сам – и при '
                'нормальном выходе, и после ошибки. Пока файл не закрыт, '
                'записанное лежит в буфере: программа, открывшая тот же файл '
                'на чтение раньше времени, увидит пустоту.\n'
                '- Каждая прочитанная строка приходит с `\\n` на конце, кроме '
                'возможно последней. Поэтому `int(line)` работает, а '
                '`line == \'да\'` – нет: перед сравнением строку чистят '
                '`strip()` или `rstrip(\'\\n\')`.\n'
                '- `f.write()` пишет строку и **не** добавляет перевод строки '
                '(его ставят сами), число перед записью переводят через '
                '`str()`, а возвращает `write()` число записанных символов.'
            )),
        ])

        quiz = _self_check(
            slug='self-check-fayly-chtenie-i-zapis',
            title='Самопроверка: чтение и запись файлов',
            description='Пять вопросов по теме урока.',
            questions=[
                dict(
                    type='choice',
                    text=(
                        'В файле `data.txt` до запуска лежала одна строка: '
                        '`пока`. Что напечатает программа?\n\n'
                        '```python\n'
                        "with open('data.txt', 'w', encoding='utf-8') as f:\n"
                        "    f.write('привет')\n"
                        '\n'
                        "with open('data.txt', encoding='utf-8') as f:\n"
                        '    print(f.read())\n'
                        '```'
                    ),
                    choices=[
                        ('`привет` – открытие в режиме `\'w\'` стёрло прежнее '
                         'содержимое ещё до первой записи', True),
                        ('Две строки: сначала `пока`, потом `привет`', False),
                        ('Одну строку `покапривет` – запись идёт в конец, а '
                         'перевод строки `write()` не добавляет', False),
                        ('`пока` – режим `\'w\'` открывает файл на запись, но '
                         'содержимое не трогает', False),
                    ],
                ),
                dict(
                    type='choice',
                    text=(
                        'В файле `answer.txt` записана одна строка: `да`, в '
                        'конце – перевод строки. Что напечатает программа?\n\n'
                        '```python\n'
                        "answer = 'да'\n"
                        '\n'
                        "with open('answer.txt', encoding='utf-8') as f:\n"
                        '    line = f.readline()\n'
                        '\n'
                        'print(line == answer)\n'
                        '```'
                    ),
                    choices=[
                        ('`False`: `readline()` вернула `\'да\\n\'`, а перевод '
                         'строки – такой же символ, как и остальные', True),
                        ('`True`: `readline()` возвращает строку без перевода '
                         'строки на конце', False),
                        ('`False`, потому что `readline()` читает не строку '
                         'целиком, а один символ', False),
                        ('Ошибка `TypeError`: сравнивать прочитанную строку с '
                         'обычной строкой нельзя', False),
                    ],
                ),
                dict(
                    type='choice',
                    text=(
                        'Что произойдёт, если при открытии файла с русским '
                        'текстом не указать `encoding=\'utf-8\'`?'
                    ),
                    choices=[
                        ('Python возьмёт кодировку системы; на Windows это не '
                         'UTF-8, поэтому текст либо прочитается как набор '
                         'нечитаемых символов, либо чтение упадёт с '
                         '`UnicodeDecodeError`', True),
                        ('Программа не запустится: `encoding` – обязательный '
                         'аргумент `open()`', False),
                        ('Python определит кодировку по содержимому файла и '
                         'прочитает его правильно', False),
                        ('Ничего не изменится: UTF-8 – кодировка по умолчанию '
                         'на любой системе', False),
                    ],
                ),
                dict(
                    type='choice',
                    text=(
                        'Программа записала строки в файл и тут же, не закрыв '
                        'его, открыла тот же файл на чтение – и прочитала '
                        'пустоту. Почему?'
                    ),
                    choices=[
                        ('Записанное ещё лежит в буфере: в файл его переносит '
                         'закрытие, а второе открытие видит на диске то, что '
                         'туда успело дойти', True),
                        ('Режим `\'w\'` стирает содержимое при каждом '
                         'открытии, поэтому второе открытие стёрло только что '
                         'записанное', False),
                        ('Один и тот же файл нельзя открыть дважды в одной '
                         'программе – второй `open()` возвращает пустую '
                         'заглушку', False),
                        ('`write()` не записывает строки короче буфера, для '
                         'них есть отдельный метод `writelines()`', False),
                    ],
                ),
                dict(
                    type='text',
                    text=(
                        'Файл открыт на запись. Что напечатает программа?\n\n'
                        '```python\n'
                        "with open('data.txt', 'w', encoding='utf-8') as f:\n"
                        "    print(f.write('привет'))\n"
                        '```\n\n'
                    ),
                    correct_text_answer='6',
                ),
            ],
        )
        ArticleQuiz.objects.get_or_create(
            article=article, quiz=quiz,
            defaults={'label': 'Проверь себя', 'order': 1},
        )

    def seed_8_5(self):
        article = Article.objects.get(slug='8-5-moduli-i-biblioteki-import')
        article.description = (
            'Модуль – файл с готовым кодом, библиотека – набор модулей. Три '
            'формы записи import и разница между ними; почему не пишут '
            '`from math import *`; что лежит в стандартной библиотеке и чем '
            'от неё отличаются сторонние библиотеки; pip install; '
            'ModuleNotFoundError и ловушка со своим файлом, имя которого '
            'совпало с именем модуля.'
        )
        article.save(update_fields=['description'])

        _replace_blocks(article, [
            dict(order=1, block_type='text', title='О чём этот урок', content=(
                'Программа считает площадь круга – и упирается в квадратный '
                'корень. Написать его самим? Алгоритм извлечения корня '
                'придуман задолго до нас: его написали один раз, проверили на '
                'миллионах примеров и положили в Python. Осталось только '
                'попросить.\n\n'
                'Так же со случайным числом: жребий, кубик в игре, выбор '
                'варианта – это тоже кто-то уже написал. Так же с '
                'сегодняшней датой: её умеет выдавать сама машина, и нужен '
                'лишь правильный вопрос.\n\n'
                'Ни одну из этих вещей не пишут заново. Все они лежат рядом '
                '– в файлах, которые идут в комплекте с Python, – а '
                'подключить их к своей программе умеет одна строка. Именно '
                'поэтому программа на Python из десяти строк делает то, на '
                'что в другом языке ушли бы сотни.\n\n'
                '**В этом уроке:** что такое модуль и библиотека и чем от них '
                'отличается стандартная библиотека; три формы записи '
                '`import` и разница между ними; почему не пишут `from math '
                'import *`; какие модули уже под рукой, а какие приходится '
                'ставить командой `pip install`; что означает '
                '`ModuleNotFoundError`; главная ловушка – свой файл, '
                'названный именем модуля и незаметно подменивший собой '
                'стандартный.'
            )),
            dict(order=2, block_type='text', title='Модуль, пакет, библиотека', content=(
                'До сих пор вся программа жила в одном файле. Но код, который '
                'нужен второй и третий раз, выносят в отдельный файл – и '
                'подключают его к новому.\n\n'
                '> **Модуль** – файл с кодом на Python, готовый к '
                'подключению: в нём лежат функции и значения, которыми можно '
                'пользоваться из другой программы.\n\n'
                '> **Библиотека** – набор модулей, собранных вместе по одной '
                'теме: математика – в одном наборе, работа с датами – в '
                'другом.\n\n'
                '> **Стандартная библиотека** – модули, которые идут в '
                'комплекте с Python. Их не нужно нигде брать и ставить: они '
                'уже лежат на компьютере рядом с самим языком.\n\n'
                '> **Сторонняя библиотека** – модули, которые написали другие '
                'люди и выложили отдельно. Её скачивают и устанавливают '
                'сами.\n\n'
                'Слово «пакет» значит примерно то же, что «библиотека»: '
                'несколько модулей вместе. В Python у него есть и более '
                'точное значение, но для нас пока важно одно: **модуль – это '
                'файл, а библиотека – это много файлов.**\n\n'
                'Верно и обратное: наша собственная программа – обычный файл '
                'с кодом, то есть тоже модуль. Написанное сегодня можно '
                'завтра подключить к другому файлу – ровно так же, как '
                'подключают `math`.'
            )),
            dict(order=3, block_type='text', title='Три формы импорта', content=(
                'Подключает модуль слово `import` – «импортировать», то есть '
                'ввезти. Записать это можно тремя способами, и отличаются '
                'они не смыслом, а тем, как потом выглядит обращение.\n\n'
                '| Запись | Как потом обращаться | Когда так пишут |\n'
                '|---|---|---|\n'
                '| `import math` | `math.sqrt(16)` – через имя модуля и '
                'точку | когда из модуля нужно много всего или когда важно, '
                'чтобы в каждой строке было видно, откуда взялась функция |\n'
                '| `from math import sqrt` | `sqrt(16)` – сразу по имени | '
                'когда из модуля нужна одна-две функции и имя модуля в '
                'строке только мешает |\n'
                '| `import math as m` | `m.sqrt(16)` – по короткому имени | '
                'когда имя модуля длинное и встречается в программе '
                'постоянно |\n\n'
                'Каждая запись читается как фраза: `import math` – '
                '«импортировать math»; `from math import sqrt` – «из math '
                'импортировать sqrt»; `import math as m` – «импортировать '
                'math как m».\n\n'
                'Во второй форме можно перечислить сразу несколько имён через '
                'запятую: `from math import sqrt, pi`. Ввозится при этом '
                'ровно то, что назвали, – ни больше ни меньше.\n\n'
                'Короткое имя через `as` – та же первая форма, только '
                'подписанная другим словом. Библиотека числовых массивов '
                '`numpy` (блок 19) в каждой строке превращается в `np`: '
                'ввозим тот же модуль, а пишем короче. Экономия тут не '
                'главное – `as` ставят там, где имя модуля длинное, и весь '
                'мир читает `np` как «numpy».\n\n'
                'Разница во второй колонке – это не мелочь оформления, а '
                'подсказка читателю. `math.sqrt(x)` говорит: «это чужая '
                'функция, она из модуля math». Запись `sqrt(x)` говорит '
                'только «это sqrt»: своя она или чужая – из строки не видно, '
                'и искать её приходится по всему файлу.'
            )),
            dict(order=4, block_type='code', title='', code_language='python', content=(
                '# 1. import модуль – обращение через имя модуля\n'
                'import math\n'
                '\n'
                'print(math.sqrt(16))     # 4.0 – корень из 16\n'
                'print(math.floor(3.7))   # 3 – округление вниз\n'
                'print(math.pi)           # 3.141592653589793 – число пи\n'
                '# в каждой строке видно, откуда взялась функция\n'
                '\n'
                '# 2. from модуль import имя – обращение сразу по имени\n'
                'from math import sqrt, pi\n'
                '\n'
                'print(sqrt(144))         # 12.0\n'
                'print(pi)                # 3.141592653589793\n'
                '# короче – но по записи sqrt(144) уже не сказать,\n'
                '# своя это функция или чужая\n'
                '\n'
                '# 3. import модуль as короткое_имя – та же первая форма,\n'
                '#    только имя короче\n'
                'import math as m\n'
                '\n'
                'print(m.sqrt(144))       # 12.0\n'
                'print(m.pi)              # 3.141592653589793'
            )),
            dict(order=5, block_type='text', title='Почему не пишут `from math import *`', content=(
                'У `import` есть четвёртая форма, о которой надо знать ровно '
                'для того, чтобы её не писать:\n\n'
                '```python\n'
                'from math import *\n'
                '```\n\n'
                'Звёздочка значит «всё, что есть в модуле». Python при этом '
                'не выдаст ни ошибки, ни предупреждения – программа, скорее '
                'всего, заработает. Плохо здесь не для машины, а для '
                'человека.\n\n'
                '**Имена сваливаются в общую кучу.** В `math` их десятки, и '
                'после такой строки в программе разом появляются `sqrt`, '
                '`floor`, `pi`, `e`, `sin`, `log` и ещё два десятка имён. '
                'Какое из них что делает – видно только по документации.\n\n'
                '**Они незаметно перекрывают друг друга.** Если два модуля '
                'объявили имя с одинаковым названием – а такое случается, – '
                'победит тот, что был импортирован последним. Программа не '
                'упадёт: она начнёт считать не то.\n\n'
                '**Читатель не может понять, откуда имя.** Увидев '
                '`sqrt(16)`, он не знает, своя это функция, из `math` или из '
                'другого модуля: больше такого имени в тексте программы '
                'нигде нет.\n\n'
                'Поэтому имена перечисляют явно:\n\n'
                '```python\n'
                'from math import sqrt, floor, pi\n'
                '```\n\n'
                'Строка длиннее – зато видно и что ввезли, и откуда. Это как '
                'список покупок: лучше перечислить, чем написать «всё из '
                'магазина».'
            )),
            dict(order=6, block_type='text', title='Стандартная библиотека', content=(
                'Вот модули, с которыми придётся встречаться чаще всего. Все '
                'они уже стоят на компьютере вместе с Python – ни скачивать, '
                'ни устанавливать ничего не надо.\n\n'
                '| Модуль | Что в нём | Пример вызова |\n'
                '|---|---|---|\n'
                '| `math` | математика: корни, степени, тригонометрия, '
                'константы | `math.sqrt(16)` |\n'
                '| `random` | случайные числа и случайный выбор | '
                '`random.randint(1, 6)` |\n'
                '| `datetime` | даты и время: сегодняшний день, разница между '
                'датами | `date.today()` |\n'
                "| `re` | поиск по образцу – регулярные выражения | "
                "`re.search(r'\\d+', s)` |\n"
                '| `os` | файлы и папки: список файлов, путь, переименование '
                '| `os.listdir(\'.\')` |\n'
                '| `sys` | сама программа: аргументы запуска, версия Python, '
                'выход | `sys.exit()` |\n'
                '| `time` | время: пауза в работе, секунды, замер скорости | '
                '`time.sleep(1)` |\n\n'
                '`re` стоит в таблице не для полноты: это модуль регулярных '
                'выражений, и весь следующий урок – про него.\n\n'
                'Стандартная библиотека – не короткий список, а сотни '
                'модулей: есть работа с текстом, с числами, с файлами, с '
                'датами, с архивами, с сетевыми протоколами. Про Python за '
                'это говорят «батарейки в комплекте» – то, что в других '
                'языках ищут и ставят отдельно, здесь уже лежит под рукой. '
                'Полный список – в документации, docs.python.org.'
            )),
            dict(order=7, block_type='code', title='', code_language='python', content=(
                'import random\n'
                'from datetime import date\n'
                '\n'
                '# случайное число и случайный выбор\n'
                'print(random.randint(1, 6))                # 4 – например\n'
                "print(random.choice(['орёл', 'решка']))    # решка – например\n"
                '\n'
                '# сегодняшняя дата и та же дата, записанная по-человечески\n'
                'print(date.today())                        # год-месяц-день\n'
                "print(date.today().strftime('%d.%m.%Y'))   # день.месяц.год\n"
                '# у даты есть готовый способ напечатать себя в любом виде'
            )),
            dict(order=8, block_type='text', title='Сторонние библиотеки и `pip`', content=(
                'В стандартной библиотеке есть многое – но не всё. Попросить '
                'страницу из интернета, посчитать таблицу чисел, нарисовать '
                'график – этого там нет: такие задачи решают отдельные '
                'библиотеки, которые пишут и поддерживают другие люди.\n\n'
                '> **`pip`** – установщик пакетов Python: программа, которая '
                'скачивает библиотеку из интернета и раскладывает её так, '
                'чтобы `import` её нашёл.\n\n'
                'Ставится сторонняя библиотека командой в терминале:\n\n'
                '```\n'
                'pip install requests\n'
                '```\n\n'
                'Читается буквально: «pip, установи requests». Делается это '
                '**один раз** на компьютере – и всё, дальше библиотека '
                'доступна любой программе, как будто всегда там была.\n\n'
                'Важно не перепутать: `pip install` – **команда терминала, а '
                'не код Python**. Внутри программы такая строка '
                'бессмысленна: Python попытается увидеть в ней вызов функции '
                '`pip` и остановится с `NameError`.\n\n'
                'А теперь о том, что бывает, когда библиотеки нет. Попытка '
                'импортировать то, чего на компьютере не лежит, '
                'останавливает программу первой же строкой:\n\n'
                '```\n'
                "ModuleNotFoundError: No module named 'requests'\n"
                '```\n\n'
                'Читается дословно: «модуль не найден – модуля с именем '
                'requests нет». Причин ровно две, и проверяют их по '
                'очереди:\n\n'
                '1. **Опечатка в имени.** Имя модуля пишут точно: '
                '`requests`, а не `request` и не `requsts`. Одна пропущенная '
                'буква – и модуль «не найден», хотя всё остальное в '
                'программе верно.\n'
                '2. **Библиотека не установлена.** Тогда её ставят: '
                '`pip install requests` – и запускают программу заново.\n\n'
                'Ошибка при этом честная: Python действительно искал модуль и '
                'не нашёл. И её стоит отличать от соседней: если опечатка не '
                'в имени модуля, а в самом слове `import` (например, '
                '`improt math`), сообщение будет совсем другим – '
                '`SyntaxError`, «не понимаю такую запись». '
                '`ModuleNotFoundError` – это всегда «запись понятна, а модуля '
                'нет».'
            )),
            dict(order=9, block_type='text', title='Ловушка: свой файл с именем модуля', content=(
                'Теперь ловушка, в которую попадают почти все – и почти никто '
                'не понимает с первого раза. Программу про случайные числа '
                'сохранили под именем `random.py` – и она перестала работать. '
                'Тот же файл, переименованный в `task.py`, работает снова. '
                'Что произошло?\n\n'
                '> **Модуль ищут по списку папок, и папка программы стоит в '
                'нём раньше стандартной библиотеки.**\n\n'
                'Когда программа пишет `import random`, Python не бросается '
                'сразу в стандартную библиотеку. Он смотрит по очереди: '
                'сначала папку, из которой запущена программа, потом папки, '
                'добавленные вручную, и только потом – модули, идущие с '
                'Python. В папке программы лежит `random.py`. Имя совпало – '
                'поиск закончен: под именем `random` в программу попал '
                '**ваш файл**, а настоящий модуль со случайными числами до '
                'дела не дошёл.\n\n'
                'Дальше всё зависит от того, что в вашем файле. Чаще всего '
                'он пустой или почти пустой, и первая же строка с делом '
                'падает:\n\n'
                '```\n'
                "AttributeError: module 'random' has no attribute 'randint'\n"
                '```\n\n'
                'Читается это сообщение обманчиво: «в модуле random нет '
                'randint». Можно пойти в документацию, убедиться, что '
                '`randint` там есть, и решить, что ошибка врёт. А врёт не '
                'ошибка – под именем `random` подключён не тот файл.\n\n'
                'Точно так же ломает жизнь любой свой файл, чьё имя совпало с '
                'именем модуля: `re.py`, `math.py`, `datetime.py`, `os.py`. '
                'Особенно обидно с `re.py`: программа работает, пока в ней '
                'нет регулярных выражений, а потом падает.\n\n'
                'Что делать:\n\n'
                '- **Не называть свои файлы именами модулей.** Имя файла '
                'программы должно говорить о задаче: `task.py`, `perevod.py`, '
                '`dnevnik.py`.\n'
                '- **Посмотреть, откуда пришёл модуль.** Одна строка отвечает '
                'на вопрос целиком:\n\n'
                '```python\n'
                'import random\n'
                'print(random.__file__)\n'
                '# C:\\Python313\\Lib\\random.py – вот это настоящий модуль\n'
                '```\n\n'
                'У каждого модуля есть переменная `__file__` – путь к файлу, '
                'из которого он загружен. Если в выводе стоит путь к вашей '
                'папке, значит под именем `random` найден ваш файл, и его '
                'надо переименовать.'
            )),
            dict(order=10, block_type='text', title='Как узнать, что умеет модуль', content=(
                'Остался практический вопрос: откуда узнают, какие имена есть '
                'в модуле и что они делают. Способов три, и все они под '
                'рукой.\n\n'
                '**Документация.** docs.python.org – официальная документация '
                'Python, у неё есть и русский раздел. В поиске набирают '
                '«python math» – и получают страницу, где перечислена каждая '
                'функция модуля с примером. Это единственный источник, '
                'которому стоит верить целиком: в случайной статье из '
                'интернета пример может быть устаревшим.\n\n'
                '**`help()` – справка прямо в программе:**\n\n'
                '```python\n'
                'import math\n'
                '\n'
                'help(math)        # список имён модуля с описанием каждого\n'
                'help(math.sqrt)   # справка по одной функции\n'
                '```\n\n'
                '`help(math)` печатает длинный текст: сначала описание '
                'модуля, потом имена с первой строкой пояснения к каждому. '
                'Читают его листая, выходят – клавишей `q`.\n\n'
                '**`dir()` – одно оглавление, без пояснений:**\n\n'
                '```python\n'
                'import math\n'
                '\n'
                'print(dir(math))\n'
                "# ['__doc__', '__file__', ..., 'ceil', 'cos', 'e', 'floor', 'pi']\n"
                '```\n\n'
                '`dir(модуль)` возвращает список всех имён в модуле. Имена с '
                'двумя подчёркиваниями по краям – служебные, их пропускают '
                'глазами; остальное – то, чем можно пользоваться. Список '
                'короткий и отвечает на вопрос «есть ли тут вообще нужное», '
                'а как именно вызывать – подскажет `help()` или '
                'документация.\n\n'
                'В среде разработки третий способ находится сам: после имени '
                'модуля достаточно поставить точку, и список имён появится '
                'подсказкой. Но подсказка есть не везде, а `help()` работает '
                'в любом Python.'
            )),
            dict(order=11, block_type='text', title='Шпаргалка', content=(
                '| Что | Что делает |\n'
                '|---|---|\n'
                '| `import модуль` | подключает модуль целиком; обращение '
                'через `модуль.имя` |\n'
                '| `from модуль import имя` | подключает названные имена; '
                'обращение сразу по имени |\n'
                '| `from модуль import имя1, имя2` | то же для нескольких '
                'имён сразу |\n'
                '| `import модуль as короткое` | подключает модуль под другим '
                'именем: `np.sqrt(16)` |\n'
                '| `from модуль import *` | подключает все имена разом – '
                '**так не пишут** |\n'
                '| `pip install пакет` | ставит стороннюю библиотеку; это '
                'команда терминала, а не код Python |\n'
                '| `ModuleNotFoundError` | модуль не найден: опечатка в '
                'имени или библиотека не установлена |\n'
                '| `help(модуль)` | справка по модулю или по одной функции |\n'
                '| `dir(модуль)` | список имён, которые есть в модуле |\n'
                '| `модуль.__file__` | путь к файлу, из которого загружен '
                'модуль: сразу видно, свой он или стандартный |\n\n'
                'Первые пять строк – про запись `import`, остальные – про то, '
                'как разобраться, когда что-то пошло не так.'
            )),
            dict(order=12, block_type='text', title='Коротко', content=(
                '- **Модуль** – файл с готовым кодом, **библиотека** – набор '
                'модулей. Слово `import` подключает их к программе, чтобы не '
                'писать заново то, что уже написано.\n'
                '- Три формы записи: `import math` (обращение `math.sqrt`), '
                '`from math import sqrt` (обращение `sqrt`) и `import numpy '
                'as np` (короткое имя). Имя модуля перед точкой показывает, '
                'откуда взялась функция.\n'
                '- `from math import *` не пишут: имена сваливаются в общую '
                'кучу, незаметно перекрывают друг друга, и читатель не может '
                'понять, откуда имя взялось.\n'
                '- **Стандартная библиотека** идёт в комплекте с Python: '
                '`math`, `random`, `datetime`, `re`, `os`, `sys`, `time`. '
                '**Сторонние** библиотеки (`requests`, `numpy`, '
                '`matplotlib`) ставят командой `pip install` – один раз на '
                'компьютере. Не найденный модуль – это '
                '`ModuleNotFoundError`: либо опечатка в имени, либо '
                'библиотека не установлена.\n'
                '- Свой файл с именем модуля (`random.py`, `re.py`, '
                '`math.py`) перекрывает стандартный: Python ищет модуль '
                'сначала в папке программы. Проверить, откуда пришёл модуль, '
                'можно через `модуль.__file__`.'
            )),
        ])

        quiz = _self_check(
            slug='self-check-moduli-i-import',
            title='Самопроверка: модули и импорт',
            description='Пять вопросов по теме урока.',
            questions=[
                dict(
                    type='choice',
                    text=(
                        'Что напечатает программа?\n\n'
                        '```python\n'
                        'import math\n'
                        '\n'
                        'print(math.floor(3.7))\n'
                        '```'
                    ),
                    choices=[
                        ('`3` – `floor` округляет вниз, до ближайшего целого',
                         True),
                        ('`4` – `floor` округляет вверх', False),
                        ('`3.0` – `floor` возвращает дробное число, как и '
                         '`sqrt`', False),
                        ('`Ошибка NameError: имя math не определено – нужна '
                         'запись `from math import floor`', False),
                    ],
                ),
                dict(
                    type='choice',
                    text=(
                        'В чём разница между `import math` и `from math '
                        'import sqrt`?'
                    ),
                    choices=[
                        ('Разница только в записи вызова: в первом случае '
                         'пишут `math.sqrt(16)`, во втором – `sqrt(16)`', True),
                        ('`import math` подключает модуль целиком, а `from '
                         'math import sqrt` – одну функцию, поэтому вторая '
                         'запись работает быстрее и занимает меньше памяти',
                         False),
                        ('После `from math import sqrt` доступно и `math.'
                         'floor`: имя модуля тоже ввозится, просто его не '
                         'видно', False),
                        ('`import math` нельзя записать в одной программе '
                         'вместе с другими `import`', False),
                    ],
                ),
                dict(
                    type='choice',
                    text=(
                        'Программу сохранили под именем `random.py`. После '
                        'этого вызов `random.randint(1, 6)` перестал '
                        'работать. Почему?'
                    ),
                    choices=[
                        ('Python ищет модуль сначала в папке программы: под '
                         'именем `random` нашёлся свой файл, а стандартный '
                         'модуль до дела не дошёл', True),
                        ('Свой файл испортил стандартный модуль '
                         '`random` – его нужно установить заново', False),
                        ('Два модуля с одним именем существовать не могут: '
                         'Python удалил стандартный, чтобы не путаться',
                         False),
                        ('Надо было написать `from random import randint` – '
                         'при такой записи свой файл не мешает', False),
                    ],
                ),
                dict(
                    type='choice',
                    text=(
                        "Программа останавливается с сообщением "
                        "`ModuleNotFoundError: No module named 'requests'`. "
                        'Что это значит и что делать?'
                    ),
                    choices=[
                        ('Модуль не найден: либо в имени опечатка, либо '
                         'сторонняя библиотека не установлена. Имя проверяют, '
                         'а потом ставят `pip install requests`', True),
                        ('Ошибка в интернет-соединении: модули скачиваются '
                         'при каждом запуске программы', False),
                        ('Библиотеку нельзя подключить словом `import`: её '
                         'подключают только командой в терминале', False),
                        ('Программа запущена не из той папки: файл '
                         '`requests.py` лежит в другой', False),
                    ],
                ),
                dict(
                    type='text',
                    text=(
                        'Какой модуль стандартной библиотеки отвечает за '
                        'регулярные выражения?\n\n'
                        'Впишите только имя модуля, латинскими буквами.'
                    ),
                    correct_text_answer='re',
                    alternative_answers=['модуль re'],
                ),
            ],
        )
        ArticleQuiz.objects.get_or_create(
            article=article, quiz=quiz,
            defaults={'label': 'Проверь себя', 'order': 1},
        )

    def seed_8_6(self):
        article = Article.objects.get(
            slug='8-6-regulyarnye-vyrazheniya-yazyk-shablonov')
        article.description = (
            'Регулярное выражение – шаблон, описывающий целое множество '
            'строк. Сырые строки и буква r; метасимволы и классы символов; '
            'квантификаторы, жадность и лень; якоря и границы слова; '
            'экранирование; три функции поиска, объект Match и None. В '
            'уроке два виджета: шаблон и текст правятся прямо на странице.'
        )
        article.save(update_fields=['description'])

        _replace_blocks(article, [
            dict(order=1, block_type='text', title='О чём этот урок', content=(
                'Программа принимает дату и должна убедиться, что '
                'это дата: строка из десяти символов, на третьем и шестом '
                'месте – точки, между ними цифры. Срезами и `isdigit()` из '
                'урока 8.2 такая проверка расписывается в десяток отдельных '
                'условий:\n\n'
                '```python\n'
                "s = '03.09.2026'\n"
                'ok = (len(s) == 10\n'
                "      and s[2] == '.' and s[5] == '.'\n"
                '      and s[:2].isdigit() and s[3:5].isdigit()\n'
                '      and s[6:].isdigit())\n'
                '```\n\n'
                'Работает – и остаётся хрупким: одна описка в индексе, и '
                'проверка пропускает мусор. А главное, для каждой новой '
                'формы записи (телефон, почтовый индекс, номер автомобиля) '
                'придётся писать такой же десяток заново, аккуратно считая '
                'позиции.\n\n'
                'Есть язык, на котором форма записи описывается один раз и '
                'целиком:\n\n'
                '```python\n'
                'import re\n'
                '\n'
                "m = re.search(r'\\d{2}\\.\\d{2}\\.\\d{4}', s)\n"
                '```\n\n'
                'Одна строка вместо десятка проверок – и она же найдёт дату '
                'внутри длинного текста, где позиции заранее неизвестны.\n\n'
                'И честная оговорка на будущее: шаблон проверяет **форму '
                'записи**, а не смысл. Запись `45.13.2026` он пропустит: две '
                'цифры, точки на своих местах – форме всё соответствует, '
                'хотя ни сорок пятого дня, ни тринадцатого месяца не бывает. '
                'Шаблон, который знает календарь, составить можно, но это '
                'уже отдельная задача; здесь речь о форме.\n\n'
                '**В этом уроке:** что такое регулярное выражение и зачем '
                'буква `r` перед шаблоном; метасимволы `\\d`, `\\w`, `\\s` '
                'и их пары с большой буквы; классы символов в квадратных '
                'скобках; квантификаторы – «сколько раз повторить»; жадность '
                'и лень; якоря `^`, `$` и граница слова `\\b`; '
                'экранирование; три функции поиска – `search`, `match` и '
                '`fullmatch`; и когда регулярное выражение не нужно вовсе.'
            )),
            dict(order=2, block_type='text', title='Шаблон вместо перечисления', content=(
                '> **Регулярное выражение** – шаблон, который описывает не '
                'одну строку, а целое множество строк, устроенных похожим '
                'образом. Записывают его самой строкой, у которой часть '
                'символов значит не себя, а правило.\n\n'
                'Дальше будет много незнакомых знаков, но пугаться нечего: '
                'весь язык шаблонов – два десятка символов. Выучить их проще, '
                'чем два десятка методов строки, и работают они по похожим '
                'правилам в любом языке программирования. Каждый знак-правило '
                'называют **метасимволом**.\n\n'
                'Работают с шаблонами через модуль `re` – он из стандартной '
                'библиотеки, и ставить ничего не надо (про модули – урок '
                '8.5):\n\n'
                '```python\n'
                'import re\n'
                '```\n\n'
                'Приставка `re` в названиях функций – сокращение от regular '
                'expression, «регулярное выражение».'
            )),
            dict(order=3, block_type='text', title='Сырые строки: зачем буква `r`', content=(
                'Перед первым шаблоном – обязательная подробность, без '
                'которой регулярные выражения не работают вообще.\n\n'
                '> **Сырая строка** – строковый литерал с буквой `r` перед '
                'кавычкой. В нём обратный слэш остаётся самим собой: Python '
                'не превращает его ни в служебный символ, ни в начало '
                'служебной последовательности.\n\n'
                'Дело в том, что обратный слэш в обычной строке – начало '
                "команды. `'\\n'` – это не два знака, а один: перевод "
                "строки. `'\\t'` – табуляция, `'\\b'` – забой, тот самый, "
                'которым затирают символ (клавиша Backspace). Все эти последовательности Python '
                'заменяет ещё когда читает текст программы.\n\n'
                'Беда в том, что в шаблоне обратный слэш – тоже команда, '
                "только своя. `\\d` значит «цифра», `\\b` – «граница "
                'слова». И это ровно те же два знака. Какую из двух команд '
                'выполнит Python?\n\n'
                '**Свою.** Замену делает не `re`, а сам язык, и делает '
                "раньше: в строке `'\\d'` последовательность `\\d` остаётся "
                'на месте (Python её не знает, оставляет как есть и в новых '
                "версиях ещё и предупреждает), а вот `'\\b'` – уже нет: там "
                'получится один невидимый символ забоя, и шаблон станет '
                'другим. Именно так ломается самый частый шаблон новичка: '
                "записанный как `'\\bкот\\b'` вместо `r'\\bкот\\b'`, он "
                'перестаёт находить слово «кот» – потому что ищет забой, '
                'слово и снова забой.\n\n'
                'Лечится это буквой `r`:\n\n'
                '```python\n'
                "print(len('\\b'))    # 1 – один служебный символ\n"
                "print(len(r'\\b'))   # 2 – обратный слэш и буква b, как и "
                'надо\n'
                '```\n\n'
                '**Правило простое: шаблон всегда пишут сырой строкой.** '
                "`r'\\d+'`, `r'\\bкот\\b'`, `r'\\d{2}\\.\\d{2}\\.\\d{4}'`. "
                'Привыкнуть к букве `r` легко, а искать потом, почему '
                'шаблон «почти работает», – долго.'
            )),
            dict(order=4, block_type='text', title='Метасимволы: один символ из множества', content=(
                'Самые нужные метасимволы описывают **один символ** – но не '
                'какой-то конкретный, а любой из целой группы.\n\n'
                '| Метасимвол | Что значит | Что подходит |\n'
                '|---|---|---|\n'
                '| `.` | любой один символ, кроме перевода строки | в '
                'шаблоне `a.c` – `abc`, `a-c`, `a c` |\n'
                '| `\\d` | одна цифра (от digit) | `0`, `7`, `9` |\n'
                '| `\\D` | один символ, **не** цифра | буква, пробел, точка '
                '|\n'
                '| `\\w` | буква, цифра или подчёркивание (от word) | `д`, '
                '`Ж`, `ё`, `5`, `_` |\n'
                '| `\\W` | один символ, **не** `\\w` | пробел, точка, '
                'запятая |\n'
                '| `\\s` | пробельный символ (от space) | пробел, табуляция, '
                'перевод строки |\n'
                '| `\\S` | один символ, **не** `\\s` | буква, цифра, знак '
                'препинания |\n\n'
                'Запомнить пары легко: **большая буква отрицает маленькую.** '
                '`\\d` – цифра, `\\D` – всё, кроме цифры. Так устроены все '
                'три пары.\n\n'
                'И отдельно про `\\w` – то, чего не ожидают. В большинстве '
                'языков `\\w` значит строго `[A-Za-z0-9_]`: латинские буквы, '
                'цифры и подчёркивание. В Python это иначе: `\\w` считает '
                'буквой **любую** букву Юникода, и кириллица входит в неё '
                "целиком. `re.findall(r'\\w+', 'кот и котлета')` вернёт "
                "`['кот', 'и', 'котлета']`. Это удобно: один и тот же шаблон "
                'годится и для английского текста, и для русского.\n\n'
                'Про `re.findall` стоит сказать сразу: она возвращает **все** '
                'совпадения списком. Это удобно, когда надо посмотреть, что '
                'шаблон вообще находит, – именно её строку показывает виджет '
                'в этом уроке. А три главные функции поиска – `search`, '
                '`match` и `fullmatch` – разберём в конце.'
            )),
            dict(order=5, block_type='code', title='', code_language='python', content=(
                'import re\n'
                '\n'
                "text = 'Заказ 4312 принят 03.09.2026'\n"
                '\n'
                '# ищем первое число где угодно в строке\n'
                "m = re.search(r'\\d+', text)\n"
                "print(m)          # <re.Match object; span=(6, 10), "
                "match='4312'>\n"
                "print(m.group())  # 4312 – текст совпадения\n"
                '# 4312 занимает позиции 6, 7, 8 и 9 – отсюда span=(6, 10):\n'
                '# «до десятой позиции, не включая её»\n'
                '\n'
                '# ищем первое слово: [а-яА-ЯёЁ] – любой из этих символов\n'
                "print(re.search(r'[а-яА-ЯёЁ]+', text).group())   # Заказ\n"
                '\n'
                '# чего в строке нет – того не найдётся\n'
                "print(re.search(r'X', text))                     # None"
            )),
            dict(order=6, block_type='text', title='Классы символов: свой набор в квадратных скобках', content=(
                'Метасимволы описывают группы, заведённые заранее. Свой набор '
                'собирают в **классе** – квадратных скобках:\n\n'
                '| Запись | Что значит |\n'
                '|---|---|\n'
                '| `[абв]` | один символ из перечисленных: `а`, `б` или `в` |\n'
                '| `[а-я]` | диапазон: любая строчная русская буква |\n'
                '| `[0-9]` | диапазон цифр – то же самое, что `\\d` |\n'
                '| `[а-яА-Я0-9]` | в одном классе можно перечислить несколько '
                'диапазонов |\n'
                '| `[^0-9]` | крышка **отрицает**: любой символ, кроме цифр '
                '|\n\n'
                'Три подробности, на которых спотыкаются.\n\n'
                '**Внутри класса точка – это точка.** `[.]` значит ровно '
                'точку, а не «любой символ»: внутри скобок метасимволы '
                'теряют силу. Поэтому точку в дате можно искать и как `[.]`, '
                'и как `\\.` – получится одно и то же.\n\n'
                '**Диапазон идёт от меньшего к большему.** `[а-я]` работает, '
                '`[я-а]` – нет: Python отказывается собирать такой шаблон и '
                'сообщает об ошибке. Порядок символов в диапазоне – не '
                'пожелание, а правило.\n\n'
                '**Крышка отрицает весь класс целиком.** `[^0-9]` – один '
                'символ, не цифра. Сочетать «не» с частью списка нельзя: '
                '`[^абв]` читается как «любой, кроме а, б и в», и никак '
                'иначе.\n\n'
                'И главное: класс – это всегда **один** символ, сколько бы в '
                'нём ни было перечислено. Чтобы таких символов шло подряд '
                'несколько, нужны квантификаторы – о них через блок.'
            )),
            dict(
                order=7, block_type='widget',
                title='Шаблон и текст: что нашлось',
                content=(
                    'Перед вами шаблон и текст – и то и другое можно править '
                    'прямо на странице, подсветка пересчитается сразу. Под '
                    'текстом видно, что именно вернула бы `re.findall(...)`, а '
                    'под ним – список совпадений с позициями: номер символа, '
                    'с которого совпадение начинается, и сам текст.\n\n'
                    'Начните с готовых кнопок слева направо. «цифры» – три '
                    'числа из фразы. «буквы» – то же самое, но наоборот: '
                    'только буквы, цифры пропущены. У «всё, кроме пробелов» '
                    'посмотрите на конец строки: точка приклеилась к '
                    'последнему слову, потому что для `\\S+` знак препинания '
                    '– такой же непробел, как буква. А у «слово целиком» '
                    'точка в совпадение уже не попадает: `\\w` знаки '
                    'препинания не считает. Разница между двумя последними '
                    'шаблонами – один символ, а последнее совпадение у них '
                    'разное.'
                ),
                widget_key='regex-lab',
                widget_config={
                    'pattern': REGEX_LAB_PATTERN,
                    'text': REGEX_LAB_TEXT,
                    'presets': [
                        {'title': 'цифры', 'pattern': r'\d+',
                         'text': REGEX_LAB_TEXT},
                        {'title': 'буквы', 'pattern': r'[а-яА-ЯёЁ]+',
                         'text': REGEX_LAB_TEXT},
                        {'title': 'всё, кроме пробелов', 'pattern': r'\S+',
                         'text': REGEX_LAB_TEXT},
                        {'title': 'слово целиком', 'pattern': r'\w+',
                         'text': REGEX_LAB_TEXT},
                    ],
                },
            ),
            dict(order=8, block_type='text', title='Квантификаторы: сколько раз повторить', content=(
                'Метасимвол описывает один символ, а сколько таких символов '
                'идёт подряд – говорит **квантификатор**, то есть «сколько '
                'раз». Он ставится сразу после символа и относится ровно к '
                'нему:\n\n'
                '| Квантификатор | Сколько раз | Пример | Что найдёт |\n'
                '|---|---|---|---|\n'
                '| `*` | ноль и больше | `ab*c` | `ac`, `abc`, `abbbc` |\n'
                '| `+` | один и больше | `ab+c` | `abc`, `abbbc`, но не `ac` '
                '|\n'
                '| `?` | ноль или один | `-?\\d+` | `5` и `-5` |\n'
                '| `{n}` | ровно n раз | `\\d{3}` | ровно три цифры подряд |\n'
                '| `{n,m}` | от n до m | `\\d{2,4}` | две, три или четыре |\n'
                '| `{n,}` | n и больше | `\\d{2,}` | две и больше, без '
                'верхней границы |\n\n'
                'Звёздочка и плюс различаются одним: `*` разрешает '
                'символу не быть вовсе, `+` требует хотя бы один. Отсюда '
                'разница: шаблон `ab*c` найдёт `ac`, а '
                '`ab+c` – нет.\n\n'
                'Вопросительный знак значит «может быть, а может и не быть». '
                'Именно им описывают необязательный знак: `-?\\d+` – «минус, '
                'если он есть, и число после».\n\n'
                'И ловушка, которую создаёт `{n}`. Квантификатор считает '
                '**символы**, а не числа: для шаблона `\\d{3}` в строке '
                '`6789` есть ровно три цифры подряд – это `678`, а '
                'оставшаяся девятка никого не волнует. Шаблон не проверяет, '
                'что число трёхзначное; он ищет три цифры подряд, а где они '
                'стоят – не его дело.'
            )),
            dict(order=9, block_type='code', title='', code_language='python', content=(
                'import re\n'
                '\n'
                "text = 'Код: 12, 345, 6789'\n"
                '\n'
                "print(re.findall(r'\\d', text))       # ['1', '2', '3', ...]\n"
                '# квантификатора нет – значит ровно один символ\n'
                '\n'
                "print(re.findall(r'\\d+', text))      # ['12', '345', '6789']\n"
                '# один и больше\n'
                '\n'
                "print(re.findall(r'\\d{3}', text))    # ['345', '678']\n"
                '# ровно три подряд: в 6789 хватило только на 678\n'
                '\n'
                "print(re.findall(r'\\d{2,4}', text))  # ['12', '345', '6789']\n"
                '# от двух до четырёх – берёт как можно больше\n'
                '\n'
                "print(re.findall(r'\\d{2,}', text))   # ['12', '345', '6789']\n"
                '# два и больше, верхней границы нет\n'
                '\n'
                '# поиск идёт слева направо и после каждого совпадения\n'
                '# продолжается с того места, где оно кончилось\n'
                '\n'
                "# '?' – «ноль или один раз»: минус может быть, а может и "
                'не быть\n'
                "print(re.findall(r'-?\\d+', '10 -5 3 -42'))\n"
                "# ['10', '-5', '3', '-42']"
            )),
            dict(order=10, block_type='text', title='Жадность: `.*` и `.*?`', content=(
                'Квантификаторы `*` и `+` **жадные**: они берут как можно '
                'больше символов. Отсюда неожиданный результат, на котором '
                'спотыкаются даже опытные:\n\n'
                '```python\n'
                'import re\n'
                '\n'
                'text = \'Кавычки: "раз" и "два"\'\n'
                '\n'
                'print(re.search(r\'".*"\', text).group())    # "раз" и '
                '"два"\n'
                'print(re.search(r\'".*?"\', text).group())   # "раз"\n'
                '```\n\n'
                'Первый шаблон ищет кавычку, потом что угодно, потом кавычку '
                '– и находит от **первой** кавычки до последней: `.*` забрал '
                'и «раз», и второе открытие кавычки, и всё между ними. '
                'Второй отличается одним знаком – вопросительным после '
                'звёздочки – и берёт минимум: от кавычки до ближайшей '
                'следующей кавычки.\n\n'
                '> **Жадный квантификатор** – берёт как можно больше '
                'символов. Добавленный после него `?` делает квантификатор '
                '**ленивым**: берёт как можно меньше.\n\n'
                'Запомнить, какой из двух что делает, помогает сама запись: '
                '`?` рядом с квантификатором читается как «не надо много, '
                'хватит и меньшего».\n\n'
                'Жадность страшна не сама по себе, а тем, что `.*` без второй '
                'кавычки уходит в конец строки: он берёт всё до последнего '
                'символа, потому что шаблону больше ничто не мешает. Если '
                'совпадение вышло длиннее, чем вы ожидали, – ищите причину в '
                'жадности.'
            )),
            dict(order=11, block_type='text', title='Якоря: `^`, `$` и граница слова `\\b`', content=(
                'Пока все шаблоны искали совпадение где угодно в строке. Но '
                'иногда нужно, чтобы кусок стоял в определённом месте – в '
                'начале или в конце.\n\n'
                '| Знак | Что значит |\n'
                '|---|---|\n'
                '| `^` | начало строки |\n'
                '| `$` | конец строки |\n'
                '| `\\b` | граница слова: место, где буква соседствует с '
                'не-буквой |\n\n'
                '**`^` и `$` – не символы, а места.** Они ничего не занимают '
                'в строке и ничего не добавляют к совпадению: шаблон `^\\d+` '
                'в строке `12 34` найдёт `12`, а не «начало» вместе с `12`. '
                'Это называют нулевой шириной: проверка есть, а текста за '
                'ней нет.\n\n'
                'Из этого следует полезное. `^\\d+` требует цифры в начале, '
                'но ничего не говорит про остаток строки. Чтобы потребовать '
                'ещё и конец, ставят `$`: шаблон `^\\d+$` подойдёт строке '
                '`12`, но не строке `12 34`.\n\n'
                '**`\\b` – граница слова.** Это тоже место, а не символ: оно '
                'стоит там, где с одной стороны буква, цифра или '
                'подчёркивание, а с другой – ничего такого. Записывают '
                'границу, когда слово нужно найти целиком: `r\'\\bкот\\b\'` '
                'найдёт `кот` в строке `кот и котлета`, но `котлета` ему не '
                'подойдёт – там после `кот` идёт буква, а не граница. Без '
                '`\\b` шаблон `кот` нашёл бы кусок слова и в `котлете` '
                'тоже.\n'
            )),
            dict(order=12, block_type='text', title='Экранирование: точка, которая значит точку', content=(
                'Часть знаков в шаблоне значит не себя, а правило: `.` `*` '
                '`+` `?` `{` `}` `[` `]` `^` `$` и сам `\\`. Все они уже '
                'встретились выше.\n\n'
                'Отсюда вопрос: как искать точку, если `.` значит «любой '
                'символ»? Ответ – поставить перед ней обратный слэш:\n\n'
                '> **Экранирование** – обратный слэш перед метасимволом '
                'отменяет его служебный смысл: знак начинает значить сам '
                'себя.\n\n'
                '| В шаблоне | Что найдёт |\n'
                '|---|---|\n'
                '| `\\.` | точку |\n'
                '| `\\\\` | обратный слэш |\n\n'
                'Это ровно та причина, из-за которой дату ищут шаблоном '
                "`r'\\d{2}\\.\\d{2}\\.\\d{4}'`, а не "
                "`r'\\d{2}.\\d{2}.\\d{4}'`. Второй шаблон формально тоже "
                'сработает – но он найдёт и `03x09y2026`: точки в нём значат '
                '«любой символ». Ошибка, которая проходит все проверки на '
                'правильных данных и ломается на первой же случайной строке.\n\n'
                'Внутри класса символов экранировать почти нечего: там, как '
                'уже сказано, `[.]` и так значит точку. А вот обратный слэш '
                'экранируют всегда, и в шаблоне он записывается двумя '
                'знаками: `\\\\` – это один знак `\\` в готовой строке.'
            )),
            dict(order=13, block_type='text', title='Три функции поиска: `search`, `match`, `fullmatch`', content=(
                'Найти совпадение можно тремя функциями, и разница между ними '
                'только в том, **где** разрешено совпадение начинаться и чем '
                'оно должно кончиться.\n\n'
                '| Функция | Что проверяет | Когда брать |\n'
                '|---|---|---|\n'
                '| `re.search(шаблон, строка)` | есть ли совпадение **где '
                'угодно** в строке | обычный случай: «найти в строке '
                'что-нибудь по образцу» |\n'
                '| `re.match(шаблон, строка)` | совпадение начинается **с '
                'начала** строки, но кончиться может где угодно | строка '
                'начинается с образца, а дальше идёт что угодно |\n'
                '| `re.fullmatch(шаблон, строка)` | строка совпадает с '
                'шаблоном **целиком** | проверка формата: «эта строка – '
                'ровно дата, и ничего лишнего» |\n\n'
                'Все три возвращают одно и то же: либо объект **`Match`** – '
                'найденный кусок со всеми сведениями о нём, либо **`None`** – '
                '«ничего не нашлось».\n\n'
                '> **`None`** – особое значение «здесь ничего нет». Оно не '
                'равно ни пустой строке, ни нулю: так функция честно '
                'сообщает, что результата не получилось.\n\n'
                'Проверяют результат всегда одинаково, через `if`:\n\n'
                '```python\n'
                'm = re.search(шаблон, строка)\n'
                'if m:\n'
                '    print(m.group())     # есть совпадение – вот его текст\n'
                'else:\n'
                "    print('не найдено')\n"
                '```\n\n'
                '**`if m:` читается как «если совпадение есть»:** объект '
                '`Match` в условии даёт истину, а `None` – ложь. Текст самого '
                'совпадения забирают методом `m.group()`.\n\n'
                'Самая частая ошибка – пропустить проверку:\n\n'
                '```python\n'
                "print(re.search(r'X', 'кот').group())\n"
                "# AttributeError: 'NoneType' object has no attribute 'group'\n"
                '```\n\n'
                'Сообщение читается странно, а означает простое: совпадения '
                'не нашлось, `None` – это не `Match`, и метода `group()` у '
                'него нет. Поэтому перед `group()` всегда стоит `if m:`.'
            )),
            dict(order=14, block_type='code', title='', code_language='python', content=(
                'import re\n'
                '\n'
                "date = '03.09.2026'\n"
                "pattern = r'\\d{2}\\.\\d{2}\\.\\d{4}'\n"
                '\n'
                '# search – совпадение может стоять где угодно в строке\n'
                'm = re.search(pattern, date)\n'
                'if m:\n'
                "    print('нашли:', m.group())        # нашли: 03.09.2026\n"
                '\n'
                '# fullmatch – строка должна быть датой целиком\n'
                'm = re.fullmatch(pattern, date)\n'
                'if m:\n'
                "    print('это дата и ничего лишнего')\n"
                '\n'
                '# а здесь перед датой стоит слово – и fullmatch молчит\n'
                "m = re.fullmatch(pattern, 'сдано ' + date)\n"
                'if not m:\n'
                "    print('не дата: в строке есть лишнее')\n"
                '\n'
                '# search на той же строке дату находит\n'
                "m = re.search(pattern, 'сдано ' + date)\n"
                'if m:\n'
                "    print(m.group())                  # 03.09.2026"
            )),
            dict(
                order=15, block_type='widget',
                title='Шаблон для даты: что он пропускает',
                content=(
                    'Тот же виджет, но теперь про дату – и про то, что один '
                    'шаблон пропускает не всё, что похоже на правду.\n\n'
                    'В тексте три записи, похожие на дату, а подходит шаблону '
                    'только две. Кнопки показывают, что меняется, если '
                    'разрешить в дне и месяце одну цифру вместо двух: тогда '
                    'под шаблон попадает и короткая запись `1.1.26`. Заодно '
                    'видно, что строгость при этом падает: `\\d{1,2}` '
                    'разрешает и `03.09.2026`, и `1.1.26` – а заодно '
                    'пропустит `99.99.2026`, потому что форму оно соблюдает.\n\n'
                    'Попробуйте и обратное: замените `\\d{4}` на `\\d{2}` и '
                    'посмотрите, что станет с совпадениями. А потом почините '
                    'шаблон – так с регулярными выражениями и работают: '
                    'пишут, смотрят на подсветку, правят.'
                ),
                widget_key='regex-lab',
                widget_config={
                    'pattern': REGEX_DATE_PATTERN,
                    'text': REGEX_DATE_TEXT,
                    'presets': [
                        {'title': 'строго две цифры',
                         'pattern': r'\d{2}\.\d{2}\.\d{4}',
                         'text': REGEX_DATE_TEXT},
                        {'title': 'одна или две',
                         'pattern': r'\d{1,2}\.\d{1,2}\.\d{2,4}',
                         'text': REGEX_DATE_TEXT},
                        {'title': 'день и месяц',
                         'pattern': r'\d{2}\.\d{2}',
                         'text': REGEX_DATE_TEXT},
                        {'title': 'только год',
                         'pattern': r'\d{4}',
                         'text': REGEX_DATE_TEXT},
                    ],
                },
            ),
            dict(order=16, block_type='text', title='Шпаргалка', content=(
                'Одна таблица на весь урок – синтаксис и функции вместе.\n\n'
                '| Что | Что значит |\n'
                '|---|---|\n'
                '| `.` | любой один символ, кроме перевода строки |\n'
                '| `\\d` `\\D` | цифра / не цифра |\n'
                '| `\\w` `\\W` | буква, цифра, подчёркивание / всё остальное '
                '(в Python `\\w` включает кириллицу) |\n'
                '| `\\s` `\\S` | пробельный символ / всё остальное |\n'
                '| `[абв]` | один символ из перечисленных |\n'
                '| `[а-я]`, `[0-9]` | диапазон; внутри класса точка значит '
                'точку |\n'
                '| `[^0-9]` | любой символ, кроме перечисленных |\n'
                '| `*`, `+`, `?` | ноль и больше; один и больше; ноль или '
                'один |\n'
                '| `{n}`, `{n,m}`, `{n,}` | ровно n; от n до m; n и больше |\n'
                '| `*?` | ленивый квантификатор: берёт как можно меньше |\n'
                '| `^`, `$` | начало и конец строки |\n'
                '| `\\b` | граница слова |\n'
                '| `\\.`, `\\\\` | точка как точка; обратный слэш |\n'
                '| `r\'…\'` | сырая строка – так записывают любой шаблон |\n'
                '| `re.search` | первое совпадение где угодно в строке |\n'
                '| `re.match` | совпадение с начала строки |\n'
                '| `re.fullmatch` | совпадение со всей строкой целиком |\n'
                '| `re.findall` | список всех совпадений – это показывает '
                'виджет |\n'
                '| `if m:` | проверка, что совпадение есть |\n'
                '| `m.group()` | текст совпадения |\n\n'
                'И предупреждение, которое важнее всех строк выше. '
                'Регулярное выражение – инструмент для **образца**. Если '
                'кусок известен заранее и находится обычным `in`, `find()` '
                'или `split()`, шаблон только удлиняет запись и работает '
                'медленнее: `\'да\' in line` и понятнее, и быстрее, чем '
                "`re.search(r'да', line)`. Регулярку берут там, где "
                'перечислить варианты нельзя, а описать форму – можно.'
            )),
            dict(order=17, block_type='text', title='Коротко', content=(
                '- **Регулярное выражение** – шаблон, описывающий целое '
                'множество строк. Он проверяет форму записи, а не смысл: '
                '`45.13.2026` под шаблон даты подойдёт.\n'
                '- Шаблон пишут **сырой строкой**: `r\'\\d+\'`. Без буквы `r` '
                'обратный слэш обработает сам Python, и `\\b` из границы '
                'слова превратится в невидимый забой – шаблон перестанет '
                'находить что-либо.\n'
                '- `\\d`, `\\w`, `\\s` – цифра, «словесный» символ и '
                'пробельный; большая буква отрицает маленькую. В Python `\\w` '
                'считает буквой и кириллицу. Класс `[...]` задаёт свой набор '
                'символов, `[^...]` – всё, кроме них, а внутри класса точка '
                'значит точку.\n'
                '- Квантификаторы `*`, `+`, `?`, `{n}`, `{n,m}`, `{n,}` '
                'считают повторы и жадны по умолчанию; добавленный `?` делает '
                'их ленивыми. `^`, `$` и `\\b` привязывают совпадение к '
                'месту – началу, концу и границе слова; `\\.` и `\\\\` '
                'экранируют точку и сам обратный слэш.\n'
                '- `search` ищет где угодно, `match` – с начала, `fullmatch` '
                '– по всей строке целиком. Все три возвращают `Match` или '
                '`None`, и перед `group()` нужна проверка `if m:`.\n'
                '- И последнее: регулярка нужна там, где кусок описывается '
                '**образцом**, а не там, где его находит обычный `find()`. '
                'Если строка известна заранее, `in`, `find()` и `split()` '
                'короче, понятнее и быстрее.'
            )),
        ])

        quiz = _self_check(
            slug='self-check-regulyarnye-vyrazheniya',
            title='Самопроверка: язык регулярных выражений',
            description='Пять вопросов по теме урока.',
            questions=[
                dict(
                    type='choice',
                    text=(
                        'Что напечатает программа?\n\n'
                        '```python\n'
                        'import re\n'
                        '\n'
                        "m = re.search(r'\\d+', 'дом 12, кв 5')\n"
                        'print(m.group())\n'
                        '```'
                    ),
                    choices=[
                        ('`12` – `search` возвращает первое совпадение', True),
                        ('`5` – последнее число строки', False),
                        ('`125` – все цифры строки, склеенные вместе',
                         False),
                        ('`None` – в строке нет ни одного числа целиком',
                         False),
                    ],
                ),
                dict(
                    type='choice',
                    text=(
                        'Что вернёт `re.fullmatch(r\'\\d{2}\\.\\d{2}\\.'
                        "\\d{4}', 'сдано 03.09.2026')`?"
                    ),
                    choices=[
                        ('`None`: `fullmatch` требует совпадения со всей '
                         'строкой целиком, а здесь есть лишние слова. '
                         '`search` на этой же строке дату нашёл бы', True),
                        ('Объект `Match` с текстом `03.09.2026`: `fullmatch` '
                         'ищет по всей строке и выхватывает из неё дату',
                         False),
                        ('Объект `Match` с текстом `сдано 03.09.2026`',
                         False),
                        ('Ошибку: шаблон не подходит этой строке', False),
                    ],
                ),
                dict(
                    type='choice',
                    text=(
                        'Функция `re.search` не нашла в строке ничего '
                        'подходящего. Что она вернёт и как это проверяют?'
                    ),
                    choices=[
                        ('`None`; проверяют через `if m:` – объект `Match` в '
                         'условии даёт истину, а `None` – ложь', True),
                        ('Пустую строку `\'\'`; проверяют через `if m == '
                         '\'\':`', False),
                        ('Ошибку `AttributeError`; её перехватывают через '
                         '`try`', False),
                        ('Число `0`; проверяют через `if m == 0:`', False),
                    ],
                ),
                dict(
                    type='choice',
                    text=(
                        'Шаблон `\\bкот\\b` записали обычной строкой, без '
                        'буквы `r`, – и программа перестала находить слово '
                        '«кот» в тексте. Почему?'
                    ),
                    choices=[
                        ('В обычной строке `\\b` – служебная '
                         'последовательность «забой»: Python заменил её ещё '
                         'когда читал программу, и в шаблон попал невидимый '
                         'служебный символ вместо границы слова', True),
                        ('Без буквы `r` модуль `re` отказывается принимать '
                         'шаблон и сообщает об ошибке', False),
                        ('Без буквы `r` шаблон начинает различать регистр '
                         'букв, а слово в тексте написано с большой буквы',
                         False),
                        ('В обычной строке обратный слэш исчезает вовсе, и '
                         'шаблон превращается в `кот` без границ слова',
                         False),
                    ],
                ),
                dict(
                    type='text',
                    text=(
                        'Сколько совпадений найдёт `re.findall(r\'\\d{2}\', '
                        "'123 45 6789')`?\n\n"
                        'Впишите только число.'
                    ),
                    correct_text_answer='4',
                ),
            ],
        )
        ArticleQuiz.objects.get_or_create(
            article=article, quiz=quiz,
            defaults={'label': 'Проверь себя', 'order': 1},
        )

    def seed_8_7(self):
        article = Article.objects.get(
            slug='8-7-regulyarnye-vyrazheniya-na-praktike')
        article.description = (
            'Что делать с найденным: re.findall и его ловушка со скобками – '
            'без групп список совпадений, одна группа даёт список её '
            'содержимого, две и больше – кортежи. Группы и m.group(1), '
            'замена по шаблону через re.sub с параметром count, разрез '
            'строки сразу по нескольким разделителям через re.split, разбор '
            'файла построчно и правило, когда регулярное выражение брать не '
            'нужно вовсе.'
        )
        article.save(update_fields=['description'])

        _replace_blocks(article, [
            dict(order=1, block_type='text', title='О чём этот урок', content=(
                'В папке лежит файл `journal.txt` – журнал, который '
                'программа дописывает каждый день. В каждой строке дата, '
                'время и число:\n\n'
                '```\n'
                '03.09.2026 14:05 вход 12\n'
                '03.09.2026 14:40 выход 7\n'
                '04.09.2026 09:10 вход 5\n'
                '```\n\n'
                'Нужно сложить все числа за сентябрь – и заодно сосчитать, '
                'сколько всего было записей. Найти одно совпадение мы умеем: '
                '`re.search` отыщет и дату, и первое число. Но строк в файле '
                'тысячи, и в каждой нужно разобрать дату на день, месяц и '
                'год, а число отделить от остального текста. Значит, нужны '
                'две новые вещи: получить **все** совпадения сразу и вынуть '
                'из совпадения его части.\n\n'
                '**В этом уроке:** `re.findall` – все совпадения списком и '
                'ловушка со скобками, из-за которой он возвращает не то, '
                'что ждали; группы и `m.group(1)`; замена по шаблону через '
                '`re.sub`; разрез строки сразу по нескольким разделителям '
                'через `re.split`; разбор файла построчно; и правило, когда '
                'регулярное выражение брать не надо вовсе.'
            )),
            dict(order=2, block_type='text', title='`findall()`: все совпадения сразу', content=(
                'Поиск одного совпадения – это `search`. Когда нужно не '
                'первое, а **все**, берут другую функцию.\n\n'
                '> **`re.findall(шаблон, строка)`** – возвращает список всех '
                'совпадений, найденных в строке слева направо. Не объекты '
                '`Match`, а готовые куски текста.\n\n'
                '| Что сравниваем | `re.search` | `re.findall` |\n'
                '|---|---|---|\n'
                '| Сколько находит | первое совпадение | все совпадения |\n'
                '| Что возвращает | объект `Match` | список строк |\n'
                '| Если совпадений нет | `None` | пустой список `[]` |\n'
                '| Как взять текст | `m.group()` | элемент списка |\n\n'
                'Разница в возврате не случайна. `search` рассказывает всё о '
                '**одном** совпадении: где оно стоит, из чего состоит. '
                '`findall` отвечает на другой вопрос – «что тут вообще '
                'есть», – и потому отдаёт только текст, без координат и без '
                'объектов.\n\n'
                '```python\n'
                'import re\n'
                '\n'
                "text = 'В корзине 12 яблок, 5 груш и 2026 вишен.'\n"
                '\n'
                "print(re.findall(r'\\d+', text))        # ['12', '5', '2026']\n"
                "print(len(re.findall(r'\\d+', text)))   # 3 – столько чисел\n"
                '\n'
                "print(re.findall(r'\\d+', 'здесь чисел нет'))   # []\n"
                '# пустой список, а не None: совпадений не нашлось ни одного\n'
                '```\n\n'
                'Список удобно считать: `len()` даёт количество совпадений. '
                'Именно так в задаче про журнал и узнаётся, сколько строк '
                'подошло.'
            )),
            dict(order=3, block_type='code', title='', code_language='python', content=(
                'import re\n'
                '\n'
                "text = 'Заказ 4312 от 03.09.2026, сумма 1500 руб.'\n"
                '\n'
                '# все числа подряд: дата распалась на три числа\n'
                "print(re.findall(r'\\d+', text))\n"
                "# ['4312', '03', '09', '2026', '1500']\n"
                "print(len(re.findall(r'\\d+', text)))     # 5\n"
                '\n'
                '# \\w+ – «словесные» символы: буквы, цифры и подчёркивание\n'
                "print(re.findall(r'\\w+', text))\n"
                "# ['Заказ', '4312', 'от', '03', '09', '2026', 'сумма', "
                "'1500', 'руб']\n"
                '\n'
                '# только русские буквы – цифры в такие слова не попадут\n'
                "print(re.findall(r'[а-яА-ЯёЁ]+', text))\n"
                "# ['Заказ', 'от', 'сумма', 'руб']\n"
                '\n'
                '# сколько раз встретилось слово «кот» целиком\n'
                "print(len(re.findall(r'\\bкот\\b', 'кот и котлета, кот')))"
                '   # 2'
            )),
            dict(order=4, block_type='text', title='Ловушка: скобки меняют результат `findall`', content=(
                'Первое, на чём спотыкаются все: стоит в шаблоне появиться '
                'скобкам, и `findall` возвращает совсем не то, что от него '
                'ждут.\n\n'
                '```python\n'
                'import re\n'
                '\n'
                "text = 'кот 3, пёс 12'\n"
                '\n'
                "print(re.findall(r'\\w+ \\d+', text))\n"
                "# ['кот 3', 'пёс 12'] – совпадения целиком\n"
                '\n'
                "print(re.findall(r'(\\w+) \\d+', text))\n"
                "# ['кот', 'пёс'] – только содержимое группы\n"
                '\n'
                "print(re.findall(r'(\\w+) (\\d+)', text))\n"
                "# [('кот', '3'), ('пёс', '12')] – кортежи групп\n"
                '```\n\n'
                'Правило ровно такое: **без групп – совпадения целиком, одна '
                'группа – список её содержимого, две и больше – список '
                'кортежей.** И сделано это нарочно. Скобки в шаблоне ставят '
                'не просто так, а чтобы выделить нужную часть, – и `findall` '
                'возвращает именно её. Числа из примера нужны были без слов, '
                'и лишний текст в списке только мешал бы.\n\n'
                'Если нужны и часть, и совпадение целиком, весь шаблон берут '
                'в ещё одну пару скобок – тогда первой группой станет всё '
                'совпадение:\n\n'
                '```python\n'
                "print(re.findall(r'((\\w+) (\\d+))', text))\n"
                "# [('кот 3', 'кот', '3'), ('пёс 12', 'пёс', '12')]\n"
                '```\n\n'
                'И предупреждение на будущее: круглые скобки в шаблоне – это '
                '**всегда** группа. Поставленные просто чтобы сгруппировать '
                'ветки «или», они точно так же переменят результат '
                '`findall`. Для такой группировки есть форма `(?:…)` – '
                'скобки без памяти:\n\n'
                '```python\n'
                "print(re.findall(r'(?:кот|пёс)', 'кот и пёс'))\n"
                "# ['кот', 'пёс'] – строки, а не кортежи\n"
                '```'
            )),
            dict(order=5, block_type='text', title='Группы: вытащить части совпадения', content=(
                'Второй способ разобрать найденное на части – группы. Он '
                'работает и с `search`, и с `match`, и с `fullmatch`.\n\n'
                '> **Группа** – часть шаблона в круглых скобках. Совпадение с '
                'этой частью запоминается отдельно, и его можно достать из '
                'объекта `Match`.\n\n'
                '```python\n'
                'import re\n'
                '\n'
                "m = re.search(r'(\\d{2})\\.(\\d{2})\\.(\\d{4})', "
                "'03.09.2026')\n"
                '\n'
                'print(m.group(0))     # 03.09.2026 – всё совпадение\n'
                'print(m.group(1))     # 03 – первая группа\n'
                'print(m.group(2))     # 09\n'
                'print(m.group(3))     # 2026\n'
                "print(m.groups())     # ('03', '09', '2026')\n"
                '```\n\n'
                '**`group(0)` – это всё совпадение целиком**, а группы '
                'начинаются с единицы. Номер группы определяется '
                '**открывающей скобкой**: первая слева открылась – первая '
                'группа, вторая открылась – вторая. Поэтому вложенные одна в '
                'другую скобки нумеруются по порядку открытия:\n\n'
                '```python\n'
                "m = re.search(r'((\\d{2})\\.(\\d{2})\\.(\\d{4}))', "
                "'03.09.2026')\n"
                '\n'
                'print(m.group(1))     # 03.09.2026 – внешняя скобка\n'
                'print(m.group(2))     # 03 – та, что открылась следом\n'
                '```\n\n'
                'Работает это только с объектом `Match`: `findall` объектов '
                'не отдаёт, у него вместо `group()` – список, разобранный в '
                'предыдущем блоке.'
            )),
            dict(order=6, block_type='code', title='', code_language='python', content=(
                'import re\n'
                '\n'
                "date = '03.09.2026'\n"
                "pattern = r'(\\d{2})\\.(\\d{2})\\.(\\d{4})'\n"
                '\n'
                'm = re.search(pattern, date)\n'
                'if m:\n'
                '    day, month, year = m.groups()   # три группы – три имени\n'
                '    print(day, month, year)          # 03 09 2026\n'
                "    print('месяц:', month)           # месяц: 09\n"
                '\n'
                '    # group(0) – совпадение целиком, группы – его части\n'
                '    print(m.group(0))                # 03.09.2026\n'
                '    print(m.group(1))                # 03\n'
                '\n'
                '    # группы – строки, как и всё, что возвращает re\n'
                '    print(int(m.group(3)) + 1)       # 2027'
            )),
            dict(
                order=7, block_type='widget',
                title='Скобки: что вернёт findall',
                content=(
                    'Тот же виджет, но теперь про группы: в тексте три даты, '
                    'а шаблон меняется от кнопки к кнопке. Под текстом '
                    'видно, что именно вернул бы `re.findall(...)`, – и это '
                    'самый быстрый способ увидеть ловушку из блока выше '
                    'своими глазами.\n\n'
                    'Начните с «день, месяц, год»: две группы в шаблоне – и '
                    'список состоит из кортежей. Нажмите «день и месяц» – '
                    'скобок стало меньше, а вместе с ними из списка исчез и '
                    'год: одна группа даёт список строк. А «без групп» '
                    'возвращает даты целиком. Один и тот же текст, три '
                    'разных ответа – разница только в скобках.\n\n'
                    'Допишите в шаблон ещё одну пару скобок вокруг всего '
                    'шаблона – и первым в каждом кортеже встанет вся дата. '
                    'Так и проверяйте свои шаблоны: правьте и смотрите, что '
                    'стало со списком.'
                ),
                widget_key='regex-lab',
                widget_config={
                    'pattern': REGEX_GROUP_PATTERN,
                    'text': REGEX_GROUP_TEXT,
                    'presets': [
                        {'title': 'без групп',
                         'pattern': r'\d{2}\.\d{2}\.\d{4}',
                         'text': REGEX_GROUP_TEXT},
                        {'title': 'день и месяц',
                         'pattern': r'(\d{2})\.(\d{2})\.\d{4}',
                         'text': REGEX_GROUP_TEXT},
                        {'title': 'день, месяц, год',
                         'pattern': r'(\d{2})\.(\d{2})\.(\d{4})',
                         'text': REGEX_GROUP_TEXT},
                    ],
                },
            ),
            dict(order=8, block_type='text', title='`sub()`: замена по шаблону', content=(
                '`replace()` из урока 8.2 меняет один точно известный кусок. '
                'Когда заменять надо по образцу – все числа, все даты, все '
                'пробелы подряд, – берут `re.sub`.\n\n'
                '> **`re.sub(шаблон, замена, строка)`** – заменяет **все** '
                'совпадения шаблона на указанный текст и возвращает новую '
                'строку.\n\n'
                '```python\n'
                'import re\n'
                '\n'
                "print(re.sub(r'\\d', '*', 'кот 3 и пёс 12'))\n"
                '# кот * и пёс **\n'
                '```\n\n'
                'Четвёртый параметр – `count` – ограничивает число замен. '
                '`count=1` заменит только первое совпадение, `count=3` – '
                'первые три; без него заменяются все:\n\n'
                '```python\n'
                "print(re.sub(r'\\d', '*', 'кот 3 и пёс 12', count=1))\n"
                '# кот * и пёс 12\n'
                '```\n\n'
                'Замена на пустую строку – это **удаление**: так убирают '
                'лишние пробелы, дефисы или знаки препинания. А ещё '
                'запомним главное: **исходная строка не меняется**. `sub` '
                'ничего не правит на месте – он возвращает новую строку, и '
                'если результат никуда не сохранить, всё останется как '
                'было. Строки в Python неизменяемы (урок 8.1), заменить в '
                'них символ невозможно в принципе.'
            )),
            dict(order=9, block_type='code', title='', code_language='python', content=(
                'import re\n'
                '\n'
                "text = 'Звоните: +7-913-555-35-35 или +7-903-111-22-33'\n"
                '\n'
                '# каждая цифра – звёздочка\n'
                "print(re.sub(r'\\d', '*', text))\n"
                '# Звоните: +*-***-***-**-** или +*-***-***-**-**\n'
                '\n'
                '# count – только первые одиннадцать цифр,\n'
                '# то есть первый номер целиком\n'
                "print(re.sub(r'\\d', '*', text, count=11))\n"
                '# Звоните: +*-***-***-**-** или +7-903-111-22-33\n'
                '\n'
                '# результат – новая строка, исходная не меняется\n'
                'print(text)\n'
                '# Звоните: +7-913-555-35-35 или +7-903-111-22-33\n'
                '\n'
                '# замена на пустую строку – это удаление\n'
                "messy = 'кот   и    пёс'\n"
                "print(re.sub(r'\\s+', ' ', messy))   # кот и пёс\n"
                "print(re.sub(r'\\s+', '', messy))    # котипёс"
            )),
            dict(order=10, block_type='text', title='`re.split()`: несколько разделителей сразу', content=(
                '`split()` из урока 8.2 умеет одну из двух вещей: без '
                'аргумента режет по пробелам, с аргументом – по одной точно '
                'известной строке. Несколько разных разделителей ему '
                'недоступны, а в данных они встречаются постоянно: поля '
                'пишут то через точку с запятой, то через запятую, то через '
                'точку.\n\n'
                '> **`re.split(шаблон, строка)`** – разрезает строку по всем '
                'местам, которые подходят под шаблон. Разделителем может '
                'быть любой образец, а не только одна конкретная строка.\n\n'
                'Чаще всего разделители просто перечисляют в классе:\n\n'
                '```python\n'
                'import re\n'
                '\n'
                "line = 'Иванов;9А,5.отлично'\n"
                "print(re.split(r'[;,.]', line))\n"
                "# ['Иванов', '9А', '5', 'отлично']\n"
                '```\n\n'
                'Связка из урока 8.2 сделала бы то же самое только цепочкой '
                '`replace`: сначала один знак заменить на общий, потом '
                'второй, потом резать. При трёх-четырёх разделителях такая '
                'цепочка становится нечитаемой, а ошибка в порядке замен '
                'тихо портит данные.\n\n'
                'Шаблон умеет и то, чего `split()` не умеет вовсе, – '
                'описать разделитель вместе с окружением. Так снимают '
                'разделители вместе с пробелами вокруг них, и отдельный '
                '`strip()` потом не нужен:\n\n'
                '```python\n'
                "line = 'Иванов ; 9А , 5'\n"
                "print(re.split(r'\\s*[,;]\\s*', line))   "
                "# ['Иванов', '9А', '5']\n"
                '```\n\n'
                'И привычка, которую стоит завести сразу: **подряд идущие '
                'разделители дают пустые куски.** Разрез строки '
                "`'Иванов;;9А'` по шаблону `[,;]` даст три элемента, и "
                'средний из них – пустая строка: между двумя разделителями '
                'ничего не было. Это не поломка, а сведения. Если пустые '
                'куски не нужны, их отбрасывают вручную – так и сделано в '
                'примере ниже.'
            )),
            dict(order=11, block_type='code', title='', code_language='python', content=(
                'import re\n'
                '\n'
                "text = 'Привет, мир! Как дела? Хорошо...'\n"
                '\n'
                '# один шаблон вместо цепочки replace\n'
                "print(re.split(r'[,.!?]+', text))\n"
                "# ['Привет', ' мир', ' Как дела', ' Хорошо', '']\n"
                '# последний элемент пустой: строка кончалась разделителями\n'
                '\n'
                '# пустые куски и лишние пробелы убираем вручную\n'
                'parts = []\n'
                "for piece in re.split(r'[,.!?]+', text):\n"
                '    piece = piece.strip()\n'
                '    if piece:            # пустая строка в условии – ложь\n'
                '        parts.append(piece)\n'
                "print(parts)             # ['Привет', 'мир', 'Как дела', "
                "'Хорошо']\n"
                '\n'
                '# несколько разделителей перечисляются в одном классе\n'
                "line = 'Иванов;9А,5.отлично'\n"
                "print(re.split(r'[;,. ]', line))   "
                "# ['Иванов', '9А', '5', 'отлично']"
            )),
            dict(order=12, block_type='text', title='Разбор файла построчно', content=(
                'Теперь соединим регулярные выражения с файлами из урока 8.4. '
                'Схема всегда одна и та же: открыть файл, пройти по строкам '
                'циклом, на каждой строке найти образец и сложить найденное '
                'в накопитель.\n\n'
                '```python\n'
                'import re\n'
                '\n'
                'total = 0\n'
                "with open('journal.txt', encoding='utf-8') as f:\n"
                '    for line in f:\n'
                "        for number in re.findall(r'\\d+', line):\n"
                '            total += int(number)\n'
                '```\n\n'
                'Накопитель – обычная переменная, объявленная **до** цикла. '
                'Внутри цикла она меняется, а после него хранит итог; если '
                'объявить её внутри, на каждой строке счёт начинался бы '
                'заново.\n\n'
                'И подробность про перевод строки. Строка, прочитанная из '
                'файла, приходит с `\\n` на конце (урок 8.4), и это почти '
                'никогда не мешает: `\\d+` ищет цифры, а перевод строки – не '
                'цифра. Полезно и обратное: точка `.` по умолчанию перевод '
                'строки **не** находит, поэтому шаблон `.+` не выйдет за '
                'пределы своей строки и не склеит две записи в одну. А вот '
                '`$` прямо перед этим `\\n` совпадение заканчивает – так и '
                'находят число в самом конце строки.'
            )),
            dict(order=13, block_type='code', title='', code_language='python', content=(
                'import re\n'
                '\n'
                '# так выглядит файл journal.txt – пять строк:\n'
                '#   03.09.2026 14:05 вход 12\n'
                '#   03.09.2026 14:40 выход 7\n'
                '#   04.09.2026 09:10 вход 5\n'
                '#   04.09.2026 09:30 сбой\n'
                '#   05.09.2026 10:00 вход 20\n'
                '\n'
                'total = 0     # сумма чисел\n'
                'count = 0     # сколько строк подошло\n'
                '\n'
                "with open('journal.txt', encoding='utf-8') as f:\n"
                '    for line in f:\n'
                '        # одна группа – findall вернёт список строк:\n'
                '        # пустой или из одного элемента\n'
                "        found = re.findall(r'(\\d+)$', line)\n"
                '        if found:      # пустой список в условии – ложь\n'
                '            total += int(found[0])\n'
                '            count += 1\n'
                '\n'
                "print(count, total)   # 4 44\n"
                '# в строке «сбой» числа в конце нет – она не считается,\n'
                '# а из даты и времени числа не взяты: шаблон требует\n'
                '# цифры в самом конце строки'
            )),
            dict(order=14, block_type='text', title='Когда регулярка лишняя', content=(
                'Регулярное выражение – инструмент мощный, и именно поэтому '
                'его хочется применить везде. Делать так не стоит.\n\n'
                '> **Правило: образец – регуляркой, точно известный кусок – '
                'обычными методами строки.** Если нужный текст можно '
                'написать целиком, шаблон только удлиняет запись: он '
                'медленнее и требует от читателя знать язык шаблонов.\n\n'
                '| Задача | Чем решать |\n'
                '|---|---|\n'
                '| Узнать, есть ли в строке слово «ошибка» | `\'ошибка\' in '
                "line` или `line.find('ошибка')` |\n"
                '| Разрезать строку по одной запятой | `line.split(\',\')` |\n'
                '| Заменить букву «ё» на «е» | `line.replace(\'ё\', \'е\')` '
                '|\n'
                '| Проверить начало или конец строки | `line.startswith(...)`, '
                '`line.endswith(...)` |\n'
                '| Найти все даты в журнале, вырезать числа, разобрать '
                'телефон по образцу | регулярное выражение |\n\n'
                'Разница не только в длине записи. Проверка `\'да\' in line` '
                '– прямое сравнение подстроки, а `re.search` разбирает '
                'шаблон и проходит по строке по правилам движка; на тысячах '
                'строк это заметная разница в скорости. И читается `in` без '
                'всякой подготовки: чтобы понять `re.search(r\'да\', line)`, '
                'надо помнить, как устроены шаблоны.\n\n'
                'Регулярка нужна там, где перечислить варианты нельзя, а '
                'образец описать можно: дата, номер телефона, почтовый '
                'индекс, все числа в файле. Там она незаменима. Там, где '
                'текст известен заранее, она лишняя.'
            )),
            dict(order=15, block_type='text', title='Коротко', content=(
                '- `re.findall(шаблон, строка)` возвращает **список всех '
                'совпадений** слева направо, без объектов `Match`. Если '
                'совпадений нет – пустой список `[]`, а не `None`; '
                'количество даёт `len(...)`.\n'
                '- **Ловушка со скобками:** без групп `findall` возвращает '
                'совпадения целиком, одна группа – список её содержимого, '
                'две и больше – список кортежей. Скобки ставят ради нужной '
                'части, поэтому лишний текст в результат и не попадает.\n'
                '- **Группа** – часть шаблона в скобках; нумеруются группы '
                'по порядку открывающих скобок. У объекта `Match` '
                '`m.group(0)` – всё совпадение, `m.group(1)`, `m.group(2)` … '
                '– группы, а `m.groups()` – кортеж всех групп сразу.\n'
                '- `re.sub(шаблон, замена, строка)` заменяет все совпадения, '
                '`count` ограничивает их число, замена на пустую строку – '
                'удаление. Исходная строка не меняется: `sub` возвращает '
                'новую.\n'
                '- `re.split(шаблон, строка)` режет сразу по нескольким '
                'разделителям из класса и умеет разделитель-образец вроде '
                '`\\s*[,;]\\s*`; подряд идущие разделители оставляют пустые '
                'куски, которые убирают вручную.\n'
                '- Файл разбирают построчно: `for line in f`, `findall` на '
                'каждой строке, накопитель до цикла. Перевод строки на конце '
                'шаблону не мешает, а `.` его не находит – совпадение не '
                'выходит за свою строку. И правило: регулярка – для '
                '**образца**, а для точно известного куска есть `in`, '
                '`find()`, `split()` и `replace()`.'
            )),
        ])

        quiz = _self_check(
            slug='self-check-regulyarnye-vyrazheniya-na-praktike',
            title='Самопроверка: регулярные выражения на практике',
            description='Пять вопросов по теме урока.',
            questions=[
                dict(
                    type='choice',
                    text=(
                        'Что напечатает программа?\n\n'
                        '```python\n'
                        'import re\n'
                        '\n'
                        "print(re.findall(r'(\\w+) \\d+', 'мяу 5, гав 10'))\n"
                        '```'
                    ),
                    choices=[
                        ("`['мяу', 'гав']` – скобки сделали группу, и "
                         '`findall` вернул содержимое группы, а не совпадения '
                         'целиком', True),
                        ("`['мяу 5', 'гав 10']` – список совпадений целиком",
                         False),
                        ("`[('мяу', '5'), ('гав', '10')]` – список кортежей",
                         False),
                        ('`None` – шаблон не подошёл строке', False),
                    ],
                ),
                dict(
                    type='choice',
                    text=(
                        'Что напечатает программа?\n\n'
                        '```python\n'
                        'import re\n'
                        '\n'
                        "s = 'кот 3'\n"
                        "re.sub(r'\\d', '*', s)\n"
                        'print(s)\n'
                        '```'
                    ),
                    choices=[
                        ('`кот 3` – `re.sub` не меняет исходную строку, а '
                         'возвращает новую; здесь результат никто не '
                         'сохранил', True),
                        ('`кот *` – `re.sub` заменил цифру прямо в строке '
                         '`s`', False),
                        ('`None` – `re.sub` меняет строку на месте и ничего '
                         'не возвращает', False),
                        ('Ошибку `TypeError`: строку изменить нельзя', False),
                    ],
                ),
                dict(
                    type='choice',
                    text=(
                        'Чем `re.split` отличается от `split()` из урока 8.2?'
                    ),
                    choices=[
                        ('`split()` режет по одной точно известной строке (а '
                         "без аргумента – только по пробелам), `re.split` "
                         'принимает шаблон, поэтому разделителей может быть '
                         "сразу несколько: `re.split(r'[;,.]', line)'", True),
                        ('`re.split` возвращает объекты `Match`, а `split()` '
                         '– строки', False),
                        ('`re.split` умеет резать только по одному символу '
                         'за вызов, зато работает быстрее', False),
                        ('`re.split` выбрасывает пустые куски, а `split()` их '
                         'оставляет', False),
                    ],
                ),
                dict(
                    type='choice',
                    text=(
                        'Программа проверяет, встречается ли в строке точно '
                        'известное слово: `if re.search(r\'ошибка\', line):`. '
                        'Почему это неудачный выбор и что написать вместо '
                        'него?'
                    ),
                    choices=[
                        ("Слово известно целиком, а шаблон нужен для образца: "
                         "`if 'ошибка' in line:` короче, читается без знания "
                         "модуля `re` и работает быстрее", True),
                        ('`re.search` возвращает список, а не объект `Match`, '
                         'поэтому условие всегда истинно', False),
                        ('Модуль `re` не входит в стандартную библиотеку, и '
                         'программу придётся запускать с дополнительной '
                         'установкой', False),
                        ('Ничего менять не надо: для поиска слова регулярное '
                         'выражение обязательно', False),
                    ],
                ),
                dict(
                    type='text',
                    text=(
                        'Сколько элементов вернёт '
                        "`len(re.findall(r'\\d{2}', '12345'))`?\n\n"
                        'Впишите только число.'
                    ),
                    correct_text_answer='2',
                ),
            ],
        )
        ArticleQuiz.objects.get_or_create(
            article=article, quiz=quiz,
            defaults={'label': 'Проверь себя', 'order': 1},
        )

    def seed_8_8(self):
        """Практикум блока 8: отдельная страница обязательных задач.

        Не статья: теории здесь нет, только 20 задач на программирование с
        автопроверкой. Порядок по нарастающей: 1–2 базовые операции со
        строкой, 3–4 поиск и замена, 5–7 разбор строки посимвольно, 8–10
        шифрование, сжатие и перекрывающиеся вхождения, 11–14 файлы,
        15–17 регулярные выражения, 18–20 разбор
        приложенного файла.

        Материал ограничен блоками 1–8: арифметика, input/print,
        if/elif/else, while, for/range, строки целиком (индексы, срезы,
        методы, split/join, f-строки), ord()/chr() из блока 7, файлы (open, with,
        режимы 'w' и 'a', чтение по строкам) и модуль re (fullmatch,
        findall, sub). Ни списков как темы, ни своих функций, ни словарей,
        ни сортировки: из split() и findall() берутся только длина, индекс
        и обход циклом.

        Ожидаемые ответы выверены по эталонным решениям – по одному на
        каждую задачу, – а не выписаны от руки.
        """
        section = Section.objects.get(slug='blok-8')

        quiz = _self_check(
            slug='praktikum-blok-8',
            title='Практикум блока 8: обязательные задачи',
            description=(
                '20 программ на Python с автоматической проверкой. Попыток не '
                'ограничено, решённые задачи сохраняются. Задача засчитывается '
                'только если пройдены все тесты. Важно: input() без '
                'текста-подсказки, ничего лишнего не печатать, формат вывода – '
                'строго по условию.'
            ),
            questions=[
                dict(
                    type='code', title='Задача 1. Паспорт строки',
                    text=(
                        'Напишите программу, которая считывает строку и выводит, '
                        'сколько в ней символов, а также её первый и последний '
                        'символ.\n'
                        '\n'
                        'Символом считается любой знак, включая пробел.\n'
                        '\n'
                        '**Ввод:** одна непустая строка.\n'
                        '**Вывод:** одно число и два символа через пробел – длина '
                        'строки, её первый символ и её последний символ.\n'
                        '\n'
                        '###### Пример ввода\n'
                        '\n'
                        '```text\n'
                        'привет\n'
                        '```\n'
                        '\n'
                        '###### Пример вывода\n'
                        '\n'
                        '```text\n'
                        '6 п т\n'
                        '```'
                    ),
                    test_cases=[
                        ('привет\n', '6 п т'),
                        ('a\n', '1 a a'),
                        ('Python 3\n', '8 P 3'),
                        ('ёж\n', '2 ё ж'),
                    ],
                ),
                dict(
                    type='code', title='Задача 2. Задом наперёд',
                    text=(
                        'Напишите программу, которая считывает строку и печатает '
                        'её же, но в обратном порядке.\n'
                        '\n'
                        '**Ввод:** одна строка.\n'
                        '**Вывод:** одна строка – исходная строка в обратном '
                        'порядке.\n'
                        '\n'
                        '###### Пример ввода\n'
                        '\n'
                        '```text\n'
                        'привет\n'
                        '```\n'
                        '\n'
                        '###### Пример вывода\n'
                        '\n'
                        '```text\n'
                        'тевирп\n'
                        '```'
                    ),
                    test_cases=[
                        ('привет\n', 'тевирп'),
                        ('a\n', 'a'),
                        ('12345\n', '54321'),
                        ('абв где\n', 'едг вба'),
                    ],
                ),
                dict(
                    type='code', title='Задача 3. Сколько раз и где',
                    text=(
                        'Напишите программу, которая считывает текст и один '
                        'символ, а затем сообщает, сколько раз этот символ '
                        'встречается в тексте, где он стоит впервые и где – в '
                        'последний раз.\n'
                        '\n'
                        'Позиции считаются с нуля: у первого символа позиция 0.\n'
                        '\n'
                        '**Ввод:** две строки – текст, затем один символ.\n'
                        '**Вывод:** три числа через пробел – сколько раз символ '
                        'встречается, позиция первого вхождения и позиция '
                        'последнего. Если символа в тексте нет, вывести '
                        '`0 -1 -1`.\n'
                        '\n'
                        '###### Пример ввода\n'
                        '\n'
                        '```text\n'
                        'кот и кот\n'
                        'о\n'
                        '```\n'
                        '\n'
                        '###### Пример вывода\n'
                        '\n'
                        '```text\n'
                        '2 1 7\n'
                        '```'
                    ),
                    test_cases=[
                        ('кот и кот\nо\n', '2 1 7'),
                        ('кот и кот\nх\n', '0 -1 -1'),
                        ('ааа\nа\n', '3 0 2'),
                        ('один\nн\n', '1 3 3'),
                    ],
                ),
                dict(
                    type='code', title='Задача 4. Замена',
                    text=(
                        'Напишите программу, которая считывает текст и заменяет '
                        'в нём все вхождения одной подстроки на другую.\n'
                        '\n'
                        '**Ввод:** три строки – текст, что заменить и на что '
                        'заменить. Все три строки непустые.\n'
                        '**Вывод:** две строки – текст после замены всех '
                        'вхождений и число сделанных замен.\n'
                        '\n'
                        '###### Пример ввода\n'
                        '\n'
                        '```text\n'
                        'мама мыла раму\n'
                        'ма\n'
                        'па\n'
                        '```\n'
                        '\n'
                        '###### Пример вывода\n'
                        '\n'
                        '```text\n'
                        'папа мыла раму\n'
                        '2\n'
                        '```'
                    ),
                    test_cases=[
                        ('мама мыла раму\nма\nпа\n', 'папа мыла раму\n2'),
                        ('мама мыла раму\nкот\nпёс\n', 'мама мыла раму\n0'),
                        ('ааа\nа\nб\n', 'ббб\n3'),
                        ('1234512345\n12\nX\n', 'X345X345\n2'),
                    ],
                ),
                dict(
                    type='code', title='Задача 5. Буквы, цифры и остальное',
                    text=(
                        'Напишите программу, которая считывает строку и '
                        'сообщает, сколько в ней букв, сколько цифр и сколько '
                        'прочих символов.\n'
                        '\n'
                        'Прочими считаются все символы, которые не буквы и не '
                        'цифры: пробелы, знаки препинания, скобки.\n'
                        '\n'
                        '**Ввод:** одна строка.\n'
                        '**Вывод:** три числа через пробел – количество букв, '
                        'количество цифр и количество прочих символов.\n'
                        '\n'
                        '###### Пример ввода\n'
                        '\n'
                        '```text\n'
                        'Дом 12, кот!\n'
                        '```\n'
                        '\n'
                        '###### Пример вывода\n'
                        '\n'
                        '```text\n'
                        '6 2 4\n'
                        '```'
                    ),
                    test_cases=[
                        ('Дом 12, кот!\n', '6 2 4'),
                        ('abc\n', '3 0 0'),
                        ('2026\n', '0 4 0'),
                        ('а1 б2 в3.\n', '3 3 3'),
                    ],
                ),
                dict(
                    type='code', title='Задача 6. Аббревиатура',
                    text=(
                        'Напишите программу, которая составляет из текста '
                        'аббревиатуру: берёт первую букву каждого слова и '
                        'записывает эти буквы подряд заглавными.\n'
                        '\n'
                        'Слова отделены друг от друга пробелами, но пробелов '
                        'между словами может быть несколько подряд, и по краям '
                        'строки они тоже бывают.\n'
                        '\n'
                        '**Ввод:** одна строка, в которой есть хотя бы одно '
                        'слово.\n'
                        '**Вывод:** одна строка – аббревиатура заглавными '
                        'буквами.\n'
                        '\n'
                        '###### Пример ввода\n'
                        '\n'
                        '```text\n'
                        'московский государственный университет\n'
                        '```\n'
                        '\n'
                        '###### Пример вывода\n'
                        '\n'
                        '```text\n'
                        'МГУ\n'
                        '```'
                    ),
                    test_cases=[
                        ('московский государственный университет\n', 'МГУ'),
                        ('  тихо  идёт   кот \n', 'ТИК'),
                        ('единственное\n', 'Е'),
                        ('high performance computing\n', 'HPC'),
                    ],
                ),
                dict(
                    type='code', title='Задача 7. Разные символы',
                    text=(
                        'Напишите программу, которая считает, сколько в строке '
                        'различных символов и сколько символов встречается в ней '
                        'ровно один раз.\n'
                        '\n'
                        'Регистр важен: `A` и `a` – разные символы. Пробел – '
                        'тоже символ.\n'
                        '\n'
                        'В строке `кот и кот` различных символов пять – `к`, '
                        '`о`, `т`, пробел и `и`, – а ровно один раз встречается '
                        'только `и`.\n'
                        '\n'
                        '**Ввод:** одна непустая строка.\n'
                        '**Вывод:** два числа через пробел – количество '
                        'различных символов и количество символов, встретившихся '
                        'ровно один раз.\n'
                        '\n'
                        '###### Пример ввода\n'
                        '\n'
                        '```text\n'
                        'кот и кот\n'
                        '```\n'
                        '\n'
                        '###### Пример вывода\n'
                        '\n'
                        '```text\n'
                        '5 1\n'
                        '```'
                    ),
                    test_cases=[
                        ('кот и кот\n', '5 1'),
                        ('ааа\n', '1 0'),
                        ('abcd\n', '4 4'),
                        ('Ааbb\n', '3 2'),
                    ],
                ),
                dict(
                    type='code', title='Задача 8. Шифр Цезаря',
                    text=(
                        'Шифр Цезаря сдвигает каждую букву на k позиций вперёд '
                        'по алфавиту, по кругу: за `z` снова идёт `a`. Регистр '
                        'буквы сохраняется, а пробелы и знаки препинания '
                        'остаются на своих местах.\n'
                        '\n'
                        'Напишите программу, которая шифрует строку таким '
                        'способом.\n'
                        '\n'
                        '**Ввод:** строка из латинских букв, пробелов и знаков '
                        'препинания, затем на новой строке целое число k от 0 '
                        'до 25.\n'
                        '**Вывод:** одна строка – зашифрованный текст.\n'
                        '\n'
                        '###### Пример ввода\n'
                        '\n'
                        '```text\n'
                        'abc\n'
                        '3\n'
                        '```\n'
                        '\n'
                        '###### Пример вывода\n'
                        '\n'
                        '```text\n'
                        'def\n'
                        '```'
                    ),
                    test_cases=[
                        ('abc\n3\n', 'def'),
                        ('Hello, World!\n0\n', 'Hello, World!'),
                        ('abz ABZ\n1\n', 'bca BCA'),
                        ('a\n25\n', 'z'),
                    ],
                ),
                dict(
                    type='code', title='Задача 9. Вхождения с перекрытием',
                    text=(
                        'Напишите программу, которая считает, сколько раз одна '
                        'строка встречается в другой, **считая и перекрывающиеся** '
                        'вхождения.\n'
                        '\n'
                        'В строке `ААА` подстрока `АА` встречается два раза: на '
                        'позициях 0 и 1.\n'
                        '\n'
                        '**Ввод:** две строки – текст, затем непустая подстрока.\n'
                        '**Вывод:** одно число – количество вхождений, включая '
                        'перекрывающиеся.\n'
                        '\n'
                        '###### Пример ввода\n'
                        '\n'
                        '```text\n'
                        'ААА\n'
                        'АА\n'
                        '```\n'
                        '\n'
                        '###### Пример вывода\n'
                        '\n'
                        '```text\n'
                        '2\n'
                        '```'
                    ),
                    test_cases=[
                        ('ААА\nАА\n', '2'),
                        ('аааа\nаа\n', '3'),
                        ('кошка съела кошку\nкошк\n', '2'),
                        ('абв\nгде\n', '0'),
                    ],
                ),
                dict(
                    type='code', title='Задача 10. Сжатие',
                    text=(
                        'Напишите программу, которая сжимает строку: каждая '
                        'цепочка одинаковых символов заменяется на сам символ и '
                        'её длину.\n'
                        '\n'
                        'Число пишется всегда, даже если цепочка состоит из '
                        'одного символа: из строки `AAABBC` получается `A3B2C1`.\n'
                        '\n'
                        '**Ввод:** одна непустая строка.\n'
                        '**Вывод:** одна строка – сжатая запись.\n'
                        '\n'
                        '###### Пример ввода\n'
                        '\n'
                        '```text\n'
                        'AAABBC\n'
                        '```\n'
                        '\n'
                        '###### Пример вывода\n'
                        '\n'
                        '```text\n'
                        'A3B2C1\n'
                        '```'
                    ),
                    test_cases=[
                        ('AAABBC\n', 'A3B2C1'),
                        ('AB\n', 'A1B1'),
                        ('AAAA\n', 'A4'),
                        ('AaAa\n', 'A1a1A1a1'),
                    ],
                ),
                dict(
                    type='code', title='Задача 11. Записать и пересчитать',
                    text=(
                        'Напишите программу, которая считывает число n и n строк, '
                        'записывает эти строки в файл `lines.txt` – по одной в '
                        'строке, – а затем **открывает файл заново на чтение** и '
                        'считает, сколько в нём строк и сколько в них всего '
                        'символов без учёта переводов строки.\n'
                        '\n'
                        'Считать нужно именно по прочитанному файлу, а не по '
                        'тому, что было в памяти: ради этого файл и открывается '
                        'второй раз.\n'
                        '\n'
                        '**Ввод:** число n, затем n строк.\n'
                        '**Вывод:** два числа через пробел – количество строк в '
                        'файле и общее число символов в них.\n'
                        '\n'
                        '###### Пример ввода\n'
                        '\n'
                        '```text\n'
                        '3\n'
                        'привет\n'
                        'кот\n'
                        'да\n'
                        '```\n'
                        '\n'
                        '###### Пример вывода\n'
                        '\n'
                        '```text\n'
                        '3 11\n'
                        '```'
                    ),
                    test_cases=[
                        ('3\nпривет\nкот\nда\n', '3 11'),
                        ('1\nок\n', '1 2'),
                        ('2\n\nаб\n', '2 2'),
                        ('3\na\nb\nc\n', '3 3'),
                    ],
                ),
                dict(
                    type='code', title='Задача 12. Сумма из файла',
                    text=(
                        'Напишите программу, которая считывает число n и n целых '
                        'чисел, записывает их в файл `numbers.txt` – по одному в '
                        'строке, – затем читает файл и выводит сумму всех чисел и '
                        'наибольшее из них.\n'
                        '\n'
                        'Сумму и максимум ищите по прочитанному файлу.\n'
                        '\n'
                        '**Ввод:** число n (не меньше 1), затем n целых чисел, '
                        'каждое на своей строке.\n'
                        '**Вывод:** два числа через пробел – сумма и максимум.\n'
                        '\n'
                        '###### Пример ввода\n'
                        '\n'
                        '```text\n'
                        '3\n'
                        '5\n'
                        '-2\n'
                        '10\n'
                        '```\n'
                        '\n'
                        '###### Пример вывода\n'
                        '\n'
                        '```text\n'
                        '13 10\n'
                        '```'
                    ),
                    test_cases=[
                        ('3\n5\n-2\n10\n', '13 10'),
                        ('1\n7\n', '7 7'),
                        ('3\n-5\n-2\n-10\n', '-17 -2'),
                        ('2\n0\n0\n', '0 0'),
                    ],
                ),
                dict(
                    type='code', title='Задача 13. Журнал',
                    text=(
                        'Напишите программу, которая ведёт журнал в файле '
                        '`log.txt`: сначала создаёт пустой файл, затем дописывает '
                        'в него строки по одной, а в конце читает файл и выводит, '
                        'сколько в журнале строк и какова последняя строка.\n'
                        '\n'
                        '**Ввод:** число n (не меньше 1), затем n строк.\n'
                        '**Вывод:** две строки – количество строк в журнале и '
                        'последняя строка.\n'
                        '\n'
                        '###### Пример ввода\n'
                        '\n'
                        '```text\n'
                        '3\n'
                        'вход\n'
                        'выход\n'
                        'сбой\n'
                        '```\n'
                        '\n'
                        '###### Пример вывода\n'
                        '\n'
                        '```text\n'
                        '3\n'
                        'сбой\n'
                        '```'
                    ),
                    test_cases=[
                        ('3\nвход\nвыход\nсбой\n', '3\nсбой'),
                        ('1\nодна\n', '1\nодна'),
                        ('2\nпервый день\nвторой день\n', '2\nвторой день'),
                        ('4\n09:00 вход\n09:30 выход\n10:00 сбой\n10:05 сбой\n',
                         '4\n10:05 сбой'),
                    ],
                ),
                dict(
                    type='code', title='Задача 14. Фильтр строк',
                    text=(
                        'Напишите программу, которая считывает число k, число n и '
                        'n строк, записывает все строки в файл `in.txt`, затем '
                        'читает его и записывает в файл `out.txt` только те '
                        'строки, длина которых **больше** k.\n'
                        '\n'
                        '**Ввод:** число k, число n, затем n строк.\n'
                        '**Вывод:** количество записанных строк, а если их хотя '
                        'бы одна – то и последняя из них на следующей строке. '
                        'Если подходящих строк нет, выводится только `0`.\n'
                        '\n'
                        '###### Пример ввода\n'
                        '\n'
                        '```text\n'
                        '3\n'
                        '3\n'
                        'кот\n'
                        'собака\n'
                        'дом\n'
                        '```\n'
                        '\n'
                        '###### Пример вывода\n'
                        '\n'
                        '```text\n'
                        '1\n'
                        'собака\n'
                        '```'
                    ),
                    test_cases=[
                        ('3\n3\nкот\nсобака\nдом\n', '1\nсобака'),
                        ('10\n2\nкот\nдом\n', '0'),
                        ('3\n2\nкот\nкошка\n', '1\nкошка'),
                        ('1\n3\nа\nбб\nввв\n', '2\nввв'),
                    ],
                ),
                dict(
                    type='code', title='Задача 15. Слова с заглавной буквы',
                    text=(
                        'Напишите программу, которая находит в тексте все слова, '
                        'начинающиеся с заглавной русской буквы.\n'
                        '\n'
                        'Словом считается цепочка русских букв подряд; «ё» и «Ё» '
                        '– тоже русские буквы. Слов, записанных целиком '
                        'заглавными, в тексте не встречается.\n'
                        '\n'
                        '**Ввод:** одна строка.\n'
                        '**Вывод:** одно число – сколько нашлось таких слов, а '
                        'если их хотя бы одно, то на следующей строке первое из '
                        'них.\n'
                        '\n'
                        '###### Пример ввода\n'
                        '\n'
                        '```text\n'
                        'Кот Васька поймал мышь в Москве\n'
                        '```\n'
                        '\n'
                        '###### Пример вывода\n'
                        '\n'
                        '```text\n'
                        '3\n'
                        'Кот\n'
                        '```'
                    ),
                    test_cases=[
                        ('Кот Васька поймал мышь в Москве\n', '3\nКот'),
                        ('нет заглавных букв\n', '0'),
                        ('Ёжик нашёл Ёлку\n', '2\nЁжик'),
                        ('дом 5, улица Мира\n', '1\nМира'),
                    ],
                ),
                dict(
                    type='code', title='Задача 16. Скрыть номера',
                    text=(
                        'Напишите программу, которая скрывает в тексте длинные '
                        'номера: каждая цепочка из **шести и более** цифр подряд '
                        'заменяется на текст `<скрыто>`.\n'
                        '\n'
                        'Цепочки короче шести цифр не трогаются: из строки '
                        '`12345 и 123456` получится `12345 и <скрыто>`.\n'
                        '\n'
                        '**Ввод:** одна строка.\n'
                        '**Вывод:** две строки – получившийся текст и число '
                        'сделанных замен.\n'
                        '\n'
                        '###### Пример ввода\n'
                        '\n'
                        '```text\n'
                        'Платёж 12345678 принят\n'
                        '```\n'
                        '\n'
                        '###### Пример вывода\n'
                        '\n'
                        '```text\n'
                        'Платёж <скрыто> принят\n'
                        '1\n'
                        '```'
                    ),
                    test_cases=[
                        ('Платёж 12345678 принят\n', 'Платёж <скрыто> принят\n1'),
                        ('12345 и 123456\n', '12345 и <скрыто>\n1'),
                        ('нет цифр\n', 'нет цифр\n0'),
                        ('код 123456 и код 7654321\n', 'код <скрыто> и код <скрыто>\n2'),
                    ],
                ),
                dict(
                    type='code', title='Задача 17. Проверка даты',
                    text=(
                        'Напишите программу, которая проверяет, является ли '
                        'введённая строка датой в формате `ДД.ММ.ГГГГ`.\n'
                        '\n'
                        'Строка должна быть датой целиком, без лишних символов: '
                        'день – от 01 до 31, месяц – от 01 до 12, год – ровно '
                        'четыре цифры. Ведущие нули обязательны: `1.1.2026` – не '
                        'дата, а `01.01.2026` – дата. Любой лишний текст вокруг '
                        'тоже делает строку не датой: «сдано 03.09.2026» – ответ '
                        '`NO`.\n'
                        '\n'
                        '**Ввод:** одна строка.\n'
                        '**Вывод:** одно слово – `YES`, если строка является '
                        'датой, и `NO`, если нет.\n'
                        '\n'
                        '###### Пример ввода\n'
                        '\n'
                        '```text\n'
                        '31.12.2026\n'
                        '```\n'
                        '\n'
                        '###### Пример вывода\n'
                        '\n'
                        '```text\n'
                        'YES\n'
                        '```'
                    ),
                    test_cases=[
                        ('31.12.2026\n', 'YES'),
                        ('1.1.2026\n', 'NO'),
                        ('03.13.2026\n', 'NO'),
                        ('сдано 03.09.2026\n', 'NO'),
                    ],
                ),
                dict(
                    type='code', title='Задача 18. Самая длинная цепочка в файле',
                    text=(
                        'К задаче приложены три файла. Их можно скачать и открыть – '
                        'внутри каждого одна длинная строка из заглавных латинских букв.\n'
                        '\n'
                        'На вход подаётся имя одного из этих файлов. Откройте его и '
                        'определите длину самой длинной цепочки одинаковых букв, идущих '
                        'подряд.\n'
                        '\n'
                        'Файл большой, вводить его содержимое руками никто не станет – '
                        'в том и смысл: программа читает данные с диска сама.\n'
                        '\n'
                        '**Ввод:** одна строка – имя файла.\n'
                        '**Вывод:** одно число – длина самой длинной цепочки.\n'
                        '\n'
                        'Формат показан на маленьком выдуманном файле: если бы внутри '
                        'лежало `AABBBBAC`, ответ был бы 4 – четыре буквы `B` подряд.\n'
                        '\n'
                        '###### Пример ввода\n'
                        '\n'
                        '```text\n'
                        'example.txt\n'
                        '```\n'
                        '\n'
                        '###### Пример вывода\n'
                        '\n'
                        '```text\n'
                        '4\n'
                        '```'
                    ),
                    files=CHAIN_FILES,
                    test_cases=[
                        (name + '\n', str(_longest_run(text)))
                        for name, text in CHAIN_FILES
                    ],
                ),
                dict(
                    type='code', title='Задача 19. Самый короткий кусок с нужным числом букв',
                    text=(
                        'К задаче приложены три файла. В каждом – одна длинная строка из '
                        'букв `A`, `B` и `Z`.\n'
                        '\n'
                        'На вход подаётся имя файла и число `k`. Определите **минимальную '
                        'длину** непрерывного куска строки, внутри которого буква `Z` '
                        'встречается ровно `k` раз. Гарантируется, что подходящий кусок '
                        'существует.\n'
                        '\n'
                        'Перебрать все пары границ не получится: в файле десятки тысяч '
                        'символов, и пар границ выходит больше сотни миллионов. Нужен '
                        'проход окном из урока 8.3 – обе границы двигаются только вперёд.\n'
                        '\n'
                        '**Ввод:** две строки – имя файла и целое число `k`.\n'
                        '**Вывод:** одно число – длина самого короткого подходящего куска.\n'
                        '\n'
                        'Формат показан на маленьком выдуманном файле: если бы внутри '
                        'лежало `AZBZCZ`, а `k` равнялось 2, ответ был бы 3 – кусок '
                        '`ZBZ`.\n'
                        '\n'
                        '###### Пример ввода\n'
                        '\n'
                        '```text\n'
                        'example.txt\n'
                        '2\n'
                        '```\n'
                        '\n'
                        '###### Пример вывода\n'
                        '\n'
                        '```text\n'
                        '3\n'
                        '```'
                    ),
                    files=ZONE_FILES,
                    test_cases=[
                        ('{}\n{}\n'.format(name, ZONE_K),
                         str(_min_window_exact(text, 'Z', ZONE_K)))
                        for name, text in ZONE_FILES
                    ],
                ),
                dict(
                    type='code', title='Задача 20. Самый длинный кусок с нужным числом пар',
                    text=(
                        'К задаче приложены три файла. В каждом – одна длинная строка из '
                        'букв `A`, `B` и `C`.\n'
                        '\n'
                        'На вход подаётся имя файла и число `n`. Определите **максимальную '
                        'длину** непрерывного куска строки, внутри которого пара символов '
                        '`BC` – именно в таком порядке и подряд – встречается ровно `n` '
                        'раз. Гарантируется, что подходящий кусок существует.\n'
                        '\n'
                        'Пара считается попавшей в кусок, только если внутрь попали оба её '
                        'символа: пара, у которой `B` осталась левее границы, не в счёт. '
                        'Это и есть главная тонкость задачи – следите за тем, что '
                        'происходит с парой на границе, когда окно сдвигается.\n'
                        '\n'
                        '**Ввод:** две строки – имя файла и целое число `n`.\n'
                        '**Вывод:** одно число – длина самого длинного подходящего куска.\n'
                        '\n'
                        'Формат показан на маленьком выдуманном файле: если бы внутри '
                        'лежало `ABCABCA`, а `n` равнялось 1, ответ был бы 5 – кусок '
                        '`ABCAB`. Пара `BC` в нём одна: вторая `B` стоит последней, и её '
                        '`C` в кусок уже не попала.\n'
                        '\n'
                        '###### Пример ввода\n'
                        '\n'
                        '```text\n'
                        'example.txt\n'
                        '1\n'
                        '```\n'
                        '\n'
                        '###### Пример вывода\n'
                        '\n'
                        '```text\n'
                        '5\n'
                        '```'
                    ),
                    files=PAIR_FILES,
                    test_cases=[
                        ('{}\n{}\n'.format(name, PAIR_N),
                         str(_max_window_pairs(text, 'BC', PAIR_N)))
                        for name, text in PAIR_FILES
                    ],
                ),
            ],
        )
        section.practicum_quiz = quiz
        section.save(update_fields=['practicum_quiz'])
