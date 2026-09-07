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
    # Пропорция кадра. Задачи рассчитаны на разные окна: Task_2 (маятник) –
    # 850x1200, вертикальное, Task_3 (гравитация) – 1200x800. Одна общая
    # пропорция сплющивает половину из них, поэтому она у каждой задачи своя.
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
