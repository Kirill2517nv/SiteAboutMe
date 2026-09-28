// Отзыв читателя на странице статьи: правка блока (✎) и звёзды под статьёй.
// Разметка – templates/textbook/_article_feedback.html, сервер –
// textbook/views_feedback.py. Правка совещательная: в статью она не
// попадает, её читает учитель на /textbook/feedback/.

function escapeHtml(s) {
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

// Diff двух списков: [['=', x], ['-', x], ['+', y], …]. Общие начало и конец
// срезаются сразу (правка почти всегда локальна), середина – по LCS.
function diffOps(x, y) {
    let pre = 0;
    while (pre < x.length && pre < y.length && x[pre] === y[pre]) pre++;
    let suf = 0;
    while (suf < x.length - pre && suf < y.length - pre
           && x[x.length - 1 - suf] === y[y.length - 1 - suf]) suf++;
    const xs = x.slice(pre, x.length - suf), ys = y.slice(pre, y.length - suf);
    const n = xs.length, m = ys.length;

    const ops = x.slice(0, pre).map(t => ['=', t]);
    // ponytail: LCS за n·m по памяти; если переписан целиком огромный блок –
    // «всё удалено / всё новое». Myers, если это станет нормой.
    if (n * m > 1e6) {
        xs.forEach(t => ops.push(['-', t]));
        ys.forEach(t => ops.push(['+', t]));
    } else {
        const L = Array.from({ length: n + 1 }, () => new Uint32Array(m + 1));
        for (let i = n - 1; i >= 0; i--) {
            for (let j = m - 1; j >= 0; j--) {
                L[i][j] = xs[i] === ys[j] ? L[i + 1][j + 1] + 1 : Math.max(L[i + 1][j], L[i][j + 1]);
            }
        }
        let i = 0, j = 0;
        while (i < n && j < m) {
            if (xs[i] === ys[j]) { ops.push(['=', xs[i]]); i++; j++; }
            else if (L[i + 1][j] >= L[i][j + 1]) ops.push(['-', xs[i++]]);
            else ops.push(['+', ys[j++]]);
        }
        while (i < n) ops.push(['-', xs[i++]]);
        while (j < m) ops.push(['+', ys[j++]]);
    }
    x.slice(x.length - suf).forEach(t => ops.push(['=', t]));
    return ops;
}

// Строка кода в превью: полоса слева как в git – зелёная у новой, красная у
// удалённой, прозрачная у прежней (чтобы отступы не прыгали).
const CODE_LINE = {
    '=': 'border-l-4 border-transparent pl-2',
    '+': 'border-l-4 border-green-500 pl-2 bg-green-500/20',
    '-': 'border-l-4 border-red-500 pl-2 bg-red-500/20 line-through decoration-red-400/70',
};

// Построчный diff кода с подсветкой синтаксиса той же hljs, что красит блоки
// статьи. Строки красятся по отдельности, иначе новую и удалённую не разнести.
// ponytail: многострочная строка/докстринг в Python раскрасится неверно со
// второй строки – склейка спанов hljs по строкам, если это начнёт мешать.
function codeDiff(a, b, lang) {
    const hl = window.hljs && hljs.getLanguage(lang)
        ? (line) => hljs.highlight(line, { language: lang, ignoreIllegals: true }).value
        : escapeHtml;
    return diffOps(a.split('\n'), b.split('\n'))
        .map(([k, line]) => `<span class="block ${CODE_LINE[k]}">${hl(line) || ' '}</span>`)
        .join('');
}

if (typeof module !== 'undefined') module.exports = { diffOps };

(function () {
    if (typeof document === 'undefined') return;
    const root = document.getElementById('article-root');
    const dialog = document.getElementById('suggest-dialog');
    if (!root || !dialog) return;
    const csrf = root.dataset.csrf;

    // ---------- Диалог правки ----------
    const form = dialog.querySelector('form');
    const proposed = form.elements.proposed;
    const kindEl = dialog.querySelector('[data-suggest-kind]');
    const labelEl = dialog.querySelector('[data-suggest-label]');
    const diffWrap = dialog.querySelector('[data-suggest-diff-wrap]');
    const diffOut = dialog.querySelector('[data-suggest-diff]');
    const diffLang = dialog.querySelector('[data-suggest-diff-lang]');
    const previewWrap = dialog.querySelector('[data-suggest-preview-wrap]');
    const previewOut = dialog.querySelector('[data-suggest-preview]');
    const msg = dialog.querySelector('[data-suggest-error]');
    const submitBtn = form.querySelector('[type=submit]');
    const MSG_ERR = 'text-sm text-red-600 dark:text-red-400';
    const MSG_OK = 'text-sm text-green-700 dark:text-green-400';
    let current = null;   // ответ GET исходника блока + url
    let previewTimer = null, previewSeq = 0;

    // Текст и формулу сервер рисует тем же markdownify, что и статью, –
    // превью не может разойтись со страницей. Код на странице и так показан
    // исходником, поэтому для него – diff прямо здесь, без запроса.
    async function loadPreview() {
        const seq = ++previewSeq;
        const body = new FormData();
        body.append('proposed', proposed.value);
        try {
            const r = await fetch(current.preview_url, {
                method: 'POST', body, headers: { 'X-CSRFToken': csrf },
            });
            if (!r.ok || seq !== previewSeq) return;   // ответ устарел – ученик уже печатает дальше
            previewOut.innerHTML = (await r.json()).html;
            if (window.MathJax && MathJax.typesetPromise) {
                MathJax.typesetClear([previewOut]);
                MathJax.typesetPromise([previewOut]).catch(() => {});
            }
        } catch { /* превью – подсказка, без него правку всё равно можно отправить */ }
    }

    function render() {
        const kind = current && current.original ? current.type : null;
        diffWrap.style.display = kind === 'code' ? '' : 'none';
        previewWrap.style.display = kind === 'text' || kind === 'formula' ? '' : 'none';
        if (kind === 'code') {
            diffLang.textContent = current.language || 'код';
            diffOut.className = `hljs language-${current.language}`;
            diffOut.innerHTML = codeDiff(current.original, proposed.value, current.language);
        }
        if (kind === 'text' || kind === 'formula') {
            clearTimeout(previewTimer);
            previewTimer = setTimeout(loadPreview, 300);
        }
    }

    function open(state) {
        current = state;
        form.reset();
        msg.textContent = '';
        previewOut.innerHTML = '';
        submitBtn.disabled = false;
        kindEl.textContent = `Блок: ${state.kind.toLowerCase()}`;
        labelEl.textContent = state.original
            ? 'Как лучше – поправьте текст прямо здесь'
            : 'Как было бы лучше – опишите словами';
        proposed.value = state.original;
        render();
        dialog.showModal();
        proposed.focus();
    }

    proposed.addEventListener('input', render);
    dialog.querySelector('[data-suggest-cancel]').addEventListener('click', () => dialog.close());

    document.querySelectorAll('[data-suggest-block]').forEach(btn => {
        btn.addEventListener('click', async () => {
            const url = btn.closest('[data-suggest-url]').dataset.suggestUrl;
            try {
                const r = await fetch(url, { headers: { Accept: 'application/json' } });
                if (!r.ok) throw new Error(r.status);
                open({ ...(await r.json()), url });
            } catch {
                btn.title = 'Не удалось открыть редактор – обновите страницу';
            }
        });
    });

    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const file = form.elements.image.files[0];
        if (file && file.size > 5 * 1024 * 1024) {
            msg.className = MSG_ERR;
            msg.textContent = 'Картинка больше 5 МБ';
            return;
        }
        const body = new FormData(form);
        submitBtn.disabled = true;
        msg.textContent = '';
        try {
            const r = await fetch(current.url, {
                method: 'POST', body, headers: { 'X-CSRFToken': csrf },
            });
            const data = await r.json().catch(() => ({}));
            if (!r.ok) throw new Error(data.error || 'Не удалось отправить');
            msg.className = MSG_OK;
            msg.textContent = 'Спасибо! Ответ учителя появится в вашем профиле.';
            setTimeout(() => dialog.close(), 1500);
        } catch (err) {
            msg.className = MSG_ERR;
            msg.textContent = err.message;
            submitBtn.disabled = false;
        }
    });

    // ---------- Звёзды ----------
    const rating = document.getElementById('article-rating');
    if (!rating) return;
    const stars = [...rating.querySelectorAll('[data-star]')];
    const commentBox = rating.querySelector('[data-rate-comment]');
    const comment = commentBox.querySelector('textarea');
    const status = rating.querySelector('[data-rate-status]');
    let value = Number(rating.dataset.stars) || 0;

    function paint(n) {
        stars.forEach((s, i) => {
            const on = i < n;
            s.classList.toggle('text-amber-400', on);
            s.classList.toggle('text-gray-300', !on);
            s.classList.toggle('dark:text-slate-600', !on);
        });
    }

    async function save() {
        const body = new FormData();
        body.append('stars', value);
        // Комментарий – только к низкой оценке: поле видно лишь при 1–3.
        body.append('comment', value <= 3 ? comment.value : '');
        status.textContent = '…';
        try {
            const r = await fetch(rating.dataset.rateUrl, {
                method: 'POST', body, headers: { 'X-CSRFToken': csrf },
            });
            status.textContent = r.ok ? 'Сохранено, спасибо!' : 'Не удалось сохранить';
        } catch {
            status.textContent = 'Нет связи с сервером';
        }
    }

    stars.forEach((s, i) => {
        s.addEventListener('mouseenter', () => paint(i + 1));
        s.addEventListener('mouseleave', () => paint(value));
        s.addEventListener('click', () => {
            value = i + 1;
            paint(value);
            commentBox.style.display = value <= 3 ? '' : 'none';
            save();
        });
    });
    rating.querySelector('[data-rate-send]').addEventListener('click', save);

    paint(value);
    if (value && value <= 3) commentBox.style.display = '';
})();
