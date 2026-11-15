"""Идемпотентный посев полной структуры учебника: 20 блоков и все статьи (только заголовки).

Контент статей не заполняется – создаются лишь заголовки/секции для навигации.
Запуск повторно безопасен: обновляет заголовки и порядок, не плодит дубли.
"""
import re

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Count

from textbook.models import Article, Section

# Транслитерация RU → LAT для ASCII-слагов (маршрут <slug:slug> не принимает кириллицу).
_RU2LAT = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'e',
    'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
    'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
    'ф': 'f', 'х': 'h', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'sch',
    'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya',
}


def slugify_ru(text, maxlen=120):
    text = text.lower()
    out = []
    for ch in text:
        out.append(_RU2LAT.get(ch, ch))
    s = ''.join(out)
    s = re.sub(r'[^a-z0-9]+', '-', s).strip('-')
    return s[:maxlen].strip('-')


# Блоки выше этого номера создаются скрытыми: контент в базе есть, но на сайте
# блок не появится, пока учитель не поставит галку «Опубликовано» в админке.
# Действует только при создании – уже существующим блокам публикацию не меняем.
PUBLISHED_UPTO = 6

# Уже существующие статьи с контентом – сохраняем их slug (не пересоздаём).
_KEEP_SLUG = {
    (5, 2): 'celye-chisla-v-pamyati',
    # Ревизия блока 9 сменила заголовок урока 9.1, а прогресс чтения висит на слаге.
    (9, 1): '9-1-chto-takoe-massiv-i-list-v-python',
}

