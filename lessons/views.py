import mimetypes
import os
import re
from urllib.parse import quote

from django.shortcuts import render, get_object_or_404
from django.http import FileResponse, Http404

from .models import Lesson, Section, LessonAttachment


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
    blocks = lesson.blocks.all().order_by('order')
    attachments = lesson.attachments.all()
    context = {
        'lesson': lesson,
        'blocks': blocks,
        'attachments': attachments,
        'page_type': 'lesson',
    }
    return render(request, 'lessons/lesson_detail.html', context)


def lesson_file_download_view(request, lesson_id, attachment_id):
    """Download a LessonAttachment file."""
    attachment = get_object_or_404(
        LessonAttachment, id=attachment_id, lesson_id=lesson_id
    )
    if not attachment.file:
        raise Http404("Файл не найден")

    filename = os.path.basename(attachment.file.name)
    content_type, _ = mimetypes.guess_type(filename)

    response = FileResponse(
        attachment.file.open("rb"),
        as_attachment=True,
        content_type=content_type or "application/octet-stream",
    )
    response["Content-Disposition"] = _attachment_content_disposition(filename)
    return response


def presentation_pdf_download_view(request, lesson_id):
    """Download presentation PDF for a lesson."""
    lesson = get_object_or_404(Lesson, id=lesson_id)
    if not lesson.presentation_pdf:
        raise Http404("PDF не найден")

    filename = os.path.basename(lesson.presentation_pdf.name)
    content_type, _ = mimetypes.guess_type(filename)

    response = FileResponse(
        lesson.presentation_pdf.open("rb"),
        as_attachment=True,
        content_type=content_type or "application/pdf",
    )
    response["Content-Disposition"] = _attachment_content_disposition(filename)
    return response
