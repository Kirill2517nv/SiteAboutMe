from django.shortcuts import render, get_object_or_404
from django.http import FileResponse, Http404, HttpResponse
from django.conf import settings
from .models import Lesson, Section
import os
import mimetypes
import re
from urllib.parse import quote

def _attachment_content_disposition(filename: str) -> str:
    safe = (filename or "download").replace("\r", "").replace("\n", "")
    ascii_fallback = re.sub(r"[^A-Za-z0-9.\-_]", "_", safe) or "download"
    return f'attachment; filename="{ascii_fallback}"; filename*=UTF-8\'\'{quote(safe)}'

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

def lesson_file_download_view(request, lesson_id):
    """
    Download Lesson.file with a stable filename across browsers/OS.
    """
    lesson = get_object_or_404(Lesson, id=lesson_id)
    if not lesson.file:
        raise Http404("Файл не найден")

    filename = os.path.basename(lesson.file.name)
    content_type, _ = mimetypes.guess_type(filename)

    response = FileResponse(
        lesson.file.open("rb"),
        as_attachment=True,
        content_type=content_type or "application/octet-stream",
    )
    response["Content-Disposition"] = _attachment_content_disposition(filename)
    return response
