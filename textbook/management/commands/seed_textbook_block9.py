"""Идемпотентный посев контента блока 9 «Списки, кортежи, множества и словари».

Статьи-заголовки уже созданы командой seed_textbook_structure. Здесь
наполняем их блоками (ArticleBlock) и тестами самопроверки – урок за уроком.
Добавляя новый урок, дописывайте seed_9_N() и вызывайте её из handle().
"""
from copy import deepcopy

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand
from django.db import transaction

from quizzes.models import (
    Choice, Question, QuestionFile, Quiz, TestCase, UserAnswer, UserResult,
)
from textbook.models import Article, ArticleQuiz, Section


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


# Старые статьи блока: уроков было семь и все про списки, тема разбита иначе
# и слаги сменились. Пустых сирот подчищает seed_textbook_structure, но эти –
# с контентом, и он их намеренно не трогает. Чей-то прогресс чтения тут
# важнее нашей чистоты: если статью уже читали, снимаем с публикации и
# оставляем данные учителю.
_OBSOLETE = [
    '9-2-izmenenie-spiskov',
    '9-3-spisochnye-vyrazheniya-list-comprehensions',
    '9-4-vstroennye-funktsii-dlya-spiskov',
    '9-5-algoritmy-lineynogo-poiska',
    '9-6-dvumernye-massivy-matritsy',
    '9-7-ssylki-i-kopirovanie',
]

_OBSOLETE_QUIZZES = [
    'self-check-chto-takoe-massiv-i-list-v-python',
    'self-check-izmenenie-spiskov',
    'self-check-spisochnye-vyrazheniya',
    'self-check-vstroennye-funktsii-spiskov',
    'self-check-lineynyy-poisk',
    'self-check-dvumernye-massivy',
    'self-check-ssylki-i-kopirovanie',
]


def _retire_old_articles(stdout=None):
    # Удаляем и с прогрессом чтения: снятая с публикации статья всё равно
    # висела в сайдбаре у учителя дублем нового урока с тем же номером.
    # Прогресс по старой статье теряется – решение Кирилла (2026-11-15).
    deleted, _ = Article.objects.filter(slug__in=_OBSOLETE).delete()
    # Урок 9.1 остаётся, но его старая самопроверка – нет: иначе под статьёй
    # висели бы два теста, а сохранённая (с ответами учеников) старая
    # самопроверка не удалится сама.
    ArticleQuiz.objects.filter(
        article__slug='9-1-chto-takoe-massiv-i-list-v-python',
        quiz__slug__in=_OBSOLETE_QUIZZES,
    ).delete()
    for quiz in Quiz.objects.filter(slug__in=_OBSOLETE_QUIZZES):
        if not UserResult.objects.filter(quiz=quiz).exists():
            quiz.delete()
    if deleted and stdout:
        stdout.write(f'Старые статьи блока удалены (объектов: {deleted}).')


# Код, который трассирует loop-trace в уроке 9.1: цикл повышает каждую оценку
# на балл. Смысл трассы – показать главное свойство list: список меняется
# на месте, а копия, снятая срезом до цикла, остаётся прежней.
MARKS_CODE = [
    'marks = [5, 4, 3, 5, 4]',
    'backup = marks[:]',
    'for i in range(len(marks)):',
    '    marks[i] = marks[i] + 1',
    'print(marks)',
    'print(backup)',
]


def _marks_trace(start=(5, 4, 3, 5, 4)):
    """Пошаговая трасса цикла, меняющего список на месте.

    Виджет ничего не вычисляет сам – повторяем разбираемый алгоритм обычным
    циклом и складываем ПОЛНОЕ состояние на каждом шаге. backup показываем
    в состоянии намеренно: смысл трассы в том, что он не меняется ни разу.
    """
    steps = []
    marks = None
    backup = None
    i = None

    def state():
        s = {}
        if marks is not None:
            s['marks'] = list(marks)
        if backup is not None:
            s['backup'] = list(backup)
        if i is not None:
            s['i'] = i
            s['marks[i]'] = marks[i]
        return s

    marks = list(start)
    steps.append(dict(
        line=1, vars=state(),
        note='Пять оценок лежат под одним именем, каждая доступна по своему номеру.',
    ))

    backup = marks[:]
    steps.append(dict(
        line=2, vars=state(),
        note='Срез скопировал всю ленту. backup – новый список, а не второе имя '
             'для marks: дальше он меняться не будет.',
    ))

    for pos in range(len(marks)):
        i = pos
        steps.append(dict(
            line=3, vars=state(),
            note='Берём очередной индекс: i = {}. По этому номеру сейчас лежит '
                 '{}.'.format(pos, marks[pos]),
        ))
        was = marks[pos]
        marks[pos] = was + 1
        note = 'Записали {} на место {}: было {}, стало {}.'.format(
            marks[pos], pos, was, marks[pos])
        if pos == 0:
            note += (' Список изменился на месте – новый объект не создавался, '
                     'id(marks) остался прежним. Со строкой так было нельзя.')
        steps.append(dict(line=4, vars=state(), note=note))

    i = None
    steps.append(dict(
        line=3, vars=state(),
        note='Индексы кончились – цикл завершён.',
    ))
    steps.append(dict(
        line=5, vars=state(), out=str(marks),
        note='Все оценки выросли на балл.',
    ))
    steps.append(dict(
        line=6, vars=state(), out=str(backup),
        note='А копия осталась ровно такой, какой её сняли до цикла.',
    ))
    return steps


# Код, который трассирует loop-trace в уроке 9.2: попытка убрать все нули
# удалением прямо во время перебора. Смысл трассы – показать скрытый счётчик
# цикла: список укорачивается влево, счётчик растёт вправо, элемент проскакивает.
REMOVE_CODE = [
    'nums = [1, 0, 0, 3]',
    'for x in nums:',
    '    if x == 0:',
    '        nums.remove(x)',
    'print(nums)',
]


def _remove_trace(start=(1, 0, 0, 3)):
    """Пошаговая трасса цикла, удаляющего элементы из перебираемого списка.

    Повторяем поведение for-по-списку вручную, через явный индекс: именно
    этот индекс в коде не виден, и именно из-за него теряется элемент.
    Переменную счётчика показываем в состоянии под именем «позиция».
    """
    steps = []
    nums = list(start)
    x = None
    pos = None

    def state():
        s = {'nums': list(nums)}
        if pos is not None:
            s['позиция'] = pos
        if x is not None:
            s['x'] = x
        return s

    steps.append(dict(
        line=1, vars=state(),
        note='Четыре числа, два нуля. Задача – убрать из списка все нули.',
    ))

    pos = 0
    while pos < len(nums):
        x = nums[pos]
        note = 'Цикл берёт элемент с позиции {}: x = {}.'.format(pos, x)
        if pos == 0:
            note += (' Этой позиции в коде не видно – счётчик у for свой, '
                     'внутренний, и он просто растёт на единицу каждый шаг.')
        steps.append(dict(line=2, vars=state(), note=note))

        is_zero = (x == 0)
        steps.append(dict(
            line=3, vars=state(), check=is_zero,
            note='Проверяем: {} {} нулю.'.format(x, 'равен' if is_zero else 'не равен'),
        ))

        if is_zero:
            nums.remove(x)
            steps.append(dict(
                line=4, vars=state(),
                note='Нуль удалён, и всё, что было правее, уехало влево на одну '
                     'клетку. В списке осталось {} элемента.'.format(len(nums)),
            ))

        pos += 1

    # x намеренно не сбрасываем: после цикла переменная в Python сохраняет
    # последнее значение, и в трассе она должна вести себя так же.
    steps.append(dict(
        line=2, vars=state(),
        note='Счётчик дорос до {}, а в списке всего {} элемента – индексы 0–{}. '
             'Брать больше нечего, цикл заканчивается.'.format(
                 pos, len(nums), len(nums) - 1),
    ))
    steps.append(dict(
        line=5, vars=state(), out=str(nums),
        note='Один нуль уцелел. После удаления он встал на позицию, которую '
             'счётчик уже прошёл, – цикл до него просто не добрался.',
    ))
    return steps


# Код, который трассирует loop-trace в уроке 9.2: sorted() и a.sort() рядом.
# Смысл трассы – показать две разницы сразу: что происходит с самим списком
# и что каждая запись возвращает. Последняя строка печатает результат sort()
# напрямую – вывести None можно только так: в колонке переменных прочерк
# означает «переменной ещё нет», и для None он читался бы неверно.
SORT_CODE = [
    'a = [3, 1, 2]',
    'b = sorted(a)',
    'print(a)',
    'print(b)',
    'a.sort()',
    'print(a)',
    'print(a.sort())',
]


def _sort_trace(start=(3, 1, 2)):
    """Пошаговая трасса пары sorted() / list.sort().

    Виджет ничего не вычисляет сам – повторяем обе операции обычным Python
    и складываем ПОЛНОЕ состояние на каждом шаге.
    """
    steps = []
    a = None
    b = None

    def state():
        s = {}
        if a is not None:
            s['a'] = list(a)
        if b is not None:
            s['b'] = list(b)
        return s

    a = list(start)
    steps.append(dict(
        line=1, vars=state(),
        note='Три числа не по порядку. Дальше мы упорядочим их двумя разными '
             'способами и посмотрим, чем эти способы отличаются.',
    ))

    b = sorted(a)
    steps.append(dict(
        line=2, vars=state(),
        note='sorted() построила НОВЫЙ список и вернула его – он достался '
             'имени b. Посмотрите на строку a: она не изменилась ни на один '
             'элемент.',
    ))
    steps.append(dict(
        line=3, vars=state(), out=str(a),
        note='Исходный список в прежнем беспорядке.',
    ))
    steps.append(dict(
        line=4, vars=state(), out=str(b),
        note='А в b лежат те же числа, выстроенные по возрастанию.',
    ))

    a.sort()
    steps.append(dict(
        line=5, vars=state(),
        note='Метод sort() работает наоборот: он ничего не создаёт и ничего '
             'не отдаёт – он перестраивает сам список a, на месте. Именно '
             'поэтому слева от него нет никакого присваивания.',
    ))
    steps.append(dict(
        line=6, vars=state(), out=str(a),
        note='Теперь по порядку выстроен и сам a.',
    ))

    a.sort()
    steps.append(dict(
        line=7, vars=state(), out='None',
        note='Вот что sort() возвращает на самом деле – None. Список уже '
             'упорядочен, поэтому переставлять нечего, зато видно значение. '
             'Запись b = a.sort() положила бы в b именно его: та самая '
             'ловушка из урока 9.2.',
    ))
    return steps


# Сквозной пример блока 9: журнал класса. Строка – ученик, столбец –
# контрольная. Одна лента оценок, каких в уроке 9.1 было пять, здесь
# сложена в четыре строки.
JOURNAL = [[5, 4, 3], [3, 3, 4], [5, 5, 5], [4, 2, 3]]
NAMES = ['Аня', 'Борис', 'Вера', 'Глеб']

# Код, который трассирует loop-trace в уроке 9.3: сумма всех оценок журнала
# вложенными циклами. Смысл трассы – показать, что внутренний цикл
# прокручивается целиком на каждый шаг внешнего.
MATRIX_CODE = [
    'journal = [[5, 4, 3], [3, 3, 4], [5, 5, 5], [4, 2, 3]]',
    'total = 0',
    'for i in range(len(journal)):',
    '    for j in range(len(journal[0])):',
    '        total = total + journal[i][j]',
    'print(total)',
]


def _matrix_trace(table=None):
    """Пошаговая трасса обхода таблицы вложенными циклами.

    Виджет ничего не вычисляет сам – повторяем разбираемый алгоритм обычными
    циклами и складываем ПОЛНОЕ состояние на каждом шаге. journal[i][j]
    показываем отдельной строкой состояния: именно это значение прибавляется.
    """
    journal = [list(row) for row in (table or JOURNAL)]
    steps = []
    total = None
    i = None
    j = None

    def state():
        s = {'journal': [list(row) for row in journal]}
        if i is not None:
            s['i'] = i
        if j is not None:
            s['j'] = j
            s['journal[i][j]'] = journal[i][j]
        if total is not None:
            s['total'] = total
        return s

    steps.append(dict(
        line=1, vars=state(),
        note='Четыре строки по три оценки. Строка – ученик, столбец – '
             'контрольная.',
    ))

    total = 0
    steps.append(dict(
        line=2, vars=state(),
        note='Накопитель суммы – он тут ровно такой же, как в любой задаче '
             'на сумму, новых идей не будет.',
    ))

    for row_no in range(len(journal)):
        i = row_no
        j = None
        note = 'Внешний цикл: i = {}. Работаем со строкой {} – это ' \
               'оценки, которые получил один ученик.'.format(row_no, journal[row_no])
        if row_no == 1:
            note += (' Обратите внимание: внутренний цикл к этому моменту '
                     'успел прокрутиться целиком.')
        steps.append(dict(line=3, vars=state(), note=note))

        for col_no in range(len(journal[0])):
            j = col_no
            steps.append(dict(
                line=4, vars=state(),
                note='Внутренний цикл: j = {}. На пересечении лежит '
                     'journal[{}][{}] = {}.'.format(
                         col_no, row_no, col_no, journal[row_no][col_no]),
            ))
            was = total
            total = total + journal[row_no][col_no]
            steps.append(dict(
                line=5, vars=state(),
                note='Прибавили: {} + {} = {}.'.format(
                    was, journal[row_no][col_no], total),
            ))

        j = None
        steps.append(dict(
            line=3, vars=state(),
            note='Строка кончилась, j начнётся заново с нуля, а i вырастет '
                 'на единицу.' if row_no < len(journal) - 1 else
                 'Строки кончились – оба цикла завершены.',
        ))

    i = None
    j = None
    steps.append(dict(
        line=6, vars=state(), out=str(total),
        note='Тело внутреннего цикла выполнилось {} раз – ровно столько, '
             'сколько клеток в таблице.'.format(len(journal) * len(journal[0])),
    ))
    return steps


# Код, который трассирует loop-trace в уроке 9.3: второе имя против глубокой
# копии. Смысл трассы – показать, что одна и та же правка задевает то оба
# имени, то одно, и что видно это по проверкам is.
COPY_CODE = [
    'from copy import deepcopy',
    'journal = [[5, 4, 3], [3, 3, 4]]',
    'backup = journal',
    'journal[0][0] = 2',
    'backup = deepcopy(journal)',
    'journal[0][0] = 5',
    'print(journal)',
    'print(backup)',
]


def _copy_trace():
    """Пошаговая трасса: b = a против b = deepcopy(a).

    Виджет ничего не вычисляет сам – повторяем сценарий обычным кодом.
    Вместо числовых id() держим в состоянии две проверки is: они отвечают на
    тот же вопрос («один это объект или разные»), но читаются без пояснений.
    """
    steps = []
    journal = None
    backup = None

    def state():
        s = {}
        if journal is not None:
            s['journal'] = [list(row) for row in journal]
        if backup is not None:
            s['backup'] = [list(row) for row in backup]
            s['backup is journal'] = backup is journal
            s['backup[0] is journal[0]'] = backup[0] is journal[0]
        return s

    steps.append(dict(
        line=1, vars=state(),
        note='Модуль copy входит в стандартную библиотеку – устанавливать '
             'ничего не нужно.',
    ))

    journal = [[5, 4, 3], [3, 3, 4]]
    steps.append(dict(
        line=2, vars=state(),
        note='Журнал из двух строк. Пока имя одно.',
    ))

    backup = journal
    steps.append(dict(
        line=3, vars=state(),
        note='Копии не произошло: в backup легла та же ссылка. Обе проверки '
             'is отвечают True – объект один, имён два.',
    ))

    journal[0][0] = 2
    steps.append(dict(
        line=4, vars=state(),
        note='Правим клетку через одно имя – меняется и то, что видно через '
             'другое. Резервной копии не существует.',
    ))

    backup = deepcopy(journal)
    steps.append(dict(
        line=5, vars=state(),
        note='deepcopy построил новый внешний список и новые строки внутри. '
             'Теперь обе проверки is отвечают False – общих объектов не '
             'осталось.',
    ))

    journal[0][0] = 5
    steps.append(dict(
        line=6, vars=state(),
        note='Та же самая правка, но теперь она видна только в journal. '
             'Копия живёт своей жизнью.',
    ))

    steps.append(dict(
        line=7, vars=state(), out=str(journal),
        note='В журнале – исправленная оценка.',
    ))
    steps.append(dict(
        line=8, vars=state(), out=str(backup),
        note='А в копии – то состояние, в котором её сняли.',
    ))
    return steps



def _raw(value):
    """Значение для loop-trace, которое виджет не умеет собрать сам.

    Списки и числа виджет печатает по-питоновски сам, а множество и словарь
    приходят из JSON обычным объектом и превращались бы в «[object Object]».
    Поэтому кладём готовую строку: {'__raw': "{'А': 3}"} – виджет печатает
    её как есть. Строку берём из настоящего repr(), чтобы порядок элементов
    в трассе совпадал с тем, что Python покажет ученику.
    """
    return {'__raw': repr(value)}


# ── Трасса (урок 9.5): поиск первого повторяющегося элемента ──────────
DUP_CODE = [
    'nums = [5, 3, 8, 3, 1, 8]',
    'seen = set()',
    'for x in nums:',
    '    if x in seen:',
    "        print('первый повтор:', x)",
    '        break',
    '    seen.add(x)',
]


def _dup_trace(data=(5, 3, 8, 3, 1, 8)):
    """Пошаговая трасса поиска первого повтора через множество.

    Виджет ничего не считает сам – повторяем алгоритм обычным циклом и
    складываем полное состояние на каждом шаге.
    """
    steps = []
    nums = list(data)
    seen = set()
    x = None

    def state():
        s = {'nums': list(nums), 'seen': _raw(seen)}
        if x is not None:
            s['x'] = x
        return s

    steps.append(dict(
        line=1, vars={'nums': list(nums)},
        note='Шесть чисел, среди них есть повторы. Задача – найти первое '
             'число, которое встретится во второй раз.',
    ))
    steps.append(dict(
        line=2, vars=state(),
        note='Пустое множество: сюда будем складывать всё, что уже видели. '
             'Пустое множество записывается только так – {} это словарь.',
    ))

    for value in nums:
        x = value
        steps.append(dict(
            line=3, vars=state(),
            note='Берём очередное число из списка.',
        ))
        if x in seen:
            steps.append(dict(
                line=4, vars=state(), check=True,
                note='Число %d в множестве есть – значит, оно уже встречалось. '
                     'Проверка заняла один шаг, размер множества на неё не '
                     'влияет.' % x,
            ))
            steps.append(dict(
                line=5, vars=state(), out='первый повтор: %d' % x,
                note='Ответ найден.',
            ))
            steps.append(dict(
                line=6, vars=state(),
                note='break – дальше идти незачем, первый повтор нам и был '
                     'нужен. Остаток списка программа не смотрит.',
            ))
            break
        steps.append(dict(
            line=4, vars=state(), check=False,
            note='Числа %d в множестве нет – раньше оно не встречалось.' % x,
        ))
        seen.add(x)
        steps.append(dict(
            line=7, vars=state(),
            note='Запомнили число. Множество выросло на один элемент.',
        ))

    return steps


