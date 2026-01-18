from django.shortcuts import render, get_object_or_404
from .models import Lesson, Section

def lesson_list_view(request):
    sections = Section.objects.prefetch_related('lessons').all()
    orphan_lessons = Lesson.objects.filter(section__isnull=True)
    context = {
        'sections': sections,
        'orphan_lessons': orphan_lessons
    }
    return render(request, 'lessons/lesson_list.html', context)

def lesson_detail_view(request, lesson_id):
    lesson = get_object_or_404(Lesson, id=lesson_id)
    context = {'lesson': lesson}
    return render(request, 'lessons/lesson_detail.html', context)
