/*
 * Реестр интерактивных виджетов учебника.
 *
 * Паттерн: в БД блок типа `widget` хранит `widget_key` + `widget_config` (JSON).
 * Здесь регистрируются компоненты по ключу. Новый виджет = одна регистрация;
 * хранение и монтирование единообразны, конфиг задаёт параметры.
 *
 * Рамка: шаблон отдаёт голый <div data-widget data-title data-config>, каждый
 * виджет сам решает, как её заполнить. Для простых виджетов используйте
 * widgetFrame(el, title) — она рисует стандартную .textbook-widget рамку
 * (см. static/css/textbook-article.css) и возвращает контейнер для контента.
 * Виджету с собственной шапкой (счётчик, иконка — см. top-answers) рамка не
 * нужна, он строит разметку полностью сам.
 *
 * Регистрация своего виджета из другого файла:
 *   TextbookWidgets.register('my-widget', function (el, config) { ... });
 */
(function () {
    'use strict';

    const registry = {};

    function register(key, factory) {
        registry[key] = factory;
    }

    function init(root) {
        const scope = root || document;
        scope.querySelectorAll('[data-widget]').forEach(function (el) {
            if (el.dataset.mounted === '1') return;
            const key = el.dataset.widget;
            let config = {};
            try {
                config = JSON.parse(el.dataset.config || '{}');
            } catch (e) {
                console.warn('textbook-widget: некорректный JSON в data-config', key, e);
            }
            const factory = registry[key];
            if (!factory) {
                el.innerHTML = '<p class="text-sm text-red-500">Неизвестный виджет: ' + key + '</p>';
                return;
            }
            try {
                factory(el, config);
                el.dataset.mounted = '1';
            } catch (e) {
                console.error('textbook-widget: ошибка монтирования', key, e);
            }
        });
    }

    window.TextbookWidgets = { register: register, init: init };

    function escapeHtml(s) {
        const d = document.createElement('div');
        d.textContent = s == null ? '' : String(s);
        return d.innerHTML;
    }

    // Стандартная рамка .textbook-widget (см. CSS) для виджетов без своей шапки.
    // Возвращает .textbook-widget__body — контент добавляется внутрь него.
    function widgetFrame(el, title) {
        const frame = document.createElement('div');
        frame.className = 'textbook-widget';
        if (title) {
            const header = document.createElement('div');
            header.className = 'textbook-widget__header';
            header.innerHTML = '<div class="textbook-widget__title">' + escapeHtml(title) + '</div>';
            frame.appendChild(header);
        }
        const body = document.createElement('div');
        body.className = 'textbook-widget__body';
        frame.appendChild(body);
        el.appendChild(frame);
        return body;
    }

    // ─────────────────────────────────────────────────────────────
    // Виджет: bits-viewer — битовая раскладка целого числа.
    // Конфиг: { "value": 42, "bits": 8 }. Биты кликабельны — десятичное
    // значение пересчитывается на лету (наглядно «как число хранится в памяти»).
    // ─────────────────────────────────────────────────────────────
    register('bits-viewer', function (el, config) {
        const bitsCount = Math.min(Math.max(parseInt(config.bits, 10) || 8, 1), 32);
        let value = (parseInt(config.value, 10) || 0) & ((bitsCount < 32 ? (1 << bitsCount) : 0x100000000) - 1);

        const wrap = document.createElement('div');

        const bitsRow = document.createElement('div');
        bitsRow.className = 'flex flex-wrap gap-1 justify-center';

        const cells = [];
        for (let i = bitsCount - 1; i >= 0; i--) {
            const cell = document.createElement('button');
            cell.type = 'button';
            cell.className = 'w-9 h-11 rounded-md font-mono text-lg flex flex-col items-center justify-center border transition-colors';
            cell.dataset.bit = String(i);
            const idx = document.createElement('span');
            idx.className = 'text-[9px] text-gray-400 leading-none mb-0.5';
            idx.textContent = i;
            const val = document.createElement('span');
            val.className = 'leading-none';
            cell.appendChild(idx);
            cell.appendChild(val);
            cell._val = val;
            cell.addEventListener('click', function () {
                value ^= (1 << i);
                if (value < 0) value = value >>> 0; // держим беззнаковым
                render();
            });
            cells.push(cell);
            bitsRow.appendChild(cell);
        }

        const readout = document.createElement('div');
        readout.className = 'mt-4 text-center text-sm text-gray-600 dark:text-slate-300 font-mono';

        function render() {
            const masked = bitsCount === 32 ? (value >>> 0) : (value & ((1 << bitsCount) - 1));
            cells.forEach(function (cell) {
                const i = parseInt(cell.dataset.bit, 10);
                const on = (masked >>> i) & 1;
                cell._val.textContent = on ? '1' : '0';
                cell.className = 'w-9 h-11 rounded-md font-mono text-lg flex flex-col items-center justify-center border transition-colors ' +
                    (on
                        ? 'bg-brand-600 text-white border-brand-600 dark:bg-cyan-500 dark:border-cyan-500'
                        : 'bg-gray-50 text-gray-400 border-gray-200 dark:bg-slate-700 dark:border-slate-600');
            });
            readout.innerHTML =
                'Десятичное: <b class="text-gray-900 dark:text-white">' + masked + '</b>' +
                ' &nbsp;·&nbsp; 0x' + masked.toString(16).toUpperCase() +
                ' &nbsp;·&nbsp; 0b' + masked.toString(2).padStart(bitsCount, '0');
        }

        const body = widgetFrame(el, el.dataset.title);
        body.appendChild(wrap);
        wrap.appendChild(bitsRow);
        wrap.appendChild(readout);
        render();
    });

    // ─────────────────────────────────────────────────────────────
    // Виджет: top-answers — мини-игра «100 к одному». Ученик вписывает вариант
    // ответа в поле; при совпадении с ещё не угаданным ответом строка
    // раскрывается (место, текст, процент). Промах — «страйк» (до 3, не
    // блокирует игру). «Показать все» — раскрывает остаток разом.
    // Конфиг: { "question": "...", "answers": [{"text":.., "percent":..}, ...], "note": "..." }
    // ─────────────────────────────────────────────────────────────
    const RANK_ICON_SVG = '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">' +
        '<path stroke-linecap="round" stroke-linejoin="round" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m0 0a2 2 0 002 2h2a2 2 0 002-2v-3a2 2 0 00-2-2h-2a2 2 0 00-2 2z"></path>' +
        '</svg>';

    function normalizeAnswer(s) {
        return (s || '')
            .toLowerCase()
            .trim()
            .replace(/[^a-zа-яё0-9 ]/gi, '')
            .replace(/\s+/g, ' ');
    }

    register('top-answers', function (el, config) {
        const answers = (config.answers || []).map(function (a) {
            return { text: a.text, percent: a.percent, revealed: false };
        });
        const total = answers.length;
        let strikes = 0;
        let messageTimer = null;

        el.innerHTML =
            '<div class="textbook-widget">' +
                '<div class="textbook-widget__header">' +
                    '<span class="textbook-widget__icon">' + RANK_ICON_SVG + '</span>' +
                    '<div>' +
                        '<div class="textbook-widget__title">' + escapeHtml(el.dataset.title || 'Разминка: 100 к одному') + '</div>' +
                        '<div class="textbook-widget__subtitle">Угадайте топ-' + total + ' ответов</div>' +
                    '</div>' +
                    '<div class="textbook-widget__counter" data-role="counter">0/' + total + ' угадано</div>' +
                '</div>' +
                '<div class="textbook-widget__body">' +
                    '<p class="tw-topanswers__question">' + escapeHtml(config.question || '') + '</p>' +
                    '<div class="tw-topanswers__rows" data-role="rows"></div>' +
                    '<div class="tw-topanswers__controls">' +
                        '<input type="text" class="tw-topanswers__input" data-role="input" placeholder="Ваш вариант ответа…">' +
                        '<button type="button" class="tw-topanswers__btn tw-topanswers__btn--primary" data-role="submit">Ответить</button>' +
                        '<button type="button" class="tw-topanswers__btn tw-topanswers__btn--secondary" data-role="reveal-all">Показать все</button>' +
                    '</div>' +
                    '<div class="tw-topanswers__meta">' +
                        '<div class="tw-topanswers__strikes" data-role="strikes"></div>' +
                        '<span class="tw-topanswers__message" data-role="message"></span>' +
                    '</div>' +
                    (config.note ? '<p class="tw-topanswers__note">' + escapeHtml(config.note) + '</p>' : '') +
                '</div>' +
            '</div>';

        const rowsEl = el.querySelector('[data-role="rows"]');
        const counterEl = el.querySelector('[data-role="counter"]');
        const strikesEl = el.querySelector('[data-role="strikes"]');
        const messageEl = el.querySelector('[data-role="message"]');
        const inputEl = el.querySelector('[data-role="input"]');

        function renderRows() {
            rowsEl.innerHTML = answers.map(function (a, i) {
                return '<div class="tw-topanswers__row' + (a.revealed ? ' is-revealed' : '') + '">' +
                    '<span class="tw-topanswers__rank">' + (i + 1) + '</span>' +
                    '<span class="tw-topanswers__label">' + (a.revealed ? escapeHtml(a.text) : 'Ваш вариант…') + '</span>' +
                    (a.revealed ? '<span class="tw-topanswers__percent">' + a.percent + '%</span>' : '') +
                    '</div>';
            }).join('');
            const revealedCount = answers.filter(function (a) { return a.revealed; }).length;
            counterEl.textContent = revealedCount + '/' + total + ' угадано';
        }

        function renderStrikes() {
            strikesEl.innerHTML = [0, 1, 2].map(function (i) {
                return '<span class="tw-topanswers__strike' + (i < strikes ? ' is-active' : '') + '"></span>';
            }).join('');
        }

        function showMessage(text) {
            messageEl.textContent = text;
            clearTimeout(messageTimer);
            messageTimer = setTimeout(function () { messageEl.textContent = ''; }, 1600);
        }

        function submitGuess() {
            const norm = normalizeAnswer(inputEl.value);
            inputEl.value = '';
            if (!norm) return;

            let match = null;
            for (const a of answers) {
                if (a.revealed) continue;
                const words = normalizeAnswer(a.text).split(/[\s/]+/).filter(Boolean);
                if (words.some(function (w) { return w.length > 2 && (norm.includes(w) || w.includes(norm)); })) {
                    match = a;
                    break;
                }
            }

            if (match) {
                match.revealed = true;
                renderRows();
            } else {
                strikes = Math.min(strikes + 1, 3);
                renderStrikes();
                showMessage('Такого ответа нет в топ-' + total);
            }
        }

        function revealAll() {
            answers.forEach(function (a) { a.revealed = true; });
            renderRows();
        }

        el.querySelector('[data-role="submit"]').addEventListener('click', submitGuess);
        el.querySelector('[data-role="reveal-all"]').addEventListener('click', revealAll);
        inputEl.addEventListener('keydown', function (e) {
            if (e.key === 'Enter') submitGuess();
        });

        renderRows();
        renderStrikes();
    });

    // ─────────────────────────────────────────────────────────────
    // Виджет: embed — внешний iframe (Python Tutor, GeoGebra и т.п.).
    // Конфиг: { "src": "https://...", "height": 480 }.
    // ─────────────────────────────────────────────────────────────
    register('embed', function (el, config) {
        if (!config.src) {
            el.innerHTML = '<p class="text-sm text-red-500">embed: не задан src</p>';
            return;
        }
        const iframe = document.createElement('iframe');
        iframe.src = config.src;
        iframe.loading = 'lazy';
        iframe.className = 'w-full rounded-lg border-0';
        iframe.style.height = (parseInt(config.height, 10) || 480) + 'px';
        iframe.setAttribute('frameborder', '0');
        iframe.setAttribute('allowfullscreen', '');
        const body = widgetFrame(el, el.dataset.title);
        body.style.padding = '0';
        body.appendChild(iframe);
    });

    document.addEventListener('DOMContentLoaded', function () {
        init();
    });
})();
