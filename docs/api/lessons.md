# Lessons API

Приложение `lessons` предоставляет 4 публичных endpoint'а для просмотра уроков и скачивания файлов.

---

## Endpoints

### GET `/lessons/` — Список уроков

**View:** `lesson_list_view`
**Auth:** Не требуется
**Template:** `lessons/lesson_list.html`

Загружает разделы с предзагрузкой уроков + уроки без раздела (orphan lessons).

---

### GET `/lessons/<id>/` — Детали урока

**View:** `lesson_detail_view`
**Auth:** Не требуется
**Template:** `lessons/lesson_detail.html`

Отображает урок с блоками контента (упорядоченными по `order`), секцией презентации Slidev и списком файловых вложений.

**Контекст шаблона:**

| Переменная | Тип | Описание |
|------------|-----|----------|
| `lesson` | Lesson | Объект урока |
| `blocks` | QuerySet | Блоки контента, отсортированные по `order` |
| `attachments` | QuerySet | Вложения `LessonAttachment`, отсортированные по `order` |

---

### GET `/lessons/<id>/file/<attachment_id>/` — Скачать вложение

**View:** `lesson_file_download_view`
**Auth:** Не требуется
**Response:** `FileResponse` с `Content-Disposition: attachment`

Скачивает файл `LessonAttachment`. Параметр `attachment_id` верифицируется по `lesson_id` — защита от IDOR. Имя файла кодируется по RFC 5987 для корректного отображения кириллицы.

!!! info "Nginx X-Accel-Redirect"
    В production файлы отдаются через Nginx `X-Accel-Redirect` для оптимальной производительности. В development используется Django `FileResponse`.

---

### GET `/lessons/<id>/presentation-pdf/` — Скачать PDF презентации

**View:** `presentation_pdf_download_view`
**Auth:** Не требуется
**Response:** `FileResponse` с `Content-Disposition: attachment`

Скачивает PDF-версию Slidev-презентации (`Lesson.presentation_pdf`). Возвращает 404, если PDF не загружен.
