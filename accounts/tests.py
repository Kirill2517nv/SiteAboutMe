import io
import os
import tempfile
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from PIL import Image

from accounts.models import Profile, StudentGroup
from quizzes.models import Question, Quiz, UserAnswer, UserResult
from textbook.models import Article, ArticleProgress, Section
from textbook.services import profile_textbook_stats

# Боевое хранилище статики требует прогнанного collectstatic — тестам он не нужен.
NO_MANIFEST_STATIC = override_settings(STORAGES={
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
})


@NO_MANIFEST_STATIC
class ProfileAccessTests(TestCase):
    """Чужой профиль виден только учителю (суперпользователю)."""

    @classmethod
    def setUpTestData(cls):
        cls.student = User.objects.create_user('student', password='pw')
        cls.other = User.objects.create_user('other', password='pw')
        cls.teacher = User.objects.create_superuser('teacher', password='pw')

    def test_own_profile_ok(self):
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(reverse('accounts:profile')).status_code, 200)

    def test_student_cannot_open_foreign_profile(self):
        self.client.force_login(self.student)
        response = self.client.get(
            reverse('accounts:student_profile', args=[self.other.id])
        )
        self.assertEqual(response.status_code, 403)

    def test_student_can_open_own_profile_by_id(self):
        self.client.force_login(self.student)
        response = self.client.get(
            reverse('accounts:student_profile', args=[self.student.id])
        )
        self.assertEqual(response.status_code, 200)

    def test_teacher_opens_student_profile(self):
        self.client.force_login(self.teacher)
        response = self.client.get(
            reverse('accounts:student_profile', args=[self.student.id])
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['profile_user'], self.student)
        self.assertFalse(response.context['is_own'])

    def test_anonymous_redirected(self):
        response = self.client.get(reverse('accounts:profile'))
        self.assertEqual(response.status_code, 302)


def _png(color='red', name='pic.png'):
    buffer = io.BytesIO()
    Image.new('RGB', (10, 10), color).save(buffer, 'PNG')
    return SimpleUploadedFile(name, buffer.getvalue(), content_type='image/png')