# ── Трасса (урок 9.6): подсчёт частот букв словарём ───────────────────
FREQ_CODE = [
    "word = 'АБРАКАДАБРА'",
    'freq = {}',
    'for ch in word:',
    '    freq[ch] = freq.get(ch, 0) + 1',
    'print(freq)',
]


def _freq_trace(word='АБРАКАДАБРА'):
    """Пошаговая трасса подсчёта частот букв – то же слово, что в уроке 7.5."""
    steps = []
    freq = {}
    ch = None

    def state():
        s = {'word': word, 'freq': _raw(freq)}
        if ch is not None:
            s['ch'] = ch
        return s

    steps.append(dict(
        line=1, vars={'word': word},
        note='Слово, у которого будем считать буквы. Ровно его мы разбирали '
             'в уроке 7.5, когда строили дерево Хаффмана.',
    ))
    steps.append(dict(
        line=2, vars=state(),
        note='Пустой словарь. Ключом будет буква, значением – сколько раз '
             'она встретилась.',
    ))

    for letter in word:
        ch = letter
        steps.append(dict(
            line=3, vars=state(),
            note='Очередная буква слова.',
        ))
        was = freq.get(ch, 0)
        freq[ch] = was + 1
        if was == 0:
            note = ('Буквы «%s» в словаре не было: get вернул значение по '
                    'умолчанию 0, и в словаре появилась новая пара со '
                    'значением 1.' % ch)
        else:
            note = ('Буква «%s» уже была: get вернул %d, записали %d. Ключ '
                    'тот же, поменялось только значение.' % (ch, was, was + 1))
        steps.append(dict(line=4, vars=state(), note=note))

    ch = None
    steps.append(dict(
        line=5, vars=state(), out=repr(freq),
        note='Готово. Обратите внимание на порядок ключей: он совпал с '
             'порядком первого появления букв в слове.',
    ))
    return steps