# (номер блока, заголовок блока, [заголовки статей])
STRUCTURE = [
    (1, "Блок 1. Введение в информатику и Python", [
        "Что такое информатика?",
        "Устройство компьютера: принципы фон Неймана",
        "Техника безопасности и гигиена",
        "Настройка IDE и первая программа",
        "Переменные и динамическая типизация",
        "Целые числа int и вещественные float",
        "Ввод и вывод данных",
        "Строки str – первое знакомство",
    ]),
    (2, "Блок 2. Системы счисления", [
        "Что такое позиционная система счисления?",
        "Двоичная система",
        "Восьмеричная и шестнадцатеричная системы",
        "Перевод из любой СС в десятичную",
        "Перевод из десятичной в любую СС",
        "Быстрый перевод через Python",
    ]),
    (3, "Блок 3. Алгебра логики", [
        "Что такое логическое высказывание?",
        "Базовые операции: НЕ, И, ИЛИ",
        "Сложные операции: импликация и эквивалентность",
        "Законы алгебры логики",
        "Физическая реализация логики",
        "Ветвления в Python: if / elif / else",
        "Логические операторы в Python: and, or, not",
        "Программное вычисление логических выражений",
    ]),
    (4, "Блок 4. Циклы в Python", [
        "Зачем нужны циклы?",
        "Цикл while",
        "Применение while: работа с числами",
        "Цикл for и функция range()",
        "break, continue, else в циклах",
        "Задачи с циклами: алгоритмы на числах",
        "Вложенные циклы",
        "Перебор диапазонов: минимум, максимум и поиск по условию",
    ]),
    (5, "Блок 5. Представление чисел в памяти", [
        "Бит, байт, машинное слово",
        "Целые числа в памяти",
        "Вещественные числа: стандарт IEEE 754",
    ]),
    (6, "Блок 6. Побитовые операции", [
        "Побитовые AND, OR, XOR, NOT",
        "Операции сдвига << и >>",
        "Битовые маски",
        "Задачи на быстрые вычисления",
    ]),
    (7, "Блок 7. Кодирование информации", [
        "Алфавитный подход к измерению информации",
        "История кодирования текста: ASCII",
        "Unicode и UTF-8",
        "Неравномерное кодирование",
        "Алгоритм Хаффмана",
        "Кодирование звука",
        "Кодирование изображений",
    ]),
    (8, "Блок 8. Строки, файлы и регулярные выражения", [
        "Строки: символы, индексы и срезы",
        "Методы строк: поиск, замена, разбиение",
        "Алгоритмические задачи со строками",
        "Файлы: чтение и запись",
        "Модули и библиотеки: import",
        "Регулярные выражения: язык шаблонов",
        "Регулярные выражения на практике",
    ]),
    (9, "Блок 9. Списки, кортежи, множества и словари", [
        "Списки: индексы, срезы и изменяемость",
        "Методы списков и встроенные функции",
        "Списочные выражения и вложенные списки",
        "Кортежи",
        "Множества",
        "Словари",
    ]),
    # Бывшие блоки 10 «Анализ сложности» и 11 «Алгоритмы сортировки» слиты
    # (2026-11-15): сложность – инструмент, сортировки – материал, на котором
    # им пользуются. Номера блоков дальше сдвинуты на один – см. _merge_blocks_10_11.
    (10, "Блок 10. Сложность алгоритмов и сортировка", [
        "Сложность алгоритма и O-нотация",
        "Как оценить сложность по коду",
        "Простые сортировки: пузырьком, выбором, вставками",
        "Быстрая сортировка",
        "Двоичный поиск",
        "Встроенная сортировка: sorted, sort и key",
    ]),
    (11, "Блок 11. Функции в Python", [
        "Зачем нужны функции?",
        "Объявление функции: def, аргументы, return",
        "Рекурсия: базовые понятия",
        "Стек вызовов и Stack Overflow",
        "Числа Фибоначчи: рекурсия vs итерация",
    ]),
    (12, "Блок 12. Теория графов", [
        # Бывшие 13.1–13.3 (что такое граф, виды, представление) слиты в один
        # урок: по отдельности на каждый набиралось по паре абзацев.
        "Что такое граф?",
        "Структуры данных Python: set и dict",
        "Обход в ширину (BFS)",
        "Обход в глубину (DFS)",
        "Задачи на графах",
    ]),
    (13, "Блок 13. Компьютерные сети", [
        "Зачем нужны компьютерные сети?",
        "Физический уровень передачи данных",
        "Модель OSI: 7 уровней",
        "Стек TCP/IP",
        "IP-адресация (IPv4)",
        "Маски подсетей",
        "Прикладной уровень: HTTP и HTTPS",
        "Служба DNS",
        "Протоколы транспортного уровня: TCP и UDP",
        "Практика: сетевые утилиты",
        "Основы сетевой безопасности",
        "Сетевое программирование: библиотека requests",
    ]),
    (14, "Блок 14. Веб-разработка: HTML и CSS", [
        "Как работает веб?",
        "Front-end vs Back-end",
        "Структура HTML-документа",
        "Семантическая разметка HTML5",
        "Медиа и гиперссылки",
        "Формы и интерактивные элементы",
        "Введение в CSS3",
        "Селекторы CSS",
        "Практический проект: страница-резюме",
    ]),
    (15, "Блок 15. ИИ и машинное обучение", [
        "История и философия ИИ",
        "Классические алгоритмы vs машинное обучение",
        "Направления МО",
        "Биологический нейрон и его модель",
        "Перцептрон Розенблатта",
        "Обучение перцептрона",
        "Программирование перцептрона на Python",
        "Глубокое обучение: TensorFlow и Keras",
        "Проект: распознавание цифр (MNIST)",
    ]),
    (16, "Блок 16. Теория игр", [
        "Что изучает теория игр?",
        "Равновесие Нэша",
        "Дерево игры",
        "Игра Ним с двумя кучами",
        "Алгоритмизация: программа на Python",
    ]),
    (17, "Блок 17. Динамическое программирование", [
        "Идея динамического программирования",
        "Мемоизация (Top-down)",
        "Таблицы (Bottom-up)",
        "Задача о монетах (размен)",
        "Робот в прямоугольной таблице",
        "Задача о рюкзаке/монетах с минимумом монет",
        "LCS и LIS",
    ]),
    (18, "Блок 18. Data Science и анализ данных", [
        "Введение в Data Science",
        "Работа с файлами в Python",
        "NumPy: векторизованные вычисления",
        "Matplotlib: визуализация данных",
        "Численные методы: уравнения",
        "Численное интегрирование",
        "Оптимизация: метод золотого сечения",
        "Метод наименьших квадратов",
        "Моделирование физических процессов",
        "Excel как инструмент анализа",
        "Кластеризация данных (k-means)",
    ]),
    (19, "Блок 19. Базы данных и SQL", [
        "Зачем нужны базы данных?",
        "Таблицы, поля, записи",
        "Первичный и внешний ключи",
        "Виды связей между таблицами",
        "Введение в SQL",
        "Выборка данных: SELECT",
        "Фильтрация: WHERE",
        "Сортировка и ограничение",
        "Агрегатные функции",
        "Группировка: GROUP BY и HAVING",
        "Python + SQLite3",
        "Итоговый проект: Python-скрипт с БД",
    ]),
    (20, "Блок 20. Объектно-ориентированное программирование (ООП)", [
        "Зачем нужно ООП?",
        "Класс и объект",
        "Атрибуты и методы",
        "Инкапсуляция",
        "Наследование",
        "Полиморфизм",
        "Проектирование ООП-приложения",
        "GUI на Python: знакомство с Tkinter/PyQt",
        "Интеграция GUI + БД",
        "Тестирование и код-ревью",
    ]),
]


