"""Сервисные функции учебника, вызываемые из quizzes (хуки прогресса)."""
from django.utils import timezone


def quiz_is_passed(user, quiz):
    """
    Считается ли тест самопроверки пройденным для ученика.

    Смотрит на все результаты ученика по этому тесту (баллы накапливаются
    между попытками — см. quiz_detail_view), считая число уникальных
    верно решённых вопросов.
    """
    from quizzes.models import UserAnswer

    total_questions = quiz.questions.count()
    if total_questions == 0:
        return False

    correct_count = (
        UserAnswer.objects.filter(
            user_result__user=user,
            user_result__quiz=quiz,
            is_correct=True,
        )
        .values('question_id')
        .distinct()
        .count()
    )

    # correct_count — число уникальных верно решённых вопросов из total_questions
    # (баллы накапливаются между попытками). Критерий «тема освоена»: не менее 85%.
    passed = correct_count >= total_questions * 0.85
    return passed


def update_article_mastery(user, quiz):
    """
    Хук после сабмита теста. Если quiz — самопроверка статьи и ученик её
    прошёл, помечает связанные статьи статусом «освоено» (mastered).

    Безопасен к вызову для любого теста: для не-самопроверок сразу выходит.
    """
    if not getattr(quiz, 'is_self_check', False):
        return

    from .models import ArticleProgress, ArticleQuiz

    links = list(ArticleQuiz.objects.filter(quiz=quiz).select_related('article'))
    if not links:
        return

    if not quiz_is_passed(user, quiz):
        return

    now = timezone.now()
    for link in links:
        progress, _ = ArticleProgress.objects.get_or_create(user=user, article=link.article)
        if progress.status != 'mastered':
            progress.status = 'mastered'
            progress.mastered_at = now
            if progress.read_at is None:
                progress.read_at = now
            progress.save(update_fields=['status', 'mastered_at', 'read_at', 'updated_at'])