@NO_MANIFEST_STATIC
@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class AvatarUploadTests(TestCase):
    """Аватар: файлы не копятся, а не-картинка не проходит."""

    def setUp(self):
        self.student = User.objects.create_user('av', password='pw')
        self.client.force_login(self.student)

    def _avatar_name(self):
        return Profile.objects.get(user=self.student).avatar.name

    def _on_disk(self, name):
        return os.path.exists(os.path.join(settings.MEDIA_ROOT, name))

    def test_old_file_deleted_on_replace(self):
        self.client.post(reverse('accounts:profile'), {'avatar': _png('red')})
        first = self._avatar_name()
        self.client.post(reverse('accounts:profile'), {'avatar': _png('blue')})
        second = self._avatar_name()

        self.assertNotEqual(first, second)
        self.assertFalse(self._on_disk(first), 'старый аватар остался на диске')
        self.assertTrue(self._on_disk(second))

    def test_broken_image_rejected(self):
        response = self.client.post(reverse('accounts:profile'), {
            'avatar': SimpleUploadedFile('evil.png', b'MZ not an image',
                                         content_type='image/png'),
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['avatar_error'])
        self.assertEqual(self._avatar_name(), '')

    def test_upload_into_foreign_profile_forbidden(self):
        teacher = User.objects.create_superuser('teacher2', password='pw')
        self.client.force_login(teacher)
        response = self.client.post(
            reverse('accounts:student_profile', args=[self.student.id]),
            {'avatar': _png('green')},
        )
        self.assertEqual(response.status_code, 403)


class TextbookStatsTests(TestCase):
    """Оценка за блок и средний балл считаются от решённых задач практикума."""

    @classmethod
    def setUpTestData(cls):
        cls.student = User.objects.create_user('student', password='pw')

        cls.practicum = Quiz.objects.create(title='Практикум 1')
        cls.questions = [
            Question.objects.create(quiz=cls.practicum, text=f'q{i}', correct_text_answer=str(i))
            for i in range(4)
        ]
        cls.section = Section.objects.create(
            title='Блок 1', slug='block-1', order=1, is_published=True,
            practicum_quiz=cls.practicum,
            grade_3_from=1, grade_4_from=2, grade_5_from=4,
        )
        # Второй блок без порогов — в средний балл попадать не должен.
        cls.ungraded = Section.objects.create(
            title='Блок 2', slug='block-2', order=2, is_published=True,
        )
        cls.article = Article.objects.create(
            track='material', section=cls.section, slug='a1', title='Урок 1', is_published=True,
        )

    def solve(self, count):
        result = UserResult.objects.create(user=self.student, quiz=self.practicum, score=count)
        for question in self.questions[:count]:
            UserAnswer.objects.create(
                user_result=result, question=question,
                text_answer=question.correct_text_answer, is_correct=True,
            )

    def test_untouched_sections_are_not_graded(self):
        stats = profile_textbook_stats(self.student)
        self.assertIsNone(stats['avg_grade'])
        self.assertEqual(stats['graded_count'], 0)

    def test_grade_and_next_step(self):
        self.solve(2)
        stats = profile_textbook_stats(self.student)
        block = next(s for s in stats['sections'] if s['section'] == self.section)

        self.assertEqual(block['practicum_done'], 2)
        self.assertEqual(block['grade'], 4)
        self.assertEqual(block['next_step'], {'grade': 5, 'left': 2})
        # Средний балл — только по блоку с порогами, второй блок не в счёт.
        self.assertEqual(stats['avg_grade'], 4)
        self.assertEqual(stats['graded_count'], 1)
        self.assertIn(block, stats['focus'])

    def test_completed_practicum_leaves_focus(self):
        self.solve(4)
        stats = profile_textbook_stats(self.student)
        block = next(s for s in stats['sections'] if s['section'] == self.section)

        self.assertEqual(block['grade'], 5)
        self.assertIsNone(block['next_step'])
        self.assertEqual(stats['focus'], [])

    def test_solve_time_sums_attempts_and_ignores_foreign_quizzes(self):
        UserResult.objects.create(
            user=self.student, quiz=self.practicum, score=1, duration=timedelta(minutes=10),
        )
        UserResult.objects.create(
            user=self.student, quiz=self.practicum, score=2, duration=timedelta(minutes=5),
        )
        # Тест вне учебника — его время в блок «Учебник» попадать не должно.
        outside = Quiz.objects.create(title='Вариант ЕГЭ', quiz_type='exam')
        UserResult.objects.create(
            user=self.student, quiz=outside, score=0, duration=timedelta(hours=2),
        )

        self.assertEqual(profile_textbook_stats(self.student)['solve_seconds'], 15 * 60)

    def test_read_lessons_counted(self):
        ArticleProgress.objects.create(user=self.student, article=self.article, status='read')
        stats = profile_textbook_stats(self.student)

        self.assertEqual(stats['lessons_done'], 1)
        self.assertEqual(stats['lessons_total'], 1)
        self.assertEqual(stats['lessons_pct'], 100)


@NO_MANIFEST_STATIC
class AlumniTests(TestCase):
    """Архив выпускников: попадает туда только класс с годом выпуска."""

    @classmethod
    def setUpTestData(cls):
        cls.graduated = StudentGroup.objects.create(name='11А', graduation_year=2025)
        cls.active = StudentGroup.objects.create(name='10Б')
        cls.alum = User.objects.create_user('alum', password='pw',
                                            last_name='Петров', first_name='Иван')
        Profile.objects.create(user=cls.alum, group=cls.graduated,
                               alumni_place='НГУ', alumni_about='Учусь на ФИТ.')
        cls.pupil = User.objects.create_user('pupil', password='pw', last_name='Сидоров')
        Profile.objects.create(user=cls.pupil, group=cls.active)

    def test_anonymous_sees_graduated_class_only(self):
        response = self.client.get(reverse('alumni'))
        self.assertEqual(response.status_code, 200)
        page = response.content.decode()

        self.assertIn('Иван', page)
        self.assertIn('Учусь на ФИТ.', page)
        # Персональные данные: наружу идут имя и год, но не фамилия и не номер класса.
        self.assertNotIn('Петров', page, 'фамилия выпускника на публичной странице')
        self.assertNotIn('11А', page, 'номер класса на публичной странице')
        self.assertNotIn('Сидоров', page, 'действующий класс попал в архив')

    def test_first_cohort_marked(self):
        earlier = StudentGroup.objects.create(name='11В', graduation_year=2024)
        response = self.client.get(reverse('alumni'))
        flags = {g.name: g.is_first for g in response.context['groups']}

        self.assertEqual(flags, {earlier.name: True, self.graduated.name: False})
        self.assertIn('Первый выпуск', response.content.decode())

    def test_student_fills_own_card(self):
        self.client.force_login(self.alum)
        self.client.post(reverse('accounts:profile'), {
            'alumni_place': 'НГТУ', 'alumni_about': 'Работаю.',
        })
        profile = Profile.objects.get(user=self.alum)

        self.assertEqual(profile.alumni_place, 'НГТУ')
        self.assertEqual(profile.alumni_about, 'Работаю.')
        # Аватар второй формой не затёрло.
        self.assertEqual(profile.avatar.name, '')

    def test_alumni_badge_in_name(self):
        from accounts.templatetags.profile_tags import student_name

        self.assertEqual(student_name(self.alum), 'Петров Иван 🎓 2025')
        self.assertEqual(student_name(self.pupil), 'Сидоров')

    def test_graduated_group_hidden_from_active_lists(self):
        from textbook.services import visible_group_ids

        request = RequestFactory().get('/')
        request.user = User.objects.create_superuser('t', password='pw')

        self.assertEqual(visible_group_ids(request), [self.active.id])
