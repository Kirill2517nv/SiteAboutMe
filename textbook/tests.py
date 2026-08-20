"""Тесты учебника. Запуск: python manage.py test textbook"""
from django.test import SimpleTestCase, TestCase, override_settings

from quizzes.models import Question, Quiz
from textbook.models import Section
from textbook.services import frontier_positions, shuffle_choices, sync_question_texts
from textbook.templatetags.textbook_tags import markdownify


class UngluedListsTest(SimpleTestCase):
    """Список, приклеенный к абзацу без пустой строки, всё равно должен стать <ul>.

    Контент учебника написан именно так, а чистый Markdown в этом случае видит
    продолжение абзаца — с nl2br дефисы выводились как текст.
    """

    def test_list_glued_to_paragraph_becomes_list(self):
        html = markdownify('Встречается на каждом шагу:\n'
                           '- азбука Морзе;\n'
                           '- картотека в библиотеке.')
        self.assertIn('<ul>', html)
        self.assertEqual(html.count('<li>'), 2)

    def test_numbered_list_too(self):
        html = markdownify('Порядок такой:\n1. выборка;\n2. декодирование.')
        self.assertIn('<ol>', html)
        self.assertEqual(html.count('<li>'), 2)

    def test_normal_markdown_still_works(self):
        html = markdownify('Абзац.\n\n- пункт;\n- пункт.')
        self.assertEqual(html.count('<li>'), 2)

    def test_dashes_inside_fenced_code_are_not_touched(self):
        """В блоках кода дефис начинает строку столбика вычитания, не список."""
        html = markdownify('Вычитание единицы:\n\n```\n  00001100   (12)\n'
                           '- 00000001   (1)\n= 00001011   (11)\n```')
        self.assertNotIn('<li>', html)
        self.assertIn('<code>', html)


class SyncQuestionTextsTest(TestCase):
    """Условия задач должны обновляться и там, где ответы учеников уже есть."""

    def setUp(self):
        self.quiz = Quiz.objects.create(title='Практикум', slug='p-test')
        for i in (1, 2):
            Question.objects.create(quiz=self.quiz, question_type='text',
                                    title=f'Задача {i}', text=f'Старое условие {i}')

    def test_texts_updated_in_place(self):
        specs = [dict(title='Задача 1', text='Новое **условие** 1'),
                 dict(title='Задача 2', text='Новое **условие** 2')]
        self.assertEqual(sync_question_texts(self.quiz, specs), 2)
        self.assertEqual(
            [q.text for q in self.quiz.questions.order_by('id')],
            ['Новое **условие** 1', 'Новое **условие** 2'],
        )

    def test_nothing_touched_when_count_differs(self):
        """Набор задач правили руками — сопоставлять по порядку уже нельзя."""
        self.assertEqual(sync_question_texts(self.quiz, [dict(title='Задача 1', text='X')]), 0)
        self.assertEqual(self.quiz.questions.order_by('id').first().text, 'Старое условие 1')


class GradeScaleTest(SimpleTestCase):
    """Шкала «сколько задач на какую оценку» — то, что видит ученик в блоке."""

    section = Section(grade_5_from=12, grade_4_from=9, grade_3_from=6)

    def test_shows_all_thresholds_with_reached_marked(self):
        scale = self.section.grade_scale(7)
        self.assertEqual([(s['grade'], s['need'], s['reached']) for s in scale],
                         [(5, 12, False), (4, 9, False), (3, 6, True)])

    def test_no_scale_without_thresholds(self):
        self.assertEqual(Section().grade_scale(5), [])