class Command(BaseCommand):
    help = "Наполняет статьи блока 9 контентом (уроки добавляются постепенно)."

    @transaction.atomic
    def handle(self, *args, **options):
        _retire_old_articles(self.stdout)
        self.seed_9_1()
        self.seed_9_2()
        self.seed_9_3()
        self.seed_9_4()
        self.seed_9_5()
        self.seed_9_6()
        self.seed_9_practicum()
        self.stdout.write(self.style.SUCCESS('Готово: блок 9 обновлён.'))

    def seed_9_1(self):
        article = Article.objects.get(slug='9-1-chto-takoe-massiv-i-list-v-python')
        article.title = 'Списки: индексы, срезы и изменяемость'
        article.description = (
            'Список как набор значений под одним именем: создание, индексы и '
            'срезы, изменение элементов на месте и разница между вторым именем '
            'и копией.'
        )
        article.save(update_fields=['title', 'description'])

        _replace_blocks(article, [
            dict(order=1, block_type='text', title='О чём этот урок', content=(
                'За четверть было пять контрольных, и надо посчитать средний '
                'балл. В пяти переменных `m1`–`m5` оценки хранить можно, но '
                'цикл по таким именам не напишешь: `range()` умеет считать '
                'числа, а не придумывать имена переменных. Строка тоже не '
                'подходит – в ней лежат символы, а не числа, и исправить одну '
                'оценку всё равно не получится.\n\n'
                'Нужен один набор значений, где у каждого есть номер и любую '
                'позицию можно заменить.\n\n'
                '**В этом уроке:** как создать список и как он устроен; '
                'индексы, отрицательные индексы и срезы – по тем же правилам, '
                'что у строки; почему список можно менять, а строку нельзя; '
                'обход списка циклом и ловушка при попытке изменить элементы; '
                'операции `+`, `*`, `in`; чтение списка чисел из строки ввода; '
                'почему `b = a` – не копия и как получить настоящую копию.'
            )),
            dict(order=2, block_type='text', title='Список', content=(
                '> **Список** (`list`) – упорядоченная изменяемая '
                'последовательность значений. Записывается квадратными '
                'скобками, элементы разделяются запятыми.\n\n'
                'Элементы могут быть **разных типов** – числа, строки, даже '
                'другие списки. Длина не фиксирована, а пустой список `[]` – '
                'вполне нормальное значение. Длину даёт всё та же функция '
                '`len()`, что и у строки.\n\n'
                'Готовый список можно получить и из другого набора значений: '
                '`list()` разбирает строку на символы, а `range()` превращает '
                'в список чисел.\n\n'
                '```python\n'
                'marks = [5, 4, 3, 5, 4]           # список чисел\n'
                "names = ['Аня', 'Борис', 'Вера']  # список строк\n"
                "mixed = [7, 'кот', 3.14, True]    # разные типы – можно\n"
                'empty = []                        # пустой список\n'
                '\n'
                "print(list('abc'))                # ['a', 'b', 'c']\n"
                'print(list(range(5)))             # [0, 1, 2, 3, 4]\n'
                'print(len(marks))                 # 5\n'
                'print(len(empty))                 # 0\n'
                '```'
            )),
            dict(order=3, block_type='text', title='Индексы и срезы', content=(
                'Правила те же, что у строки: нумерация с нуля, отрицательные '
                'индексы считают с конца, срез `a[start:stop:step]` правую '
                'границу не включает.\n\n'
                '| Выражение | Результат |\n'
                '|---|---|\n'
                '| `marks[0]` | `5` – первый элемент |\n'
                '| `marks[-1]` | `4` – последний |\n'
                '| `marks[1:3]` | `[4, 3]` – с 1-го по 2-й |\n'
                '| `marks[::2]` | `[5, 3, 4]` – через один |\n'
                '| `marks[::-1]` | `[4, 5, 3, 4, 5]` – развёрнутый |\n'
                '| `marks[:]` | `[5, 4, 3, 5, 4]` – весь список |\n\n'
                'Разница со строкой одна, но важная: **срез списка даёт новый '
                'список**, а не кусочек исходного. Поэтому `a[:]` – самый '
                'короткий способ снять копию.\n\n'
                'И про границы. Обращение к несуществующему элементу '
                '`marks[5]` останавливает программу с `IndexError`. А срез за '
                'границей `marks[3:100]` ошибки не даёт – просто отдаёт то, '
                'что есть: `[5, 4]`.\n\n'
                '```python\n'
                'marks = [5, 4, 3, 5, 4]\n'
                '\n'
                'print(marks[0])      # 5\n'
                'print(marks[-1])     # 4\n'
                'print(marks[1:3])    # [4, 3]\n'
                'print(marks[::2])    # [5, 3, 4]\n'
                'print(marks[::-1])   # [4, 5, 3, 4, 5]\n'
                'print(marks[:])      # [5, 4, 3, 5, 4]\n'
                'print(marks[3:100])  # [5, 4] – срез за границей не падает\n'
                'print(marks[2])      # 3   – элемент\n'
                'print(marks[2:3])    # [3] – список из одного элемента\n'
                '\n'
                'print(marks[5])      # IndexError: list index out of range\n'
                '```'
            )),
            dict(order=4, block_type='text', title='Список можно менять', content=(
                '> **Изменяемость** – свойство объекта менять своё содержимое '
                'на месте, не превращаясь в новый объект.\n\n'
                'Присваивание по индексу `marks[0] = 2` заменяет элемент. Тот '
                'же код для строки даёт `TypeError`: строка неизменяема, её '
                '«изменение» всегда строит новую строку и перевешивает на неё '
                'имя. Список меняется **на месте**: объект остаётся тем же, '
                'другим становится только его содержимое.\n\n'
                'Отсюда следствие, которое ловит всех: если на список смотрят '
                'два имени, правка через одно видна и через другое.\n\n'
                '```python\n'
                'marks = [5, 4, 3, 5, 4]\n'
                'marks[0] = 2\n'
                'print(marks)     # [2, 4, 3, 5, 4]\n'
                '\n'
                "s = 'кот'\n"
                "s[0] = 'р'       # TypeError: 'str' object does not support\n"
                '                 # item assignment\n'
                '```'
            )),
            dict(
                order=5, block_type='widget',
                title='Список меняется на месте',
                content=(
                    'Программа повышает каждую оценку на балл. Пройдите трассу '
                    'и следите за двумя списками: marks меняется прямо в '
                    'ленте, а backup, снятый срезом до цикла, остаётся прежним.'
                ),
                widget_key='loop-trace',
                widget_config={
                    'code': MARKS_CODE,
                    'vars': ['marks', 'backup', 'i', 'marks[i]'],
                    'steps': _marks_trace(),
                },
            ),
            dict(order=6, block_type='text', title='Обход списка', content=(
                'Способа два, оба знакомы по строкам:\n\n'
                '- `for m in marks` – когда нужны только значения;\n'
                '- `for i in range(len(marks))` – когда нужен номер.\n\n'
                'Ловушка: цикл `for m in marks: m = m + 1` **список не '
                'меняет**. `m` – обычная переменная, на каждом шаге в неё '
                'кладут очередное значение, и присваивание перевешивает саму '
                '`m`, а не клетку списка.\n\n'
                'Чтобы менять элементы, нужен доступ по индексу: '
                '`marks[i] = ...`. Правило коротко: **читать удобно по '
                'значениям, менять – только по индексам.**\n\n'
                '```python\n'
                'marks = [5, 4, 3, 5, 4]\n'
                '\n'
                'for m in marks:\n'
                "    print(m, end=' ')     # 5 4 3 5 4\n"
                'print()\n'
                '\n'
                'for i in range(len(marks)):\n'
                '    print(i, marks[i])    # 0 5, 1 4, 2 3, 3 5, 4 4\n'
                '\n'
                'for m in marks:\n'
                '    m = m + 1             # меняется только переменная m\n'
                'print(marks)              # [5, 4, 3, 5, 4]\n'
                '\n'
                'for i in range(len(marks)):\n'
                '    marks[i] = marks[i] + 1\n'
                'print(marks)              # [6, 5, 4, 6, 5]\n'
                '```'
            )),
            dict(order=7, block_type='text', title='Операции над списками', content=(
                '| Операция | Что делает | Пример |\n'
                '|---|---|---|\n'
                '| `a + b` | склеивает два списка в новый | `[1, 2] + [3]` → '
                '`[1, 2, 3]` |\n'
                '| `a * n` | повторяет список `n` раз | `[0] * 3` → '
                '`[0, 0, 0]` |\n'
                '| `x in a` | есть ли элемент целиком | `3 in [1, 2, 3]` → '
                '`True` |\n'
                '| `a == b` | совпадают ли значения по порядку | '
                '`[1, 2] == [1, 2]` → `True` |\n'
                '| `len(a)` | сколько элементов | `len([5, 4, 3])` → `3` |\n\n'
                'Не путайте `in` у списка и у строки: у строки он ищет '
                'подстроку, у списка сравнивает с элементами целиком, внутрь '
                'не заглядывая.'
            )),
            dict(order=8, block_type='text', title='Список из строки ввода', content=(
                '`input()` всегда возвращает строку. Но `split()` без '
                'аргумента режет её по пробелам и отдаёт **список строк** – '
                'и это уже почти то, что нужно.\n\n'
                'Дальше каждый кусок переводят в число. Проверить, что все они '
                'числа, `int()` не умеет: на постороннем слове он остановит '
                'программу с `ValueError`.\n\n'
                '```python\n'
                'nums = []\n'
                'for s in input().split():\n'
                '    nums.append(int(s))\n'
                '```\n\n'
                'Для вывода есть две записи. `print(*nums)` раскладывает '
                'список в аргументы, и числа печатаются через пробел. А '
                "`' '.join(...)` собирает строку, но требует, чтобы все "
                'элементы уже были строками, – числам нужен `str()`.\n\n'
                'Короткая запись чтения чисел одной строкой будет в уроке 9.3.\n\n'
                '```python\n'
                "parts = input().split()   # ввели: 4 8 15\n"
                "print(parts)              # ['4', '8', '15'] – строки, не числа\n"
                '\n'
                'nums = []\n'
                'for s in parts:\n'
                '    nums.append(int(s))\n'
                'print(nums)               # [4, 8, 15]\n'
                'print(sum(nums))          # 27\n'
                '\n'
                'print(*nums)              # 4 8 15 – звёздочка раскладывает\n'
                '                          # список в аргументы print\n'
                "print(' '.join(parts))    # 4 8 15 – join склеивает строки\n"
                'print(sum(nums) / len(nums))   # 9.0\n'
                '```'
            )),
            dict(order=9, block_type='text', title='Два имени – один список', content=(
                'Присваивание `b = a` **не копирует** список. Оно кладёт в `b` '
                'ссылку на тот же объект, и дальше `a` и `b` – два имени одной '
                'ленты.\n\n'
                'Проверить это можно двумя вопросами:\n\n'
                '| Запись | Что спрашивает |\n'
                '|---|---|\n'
                '| `a == b` | одинаковые ли значения |\n'
                '| `a is b` | один ли это объект |\n\n'
                'Два разных списка с одинаковыми числами дают `==` → `True`, а '
                '`is` → `False`.\n\n'
                '```python\n'
                'a = [1, 2, 3]\n'
                'b = a              # второе имя, а не копия\n'
                'b[0] = 99\n'
                'print(a)           # [99, 2, 3] – правка видна через оба имени\n'
                'print(a is b)      # True – объект один\n'
                '\n'
                'c = [1, 2, 3]\n'
                'd = [1, 2, 3]\n'
                'print(c == d)      # True – значения одинаковые\n'
                'print(c is d)      # False – а объекты разные\n'
                '```'
            )),
            dict(order=10, block_type='text', title='Копия списка', content=(
                'Настоящих копий три, и все дают независимый список:\n\n'
                '- `a[:]` – срез всей ленты;\n'
                '- `a.copy()` – метод списка;\n'
                '- `list(a)` – функция построения списка.\n\n'
                'Правки в копии исходный список не задевают. Оговорка: это '
                'копия **самой ленты**. Если внутри лежат другие списки, они '
                'останутся общими – тонкость разберём в уроке 9.3.\n\n'
                '```python\n'
                'a = [1, 2, 3]\n'
                'b = a[:]\n'
                'b[0] = 99\n'
                'print(a)          # [1, 2, 3] – исходный не изменился\n'
                'print(b)          # [99, 2, 3]\n'
                '\n'
                'print(a.copy())   # [1, 2, 3]\n'
                'print(list(a))    # [1, 2, 3]\n'
                '```'
            )),
            dict(order=11, block_type='text', title='Коротко', content=(
                '- **Список** – упорядоченная изменяемая последовательность; '
                'элементы могут быть разных типов, длина не фиксирована.\n'
                '- Индексы, отрицательные индексы, `len()` и срезы работают '
                'как у строки; срез списка даёт **новый список**.\n'
                '- Список **меняется на месте**, поэтому `a[i] = ...` работает, '
                'а у строки даёт `TypeError`.\n'
                '- `b = a` – второе имя, а не копия; копия – `a[:]`, '
                '`a.copy()` или `list(a)`.\n'
                '- `marks[5]` при пяти элементах даёт `IndexError`, а срез '
                '`marks[3:100]` – нет.\n'
                '- Менять элементы можно только по индексу: переменная цикла '
                '`m` к списку отношения не имеет.'
            )),
            dict(order=12, block_type='text', title='Что нас ждёт в этом блоке', content=(
                '| Урок | Тема | О чём |\n'
                '|---|---|---|\n'
                '| 9.1 | Списки | создание, индексы, срезы, изменяемость |\n'
                '| 9.2 | Методы и функции | `append`, `pop`, `sort`, `sum`, '
                '`max` |\n'
                '| 9.3 | Списочные выражения | короткая сборка списков и '
                'таблицы |\n'
                '| 9.4 | Кортежи | неизменяемые наборы и распаковка |\n'
                '| 9.5 | Множества | уникальные элементы и операции над ними |\n'
                '| 9.6 | Словари | пары «ключ – значение» и подсчёт частот |\n\n'
                'В конце блока – практикум: двадцать обязательных задач от '
                'простых к сложным. Кнопка задач есть в шапке блока.'
            )),
        ])

        quiz = _self_check(
            slug='self-check-b9-1-spiski',
            title='Самопроверка: списки',
            description='Пять коротких вопросов по теме урока.',
            questions=[
                dict(
                    type='text',
                    text=(
                        'Дан список `nums = [10, 20, 30, 40]`. Что напечатает '
                        '`print(nums[-2])`? Впишите только число.'
                    ),
                    correct_text_answer='30',
                ),
                dict(
                    type='choice',
                    text=(
                        'Выполнили `a = [1, 2, 3]`, затем `b = a`, затем '
                        '`b.append(5)`. Что теперь в `a`?'
                    ),
                    choices=[
                        ('[1, 2, 3, 5] – a и b это два имени одного списка', True),
                        ('[1, 2, 3] – b получил копию в момент присваивания', False),
                        ('[1, 2, 3, 5], но только если написать b = a[:]', False),
                        ('Ошибка: список, на который смотрят два имени, менять нельзя', False),
                    ],
                ),
                dict(
                    type='choice',
                    text=(
                        'Почему цикл `for x in nums: x = x * 2` не меняет '
                        'список `nums`?'
                    ),
                    choices=[
                        ('Присваивание меняет переменную x, а не клетку списка', True),
                        ('Умножение на 2 работает только с числами в print', False),
                        ('Цикл for не может работать со списками чисел', False),
                        ('Список меняется, но результат виден только после '
                         'второго прохода', False),
                    ],
                ),
                dict(
                    type='choice',
                    text=(
                        'Список `marks` содержит пять элементов. Что произойдёт '
                        'при `print(marks[5])`?'
                    ),
                    choices=[
                        ('IndexError: list index out of range', True),
                        ('Напечатается последний элемент', False),
                        ('Напечатается None', False),
                        ('Ничего: строка просто не выполнится', False),
                    ],
                ),
                dict(
                    type='choice',
                    text=(
                        "Выполнили `s = 'кот'`, затем `s[0] = 'р'`. Что "
                        'произойдёт?'
                    ),
                    choices=[
                        ("TypeError: строку нельзя менять по индексу", True),
                        ('Строка станет «рот»', False),
                        ('Появится новая строка, а s останется прежней', False),
                        ('IndexError: индекса 0 у строки нет', False),
                    ],
                ),
            ],
        )
        ArticleQuiz.objects.get_or_create(
            article=article, quiz=quiz,
            defaults={'label': 'Проверь себя', 'order': 1},
        )

    def seed_9_2(self):
        article = Article.objects.get(slug='9-2-metody-spiskov-i-vstroennye-funktsii')
        article.title = 'Методы списков и встроенные функции'
        article.description = (
            'Добавление и удаление элементов, поиск по значению, встроенные '
            'функции sum, min, max, sorted и разница между sort() и sorted().'
        )
        article.save(update_fields=['title', 'description'])

        _replace_blocks(article, [
            dict(order=1, block_type='text', title='О чём этот урок', content=(
                'Оценки за четверть пополняются: после каждой контрольной в '
                'список нужно дописать ещё одно число. Иногда оценку '
                'исправляют – старую надо убрать. К концу четверти нужны '
                'средний балл, лучшая оценка и список по возрастанию.\n\n'
                'Всё это делается готовыми операциями: часть из них – методы '
                'самого списка, часть – обычные функции вроде `sum()`.\n\n'
                '**В этом уроке:** `append()`, `extend()` и `insert()` – как '
                'дописывать; `pop()`, `remove()`, `del` и `clear()` – как '
                'удалять; `in`, `index()` и `count()` – как искать; почему '
                'методы списка возвращают `None`; `len()`, `sum()`, `min()`, '
                '`max()`, `sorted()`; чем `sort()` отличается от `sorted()`; '
                'как найти индекс максимума, если готовой функции для этого '
                'нет.'
            )),
            dict(order=2, block_type='text', title='Добавление элементов', content=(
                '> **`append(x)`** – дописывает **один** элемент `x` в конец '
                'списка. Длина становится на 1 больше, номера старых элементов '
                'не меняются.\n\n'
                'Три способа добавить различаются тем, сколько элементов '
                'добавляется и куда:\n\n'
                '| Метод | Что добавляет | Куда |\n'
                '|---|---|---|\n'
                '| `a.append(x)` | один элемент `x` | в конец |\n'
                '| `a.extend(seq)` | все элементы `seq` по очереди | в конец |\n'
                '| `a.insert(i, x)` | один элемент `x` | на позицию `i`, '
                'остальные сдвигаются вправо |\n\n'
                'Главная путаница – `append` против `extend`. '
                '`a.append([7, 8])` добавит **один** элемент, и этим элементом '
                'будет целый список. `a.extend([7, 8])` добавит **два** '
                'элемента.\n\n'
                '`insert()` меняет номера всех элементов правее точки вставки. '
                'Индекс за границей ошибки не даёт – значение прижимается к '
                'краю: `insert(100, x)` допишет в конец.\n\n'
                '```python\n'
                'marks = [5, 4]\n'
                'marks.append(3)          # [5, 4, 3]\n'
                'marks.extend([5, 4])     # [5, 4, 3, 5, 4]\n'
                "marks.insert(1, 2)       # [5, 2, 4, 3, 5, 4]\n"
                'print(marks)\n'
                '\n'
                'a = [1, 2]\n'
                'a.append([7, 8])\n'
                'print(a, len(a))         # [1, 2, [7, 8]] 3 – один элемент\n'
                '\n'
                'b = [1, 2]\n'
                'b.extend([7, 8])\n'
                'print(b, len(b))         # [1, 2, 7, 8] 4 – два элемента\n'
                '\n'
                "names = ['Аня', 'Вера']\n"
                "names.insert(1, 'Борис')\n"
                "print(names)             # ['Аня', 'Борис', 'Вера']\n"
                "names.insert(100, 'Яна')\n"
                "print(names[-1])         # Яна – слишком большой индекс\n"
                '                         # прижимается к концу\n'
                '```'
            )),
            dict(order=3, block_type='text', title='Методы меняют список и возвращают None', content=(
                'У строки метод не мог изменить объект – строка неизменяема, '
                'поэтому `s.upper()` **строит и возвращает новую строку**, и '
                'пишут `s = s.upper()`.\n\n'
                'Список меняется на месте, и возвращать методу нечего. Поэтому '
                '`append()`, `extend()`, `insert()`, `sort()`, `reverse()`, '
                '`clear()` всегда дают `None`.\n\n'
                '> **`None`** – значение «ничего»: так метод сообщает, что '
                'результата нет, потому что работа сделана прямо в списке.\n\n'
                'Ошибка, которую делают по одному разу: `a = a.append(5)`. '
                'Список пополнится, но в `a` тут же положат `None`, и имя '
                'списка потеряно. Следующая строка упадёт с `TypeError`.\n\n'
                'Правило: **у строки – `s = s.метод()`, у списка – просто '
                '`a.метод()` отдельной строкой.**\n\n'
                '```python\n'
                "s = 'привет'\n"
                'print(s.upper())     # ПРИВЕТ – вернулся новый объект\n'
                'print(s)             # привет – исходная не изменилась\n'
                '\n'
                'a = [1, 2, 3]\n'
                'print(a.append(4))   # None – возвращать нечего\n'
                'print(a)             # [1, 2, 3, 4] – но список изменился\n'
                '\n'
                'a = a.append(5)      # типичная ошибка\n'
                'print(a)             # None – имя списка потеряно\n'
                "print(len(a))        # TypeError: object of type 'NoneType'\n"
                '                     # has no len()\n'
                '```'
            )),
            dict(order=4, block_type='text', title='Удаление элементов', content=(
                'Выбор способа – это выбор того, что известно об удаляемом '
                'элементе:\n\n'
                '| Запись | Что удаляет | Что возвращает | Ошибка |\n'
                '|---|---|---|---|\n'
                '| `a.pop(i)` | элемент с индексом `i` | сам элемент | '
                '`IndexError`, если индекса нет |\n'
                '| `a.pop()` | последний элемент | сам элемент | `IndexError` '
                'на пустом списке |\n'
                '| `a.remove(x)` | **первое** совпадение с `x` | `None` | '
                '`ValueError`, если значения нет |\n'
                '| `del a[i]` | элемент с индексом `i` | ничего (оператор) | '
                '`IndexError` |\n'
                '| `a.clear()` | всё содержимое | `None` | нет |\n\n'
                '`pop()` – единственный метод списка, который возвращает '
                'удалённое значение: иначе оно пропало бы безвозвратно. '
                '`remove()` удаляет только первое совпадение, остальные такие '
                'же остаются.\n\n'
                '`clear()` опустошает **тот же** список, а `a = []` создаёт '
                'новый. Второе имя, если оно было, увидит разницу: после '
                '`clear()` – пустоту, после `a = []` – старый полный список.\n\n'
                '```python\n'
                'a = [10, 20, 30, 20]\n'
                '\n'
                'print(a.pop(0))   # 10 – pop отдаёт удалённое\n'
                'print(a)          # [20, 30, 20]\n'
                'print(a.pop())    # 20 – без аргумента последний\n'
                'print(a)          # [20, 30]\n'
                '\n'
                'a.remove(20)      # первое совпадение\n'
                'print(a)          # [30]\n'
                'a.remove(99)      # ValueError: list.remove(x): x not in list\n'
                '\n'
                'a = [10, 20, 30]\n'
                'del a[1]\n'
                'print(a)          # [10, 30]\n'
                'a.clear()\n'
                'print(a)          # []\n'
                '```'
            )),
            dict(order=5, block_type='text', title='Поиск: `in`, `index`, `count`', content=(
                '- `x in a` отвечает `True` или `False` и ничего не ищет внутри '
                'элементов;\n'
                '- `a.index(x)` возвращает номер **первого** совпадения, а если '
                'значения нет – останавливает программу с `ValueError`;\n'
                '- `a.count(x)` считает, сколько раз значение встретилось.\n\n'
                'Из-за `ValueError` у `index()` обычный порядок такой: сначала '
                'проверить `if x in a`, и только внутри условия звать '
                '`index()`.\n\n'
                'С `find()` у строки та же работа устроена иначе: там «не '
                'найдено» – это `-1`, а не ошибка. У списка такого значения '
                'нет, потому что `-1` – законный индекс.\n\n'
                '```python\n'
                'a = [10, 20, 30, 20]\n'
                'print(20 in a)      # True\n'
                'print(99 in a)      # False\n'
                'print(a.count(20))  # 2\n'
                'print(a.index(30))  # 2\n'
                '\n'
                'a.index(99)         # ValueError: 99 is not in list\n'
                '\n'
                'if 99 in a:         # сначала проверка, потом index\n'
                '    print(a.index(99))\n'
                '```'
            )),
            dict(
                order=6, block_type='widget',
                title='Что будет, если удалять прямо во время перебора',
                content=(
                    'Программа хочет убрать из списка все нули. Пройдите трассу '
                    'и следите за строкой «позиция»: список укорачивается '
                    'влево, счётчик растёт вправо, и один элемент '
                    'проскакивает мимо проверки.'
                ),
                widget_key='loop-trace',
                widget_config={
                    'code': REMOVE_CODE,
                    'vars': ['nums', 'позиция', 'x'],
                    'steps': _remove_trace(),
                },
            ),
            dict(order=7, block_type='text', title='Как удалять правильно', content=(
                'У цикла `for` есть внутренний счётчик позиции. После '
                '`remove()` все элементы справа сдвигаются влево, а счётчик всё '
                'равно растёт – и перескакивает через элемент, вставший на '
                'освободившееся место. Программа при этом не падает, просто '
                'делает не то, что имелось в виду.\n\n'
                'Правило: **пока по списку идёт цикл, длину списка менять '
                'нельзя.** Два надёжных выхода:\n\n'
                '- идти по копии, а менять оригинал: `for x in nums[:]`;\n'
                '- ничего не удалять, а собирать новый список через '
                '`append()`.\n\n'
                'Второй способ обычно понятнее, а в уроке 9.3 появится короткая '
                'запись для него.\n\n'
                '```python\n'
                '# так – неправильно\n'
                'nums = [1, 0, 0, 3]\n'
                'for x in nums:\n'
                '    if x == 0:\n'
                '        nums.remove(x)\n'
                'print(nums)     # [1, 0, 3] – один нуль уцелел\n'
                '\n'
                '# идём по копии, меняем оригинал\n'
                'nums = [1, 0, 0, 3]\n'
                'for x in nums[:]:\n'
                '    if x == 0:\n'
                '        nums.remove(x)\n'
                'print(nums)     # [1, 3]\n'
                '\n'
                '# или собираем новый список\n'
                'nums = [1, 0, 0, 3]\n'
                'result = []\n'
                'for x in nums:\n'
                '    if x != 0:\n'
                '        result.append(x)\n'
                'print(result)   # [1, 3]\n'
                '```'
            )),
            dict(order=8, block_type='text', title='Встроенные функции', content=(
                'Это не методы списка: их вызывают от имени функции, и они '
                'работают с любой последовательностью.\n\n'
                '| Функция | Что возвращает | Пример |\n'
                '|---|---|---|\n'
                '| `len(a)` | количество элементов | `3` |\n'
                '| `sum(a)` | сумму чисел | `12` |\n'
                '| `min(a)` | наименьший элемент | `3` |\n'
                '| `max(a)` | наибольший элемент | `5` |\n'
                '| `sorted(a)` | **новый** список по возрастанию | `[3, 4, 5]` |\n\n'
                'Среднее арифметическое готовой функции не имеет: это '
                '`sum(a) / len(a)`.\n\n'
                'На пустом списке обе крайности – ошибки: `max([])` даёт '
                '`ValueError`, а деление на `len([])` – `ZeroDivisionError`. '
                'Поэтому перед средним список проверяют на пустоту.\n\n'
                '```python\n'
                'a = [5, 4, 3]\n'
                'print(len(a))          # 3\n'
                'print(sum(a))          # 12\n'
                'print(min(a))          # 3\n'
                'print(max(a))          # 5\n'
                'print(sum(a) / len(a)) # 4.0\n'
                '\n'
                'print(sorted(a))       # [3, 4, 5] – новый список\n'
                'print(a)               # [5, 4, 3] – исходный не тронут\n'
                '\n'
                'print(max([]))         # ValueError: max() arg is an empty\n'
                '                       # sequence\n'
                'empty = []\n'
                'print(sum(empty) / len(empty))   # ZeroDivisionError\n'
                '\n'
                'if len(empty) > 0:     # а так – без ошибки\n'
                '    print(sum(empty) / len(empty))\n'
                '```'
            )),
            dict(order=9, block_type='text', title='`sort()` и `sorted()`', content=(
                'Сортируют одинаково, различаются двумя вещами:\n\n'
                '| | `sorted(a)` | `a.sort()` |\n'
                '|---|---|---|\n'
                '| Что делает | строит **новый** список | перестраивает сам '
                'список |\n'
                '| Что возвращает | новый список | `None` |\n'
                '| Нужно ли присваивание | да, если результат нужен | нет |\n\n'
                'Оба умеют `reverse=True` – по убыванию. Это параметр, а не '
                'функция: `a.sort(reverse=True)` пишется прямо в скобках.\n\n'
                'Сортировать можно только однотипные значения: '
                "`sorted([3, 'a'])` даёт `TypeError` – число со строкой не "
                'сравнить.\n\n'
                'Развернуть список можно и без сортировки: `a.reverse()` '
                'переставляет элементы на месте, а `a[::-1]` даёт развёрнутую '
                'копию и исходный список не трогает.\n\n'
                '```python\n'
                'a = [3, 1, 2]\n'
                'print(sorted(a))         # [1, 2, 3]\n'
                'print(a)                 # [3, 1, 2] – функция не тронула\n'
                '\n'
                'a.sort()\n'
                'print(a)                 # [1, 2, 3] – метод перестроил сам\n'
                'print(a.sort())          # None\n'
                '\n'
                'a.sort(reverse=True)\n'
                'print(a)                 # [3, 2, 1]\n'
                '\n'
                'a.reverse()\n'
                'print(a)                 # [1, 2, 3] – на месте\n'
                'print(a[::-1])           # [3, 2, 1] – копия, a не изменился\n'
                '```'
            )),
            dict(
                order=10, block_type='widget',
                title='Что возвращает sort()',
                content=(
                    'Пройдите трассу и сравните два действия: sorted() отдала '
                    'новый список, а sort() перестроила старый и вернула None.'
                ),
                widget_key='loop-trace',
                widget_config={
                    'code': SORT_CODE,
                    'vars': ['a', 'b'],
                    'steps': _sort_trace(),
                },
            ),
            dict(order=11, block_type='text', title='Когда встроенной функции нет: поиск циклом', content=(
                '`max()` отдаёт наибольшее значение, но не его номер. Если '
                'нужен индекс максимума, пишут цикл: запоминают лучший индекс '
                'и сравнивают с ним каждый следующий элемент.\n\n'
                'Строгое `>` оставляет **первый** максимум: равный следующий '
                'элемент условие не проходит. Нужен последний – ставят `>=`.\n\n'
                'Вторая задача – все позиции максимума. Здесь сначала узнают '
                'само значение через `max()`, а потом перебирают индексы и '
                'печатают подходящие.\n\n'
                'Третья – первый подходящий элемент. Его ищут с `break`: как '
                'только нашли, дальше смотреть незачем. Признак «не нашли» – '
                '`None`: число тут не годится, у списка законны и '
                'отрицательные индексы.\n\n'
                '```python\n'
                '# индекс максимума: строгое > оставляет первый\n'
                'a = [5, 4, 3, 5, 4]\n'
                'best = 0\n'
                'for i in range(1, len(a)):\n'
                '    if a[i] > a[best]:\n'
                '        best = i\n'
                'print(best, a[best])     # 0 5\n'
                '\n'
                '# все позиции максимума\n'
                'best = max(a)\n'
                'for i in range(len(a)):\n'
                '    if a[i] == best:\n'
                "        print(i, end=' ')    # 0 3\n"
                'print()\n'
                '\n'
                '# первый отрицательный: break плюс флаг «не нашли»\n'
                'temps = [3, 5, -1, 4]\n'
                'found = None                 # пока не нашли\n'
                'for i in range(len(temps)):\n'
                '    if temps[i] < 0:\n'
                '        found = i\n'
                '        break\n'
                'if found is None:\n'
                '    print(\'отрицательных нет\')\n'
                'else:\n'
                '    print(found)             # 2\n'
                '```'
            )),
            dict(order=12, block_type='text', title='Коротко', content=(
                '- Добавляют `append(x)`, `extend(seq)` и `insert(i, x)`; '
                'удаляют `pop()`, `remove(x)`, `del a[i]`, `clear()`.\n'
                '- Методы списка меняют его **на месте** и возвращают `None`; '
                '`pop()` – исключение, он отдаёт удалённый элемент.\n'
                '- `remove()` убирает только первое совпадение; удалять из '
                'списка во время цикла по нему нельзя – перебирайте `nums[:]` '
                'или собирайте новый список.\n'
                '- `sorted(a)` возвращает новый список, `a.sort()` меняет сам '
                'список и возвращает `None`.\n'
                '- `max([])` – `ValueError`, деление на `len([])` – '
                '`ZeroDivisionError`.\n'
                '- Индекс максимума встроенная функция не отдаёт – его ищут '
                'циклом.'
            )),
        ])

        quiz = _self_check(
            slug='self-check-b9-2-metody',
            title='Самопроверка: методы списков и функции',
            description='Пять коротких вопросов по теме урока.',
            questions=[
                dict(
                    type='text',
                    text=(
                        'Что напечатает эта программа?\n\n'
                        '```python\n'
                        'a = [3, 1, 2]\n'
                        'b = a.sort()\n'
                        'print(b)\n'
                        '```'
                    ),
                    correct_text_answer='None',
                ),
                dict(
                    type='text',
                    text=(
                        'Что напечатает эта программа?\n\n'
                        '```python\n'
                        'nums = [1, 0, 0, 3]\n'
                        'for x in nums:\n'
                        '    if x == 0:\n'
                        '        nums.remove(x)\n'
                        'print(nums)\n'
                        '```'
                    ),
                    correct_text_answer='[1, 0, 3]',
                    alternative_answers=['[1,0,3]'],
                ),
                dict(
                    type='choice',
                    text='Сколько элементов удалит вызов `a.remove(x)`?',
                    choices=[
                        ('Только первое совпадение слева', True),
                        ('Все совпадения с x', False),
                        ('Последнее совпадение', False),
                        ('Ни одного, если x встречается больше одного раза', False),
                    ],
                ),
                dict(
                    type='choice',
                    text='Что произойдёт при `print(max([]))`?',
                    choices=[
                        ('ValueError: у пустой последовательности нет максимума', True),
                        ('Напечатается 0', False),
                        ('Напечатается None', False),
                        ('Напечатается пустой список', False),
                    ],
                ),
                dict(
                    type='choice',
                    text=(
                        'После какой операции изменился сам список `a`?'
                    ),
                    choices=[
                        ('После `a.sort()`', True),
                        ('После `sorted(a)`', False),
                        ('После `a[::-1]`', False),
                        ('После `list(a)`', False),
                    ],
                ),
            ],
        )
        ArticleQuiz.objects.get_or_create(
            article=article, quiz=quiz,
            defaults={'label': 'Проверь себя', 'order': 1},
        )

    def seed_9_3(self):
        article = Article.objects.get(slug='9-3-spisochnye-vyrazheniya-i-vlozhennye-spiski')
        article.title = 'Списочные выражения и вложенные списки'
        article.description = (
            'Короткая сборка списков одним выражением, отбор и замена значений, '
            'таблицы как списки списков и правильное копирование таблицы.'
        )
        article.save(update_fields=['title', 'description'])

        _replace_blocks(article, [
            dict(order=1, block_type='text', title='О чём этот урок', content=(
                'Схема «пустой список, потом `append()` в цикле» встречается в '
                'каждой второй задаче: квадраты чисел, чётные элементы, слова '
                'из ввода. Для неё есть короткая запись в одну строку.\n\n'
                'Отдельная тема – журнал класса: строка на ученика, столбец на '
                'контрольную. Это список, элементами которого служат другие '
                'списки, и работать с ним нужно иначе, чем с плоской лентой.\n\n'
                '**В этом уроке:** списочное выражение и его эквивалент с '
                'циклом; отбор через `if` в конце и выбор значения через '
                '`if-else` в начале; когда лучше оставить обычный цикл; '
                'вложенные списки и обращение `journal[i][j]`; обход таблицы и '
                'суммы по строкам и столбцам; создание таблицы нужного размера '
                'и ловушка `[[0] * m] * n`; поверхностная и глубокая копия.'
            )),
            dict(order=2, block_type='text', title='Списочное выражение', content=(
                '> **Списочное выражение** – запись, которая строит новый '
                'список из элементов другого набора: `[выражение for x in '
                'последовательность]`. Читается «собрать выражение для каждого '
                '`x` из последовательности».\n\n'
                '```python\n'
                'squares = []\n'
                'for x in range(5):\n'
                '    squares.append(x * x)\n'
                '```\n\n'
                'Эти три строки и `[x * x for x in range(5)]` дают один и тот '
                'же список `[0, 1, 4, 9, 16]`. Переменная `x` живёт только '
                'внутри выражения – наружу она не выходит.\n\n'
                'Отсюда короткое чтение чисел, о котором шла речь в уроке 9.1: '
                '`nums = [int(s) for s in input().split()]` сразу даёт список '
                'чисел, без промежуточного `parts`.\n\n'
                '```python\n'
                'print([x * x for x in range(5)])   # [0, 1, 4, 9, 16]\n'
                '\n'
                'nums = [int(s) for s in input().split()]   # 4 8 15\n'
                'print(nums)                        # [4, 8, 15]\n'
                '\n'
                "words = ['кот', 'дом', 'лес']\n"
                'print([len(w) for w in words])     # [3, 3, 3]\n'
                'print([w.upper() for w in words])  # [\'КОТ\', \'ДОМ\', \'ЛЕС\']\n'
                '```'
            )),
            dict(order=3, block_type='text', title='Отбор и выбор значения', content=(
                '`if` в списочном выражении может стоять в двух местах, и '
                'делает он разное:\n\n'
                '| Запись | Что делает | Результат для `a = [3, -8, 5]` |\n'
                '|---|---|---|\n'
                '| `[x for x in a if x > 0]` | **отбирает**: неподходящие '
                'элементы в результат не попадают | `[3, 5]` |\n'
                '| `[x if x > 0 else 0 for x in a]` | **выбирает значение** для '
                'каждого элемента; число элементов не меняется | `[3, 0, 5]` |\n\n'
                'Разница видна по результату: в первом случае список короче '
                'исходного, во втором – такой же длины. В первом `if` стоит в '
                'конце и работает как фильтр, во втором – в начале и требует '
                '`else`.\n\n'
                '```python\n'
                'a = [3, -8, 5, -2, 7]\n'
                '\n'
                'print([x for x in a if x > 0])         # [3, 5, 7] – отбор\n'
                'print([x if x > 0 else 0 for x in a])  # [3, 0, 5, 0, 7]\n'
                '\n'
                '# отбор и замена одновременно: отрицательные заменяем нулём\n'
                'print([x if x > 0 else 0 for x in a if x != 5])\n'
                '# [3, 0, 0, 7] – пять выброшено, остальные заменены\n'
                '```'
            )),
            dict(order=4, block_type='text', title='Когда лучше обычный цикл', content=(
                'Списочное выражение – инструмент для **одной простой '
                'операции** над каждым элементом. Если внутри нужно несколько '
                'действий, вложенное условие, `break` или накопление другого '
                'рода (сумма, счётчик, строка), обычный цикл остаётся '
                'понятнее. Вложенное выражение из трёх условий читать тяжело, '
                'а развернуть его в цикл – минута работы.'
            )),
            dict(order=5, block_type='text', title='Вложенный список', content=(
                '> **Вложенный список** – список, элементами которого служат '
                'другие списки. Двойная индексация `a[i][j]` означает: взять '
                '`i`-й элемент внешнего списка (строку), а из него – `j`-й '
                'элемент.\n\n'
                'Журнал класса – четыре строки по три оценки:\n\n'
                '| Ученик | Контрольная 1 | Контрольная 2 | Контрольная 3 |\n'
                '|---|---|---|---|\n'
                '| Аня | 5 | 4 | 3 |\n'
                '| Борис | 3 | 3 | 4 |\n'
                '| Вера | 5 | 5 | 5 |\n'
                '| Глеб | 4 | 2 | 3 |\n\n'
                '`len(journal)` – число **строк**, `len(journal[0])` – число '
                '**столбцов**. Второе работает, только если строки одинаковой '
                'длины; берут длину первой из них.\n\n'
                '```python\n'
                'journal = [[5, 4, 3], [3, 3, 4], [5, 5, 5], [4, 2, 3]]\n'
                "names = ['Аня', 'Борис', 'Вера', 'Глеб']\n"
                '\n'
                'print(len(journal))     # 4 – строк\n'
                'print(len(journal[0]))  # 3 – столбцов\n'
                '\n'
                'print(journal[1])       # [3, 3, 4] – вторая строка целиком\n'
                'print(journal[1][2])    # 4 – Борис, третья контрольная\n'
                'print(names[1])         # Борис\n'
                '\n'
                'journal[0][0] = 4       # исправили оценку Ани\n'
                'print(journal[0])       # [4, 4, 3]\n'
                '```'
            )),
            dict(order=6, block_type='text', title='Обход таблицы', content=(
                'Таблицу обходят вложенными циклами: внешний перебирает строки, '
                'внутренний – элементы внутри строки. Тело внутреннего цикла '
                'выполняется столько раз, сколько клеток в таблице.\n\n'
                'Сумма строки – просто `sum(row)`. Сумма столбца требует цикла: '
                'столбцы в списке не хранятся отдельно, их приходится собирать '
                'из разных строк – `journal[i][j]` при постоянном `j`.\n\n'
                'Напечатать строку через пробел можно `print(*row)`: '
                'звёздочка раскладывает её в аргументы, как и у плоского '
                'списка.\n\n'
                '```python\n'
                'total = 0\n'
                'for row in journal:          # row – очередная строка\n'
                '    total = total + sum(row)\n'
                'print(total)                 # 46 – сумма всех оценок\n'
                '\n'
                'for i in range(len(journal)):\n'
                '    print(names[i], sum(journal[i]) / len(journal[i]))\n'
                '# Аня 4.0 / Борис 3.3333... / Вера 5.0 / Глеб 3.0\n'
                '\n'
                '# сумма столбца: внешний цикл – по столбцам, внутренний – по строкам\n'
                'for j in range(len(journal[0])):\n'
                '    s = 0\n'
                '    for i in range(len(journal)):\n'
                '        s = s + journal[i][j]\n'
                '    print(s)                 # 17 14 15\n'
                '\n'
                'for row in journal:\n'
                '    print(*row)              # 5 4 3, затем 3 3 4 и так далее\n'
                '```'
            )),
            dict(
                order=7, block_type='widget',
                title='Обход таблицы вложенными циклами',
                content=(
                    'Пройдите трассу и проследите, как внутренний цикл '
                    'прокручивается целиком на каждый шаг внешнего, а total '
                    'растёт на каждой клетке.'
                ),
                widget_key='loop-trace',
                widget_config={
                    'code': MATRIX_CODE,
                    'vars': ['journal', 'i', 'j', 'journal[i][j]', 'total'],
                    'steps': _matrix_trace(),
                },
            ),
            dict(order=8, block_type='text', title='Таблица нужного размера', content=(
                'Таблицу из нулей строят списочным выражением: '
                '`[[0] * m for _ in range(n)]` – `n` отдельных строк, в каждой '
                '`m` нулей. Имя `_` здесь означает, что переменная цикла не '
                'нужна: строки одинаковые, номер не используется.\n\n'
                'А вот запись `[[0] * m] * n` создаёт **одну** строку и `n` '
                'ссылок на неё. Внешний список из `n` элементов, но все они – '
                'один и тот же объект. Правка одной клетки меняет весь столбец '
                'во всех строках сразу.\n\n'
                'Это та же ошибка из урока 9.1 (`b = a` вместо копии), '
                'только спрятанная в умножение.\n\n'
                '```python\n'
                'n, m = 3, 4\n'
                '\n'
                'table = [[0] * m for _ in range(n)]   # три разных строки\n'
                'table[0][0] = 1\n'
                'print(table)\n'
                '# [[1, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]]\n'
                '\n'
                'bad = [[0] * m] * n                   # одна строка, n ссылок\n'
                'bad[0][0] = 1\n'
                'print(bad)\n'
                '# [[1, 0, 0, 0], [1, 0, 0, 0], [1, 0, 0, 0]] – весь столбец\n'
                '```'
            )),
            dict(order=9, block_type='text', title='Копия таблицы', content=(
                '`a.copy()` и срез `a[:]` копируют **только внешний список**. '
                'Строки внутри остаются общими: копия – новая лента, в которой '
                'лежат ссылки на те же самые строки. Правка `b[0][0]` поэтому '
                'видна и в `a`.\n\n'
                '> **Глубокая копия** – копия, в которой скопированы и все '
                'вложенные объекты. Делается функцией `deepcopy()` из модуля '
                '`copy`.\n\n'
                'Нужна она там, где таблицу правят, а исходное состояние должно '
                'сохраниться: снимок поля для отмены хода, резервная копия '
                'журнала перед исправлением оценок.\n\n'
                'Для плоского списка чисел хватает `copy()`: копировать там '
                'нечего, кроме самой ленты.\n\n'
                '```python\n'
                'from copy import deepcopy\n'
                '\n'
                'a = [[1, 2], [3, 4]]\n'
                '\n'
                'b = a.copy()          # новый внешний список, строки общие\n'
                'b[0][0] = 99\n'
                'print(a)              # [[99, 2], [3, 4]] – правка видна в a\n'
                'print(b)              # [[99, 2], [3, 4]]\n'
                '\n'
                'a = [[1, 2], [3, 4]]\n'
                'c = deepcopy(a)       # скопировано всё\n'
                'c[0][0] = 99\n'
                'print(a)              # [[1, 2], [3, 4]] – a не тронута\n'
                'print(c)              # [[99, 2], [3, 4]]\n'
                '```'
            )),
            dict(
                order=10, block_type='widget',
                title='Второе имя против глубокой копии',
                content=(
                    'Пройдите трассу и сравните проверки is: у второго имени '
                    'они True после любой правки, у deepcopy – False, потому '
                    'что общих объектов не осталось.'
                ),
                widget_key='loop-trace',
                widget_config={
                    'code': COPY_CODE,
                    'vars': [
                        'journal', 'backup',
                        'backup is journal', 'backup[0] is journal[0]',
                    ],
                    'steps': _copy_trace(),
                },
            ),
            dict(order=11, block_type='text', title='Коротко', content=(
                '- **Списочное выражение** `[выражение for x in a]` заменяет '
                'цикл «пустой список + `append()`».\n'
                '- `if` в конце **отбирает** элементы, `if-else` в начале '
                '**выбирает значение** – длина результата разная.\n'
                '- **Вложенный список** – таблица: `a[i][j]` – строка `i`, '
                'столбец `j`; `len(a)` – строки, `len(a[0])` – столбцы.\n'
                '- Таблицу создают `[[0] * m for _ in range(n)]`, а не '
                '`[[0] * m] * n` – второе даёт `n` ссылок на одну строку.\n'
                '- `copy()` и `a[:]` копируют только внешний список; '
                '`deepcopy()` копирует и строки.'
            )),
        ])

        quiz = _self_check(
            slug='self-check-b9-3-vyrazheniya',
            title='Самопроверка: списочные выражения и таблицы',
            description='Пять коротких вопросов по теме урока.',
            questions=[
                dict(
                    type='text',
                    text=(
                        'Что напечатает `print([x * 2 for x in [1, 2, 3] '
                        'if x != 2])`?'
                    ),
                    correct_text_answer='[2, 6]',
                    alternative_answers=['[2,6]'],
                ),
                dict(
                    type='text',
                    text=(
                        'Что напечатает эта программа?\n\n'
                        '```python\n'
                        't = [[0] * 2] * 2\n'
                        't[0][0] = 1\n'
                        'print(t)\n'
                        '```'
                    ),
                    correct_text_answer='[[1, 0], [1, 0]]',
                    alternative_answers=['[[1,0],[1,0]]'],
                ),
                dict(
                    type='choice',
                    text=(
                        'Журнал хранится списком списков: каждый внутренний '
                        'список – один ученик, а числа в нём – его оценки за '
                        'контрольные по порядку. Первый индекс выбирает '
                        'ученика (строку), второй – контрольную (столбец).\n\n'
                        '```python\n'
                        'journal = [\n'
                        '    [5, 4, 3],   # первый ученик: 1-я, 2-я, 3-я контрольная\n'
                        '    [3, 3, 4],   # второй ученик\n'
                        '    [5, 5, 5],   # третий ученик\n'
                        ']\n'
                        '```\n\n'
                        'Индексы считаются с нуля: `journal[0]` – первый '
                        'ученик, `journal[0][0]` – его первая контрольная. Что '
                        'достаёт выражение `journal[1][2]`?'
                    ),
                    choices=[
                        ('Второго ученика, третью контрольную', True),
                        ('Первого ученика, вторую контрольную', False),
                        ('Третьего ученика, вторую контрольную', False),
                        ('Третью контрольную второго и третьего учеников', False),
                    ],
                ),
                dict(
                    type='choice',
                    text=(
                        'Таблица `a` – оценки двух учеников за две контрольные. '
                        'Её скопировали в `b` и в копии исправили первую '
                        'оценку первого ученика. Оригинал `a` при этом никто '
                        'не трогал.\n\n'
                        '```python\n'
                        'a = [[5, 4], [3, 3]]\n'
                        'b = a.copy()\n'
                        'b[0][0] = 2\n'
                        'print(a)\n'
                        '```\n\n'
                        'Что напечатает программа?'
                    ),
                    choices=[
                        ('[[2, 4], [3, 3]] – copy() скопировал только внешний '
                         'список, строки у a и b общие', True),
                        ('[[5, 4], [3, 3]] – правили копию, оригинал не '
                         'изменился', False),
                        ('[[2, 4], [2, 3]] – изменился весь первый столбец', False),
                        ('Ошибка: копировать таблицу через copy() нельзя', False),
                    ],
                ),
                dict(
                    type='choice',
                    text='Как узнать число столбцов в таблице `journal`?',
                    choices=[
                        ('len(journal[0])', True),
                        ('len(journal)', False),
                        ('sum(journal)', False),
                        ('journal[0]', False),
                    ],
                ),
            ],
        )
        ArticleQuiz.objects.get_or_create(
            article=article, quiz=quiz,
            defaults={'label': 'Проверь себя', 'order': 1},
        )

    def seed_9_4(self):
        article = Article.objects.get(slug='9-4-kortezhi')
        article.title = 'Кортежи'
        article.description = (
            'Неизменяемые наборы значений: создание, доступ по индексу, '
            'распаковка, enumerate и zip, сравнение кортежей по элементам.'
        )
        article.save(update_fields=['title', 'description'])

        _replace_blocks(article, [
            dict(order=1, block_type='text', title='О чём этот урок', content=(
                'Координата точки – пара чисел `(3, 4)`. Дата – тройка '
                '`(2026, 11, 15)`. Обе величины состоят из нескольких значений, '
                'которые логически неделимы: отдельно «тройка» и отдельно '
                '«четыре» смысла не имеют. И обе не должны меняться: если '
                'точка задана, координаты – часть её условия, а не поле для '
                'правок.\n\n'
                'Список для такого не годится: он разрешает менять элементы, а '
                'для этих величин любая правка – уже другая точка и другая '
                'дата.\n\n'
                '**В этом уроке:** как записывается кортеж и чем `(5,)` '
                'отличается от `(5)`; что кортеж умеет и чего не умеет; '
                'распаковка `x, y = point` и обмен значений; `enumerate()` и '
                '`zip()` – перебор с номерами и парами; сравнение кортежей по '
                'элементам и сортировка по нескольким признакам.'
            )),
            dict(order=2, block_type='text', title='Кортеж', content=(
                '> **Кортеж** (`tuple`) – упорядоченный **неизменяемый** набор '
                'значений. Записывается круглыми скобками, элементы разделяются '
                'запятыми.\n\n'
                'Скобки необязательны: `3, 4` – тот же кортеж, что `(3, 4)`. '
                'А вот запятая обязательна всегда, и из-за этого возникает '
                'главная ловушка записи: `(5)` – это просто число в скобках, '
                'а кортеж из одного элемента – `(5,)`.\n\n'
                'Пустой кортеж – `()`. Готовый кортеж получают из списка '
                'функцией `tuple()`, а обратно – `list()`.\n\n'
                'Как и список, кортеж упорядочен: элементы стоят в том порядке, '
                'в каком записаны, и доступны по индексу.\n\n'
                '```python\n'
                'point = (3, 4)\n'
                'print(point)          # (3, 4)\n'
                '\n'
                'pair = 3, 4           # скобки можно не писать\n'
                'print(pair)           # (3, 4)\n'
                '\n'
                'print((5,))           # (5,) – кортеж из одного элемента\n'
                'print((5))            # 5 – это просто число\n'
                "print(type((5,)))     # <class 'tuple'>\n"
                "print(type((5)))      # <class 'int'>\n"
                '\n'
                'print(tuple([1, 2]))  # (1, 2)\n'
                'print(tuple())        # ()\n'
                'print(list((1, 2)))   # [1, 2] – обратно в список\n'
                '```'
            )),
            dict(order=3, block_type='text', title='Что кортеж умеет и чего нет', content=(
                'Кортеж – последовательность, поэтому всё «читающее» у него '
                'такое же, как у списка. А всё, что меняет длину или '
                'содержимое, – запрещено.\n\n'
                '| Действие | Кортеж |\n'
                '|---|---|\n'
                '| `t[0]`, `t[-1]`, срезы, `len(t)` | работает |\n'
                '| `x in t`, `t.count(x)`, `t.index(x)` | работает |\n'
                '| `t1 + t2`, `t * n` | работает, даёт **новый** кортеж |\n'
                '| `t[0] = 5` | `TypeError` |\n'
                '| `t.append(x)`, `t.remove(x)`, `t.sort()` | таких методов '
                'нет – `AttributeError` |\n\n'
                'Причина одна: кортеж неизменяем. Всё, что «меняло бы» его, '
                'для него не определено. `+` и `*` при этом работают, потому '
                'что, как и у строк, создают новый объект, а исходный не '
                'трогают.'
            )),
            dict(order=4, block_type='text', title='Распаковка', content=(
                '> **Распаковка** – присваивание, в котором элементам кортежа '
                'сразу дают отдельные имена: `x, y = point`.\n\n'
                'Число имён должно совпасть с числом элементов, иначе '
                '`ValueError`. Исключение – звёздочка: `first, *rest = t` '
                'забирает первый элемент, а остальные собирает в список `rest`.\n\n'
                'Отсюда короткий обмен значений: `a, b = b, a`. Справа '
                'складывается кортеж `(b, a)`, и он распаковывается обратно в '
                '`a` и `b`. Временная переменная не нужна.\n\n'
                'Распаковка понадобится сразу ниже: `enumerate()` и '
                '`zip()` отдают пары именно для того, чтобы их сразу разложили '
                'по именам.\n\n'
                '```python\n'
                'point = (3, 4)\n'
                'x, y = point\n'
                'print(x, y)            # 3 4\n'
                '\n'
                'a, b = 1, 2\n'
                'a, b = b, a\n'
                'print(a, b)            # 2 1 – обмен без третьей переменной\n'
                '\n'
                'first, *rest = (1, 2, 3, 4)\n'
                'print(first)           # 1\n'
                'print(rest)            # [2, 3, 4] – звёздочка собрала список\n'
                '\n'
                'x, y = (1, 2, 3)       # ValueError: too many values to unpack\n'
                '```'
            )),
            dict(order=5, block_type='text', title='`enumerate` и `zip`', content=(
                'Обе функции знакомят цикл сразу с двумя значениями:\n\n'
                '| Функция | Что отдаёт на каждом шаге |\n'
                '|---|---|\n'
                '| `enumerate(a)` | пару `(индекс, элемент)` |\n'
                '| `zip(a, b)` | пару `(элемент a, элемент b)` с одинаковым '
                'номером |\n\n'
                '`enumerate()` избавляет от `for i in range(len(a))` там, где '
                'нужны и номер, и значение. `zip()` идёт по двум '
                'последовательностям одновременно и останавливается на '
                'короткой.\n\n'
                'Обе отдают пары, поэтому в заголовке цикла их распаковывают: '
                '`for i, x in enumerate(a)` и `for name, mark in zip(names, '
                'marks)`.\n\n'
                '```python\n'
                "names = ['Аня', 'Борис', 'Вера']\n"
                'marks = [5, 4, 3]\n'
                '\n'
                'for i, x in enumerate(marks):\n'
                '    print(i, names[i], x)   # 0 Аня 5, 1 Борис 4, 2 Вера 3\n'
                '\n'
                'for name, mark in zip(names, marks):\n'
                '    print(name, mark)       # Аня 5, Борис 4, Вера 3\n'
                '\n'
                '# enumerate по строкам с номерами, начиная с единицы\n'
                'for i, name in enumerate(names, 1):\n'
                '    print(i, name)          # 1 Аня, 2 Борис, 3 Вера\n'
                '```'
            )),
            dict(order=6, block_type='text', title='Сравнение кортежей', content=(
                'Кортежи сравниваются **поэлементно слева направо**, как слова '
                'в словаре: сначала первые элементы, при равенстве – вторые, и '
                'так до первого различия. Если один кортеж является началом '
                'другого, короткий считается меньшим.\n\n'
                'Отсюда сортировка дат, записанных как `(год, месяц, день)`: '
                '`sorted()` упорядочит их по году, при равном годе – по месяцу, '
                'при равном месяце – по дню. Отдельного правила для дат не '
                'нужно, порядок элементов в кортеже и есть правило.\n\n'
                '```python\n'
                'print((1, 2) < (1, 3))    # True – решили вторые элементы\n'
                'print((1, 2) < (2, 0))    # True – первый уже разный\n'
                'print((1, 2) < (1, 2, 0)) # True – короткий меньше\n'
                '\n'
                'dates = [(2024, 5, 3), (2023, 12, 1), (2024, 1, 15)]\n'
                'print(sorted(dates))\n'
                '# [(2023, 12, 1), (2024, 1, 15), (2024, 5, 3)]\n'
                '```'
            )),
            dict(order=7, block_type='text', title='Сортировка по двум признакам', content=(
                'Часто нужно «по убыванию первого, при равенстве – по '
                'возрастанию второго». Приём: в кортеж кладут '
                '**отрицательное** число вместо самого значения. Возрастающая '
                'сортировка по `-числу` даёт убывание по числу, а второй '
                'элемент остаётся возрастающим. Потом знак возвращают при '
                'выводе.\n\n'
                '```python\n'
                "goods = [('ручка', 45), ('тетрадь', 120), ('ластик', 45)]\n"
                'pairs = [(-price, name) for name, price in goods]\n'
                'for price, name in sorted(pairs):\n'
                '    print(name, -price)\n'
                '# тетрадь 120, ластик 45, ручка 45 – дорогие впереди,\n'
                '# а при равной цене – по алфавиту\n'
                '```'
            )),
            dict(order=8, block_type='text', title='Зачем кортеж, если есть список', content=(
                'Разница ровно одна – неизменяемость, но следствий у неё два.\n\n'
                'Первое: кортеж **нельзя испортить случайно**. Никакая часть '
                'программы не переставит в нём элементы и не допишет '
                'лишний. Для координат, дат и настроек это защита, а не '
                'ограничение.\n\n'
                'Второе, техническое: кортеж может быть **элементом множества '
                'и ключом словаря**, а список – нет. Причина в том, что '
                'множества и словари вычисляют место элемента по его значению, '
                'а значение изменяемого объекта может поменяться, пока он лежит '
                'внутри. Подробно это разберём в уроках 9.5 и 9.6.\n\n'
                'Практическое правило: набор значений, который задаёт объект и '
                'не меняется, – кортеж; набор, который пополняется и '
                'правится, – список.'
            )),
            dict(order=9, block_type='text', title='Коротко', content=(
                '- **Кортеж** – упорядоченный неизменяемый набор; `(5,)` – '
                'кортеж из одного элемента, `(5)` – число.\n'
                '- Индексы, срезы, `len`, `in`, `count`, `index`, `+` и `*` '
                'работают; присваивание элемента и методы `append`/`remove` – '
                'нет.\n'
                '- **Распаковка** `x, y = point` требует совпадения числа имён; '
                '`a, b = b, a` меняет значения местами.\n'
                '- `enumerate(a)` даёт пары «индекс, элемент», `zip(a, b)` – '
                'пары элементов с одинаковым номером.\n'
                '- Кортежи сравниваются поэлементно слева направо – поэтому '
                'сортировка по `(год, месяц, день)` уже упорядочивает даты.\n'
                '- Кортеж годится в ключи словаря и элементы множества, список '
                '– нет.'
            )),
        ])

        quiz = _self_check(
            slug='self-check-b9-4-kortezhi',
            title='Самопроверка: кортежи',
            description='Пять коротких вопросов по теме урока.',
            questions=[
                dict(
                    type='choice',
                    text='Что вернёт `type((5))` и `type((5,))`?',
                    choices=[
                        ('int и tuple', True),
                        ('tuple и tuple', False),
                        ('tuple и int', False),
                        ('int и int', False),
                    ],
                ),
                dict(
                    type='text',
                    text=(
                        'Что напечатает эта программа?\n\n'
                        '```python\n'
                        'a, b = 1, 2\n'
                        'a, b = b, a\n'
                        'print(a, b)\n'
                        '```'
                    ),
                    correct_text_answer='2 1',
                    alternative_answers=['2,1'],
                ),
                dict(
                    type='choice',
                    text=(
                        'Выполнили `t = (1, 2)`, затем `t[0] = 5`. Что '
                        'произойдёт?'
                    ),
                    choices=[
                        ('TypeError: кортеж не поддерживает присваивание по индексу', True),
                        ('Первый элемент станет равен 5', False),
                        ('Появится новый кортеж (5, 2)', False),
                        ('Ошибка будет только при выводе t', False),
                    ],
                ),
                dict(
                    type='text',
                    text=(
                        'Что напечатает '
                        "`print(sorted([(2, 'б'), (1, 'в'), (2, 'а')]))`?"
                    ),
                    correct_text_answer="[(1, 'в'), (2, 'а'), (2, 'б')]",
                    alternative_answers=[
                        "[(1,'в'),(2,'а'),(2,'б')]",
                        '[(1, "в"), (2, "а"), (2, "б")]',
                    ],
                ),
                dict(
                    type='choice',
                    text=(
                        'Координаты клетки поля будут ключом словаря. Какой тип '
                        'для них выбрать?'
                    ),
                    choices=[
                        ('Кортеж (x, y) – он неизменяем и годится в ключи', True),
                        ('Список [x, y] – с ним удобнее работать', False),
                        ('Строку «xy» – так короче', False),
                        ('Множество {x, y} – координаты не повторяются', False),
                    ],
                ),
            ],
        )
        ArticleQuiz.objects.get_or_create(
            article=article, quiz=quiz,
            defaults={'label': 'Проверь себя', 'order': 1},
        )

    def seed_9_5(self):
        article = Article.objects.get(slug='9-5-mnozhestva')
        article.title = 'Множества'
        article.description = (
            'Неупорядоченный набор без повторов: добавление и удаление, '
            'проверка вхождения, объединение и пересечение, приём «уже видели».'
        )
        article.save(update_fields=['title', 'description'])

        _replace_blocks(article, [
            dict(order=1, block_type='text', title='О чём этот урок', content=(
                'В журнале звонков за месяц триста строк, и среди них нужно '
                'посчитать, со сколькими **разными** номерами созванивались. '
                'Список для этого неудобен: он хранит повторы, и каждый номер '
                'пришлось бы проверять по всему накопленному списку.\n\n'
                'Вопрос «сколько разных?» – отдельный тип задачи, и для него '
                'есть отдельная структура данных.\n\n'
                '**В этом уроке:** как создать множество и почему в нём нет '
                'повторов; добавление и удаление элементов; почему индексов '
                'нет; проверка `in` и почему она быстрая; объединение, '
                'пересечение, разность и симметричная разность; приём «уже '
                'видели» для поиска повторов; какие значения можно класть в '
                'множество; зачем выводить его через `sorted()`.'
            )),
            dict(order=2, block_type='text', title='Множество', content=(
                '> **Множество** (`set`) – неупорядоченный набор **различных** '
                'значений. Записывается фигурными скобками; каждый элемент '
                'встречается не больше одного раза.\n\n'
                'Множество удобно получать из готовой последовательности: '
                '`set([1, 2, 2, 3])` убирает повторы, `set(\'мама\')` оставляет '
                'две разные буквы. Готовое литеральное множество – `{1, 2, 3}`.\n\n'
                'Порядок элементов **не гарантирован**: множество хранит их так, '
                'как удобно ему, а не в порядке добавления. Два множества с '
                'одинаковыми элементами равны независимо от порядка.\n\n'
                'И две записи, которые легко перепутать: `{}` – это **пустой '
                'словарь**, а не множество. Пустое множество создают вызовом '
                '`set()`.\n\n'
                '```python\n'
                'a = {1, 2, 3}\n'
                'print(a)             # {1, 2, 3}\n'
                '\n'
                'print(set([1, 2, 2, 3]))   # {1, 2, 3} – повтор исчез\n'
                "print(set('мама'))          # {'м', 'а'} – три буквы стали двумя\n"
                '\n'
                'print(type({}))      # <class \'dict\'> – это словарь\n'
                "print(type(set()))   # <class 'set'> – вот пустое множество\n"
                'print(len(set(\'мама\')))   # 2 – различных букв\n'
                'print({1, 2} == {2, 1})    # True – порядок не важен\n'
                '```'
            )),
            dict(order=3, block_type='text', title='Добавление и удаление', content=(
                '| Метод | Что делает | Ошибка |\n'
                '|---|---|---|\n'
                '| `s.add(x)` | добавляет `x`; если он уже есть, ничего не '
                'меняется | нет |\n'
                '| `s.remove(x)` | удаляет `x` | `KeyError`, если элемента нет |\n'
                '| `s.discard(x)` | удаляет `x`, если он есть | нет |\n'
                '| `s.pop()` | удаляет и возвращает **какой-то** элемент | '
                '`KeyError` на пустом множестве |\n'
                '| `s.clear()` | удаляет всё | нет |\n'
                '| `len(s)` | сколько элементов | – |\n\n'
                '**Индексов у множества нет.** Обращение `s[0]` даёт '
                '`TypeError`: элементы не упорядочены, и «нулевого» среди них '
                'не существует. Взять элемент по номеру можно только после '
                'превращения в список – и тогда порядок будет произвольным.\n\n'
                '`remove()` и `discard()` различаются ровно отношением к '
                'отсутствию элемента: первый считает это ошибкой, второй – '
                'нормальным случаем.\n\n'
                '```python\n'
                'a = {1, 2, 3}\n'
                'a.add(4)          # {1, 2, 3, 4}\n'
                'a.add(3)          # {1, 2, 3, 4} – тройка уже была\n'
                'print(a)\n'
                '\n'
                'a.discard(99)     # нет такого – и ладно\n'
                'print(a)          # {1, 2, 3, 4}\n'
                '\n'
                'print(a.pop())    # 1 (какой именно – не гарантировано)\n'
                'print(a)          # {2, 3, 4}\n'
                '\n'
                'a.remove(99)      # KeyError: 99\n'
                '\n'
                "print(a[0])       # TypeError: 'set' object is not\n"
                '                  # subscriptable\n'
                'print(list(a)[0]) # 2 – но порядок произвольный\n'
                '```'
            )),
            dict(order=4, block_type='text', title='Проверка `in`', content=(
                'Главное применение множества – ответ на вопрос «есть ли такой '
                'элемент».\n\n'
                '`x in a` работает и для списка, и для множества, но устроено '
                'по-разному. Список перебирает элементы по порядку: чтобы '
                'убедиться, что значения нет, он просматривает все. Множество '
                'хранит элементы так, что место нужного вычисляется сразу, без '
                'перебора, – поэтому и на тысяче элементов ответ приходит за '
                'одно действие.\n\n'
                'На маленьких списках разница не видна. На больших – в десятки '
                'и сотни раз, и именно поэтому проверку «есть ли» на большом '
                'наборе делают через множество. Как это устроено внутри, '
                'разберём в уроке 12.2.'
            )),
            dict(order=5, block_type='text', title='Операции над множествами', content=(
                'Пример: в кружок по шахматам ходят Аня, Борис и Вера, в кружок '
                'по программированию – Борис и Глеб.\n\n'
                'Операторы: `a | b` – объединение, `a & b` – пересечение, '
                '`a - b` – разность, `a ^ b` – симметричная разность. У каждой '
                'операции есть и метод.\n\n'
                '| Метод | Смысл | Результат |\n'
                '|---|---|---|\n'
                '| `a.union(b)` | объединение: кто ходит хотя бы в один | Аня, '
                'Борис, Вера, Глеб |\n'
                '| `a.intersection(b)` | пересечение: кто ходит в оба | Борис |\n'
                '| `a.difference(b)` | разность: кто только в первом | Аня, Вера |\n'
                '| `a.symmetric_difference(b)` | симметричная разность: кто ровно '
                'в одном из двух | Аня, Вера, Глеб |\n\n'
                'Разность несимметрична: `a - b` и `b - a` – разные множества. '
                'Остальные три от порядка не зависят. Оператор короче, метод '
                'привычнее тем, кто пришёл из других языков.\n\n'
                '```python\n'
                "chess = {'Аня', 'Борис', 'Вера'}\n"
                "code = {'Борис', 'Глеб'}\n"
                '\n'
                "print(chess | code)   # {'Аня', 'Борис', 'Вера', 'Глеб'}\n"
                "print(chess & code)   # {'Борис'}\n"
                "print(chess - code)   # {'Аня', 'Вера'}\n"
                "print(chess ^ code)   # {'Аня', 'Вера', 'Глеб'}\n"
                "print(code - chess)   # {'Глеб'} – разность несимметрична\n"
                '\n'
                '# порядок в выводе может отличаться – это нормально\n'
                '```'
            )),
            dict(order=6, block_type='text', title='Приём «уже видели»', content=(
                'Множество `seen` накапливает всё, что цикл уже прошёл. На '
                'каждом шаге проверка `x in seen` отвечает, встречался ли '
                'элемент раньше, – и после проверки элемент кладут в `seen`. '
                'Так находят первое повторённое число и вообще отвечают на '
                'вопрос «было ли уже такое».'
            )),
            dict(
                order=7, block_type='widget', title='Ищем первый повтор',
                content=(
                    'Программа идёт по списку и останавливается на первом '
                    'числе, которое уже встречалось. Следите за множеством '
                    '`seen`: оно растёт, а проверка на строке 4 от этого не '
                    'становится дольше.'
                ),
                widget_key='loop-trace',
                widget_config={
                    'code': DUP_CODE,
                    'vars': ['nums', 'x', 'seen'],
                    'steps': _dup_trace(),
                },
            ),
            dict(order=8, block_type='text', title='Что может лежать в множестве', content=(
                'Только **неизменяемые** значения: числа, строки, кортежи. '
                'Список положить нельзя – `TypeError: unhashable type: '
                '\'list\'`.\n\n'
                'Причина та же, что и у проверки `in` без перебора: множество '
                'вычисляет место элемента по его значению. Место должно '
                'оставаться тем же, пока элемент лежит внутри, – а у списка '
                'значение меняется при любой правке. Кортеж меняться не может, '
                'поэтому годится.\n\n'
                '> **Хешируемый** – неизменяемый объект, для которого можно '
                'вычислить постоянный числовой отпечаток. Только хешируемые '
                'объекты годятся в множество и в ключи словаря.\n\n'
                '```python\n'
                'a = {1, 2, 3}\n'
                'print([1, 2] in a)   # TypeError: unhashable type: \'list\'\n'
                '\n'
                'b = {(0, 0), (0, 1)}\n'
                'print((0, 1) in b)   # True – кортеж неизменяем\n'
                '\n'
                "c = {'a', 'b'}\n"
                'print(\'a\' in c)      # True – строка тоже неизменяема\n'
                '```'
            )),
            dict(order=9, block_type='text', title='Множество и сортировка', content=(
                'Порядок элементов множества не гарантирован, поэтому печатать '
                'его напрямую для читателя бессмысленно: от запуска к запуску '
                'порядок может отличаться. Результат выводят через `sorted()` – '
                'она возвращает список в понятном порядке.\n\n'
                'И вторая короткая запись: `len(set(a))` – число различных '
                'элементов в списке `a`. Часто именно это и спрашивается в '
                'задаче, а сам список разных значений не нужен.\n\n'
                '```python\n'
                'a = [3, 1, 3, 2, 1]\n'
                'print(len(set(a)))       # 3 – различных чисел\n'
                'print(sorted(set(a)))    # [1, 2, 3] – и в понятном порядке\n'
                'print(set(a))            # {1, 2, 3} – порядок не гарантирован\n'
                '```'
            )),
            dict(order=10, block_type='text', title='Коротко', content=(
                '- **Множество** – неупорядоченный набор без повторов; `set()` '
                'создаёт пустое, `{}` – это словарь.\n'
                '- `add`, `remove` (с `KeyError`), `discard` (без ошибки), '
                '`pop`, `clear`; индексов нет – `s[0]` даёт `TypeError`.\n'
                '- `in` у множества не перебирает элементы, поэтому на больших '
                'данных во много раз быстрее, чем у списка.\n'
                '- `|`, `&`, `-`, `^` – объединение, пересечение, разность и '
                'симметричная разность; `-` несимметрична.\n'
                '- В множество можно класть только неизменяемое: числа, '
                'строки, кортежи; список – `TypeError: unhashable`.\n'
                '- Выводить результат через `sorted()`, а число различных – '
                '`len(set(a))`.'
            )),
        ])

        quiz = _self_check(
            slug='self-check-b9-5-mnozhestva',
            title='Самопроверка: множества',
            description='Пять коротких вопросов по теме урока.',
            questions=[
                dict(
                    type='text',
                    text='Что напечатает `print(len(set([1, 2, 2, 3, 3, 3])))`?',
                    correct_text_answer='3',
                ),
                dict(
                    type='text',
                    text=(
                        'Что напечатает '
                        '`print(sorted({1, 2, 3} & {2, 3, 4}))`?'
                    ),
                    correct_text_answer='[2, 3]',
                    alternative_answers=['[2,3]'],
                ),
                dict(
                    type='choice',
                    text='Что вернёт `type({})`?',
                    choices=[
                        ("<class 'dict'> – пустые скобки создают словарь", True),
                        ("<class 'set'> – пустое множество", False),
                        ("<class 'list'> – пустой список", False),
                        ("<class 'tuple'> – пустой кортеж", False),
                    ],
                ),
                dict(
                    type='choice',
                    text=(
                        'В множестве `s` элемента 10 нет, и вызвали '
                        '`s.remove(10)`. Что произойдёт?'
                    ),
                    choices=[
                        ('KeyError: элемента нет в множестве', True),
                        ('Ничего: remove просто ничего не удалит', False),
                        ('ValueError: элемент не найден', False),
                        ('Множество станет пустым', False),
                    ],
                ),
                dict(
                    type='choice',
                    text='Что произойдёт при выполнении `{[1, 2]}`?',
                    choices=[
                        ("TypeError: unhashable type: 'list'", True),
                        ('Создастся множество из двух чисел', False),
                        ('Создастся множество из одного списка', False),
                        ('Создастся пустое множество', False),
                    ],
                ),
            ],
        )
        ArticleQuiz.objects.get_or_create(
            article=article, quiz=quiz,
            defaults={'label': 'Проверь себя', 'order': 1},
        )

    def seed_9_6(self):
        article = Article.objects.get(slug='9-6-slovari')
        article.title = 'Словари'
        article.description = (
            'Пары «ключ – значение»: добавление, удаление, get, перебор, '
            'подсчёт частот, сортировка по значению и группировка в словарь '
            'списков.'
        )
        article.save(update_fields=['title', 'description'])

        _replace_blocks(article, [
            dict(order=1, block_type='text', title='О чём этот урок', content=(
                'В телефонной книге ищут по имени, а не по номеру строки. '
                'Позиция записи ничего не значит: важно, что **Аня** – это '
                'номер, а **Борис** – другой. Список так не умеет: в нём '
                'доступ только по номеру, и чтобы найти Аню, пришлось бы '
                'перебирать все записи.\n\n'
                'Нужна структура, где доступ идёт по самому значению-признаку, '
                'и у каждого признака есть ровно одно связанное значение.\n\n'
                '**В этом уроке:** как устроен словарь и как читать значение по '
                'ключу; добавление, изменение и удаление; `in`, `get()` и '
                'значение по умолчанию; перебор ключей, значений и пар; '
                'подсчёт частот; сортировка по значению; группировка в словарь '
                'списков; какие ключи допустимы и какой тип выбрать.'
            )),
            dict(order=2, block_type='text', title='Словарь', content=(
                '> **Словарь** (`dict`) – коллекция пар '
                '**ключ – значение**. Доступ к значению идёт по ключу, а не по '
                'номеру позиции.\n\n'
                'Записывается фигурными скобками: `{\'Аня\': 5, \'Борис\': 4}`. '
                'Ключи в одном словаре не повторяются – у каждого ключа одно '
                'значение. Пустой словарь – `{}` или `dict()`.\n\n'
                'Обращение `d[\'Аня\']` возвращает значение по ключу. Если '
                'ключа нет, программа останавливается с `KeyError` – словарь не '
                'угадывает и не возвращает ничего по умолчанию.\n\n'
                'Структурно словарь похож на множество: и там, и там ключи '
                'хранятся так, что нужный находится сразу, без перебора. '
                'Поэтому ключи подчиняются тем же правилам, что элементы '
                'множества.\n\n'
                '```python\n'
                "marks = {'Аня': 5, 'Борис': 4}\n"
                "print(marks['Аня'])     # 5\n"
                '\n'
                "marks['Аня'] = 3        # замена значения по существующему ключу\n"
                "marks['Вера'] = 5       # новый ключ\n"
                'print(marks)            # {\'Аня\': 3, \'Борис\': 4, \'Вера\': 5}\n'
                '\n'
                "print(marks['Глеб'])    # KeyError: 'Глеб'\n"
                'print(dict())           # {} – пустой словарь\n'
                '```'
            )),
            dict(order=3, block_type='text', title='Добавление, изменение, удаление', content=(
                '| Запись | Что делает | Ошибка |\n'
                '|---|---|---|\n'
                '| `d[k] = v` | новый ключ – добавляет пару, существующий – '
                'меняет значение | нет |\n'
                '| `d[k]` | читает значение по ключу | `KeyError`, если ключа '
                'нет |\n'
                '| `del d[k]` | удаляет пару | `KeyError` |\n'
                '| `d.pop(k)` | удаляет пару и возвращает значение | `KeyError` |\n'
                '| `k in d` | есть ли такой **ключ** | нет |\n'
                '| `len(d)` | сколько пар | – |\n\n'
                '`in` у словаря проверяет **ключи**, а не значения: '
                '`\'Аня\' in marks` отвечает про ключ, а не про оценку.\n\n'
                'Добавление нового ключа и замена значения записываются '
                'одинаково, `d[k] = v`. Разницы в записи нет, потому что '
                'словарь сам решает: если ключ уже есть – заменить, если нет – '
                'создать пару.\n\n'
                '```python\n'
                "d = {'a': 1, 'b': 2}\n"
                "d['c'] = 3\n"
                'print(d)          # {\'a\': 1, \'b\': 2, \'c\': 3}\n'
                '\n'
                "del d['a']\n"
                'print(d)          # {\'b\': 2, \'c\': 3}\n'
                "\n"
                "print(d.pop('b')) # 2 – pop отдаёт значение\n"
                "print(d)          # {'c': 3}\n"
                '\n'
                "print('c' in d)   # True – in проверяет ключи\n"
                "print(3 in d)     # False – значение 3 ключом не считается\n"
                'print(len(d))     # 1\n'
                '```'
            )),
            dict(order=4, block_type='text', title='`get`: значение по умолчанию', content=(
                'Проверка `if k in d` перед каждым чтением быстро надоедает. '
                'Метод `get()` делает то же в одну запись:\n\n'
                '- `d.get(k)` – значение по ключу или `None`, если ключа нет;\n'
                '- `d.get(k, default)` – значение или указанная замена.\n\n'
                'Второй аргумент не записывается в словарь: он только '
                'возвращается вместо отсутствующего значения. Если пара нужна '
                'в словаре, её добавляют обычным `d[k] = default`.\n\n'
                'Именно `get()` делает коротким подсчёт частот в следующем '
                'блоке.\n\n'
                '```python\n'
                "d = {'Аня': 5}\n"
                "print(d.get('Борис'))       # None\n"
                "print(d.get('Борис', 0))    # 0\n"
                "print(d.get('Аня', 0))      # 5 – ключ есть, замена не нужна\n"
                "print(d)                    # {'Аня': 5} – словарь не изменился\n"
                '```'
            )),
            dict(order=5, block_type='text', title='Перебор словаря', content=(
                'По словарю ходят тремя способами:\n\n'
                '| Запись | Что перебирает |\n'
                '|---|---|\n'
                '| `for k in d` | ключи |\n'
                '| `d.keys()` | ключи (то же самое, но явно) |\n'
                '| `d.values()` | значения |\n'
                '| `d.items()` | пары `(ключ, значение)` |\n\n'
                'Пары из `items()` обычно сразу распаковывают: '
                '`for name, mark in d.items()` – распаковка кортежа, знакомая '
                'по уроку 9.4.\n\n'
                'Порядок перебора – **порядок добавления** ключей. Это '
                'свойство словаря в Python: он запоминает, в каком порядке '
                'ключи появились, и не переставляет их при чтении.\n\n'
                '```python\n'
                "d = {'Аня': 5, 'Борис': 4, 'Вера': 5}\n"
                '\n'
                'for k in d:\n'
                '    print(k)               # Аня, Борис, Вера – порядок добавления\n'
                '\n'
                "print(list(d.keys()))     # ['Аня', 'Борис', 'Вера']\n"
                'print(list(d.values()))   # [5, 4, 5]\n'
                '\n'
                'for name, mark in d.items():\n'
                '    print(name, mark)      # Аня 5, Борис 4, Вера 5\n'
                '```'
            )),
            dict(order=6, block_type='text', title='Подсчёт частот', content=(
                'Главный приём словаря. Нужно посчитать, сколько раз встретилось '
                'каждое значение: ключом становится само значение, а значением – '
                'счётчик.\n\n'
                '```python\n'
                'count[x] = count.get(x, 0) + 1\n'
                '```\n\n'
                'Читается так: возьми текущий счётчик для `x`, а если такого '
                'ключа ещё нет – ноль, прибавь единицу и запиши обратно. Первая '
                'встреча создаёт пару, каждая следующая увеличивает счётчик.\n\n'
                'Тот же приём считает слова, буквы, оценки – что угодно, у чего '
                'есть повторяющиеся значения.\n\n'
                '```python\n'
                "word = 'математика'\n"
                'count = {}\n'
                '\n'
                'for ch in word:\n'
                '    count[ch] = count.get(ch, 0) + 1\n'
                '\n'
                "print(count)\n"
                "# {'м': 2, 'а': 3, 'т': 2, 'е': 1, 'и': 1, 'к': 1}\n"
                '\n'
                "print(count['а'])     # 3 – буква «а» встречается трижды\n"
                '```'
            )),
            dict(
                order=7, block_type='widget', title='Считаем буквы',
                content=(
                    'Следите за словарём `freq`: на каждом шаге либо появляется '
                    'новый ключ, либо у уже существующего ключа растёт значение – '
                    'третьего не дано.'
                ),
                widget_key='loop-trace',
                widget_config={
                    'code': FREQ_CODE,
                    'vars': ['word', 'ch', 'freq'],
                    'steps': _freq_trace(),
                },
            ),
            dict(order=8, block_type='text', title='Сортировка по значению', content=(
                '`sorted(d)` и `sorted(d.items())` упорядочивают по **ключу**: '
                'сравниваются первые элементы пар.\n\n'
                'Чтобы упорядочить по значению, применяют приём из урока 9.4: '
                'собирают пары `(-значение, ключ)` и сортируют их. '
                'Возрастающая сортировка по отрицательному числу даёт убывание '
                'по настоящему значению, а при равенстве – порядок по ключу. '
                'При выводе знак возвращают.\n\n'
                'Параметр `key=` у `sorted()` умеет то же самое короче, но '
                'требует функции, а функции появятся только в блоке 11.\n\n'
                '```python\n'
                "count = {'м': 2, 'а': 3, 'т': 2, 'е': 1, 'и': 1, 'к': 1}\n"
                '\n'
                "print(sorted(count.items()))\n"
                "# [('а', 3), ('е', 1), ('и', 1), ('к', 1), ('м', 2), ('т', 2)]\n"
                '# – по алфавиту ключей\n'
                '\n'
                'pairs = [(-n, ch) for ch, n in count.items()]\n'
                'for n, ch in sorted(pairs):\n'
                '    print(ch, -n)\n'
                '# а 3, м 2, т 2, е 1, и 1, к 1\n'
                '# – по убыванию частоты, при равенстве по алфавиту\n'
                '```'
            )),
            dict(order=9, block_type='text', title='Словарь списков', content=(
                'Значением словаря может быть что угодно, в том числе список. '
                'Так делают группировку: ключ – признак группы, значение – '
                'список элементов этой группы.\n\n'
                '```python\n'
                'if k not in groups:\n'
                '    groups[k] = []\n'
                'groups[k].append(x)\n'
                '```\n\n'
                'Проверка `if k not in groups` нужна один раз на каждую новую '
                'группу: у неё ещё нет списка, в который можно дописывать. '
                'Дальше `groups[k]` возвращает готовый список, и `append()` '
                'дописывает в него.\n\n'
                '```python\n'
                'groups = {}\n'
                "pairs = [('9А', 'Аня'), ('9Б', 'Борис'), ('9А', 'Вера')]\n"
                '\n'
                'for cls, name in pairs:\n'
                '    if cls not in groups:\n'
                '        groups[cls] = []\n'
                '    groups[cls].append(name)\n'
                '\n'
                "print(groups)   # {'9А': ['Аня', 'Вера'], '9Б': ['Борис']}\n"
                '```'
            )),
            dict(order=10, block_type='text', title='Какой бывает ключ', content=(
                'Ключ должен быть **неизменяемым**, как элемент множества: '
                'число, строка, кортеж. Список в роли ключа даёт `TypeError: '
                'unhashable type: \'list\'`.\n\n'
                'Причина та же: словарь вычисляет место пары по значению ключа, '
                'и это значение не должно меняться, пока пара лежит в словаре.\n\n'
                'Кортеж в роли ключа удобен для составных признаков: '
                '`field[(2, 3)] = \'конь\'` – координата клетки как единый ключ. '
                'Значением при этом может быть любой объект, изменяемость '
                'значения ничему не мешает.\n\n'
                '```python\n'
                "field = {(2, 3): 'конь'}\n"
                "print(field[(2, 3)])       # конь – кортеж годится в ключи\n"
                '\n'
                "d = {1: 'один', 'a': 'буква'}\n"
                "print(d[1], d['a'])        # один буква\n"
                '\n'
                "d[[1, 2]] = 'x'            # TypeError: unhashable type:\n"
                '                           # \'list\'\n'
                '```'
            )),
            dict(order=11, block_type='text', title='Что выбрать', content=(
                '| Тип | Порядок | Изменяемый | Повторы | Доступ | Типичная '
                'задача |\n'
                '|---|---|---|---|---|---|\n'
                '| `list` | есть | да | да | по индексу | лента значений, '
                'которую правят |\n'
                '| `tuple` | есть | нет | да | по индексу | координата, дата, '
                'неизменяемый набор |\n'
                '| `set` | нет | да | нет | по значению (`in`) | «сколько '
                'разных», проверка вхождения |\n'
                '| `dict` | порядок добавления | да | ключи нет, значения да | '
                'по ключу | пара «признак – значение», подсчёт частот |\n\n'
                'Порядок в таблице – не «лучше-хуже», а разные ответы на разные '
                'вопросы. Список нумерует, кортеж закрепляет, множество '
                'спрашивает «есть ли», словарь ищет по названию.'
            )),
            dict(order=12, block_type='text', title='Коротко', content=(
                '- **Словарь** – пары «ключ – значение»; доступ по ключу, '
                'отсутствующий ключ – `KeyError`.\n'
                '- `d[k] = v` добавляет или заменяет пару, `del d[k]` и '
                '`d.pop(k)` удаляют; `in` проверяет **ключи**.\n'
                '- `d.get(k, default)` заменяет проверку `if k in d` и не '
                'записывает пару в словарь.\n'
                '- Перебор: `for k in d`, `d.keys()`, `d.values()`, '
                '`d.items()`; порядок – порядок добавления.\n'
                '- Подсчёт частот: `count[x] = count.get(x, 0) + 1`.\n'
                '- Сортировка по значению – через пары `(-значение, ключ)`; '
                'ключом может быть только неизменяемое значение.'
            )),
        ])

        quiz = _self_check(
            slug='self-check-b9-6-slovari',
            title='Самопроверка: словари',
            description='Пять коротких вопросов по теме урока.',
            questions=[
                dict(
                    type='text',
                    text=(
                        'Что напечатает эта программа?\n\n'
                        '```python\n'
                        "d = {'a': 1}\n"
                        "d['a'] = 5\n"
                        'print(len(d))\n'
                        '```'
                    ),
                    correct_text_answer='1',
                ),
                dict(
                    type='text',
                    text=(
                        'Что напечатает '
                        "`print('1' in {'a': 1, 'b': 2}, 'a' in {'a': 1, 'b': 2})`?"
                    ),
                    correct_text_answer='False True',
                    alternative_answers=['False,True'],
                ),
                dict(
                    type='choice',
                    text=(
                        "Что вернёт `d.get('x', 0)`, если ключа `'x'` в словаре "
                        'нет?'
                    ),
                    choices=[
                        ('0 – указанное значение по умолчанию', True),
                        ('None', False),
                        ("KeyError: ключа 'x' нет", False),
                        ('Словарь создаст ключ x со значением 0', False),
                    ],
                ),
                dict(
                    type='choice',
                    text=(
                        'Нужно посчитать, сколько раз встретилось каждое слово в '
                        'тексте. Какой тип подходит лучше всего?'
                    ),
                    choices=[
                        ('Словарь: слово – ключ, счётчик – значение', True),
                        ('Список: слова складывать по порядку', False),
                        ('Множество: оно убирает повторы', False),
                        ('Кортеж: он неизменяемый', False),
                    ],
                ),
                dict(
                    type='choice',
                    text="Что произойдёт при выполнении `{[1]: 'x'}`?",
                    choices=[
                        ("TypeError: unhashable type: 'list'", True),
                        ('Создастся словарь с ключом-списком', False),
                        ('Создастся словарь с ключом-числом 1', False),
                        ('Создастся пустой словарь', False),
                    ],
                ),
            ],
        )
        ArticleQuiz.objects.get_or_create(
            article=article, quiz=quiz,
            defaults={'label': 'Проверь себя', 'order': 1},
        )

    def seed_9_practicum(self):
        """Практикум блока 9: отдельная страница обязательных задач.

        Не статья: теории здесь нет, только 20 задач на программирование с
        автопроверкой. Порядок по нарастающей: 1–4 базовые операции со
        списком, 5–8 сортировка и вложенные списки, 9–14 словари и
        множества, 15–18 подсчёт букв и группировка, 19–20 префиксные суммы.

        Материал ограничен блоками 1–9: арифметика, input/print,
        if/elif/else, while, for/range, строки, списки (методы, срезы,
        списочные выражения), вложенные списки, кортежи, enumerate/zip,
        множества, словари и get. Своих функций, lambda и key= в курсе ещё
        не было – в подсказках их нет.

        Ожидаемые ответы выверены по эталонным решениям – по одному на
        каждую задачу, – а не выписаны от руки.
        """
        section = Section.objects.get(slug='blok-9')

        quiz = _self_check(
            slug='praktikum-blok-9',
            title='Практикум блока 9: обязательные задачи',
            description=(
                '20 программ на Python с автоматической проверкой. Попыток не '
                'ограничено, решённые задачи сохраняются. Задача засчитывается '
                'только если пройдены все тесты. Важно: input() без '
                'текста-подсказки, ничего лишнего не печатать, формат вывода – '
                'строго по условию.'
            ),
            questions=[
                dict(
                    type='code', title='Задача 1. Задом наперёд',
                    text=(
                        'Табло показывает участников забега в порядке '
                        'финиша, а награждение идёт с конца – первым '
                        'награждают последнего прибежавшего. Чтобы объявлять '
                        'результаты от конца к началу, нужен тот же список '
                        'задом наперёд.\n'
                        '\n'
                        '**Что найти:** те же числа в обратном порядке: '
                        'последнее число ввода становится первым, первое – '
                        'последним.\n'
                        '\n'
                        'Напоминание в этой первой задаче: `input()` без '
                        'текста-подсказки, иначе подсказка попадёт в вывод и '
                        'тест не пройдёт.\n'
                        '\n'
                        '**Ввод:** одна строка – целые числа через пробел '
                        '(хотя бы одно).\n'
                        '**Вывод:** те же числа в обратном порядке через '
                        'пробел.\n'
                        '\n'
                        '###### Пример ввода\n'
                        '\n'
                        '```text\n'
                        '1 2 3 4 5\n'
                        '```\n'
                        '\n'
                        '###### Пример вывода\n'
                        '\n'
                        '```text\n'
                        '5 4 3 2 1\n'
                        '```\n'
                        '\n'
                        '**Разбор примера.** Последнее число 5 встаёт '
                        'первым, за ним идут 4, 3 и 2, а единица оказывается '
                        'последней.\n'
                    ),
                    test_cases=[
                        ('1 2 3 4 5\n', '5 4 3 2 1'),
                        ('7\n', '7'),
                        ('-1 0 -1 2\n', '2 -1 0 -1'),
                    ],
                ),
                dict(
                    type='code', title='Задача 2. Больше среднего',
                    text=(
                        'Учитель хочет знать, сколько учеников написали '
                        'контрольную лучше среднего балла класса: по такому '
                        'числу видно, много ли работ выше общего уровня.\n'
                        '\n'
                        '**Что найти:** сколько чисел строго больше среднего '
                        'арифметического всех чисел; числа, равные среднему, '
                        'не считаются.\n'
                        '\n'
                        '**Ввод:** одна строка – целые числа через пробел '
                        '(хотя бы одно).\n'
                        '**Вывод:** одно число – сколько чисел строго больше '
                        'среднего.\n'
                        '\n'
                        '###### Пример ввода\n'
                        '\n'
                        '```text\n'
                        '1 2 3 4 5\n'
                        '```\n'
                        '\n'
                        '###### Пример вывода\n'
                        '\n'
                        '```text\n'
                        '2\n'
                        '```\n'
                        '\n'
                        '**Разбор примера.** Среднее чисел 1, 2, 3, 4, 5 '
                        'равно 3, поэтому больше него только 4 и 5 – ответ '
                        '2.\n'
                    ),
                    test_cases=[
                        ('1 2 3 4 5\n', '2'),
                        ('5 5 5\n', '0'),
                        ('-3 -1 10\n', '1'),
                        ('1 2\n', '1'),
                    ],
                ),
                dict(
                    type='code', title='Задача 3. Циклический сдвиг',
                    text=(
                        'Дежурные стоят в очереди по кругу: каждый день '
                        'последний в списке переходит в начало. Каким будет '
                        'список через $k$ дней? Это и есть циклический сдвиг.\n'
                        '\n'
                        '**Что найти:** список после сдвига на $k$ вправо по '
                        'кругу – последние $k$ элементов переезжают в начало, '
                        'остальные сдвигаются. Число $k$ может быть больше '
                        'длины списка.\n'
                        '\n'
                        '**Ввод:** две строки – целые числа через пробел; '
                        'целое $k$, не меньше нуля.\n'
                        '**Вывод:** элементы после сдвига через пробел.\n'
                        '\n'
                        '###### Пример ввода\n'
                        '\n'
                        '```text\n'
                        '1 2 3 4 5\n'
                        '2\n'
                        '```\n'
                        '\n'
                        '###### Пример вывода\n'
                        '\n'
                        '```text\n'
                        '4 5 1 2 3\n'
                        '```\n'
                        '\n'
                        '**Разбор примера.** При сдвиге на 2 вперёд уходят '
                        'последние два элемента `4 5`, а за ними остаются '
                        '1, 2 и 3. Сдвиг на 7 при пяти элементах даёт тот же '
                        'результат, что и на 2: сдвиг на 5 возвращает всё на '
                        'место.\n'
                    ),
                    test_cases=[
                        ('1 2 3 4 5\n2\n', '4 5 1 2 3'),
                        ('1 2 3 4 5\n0\n', '1 2 3 4 5'),
                        ('1 2 3 4 5\n7\n', '4 5 1 2 3'),
                        ('9\n100\n', '9'),
                        ('1 2 3\n3\n', '1 2 3'),
                    ],
                ),
                dict(
                    type='code', title='Задача 4. Нули в конец',
                    text=(
                        'В таблице результатов 0 означает «не пришёл». Неявки '
                        'переносят в конец списка, не меняя порядок '
                        'остальных.\n'
                        '\n'
                        '**Что найти:** список, где все нули в конце, а '
                        'ненулевые числа стоят в исходном порядке.\n'
                        '\n'
                        '**Ввод:** одна строка – целые числа через пробел.\n'
                        '**Вывод:** числа после переноса через пробел.\n'
                        '\n'
                        '###### Пример ввода\n'
                        '\n'
                        '```text\n'
                        '0 1 0 3 12\n'
                        '```\n'
                        '\n'
                        '###### Пример вывода\n'
                        '\n'
                        '```text\n'
                        '1 3 12 0 0\n'
                        '```\n'
                        '\n'
                        '**Разбор примера.** Ненулевые 1, 3 и 12 сохраняют '
                        'свой порядок, а два нуля переезжают в конец – '
                        'получается `1 3 12 0 0`.\n'
                    ),
                    test_cases=[
                        ('0 1 0 3 12\n', '1 3 12 0 0'),
                        ('0 0\n', '0 0'),
                        ('1 2 3\n', '1 2 3'),
                        ('-1 0 -2 0 0 5\n', '-1 -2 5 0 0 0'),
                    ],
                ),
                dict(
                    type='code', title='Задача 5. Слияние двух упорядоченных',
                    text=(
                        'Два класса построились по росту, каждый по '
                        'неубыванию. Нужен общий строй по росту – как на '
                        'линейке перед физкультурой.\n'
                        '\n'
                        '**Что найти:** все числа обоих списков по '
                        'неубыванию.\n'
                        '\n'
                        '**Ввод:** две строки – элементы первого и второго '
                        'списка через пробел; каждый список непустой и уже '
                        'упорядочен.\n'
                        '**Вывод:** все элементы по неубыванию через '
                        'пробел.\n'
                        '\n'
                        '###### Пример ввода\n'
                        '\n'
                        '```text\n'
                        '1 2 4\n'
                        '1 3 4\n'
                        '```\n'
                        '\n'
                        '###### Пример вывода\n'
                        '\n'
                        '```text\n'
                        '1 1 2 3 4 4\n'
                        '```\n'
                        '\n'
                        '**Разбор примера.** На каждом шаге берётся меньший '
                        'из двух текущих элементов, поэтому единицы идут '
                        'подряд, затем 2, 3 и две четвёрки.\n'
                        '\n'
                        '**Подсказка.** Попробуйте без `sorted()`: два '
                        'индекса, по одному на список, и на каждом шаге '
                        'берите меньший из двух текущих элементов.\n'
                    ),
                    test_cases=[
                        ('1 2 4\n1 3 4\n', '1 1 2 3 4 4'),
                        ('5\n1 2 3\n', '1 2 3 5'),
                        ('-5 0 0 7\n-3 0 10\n', '-5 -3 0 0 0 7 10'),
                        ('1 1 1\n1\n', '1 1 1 1'),
                    ],
                ),
                dict(
                    type='code', title='Задача 6. Транспонирование',
                    text=(
                        'Журнал записан построчно: строка – ученик, столбец – '
                        'контрольная. Для отчёта по контрольным нужен тот же '
                        'журнал наоборот: строка – контрольная, столбец – '
                        'ученик.\n'
                        '\n'
                        '**Что найти:** таблицу, где строки стали столбцами: '
                        'элемент из строки $i$ и столбца $j$ переезжает в '
                        'строку $j$ и столбец $i$.\n'
                        '\n'
                        '**Ввод:** первая строка – $n$ и $m$; далее $n$ строк '
                        'по $m$ целых чисел.\n'
                        '**Вывод:** $m$ строк по $n$ чисел через пробел.\n'
                        '\n'
                        '###### Пример ввода\n'
                        '\n'
                        '```text\n'
                        '2 3\n'
                        '1 2 3\n'
                        '4 5 6\n'
                        '```\n'
                        '\n'
                        '###### Пример вывода\n'
                        '\n'
                        '```text\n'
                        '1 4\n'
                        '2 5\n'
                        '3 6\n'
                        '```\n'
                        '\n'
                        '**Разбор примера.** Первый столбец `1 4` стал первой '
                        'строкой, второй столбец `2 5` – второй, третий '
                        '`3 6` – третьей.\n'
                    ),
                    test_cases=[
                        ('2 3\n1 2 3\n4 5 6\n', '1 4\n2 5\n3 6'),
                        ('1 1\n42\n', '42'),
                        ('3 1\n7\n-8\n9\n', '7 -8 9'),
                        ('2 2\n1 2\n3 4\n', '1 3\n2 4'),
                    ],
                ),
                dict(
                    type='code', title='Задача 7. Лучшая строка таблицы',
                    text=(
                        'Строки – магазины сети, числа в строке – выручка по '
                        'дням недели. Нужно понять, какой магазин заработал '
                        'больше всех.\n'
                        '\n'
                        '**Что найти:** номер строки (с 1) с наибольшей суммой '
                        'и саму сумму; если таких строк несколько – первую из '
                        'них.\n'
                        '\n'
                        '**Ввод:** первая строка – $n$; далее $n$ строк с '
                        'целыми числами через пробел.\n'
                        '**Вывод:** номер строки и её сумма через пробел.\n'
                        '\n'
                        '###### Пример ввода\n'
                        '\n'
                        '```text\n'
                        '3\n'
                        '1 2 3\n'
                        '4 5 6\n'
                        '0 0 1\n'
                        '```\n'
                        '\n'
                        '###### Пример вывода\n'
                        '\n'
                        '```text\n'
                        '2 15\n'
                        '```\n'
                        '\n'
                        '**Разбор примера.** Суммы строк равны 6, 15 и 1 – '
                        'лучшая вторая, поэтому ответ `2 15`.\n'
                    ),
                    test_cases=[
                        ('3\n1 2 3\n4 5 6\n0 0 1\n', '2 15'),
                        ('2\n5 5\n7 3\n', '1 10'),
                        ('3\n-1 -2\n-5 0\n-3 1\n', '3 -2'),
                        ('1\n0 0 0\n', '1 0'),
                    ],
                ),
                dict(
                    type='code', title='Задача 8. Ближайшая точка',
                    text=(
                        'Вы стоите в точке $(0, 0)$, а на карте $n$ свободных '
                        'такси. Вызываем то, которое ближе всего.\n'
                        '\n'
                        '**Что найти:** точку с наименьшим расстоянием до '
                        '$(0, 0)$; при равном расстоянии – с меньшим $x$, при '
                        'равных $x$ – с меньшим $y$.\n'
                        '\n'
                        '**Ввод:** первая строка – $n$; далее $n$ строк по два '
                        'целых числа $x$ и $y$.\n'
                        '**Вывод:** координаты точки через пробел.\n'
                        '\n'
                        '###### Пример ввода\n'
                        '\n'
                        '```text\n'
                        '3\n'
                        '1 3\n'
                        '-2 2\n'
                        '5 -1\n'
                        '```\n'
                        '\n'
                        '###### Пример вывода\n'
                        '\n'
                        '```text\n'
                        '-2 2\n'
                        '```\n'
                        '\n'
                        '**Разбор примера.** Квадраты расстояний равны 10, 8 '
                        'и 26 – меньший у точки $(-2, 2)$, она и ближе всех.\n'
                        '\n'
                        '**Подсказка.** Корень не нужен – сравнивайте '
                        '$x^2 + y^2$, а все три условия сравнения '
                        'укладываются в один кортеж.\n'
                    ),
                    test_cases=[
                        ('3\n1 3\n-2 2\n5 -1\n', '-2 2'),
                        ('2\n3 4\n-4 3\n', '-4 3'),
                        ('1\n0 0\n', '0 0'),
                        ('4\n2 0\n0 2\n0 -2\n-2 0\n', '-2 0'),
                    ],
                ),
                dict(
                    type='code', title='Задача 9. Рейтинг',
                    text=(
                        'Итоговая таблица олимпиады: у каждого участника '
                        'фамилия и балл. Места распределяются от лучшего '
                        'балла к худшему.\n'
                        '\n'
                        '**Что найти:** участников по убыванию балла, а при '
                        'равных баллах – по фамилии в алфавитном порядке.\n'
                        '\n'
                        '**Ввод:** первая строка – $n$; далее $n$ строк '
                        '«Фамилия балл» (фамилия одним словом, балл – целое '
                        'число).\n'
                        '**Вывод:** $n$ строк в том же формате «Фамилия '
                        'балл».\n'
                        '\n'
                        '###### Пример ввода\n'
                        '\n'
                        '```text\n'
                        '4\n'
                        'Иванов 85\n'
                        'Петров 92\n'
                        'Абрамов 85\n'
                        'Сидоров 70\n'
                        '```\n'
                        '\n'
                        '###### Пример вывода\n'
                        '\n'
                        '```text\n'
                        'Петров 92\n'
                        'Абрамов 85\n'
                        'Иванов 85\n'
                        'Сидоров 70\n'
                        '```\n'
                        '\n'
                        '**Разбор примера.** Лучший балл 92 у Петрова. У '
                        'Абрамова и Иванова по 85, поэтому Абрамов стоит выше: '
                        'его фамилия идёт раньше по алфавиту. Сидоров с 70 '
                        'замыкает список.\n'
                    ),
                    test_cases=[
                        ('4\nИванов 85\nПетров 92\nАбрамов 85\nСидоров 70\n',
                         'Петров 92\nАбрамов 85\nИванов 85\nСидоров 70'),
                        ('1\nОрлова 100\n', 'Орлова 100'),
                        ('3\nВолков 50\nБелов 50\nАлексеев 50\n',
                         'Алексеев 50\nБелов 50\nВолков 50'),
                    ],
                ),
                dict(
                    type='code', title='Задача 10. Без повторов',
                    text=(
                        'Журнал входов на сайт хранит номер посетителя при '
                        'каждом визите, поэтому один и тот же номер повторяется '
                        'много раз. Нужен список посетителей в порядке первого '
                        'визита.\n'
                        '\n'
                        '**Что найти:** числа без повторов – каждое стоит там, '
                        'где оно встретилось впервые; более поздние повторы '
                        'выбрасываются.\n'
                        '\n'
                        '**Ввод:** одна строка – целые числа через пробел.\n'
                        '**Вывод:** числа без повторов в порядке первого '
                        'появления через пробел.\n'
                        '\n'
                        '###### Пример ввода\n'
                        '\n'
                        '```text\n'
                        '3 1 3 2 1 5\n'
                        '```\n'
                        '\n'
                        '###### Пример вывода\n'
                        '\n'
                        '```text\n'
                        '3 1 2 5\n'
                        '```\n'
                        '\n'
                        '**Разбор примера.** Порядок задают первые встречи: '
                        '3, 1, 2 и 5. Вторые тройка и единица выброшены, '
                        'поэтому в ответе четыре числа из шести.\n'
                    ),
                    test_cases=[
                        ('3 1 3 2 1 5\n', '3 1 2 5'),
                        ('7 7 7\n', '7'),
                        ('1 2 3\n', '1 2 3'),
                        ('-1 1 -1 1 0\n', '-1 1 0'),
                    ],
                ),
                dict(
                    type='code', title='Задача 11. Общие элементы',
                    text=(
                        'Двое учеников перечислили номера задач, которые '
                        'решили; номера могут повторяться. Учитель хочет '
                        'узнать, какие задачи решили оба.\n'
                        '\n'
                        '**Что найти:** числа, которые есть в обоих списках, '
                        'без повторов, по возрастанию; если общих чисел нет – '
                        'слово `нет`.\n'
                        '\n'
                        '**Ввод:** две строки – целые числа через пробел.\n'
                        '**Вывод:** общие числа по возрастанию через пробел '
                        'или слово `нет`.\n'
                        '\n'
                        '###### Пример ввода\n'
                        '\n'
                        '```text\n'
                        '1 2 2 1\n'
                        '2 2\n'
                        '```\n'
                        '\n'
                        '###### Пример вывода\n'
                        '\n'
                        '```text\n'
                        '2\n'
                        '```\n'
                        '\n'
                        '**Разбор примера.** Двойка есть в обоих списках, а '
                        'единица – только в первом, поэтому в ответ попадает '
                        'одна двойка.\n'
                    ),
                    test_cases=[
                        ('1 2 2 1\n2 2\n', '2'),
                        ('4 9 5\n9 4 9 8 4\n', '4 9'),
                        ('1 2 3\n4 5 6\n', 'нет'),
                        ('-3 10 -3 0\n0 -3 7\n', '-3 0'),
                    ],
                ),
                dict(
                    type='code', title='Задача 12. Первый повтор',
                    text=(
                        'На турникете по очереди прикладывают карты-пропуска. '
                        'Одну карту приложили второй раз – значит, её передали '
                        'другу. Какая карта засветилась повторно первой?\n'
                        '\n'
                        '**Что найти:** число, чья **вторая** встреча случилась '
                        'раньше всех остальных вторых встреч; если повторов '
                        'нет – слово `нет`.\n'
                        '\n'
                        '**Ввод:** одна строка – целые числа через пробел.\n'
                        '**Вывод:** это число или слово `нет`.\n'
                        '\n'
                        '###### Пример ввода\n'
                        '\n'
                        '```text\n'
                        '2 5 1 2 3 5 1 2 4\n'
                        '```\n'
                        '\n'
                        '###### Пример вывода\n'
                        '\n'
                        '```text\n'
                        '2\n'
                        '```\n'
                        '\n'
                        '###### Пример 2 ввода\n'
                        '\n'
                        '```text\n'
                        '2 1 3 5 3 2\n'
                        '```\n'
                        '\n'
                        '###### Пример 2 вывода\n'
                        '\n'
                        '```text\n'
                        '3\n'
                        '```\n'
                        '\n'
                        '**Разбор примера.** Во втором примере двойка '
                        'встретилась первой, но повторилась только в самом '
                        'конце, а тройка повторилась раньше – поэтому ответ 3, '
                        'а не 2.\n'
                    ),
                    test_cases=[
                        ('2 5 1 2 3 5 1 2 4\n', '2'),
                        ('2 1 3 5 3 2\n', '3'),
                        ('1 2 3 4\n', 'нет'),
                        ('7 7\n', '7'),
                    ],
                ),
                dict(
                    type='code', title='Задача 13. Телефонная книга',
                    text=(
                        'В телефоне сохранены контакты, а потом вы ищете номера '
                        'по именам. Нужна программа, которая отвечает на такие '
                        'запросы.\n'
                        '\n'
                        '**Что найти:** для каждого запрошенного имени – номер; '
                        'если такого контакта нет – слово `нет`. Если одно имя '
                        'сохранено несколько раз, контакт перезаписан – '
                        'действует последняя запись. Имя и номер – по одному '
                        'слову без пробелов. Большие и маленькие буквы '
                        'различаются: `дима` и `Дима` – разные контакты.\n'
                        '\n'
                        '**Ввод:** первая строка – число $n$ контактов; '
                        'следующие $n$ строк – «имя номер» через пробел; затем '
                        'число $m$ запросов; следующие $m$ строк – по одному '
                        'имени.\n'
                        '**Вывод:** $m$ строк, ответ на каждый запрос в порядке '
                        'запросов.\n'
                        '\n'
                        '###### Пример ввода\n'
                        '\n'
                        '```text\n'
                        '3\n'
                        'Аня 111\n'
                        'Борис 222\n'
                        'Вера 333\n'
                        '3\n'
                        'Борис\n'
                        'Глеб\n'
                        'Аня\n'
                        '```\n'
                        '\n'
                        '###### Пример вывода\n'
                        '\n'
                        '```text\n'
                        '222\n'
                        'нет\n'
                        '111\n'
                        '```\n'
                        '\n'
                        '**Разбор примера.** Борис есть в книге – отвечаем '
                        '222; Глеба в книге нет – пишем `нет`; Аня есть – '
                        'отвечаем 111.\n'
                    ),
                    test_cases=[
                        ('3\nАня 111\nБорис 222\nВера 333\n3\nБорис\nГлеб\nАня\n',
                         '222\nнет\n111'),
                        ('2\nАня 111\nАня 999\n1\nАня\n', '999'),
                        ('1\nДима 555\n2\nдима\nДима\n', 'нет\n555'),
                    ],
                ),
                dict(
                    type='code', title='Задача 14. Частота слов',
                    text=(
                        'Какие слова автор сочинения повторяет чаще всего? '
                        'Такой список сразу показывает, о чём текст и где '
                        'автор ходит по кругу.\n'
                        '\n'
                        '**Что найти:** каждое различное слово и сколько раз '
                        'оно встретилось; сначала самые частые, при равной '
                        'частоте – по алфавиту.\n'
                        '\n'
                        '**Ввод:** одна строка – слова через пробел, '
                        'маленькими буквами.\n'
                        '**Вывод:** по строке на каждое различное слово: '
                        '«слово количество».\n'
                        '\n'
                        '###### Пример ввода\n'
                        '\n'
                        '```text\n'
                        'кот пёс кот мышь пёс кот\n'
                        '```\n'
                        '\n'
                        '###### Пример вывода\n'
                        '\n'
                        '```text\n'
                        'кот 3\n'
                        'пёс 2\n'
                        'мышь 1\n'
                        '```\n'
                        '\n'
                        '**Разбор примера.** «Кот» встретился три раза, «пёс» '
                        '– два, «мышь» – один, поэтому слова идут в таком '
                        'порядке. Если бы частоты совпали, слова встали бы по '
                        'алфавиту.\n'
                    ),
                    test_cases=[
                        ('кот пёс кот мышь пёс кот\n', 'кот 3\nпёс 2\nмышь 1'),
                        ('а б в\n', 'а 1\nб 1\nв 1'),
                        ('да да да\n', 'да 3'),
                        ('b a b a c\n', 'a 2\nb 2\nc 1'),
                    ],
                ),
                dict(
                    type='code', title='Задача 15. Анаграммы',
                    text=(
                        'В игре нужно составить из букв одного слова другое, '
                        'использовав все буквы ровно столько раз, сколько их '
                        'есть. Такие слова называют анаграммами.\n'
                        '\n'
                        '**Что найти:** `ДА`, если вторая строка составлена '
                        'ровно из тех же букв в том же количестве, иначе '
                        '`НЕТ`.\n'
                        '\n'
                        '**Ввод:** две строки без пробелов.\n'
                        '**Вывод:** `ДА` или `НЕТ`.\n'
                        '\n'
                        '###### Пример ввода\n'
                        '\n'
                        '```text\n'
                        'listen\n'
                        'silent\n'
                        '```\n'
                        '\n'
                        '###### Пример вывода\n'
                        '\n'
                        '```text\n'
                        'ДА\n'
                        '```\n'
                        '\n'
                        '**Разбор примера.** В `listen` и `silent` по одной '
                        'букве l, i, s, t, e, n – набор букв одинаковый, '
                        'поэтому ответ `ДА`.\n'
                        '\n'
                        '**Подсказка.** Посчитайте буквы каждой строки '
                        'словарём и сравните словари.\n'
                    ),
                    test_cases=[
                        ('listen\nsilent\n', 'ДА'),
                        ('aab\nabb\n', 'НЕТ'),
                        ('кот\nток\n', 'ДА'),
                        ('abc\nabcd\n', 'НЕТ'),
                        ('a\na\n', 'ДА'),
                    ],
                ),
                dict(
                    type='code', title='Задача 16. Шифр замены',
                    text=(
                        'Простой шифр заменяет каждую букву одной и той же '
                        'другой буквой. Можно ли получить вторую строку из '
                        'первой таким шифром?\n'
                        '\n'
                        'Правила шифра: одна и та же буква первой строки '
                        'всегда заменяется одной и той же буквой; две **разные** '
                        'буквы не могут перейти в одну и ту же; буква может '
                        'остаться собой. Строки одинаковой длины.\n'
                        '\n'
                        '**Что найти:** можно ли получить вторую строку из '
                        'первой таким шифром.\n'
                        '\n'
                        '**Ввод:** две строки одинаковой длины.\n'
                        '**Вывод:** `ДА` или `НЕТ`.\n'
                        '\n'
                        '###### Пример ввода\n'
                        '\n'
                        '```text\n'
                        'egg\n'
                        'add\n'
                        '```\n'
                        '\n'
                        '###### Пример вывода\n'
                        '\n'
                        '```text\n'
                        'ДА\n'
                        '```\n'
                        '\n'
                        '###### Пример 2 ввода\n'
                        '\n'
                        '```text\n'
                        'foo\n'
                        'bar\n'
                        '```\n'
                        '\n'
                        '###### Пример 2 вывода\n'
                        '\n'
                        '```text\n'
                        'НЕТ\n'
                        '```\n'
                        '\n'
                        '**Разбор примера.** `egg` → `add`: e переходит в a, '
                        'g – в d, правила соблюдены. `foo` → `bar` уже '
                        'нельзя: буква o должна стать и a, и r. Случай без '
                        'примера `ab` → `aa` тоже `НЕТ`: a и b – разные '
                        'буквы, а перешли обе в a.\n'
                        '\n'
                        '**Подсказка.** Заведите два словаря – «буква первой → '
                        'буква второй» и обратный; одного мало, он пропустит '
                        'случай `ab`/`aa`.\n'
                    ),
                    test_cases=[
                        ('egg\nadd\n', 'ДА'),
                        ('foo\nbar\n', 'НЕТ'),
                        ('paper\ntitle\n', 'ДА'),
                        ('badc\nbaba\n', 'НЕТ'),
                        ('ab\naa\n', 'НЕТ'),
                    ],
                ),
                dict(
                    type='code', title='Задача 17. Две суммы',
                    text=(
                        'На подарочном сертификате ровно target рублей, и '
                        'потратить его надо целиком на два разных товара. '
                        'Цены в списке идут **в произвольном порядке, не '
                        'отсортированы**. Отсортировать их самому не выйдет: в '
                        'ответе нужны номера товаров в исходном списке, а '
                        'сортировка их перемешает.\n'
                        '\n'
                        '**Что найти:** номера двух товаров (нумерация с '
                        'нуля), цены которых в сумме дают ровно target. Один '
                        'товар дважды брать нельзя, но у двух разных товаров '
                        'цена может совпадать. Гарантируется, что подходящая '
                        'пара ровно одна.\n'
                        '\n'
                        '**Ввод:** первая строка – цены через пробел; вторая – '
                        'target.\n'
                        '**Вывод:** два номера через пробел, меньший первым.\n'
                        '\n'
                        '###### Пример ввода\n'
                        '\n'
                        '```text\n'
                        '2 7 11 15\n'
                        '9\n'
                        '```\n'
                        '\n'
                        '###### Пример вывода\n'
                        '\n'
                        '```text\n'
                        '0 1\n'
                        '```\n'
                        '\n'
                        '**Разбор примера.** 2 + 7 = 9, это товары с номерами '
                        '0 и 1, поэтому в ответе `0 1`.\n'
                        '\n'
                        '**Подсказка.** Перебор всех пар работает, но словарь '
                        '«цена → номер» позволяет обойтись одним проходом: '
                        'для очередной цены $x$ проверьте, встречалась ли '
                        'раньше цена target − $x$ (в коде это `target - x`).\n'
                    ),
                    test_cases=[
                        ('2 7 11 15\n9\n', '0 1'),
                        ('3 2 4\n6\n', '1 2'),
                        ('3 3\n6\n', '0 1'),
                        ('-4 8 1 -1 5\n0\n', '2 3'),
                        ('5 1 -2 7\n-1\n', '1 2'),
                    ],
                ),
                dict(
                    type='code', title='Задача 18. Группы анаграмм',
                    text=(
                        'В игре «Наборщик» слова, составленные из одного и того '
                        'же набора букв, собирают в одну группу. Игрокам нужно '
                        'разложить все названные слова по таким группам.\n'
                        '\n'
                        '**Что найти:** разбить слова на группы анаграмм. '
                        'Анаграммы – слова из одних и тех же букв в одинаковом '
                        'количестве, только в другом порядке: кот – ток.\n'
                        '\n'
                        '**Ввод:** одна строка – слова через пробел.\n'
                        '**Вывод:** по строке на группу, слова группы через '
                        'пробел в том порядке, в каком они встретились; '
                        'группы – в порядке появления первого слова группы.\n'
                        '\n'
                        '###### Пример ввода\n'
                        '\n'
                        '```text\n'
                        'кот ток лук кто кук\n'
                        '```\n'
                        '\n'
                        '###### Пример вывода\n'
                        '\n'
                        '```text\n'
                        'кот ток кто\n'
                        'лук\n'
                        'кук\n'
                        '```\n'
                        '\n'
                        '**Разбор примера.** Кот, ток и кто – из букв к, о, т, '
                        'поэтому они в одной группе. Лук и кук – разные наборы '
                        'букв, у каждого своя группа.\n'
                        '\n'
                        '**Подсказка.** Ключом словаря может быть кортеж '
                        'отсортированных букв `tuple(sorted(слово))`; список '
                        'ключом быть не может.\n'
                    ),
                    test_cases=[
                        ('кот ток лук кто кук\n', 'кот ток кто\nлук\nкук'),
                        ('eat tea tan ate nat bat\n', 'eat tea ate\ntan nat\nbat'),
                        ('abc\n', 'abc'),
                        ('ab ba ab\n', 'ab ba ab'),
                    ],
                ),
                dict(
                    type='code', title='Задача 19. Самая длинная серия',
                    text=(
                        'У вас коллекция карточек с номерами, некоторые '
                        'дублируются, лежат вперемешку. Какой самый длинный '
                        'ряд карточек с номерами подряд, без пропусков, можно '
                        'выложить?\n'
                        '\n'
                        '**Что найти:** длину самой длинной серии '
                        'последовательных целых чисел (каждое следующее на 1 '
                        'больше), которые все есть в списке; порядок во входе '
                        'не важен, повторы не удлиняют серию.\n'
                        '\n'
                        '**Ввод:** одна строка – целые числа через пробел.\n'
                        '**Вывод:** одно число – длина серии.\n'
                        '\n'
                        '###### Пример ввода\n'
                        '\n'
                        '```text\n'
                        '100 4 200 1 3 2\n'
                        '```\n'
                        '\n'
                        '###### Пример вывода\n'
                        '\n'
                        '```text\n'
                        '4\n'
                        '```\n'
                        '\n'
                        '**Разбор примера.** В списке есть 1, 2, 3, 4 – серия '
                        'из четырёх. Числа 100 и 200 стоят поодиночке, каждая '
                        'серия из них длиной 1, поэтому ответ 4.\n'
                        '\n'
                        '**Подсказка.** Сложите числа в множество и начинайте '
                        'считать серию только с такого $x$, для которого '
                        '$x - 1$ в множестве нет – тогда каждая серия '
                        'считается один раз.\n'
                    ),
                    test_cases=[
                        ('100 4 200 1 3 2\n', '4'),
                        ('0 3 7 2 5 8 4 6 0 1\n', '9'),
                        ('5\n', '1'),
                        ('1 2 2 3\n', '3'),
                        ('-2 -1 10 0 11\n', '3'),
                    ],
                ),
                dict(
                    type='code', title='Задача 20. Отрезки с суммой K',
                    text=(
                        'В списке – изменение баланса кошелька по дням (бывает '
                        'и минус). Сколько есть периодов из нескольких дней '
                        'подряд (можно из одного дня), за которые баланс в '
                        'сумме изменился ровно на $k$?\n'
                        '\n'
                        '**Что найти:** количество непрерывных отрезков с '
                        'суммой ровно $k$. Отрезок – это одно или несколько '
                        'чисел, стоящих в списке подряд.\n'
                        '\n'
                        '**Ввод:** первая строка – целые числа через пробел; '
                        'вторая – целое $k$.\n'
                        '**Вывод:** одно число – сколько таких отрезков.\n'
                        '\n'
                        '###### Пример ввода\n'
                        '\n'
                        '```text\n'
                        '3 4 7 2 -3 1 4 2\n'
                        '7\n'
                        '```\n'
                        '\n'
                        '###### Пример вывода\n'
                        '\n'
                        '```text\n'
                        '4\n'
                        '```\n'
                        '\n'
                        '**Разбор примера.** Подходят четыре отрезка: `3 4`, '
                        '`7`, `7 2 -3 1` и `1 4 2` – сумма каждого равна 7, '
                        'поэтому ответ 4.\n'
                        '\n'
                        '**Подсказка.** Сумма отрезка – разность двух '
                        'префиксных сумм (сумм от начала списка); храните в '
                        'словаре, сколько раз встречалась каждая префиксная '
                        'сумма, и на каждом шаге прибавляйте к ответу, сколько '
                        'раз раньше была сумма «текущая − $k$».\n'
                    ),
                    test_cases=[
                        ('3 4 7 2 -3 1 4 2\n7\n', '4'),
                        ('1 1 1\n2\n', '2'),
                        ('1 2 3\n3\n', '2'),
                        ('1 -1 0\n0\n', '3'),
                        ('5\n4\n', '0'),
                    ],
                ),
            ],
        )
        section.practicum_quiz = quiz
        section.save(update_fields=['practicum_quiz'])
