import re

from django import template
from django.utils.html import escape, mark_safe

register = template.Library()

IMG_MARKER_RE = re.compile(r'\[img:(\d+)\]')
SUP_MARKER_RE = re.compile(r'\[sup:([^\]]+)\]')
SUB_MARKER_RE = re.compile(r'\[sub:([^\]]+)\]')


def _render_table(rows):
    """Convert list of tab-separated strings to a styled HTML table."""
    raw = [row.split('\t') for row in rows]

    # Merge continuation rows: the EGE parser splits multi-line table headers
    # into separate tab-separated lines. A continuation row has significantly
    # fewer cells than the header row. We merge its first cell onto the last
    # cell of the previous row and treat remaining cells as new columns.
    merged = []
    ref_cols = len(raw[0]) if raw else 0
    for i, cells in enumerate(raw):
        if i == 0:
            merged.append(list(cells))
            continue
        if len(cells) < ref_cols and len(cells) <= max(2, ref_cols // 2):
            prev = merged[-1]
            # Append first cell text to last cell of previous row
            if cells[0].strip():
                prev[-1] = prev[-1].rstrip() + ' ' + cells[0].strip()
            # Add remaining cells as new columns on previous row
            prev.extend(cells[1:])
            if len(prev) > ref_cols:
                ref_cols = len(prev)
        else:
            merged.append(list(cells))

    parsed = merged
    max_cols = max(len(r) for r in parsed)

    # Pad all rows to the same column count
    for row in parsed:
        row += [''] * (max_cols - len(row))

    html = ['<div class="overflow-x-auto my-3"><table class="text-sm border-collapse">']
    html.append('<thead>')
    # First row is the column header row
    html.append('<tr>')
    for cell in parsed[0]:
        html.append(
            f'<th class="border border-gray-300 px-2 py-1 bg-gray-100 '
            f'font-semibold text-center min-w-[2.5rem]">{escape(cell.strip())}</th>'
        )
    html.append('</tr>')
    html.append('</thead>')

    if len(parsed) > 1:
        html.append('<tbody>')
        for row in parsed[1:]:
            html.append('<tr>')
            for j, cell in enumerate(row):
                content = escape(cell.strip())
                if j == 0:
                    # Row header
                    html.append(
                        f'<th class="border border-gray-300 px-2 py-1 bg-gray-100 '
                        f'font-semibold text-center">{content}</th>'
                    )
                else:
                    html.append(
                        f'<td class="border border-gray-300 px-2 py-1 text-center">'
                        f'{content}</td>'
                    )
            html.append('</tr>')
        html.append('</tbody>')

    html.append('</table></div>')
    return ''.join(html)


@register.filter(is_safe=True)
def render_question_text(text, question=None):
    """
    Renders question text with tab-separated blocks converted to HTML tables.
    Regular paragraphs are wrapped in <p> tags with proper spacing.
    Supports [img:N] markers for inline image placement (1-based index).
    """
    if not text:
        return ''

    # Build image map from question object (1-based index → url)
    image_map = {}
    if question is not None:
        for idx, img in enumerate(question.images.all(), 1):
            image_map[idx] = (img.image.url, img.alt_text or '')

    lines = text.split('\n')

    # Pre-process: merge split table rows.
    # The EGE parser sometimes splits a data row across lines: the first cell
    # lands on a non-tab line, then one or more blank/nbsp lines, then the
    # remaining cells on a \t-starting line (empty first cell).
    # Heuristic: a non-tab line immediately preceding (across blanks) a
    # \t-starting tab line is the missing first cell — merge them.
    processed = []
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        stripped = line.replace('\xa0', '').strip()
        # Only short lines (≤ 30 chars) can be a split table-row first cell.
        # Long lines are paragraph text that happens to precede a table.
        if stripped and '\t' not in line and len(stripped) <= 30:
            # Look ahead past blank/nbsp-only lines
            j = i + 1
            while j < len(lines) and not lines[j].rstrip().replace('\xa0', '').strip():
                j += 1
            if j < len(lines) and lines[j].rstrip().startswith('\t'):
                # Merge: prepend this cell to the \t-starting continuation
                processed.append(stripped + lines[j].rstrip())
                i = j + 1
                continue
        processed.append(line)
        i += 1
    lines = processed

    result = []
    table_rows = []
    para_lines = []

    def flush_para():
        if para_lines:
            content = '<br>'.join(escape(l) for l in para_lines)
            result.append(f'<p class="mb-2">{content}</p>')
            para_lines.clear()

    def flush_table():
        if table_rows:
            result.append(_render_table(table_rows))
            table_rows.clear()

    for line in lines:
        line = line.rstrip()
        stripped = line.replace('\xa0', '').strip()

        if '\t' in line:
            flush_para()
            table_rows.append(line)
        elif not stripped:
            # Blank / nbsp-only line → paragraph break
            flush_table()
            flush_para()
        else:
            flush_table()
            para_lines.append(line)

    flush_table()
    flush_para()

    html = '\n'.join(result)

    # Replace [img:N] markers with actual <img> tags
    if image_map:
        def _replace_marker(m):
            idx = int(m.group(1))
            if idx in image_map:
                url, alt = image_map[idx]
                return (
                    f'<div class="my-3">'
                    f'<img src="{escape(url)}" alt="{escape(alt)}" '
                    f'class="max-w-full rounded-lg border">'
                    f'</div>'
                )
            return m.group(0)  # leave unknown markers as-is
        html = IMG_MARKER_RE.sub(_replace_marker, html)

    # Replace [sup:text] and [sub:text] markers with HTML tags
    # Content is already escaped by flush_para, so it's safe
    html = SUP_MARKER_RE.sub(r'<sup>\1</sup>', html)
    html = SUB_MARKER_RE.sub(r'<sub>\1</sub>', html)

    return mark_safe(html)


@register.filter
def has_image_markers(text):
    """Returns True if the question text contains any [img:N] markers."""
    if not text:
        return False
    return bool(IMG_MARKER_RE.search(text))