class FrontierPositionsTest(TestCase):
    """Аватарка едет только по непрерывному маршруту от начала учебника."""

    @classmethod
    def setUpTestData(cls):
        from django.contrib.auth.models import User

        from accounts.models import Profile, StudentGroup
        from textbook.models import Article, ArticleProgress, ArticleQuiz

        cls.group = StudentGroup.objects.create(name='11А')
        cls.student = User.objects.create_user('vasya')
        Profile.objects.update_or_create(user=cls.student, defaults={'group': cls.group})

        section = Section.objects.create(title='Блок 1', slug='b1', order=1, is_published=True)
        cls.articles = [
            Article.objects.create(section=section, slug=f'a{i}', title=f'Урок {i}',
                                   order=i, is_published=True)
            for i in (1, 2, 3)
        ]
        # У первых двух статей есть самопроверка на 2 вопроса, у третьей теста нет.
        cls.quizzes = []
        for article in cls.articles[:2]:
            quiz = Quiz.objects.create(title=f'СП {article.slug}', is_self_check=True)
            for n in (1, 2):
                Question.objects.create(quiz=quiz, text=f'Вопрос {n}', correct_text_answer='1')
            ArticleQuiz.objects.create(article=article, quiz=quiz)
            cls.quizzes.append(quiz)
        cls.progress_model = ArticleProgress

    def solve(self, quiz, correct_count):
        from quizzes.models import UserAnswer, UserResult

        result = UserResult.objects.create(user=self.student, quiz=quiz, score=correct_count)
        for i, question in enumerate(quiz.questions.order_by('id')):
            UserAnswer.objects.create(user_result=result, question=question,
                                      text_answer='1', is_correct=i < correct_count)

    def position(self):
        positions = frontier_positions([self.group.id])
        return next((aid for aid, users in positions.items() if self.student in users), None)

    def test_starts_at_first_article(self):
        self.assertEqual(self.position(), self.articles[0].id)

    def test_half_correct_is_enough_to_move_on(self):
        """Жёлтый уровень (1 из 2) уже засчитывается — это и есть порог «более 50%»."""
        self.solve(self.quizzes[0], 1)
        self.assertEqual(self.position(), self.articles[1].id)

    def test_below_half_does_not_move(self):
        self.solve(self.quizzes[0], 0)
        self.assertEqual(self.position(), self.articles[0].id)

    def test_jump_ahead_does_not_move_the_pin(self):
        """Ученик перепрыгнул на второй урок — фишка осталась на первом."""
        self.solve(self.quizzes[1], 2)
        self.assertEqual(self.position(), self.articles[0].id)

    def test_article_without_self_check_falls_back_to_read(self):
        self.solve(self.quizzes[0], 2)
        self.solve(self.quizzes[1], 2)
        self.assertEqual(self.position(), self.articles[2].id)
        self.progress_model.objects.create(user=self.student, article=self.articles[2],
                                           status='read')
        self.assertIsNone(self.position(), 'маршрут пройден целиком — фишки быть не должно')

    def test_other_groups_are_invisible(self):
        self.assertEqual(frontier_positions([self.group.id + 99]), {})
        self.assertEqual(frontier_positions([]), {})


class ShuffleChoicesTest(SimpleTestCase):
    """Варианты ответа перемешиваются: в сидах правильный всегда написан первым.

    Порядок обязан быть детерминированным — иначе каждый прогон
    seed_textbook_blockN переставлял бы ученику варианты заново.
    """

    CHOICES = [('верно', True), ('неверно', False), ('тоже нет', False), ('и нет', False)]

    def test_order_is_stable_for_same_question(self):
        first = shuffle_choices('Сколько будет 2 + 2?', self.CHOICES)
        second = shuffle_choices('Сколько будет 2 + 2?', self.CHOICES)
        self.assertEqual(first, second)

    def test_nothing_is_lost_or_duplicated(self):
        self.assertEqual(sorted(shuffle_choices('вопрос', self.CHOICES)), sorted(self.CHOICES))

    def test_correct_answer_is_not_always_first(self):
        positions = set()
        for i in range(30):
            mixed = shuffle_choices('Вопрос номер %d' % i, self.CHOICES)
            positions.add(next(n for n, c in enumerate(mixed) if c[1]))
        self.assertEqual(positions, {0, 1, 2, 3})

    def test_input_list_is_not_mutated(self):
        original = list(self.CHOICES)
        shuffle_choices('вопрос', self.CHOICES)
        self.assertEqual(self.CHOICES, original)


