from django.db import models
from django.urls import reverse


class CourseTask(models.Model):
    """Задача спецкурса – единица курса.

    Одна задача связывает четыре вещи, которые раньше жили порознь: физику
    (статьи учебника с track='spetskurs'), исходник (Task_N/main.cpp в
    репозитории GuiLibrary), симуляцию (WASM-сборка того же исходника) и
    задания (текстовый блок статьи, который преподаватель показывает и
    спрашивает лично).

    Раньше модель называлась Simulation и означала только третий пункт. Теория
    жила в отдельных TheoryPage/TheoryBlock – урезанной копии
    textbook.Article/ArticleBlock, из которой учебник когда-то и вырос
    (см. docstring textbook.ArticleBlock). Копию удалили, теория переехала на
    модели учебника, и здесь остался якорь трека – ровно та роль, которую для
    вкладки ЕГЭ играет textbook.EgeTask.
    """

    SEMESTER_CHOICES = [(1, 'Семестр 1'), (2, 'Семестр 2')]

    slug = models.SlugField(max_length=100, unique=True, verbose_name="URL-идентификатор")
    title = models.CharField(max_length=200, verbose_name="Название задачи")
    number = models.PositiveSmallIntegerField(
        null=True, blank=True, verbose_name="Номер задачи",
        help_text="Показывается как «Задача 2». Пусто – номер не выводится"
    )
    description = models.TextField(blank=True, verbose_name="Описание")
    thumbnail = models.ImageField(
        upload_to='spetskurs/tasks/', blank=True, null=True,
        verbose_name="Превью изображение"
    )

    html_path = models.CharField(
        max_length=300, blank=True, verbose_name="Путь к HTML-файлу симуляции",
        help_text="Относительный путь в static/, например: spetskurs/wasm/Task_2.html"
    )
    # Пропорция кадра. Задачи рассчитаны на разные окна: маятник – 1400x900,
    # пульт слева, маятник и фазовая диаграмма рядом, Task_3 (гравитация) –
    # 1200x800. Одна общая пропорция сплющивает половину из них, поэтому она
    # у каждой задачи своя.
    #
    # Кадр показывает витрину (сборку с решёнными заданиями), а не исходник
    # задания: у маятника это Demo_Pendulum, и окно у неё своё. Исходник
    # Task_2, который разбирают статьи, – вертикальные 850x1200.
    frame_width = models.PositiveSmallIntegerField(
        default=16, verbose_name="Пропорция кадра: ширина"
    )
    frame_height = models.PositiveSmallIntegerField(
        default=10, verbose_name="Пропорция кадра: высота"
    )

    code_url = models.URLField(
        blank=True, verbose_name="Ссылка на исходник",
        help_text="main.cpp этой задачи на GitHub"
    )

    semester = models.PositiveSmallIntegerField(
        choices=SEMESTER_CHOICES, default=1, verbose_name="Семестр"
    )
    order = models.PositiveIntegerField(default=0, verbose_name="Порядок")
    is_published = models.BooleanField(default=False, verbose_name="Опубликовано")

    class Meta:
        ordering = ['semester', 'order']
        verbose_name = "Задача спецкурса"
        verbose_name_plural = "Задачи спецкурса"

    def __str__(self):
        return f"Задача {self.number}. {self.title}" if self.number else self.title

    def get_absolute_url(self):
        return reverse('spetskurs:task_detail', kwargs={'slug': self.slug})

    @property
    def frame_ratio(self):
        """Значение для CSS aspect-ratio. Собирается из двух чисел, а не хранится
        строкой: строка из админки попала бы в атрибут style как есть."""
        return f"{self.frame_width} / {self.frame_height}"


class ProjectTopic(models.Model):
    """Тема проекта второго семестра – карточка на /spetskurs/projects/.

    Ученическая часть (явление, где встречается, исследование, результат,
    этапы) видна всем; teacher_notes – только суперпользователю, и шаблон не
    выводит её вовсе, а не прячет стилями: страницу открывают ученики.
    Текст пишет seed_spetskurs_projects, как и весь контент сайта.
    """

    GROUP_CHOICES = [
        ('coulomb', 'Кулоновское взаимодействие'),
        ('stat', 'Статистические методы'),
        ('grid', 'Поля на сетке'),
        ('dynamics', 'Динамика и хаос'),
    ]
    DIFFICULTY_CHOICES = [(2, '★★'), (3, '★★★')]

    slug = models.SlugField(max_length=100, unique=True, verbose_name="URL-идентификатор")
    number = models.PositiveSmallIntegerField(verbose_name="Номер")
    title = models.CharField(max_length=200, verbose_name="Название")
    group = models.CharField(max_length=20, choices=GROUP_CHOICES, verbose_name="Раздел")
    difficulty = models.PositiveSmallIntegerField(
        choices=DIFFICULTY_CHOICES, default=2, verbose_name="Сложность")
    teaser = models.CharField(max_length=300, verbose_name="Зацепка для карточки")
    phenomenon = models.TextField(verbose_name="Что за явление")
    where = models.TextField(verbose_name="Где встречается")
    research = models.TextField(verbose_name="Что вы исследуете")
    result = models.TextField(verbose_name="Что получится в конце")
    steps = models.TextField(verbose_name="Этапы работы (Markdown)")
    teacher_notes = models.TextField(blank=True, verbose_name="Заметки учителя (Markdown)")
    is_published = models.BooleanField(default=True, verbose_name="Опубликовано")

    class Meta:
        ordering = ['number']
        verbose_name = "Тема проекта"
        verbose_name_plural = "Темы проектов"

    def __str__(self):
        return f"{self.number}. {self.title}"

    def get_absolute_url(self):
        return reverse('spetskurs:project_detail', kwargs={'slug': self.slug})


class ProjectImage(models.Model):
    """Иллюстрация темы. Чужая картинка – значит, автор, лицензия и ссылка
    обязательны: подпись под ней – условие лицензии CC BY, а не украшение."""

    topic = models.ForeignKey(ProjectTopic, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='spetskurs/projects/', verbose_name="Файл")
    caption = models.CharField(max_length=300, verbose_name="Подпись")
    author = models.CharField(max_length=200, blank=True, verbose_name="Автор")
    license = models.CharField(max_length=60, verbose_name="Лицензия")
    source_url = models.URLField(verbose_name="Источник")
    order = models.PositiveSmallIntegerField(default=0, verbose_name="Порядок")

    class Meta:
        ordering = ['order']
        verbose_name = "Иллюстрация"
        verbose_name_plural = "Иллюстрации"

    def __str__(self):
        return self.caption
