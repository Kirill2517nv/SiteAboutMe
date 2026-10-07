"""
Похожие решения: насколько код одного ученика совпадает с кодом другого.

Это сигнал учителю «посмотрите и поговорите», а не вердикт: ученик его не видит,
на оценки и статистику он не влияет.

Как считается. Код превращается в поток токенов, где имена переменных стали `V`,
числа – `N`, строки – `S`, а комментарии и пробелы исчезли: переименование
переменных и переформатирование сходство не прячут. Из потока нарезаются
k-граммы (по K токенов подряд), сходство пары – доля общих k-грамм (Жаккар).
Ключевые слова, встроенные и импортированные имена (`product`, `range`,
`.count`) остаются как есть – на них держится сама идея решения.

Скидка на канон. У задания 2 все пишут `for x in product('01', repeat=4)`, и
честные решения совпадали бы на 90%. Поэтому k-грамма, которая встречается
больше чем у половины решивших (если решивших хотя бы MIN_AUTHORS), из
сравнения выбрасывается – как «базовый код» у MOSS. Голосуют различные
программы, а не авторы: иначе большая группа одинаковых копий сама сделала бы
свой код «каноном» и спряталась. Если после этого у решения
осталось меньше MIN_GRAMS фрагментов, оно целиком каноническое, и сравнивать
его не с чем.

С кем сравнивается: первое верное решение каждого ученика на каждом языке –
не последнее. Галерея «Решения других» открывается только решившему, и код,
переписанный после неё по чужому образцу, – законная учёба, а не списывание.
"""
import builtins
import io
import keyword
import re
import tokenize

from django.contrib.auth import get_user_model

from .models import CodeSubmission, UserAnswer

K = 5
# ponytail: пороги подобраны на глаз по dev-базе (14 учеников); калибровать по
# реальным парам на проде – это три числа ниже.
SHOW_FROM = 0.6
COMMON_SHARE = 0.5
MIN_AUTHORS = 5
MIN_GRAMS = 8

PY_KEEP = set(keyword.kwlist) | set(keyword.softkwlist) | set(dir(builtins))
CPP_KEEP = {
    # ключевые слова
    'auto', 'bool', 'break', 'case', 'char', 'const', 'continue', 'default', 'do',
    'double', 'else', 'false', 'float', 'for', 'if', 'int', 'long', 'namespace',
    'return', 'short', 'signed', 'sizeof', 'static', 'struct', 'switch', 'true',
    'unsigned', 'using', 'void', 'while', 'class', 'template', 'typename', 'new',
    'delete', 'nullptr', 'constexpr',
    # стандартная библиотека, которой пишут школьные задачи
    'std', 'main', 'cin', 'cout', 'cerr', 'endl', 'getline', 'ifstream', 'ofstream',
    'string', 'vector', 'map', 'set', 'pair', 'unordered_map', 'unordered_set',
    'deque', 'queue', 'stack', 'priority_queue', 'sort', 'reverse', 'max', 'min',
    'abs', 'swap', 'pow', 'sqrt', 'to_string', 'stoi', 'stoll', 'size', 'push_back',
    'begin', 'end', 'count', 'find', 'insert', 'first', 'second', 'next_permutation',
    'max_element', 'min_element', 'accumulate', 'fixed', 'setprecision',
}
LEX = re.compile(r'[A-Za-z_]\w*|\d[\w.]*|"(?:\\.|[^"\\\n])*"|\'(?:\\.|[^\'\\\n])*\'|::|->|[^\s\w]')
CPP_COMMENT = re.compile(r'//[^\n]*|/\*.*?\*/', re.S)


def _lex(code, keep):
    """Грубый лексер для C++ и для Python, который не разобрал tokenize."""
    out = []
    code = CPP_COMMENT.sub(lambda m: '\n' * m.group().count('\n'), code)
    for lineno, line in enumerate(code.splitlines(), 1):
        if line.lstrip().startswith('#'):  # #include / #define и комментарий Python
            continue
        prev = ''
        for m in LEX.finditer(line):
            tok = m.group()
            if tok[0].isalpha() or tok[0] == '_':
                tok = tok if tok in keep or prev in ('.', '::', '->') else 'V'
            elif tok[0].isdigit():
                tok = 'N'
            elif tok[0] in '"\'':
                tok = 'S'
            out.append((tok, lineno))
            prev = m.group()
    return out


def _py_tokens(code):
    try:
        raw = list(tokenize.generate_tokens(io.StringIO(code).readline))
    except (tokenize.TokenError, SyntaxError):
        return _lex(code, PY_KEEP)

    # Имена из import живут как библиотечные: `product` – часть идеи, а не переменная.
    imported, in_import = set(), False
    for t in raw:
        if t.type == tokenize.NAME and t.string in ('import', 'from'):
            in_import = True
        elif t.type == tokenize.NEWLINE:
            in_import = False
        elif in_import and t.type == tokenize.NAME:
            imported.add(t.string)

    out, prev = [], ''
    for t in raw:
        name = tokenize.tok_name[t.type]
        if t.type in (tokenize.COMMENT, tokenize.NL, tokenize.ENCODING, tokenize.ENDMARKER):
            continue
        if name.endswith(('STRING_MIDDLE', 'STRING_END')):  # f-/t-строки: одна S на строку
            continue
        if t.type == tokenize.NAME:
            tok = t.string if t.string in PY_KEEP or t.string in imported or prev == '.' else 'V'
        elif t.type == tokenize.NUMBER:
            tok = 'N'
        elif t.type == tokenize.STRING or name.endswith('STRING_START'):
            tok = 'S'
        elif t.type == tokenize.NEWLINE:
            tok = ';'
        elif t.type == tokenize.INDENT:
            tok = '{'
        elif t.type == tokenize.DEDENT:
            tok = '}'
        else:
            tok = t.string
        out.append((tok, t.start[0]))
        prev = t.string
    return out