class HintStateTest(TestCase):
    """Подсказка не существует для ученика, пока он не упрётся в задачу сам."""

    def setUp(self):
        from django.contrib.auth.models import User

        self.user = User.objects.create_user('vasya', password='x')
        self.quiz = Quiz.objects.create(title='Практикум', is_self_check=True)
        self.section = Section.objects.create(
            title='Блок', slug='blok-test', practicum_quiz=self.quiz, is_published=True
        )
        self.question = Question.objects.create(
            quiz=self.quiz, question_type='code', title='Задача 1',
            text='Условие', hint='Разложите число на цифры.',
        )

    def _fail(self, times):
        from quizzes.models import CodeSubmission

        for _ in range(times):
            CodeSubmission.objects.create(
                user=self.user, question=self.question, quiz=self.quiz,
                code='print()', status='failed',
            )

    def test_closed_until_three_failures(self):
        from textbook.services import hint_state

        self.assertIsNone(hint_state(self.user, self.question))
        self._fail(2)
        self.assertIsNone(hint_state(self.user, self.question))
        self._fail(1)
        self.assertEqual(hint_state(self.user, self.question), 'offer')

    def test_choice_is_remembered(self):
        from quizzes.models import HintChoice
        from textbook.services import hint_state

        self._fail(3)
        HintChoice.objects.create(user=self.user, question=self.question, accepted=False)
        self.assertEqual(hint_state(self.user, self.question), 'declined')
        HintChoice.objects.update(accepted=True)
        self.assertEqual(hint_state(self.user, self.question), 'taken')

    def test_deadline_and_switch_open_without_failures(self):
        from datetime import timedelta

        from django.utils import timezone

        from textbook.services import hint_state

        self.section.deadline = timezone.now() + timedelta(days=4)
        self.section.save(update_fields=['deadline'])
        self.assertIsNone(hint_state(self.user, self.question))

        self.section.deadline = timezone.now() + timedelta(days=2)
        self.section.save(update_fields=['deadline'])
        self.assertEqual(hint_state(self.user, self.question), 'offer')

        self.section.deadline = None
        self.section.hints_open = True
        self.section.save(update_fields=['deadline', 'hints_open'])
        self.assertEqual(hint_state(self.user, self.question), 'offer')

    def test_view_does_not_leak_text_before_choice(self):
        self.client.force_login(self.user)
        url = f'/quizzes/question/{self.question.id}/hint/'

        # Закрыта: ни состояния, ни текста.
        data = self.client.get(url).json()
        self.assertIsNone(data['state'])
        self.assertNotIn('hint', data)

        # Открыта, но выбор не сделан — текста всё ещё нет.
        self._fail(3)
        data = self.client.get(url).json()
        self.assertEqual(data['state'], 'offer')
        self.assertNotIn('hint', data)

        # Отказ фиксируется, текст не отдаётся.
        data = self.client.post(url, '{"action": "decline"}',
                                content_type='application/json').json()
        self.assertEqual(data['state'], 'declined')
        self.assertNotIn('hint', data)

        # Согласие — текст приходит.
        data = self.client.post(url, '{"action": "take"}',
                                content_type='application/json').json()
        self.assertEqual(data['state'], 'taken')
        self.assertIn('цифры', data['hint'])

    def test_hidden_section_hides_hint_even_when_block_is_open(self):
        """Рубильник «подсказки блока» открыт, но сам блок ещё не показан ученикам.

        Условия открытия подсказки блочные и не зависят от попыток ученика,
        поэтому без проверки публикации перебор question_id вытаскивал бы
        подсказки к задачам ненапечатанных блоков.
        """
        self.section.hints_open = True
        self.section.is_published = False
        self.section.save(update_fields=['hints_open', 'is_published'])

        self.client.force_login(self.user)
        url = f'/quizzes/question/{self.question.id}/hint/'
        data = self.client.post(url, '{"action": "take"}',
                                content_type='application/json').json()
        self.assertIsNone(data['state'])
        self.assertNotIn('hint', data)


