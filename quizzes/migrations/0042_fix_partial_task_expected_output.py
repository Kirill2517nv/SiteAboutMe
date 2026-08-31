"""
Чиним эталоны заданий 26 и 27, которые нельзя было пройти.

Две поломки, обе из импорта:
  * literal «\\n» вместо перевода строки – такой эталон не разбирается на числа;
  * два теста с одним и тем же ответом в разной раскладке («43656 36» и те же
    числа в две строки) – пройти оба одновременно невозможно, потому что зачёт
    требовал совпадения всех тестов.

После перехода на разбор чисел раскладка роли не играет, поэтому дубликат
просто удаляем, а экранированный перенос строки превращаем в настоящий.
"""
from django.db import migrations

PARTIAL_TASKS = (26, 27)


def fix(apps, schema_editor):
    TestCase = apps.get_model('quizzes', 'TestCase')

    tests = TestCase.objects.filter(question__ege_number__in=PARTIAL_TASKS)
    for test in tests:
        fixed = test.output_data.replace('\\n', '\n')
        if fixed != test.output_data:
            test.output_data = fixed
            test.save(update_fields=['output_data'])

    # Дубликаты по числам: оставляем самый первый тест каждой задачи.
    seen = {}
    for test in tests.order_by('question_id', 'id'):
        key = (test.question_id, test.input_data, ' '.join(test.output_data.split()))
        if key in seen:
            test.delete()
        else:
            seen[key] = test.id


class Migration(migrations.Migration):

    dependencies = [
        ('quizzes', '0041_codesubmission_score_examtaskprogress_score_and_more'),
    ]

    operations = [
        migrations.RunPython(fix, migrations.RunPython.noop),
    ]