def tokens(code, language='python'):
    """[(токен, номер строки)] – нормализованный поток без имён и оформления."""
    return _lex(code, CPP_KEEP) if language == 'cpp' else _py_tokens(code)


def grams(toks):
    """{k-грамма: строки кода, которые она покрывает} из потока tokens()."""
    out = {}
    for i in range(len(toks) - K + 1):
        window = toks[i:i + K]
        out.setdefault(tuple(t for t, _ in window), set()).update(line for _, line in window)
    return out


def similarity(a, b):
    """Жаккар двух множеств k-грамм; None – сравнивать не с чем."""
    if len(a) < MIN_GRAMS or len(b) < MIN_GRAMS:
        return None
    return len(a & b) / len(a | b)


def first_correct(question):
    """
    Первое верное решение каждого ученика на каждом языке.

    Ответы практикума без CodeSubmission (синхронная проверка) – Python. Отправки
    учителей не берутся: это проверка задачи, а не решение.
    """
    staff = set(get_user_model().objects.filter(is_superuser=True).values_list('id', flat=True))
    found = {}
    for sub in (CodeSubmission.objects
                .filter(question=question, is_correct=True)
                .exclude(user_id__in=staff)
                .select_related('user', 'user__profile__group')
                .order_by('created_at')):
        found.setdefault((sub.user_id, sub.language), {
            'user': sub.user, 'language': sub.language, 'code': sub.code, 'at': sub.created_at,
        })
    users = {uid for uid, _ in found}
    for ans in (UserAnswer.objects
                .filter(question=question, is_correct=True, submission__isnull=True)
                .exclude(code_answer__isnull=True).exclude(code_answer='')
                .exclude(user_result__user_id__in=staff | users)
                .select_related('user_result__user', 'user_result__user__profile__group')
                .order_by('user_result__date_completed')):
        user = ans.user_result.user
        found.setdefault((user.id, 'python'), {
            'user': user, 'language': 'python', 'code': ans.code_answer,
            'at': ans.user_result.date_completed,
        })
    return list(found.values())


def _group(user):
    profile = getattr(user, 'profile', None)
    return getattr(profile, 'group', None)


def _lines(code, hit):
    return [{'n': n, 'text': text, 'hit': n in hit} for n, text in enumerate(code.splitlines(), 1)]


def question_pairs(question, user_ids=None, show_from=SHOW_FROM):
    """
    Похожие пары по одной задаче, от самой похожей.

    user_ids – вкладка класса: пара показывается, если в ней есть хоть один
    ученик этого класса (второй может быть из параллели). None – все.
    """
    entries = first_correct(question)
    for e in entries:
        toks = tokens(e['code'], e['language'])
        e['seq'] = tuple(t for t, _ in toks)
        e['grams'] = grams(toks)

    # Канон считается по различным программам, а не по авторам: шесть копий
    # одного кода из девяти решивших – это группа списавших, а не канон, и
    # голосовать за «все так пишут» она должна один раз.
    programs = {e['seq']: e['grams'] for e in entries}
    common = set()
    if len(programs) >= MIN_AUTHORS:
        freq = {}
        for program in programs.values():
            for g in program:
                freq[g] = freq.get(g, 0) + 1
        common = {g for g, n in freq.items() if n > COMMON_SHARE * len(programs)}

    def pair(a, b):
        if a['language'] != b['language']:
            return None
        ka, kb = set(a['grams']) - common, set(b['grams']) - common
        score = similarity(ka, kb)
        if score is None or score < show_from:
            return None
        shared = ka & kb
        hit = lambda e: set().union(*(e['grams'][g] for g in shared))
        return {'score': round(score * 100), 'a': a, 'b': b, 'identical': a['seq'] == b['seq'],
                'a_lines': _lines(a['code'], hit(a)), 'b_lines': _lines(b['code'], hit(b))}

    ours = lambda e: user_ids is None or e['user'].id in user_ids
    pairs = []
    # ponytail: O(n²) по решившим одну задачу – в школе это десятки; на тысячах
    # авторов – индекс k-грамма → авторы и сравнение только тех, кто делит фрагменты.
    for i, a in enumerate(entries):
        for b in entries[i + 1:]:
            if a['user'].id != b['user'].id and (ours(a) or ours(b)):
                p = pair(a, b)
                if p:
                    ga, gb = _group(a['user']), _group(b['user'])
                    p['same_group'] = ga is not None and ga == gb
                    p['gap'] = abs(a['at'] - b['at']) if a['at'] and b['at'] else None
                    pairs.append(p)
    pairs.sort(key=lambda p: -p['score'])
    return pairs