# Манифест whitenoise существует только после collectstatic — тестам, которые
# дорисовывают страницу до конца, хватит обычной раздачи статики.
@override_settings(STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
})
class HiddenSectionAccessTest(TestCase):
    """Спрятанный блок не отдаёт содержимое по прямым ссылкам.

    На главной его нет, но URL статьи и id теста предсказуемы — гейт должен
    стоять во вьюхах, а не только в списке.
    """

    def setUp(self):
        from django.contrib.auth.models import User

        from textbook.models import Article

        self.user = User.objects.create_user('petya', password='x')
        self.quiz = Quiz.objects.create(title='Практикум 13', is_self_check=True)
        self.hidden = Section.objects.create(
            title='Блок 13', slug='blok-13', order=13,
            practicum_quiz=self.quiz, is_published=False,
        )
        self.article = Article.objects.create(
            track='material', section=self.hidden, slug='13-1-grafy',
            title='Что такое граф?', order=1, is_published=True,
        )

    def test_article_of_hidden_section_is_404(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get('/textbook/article/13-1-grafy/').status_code, 404)

    def test_progress_endpoints_reject_hidden_article(self):
        self.client.force_login(self.user)
        self.assertEqual(
            self.client.post('/textbook/article/13-1-grafy/read/').status_code, 404)
        self.assertEqual(
            self.client.post('/textbook/article/13-1-grafy/time/', {'seconds': 60}).status_code,
            404)

    def test_practicum_of_hidden_section_is_not_accessible(self):
        from textbook.services import quiz_is_hidden

        self.assertTrue(quiz_is_hidden(self.quiz))
        self.client.force_login(self.user)
        response = self.client.get(f'/quizzes/{self.quiz.id}/')
        self.assertEqual(response.status_code, 302)

    def test_teacher_can_proofread_hidden_block(self):
        """Учитель вычитывает неопубликованный блок на самом сайте, а не в админке."""
        from django.contrib.auth.models import User

        teacher = User.objects.create_superuser('teacher', 'a@b.c', 'x')
        self.client.force_login(teacher)
        self.assertEqual(self.client.get('/textbook/article/13-1-grafy/').status_code, 200)
        self.assertEqual(self.client.get(f'/quizzes/{self.quiz.id}/').status_code, 200)

    def test_publishing_the_section_opens_everything(self):
        self.hidden.is_published = True
        self.hidden.save(update_fields=['is_published'])

        self.client.force_login(self.user)
        self.assertEqual(self.client.get('/textbook/article/13-1-grafy/').status_code, 200)
        self.assertEqual(self.client.get(f'/quizzes/{self.quiz.id}/').status_code, 200)


class ReadingTimeTest(TestCase):
    """Время чтения ограничено серверными часами, а не только размером порции."""

    def setUp(self):
        from django.contrib.auth.models import User

        from textbook.models import Article

        self.user = User.objects.create_user('masha', password='x')
        self.section = Section.objects.create(
            title='Блок 1', slug='blok-1', order=1, is_published=True)
        self.article = Article.objects.create(
            track='material', section=self.section, slug='1-1-vvedenie',
            title='Введение', order=1, is_published=True,
        )
        self.client.force_login(self.user)

    def _post(self, seconds):
        return self.client.post('/textbook/article/1-1-vvedenie/time/', {'seconds': seconds})

    def test_repeated_posts_cannot_inflate_time(self):
        from textbook.models import ArticleProgress

        for _ in range(10):
            self._post(300)

        total = ArticleProgress.objects.get(user=self.user, article=self.article).time_spent_seconds
        # Первая порция идёт целиком (прогресса ещё не было), дальше бюджет
        # упирается в реально прошедшее время — то есть почти в ноль.
        self.assertLess(total, 400)