# Слияние блоков 10 и 11 (2026-11-15). Старые статьи обоих блоков удаляются
# вместе с прогрессом чтения – решение Кирилла, как и в блоке 9: снятые с
# публикации, они висели бы у учителя в сайдбаре дублями новых уроков.
_OLD_10_SLUGS = [
    '10-1-chto-takoe-slozhnost-algoritma',
    '10-2-o-notatsiya-big-o',
    '10-3-zamer-vremeni-raboty-v-python',
]
_OLD_11_TITLE = 'Блок 11. Алгоритмы сортировки'

# Блоки 12–21 стали 11–20. Раздел и его статьи переименовываются на месте, а не
# создаются заново: прогресс и ответы висят на id, а не на слаге. Узнаём раздел
# по СТАРОМУ полному заголовку – после переименования blok-12 снова существует
# (бывший 13), и проверка по одному слагу сдвинула бы его второй раз.
_SHIFTED_TITLES = {
    12: 'Блок 12. Функции в Python',
    13: 'Блок 13. Теория графов',
    14: 'Блок 14. Компьютерные сети',
    15: 'Блок 15. Веб-разработка: HTML и CSS',
    16: 'Блок 16. ИИ и машинное обучение',
    17: 'Блок 17. Теория игр',
    18: 'Блок 18. Динамическое программирование',
    19: 'Блок 19. Data Science и анализ данных',
    20: 'Блок 20. Базы данных и SQL',
    21: 'Блок 21. Объектно-ориентированное программирование (ООП)',
}


def _merge_blocks_10_11(stdout):
    from quizzes.models import Quiz, UserResult
    from textbook.models import ArticleQuiz

    old = Article.objects.filter(slug__in=_OLD_10_SLUGS) | Article.objects.filter(
        section__slug='blok-11', section__title=_OLD_11_TITLE)
    if old.exists():
        quiz_ids = list(ArticleQuiz.objects.filter(article__in=old).values_list('quiz_id', flat=True))
        n = old.count()
        old.delete()
        # Самопроверки, на которые уже отвечали, остаются в базе без статьи.
        Quiz.objects.filter(id__in=quiz_ids).exclude(
            id__in=UserResult.objects.values('quiz_id')).delete()
        stdout.write(f'Старые статьи блоков 10–11 удалены: {n}.')
    Section.objects.filter(slug='blok-11', title=_OLD_11_TITLE, articles__isnull=True).delete()

    for old_no in sorted(_SHIFTED_TITLES):
        section = Section.objects.filter(slug=f'blok-{old_no}', title=_SHIFTED_TITLES[old_no]).first()
        if not section:
            continue
        new_no = old_no - 1
        section.slug = f'blok-{new_no}'
        section.order = new_no
        section.save(update_fields=['slug', 'order'])
        for art in section.articles.filter(slug__startswith=f'{old_no}-'):
            art.slug = f'{new_no}-' + art.slug[len(f'{old_no}-'):]
            art.save(update_fields=['slug'])
        stdout.write(f'Блок {old_no} стал блоком {new_no}.')


