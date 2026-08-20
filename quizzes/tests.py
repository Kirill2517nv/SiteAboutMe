from django.test import SimpleTestCase

from .views import EGE_RECOMMENDED_TIME, ege_time_color


class EgeTimeColorTests(SimpleTestCase):
    """Пороги цвета времени общие для результатов варианта, отчёта и профиля."""

    def test_thresholds(self):
        # Задание 17: норма 14 минут, полторы нормы — 21.
        self.assertEqual(EGE_RECOMMENDED_TIME[17], 14)
        cases = {
            5 * 60: 'green',
            14 * 60: 'green',    # ровно норма — ещё зелёный
            15 * 60: 'yellow',
            21 * 60: 'yellow',   # ровно полторы нормы — ещё жёлтый
            22 * 60: 'red',
        }
        for seconds, expected in cases.items():
            with self.subTest(seconds=seconds):
                self.assertEqual(ege_time_color(seconds, 17), expected)

    def test_no_time_no_color(self):
        self.assertEqual(ege_time_color(0, 17), '')
        self.assertEqual(ege_time_color(None, 17), '')

    def test_unknown_number_falls_back_to_five_minutes(self):
        self.assertNotIn(99, EGE_RECOMMENDED_TIME)
        self.assertEqual(ege_time_color(4 * 60, 99), 'green')
        self.assertEqual(ege_time_color(9 * 60, 99), 'red')