class Command(BaseCommand):
    help = "Создаёт полную структуру учебника (20 блоков + все статьи, только заголовки)."

    @transaction.atomic
    def handle(self, *args, **options):
        _merge_blocks_10_11(self.stdout)
        sections_created = articles_created = articles_updated = 0
        expected_slugs = []

        for block_no, section_title, article_titles in STRUCTURE:
            section, sec_created = Section.objects.get_or_create(
                slug=f'blok-{block_no}',
                defaults={'title': section_title, 'order': block_no,
                          'is_published': block_no <= PUBLISHED_UPTO},
            )
            if sec_created:
                sections_created += 1
            else:
                # держим заголовок/порядок в актуальном состоянии
                if section.title != section_title or section.order != block_no:
                    section.title = section_title
                    section.order = block_no
                    section.save(update_fields=['title', 'order'])

            for idx, art_title in enumerate(article_titles, start=1):
                slug = _KEEP_SLUG.get((block_no, idx)) or slugify_ru(f'{block_no}-{idx}-{art_title}')
                expected_slugs.append(slug)
                art, created = Article.objects.get_or_create(
                    slug=slug,
                    defaults={
                        'track': 'material',
                        'section': section,
                        'title': art_title,
                        'order': idx,
                        'is_published': True,
                    },
                )
                if created:
                    articles_created += 1
                else:
                    # привязываем к каноническому блоку и выравниваем порядок,
                    # не трогая уже заполненный контент
                    fields = []
                    if art.section_id != section.id:
                        art.section = section; fields.append('section')
                    if art.order != idx:
                        art.order = idx; fields.append('order')
                    if art.track != 'material':
                        art.track = 'material'; fields.append('track')
                    if fields:
                        art.save(update_fields=fields)
                        articles_updated += 1

        # Подчищаем сирот: статьи учебных блоков, которых больше нет в STRUCTURE
        # (тему переименовали, объединили или выкинули). Удаляем только полностью
        # пустые – с контентом, самопроверкой или прогрессом ученика не трогаем,
        # чтобы правка STRUCTURE никогда не стирала чью-то работу.
        orphans = Article.objects.filter(
            track='material',
            section__slug__in=[f'blok-{no}' for no, _, _ in STRUCTURE],
        ).exclude(slug__in=expected_slugs).annotate(
            n_blocks=Count('blocks', distinct=True),
            n_quizzes=Count('self_check_quizzes', distinct=True),
            n_progress=Count('progress', distinct=True),
        ).filter(n_blocks=0, n_quizzes=0, n_progress=0)
        orphan_slugs = list(orphans.values_list('slug', flat=True))
        if orphan_slugs:
            Article.objects.filter(slug__in=orphan_slugs).delete()
            self.stdout.write(self.style.WARNING(
                'Удалены пустые статьи вне STRUCTURE: ' + ', '.join(orphan_slugs)
            ))

        # Удаляем старую демо-секцию, если её статьи переехали в blok-5
        legacy = Section.objects.filter(slug='predstavlenie-chisel').first()
        if legacy and not legacy.articles.exists():
            legacy.delete()

        self.stdout.write(self.style.SUCCESS(
            f'Готово. Блоков создано: {sections_created}, '
            f'статей создано: {articles_created}, обновлено: {articles_updated}, '
            f'сирот удалено: {len(orphan_slugs)}. '
            f'Всего блоков: {Section.objects.count()}, статей: {Article.objects.count()}.'
        ))
