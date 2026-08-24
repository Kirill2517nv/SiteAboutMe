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
    // Конфиг: { "value": 42, "bits": 8 }. Биты кликабельны — под ними
    // пересчитывается на лету формула по весам разрядов, например
    // «1·2⁷ + 0·2⁶ + … = 137».
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

        const formula = document.createElement('div');
        formula.className = 'mt-4 text-center text-base text-gray-700 dark:text-slate-200 font-mono break-words';

        function render() {
            const masked = bitsCount === 32 ? (value >>> 0) : (value & ((1 << bitsCount) - 1));
            const parts = [];
            cells.forEach(function (cell) {
                const i = parseInt(cell.dataset.bit, 10);
                const on = (masked >>> i) & 1;
                cell._val.textContent = on ? '1' : '0';
                cell.className = 'w-9 h-11 rounded-md font-mono text-lg flex flex-col items-center justify-center border transition-colors ' +
                    (on
                        ? 'bg-brand-600 text-white border-brand-600 dark:bg-cyan-500 dark:border-cyan-500'
                        : 'bg-gray-50 text-gray-400 border-gray-200 dark:bg-slate-700 dark:border-slate-600');
                parts.push(on + '·2<sup>' + i + '</sup>');
            });
            formula.innerHTML = parts.join(' + ') + ' = <b class="text-gray-900 dark:text-white">' + masked + '</b>';
        }

        const body = widgetFrame(el, el.dataset.title);
        body.appendChild(wrap);
        wrap.appendChild(bitsRow);
        wrap.appendChild(formula);
        render();
    });

    // ─────────────────────────────────────────────────────────────
    // Виджет: signed-bits — один и тот же набор битов в двух чтениях
    // одновременно: беззнаковом и знаковом (дополнительный код).
    // Главная мысль виджета: в памяти биты выглядят одинаково, разное —
    // только правило, по которому их читают. Поэтому панели показываются
    // сразу обе, без переключателя.
    // Биты кликабельны; старший разряд выделен цветом (у него в знаковом
    // чтении отрицательный вес). Под битами — строка «что лежит в памяти»,
    // ниже две панели с разложением по весам разрядов. Кнопка
    // «инвертировать и +1» повторяет алгоритм перевода в дополнительный
    // код: знаковое чтение меняет знак, беззнаковое — нет.
    // Конфиг: { "value": 251, "bits": 8 }. bits — от 4 до 16; value можно
    // задавать и отрицательным ({"value": -5} — то же, что 251 при 8 битах).
    // ─────────────────────────────────────────────────────────────
    register('signed-bits', function (el, config) {
        const bitsCount = Math.min(Math.max(parseInt(config.bits, 10) || 8, 4), 16);
        const total = 1 << bitsCount;        // 2^n — размер кольца значений
        const mask = total - 1;
        const half = total >> 1;             // 2^(n-1) — вес старшего разряда
        // Значение всегда храним беззнаковым: & mask заодно превращает
        // отрицательный value из конфига в его дополнительный код.
        let value = (parseInt(config.value, 10) || 0) & mask;

        const body = widgetFrame(el, el.dataset.title || 'Одни биты — два чтения');

        const btnChip = 'px-2.5 py-1 rounded-full text-xs border transition-colors bg-gray-50 text-gray-500 border-gray-200 hover:bg-gray-100 dark:bg-slate-700 dark:border-slate-600 dark:text-slate-300';
        const btnAction = 'px-3 py-1 rounded-full text-xs border transition-colors bg-brand-600 text-white border-brand-600 hover:bg-brand-700 dark:bg-cyan-500 dark:border-cyan-500 dark:hover:bg-cyan-400';

        const CELL_BASE = 'w-9 h-11 rounded-md font-mono text-lg flex flex-col items-center justify-center border transition-colors';
        const CELL_ON = 'bg-brand-600 text-white border-brand-600 dark:bg-cyan-500 dark:border-cyan-500';
        const CELL_ON_SIGN = 'bg-amber-500 text-white border-amber-500 dark:bg-amber-500 dark:border-amber-500';
        const CELL_OFF = 'bg-gray-50 text-gray-400 border-gray-200 dark:bg-slate-700 dark:border-slate-600';

        const bitsRow = document.createElement('div');
        bitsRow.className = 'flex flex-wrap gap-1 justify-center';

        const cells = [];
        for (let i = bitsCount - 1; i >= 0; i--) {
            const cell = document.createElement('button');
            cell.type = 'button';
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
                value = (value ^ (1 << i)) & mask;
                render();
            });
            cells.push(cell);
            bitsRow.appendChild(cell);
        }

        const signHint = document.createElement('div');
        signHint.className = 'mt-2 text-center text-xs text-gray-400 dark:text-slate-400';
        signHint.innerHTML = 'слева — старший разряд (номер ' + (bitsCount - 1) +
            '), <span class="text-amber-600 dark:text-amber-400">выделен цветом</span>: ' +
            'именно у него в знаковом чтении вес отрицательный';

        const memLine = document.createElement('div');
        memLine.className = 'mt-4 text-center font-mono text-base text-gray-700 dark:text-slate-200';

        const controls = document.createElement('div');
        controls.className = 'mt-4 flex flex-wrap gap-2 justify-center items-center';

        function presetBtn(label, v, title) {
            const b = document.createElement('button');
            b.type = 'button';
            b.className = btnChip;
            b.textContent = label;
            if (title) b.title = title;
            b.addEventListener('click', function () {
                value = v & mask;
                render();
            });
            return b;
        }

        controls.appendChild(presetBtn('0', 0, 'все биты выключены'));
        controls.appendChild(presetBtn('1', 1));
        controls.appendChild(presetBtn('максимум +', half - 1, 'наибольшее положительное знаковое'));
        controls.appendChild(presetBtn('минимум −', half, 'наименьшее отрицательное знаковое'));
        controls.appendChild(presetBtn('все единицы', mask, 'в знаковом чтении это −1'));

        const negBtn = document.createElement('button');
        negBtn.type = 'button';
        negBtn.className = btnAction;
        negBtn.textContent = 'инвертировать и +1';
        negBtn.title = 'алгоритм перевода в дополнительный код: знаковое чтение сменит знак';
        negBtn.addEventListener('click', function () {
            value = (~value + 1) & mask;
            render();
        });
        controls.appendChild(negBtn);

        const panels = document.createElement('div');
        panels.className = 'mt-5 grid gap-3 sm:grid-cols-2';

        function panel(headerText, boxClass, textClass) {
            const box = document.createElement('div');
            box.className = 'rounded-lg border p-3 ' + boxClass;
            const head = document.createElement('div');
            head.className = 'text-xs font-semibold mb-2 ' + textClass;
            head.textContent = headerText;
            const formula = document.createElement('div');
            formula.className = 'font-mono text-xs leading-relaxed break-words text-gray-600 dark:text-slate-300';
            const result = document.createElement('div');
            result.className = 'mt-2 font-mono text-2xl font-bold text-gray-900 dark:text-white';
            box.appendChild(head);
            box.appendChild(formula);
            box.appendChild(result);
            panels.appendChild(box);
            return { formula: formula, result: result };
        }

        const unsignedPanel = panel(
            'Беззнаковое чтение',
            'bg-sky-100 border-sky-300 dark:bg-sky-900/30 dark:border-sky-700',
            'text-sky-700 dark:text-sky-300'
        );
        const signedPanel = panel(
            'Знаковое чтение (дополнительный код)',
            'bg-amber-100 border-amber-300 dark:bg-amber-900/30 dark:border-amber-700',
            'text-amber-700 dark:text-amber-300'
        );

        const noteLine = document.createElement('div');
        noteLine.className = 'mt-4 text-center text-sm text-gray-500 dark:text-slate-400';

        body.appendChild(bitsRow);
        body.appendChild(signHint);
        body.appendChild(memLine);
        body.appendChild(controls);
        body.appendChild(panels);
        body.appendChild(noteLine);

        function bitString() {
            let s = '';
            for (let i = bitsCount - 1; i >= 0; i--) s += ((value >>> i) & 1);
            return s;
        }

        // В тексте учебника используется типографский минус (U+2212), а JS
        // печатает обычный дефис — приводим к виду, привычному по уроку.
        function num(n) {
            return String(n).replace('-', '−');
        }

        function render() {
            cells.forEach(function (cell) {
                const i = parseInt(cell.dataset.bit, 10);
                const on = (value >>> i) & 1;
                const isSign = i === bitsCount - 1;
                cell._val.textContent = on ? '1' : '0';
                cell.className = CELL_BASE + ' ' +
                    (on ? (isSign ? CELL_ON_SIGN : CELL_ON) : CELL_OFF);
            });

            const bits = bitString();
            let mem = 'в памяти лежит: <b class="text-gray-900 dark:text-white">' + bits + '</b>';
            if (bitsCount % 4 === 0) {
                const hex = value.toString(16).toUpperCase().padStart(bitsCount / 4, '0');
                mem += ' <span class="text-gray-400">= 0x' + hex + '</span>';
            }
            memLine.innerHTML = mem;

            // Разложение по весам разрядов: формулы отличаются ровно одним
            // слагаемым — весом старшего разряда (+2^(n-1) или −2^(n-1)).
            const uParts = [];
            const sParts = [];
            for (let i = bitsCount - 1; i >= 0; i--) {
                const on = (value >>> i) & 1;
                uParts.push(on + '·2<sup>' + i + '</sup>');
                if (i === bitsCount - 1) {
                    sParts.push('<span class="text-amber-700 dark:text-amber-300 font-bold">' +
                        (on ? '−1' : '0') + '·2<sup>' + i + '</sup></span>');
                } else {
                    sParts.push(on + '·2<sup>' + i + '</sup>');
                }
            }

            const signed = value >= half ? value - total : value;
            unsignedPanel.formula.innerHTML = uParts.join(' + ');
            unsignedPanel.result.textContent = num(value);
            signedPanel.formula.innerHTML = sParts.join(' + ');
            signedPanel.result.textContent = num(signed);

            if (value >= half) {
                noteLine.innerHTML = 'Старший бит равен 1 — знаковое чтение отрицательное: ' +
                    value + ' − 2<sup>' + bitsCount + '</sup> = ' + value + ' − ' + total +
                    ' = <b>' + num(signed) + '</b>.';
            } else {
                noteLine.innerHTML = 'Старший бит равен 0 — оба чтения дают одно и то же число. ' +
                    'Различия начинаются с ' + half + '.';
            }
        }

        render();
    });

    // ─────────────────────────────────────────────────────────────
    // Виджет: float-bits — вещественное число по стандарту IEEE 754,
    // разложенное на три поля: знак S, порядок E (хранится со смещением)
    // и мантисса M (со скрытым старшим битом).
    //
    // Главная мысль виджета: десятичное число, которое видит человек, и
    // то, что реально лежит в памяти, — разные числа. Поэтому под битами
    // всегда две строки: «Python выведет» (кратчайшая запись, которая
    // читается обратно в те же биты) и «в памяти лежит ровно» — точное
    // значение, посчитанное на BigInt, без потери цифр.
    //
    // Биты кликабельны. Кнопки «соседнее представимое» сдвигают биты как
    // целое на ±1 и показывают шаг сетки: у 0,1 он около 10⁻¹⁷, у чисел
    // порядка 2⁵³ — уже 2. Особые случаи (±∞, NaN, ноль, субнормальные
    // числа) виджет распознаёт и подписывает.
    //
    // Конфиг: { "value": 0.1, "bits": 64 }. bits: 64 (binary64 — тип
    // float в Python, значение по умолчанию) или 32 (binary32).
    // value — число или строка: "0,1", "1/3", "inf", "nan".
    // ─────────────────────────────────────────────────────────────
    register('float-bits', function (el, config) {
        const isDouble = parseInt(config.bits, 10) !== 32;
        const TOTAL = isDouble ? 64 : 32;
        const EXP_BITS = isDouble ? 11 : 8;
        const MANT_BITS = isDouble ? 52 : 23;
        const BIAS = isDouble ? 1023 : 127;
        const EXP_ALL_ONES = (1 << EXP_BITS) - 1;
        const MANT_MASK = (1n << BigInt(MANT_BITS)) - 1n;
        const INF_BITS = BigInt(EXP_ALL_ONES) << BigInt(MANT_BITS);
        const SIGN_BIT = 1n << BigInt(TOTAL - 1);
        // Длинные дроби (особенно субнормальные) дают сотни цифр — обрезаем.
        const MAX_FRAC_DIGITS = 60;

        const buf = new ArrayBuffer(8);
        const dv = new DataView(buf);

        function bitsOf(x) {
            if (isDouble) {
                dv.setFloat64(0, x);
                return dv.getBigUint64(0);
            }
            dv.setFloat32(0, x);
            return BigInt(dv.getUint32(0));
        }

        function numberOf(b) {
            if (isDouble) {
                dv.setBigUint64(0, b);
                return dv.getFloat64(0);
            }
            dv.setUint32(0, Number(b & 0xFFFFFFFFn));
            return dv.getFloat32(0);
        }

        // "0,1" / "1/3" / "inf" / "nan" → число. null — не разобрали.
        function parseValue(text) {
            let t = String(text).trim().toLowerCase()
                .replace(/\s+/g, '').replace(/[−–—]/g, '-').replace(',', '.');
            if (t === '') return null;
            if (t === 'inf' || t === '+inf' || t === '∞' || t === '+∞') return Infinity;
            if (t === '-inf' || t === '-∞') return -Infinity;
            if (t === 'nan') return NaN;
            const frac = t.match(/^(-?\d+(?:\.\d+)?)\/(-?\d+(?:\.\d+)?)$/);
            if (frac) return Number(frac[1]) / Number(frac[2]);
            if (!/^[-+]?(\d+(\.\d*)?|\.\d+)(e[-+]?\d+)?$/.test(t)) return null;
            return Number(t);
        }

        let bits = bitsOf((function () {
            const v = config.value === undefined ? 0.1 : parseValue(config.value);
            return v === null ? 0.1 : v;
        })());

        function getBit(i) {
            return Number((bits >> BigInt(i)) & 1n);
        }
        function expField() {
            return Number((bits >> BigInt(MANT_BITS)) & BigInt(EXP_ALL_ONES));
        }
        function mantField() {
            return bits & MANT_MASK;
        }
        function bitString(from, width) {
            let s = '';
            for (let i = from + width - 1; i >= from; i--) s += getBit(i);
            return s;
        }

        // Точное десятичное значение набора битов. Любая двоичная дробь
        // конечна в десятичной записи, поэтому «ровно» здесь буквальное:
        // mant·2⁻ᵏ = mant·5ᵏ / 10ᵏ, а BigInt считает mant·5ᵏ без потерь.
        // Возвращает части записи: {sign, int, frac}; null — ±∞ или NaN.
        function exactParts() {
            const E = expField();
            if (E === EXP_ALL_ONES) return null;   // ±∞ и NaN — не числа
            const sign = getBit(TOTAL - 1) ? '-' : '';
            let mant, exp;
            if (E === 0) {
                mant = mantField();                // субнормальное или ноль
                exp = 1 - BIAS - MANT_BITS;
            } else {
                mant = (1n << BigInt(MANT_BITS)) | mantField();
                exp = E - BIAS - MANT_BITS;
            }
            if (mant === 0n) return { sign: sign, int: '0', frac: '' };
            if (exp >= 0) {
                return { sign: sign, int: (mant << BigInt(exp)).toString(), frac: '' };
            }
            const k = -exp;
            let digits = (mant * 5n ** BigInt(k)).toString();
            if (digits.length <= k) digits = '0'.repeat(k - digits.length + 1) + digits;
            return {
                sign: sign,
                int: digits.slice(0, digits.length - k),
                frac: digits.slice(digits.length - k).replace(/0+$/, ''),
            };
        }

        // Каноническая форма десятичной записи: знак + значащие цифры + порядок.
        // Нужна, чтобы сравнить точное значение с кратчайшей печатной записью,
        // не завязываясь на формат («0.1» и «1e-1» дают одну и ту же строку).
        function canonDecimal(intPart, frac, sign) {
            let digits = intPart + frac;
            let exp = -frac.length;
            const lead = digits.search(/[1-9]/);
            if (lead === -1) return '0';
            digits = digits.slice(lead);
            const trail = digits.match(/0*$/)[0].length;
            if (trail) {
                digits = digits.slice(0, digits.length - trail);
                exp += trail;
            }
            return (sign === '-' ? '-' : '') + digits + 'e' + exp;
        }

        function canonOfNumber(x) {
            const m = String(x).match(/^([-+]?)(\d*)(?:\.(\d*))?(?:[eE]([-+]?\d+))?$/);
            if (!m) return null;
            const frac = m[3] || '';
            const base = canonDecimal(m[2] || '0', frac, m[1]);
            if (base === '0' || !m[4]) return base;
            const parts = base.split('e');
            return parts[0] + 'e' + (parseInt(parts[1], 10) + parseInt(m[4], 10));
        }

        // Длинные записи (сотни цифр у субнормальных и у больших степеней
        // двойки) читать бессмысленно — показываем значащие цифры и порядок.
        function formatExact(parts) {
            const sign = parts.sign === '-' ? '−' : '';
            const digits = parts.int + parts.frac;
            const lead = digits.search(/[1-9]/);
            if (lead === -1) return sign + '0';

            const shortEnough = parts.int.length <= MAX_FRAC_DIGITS &&
                parts.frac.length <= MAX_FRAC_DIGITS;
            if (shortEnough) {
                return sign + parts.int + (parts.frac ? ',' + parts.frac : '');
            }
            // Порядок = позиция первой значащей цифры относительно запятой.
            const exp = parts.int.length - lead - 1;
            let sig = digits.slice(lead).replace(/0+$/, '');
            const cut = sig.length > MAX_FRAC_DIGITS;
            if (cut) sig = sig.slice(0, MAX_FRAC_DIGITS);
            const head = sig.slice(0, 1);
            const tail = sig.slice(1);
            return sign + head + (tail ? ',' + tail : '') + (cut ? '…' : '') +
                '·10<sup>' + String(exp).replace('-', '−') + '</sup>';
        }

        // Кратчайшая запись — то, что напечатает print(): и Python, и JS
        // выводят минимальную строку, читающуюся обратно в те же биты.
        function shortRepr() {
            const v = numberOf(bits);
            if (Number.isNaN(v)) return 'nan';
            if (v === Infinity) return 'inf';
            if (v === -Infinity) return '-inf';
            if (Object.is(v, -0)) return '-0.0';
            const s = String(v);
            return s.indexOf('.') === -1 && s.indexOf('e') === -1 ? s + '.0' : s;
        }

        function sci(x) {
            const s = x.toExponential(2);
            const parts = s.split('e');
            const exp = parseInt(parts[1], 10);
            return parts[0].replace('.', ',').replace('-', '−') +
                '·10<sup>' + String(exp).replace('-', '−') + '</sup>';
        }

        const body = widgetFrame(el, el.dataset.title ||
            ('Вещественное число в памяти: ' + TOTAL + ' бита'));

        const CELL_BASE = 'h-6 w-4 rounded-sm font-mono text-[10px] leading-none flex items-center justify-center border transition-colors';
        const CELL_OFF = 'bg-white text-gray-300 border-gray-200 dark:bg-slate-800 dark:border-slate-600 dark:text-slate-500';
        const CELL_SIGN = 'bg-amber-500 text-white border-amber-500';
        const CELL_EXP = 'bg-sky-600 text-white border-sky-600 dark:bg-sky-500 dark:border-sky-500';
        const CELL_MANT = 'bg-violet-600 text-white border-violet-600 dark:bg-violet-500 dark:border-violet-500';

        const btnChip = 'px-2.5 py-1 rounded-full text-xs border transition-colors bg-gray-50 text-gray-500 border-gray-200 hover:bg-gray-100 dark:bg-slate-700 dark:border-slate-600 dark:text-slate-300';
        const btnAction = 'px-3 py-1 rounded-full text-xs border transition-colors bg-brand-600 text-white border-brand-600 hover:bg-brand-700 dark:bg-cyan-500 dark:border-cyan-500 dark:hover:bg-cyan-400';

        // ---- строка ввода и пресеты ----
        const inputRow = document.createElement('div');
        inputRow.className = 'flex flex-wrap items-center justify-center gap-2';

        const inputLabel = document.createElement('label');
        inputLabel.className = 'text-sm text-gray-600 dark:text-slate-300';
        inputLabel.textContent = 'Десятичное значение:';

        const input = document.createElement('input');
        input.type = 'text';
        input.value = '0,1';
        input.placeholder = '0,1';
        input.className = 'w-64 max-w-full text-center rounded-md border px-2 py-1 font-mono text-base border-gray-200 bg-white text-gray-900 dark:border-slate-600 dark:bg-slate-800 dark:text-white';
        input.addEventListener('change', function () {
            const v = parseValue(input.value);
            if (v === null) {
                input.classList.add('border-red-400');
                return;
            }
            input.classList.remove('border-red-400');
            bits = bitsOf(v);
            render();
        });

        inputRow.appendChild(inputLabel);
        inputRow.appendChild(input);

        const presets = document.createElement('div');
        presets.className = 'mt-2 flex flex-wrap gap-1.5 justify-center';

        function preset(label, text, hint) {
            const b = document.createElement('button');
            b.type = 'button';
            b.className = btnChip;
            b.innerHTML = label;
            if (hint) b.title = hint;
            b.addEventListener('click', function () {
                bits = bitsOf(parseValue(text));
                input.value = text;
                input.classList.remove('border-red-400');
                render();
            });
            return b;
        }

        [
            ['0,1', '0,1', 'бесконечная двоичная дробь — точно не записывается'],
            ['0,2', '0,2', null],
            ['0,3', '0,3', 'округлилось вниз, в отличие от 0,1 и 0,2'],
            ['0,5', '0,5', 'знаменатель — степень двойки, записывается точно'],
            ['5,75', '5,75', 'пример, который в уроке разобран вручную'],
            ['1/3', '1/3', null],
            ['2<sup>53</sup>', '9007199254740992', 'дальше соседние целые числа уже не различаются'],
            ['∞', 'inf', 'порядок из всех единиц, мантисса нулевая'],
            ['NaN', 'nan', 'порядок из всех единиц, мантисса ненулевая'],
        ].forEach(function (p) {
            presets.appendChild(preset(p[0], p[1], p[2]));
        });

        const sumBtn = document.createElement('button');
        sumBtn.type = 'button';
        sumBtn.className = btnAction;
        sumBtn.textContent = '0,1 + 0,2';
        sumBtn.title = 'результат сложения — не то же самое, что 0,3';
        sumBtn.addEventListener('click', function () {
            bits = bitsOf(0.1 + 0.2);
            input.value = shortRepr().replace('.', ',');
            render();
        });
        presets.appendChild(sumBtn);

        // ---- три поля битов ----
        const formulaHint = document.createElement('div');
        formulaHint.className = 'mt-5 text-center font-mono text-sm text-gray-500 dark:text-slate-400';
        formulaHint.innerHTML = 'v = (−1)<sup>S</sup> · (1 + M/2<sup>' + MANT_BITS +
            '</sup>) · 2<sup>E − ' + BIAS + '</sup>';

        const fields = document.createElement('div');
        fields.className = 'mt-3 flex flex-wrap gap-3';

        const cells = [];

        function fieldBox(title, from, width, onClass, boxClass, textClass, full) {
            const box = document.createElement('div');
            box.className = 'rounded-lg border p-2.5 ' + boxClass + (full ? ' w-full' : ' shrink-0');
            const head = document.createElement('div');
            head.className = 'text-[11px] font-semibold mb-1.5 ' + textClass;
            head.textContent = title;
            const row = document.createElement('div');
            row.className = 'flex flex-wrap gap-px';
            for (let i = from + width - 1; i >= from; i--) {
                const cell = document.createElement('button');
                cell.type = 'button';
                cell.title = 'бит ' + i;
                cell.setAttribute('aria-label', 'Переключить бит ' + i);
                cell.addEventListener('click', (function (index) {
                    return function () {
                        bits ^= (1n << BigInt(index));
                        input.value = shortRepr().replace('.', ',');
                        render();
                    };
                })(i));
                cells.push({ index: i, el: cell, on: onClass });
                row.appendChild(cell);
            }
            box.appendChild(head);
            box.appendChild(row);
            fields.appendChild(box);
        }

        fieldBox('Знак S', TOTAL - 1, 1, CELL_SIGN,
            'bg-amber-50 border-amber-300 dark:bg-amber-900/30 dark:border-amber-700',
            'text-amber-700 dark:text-amber-300', false);
        fieldBox('Порядок E (' + EXP_BITS + ' битов)', MANT_BITS, EXP_BITS, CELL_EXP,
            'bg-sky-50 border-sky-300 dark:bg-sky-900/30 dark:border-sky-700',
            'text-sky-700 dark:text-sky-300', false);
        fieldBox('Мантисса M (' + MANT_BITS + ' битов)', 0, MANT_BITS, CELL_MANT,
            'bg-violet-50 border-violet-300 dark:bg-violet-900/30 dark:border-violet-700',
            'text-violet-700 dark:text-violet-300', true);

        const clickHint = document.createElement('div');
        clickHint.className = 'mt-2 text-center text-xs text-gray-400 dark:text-slate-400';
        clickHint.textContent = 'биты можно переключать щелчком — значение пересчитается';

        // ---- панели разбора полей ----
        const panels = document.createElement('div');
        panels.className = 'mt-4 grid gap-3 sm:grid-cols-3';

        function panel(headerText, boxClass, textClass) {
            const box = document.createElement('div');
            box.className = 'rounded-lg border p-3 ' + boxClass;
            const head = document.createElement('div');
            head.className = 'text-xs font-semibold mb-2 ' + textClass;
            head.textContent = headerText;
            const value = document.createElement('div');
            value.className = 'font-mono text-xl font-bold text-gray-900 dark:text-white break-all';
            const detail = document.createElement('div');
            detail.className = 'mt-1 font-mono text-[11px] leading-relaxed text-gray-500 dark:text-slate-400 break-all';
            box.appendChild(head);
            box.appendChild(value);
            box.appendChild(detail);
            panels.appendChild(box);
            return { value: value, detail: detail };
        }

        const signPanel = panel('Знак',
            'bg-amber-50 border-amber-300 dark:bg-amber-900/30 dark:border-amber-700',
            'text-amber-700 dark:text-amber-300');
        const expPanel = panel('Порядок',
            'bg-sky-50 border-sky-300 dark:bg-sky-900/30 dark:border-sky-700',
            'text-sky-700 dark:text-sky-300');
        const mantPanel = panel('Мантисса',
            'bg-violet-50 border-violet-300 dark:bg-violet-900/30 dark:border-violet-700',
            'text-violet-700 dark:text-violet-300');

        // ---- две строки: что печатается и что лежит в памяти ----
        const results = document.createElement('div');
        results.className = 'mt-4 rounded-lg border border-gray-200 dark:border-slate-600 divide-y divide-gray-200 dark:divide-slate-600';

        function resultRow(label) {
            const row = document.createElement('div');
            row.className = 'p-3';
            const head = document.createElement('div');
            head.className = 'text-[11px] text-gray-400 dark:text-slate-400 mb-1';
            head.textContent = label;
            const val = document.createElement('div');
            val.className = 'font-mono text-sm text-gray-900 dark:text-white break-all';
            row.appendChild(head);
            row.appendChild(val);
            results.appendChild(row);
            return val;
        }

        const printedLine = resultRow('Python выведет — print(x)');
        const exactLine = resultRow('В памяти лежит ровно');

        const noteLine = document.createElement('div');
        noteLine.className = 'mt-3 text-sm text-gray-500 dark:text-slate-400';

        // ---- соседние представимые числа ----
        const stepRow = document.createElement('div');
        stepRow.className = 'mt-4 flex flex-wrap gap-2 justify-center items-center';

        function neighborBits(up) {
            const negative = (bits & SIGN_BIT) !== 0n;
            const magnitude = bits & ~SIGN_BIT;
            // Вверх по числовой оси: для положительных биты растут, для
            // отрицательных — убывают. Через ноль переходим на другой знак.
            const away = up !== negative;
            if (away) {
                if (magnitude >= INF_BITS) return bits;   // дальше только NaN
                return bits + 1n;
            }
            if (magnitude === 0n) return (bits ^ SIGN_BIT) | 1n;  // ±0 → минимальное с другим знаком
            return bits - 1n;
        }

        function stepBtn(label, up) {
            const b = document.createElement('button');
            b.type = 'button';
            b.className = btnChip;
            b.textContent = label;
            b.title = 'соседнее представимое число: биты как целое ±1';
            b.addEventListener('click', function () {
                if (Number.isNaN(numberOf(bits))) return;
                bits = neighborBits(up);
                input.value = shortRepr().replace('.', ',');
                render();
            });
            return b;
        }

        const ulpLine = document.createElement('span');
        ulpLine.className = 'text-xs text-gray-500 dark:text-slate-400';

        stepRow.appendChild(stepBtn('◂ предыдущее', false));
        stepRow.appendChild(stepBtn('следующее ▸', true));
        stepRow.appendChild(ulpLine);

        body.appendChild(inputRow);
        body.appendChild(presets);
        body.appendChild(formulaHint);
        body.appendChild(fields);
        body.appendChild(clickHint);
        body.appendChild(panels);
        body.appendChild(results);
        body.appendChild(noteLine);
        body.appendChild(stepRow);

        function render() {
            cells.forEach(function (c) {
                const on = getBit(c.index);
                c.el.textContent = on ? '1' : '0';
                c.el.className = CELL_BASE + ' ' + (on ? c.on : CELL_OFF);
            });

            const E = expField();
            const M = mantField();
            const negative = getBit(TOTAL - 1) === 1;
            const value = numberOf(bits);
            const special = E === EXP_ALL_ONES;
            const denormal = E === 0;

            signPanel.value.textContent = negative ? '−' : '+';
            signPanel.detail.innerHTML = 'S = ' + (negative ? 1 : 0) + ', множитель (−1)<sup>S</sup>';

            const expBits = bitString(MANT_BITS, EXP_BITS);
            if (special) {
                expPanel.value.textContent = 'служебный';
                expPanel.detail.innerHTML = 'E = ' + expBits +
                    ' — все единицы. Это не число, а маркер особого значения.';
            } else if (denormal) {
                expPanel.value.innerHTML = '2<sup>' + String(1 - BIAS).replace('-', '−') + '</sup>';
                expPanel.detail.innerHTML = 'E = ' + expBits +
                    ' — все нули: скрытого старшего бита нет, порядок фиксирован.';
            } else {
                expPanel.value.innerHTML = '2<sup>' + String(E - BIAS).replace('-', '−') + '</sup>';
                expPanel.detail.innerHTML = 'E = ' + expBits + ' = ' + E + ', порядок = ' +
                    E + ' − ' + BIAS + ' = ' + String(E - BIAS).replace('-', '−');
            }

            const mantBits = bitString(0, MANT_BITS).replace(/0+$/, '');
            if (special) {
                mantPanel.value.textContent = M === 0n ? 'нулевая' : 'ненулевая';
                mantPanel.detail.textContent = M === 0n
                    ? 'мантисса из нулей при служебном порядке — бесконечность'
                    : 'ненулевая мантисса при служебном порядке — NaN';
            } else {
                const lead = denormal ? '0' : '1';
                const frac = mantBits === '' ? '0' : mantBits;
                const mantValue = (denormal ? 0 : 1) + Number(M) / Math.pow(2, MANT_BITS);
                const shown = String(mantValue);
                mantPanel.value.innerHTML = shown.indexOf('e') === -1
                    ? shown.replace('.', ',')
                    : sci(mantValue);
                mantPanel.detail.innerHTML = lead + ',' + frac + '<sub>2</sub> = ' + lead +
                    ' + ' + M.toString() + '/2<sup>' + MANT_BITS + '</sup>';
            }

            printedLine.textContent = shortRepr();
            const parts = exactParts();
            let exactMatchesPrinted = false;
            if (parts === null) {
                exactLine.innerHTML = M === 0n
                    ? (negative ? '−∞' : '+∞') + ' — бесконечность, обычного значения нет'
                    : 'NaN — не число, значения нет';
            } else {
                exactLine.innerHTML = formatExact(parts);
                exactMatchesPrinted =
                    canonDecimal(parts.int, parts.frac, parts.sign) === canonOfNumber(value);
            }

            if (special) {
                noteLine.innerHTML = M === 0n
                    ? 'Порядок из всех единиц и нулевая мантисса — <b>бесконечность</b>. ' +
                      'Её можно получить переполнением: если умножать большое число на 10, ' +
                      'в какой-то момент результат перестанет влезать в ' + TOTAL + ' бита.'
                    : 'Порядок из всех единиц и ненулевая мантисса — <b>NaN</b>. ' +
                      'Такое значение не равно даже самому себе: сравнение x == x даёт False.';
            } else if (M === 0n && E === 0) {
                noteLine.innerHTML = 'Все биты, кроме знака, нулевые — это <b>ноль</b>. ' +
                    'Знак хранится отдельно, поэтому нулей формально два: +0,0 и −0,0. ' +
                    'При сравнении стандарт требует считать их равными.';
            } else if (denormal) {
                noteLine.innerHTML = 'Порядок из нулей — <b>субнормальное число</b>: скрытого ' +
                    'старшего бита нет, значащих цифр меньше обычного. Такие числа ' +
                    'позволяют плавно дотянуться до нуля, теряя точность.';
            } else if (exactMatchesPrinted) {
                noteLine.innerHTML = 'Это число <b>записано точно</b>: его знаменатель — ' +
                    'степень двойки, поэтому двоичная дробь конечна и обрезать нечего. ' +
                    'Напечатанное значение и есть то, что лежит в памяти.';
            } else if (parts !== null && parts.frac === '') {
                // Целое значение: двоичная дробь конечна, просто десятичная
                // запись слишком длинная, чтобы её печатать целиком.
                noteLine.innerHTML = 'Значение целое, и в памяти лежит ровно оно — ' +
                    'но его десятичная запись слишком длинная для печати, поэтому ' +
                    'print показывает <b>кратчайшую</b> запись: минимальную из тех, ' +
                    'которые читаются обратно в те же биты.';
            } else {
                noteLine.innerHTML = 'У этой десятичной дроби нет точного двоичного ' +
                    'представления, поэтому в памяти лежит <b>ближайшее представимое</b> ' +
                    'значение. Печатается при этом кратчайшая запись — минимальная из ' +
                    'тех, которые читаются обратно в те же биты, — и потому выглядит ' +
                    'аккуратнее, чем то, что хранится на самом деле.';
            }

            if (Number.isNaN(value) || !Number.isFinite(value)) {
                ulpLine.innerHTML = '';
            } else {
                const next = numberOf(neighborBits(true));
                const gap = Math.abs(next - value);
                ulpLine.innerHTML = gap === 0
                    ? ''
                    : 'шаг сетки здесь: ' + (gap >= 1 ? String(gap).replace('.', ',') : sci(gap));
            }
        }

        input.value = shortRepr().replace('.', ',');
        render();
    });

    // ─────────────────────────────────────────────────────────────
    // Виджет: bitwise-ops — четыре побитовые операции (& | ^ ~) над двумя
    // числами, записанными в столбик: a, b и результат выровнены по разрядам.
    //
    // Главная мысль виджета: разряды считаются независимо друг от друга —
    // каждый столбик сам по себе, никакого переноса, в отличие от сложения.
    // Поэтому строки жёстко выровнены по колонкам, а наведение на любой
    // разряд (или клик по нему) объясняет, как получился именно его бит.
    //
    // Биты строк a и b кликабельны, значения можно вводить и десятичным
    // числом. Переключатель меняет операцию; у унарного ~ строка b
    // скрывается, а под результатом появляется пояснение, почему Python
    // печатает −x−1, а не беззнаковое значение этих же битов.
    // Конфиг: { "a": 12, "b": 10, "bits": 8, "op": "&" }.
    // bits — от 4 до 16; op — "&", "|", "^" или "~".
    // ─────────────────────────────────────────────────────────────
    register('bitwise-ops', function (el, config) {
        const bitsCount = Math.min(Math.max(parseInt(config.bits, 10) || 8, 4), 16);
        const total = 1 << bitsCount;
        const mask = total - 1;

        // & mask заодно переводит отрицательное значение из конфига в его
        // дополнительный код — как в signed-bits.
        let a = (config.a === undefined ? 12 : parseInt(config.a, 10) || 0) & mask;
        let b = (config.b === undefined ? 10 : parseInt(config.b, 10) || 0) & mask;

        const OPS = [
            {
                key: '&', name: 'И', expr: 'a & b', unary: false,
                apply: function (x, y) { return x & y; },
                why: function (x, y) {
                    return x === 1 && y === 1 ? 'единицы у обоих' : 'хотя бы один ноль';
                },
            },
            {
                key: '|', name: 'ИЛИ', expr: 'a | b', unary: false,
                apply: function (x, y) { return x | y; },
                why: function (x, y) {
                    return x === 1 || y === 1 ? 'хотя бы одна единица' : 'нули у обоих';
                },
            },
            {
                key: '^', name: 'XOR', expr: 'a ^ b', unary: false,
                apply: function (x, y) { return x ^ y; },
                why: function (x, y) {
                    return x !== y ? 'биты различны' : 'биты одинаковы';
                },
            },
            {
                key: '~', name: 'НЕ', expr: '~a', unary: true,
                apply: function (x) { return (~x) & mask; },
                why: function (x) {
                    return x === 1 ? 'единица переворачивается в ноль' : 'ноль переворачивается в единицу';
                },
            },
        ];

        let op = OPS.filter(function (o) { return o.key === config.op; })[0] || OPS[0];

        const body = widgetFrame(el, el.dataset.title || 'Побитовые операции в столбик');

        const btnChip = 'px-2.5 py-1 rounded-full text-xs border transition-colors bg-gray-50 text-gray-500 border-gray-200 hover:bg-gray-100 dark:bg-slate-700 dark:border-slate-600 dark:text-slate-300';
        const btnActive = 'px-2.5 py-1 rounded-full text-xs border transition-colors bg-brand-600 text-white border-brand-600 dark:bg-cyan-500 dark:border-cyan-500';
        const inputClass = 'w-20 text-center rounded-md border px-2 py-1 font-mono text-base border-gray-200 bg-white text-gray-900 dark:border-slate-600 dark:bg-slate-800 dark:text-white';

        const CELL_BASE = 'w-8 h-10 shrink-0 rounded-md font-mono text-base flex items-center justify-center border transition-colors';
        const CELL_ON = 'bg-brand-600 text-white border-brand-600 dark:bg-cyan-500 dark:border-cyan-500';
        const CELL_OFF = 'bg-gray-50 text-gray-400 border-gray-200 dark:bg-slate-700 dark:border-slate-600';
        const RES_ON = 'bg-emerald-500 text-white border-emerald-500 dark:bg-emerald-500 dark:border-emerald-500';
        const RES_OFF = 'bg-emerald-50 text-emerald-600/50 border-emerald-200 dark:bg-slate-700 dark:border-slate-600 dark:text-slate-400';
        const HILITE = ' ring-2 ring-amber-400 dark:ring-amber-400';

        // Разряд под курсором — подсвечивается сразу во всех строках.
        let hover = null;

        // ── переключатель операции ───────────────────────────────
        const opRow = document.createElement('div');
        opRow.className = 'flex flex-wrap gap-2 justify-center';
        const opButtons = [];
        OPS.forEach(function (o) {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.innerHTML = '<span class="font-mono">' + escapeHtml(o.key) + '</span> ' + escapeHtml(o.name);
            btn.addEventListener('click', function () {
                op = o;
                hover = null;
                render();
            });
            opButtons.push({ btn: btn, op: o });
            opRow.appendChild(btn);
        });

        // ── строки в столбик ─────────────────────────────────────
        // Выравнивание по разрядам держится на одинаковой ширине ячеек, а не
        // на grid: строку b у операции ~ нужно уметь целиком скрывать, и в
        // grid соседние ячейки при этом уехали бы в освободившиеся места.
        const scroller = document.createElement('div');
        scroller.className = 'mt-4 overflow-x-auto';

        const table = document.createElement('div');
        table.className = 'inline-block min-w-full';
        scroller.appendChild(table);

        function makeRow() {
            const row = document.createElement('div');
            row.className = 'flex items-center gap-1 justify-center';
            const label = document.createElement('div');
            label.className = 'w-16 shrink-0 pr-2 text-right font-mono text-sm text-gray-500 dark:text-slate-400';
            const value = document.createElement('div');
            value.className = 'w-20 shrink-0 pl-2 font-mono text-sm text-gray-700 dark:text-slate-200';
            row.appendChild(label);
            row.appendChild(value);
            table.appendChild(row);
            return { row: row, label: label, value: value };
        }

        // Ячейки добавляются между label и value, поэтому вставляем before(value).
        function addCells(rowObj, interactive, onToggle) {
            const cells = [];
            for (let i = bitsCount - 1; i >= 0; i--) {
                const cell = document.createElement(interactive ? 'button' : 'div');
                if (interactive) {
                    cell.type = 'button';
                    cell.addEventListener('click', function () { onToggle(i); });
                }
                cell.dataset.bit = String(i);
                cell.addEventListener('mouseenter', function () { hover = i; render(); });
                cell.addEventListener('mouseleave', function () { hover = null; render(); });
                rowObj.row.insertBefore(cell, rowObj.value);
                cells[i] = cell;
            }
            return cells;
        }

        // Шапка с номерами разрядов
        const headRow = makeRow();
        headRow.label.textContent = 'разряд';
        for (let i = bitsCount - 1; i >= 0; i--) {
            const idx = document.createElement('div');
            idx.className = 'w-8 shrink-0 text-center text-[10px] text-gray-400 dark:text-slate-500';
            idx.textContent = i;
            headRow.row.insertBefore(idx, headRow.value);
        }

        const rowA = makeRow();
        rowA.label.textContent = 'a =';
        const cellsA = addCells(rowA, true, function (i) { a ^= (1 << i); a &= mask; render(); });

        const rowB = makeRow();
        rowB.label.textContent = 'b =';
        const cellsB = addCells(rowB, true, function (i) { b ^= (1 << i); b &= mask; render(); });

        const divider = document.createElement('div');
        divider.className = 'my-2 border-t border-gray-200 dark:border-slate-600';
        table.appendChild(divider);

        const rowR = makeRow();
        const cellsR = addCells(rowR, false, null);

        // ── подсказка про разряд и служебные строки ──────────────
        const hintLine = document.createElement('div');
        hintLine.className = 'mt-3 text-center text-sm text-gray-500 dark:text-slate-400 min-h-[1.5rem]';

        const controls = document.createElement('div');
        controls.className = 'mt-4 flex flex-wrap gap-3 justify-center items-center';

        const inputA = document.createElement('input');
        inputA.type = 'number';
        inputA.min = '0';
        inputA.max = String(mask);
        inputA.className = inputClass;
        inputA.setAttribute('aria-label', 'Значение a');
        inputA.addEventListener('input', function () {
            a = (parseInt(inputA.value, 10) || 0) & mask;
            render(true);
        });

        const inputB = document.createElement('input');
        inputB.type = 'number';
        inputB.min = '0';
        inputB.max = String(mask);
        inputB.className = inputClass;
        inputB.setAttribute('aria-label', 'Значение b');
        inputB.addEventListener('input', function () {
            b = (parseInt(inputB.value, 10) || 0) & mask;
            render(true);
        });

        const labelA = document.createElement('label');
        labelA.className = 'flex items-center gap-2 text-sm text-gray-500 dark:text-slate-400';
        labelA.innerHTML = '<span class="font-mono">a</span>';
        labelA.appendChild(inputA);

        const labelB = document.createElement('label');
        labelB.className = 'flex items-center gap-2 text-sm text-gray-500 dark:text-slate-400';
        labelB.innerHTML = '<span class="font-mono">b</span>';
        labelB.appendChild(inputB);

        controls.appendChild(labelA);
        controls.appendChild(labelB);

        const presets = document.createElement('div');
        presets.className = 'mt-3 flex flex-wrap gap-2 justify-center items-center';

        function presetBtn(label, va, vb, title) {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = btnChip;
            btn.textContent = label;
            if (title) btn.title = title;
            btn.addEventListener('click', function () {
                a = va & mask;
                b = vb & mask;
                render();
            });
            presets.appendChild(btn);
        }

        presetBtn('12 и 10', 12, 10, 'пример из урока');
        presetBtn('маска младших разрядов', 0b11001011 & mask, 0b1111, 'b оставляет только четыре младших бита числа a');
        presetBtn('b = все единицы', 0b10110100 & mask, mask, 'с XOR это инверсия a, с И — само a');
        presetBtn('b = 1', 7, 1, 'проверка чётности: a & 1');

        const noteLine = document.createElement('div');
        noteLine.className = 'mt-4 text-center text-sm text-gray-500 dark:text-slate-400';

        body.appendChild(opRow);
        body.appendChild(scroller);
        body.appendChild(hintLine);
        body.appendChild(controls);
        body.appendChild(presets);
        body.appendChild(noteLine);

        function num(n) {
            return String(n).replace('-', '−');
        }

        function paint(cell, on, isResult) {
            let cls = CELL_BASE + ' ' + (isResult
                ? (on ? RES_ON : RES_OFF)
                : (on ? CELL_ON : CELL_OFF));
            if (hover !== null && parseInt(cell.dataset.bit, 10) === hover) cls += HILITE;
            cell.className = cls;
            cell.textContent = on ? '1' : '0';
        }

        // fromInput: не трогаем сами поля ввода, чтобы не сбивать курсор.
        function render(fromInput) {
            const result = op.unary ? op.apply(a) : op.apply(a, b);

            for (let i = 0; i < bitsCount; i++) {
                paint(cellsA[i], (a >>> i) & 1, false);
                paint(cellsB[i], (b >>> i) & 1, false);
                paint(cellsR[i], (result >>> i) & 1, true);
            }

            rowB.row.style.display = op.unary ? 'none' : '';
            labelB.style.display = op.unary ? 'none' : '';

            rowA.value.textContent = '= ' + a;
            rowB.value.textContent = '= ' + b;
            rowR.label.innerHTML = '<b class="text-emerald-600 dark:text-emerald-400">' +
                escapeHtml(op.expr) + '</b> =';
            rowR.value.innerHTML = '= <b class="text-gray-900 dark:text-white">' + result + '</b>';

            opButtons.forEach(function (item) {
                item.btn.className = item.op === op ? btnActive : btnChip;
            });

            if (!fromInput) {
                inputA.value = String(a);
                inputB.value = String(b);
            }

            if (hover === null) {
                hintLine.textContent = 'Наведите на любой разряд — разберём, как получился его бит.';
            } else {
                const x = (a >>> hover) & 1;
                const y = (b >>> hover) & 1;
                const r = (result >>> hover) & 1;
                const expr = op.unary
                    ? '~' + x + ' = ' + r
                    : x + ' ' + op.key + ' ' + y + ' = ' + r;
                hintLine.innerHTML = 'разряд ' + hover + ': <b class="font-mono text-gray-900 dark:text-white">' +
                    escapeHtml(expr) + '</b> — ' + (op.unary ? op.why(x) : op.why(x, y));
            }

            if (op.unary) {
                const pythonValue = -a - 1;
                noteLine.innerHTML = 'В этих ' + bitsCount + ' разрядах результат — ' +
                    '<b>' + result + '</b>. А Python на <span class="font-mono">print(~' + a +
                    ')</span> выведет <b>' + num(pythonValue) + '</b>: у типа <span class="font-mono">int</span> ' +
                    'нет фиксированной ширины, слева получается бесконечная цепочка единиц — ' +
                    'то есть отрицательное число в дополнительном коде.';
            } else {
                noteLine.innerHTML = 'Каждый столбик считается сам по себе: переноса в соседний ' +
                    'разряд, как при сложении, здесь не бывает.';
            }
        }

        render();
    });

    // ─────────────────────────────────────────────────────────────
    // Виджет: shift-viewer — сдвиги << и >> в столбик.
    //
    // Главная мысль виджета: биты не меняются, меняется их разряд. Поэтому
    // строка исходного числа и строка результата выровнены по колонкам, а
    // наведение на любой разряд показывает, откуда в нём взялся бит (или
    // что бит въехал в освободившийся разряд).
    //
    // За границей ленты рисуется отдельная зона — она есть только у строки
    // результата, потому что именно туда уходят биты, вышедшие за край:
    //   << — зона слева: в режиме «n бит» разряды потеряны (пунктир,
    //        зачёркнуты), в режиме «Python» они остаются (число стало длиннее);
    //   >> — зона справа: выпавшие младшие биты, то есть остаток от деления.
    // Въехавшие в освободившиеся разряды биты подсвечены отдельным цветом:
    // у << это всегда нули, у >> — нули либо копии знакового бита.
    //
    // Биты исходного числа кликабельны, значение можно вводить и числом.
    // Переключатели: операция, величина сдвига, «знаковое» (дополнительный
    // код) и «Python: int без границ» — последний и показывает разницу между
    // переполнением при фиксированной ширине и ростом числа в Python.
    // Конфиг: { "value": 3, "bits": 8, "op": "<<", "k": 2,
    //           "signed": false, "python": true }.
    // bits — от 4 до 16; op — "<<" или ">>"; k — от 1 до min(bits, 8);
    // value можно задавать отрицательным (тогда обычно нужен "signed": true).
    // ─────────────────────────────────────────────────────────────
    register('shift-viewer', function (el, config) {
        const bitsCount = Math.min(Math.max(parseInt(config.bits, 10) || 8, 4), 16);
        const total = 1 << bitsCount;
        const mask = total - 1;
        const half = total >> 1;
        const maxK = Math.min(bitsCount, 8);

        let op = config.op === '>>' ? '>>' : '<<';
        let k = Math.min(Math.max(parseInt(config.k, 10) || 1, 1), maxK);
        let signed = config.signed === true;
        let python = config.python !== false;
        // & mask переводит отрицательное значение из конфига в дополнительный
        // код — как в signed-bits и bitwise-ops.
        let raw = (config.value === undefined ? 3 : parseInt(config.value, 10) || 0) & mask;

        const body = widgetFrame(el, el.dataset.title || 'Сдвиги в столбик');

        const btnChip = 'px-2.5 py-1 rounded-full text-xs border transition-colors bg-gray-50 text-gray-500 border-gray-200 hover:bg-gray-100 dark:bg-slate-700 dark:border-slate-600 dark:text-slate-300';
        const btnActive = 'px-2.5 py-1 rounded-full text-xs border transition-colors bg-brand-600 text-white border-brand-600 dark:bg-cyan-500 dark:border-cyan-500';
        const inputClass = 'w-24 text-center rounded-md border px-2 py-1 font-mono text-base border-gray-200 bg-white text-gray-900 dark:border-slate-600 dark:bg-slate-800 dark:text-white';

        const CELL_BASE = 'w-8 h-10 shrink-0 rounded-md font-mono text-base flex items-center justify-center border transition-colors';
        const CELL_ON = 'bg-brand-600 text-white border-brand-600 dark:bg-cyan-500 dark:border-cyan-500';
        const CELL_OFF = 'bg-gray-50 text-gray-400 border-gray-200 dark:bg-slate-700 dark:border-slate-600';
        const RES_ON = 'bg-emerald-500 text-white border-emerald-500 dark:bg-emerald-500 dark:border-emerald-500';
        const RES_OFF = 'bg-emerald-50 text-emerald-600/50 border-emerald-200 dark:bg-slate-700 dark:border-slate-600 dark:text-slate-400';
        // Разряды, освободившиеся после сдвига: в них въехал новый бит.
        const NEW_ON = 'bg-amber-400 text-white border-amber-400 dark:bg-amber-500 dark:border-amber-500';
        const NEW_OFF = 'bg-amber-50 text-amber-600 border-amber-300 dark:bg-amber-900/30 dark:border-amber-700 dark:text-amber-300';
        // Зона за краем ленты: уехавшие биты — потерянные и сохранившиеся.
        const LOST = 'border-dashed text-gray-400 border-gray-300 line-through dark:text-slate-500 dark:border-slate-600';
        const KEPT_ON = 'bg-sky-500 text-white border-sky-500 dark:bg-sky-500 dark:border-sky-500';
        const KEPT_OFF = 'bg-sky-50 text-sky-500/60 border-sky-200 dark:bg-slate-700 dark:border-slate-600 dark:text-slate-400';
        const HILITE = ' ring-2 ring-rose-400 dark:ring-rose-400';

        // Разряд под курсором: { row: 'x' | 'res', zone, idx }.
        let hover = null;

        function pow2(n) { return Math.pow(2, n); }
        function bitAt(v, i) { return Math.floor(v / pow2(i)) % 2; }
        // Значение → биты: у отрицательного числа это дополнительный код
        // нужной ширины, поэтому одна формула годится для обоих случаев.
        function bitsOf(v, width) { return v < 0 ? v + pow2(width) : v; }
        function readVal(bits) { return signed && (bits & half) ? bits - total : bits; }
        function num(n) { return String(n).replace('-', '−'); }

        // Всё состояние результата считается в одном месте: остальной код
        // только рисует то, что вернула эта функция.
        function compute() {
            const xVal = readVal(raw);
            if (op === '<<') {
                const fullVal = xVal * pow2(k);              // без ограничения ширины
                const fullBits = bitsOf(fullVal, bitsCount + k);
                const cut = fullBits % total;                // остались младшие n разрядов
                return {
                    xVal: xVal,
                    fullVal: fullVal,
                    resVal: python ? fullVal : readVal(cut),
                    bodyBits: python ? fullBits % pow2(bitsCount + k) : cut,
                    overBits: Math.floor(fullBits / total),  // зона за левым краем
                    lostVal: null,
                };
            }
            // >> одинаков в обоих режимах: разница только в том, что въезжает
            // слева — ноль или копия знакового бита.
            const resVal = Math.floor(xVal / pow2(k));
            return {
                xVal: xVal,
                fullVal: resVal,
                resVal: resVal,
                bodyBits: bitsOf(resVal, bitsCount),
                overBits: 0,
                lostVal: raw % pow2(k),                      // выпавшие младшие разряды
            };
        }

        // Колонки таблицы: лента разрядов плюс зона за краем — слева у <<
        // (разряды n…n+k−1) и справа у >> (выпавшие биты).
        function makeCols() {
            const cols = [];
            if (op === '<<') {
                for (let i = k - 1; i >= 0; i--) cols.push({ zone: 'over', idx: bitsCount + i });
            }
            for (let i = bitsCount - 1; i >= 0; i--) cols.push({ zone: 'tape', idx: i });
            if (op === '>>') {
                for (let i = k - 1; i >= 0; i--) cols.push({ zone: 'out', idx: i });
            }
            return cols;
        }

        // Откуда приехал бит разряда col строки результата: либо разряд
        // исходного числа, либо «въехал новый».
        function sourceOf(col) {
            if (op === '<<') {
                const src = col.idx - k;
                return src >= 0 ? src : null;
            }
            if (col.zone === 'out') return col.idx;          // выпал, разряд не менял
            const src = col.idx + k;
            return src <= bitsCount - 1 ? src : null;
        }

        // Куда уехал бит разряда idx исходного числа.
        function targetOf(idx) {
            if (op === '<<') {
                const dst = idx + k;
                return { zone: dst >= bitsCount ? 'over' : 'tape', idx: dst };
            }
            const dst = idx - k;
            return dst >= 0 ? { zone: 'tape', idx: dst } : { zone: 'out', idx: idx };
        }

        // ── переключатель операции ───────────────────────────────
        const opRow = document.createElement('div');
        opRow.className = 'flex flex-wrap gap-2 justify-center items-center';
        const opButtons = [];
        [
            { key: '<<', name: 'влево' },
            { key: '>>', name: 'вправо' },
        ].forEach(function (o) {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.innerHTML = '<span class="font-mono">' + escapeHtml(o.key) + '</span> ' + escapeHtml(o.name);
            btn.addEventListener('click', function () {
                op = o.key;
                hover = null;
                render(true);
            });
            opButtons.push({ btn: btn, key: o.key });
            opRow.appendChild(btn);
        });

        // ── величина сдвига ──────────────────────────────────────
        const kRow = document.createElement('div');
        kRow.className = 'mt-3 flex flex-wrap gap-2 justify-center items-center';
        const kLabel = document.createElement('span');
        kLabel.className = 'text-sm text-gray-500 dark:text-slate-400';
        kLabel.textContent = 'на сколько разрядов:';
        kRow.appendChild(kLabel);
        const kButtons = [];
        for (let i = 1; i <= maxK; i++) {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.textContent = String(i);
            (function (value) {
                btn.addEventListener('click', function () {
                    k = value;
                    hover = null;
                    render(true);
                });
            })(i);
            kButtons.push({ btn: btn, k: i });
            kRow.appendChild(btn);
        }

        // ── строки в столбик ─────────────────────────────────────
        const scroller = document.createElement('div');
        scroller.className = 'mt-4 overflow-x-auto';
        const table = document.createElement('div');
        table.className = 'inline-block min-w-full';
        scroller.appendChild(table);

        function makeRow() {
            const row = document.createElement('div');
            row.className = 'flex items-center gap-1 justify-center';
            const label = document.createElement('div');
            label.className = 'w-20 shrink-0 pr-2 text-right font-mono text-sm text-gray-500 dark:text-slate-400';
            const value = document.createElement('div');
            value.className = 'w-24 shrink-0 pl-2 font-mono text-sm text-gray-700 dark:text-slate-200';
            row.appendChild(label);
            row.appendChild(value);
            table.appendChild(row);
            return { row: row, label: label, value: value };
        }

        // Таблица пересобирается только когда меняется набор колонок
        // (операция или величина сдвига). При наведении и правке битов
        // достаточно перекрасить готовые ячейки: пересборка под курсором
        // ломала бы hover — mouseleave не пришёл бы с удалённого элемента.
        let cols = [];
        let rowX = null;
        let rowR = null;
        const cellsX = {};
        const cellsR = {};

        function key(zone, idx) { return zone + ':' + idx; }

        function buildTable() {
            table.innerHTML = '';
            Object.keys(cellsX).forEach(function (n) { delete cellsX[n]; });
            Object.keys(cellsR).forEach(function (n) { delete cellsR[n]; });
            cols = makeCols();

            const headRow = makeRow();
            headRow.label.textContent = 'разряд';
            cols.forEach(function (col) {
                const idx = document.createElement('div');
                idx.className = 'w-8 shrink-0 text-center text-[10px] text-gray-400 dark:text-slate-500';
                idx.textContent = col.zone === 'out' ? '·' : String(col.idx);
                headRow.row.insertBefore(idx, headRow.value);
            });

            rowX = makeRow();
            rowX.label.textContent = 'x =';
            cols.forEach(function (col) {
                // Зона за краем принадлежит только строке результата: у
                // исходного числа этих разрядов ещё нет.
                if (col.zone !== 'tape') {
                    const spacer = document.createElement('div');
                    spacer.className = 'w-8 h-10 shrink-0';
                    rowX.row.insertBefore(spacer, rowX.value);
                    return;
                }
                const cell = document.createElement('button');
                cell.type = 'button';
                cell.dataset.bit = String(col.idx);
                (function (idx) {
                    cell.addEventListener('click', function () {
                        raw ^= (1 << idx);
                        raw &= mask;
                        render();
                    });
                    cell.addEventListener('mouseenter', function () {
                        hover = { row: 'x', zone: 'tape', idx: idx };
                        paint();
                    });
                })(col.idx);
                cell.addEventListener('mouseleave', function () { hover = null; paint(); });
                rowX.row.insertBefore(cell, rowX.value);
                cellsX[key(col.zone, col.idx)] = cell;
            });

            const divider = document.createElement('div');
            divider.className = 'my-2 border-t border-gray-200 dark:border-slate-600';
            table.appendChild(divider);

            rowR = makeRow();
            cols.forEach(function (col) {
                const cell = document.createElement('div');
                cell.dataset.bit = String(col.idx);
                (function (c) {
                    cell.addEventListener('mouseenter', function () {
                        hover = { row: 'res', zone: c.zone, idx: c.idx };
                        paint();
                    });
                })(col);
                cell.addEventListener('mouseleave', function () { hover = null; paint(); });
                rowR.row.insertBefore(cell, rowR.value);
                cellsR[key(col.zone, col.idx)] = cell;
            });
        }

        // ── подсказка, управление, пояснение ─────────────────────
        const hintLine = document.createElement('div');
        hintLine.className = 'mt-3 text-center text-sm text-gray-500 dark:text-slate-400 min-h-[1.5rem]';

        const controls = document.createElement('div');
        controls.className = 'mt-4 flex flex-wrap gap-3 justify-center items-center';

        const input = document.createElement('input');
        input.type = 'number';
        input.className = inputClass;
        input.setAttribute('aria-label', 'Значение x');
        input.addEventListener('input', function () {
            raw = (parseInt(input.value, 10) || 0) & mask;
            render(false, true);
        });
        const inputLabel = document.createElement('label');
        inputLabel.className = 'flex items-center gap-2 text-sm text-gray-500 dark:text-slate-400';
        inputLabel.innerHTML = '<span class="font-mono">x</span>';
        inputLabel.appendChild(input);
        controls.appendChild(inputLabel);

        const signedBtn = document.createElement('button');
        signedBtn.type = 'button';
        signedBtn.textContent = 'знаковое число';
        signedBtn.title = 'читать биты как дополнительный код (урок 5.2)';
        signedBtn.addEventListener('click', function () {
            signed = !signed;
            render();
        });
        controls.appendChild(signedBtn);

        const pythonBtn = document.createElement('button');
        pythonBtn.type = 'button';
        pythonBtn.title = 'у int в Python нет фиксированной ширины: при сдвиге влево число просто становится длиннее';
        pythonBtn.addEventListener('click', function () {
            python = !python;
            hover = null;
            render(true);
        });
        controls.appendChild(pythonBtn);

        const presets = document.createElement('div');
        presets.className = 'mt-3 flex flex-wrap gap-2 justify-center items-center';

        function presetBtn(label, state, title) {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = btnChip;
            btn.textContent = label;
            if (title) btn.title = title;
            btn.addEventListener('click', function () {
                op = state.op;
                k = Math.min(state.k, maxK);
                signed = state.signed === true;
                python = state.python === true;
                raw = state.value & mask;
                hover = null;
                render(true);
            });
            presets.appendChild(btn);
        }

        presetBtn('3 << 2', { op: '<<', k: 2, value: 3, python: true }, 'пример из урока: 3 · 4 = 12');
        presetBtn('40 >> 3', { op: '>>', k: 3, value: 40 }, '40 // 8 = 5, выпавшие биты нулевые');
        presetBtn('41 >> 1', { op: '>>', k: 1, value: 41 }, 'выпал единичный бит — это остаток');
        presetBtn('−7 >> 1', { op: '>>', k: 1, value: -7, signed: true }, 'арифметический сдвиг: знак сохраняется');
        presetBtn('200 << 1 в 8 битах', { op: '<<', k: 1, value: 200, python: false }, 'переполнение: старший бит уехал за край');

        const noteLine = document.createElement('div');
        noteLine.className = 'mt-4 text-center text-sm text-gray-500 dark:text-slate-400';

        body.appendChild(opRow);
        body.appendChild(kRow);
        body.appendChild(scroller);
        body.appendChild(hintLine);
        body.appendChild(controls);
        body.appendChild(presets);
        body.appendChild(noteLine);

        function paintCell(cell, on, style, focused) {
            let cls = CELL_BASE + ' ' + style;
            if (focused) cls += HILITE;
            cell.className = cls;
            cell.textContent = on ? '1' : '0';
        }

        function paint(fromInput) {
            const s = compute();

            // Что подсвечено: разряд под курсором и его пара в другой строке.
            let focusX = null;
            let focusR = null;
            if (hover) {
                if (hover.row === 'x') {
                    focusX = hover.idx;
                    focusR = targetOf(hover.idx);
                } else {
                    focusR = { zone: hover.zone, idx: hover.idx };
                    focusX = sourceOf(focusR);
                }
            }

            cols.forEach(function (col) {
                const cellX = cellsX[key(col.zone, col.idx)];
                if (cellX) {
                    paintCell(cellX, bitAt(raw, col.idx), bitAt(raw, col.idx) ? CELL_ON : CELL_OFF,
                        focusX === col.idx);
                }

                const cellR = cellsR[key(col.zone, col.idx)];
                const isFocused = focusR !== null && focusR.zone === col.zone && focusR.idx === col.idx;
                if (col.zone === 'over') {
                    const on = bitAt(s.overBits, col.idx - bitsCount);
                    // В режиме Python эти разряды остаются частью числа,
                    // в режиме фиксированной ширины — потеряны.
                    paintCell(cellR, on, python ? (on ? KEPT_ON : KEPT_OFF) : LOST, isFocused);
                } else if (col.zone === 'out') {
                    paintCell(cellR, bitAt(s.lostVal, col.idx), LOST, isFocused);
                } else {
                    const on = bitAt(s.bodyBits, col.idx);
                    // Разряд освободился, если бита-источника у него нет.
                    const isNew = sourceOf(col) === null;
                    paintCell(cellR, on, isNew ? (on ? NEW_ON : NEW_OFF) : (on ? RES_ON : RES_OFF), isFocused);
                }
            });

            rowX.value.textContent = '= ' + num(s.xVal);
            rowR.label.innerHTML = '<b class="text-emerald-600 dark:text-emerald-400">x ' +
                escapeHtml(op) + ' ' + k + '</b> =';
            rowR.value.innerHTML = '= <b class="text-gray-900 dark:text-white">' + num(s.resVal) + '</b>';

            opButtons.forEach(function (item) {
                item.btn.className = item.key === op ? btnActive : btnChip;
            });
            kButtons.forEach(function (item) {
                item.btn.className = item.k === k ? btnActive : btnChip;
            });
            signedBtn.className = signed ? btnActive : btnChip;
            pythonBtn.className = python ? btnActive : btnChip;
            pythonBtn.textContent = python ? 'Python: int без границ' : 'ячейка ' + bitsCount + ' бит';

            if (!fromInput) {
                input.value = String(s.xVal);
                input.min = String(signed ? -half : 0);
                input.max = String(signed ? half - 1 : mask);
            }

            paintHint(s, focusX, focusR);
            paintNote(s);
        }

        function paintHint(s, focusX, focusR) {
            if (!hover) {
                hintLine.textContent = 'Наведите на любой разряд — покажу, откуда в нём взялся бит.';
                return;
            }
            if (focusR && focusR.zone === 'out') {
                hintLine.innerHTML = 'бит разряда ' + focusR.idx + ' уехал за правый край: ' +
                    'он потерян, и это ровно остаток от деления.';
                return;
            }
            if (focusR && focusR.zone === 'over') {
                hintLine.innerHTML = 'бит разряда ' + num(focusX) + ' переехал в разряд ' + focusR.idx +
                    ' — за границу ленты. ' + (python
                        ? 'В Python он остаётся: число просто стало длиннее.'
                        : 'В ячейке шириной ' + bitsCount + ' бит такого разряда нет — бит потерян.');
                return;
            }
            if (focusX === null) {
                const fill = op === '<<'
                    ? 'ноль: младшие разряды освободились'
                    : (signed && s.xVal < 0
                        ? 'копия знакового бита — единица, поэтому число остаётся отрицательным'
                        : 'ноль: свободные старшие разряды заполняются нулями');
                hintLine.innerHTML = 'в разряд ' + focusR.idx + ' въехал новый бит — ' + fill + '.';
                return;
            }
            hintLine.innerHTML = 'бит из разряда <b>' + focusX + '</b> переехал в разряд <b>' +
                focusR.idx + '</b>: его вес ' + (op === '<<' ? 'вырос' : 'упал') + ' в 2<sup>' + k +
                '</sup> раз.';
        }

        function paintNote(s) {
            const p = '2<sup>' + k + '</sup>';
            if (op === '<<') {
                if (python) {
                    noteLine.innerHTML = '<span class="font-mono">x << ' + k + '</span> = ' +
                        num(s.xVal) + ' · ' + p + ' = <b>' + num(s.resVal) + '</b>. ' +
                        (s.overBits !== 0
                            ? 'Разряды выше ' + (bitsCount - 1) + '-го никуда не делись: у типа ' +
                              '<span class="font-mono">int</span> в Python нет фиксированной ширины.'
                            : 'Пока всё умещается в ' + bitsCount + ' разрядов.');
                } else if (s.overBits !== 0) {
                    noteLine.innerHTML = 'В ячейке шириной ' + bitsCount + ' бит результат — <b>' +
                        num(s.resVal) + '</b>, а не ' + num(s.fullVal) + ': старшие разряды уехали ' +
                        'за край и потеряны. Так ведёт себя число в C или Java — и так же работает ' +
                        '<span class="font-mono">(x << ' + k + ') & 0x' +
                        mask.toString(16).toUpperCase() + '</span> в Python.';
                } else {
                    noteLine.innerHTML = 'За край уехали только нули, поэтому ничего не потеряно: ' +
                        'результат ровно ' + num(s.xVal) + ' · ' + p + ' = <b>' + num(s.resVal) + '</b>.';
                }
                return;
            }
            const tail = (signed && s.xVal < 0)
                ? ' Слева въехали копии знакового бита, поэтому число осталось отрицательным, ' +
                  'а округление пошло вниз — как у <span class="font-mono">//</span>.'
                : '';
            noteLine.innerHTML = '<span class="font-mono">x >> ' + k + '</span> = ' + num(s.xVal) +
                ' // ' + p + ' = <b>' + num(s.resVal) + '</b>. Проверка: ' + num(s.resVal) + ' · ' +
                p + ' + ' + s.lostVal + ' = ' + num(s.xVal) + ' — выпавшие младшие биты и есть ' +
                'остаток от деления.' + tail;
        }

        // structural: пересобрать колонки; fromInput: не трогать поле ввода,
        // чтобы не сбивать курсор.
        function render(structural, fromInput) {
            if (structural || cols.length === 0) buildTable();
            paint(fromInput);
        }

        render(true);
    });

    // ─────────────────────────────────────────────────────────────
    // Виджет: bits-grouper — перевод двоичного числа в восьмеричную/
    // шестнадцатеричную запись группировкой битов (по 3 или по 4).
    // Биты кликабельны (как в bits-viewer), переключатель меняет основание;
    // группы битов подсвечиваются цветом, под ними — цифра-результат той же
    // подсветки, внизу — итоговое число в выбранной системе и в десятичной.
    // Конфиг: { "value": 214, "bits": 8, "radix": 16 }. radix: 8 или 16.
    // ─────────────────────────────────────────────────────────────
    register('bits-grouper', function (el, config) {
        const bitsCount = Math.min(Math.max(parseInt(config.bits, 10) || 8, 3), 32);
        let value = (parseInt(config.value, 10) || 0) & ((bitsCount < 32 ? (1 << bitsCount) : 0x100000000) - 1);
        let radix = parseInt(config.radix, 10) === 8 ? 8 : 16;

        const GROUP_COLORS = [
            { box: 'bg-amber-100 border-amber-300 dark:bg-amber-900/30 dark:border-amber-700', text: 'text-amber-700 dark:text-amber-300' },
            { box: 'bg-sky-100 border-sky-300 dark:bg-sky-900/30 dark:border-sky-700', text: 'text-sky-700 dark:text-sky-300' },
            { box: 'bg-emerald-100 border-emerald-300 dark:bg-emerald-900/30 dark:border-emerald-700', text: 'text-emerald-700 dark:text-emerald-300' },
        ];

        // Размеры групп битов слева направо (от старших разрядов к младшим).
        // Если bitsCount не делится на groupSize нацело, "лишние" биты уходят
        // в крайнюю левую (старшую) группу — она получается короче остальных.
        function groupSizes(groupSize) {
            const sizes = [];
            let remaining = bitsCount;
            const rem = remaining % groupSize;
            if (rem !== 0) {
                sizes.push(rem);
                remaining -= rem;
            }
            while (remaining > 0) {
                sizes.push(groupSize);
                remaining -= groupSize;
            }
            return sizes;
        }

        const body = widgetFrame(el, el.dataset.title);

        const toggleRow = document.createElement('div');
        toggleRow.className = 'flex flex-wrap gap-2 justify-center mb-4';
        const toggleBtns = [8, 16].map(function (r) {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.textContent = r === 8 ? 'Восьмеричная (по 3 бита)' : 'Шестнадцатеричная (по 4 бита)';
            btn.dataset.radix = String(r);
            btn.addEventListener('click', function () {
                radix = r;
                render();
            });
            toggleRow.appendChild(btn);
            return btn;
        });

        const groupsRow = document.createElement('div');
        groupsRow.className = 'flex flex-wrap gap-2 justify-center';

        const digitsRow = document.createElement('div');
        digitsRow.className = 'flex flex-wrap gap-2 justify-center mt-2';

        const resultLine = document.createElement('div');
        resultLine.className = 'mt-4 text-center text-base text-gray-700 dark:text-slate-200 font-mono break-words';

        body.appendChild(toggleRow);
        body.appendChild(groupsRow);
        body.appendChild(digitsRow);
        body.appendChild(resultLine);

        function render() {
            toggleBtns.forEach(function (btn) {
                const active = parseInt(btn.dataset.radix, 10) === radix;
                btn.className = 'px-3 py-1.5 rounded-full text-sm border transition-colors ' +
                    (active
                        ? 'bg-brand-600 text-white border-brand-600 dark:bg-cyan-500 dark:border-cyan-500'
                        : 'bg-gray-50 text-gray-500 border-gray-200 dark:bg-slate-700 dark:border-slate-600');
            });

            const groupSize = radix === 8 ? 3 : 4;
            const sizes = groupSizes(groupSize);

            groupsRow.innerHTML = '';
            digitsRow.innerHTML = '';

            let bitCursor = bitsCount - 1;
            const digits = [];

            sizes.forEach(function (size, groupIndex) {
                const color = GROUP_COLORS[groupIndex % GROUP_COLORS.length];

                const groupBox = document.createElement('div');
                groupBox.className = 'flex gap-0.5 p-1 rounded-lg border ' + color.box;

                let groupValue = 0;
                for (let k = 0; k < size; k++) {
                    const i = bitCursor - k;
                    const on = (value >>> i) & 1;
                    groupValue = (groupValue << 1) | on;

                    const cell = document.createElement('button');
                    cell.type = 'button';
                    cell.className = 'w-8 h-10 rounded font-mono text-base flex items-center justify-center border transition-colors ' +
                        (on
                            ? 'bg-brand-600 text-white border-brand-600 dark:bg-cyan-500 dark:border-cyan-500'
                            : 'bg-white text-gray-400 border-gray-200 dark:bg-slate-800 dark:border-slate-600');
                    cell.textContent = on ? '1' : '0';
                    cell.dataset.bit = String(i);
                    cell.addEventListener('click', function () {
                        value ^= (1 << i);
                        if (value < 0) value = value >>> 0;
                        render();
                    });
                    groupBox.appendChild(cell);
                }
                bitCursor -= size;
                groupsRow.appendChild(groupBox);

                const digitChar = groupValue.toString(radix).toUpperCase();
                digits.push(digitChar);

                const chip = document.createElement('div');
                chip.className = 'text-center font-mono text-lg font-bold rounded-md py-1 px-2 border ' + color.box + ' ' + color.text;
                digitsRow.appendChild(chip).textContent = digitChar;
            });

            const masked = bitsCount === 32 ? (value >>> 0) : (value & ((1 << bitsCount) - 1));
            const radixLabel = radix === 8 ? 'восьмеричное' : 'шестнадцатеричное';
            resultLine.innerHTML = digits.join('') + '<sub>' + radix + '</sub> (' + radixLabel + ') = ' +
                '<b class="text-gray-900 dark:text-white">' + masked + '</b><sub>10</sub>';
        }

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
    // Виджет: radix-converter — перевод числа из произвольной системы
    // счисления (основание 2–36, цифры 0–9 и A–Z) в десятичную. Число
    // фиксировано на 3 разряда; каждый разряд меняется кнопками ▲/▼
    // (по модулю текущего основания), основание — отдельным полем ввода.
    // Под числом — развёрнутая форма: разложение по степеням основания
    // и сумма, пересчитываются на лету.
    // Конфиг: { "base": 5, "digits": [d0, d1, d2] } — digits[0] младший разряд.
    // ─────────────────────────────────────────────────────────────
    register('radix-converter', function (el, config) {
        const DIGITS_COUNT = 3;

        function clamp(v, min, max) {
            return Math.max(min, Math.min(max, v));
        }
        function digitChar(v) {
            return v < 10 ? String(v) : String.fromCharCode(55 + v); // 10 → 'A', 35 → 'Z'
        }

        let base = clamp(parseInt(config.base, 10) || 10, 2, 36);
        let digits = Array.isArray(config.digits) && config.digits.length === DIGITS_COUNT
            ? config.digits.map(function (d) { return clamp(parseInt(d, 10) || 0, 0, base - 1); })
            : [0, 0, 1];

        const body = widgetFrame(el, el.dataset.title);

        const baseRow = document.createElement('div');
        baseRow.className = 'flex items-center justify-center gap-2 mb-5';
        const baseLabel = document.createElement('label');
        baseLabel.textContent = 'Основание системы счисления (2–36):';
        baseLabel.className = 'text-sm text-gray-600 dark:text-slate-300';
        const baseInput = document.createElement('input');
        baseInput.type = 'number';
        baseInput.min = '2';
        baseInput.max = '36';
        baseInput.value = String(base);
        baseInput.className = 'w-16 text-center rounded-md border px-2 py-1 font-mono text-base border-gray-200 bg-white text-gray-900 dark:border-slate-600 dark:bg-slate-800 dark:text-white';
        baseInput.addEventListener('change', function () {
            base = clamp(parseInt(baseInput.value, 10) || 10, 2, 36);
            baseInput.value = String(base);
            digits = digits.map(function (d) { return clamp(d, 0, base - 1); });
            render();
        });
        baseRow.appendChild(baseLabel);
        baseRow.appendChild(baseInput);

        const digitsRow = document.createElement('div');
        digitsRow.className = 'flex gap-3 justify-center';

        const btnClass = 'w-9 h-7 rounded-md border text-sm flex items-center justify-center transition-colors ' +
            'bg-gray-50 text-gray-500 border-gray-200 hover:bg-gray-100 dark:bg-slate-700 dark:border-slate-600 dark:text-slate-300';

        const cells = [];
        for (let position = DIGITS_COUNT - 1; position >= 0; position--) {
            const col = document.createElement('div');
            col.className = 'flex flex-col items-center gap-1';

            const up = document.createElement('button');
            up.type = 'button';
            up.textContent = '▲';
            up.className = btnClass;
            up.setAttribute('aria-label', 'Увеличить цифру разряда ' + position);

            const val = document.createElement('div');
            val.className = 'w-9 h-11 rounded-md font-mono text-lg flex items-center justify-center border ' +
                'bg-brand-600 text-white border-brand-600 dark:bg-cyan-500 dark:border-cyan-500';

            const down = document.createElement('button');
            down.type = 'button';
            down.textContent = '▼';
            down.className = btnClass;
            down.setAttribute('aria-label', 'Уменьшить цифру разряда ' + position);

            const idx = document.createElement('span');
            idx.className = 'text-[10px] text-gray-400';
            idx.textContent = 'разряд ' + position;

            up.addEventListener('click', function () {
                digits[position] = digits[position] + 1 > base - 1 ? 0 : digits[position] + 1;
                render();
            });
            down.addEventListener('click', function () {
                digits[position] = digits[position] - 1 < 0 ? base - 1 : digits[position] - 1;
                render();
            });

            col.appendChild(up);
            col.appendChild(val);
            col.appendChild(down);
            col.appendChild(idx);
            digitsRow.appendChild(col);
            cells.push({ position: position, val: val });
        }

        const formula = document.createElement('div');
        formula.className = 'mt-5 text-center text-base text-gray-700 dark:text-slate-200 font-mono break-words';

        const resultLine = document.createElement('div');
        resultLine.className = 'mt-2 text-center text-lg font-mono';

        function render() {
            cells.forEach(function (c) { c.val.textContent = digitChar(digits[c.position]); });

            let sum = 0;
            const parts = [];
            for (let position = DIGITS_COUNT - 1; position >= 0; position--) {
                const d = digits[position];
                const weight = Math.pow(base, position);
                sum += d * weight;
                parts.push(digitChar(d) + '·' + base + '<sup>' + position + '</sup>');
            }
            formula.innerHTML = parts.join(' + ');
            resultLine.innerHTML = '= <b class="text-gray-900 dark:text-white">' + sum + '</b><sub>10</sub>';
        }

        body.appendChild(baseRow);
        body.appendChild(digitsRow);
        body.appendChild(formula);
        body.appendChild(resultLine);
        render();
    });

    // ─────────────────────────────────────────────────────────────
    // Виджет: division-ladder — перевод десятичного числа в любую систему
    // счисления делением уголком («лесенкой»). Шаги раскрываются по кнопке
    // (или все сразу): каждый шаг — деление текущего числа на основание с
    // остатком, остаток подсвечивается цветом. Когда частное становится 0,
    // под лесенкой собирается ответ — остатки в порядке чтения снизу вверх.
    // Конфиг: { "value": 97, "base": 5 }. value: 1–9999.
    // ─────────────────────────────────────────────────────────────
    const LADDER_REMAINDER_COLOR =
        'bg-orange-100 border-orange-300 text-orange-700 dark:bg-orange-900/30 dark:border-orange-700 dark:text-orange-300';

    register('division-ladder', function (el, config) {
        function clamp(v, min, max) { return Math.max(min, Math.min(max, v)); }
        function digitChar(v) { return v < 10 ? String(v) : String.fromCharCode(55 + v); }

        let value = clamp(parseInt(config.value, 10) || 97, 1, 9999);
        let base = clamp(parseInt(config.base, 10) || 5, 2, 36);
        let steps = [];
        let done = false;

        const body = widgetFrame(el, el.dataset.title || 'Деление уголком');

        const btnPrimary = 'px-3 py-1.5 rounded-full text-sm border transition-colors bg-brand-600 text-white border-brand-600 hover:bg-brand-700 dark:bg-cyan-500 dark:border-cyan-500 dark:hover:bg-cyan-400';
        const btnSecondary = 'px-3 py-1.5 rounded-full text-sm border transition-colors bg-gray-50 text-gray-500 border-gray-200 hover:bg-gray-100 dark:bg-slate-700 dark:border-slate-600 dark:text-slate-300';
        const inputClass = 'text-center rounded-md border px-2 py-1 font-mono text-base border-gray-200 bg-white text-gray-900 dark:border-slate-600 dark:bg-slate-800 dark:text-white';

        function labeledInput(labelText, inputEl) {
            const col = document.createElement('div');
            col.className = 'flex flex-col items-center gap-1';
            const label = document.createElement('label');
            label.textContent = labelText;
            label.className = 'text-xs text-gray-500 dark:text-slate-400';
            col.appendChild(label);
            col.appendChild(inputEl);
            return col;
        }

        const valueInput = document.createElement('input');
        valueInput.type = 'number';
        valueInput.min = '1';
        valueInput.max = '9999';
        valueInput.value = String(value);
        valueInput.className = inputClass + ' w-24';

        const baseInput = document.createElement('input');
        baseInput.type = 'number';
        baseInput.min = '2';
        baseInput.max = '36';
        baseInput.value = String(base);
        baseInput.className = inputClass + ' w-16';

        const stepBtn = document.createElement('button');
        stepBtn.type = 'button';
        stepBtn.textContent = 'Следующий шаг';

        const allBtn = document.createElement('button');
        allBtn.type = 'button';
        allBtn.textContent = 'Показать всё';
        allBtn.className = btnSecondary;

        const resetBtn = document.createElement('button');
        resetBtn.type = 'button';
        resetBtn.textContent = 'Сбросить';
        resetBtn.className = btnSecondary;

        const controls = document.createElement('div');
        controls.className = 'flex flex-wrap items-end gap-3 justify-center mb-5';
        controls.appendChild(labeledInput('Число (10)', valueInput));
        controls.appendChild(labeledInput('Основание', baseInput));
        controls.appendChild(stepBtn);
        controls.appendChild(allBtn);
        controls.appendChild(resetBtn);

        // Ступеньки лесенки сдвигаются вправо без ограничения (см. render) — на
        // узких экранах или при базе 2 (много шагов) итоговая ширина может
        // превысить ширину виджета. Внешняя рамка .textbook-widget обрезает
        // всё, что выходит за её границы (overflow: hidden), поэтому лесенку
        // оборачиваем в свой прокручиваемый контейнер — так самый дальний
        // остаток остаётся доступен прокруткой, а не обрезается незаметно.
        const ladderScroll = document.createElement('div');
        ladderScroll.className = 'overflow-x-auto pb-1';

        const ladder = document.createElement('div');
        ladder.className = 'flex flex-col gap-2 w-max relative';
        ladderScroll.appendChild(ladder);

        // Зелёная стрелка снизу вверх: соединяет остаток последнего шага
        // (снизу лесенки, читается первым) с остатком первого шага (сверху,
        // читается последним) — наглядно показывает направление чтения
        // остатков при сборке ответа.
        function drawLadderArrow(rowEls) {
            if (rowEls.length < 2) {
                ladder.style.paddingRight = '';
                return;
            }
            const svgNS = 'http://www.w3.org/2000/svg';
            const gap = 14;
            const reserve = gap + 14;

            // Резервируем место под стрелку паддингом самого контейнера —
            // иначе абсолютно спозиционированный svg «вылезает» за пределы
            // ladder и заставляет ladderScroll рисовать горизонтальный
            // скроллбар ради пары лишних пикселей.
            ladder.style.paddingRight = reserve + 'px';

            const ladderRect = ladder.getBoundingClientRect();
            const topRem = rowEls[0].rem.getBoundingClientRect();
            const bottomRem = rowEls[rowEls.length - 1].rem.getBoundingClientRect();

            // Точки крепления — правее ячеек с остатком (не поверх них), на
            // уровне их вертикальной середины. Так как ступеньки лесенки
            // сдвигаются вправо построчно, прямая линия между ними сама
            // получается диагональю, без ручного расчёта изгиба.
            const x1 = bottomRem.right - ladderRect.left + gap;
            const y1 = bottomRem.top - ladderRect.top + bottomRem.height / 2;
            const x2 = topRem.right - ladderRect.left + gap;
            const y2 = topRem.top - ladderRect.top + topRem.height / 2;

            const svg = document.createElementNS(svgNS, 'svg');
            svg.setAttribute('width', String(ladder.scrollWidth));
            svg.setAttribute('height', String(ladder.scrollHeight));
            svg.style.position = 'absolute';
            svg.style.left = '0';
            svg.style.top = '0';
            svg.style.overflow = 'visible';
            svg.style.pointerEvents = 'none';

            const defs = document.createElementNS(svgNS, 'defs');
            const marker = document.createElementNS(svgNS, 'marker');
            marker.setAttribute('id', 'ladder-arrowhead');
            marker.setAttribute('markerWidth', '8');
            marker.setAttribute('markerHeight', '8');
            marker.setAttribute('refX', '8');
            marker.setAttribute('refY', '4');
            marker.setAttribute('orient', 'auto');
            const head = document.createElementNS(svgNS, 'path');
            head.setAttribute('d', 'M0,0 L8,4 L0,8 Z');
            head.setAttribute('fill', '#10b981');
            marker.appendChild(head);
            defs.appendChild(marker);
            svg.appendChild(defs);

            const line = document.createElementNS(svgNS, 'line');
            line.setAttribute('x1', String(x1));
            line.setAttribute('y1', String(y1));
            line.setAttribute('x2', String(x2));
            line.setAttribute('y2', String(y2));
            line.setAttribute('stroke', '#10b981');
            line.setAttribute('stroke-width', '2.5');
            line.setAttribute('marker-end', 'url(#ladder-arrowhead)');
            svg.appendChild(line);

            ladder.appendChild(svg);
        }

        const resultLine = document.createElement('div');
        resultLine.className = 'mt-5 text-center text-lg font-mono min-h-[2.5rem]';

        body.appendChild(controls);
        body.appendChild(ladderScroll);
        body.appendChild(resultLine);

        function reset() {
            steps = [];
            done = false;
            render();
        }

        function stepForward() {
            if (done) return;
            const n = steps.length === 0 ? value : steps[steps.length - 1].quotient;
            const quotient = Math.floor(n / base);
            const remainder = n % base;
            steps.push({ dividend: n, quotient: quotient, remainder: remainder });
            if (quotient === 0) done = true;
            render();
        }

        function showAll() {
            while (!done) stepForward();
        }

        function render() {
            ladder.innerHTML = '';
            const rowEls = [];
            steps.forEach(function (step, i) {
                const row = document.createElement('div');
                row.className = 'flex items-center gap-3 font-mono text-base';
                row.style.marginLeft = (i * 20) + 'px';

                const eq = document.createElement('div');
                eq.className = 'flex items-center gap-2 px-3 py-1.5 rounded-lg border bg-gray-50 border-gray-200 text-gray-700 dark:bg-slate-800 dark:border-slate-600 dark:text-slate-200';
                eq.innerHTML = step.dividend + ' : ' + base + ' = <b>' + step.quotient + '</b>';

                const rem = document.createElement('div');
                rem.className = 'px-2 py-1 rounded-md border text-sm font-bold ' + LADDER_REMAINDER_COLOR;
                rem.textContent = 'ост. ' + digitChar(step.remainder);

                row.appendChild(eq);
                row.appendChild(rem);
                ladder.appendChild(row);
                rowEls.push({ row: row, rem: rem });
            });

            if (done) {
                drawLadderArrow(rowEls);
            } else {
                ladder.style.paddingRight = '';
            }

            if (steps.length === 0) {
                resultLine.innerHTML = '<span class="text-gray-400 text-sm font-sans">Нажмите «Следующий шаг», чтобы начать деление.</span>';
            } else if (!done) {
                resultLine.innerHTML = '<span class="text-gray-400 text-sm font-sans">Частное ещё не равно 0 — продолжайте деление.</span>';
            } else {
                const chips = steps.map(function (s) {
                    return '<span class="inline-flex items-center justify-center w-7 h-7 rounded-md border text-sm font-bold ' + LADDER_REMAINDER_COLOR + '">' + digitChar(s.remainder) + '</span>';
                });
                const answer = steps.map(function (s) { return digitChar(s.remainder); }).reverse().join('');
                resultLine.innerHTML =
                    '<div class="flex flex-col items-center gap-2">' +
                        '<div class="flex items-center gap-2 text-sm font-sans text-gray-400">' +
                            '<span>читаем остатки снизу вверх:</span>' +
                            '<span class="flex gap-1">' + chips.slice().reverse().join('') + '</span>' +
                        '</div>' +
                        '<div>' + value + '<sub>10</sub> = <b class="text-gray-900 dark:text-white">' + answer + '</b><sub>' + base + '</sub></div>' +
                    '</div>';
            }

            stepBtn.disabled = done;
            stepBtn.className = btnPrimary + (done ? ' opacity-50 cursor-not-allowed' : '');
            allBtn.disabled = done;
        }

        valueInput.addEventListener('change', function () {
            value = clamp(parseInt(valueInput.value, 10) || 1, 1, 9999);
            valueInput.value = String(value);
            reset();
        });
        baseInput.addEventListener('change', function () {
            base = clamp(parseInt(baseInput.value, 10) || 10, 2, 36);
            baseInput.value = String(base);
            reset();
        });
        stepBtn.addEventListener('click', stepForward);
        allBtn.addEventListener('click', showAll);
        resetBtn.addEventListener('click', reset);

        render();
    });

    // ─────────────────────────────────────────────────────────────
    // Виджет: encoding-strip — «кодовая лента»: текст записывают одной
    // кодовой таблицей, а читают другой. Главная мысль виджета: байты в
    // файле не меняются, меняется только таблица, по которой их читают, —
    // отсюда и берутся «кракозябры».
    //
    // Сверху поле с текстом и два ряда переключателей («Записали в» /
    // «Читаем как»), ниже — лента байтов: в ячейке шестнадцатеричный код,
    // символ при текущем чтении и десятичный код. Байты нижней половины
    // (< 0x80) окрашены отдельно: там все таблицы совпадают, поэтому
    // латиница никогда не ломается. Клик по байту раскрывает панель — как
    // тот же самый байт читает каждая таблица.
    //
    // Верхние половины таблиц сняты с реальных кодеков Python (cp1251,
    // koi8-r, cp866, iso8859-5); \u0000 — позиция, за которой в таблице не
    // закреплён символ. Кодировка ascii своей верхней половины не имеет
    // вовсе: старшие байты в ней не читаются, а русские буквы не
    // записываются (вместо них, как и у настоящих кодировщиков, «?»).
    //
    // Конфиг: { "text": "Привет", "written": "cp1251", "read": "koi8-r",
    //           "encodings": ["ascii", "cp1251", "koi8-r", "cp866"] }
    // ─────────────────────────────────────────────────────────────
    const ENC_HIGH = {
        'cp1251': 'ЂЃ‚ѓ„…†‡€‰Љ‹ЊЌЋЏђ‘’“”•–—\u0000™љ›њќћџ\u00A0ЎўЈ¤Ґ¦§Ё©Є«¬\u00AD®Ї°±Ііґµ¶·ё№є»јЅѕїАБВГДЕЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯабвгдежзийклмнопрстуфхцчшщъыьэюя',
        'koi8-r': '─│┌┐└┘├┤┬┴┼▀▄█▌▐░▒▓⌠■∙√≈≤≥\u00A0⌡°²·÷═║╒ё╓╔╕╖╗╘╙╚╛╜╝╞╟╠╡Ё╢╣╤╥╦╧╨╩╪╫╬©юабцдефгхийклмнопярстужвьызшэщчъЮАБЦДЕФГХИЙКЛМНОПЯРСТУЖВЬЫЗШЭЩЧЪ',
        'cp866': 'АБВГДЕЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯабвгдежзийклмноп░▒▓│┤╡╢╖╕╣║╗╝╜╛┐└┴┬├─┼╞╟╚╔╩╦╠═╬╧╨╤╥╙╘╒╓╫╪┘┌█▄▌▐▀рстуфхцчшщъыьэюяЁёЄєЇїЎў°∙·√№¤■\u00A0',
        'iso8859-5': '\u0080\u0081\u0082\u0083\u0084\u0085\u0086\u0087\u0088\u0089\u008A\u008B\u008C\u008D\u008E\u008F\u0090\u0091\u0092\u0093\u0094\u0095\u0096\u0097\u0098\u0099\u009A\u009B\u009C\u009D\u009E\u009F\u00A0ЁЂЃЄЅІЇЈЉЊЋЌ\u00ADЎЏАБВГДЕЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯабвгдежзийклмнопрстуфхцчшщъыьэюя№ёђѓєѕіїјљњћќ§ўџ',
    };

    const ENC_LABELS = {
        'ascii': 'ASCII (7 битов)',
        'cp1251': 'Windows-1251',
        'koi8-r': 'KOI8-R',
        'cp866': 'CP866 (DOS)',
        'iso8859-5': 'ISO 8859-5',
    };

    const ENC_ORDER = ['ascii', 'cp1251', 'koi8-r', 'cp866', 'iso8859-5'];

    // Символ по коду байта в заданной таблице; null — символа с таким кодом
    // в таблице нет. Нижняя половина одинакова у всех таблиц — это и есть
    // унаследованный от ASCII общий фундамент.
    function encDecodeByte(enc, b) {
        if (b < 0x80) return String.fromCharCode(b);
        const high = ENC_HIGH[enc];
        if (!high) return null;
        const ch = high.charAt(b - 0x80);
        return ch === '\u0000' ? null : ch;
    }

    const encReverseCache = {};

    // Обратное отображение «символ → код байта» для кодирования текста.
    function encReverse(enc) {
        if (encReverseCache[enc]) return encReverseCache[enc];
        const map = Object.create(null);
        for (let b = 0x20; b < 0x7F; b++) map[String.fromCharCode(b)] = b;
        const high = ENC_HIGH[enc];
        if (high) {
            for (let i = 0; i < high.length; i++) {
                const ch = high.charAt(i);
                if (ch !== '\u0000' && map[ch] === undefined) map[ch] = 0x80 + i;
            }
        }
        encReverseCache[enc] = map;
        return map;
    }

    // Как показать символ в ячейке: невидимые символы подменяем значком,
    // иначе ячейка выглядит пустой и читается как ошибка виджета.
    function encGlyph(ch) {
        if (ch === null) return { text: '—', dim: true, note: 'кода нет в таблице' };
        const code = ch.charCodeAt(0);
        if (ch === ' ' || code === 0xA0) return { text: '␣', dim: true, note: 'пробел' };
        if (code === 0xAD) return { text: '·', dim: true, note: 'мягкий перенос' };
        return { text: ch, dim: false, note: null };
    }

    register('encoding-strip', function (el, config) {
        const available = (Array.isArray(config.encodings) && config.encodings.length
            ? config.encodings
            : ['ascii', 'cp1251', 'koi8-r', 'cp866']
        ).filter(function (e) { return ENC_ORDER.indexOf(e) >= 0; });
        if (available.length < 2) available.push('cp1251', 'koi8-r');

        function pick(name, fallback) {
            return available.indexOf(name) >= 0 ? name : fallback;
        }
        let written = pick(config.written, available[0]);
        let read = pick(config.read, available[available.length - 1]);
        let text = typeof config.text === 'string' && config.text ? config.text : 'Привет';
        let selected = -1;

        const btnChip = 'px-2.5 py-1 rounded-full text-xs border transition-colors bg-gray-50 text-gray-500 border-gray-200 hover:bg-gray-100 dark:bg-slate-700 dark:border-slate-600 dark:text-slate-300';
        const btnActive = 'px-2.5 py-1 rounded-full text-xs border transition-colors bg-brand-600 text-white border-brand-600 dark:bg-cyan-500 dark:border-cyan-500';
        const inputClass = 'rounded-md border px-2 py-1 font-mono text-base border-gray-200 bg-white text-gray-900 dark:border-slate-600 dark:bg-slate-800 dark:text-white';

        const body = widgetFrame(el, el.dataset.title);

        // ── управление: текст + два ряда переключателей таблиц
        const textRow = document.createElement('div');
        textRow.className = 'flex flex-wrap items-center gap-2 justify-center mb-4';
        const textLabel = document.createElement('label');
        textLabel.className = 'text-xs text-gray-500 dark:text-slate-400';
        textLabel.textContent = 'Текст';
        const textInput = document.createElement('input');
        textInput.type = 'text';
        textInput.value = text;
        textInput.maxLength = 20;
        textInput.className = inputClass + ' w-56';
        textRow.appendChild(textLabel);
        textRow.appendChild(textInput);

        function toggleRow(labelText, getCurrent, setCurrent) {
            const row = document.createElement('div');
            row.className = 'flex flex-wrap items-center gap-2 justify-center mb-2';
            const label = document.createElement('span');
            label.className = 'text-xs text-gray-500 dark:text-slate-400 w-28 text-right';
            label.textContent = labelText;
            row.appendChild(label);
            const btns = available.map(function (enc) {
                const btn = document.createElement('button');
                btn.type = 'button';
                btn.textContent = ENC_LABELS[enc];
                btn.dataset.enc = enc;
                btn.addEventListener('click', function () {
                    setCurrent(enc);
                    render();
                });
                row.appendChild(btn);
                return btn;
            });
            row._refresh = function () {
                btns.forEach(function (btn) {
                    btn.className = btn.dataset.enc === getCurrent() ? btnActive : btnChip;
                });
            };
            return row;
        }

        const writtenRow = toggleRow('Записали в', function () { return written; },
            function (v) { written = v; selected = -1; });
        const readRow = toggleRow('Читаем как', function () { return read; },
            function (v) { read = v; });

        const swapBtn = document.createElement('button');
        swapBtn.type = 'button';
        swapBtn.textContent = 'Поменять таблицы местами';
        swapBtn.className = btnChip + ' mt-1';
        swapBtn.addEventListener('click', function () {
            const t = written;
            written = read;
            read = t;
            selected = -1;
            render();
        });
        const swapRow = document.createElement('div');
        swapRow.className = 'flex justify-center mb-4';
        swapRow.appendChild(swapBtn);

        // ── лента байтов (может не влезть по ширине — своя прокрутка,
        // т.к. рамка .textbook-widget обрезает выходящее за границы)
        const stripScroll = document.createElement('div');
        stripScroll.className = 'overflow-x-auto py-1';
        const strip = document.createElement('div');
        strip.className = 'flex gap-1 justify-center w-max mx-auto';
        stripScroll.appendChild(strip);

        const lines = document.createElement('div');
        lines.className = 'mt-4 space-y-1 text-center text-base';

        const note = document.createElement('div');
        note.className = 'mt-3 text-center text-sm text-gray-500 dark:text-slate-400';

        const detail = document.createElement('div');
        detail.className = 'mt-4 rounded-lg border border-gray-200 bg-gray-50 p-3 dark:border-slate-600 dark:bg-slate-800';

        body.appendChild(textRow);
        body.appendChild(writtenRow);
        body.appendChild(readRow);
        body.appendChild(swapRow);
        body.appendChild(stripScroll);
        body.appendChild(lines);
        body.appendChild(note);
        body.appendChild(detail);

        function encodeText(str, enc) {
            const map = encReverse(enc);
            const out = [];
            for (let i = 0; i < str.length; i++) {
                const ch = str.charAt(i);
                const b = map[ch];
                out.push(b === undefined
                    ? { byte: 0x3F, ok: false, src: ch }   // как errors='replace': знак «?»
                    : { byte: b, ok: true, src: ch });
            }
            return out;
        }

        function hex(b) {
            return '0x' + b.toString(16).toUpperCase().padStart(2, '0');
        }

        function bin(b) {
            const s = b.toString(2).padStart(8, '0');
            return s.slice(0, 4) + ' ' + s.slice(4);
        }

        function renderDetail(bytes) {
            detail.innerHTML = '';
            if (selected < 0 || selected >= bytes.length) {
                detail.innerHTML = '<p class="text-sm text-gray-500 dark:text-slate-400 text-center">' +
                    'Нажмите на любой байт ленты — покажу, как его читает каждая таблица.</p>';
                return;
            }
            const b = bytes[selected].byte;
            const head = document.createElement('div');
            head.className = 'text-center font-mono text-sm text-gray-700 dark:text-slate-200 mb-2';
            head.textContent = 'Байт ' + hex(b) + ' = ' + b + ' = ' + bin(b);
            detail.appendChild(head);

            const list = document.createElement('div');
            list.className = 'flex flex-wrap gap-2 justify-center';
            available.forEach(function (enc) {
                const g = encGlyph(encDecodeByte(enc, b));
                const chip = document.createElement('div');
                const active = enc === read;
                chip.className = 'px-2.5 py-1 rounded-md border text-sm ' + (active
                    ? 'bg-brand-600 text-white border-brand-600 dark:bg-cyan-500 dark:border-cyan-500'
                    : 'bg-white text-gray-600 border-gray-200 dark:bg-slate-700 dark:border-slate-600 dark:text-slate-300');
                chip.innerHTML = escapeHtml(ENC_LABELS[enc]) + ' → <b class="font-mono">' +
                    escapeHtml(g.text) + '</b>';
                if (g.note) chip.title = g.note;
                list.appendChild(chip);
            });
            detail.appendChild(list);

            if (b < 0x80) {
                const hint = document.createElement('p');
                hint.className = 'mt-2 text-center text-xs text-gray-500 dark:text-slate-400';
                hint.textContent = 'Код меньше 128 — это нижняя половина, унаследованная от ASCII. ' +
                    'Здесь все таблицы совпадают, поэтому такой байт нигде не ломается.';
                detail.appendChild(hint);
            }
        }

        function render() {
            writtenRow._refresh();
            readRow._refresh();

            const bytes = encodeText(text, written);

            strip.innerHTML = '';
            bytes.forEach(function (item, index) {
                const ch = encDecodeByte(read, item.byte);
                const g = encGlyph(ch);
                const cell = document.createElement('button');
                cell.type = 'button';
                let tone;
                if (!item.ok) {
                    tone = 'bg-red-100 border-red-300 text-red-700 dark:bg-red-900/30 dark:border-red-700 dark:text-red-300';
                } else if (item.byte < 0x80) {
                    tone = 'bg-gray-50 border-gray-200 text-gray-600 dark:bg-slate-700 dark:border-slate-600 dark:text-slate-300';
                } else {
                    tone = 'bg-amber-100 border-amber-300 text-amber-800 dark:bg-amber-900/30 dark:border-amber-700 dark:text-amber-200';
                }
                cell.className = 'w-14 py-1.5 rounded-md border flex flex-col items-center justify-center transition-colors ' +
                    tone + (index === selected ? ' ring-2 ring-brand-500 dark:ring-cyan-400' : '');
                cell.innerHTML =
                    '<span class="text-[10px] font-mono leading-none opacity-70">' + hex(item.byte) + '</span>' +
                    '<span class="text-xl font-mono leading-tight my-0.5' + (g.dim ? ' opacity-40' : '') + '">' +
                        escapeHtml(g.text) + '</span>' +
                    '<span class="text-[10px] font-mono leading-none opacity-70">' + item.byte + '</span>';
                cell.addEventListener('click', function () {
                    selected = (selected === index) ? -1 : index;
                    render();
                });
                strip.appendChild(cell);
            });

            const decoded = bytes.map(function (item) {
                return encGlyph(encDecodeByte(read, item.byte)).text;
            }).join('');
            const stored = bytes.map(function (item) {
                return item.ok ? item.src : '?';
            }).join('');

            lines.innerHTML =
                '<div class="text-gray-700 dark:text-slate-200">Записали в ' +
                    escapeHtml(ENC_LABELS[written]) + ': <b class="font-mono">' +
                    escapeHtml(stored) + '</b></div>' +
                '<div class="text-gray-700 dark:text-slate-200">Читаем как ' +
                    escapeHtml(ENC_LABELS[read]) + ': <b class="font-mono">' +
                    escapeHtml(decoded) + '</b></div>';

            const lost = bytes.filter(function (item) { return !item.ok; }).length;
            const allLow = bytes.every(function (item) { return item.byte < 0x80; });
            if (lost > 0) {
                note.textContent = 'В таблице ' + ENC_LABELS[written] + ' таких символов нет вовсе — ' +
                    'вместо них записан знак «?». Обратно из «?» исходную букву уже не достать.';
            } else if (written === read) {
                note.textContent = 'Записали и читаем по одной таблице — текст цел.';
            } else if (allLow) {
                note.textContent = 'Все байты меньше 128, а в этой половине таблицы совпадают — ' +
                    'вот почему латиница не ломается никогда.';
            } else {
                note.textContent = 'Байты в ленте не изменились — изменилась только таблица, ' +
                    'по которой их читают. Так и получаются «кракозябры».';
            }

            renderDetail(bytes);
        }

        textInput.addEventListener('input', function () {
            text = textInput.value;
            selected = -1;
            render();
        });

        render();
    });

    // ─────────────────────────────────────────────────────────────
    // Виджет: utf8-builder — как кодовая точка Unicode превращается в
    // байты UTF-8. Сверху лента символов текста: у каждого свой U+код и
    // свои 1–4 байта, цвет группы = длина записи. Клик по символу
    // раскрывает панель сборки: биты номера отдельной лентой, ниже
    // шаблон байтов, где служебные метки (0 / 110 / 1110 / 11110 у
    // ведущего байта, 10 у продолжений) показаны серым, а биты номера
    // разъезжаются по свободным местам. Наведение на бит подсвечивает,
    // из какого разряда номера он приехал.
    // Главная мысль виджета: биты номера не перемешиваются и не
    // меняются — они просто распределяются между метками.
    // Конфиг: { "text": "AЖ😀", "presets": ["A", "Ж"], "compare": true }.
    // compare (по умолчанию включён) добавляет строку сравнения объёма
    // текста в UTF-8 / UTF-16 / UTF-32.
    // ─────────────────────────────────────────────────────────────
    register('utf8-builder', function (el, config) {
        // Шаблоны UTF-8: сколько битов номера влезает и какие метки у байтов.
        // Из marks выводится всё остальное: длина, свободные места, границы.
        const TEMPLATES = [
            { len: 1, payload: 7, max: 0x7F, marks: ['0'] },
            { len: 2, payload: 11, max: 0x7FF, marks: ['110', '10'] },
            { len: 3, payload: 16, max: 0xFFFF, marks: ['1110', '10', '10'] },
            { len: 4, payload: 21, max: 0x10FFFF, marks: ['11110', '10', '10', '10'] }
        ];

        const TONE = {
            1: 'bg-gray-50 border-gray-200 text-gray-700 dark:bg-slate-700 dark:border-slate-600 dark:text-slate-200',
            2: 'bg-amber-50 border-amber-300 text-amber-900 dark:bg-amber-900/30 dark:border-amber-700 dark:text-amber-100',
            3: 'bg-emerald-50 border-emerald-300 text-emerald-900 dark:bg-emerald-900/30 dark:border-emerald-700 dark:text-emerald-100',
            4: 'bg-violet-50 border-violet-300 text-violet-900 dark:bg-violet-900/30 dark:border-violet-700 dark:text-violet-100'
        };
        const LEN_NOTE = {
            1: 'Код меньше 128 — сработал самый короткий шаблон 0xxxxxxx. ' +
               'Байт получился ровно такой же, как в ASCII шестьдесят лет назад: ' +
               'именно поэтому английский текст в UTF-8 не потолстел ни на байт.',
            2: 'Ведущий байт начинается с 110 — две единицы до первого нуля, ' +
               'значит символ занимает два байта. Так кодируется вся кириллица: ' +
               'вдвое дороже, чем в однобайтовой Windows-1251, — это цена ' +
               'единой таблицы.',
            3: 'Ведущий байт начинается с 1110 — три единицы, символ занимает ' +
               'три байта. Столько стоят иероглифы и большинство знаков ' +
               'основной плоскости за пределами латиницы и кириллицы.',
            4: 'Ведущий байт начинается с 11110 — четыре единицы, символ ' +
               'занимает четыре байта, максимум для UTF-8. Сюда попадают ' +
               'символы верхних плоскостей: эмодзи, редкие письменности.'
        };

        const CHIP = 'px-2.5 py-1 rounded-full text-xs border transition-colors bg-gray-50 text-gray-500 border-gray-200 hover:bg-gray-100 dark:bg-slate-700 dark:border-slate-600 dark:text-slate-300';
        const INPUT = 'rounded-md border px-2 py-1 font-mono text-base border-gray-200 bg-white text-gray-900 dark:border-slate-600 dark:bg-slate-800 dark:text-white';
        const BIT_ON = 'bg-brand-600 text-white border-brand-600 dark:bg-cyan-500 dark:border-cyan-500';
        const BIT_OFF = 'bg-gray-50 text-gray-400 border-gray-200 dark:bg-slate-700 dark:border-slate-600 dark:text-slate-400';
        const BIT_MARK = 'bg-gray-200 text-gray-500 border-gray-300 dark:bg-slate-600 dark:text-slate-400 dark:border-slate-500';
        const RING = ' ring-2 ring-amber-400 dark:ring-amber-300';

        const presets = (Array.isArray(config.presets) && config.presets.length
            ? config.presets
            : ['A', 'Ж', '€', '你', '\u{1F600}', 'Привет']
        ).slice(0, 8);
        let text = typeof config.text === 'string' && config.text
            ? config.text
            : 'AЖ\u{1F600}';
        const showCompare = config.compare !== false;
        let selected = 0;

        function plural(n, one, few, many) {
            const tail = Math.abs(n) % 100;
            if (tail >= 11 && tail <= 14) return many;
            const last = tail % 10;
            if (last === 1) return one;
            if (last >= 2 && last <= 4) return few;
            return many;
        }

        function template(cp) {
            for (let i = 0; i < TEMPLATES.length; i++) {
                if (cp <= TEMPLATES[i].max) return TEMPLATES[i];
            }
            return TEMPLATES[TEMPLATES.length - 1];
        }

        // Кодируем сами, а не через TextEncoder: нужны не только байты,
        // но и то, какой бит номера в какое место шаблона уехал.
        function encodeChar(cp) {
            const tpl = template(cp);
            const bits = cp.toString(2).padStart(tpl.payload, '0');
            const bytes = [];
            let pos = 0;
            tpl.marks.forEach(function (mark) {
                const room = 8 - mark.length;
                const chunk = bits.slice(pos, pos + room);
                bytes.push({ mark: mark, chunk: chunk, from: pos, value: parseInt(mark + chunk, 2) });
                pos += room;
            });
            return { cp: cp, tpl: tpl, bits: bits, bytes: bytes };
        }

        function hex(b) {
            return b.toString(16).toUpperCase().padStart(2, '0');
        }

        function uplus(cp) {
            return 'U+' + cp.toString(16).toUpperCase().padStart(4, '0');
        }

        function glyph(cp) {
            if (cp === 32) return '␣';          // пробел — иначе ячейка пустая
            return String.fromCodePoint(cp);
        }

        const body = widgetFrame(el, el.dataset.title);

        // ── управление: поле ввода и готовые примеры
        const topRow = document.createElement('div');
        topRow.className = 'flex flex-wrap items-center gap-2 justify-center mb-3';
        const label = document.createElement('label');
        label.className = 'text-xs text-gray-500 dark:text-slate-400';
        label.textContent = 'Текст';
        const input = document.createElement('input');
        input.type = 'text';
        input.value = text;
        input.maxLength = 24;
        input.className = INPUT + ' w-56';
        topRow.appendChild(label);
        topRow.appendChild(input);

        const presetRow = document.createElement('div');
        presetRow.className = 'flex flex-wrap items-center gap-2 justify-center mb-4';
        presets.forEach(function (p) {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = CHIP;
            btn.textContent = p;
            btn.addEventListener('click', function () {
                text = p;
                input.value = p;
                selected = 0;
                render();
            });
            presetRow.appendChild(btn);
        });

        // ── лента символов (может не влезть по ширине — своя прокрутка)
        const stripScroll = document.createElement('div');
        stripScroll.className = 'overflow-x-auto py-1';
        const strip = document.createElement('div');
        strip.className = 'flex gap-2 justify-center w-max mx-auto';
        stripScroll.appendChild(strip);

        const summary = document.createElement('div');
        summary.className = 'mt-3 text-center text-sm text-gray-600 dark:text-slate-300';

        const panel = document.createElement('div');
        panel.className = 'mt-4 rounded-lg border border-gray-200 bg-gray-50 p-3 dark:border-slate-600 dark:bg-slate-800';

        body.appendChild(topRow);
        body.appendChild(presetRow);
        body.appendChild(stripScroll);
        body.appendChild(summary);
        body.appendChild(panel);

        function renderStrip(chars) {
            strip.innerHTML = '';
            chars.forEach(function (item, index) {
                const card = document.createElement('button');
                card.type = 'button';
                card.className = 'px-2 py-1.5 rounded-md border transition-colors ' +
                    TONE[item.tpl.len] + (index === selected ? RING : '');
                const bytesHtml = item.bytes.map(function (b) {
                    return '<span class="px-1 py-0.5 rounded bg-white/70 dark:bg-slate-900/40">' +
                        '<span class="opacity-40">' + b.mark + '</span>' + b.chunk + '</span>';
                }).join('');
                card.innerHTML =
                    '<div class="text-xl font-mono leading-tight">' + escapeHtml(glyph(item.cp)) + '</div>' +
                    '<div class="text-[10px] font-mono opacity-70 leading-none mb-1">' + uplus(item.cp) + '</div>' +
                    '<div class="flex gap-1 text-[10px] font-mono leading-none">' + bytesHtml + '</div>' +
                    '<div class="text-[11px] font-mono mt-1 leading-none">' +
                        item.bytes.map(function (b) { return hex(b.value); }).join(' ') + '</div>';
                card.addEventListener('click', function () {
                    selected = index;
                    render();
                });
                strip.appendChild(card);
            });
        }

        function renderSummary(chars) {
            const utf8 = chars.reduce(function (s, i) { return s + i.tpl.len; }, 0);
            const utf16 = chars.reduce(function (s, i) { return s + (i.cp > 0xFFFF ? 4 : 2); }, 0);
            const utf32 = chars.length * 4;
            let html = '<b>' + chars.length + '</b> ' +
                plural(chars.length, 'символ', 'символа', 'символов') + ' → <b>' + utf8 + '</b> ' +
                plural(utf8, 'байт', 'байта', 'байтов') + ' в UTF-8';
            if (showCompare) {
                html += '<div class="mt-1 text-xs text-gray-500 dark:text-slate-400">' +
                    'тот же текст: UTF-8 — ' + utf8 + ' Б · UTF-16 — ' + utf16 +
                    ' Б · UTF-32 — ' + utf32 + ' Б</div>';
            }
            summary.innerHTML = html;
        }

        function renderPanel(chars) {
            panel.innerHTML = '';
            const item = chars[selected];
            const tpl = item.tpl;

            const head = document.createElement('div');
            head.className = 'text-center mb-3';
            head.innerHTML =
                '<span class="text-2xl font-mono">' + escapeHtml(glyph(item.cp)) + '</span>' +
                '<span class="ml-2 font-mono text-sm text-gray-600 dark:text-slate-300">' +
                    uplus(item.cp) + ' · код ' + item.cp + ' · ' + tpl.len + ' ' +
                    plural(tpl.len, 'байт', 'байта', 'байтов') + '</span>';
            panel.appendChild(head);

            // ── лента битов номера
            const srcCaption = document.createElement('div');
            srcCaption.className = 'text-center text-xs text-gray-500 dark:text-slate-400 mb-1';
            srcCaption.textContent = 'Номер ' + item.cp + ' в двоичном виде — ' + tpl.payload + ' ' +
                plural(tpl.payload, 'бит', 'бита', 'битов') + ':';
            panel.appendChild(srcCaption);

            const srcScroll = document.createElement('div');
            // py-1, а не pb-1: overflow-x-auto режет и по вертикали, поэтому
            // без верхнего отступа кольцо подсветки (ring-2) обрезается сверху.
            srcScroll.className = 'overflow-x-auto py-1';
            const srcRow = document.createElement('div');
            srcRow.className = 'flex gap-0.5 justify-center w-max mx-auto';
            srcScroll.appendChild(srcRow);
            panel.appendChild(srcScroll);

            const srcCells = [];
            for (let i = 0; i < tpl.payload; i++) {
                const cell = document.createElement('span');
                cell.className = 'w-6 h-6 rounded border font-mono text-xs flex items-center justify-center ' +
                    (item.bits.charAt(i) === '1' ? BIT_ON : BIT_OFF);
                cell.textContent = item.bits.charAt(i);
                srcCells.push(cell);
                srcRow.appendChild(cell);
            }

            const arrow = document.createElement('div');
            arrow.className = 'text-center text-xs text-gray-500 dark:text-slate-400 my-2';
            arrow.textContent = 'разъезжаются по свободным местам шаблона ↓';
            panel.appendChild(arrow);

            // ── байты: серые метки + приехавшие биты номера
            const bytesScroll = document.createElement('div');
            bytesScroll.className = 'overflow-x-auto pb-1';
            const bytesRow = document.createElement('div');
            bytesRow.className = 'flex gap-3 justify-center w-max mx-auto';
            bytesScroll.appendChild(bytesRow);
            panel.appendChild(bytesScroll);

            const payCells = {};

            function highlight(pos, on) {
                if (!srcCells[pos] || !payCells[pos]) return;
                [srcCells[pos], payCells[pos]].forEach(function (c) {
                    c.className = c.className.replace(RING, '') + (on ? RING : '');
                });
            }

            item.bytes.forEach(function (b, bi) {
                const box = document.createElement('div');
                box.className = 'rounded-md border p-1.5 ' + TONE[tpl.len];

                const row = document.createElement('div');
                row.className = 'flex gap-0.5';
                b.mark.split('').forEach(function (m) {
                    const cell = document.createElement('span');
                    cell.className = 'w-6 h-6 rounded border font-mono text-xs flex items-center justify-center ' + BIT_MARK;
                    cell.textContent = m;
                    cell.title = bi === 0
                        ? 'Метка ведущего байта: единиц до первого нуля столько же, сколько байтов у символа'
                        : 'Метка 10 — байт-продолжение, сам по себе символом не является';
                    row.appendChild(cell);
                });
                b.chunk.split('').forEach(function (bit, k) {
                    const pos = b.from + k;
                    const cell = document.createElement('span');
                    cell.className = 'w-6 h-6 rounded border font-mono text-xs flex items-center justify-center cursor-default ' +
                        (bit === '1' ? BIT_ON : BIT_OFF);
                    cell.textContent = bit;
                    cell.title = 'Бит № ' + pos + ' номера символа';
                    cell.addEventListener('mouseenter', function () { highlight(pos, true); });
                    cell.addEventListener('mouseleave', function () { highlight(pos, false); });
                    payCells[pos] = cell;
                    row.appendChild(cell);
                });
                box.appendChild(row);

                const cap = document.createElement('div');
                cap.className = 'text-center text-[11px] font-mono mt-1 leading-none';
                cap.textContent = '0x' + hex(b.value) + ' = ' + b.value;
                box.appendChild(cap);

                const role = document.createElement('div');
                role.className = 'text-center text-[10px] mt-0.5 leading-none opacity-70';
                role.textContent = bi === 0 ? 'ведущий' : 'продолжение';
                box.appendChild(role);

                bytesRow.appendChild(box);
            });

            const result = document.createElement('div');
            result.className = 'mt-3 text-center text-sm text-gray-700 dark:text-slate-200';
            const hexes = item.bytes.map(function (b) { return hex(b.value); }).join(' ');
            const pyBytes = item.bytes.map(function (b) { return '\\x' + hex(b.value).toLowerCase(); }).join('');
            result.innerHTML =
                'Итог: <b class="font-mono">' + hexes + '</b>' +
                '<div class="mt-1 text-xs text-gray-500 dark:text-slate-400 font-mono">' +
                    escapeHtml("'" + String.fromCodePoint(item.cp) + "'.encode('utf-8')") + ' → ' +
                    escapeHtml("b'" + pyBytes + "'") + '</div>';
            panel.appendChild(result);

            const note = document.createElement('p');
            note.className = 'mt-3 text-xs text-gray-500 dark:text-slate-400 text-center';
            note.textContent = LEN_NOTE[tpl.len];
            panel.appendChild(note);
        }

        function render() {
            const chars = Array.from(text).map(function (ch) {
                return encodeChar(ch.codePointAt(0));
            });

            if (!chars.length) {
                strip.innerHTML = '';
                summary.textContent = '';
                panel.innerHTML = '<p class="text-sm text-gray-500 dark:text-slate-400 text-center">' +
                    'Введите любой текст — покажу, во что он превращается в UTF-8.</p>';
                return;
            }
            if (selected >= chars.length) selected = 0;

            renderStrip(chars);
            renderSummary(chars);
            renderPanel(chars);
        }

        input.addEventListener('input', function () {
            text = input.value;
            selected = 0;
            render();
        });

        render();
    });

    // ─────────────────────────────────────────────────────────────
    // Виджет: fano-code — условие Фано, кодовое дерево и декодирование.
    //
    // Таблица кодов редактируется (принимаются только 0 и 1). Виджет
    // проверяет прямое и обратное условия Фано, рисует кодовое дерево
    // (символы обязаны стоять в листьях) и разбирает ленту битов, показывая
    // ВСЕ её прочтения — на неоднозначной таблице их несколько.
    //
    // Конфиг: {"codes": [["А","0"],["Б","10"]], "message": "0110",
    //          "presets": [{"title": "…", "codes": [...], "message": "…"}]}
    // ─────────────────────────────────────────────────────────────
    register('fano-code', function (el, config) {
        const MAX_ROWS = 8;
        const MAX_CODE = 8;       // длина одного кодового слова
        const MAX_TAPE = 24;      // длина ленты битов
        const MAX_VARIANTS = 6;   // сколько прочтений показываем
        const GUARD = 200000;     // предохранитель от экспоненциального перебора
        const SVG_NS = 'http://www.w3.org/2000/svg';
        const LETTERS = ['А', 'Б', 'В', 'Г', 'Д', 'Е', 'Ж', 'З'];

        // Цвет закреплён за строкой таблицы: одна и та же буква одинаково
        // выглядит в таблице, в дереве и в разобранной ленте.
        const TONE = [
            'bg-amber-50 border-amber-300 text-amber-900 dark:bg-amber-900/40 dark:border-amber-700 dark:text-amber-100',
            'bg-emerald-50 border-emerald-300 text-emerald-900 dark:bg-emerald-900/40 dark:border-emerald-700 dark:text-emerald-100',
            'bg-violet-50 border-violet-300 text-violet-900 dark:bg-violet-900/40 dark:border-violet-700 dark:text-violet-100',
            'bg-sky-50 border-sky-300 text-sky-900 dark:bg-sky-900/40 dark:border-sky-700 dark:text-sky-100',
            'bg-rose-50 border-rose-300 text-rose-900 dark:bg-rose-900/40 dark:border-rose-700 dark:text-rose-100',
            'bg-lime-50 border-lime-300 text-lime-900 dark:bg-lime-900/40 dark:border-lime-700 dark:text-lime-100',
            'bg-orange-50 border-orange-300 text-orange-900 dark:bg-orange-900/40 dark:border-orange-700 dark:text-orange-100',
            'bg-teal-50 border-teal-300 text-teal-900 dark:bg-teal-900/40 dark:border-teal-700 dark:text-teal-100'
        ];
        const SVG_TONE = [
            'fill-amber-100 stroke-amber-400 dark:fill-amber-800 dark:stroke-amber-500',
            'fill-emerald-100 stroke-emerald-400 dark:fill-emerald-800 dark:stroke-emerald-500',
            'fill-violet-100 stroke-violet-400 dark:fill-violet-800 dark:stroke-violet-500',
            'fill-sky-100 stroke-sky-400 dark:fill-sky-800 dark:stroke-sky-500',
            'fill-rose-100 stroke-rose-400 dark:fill-rose-800 dark:stroke-rose-500',
            'fill-lime-100 stroke-lime-400 dark:fill-lime-800 dark:stroke-lime-500',
            'fill-orange-100 stroke-orange-400 dark:fill-orange-800 dark:stroke-orange-500',
            'fill-teal-100 stroke-teal-400 dark:fill-teal-800 dark:stroke-teal-500'
        ];

        const CHIP = 'px-2.5 py-1 rounded-full text-xs border transition-colors bg-gray-50 text-gray-500 border-gray-200 hover:bg-gray-100 dark:bg-slate-700 dark:border-slate-600 dark:text-slate-300';
        const CHIP_ON = 'px-2.5 py-1 rounded-full text-xs border transition-colors bg-brand-600 text-white border-brand-600 dark:bg-cyan-500 dark:border-cyan-500';
        const INPUT = 'rounded-md border px-2 py-1 font-mono text-sm border-gray-200 bg-white text-gray-900 dark:border-slate-600 dark:bg-slate-800 dark:text-white';
        const CARD = 'rounded-lg border border-gray-200 bg-gray-50 p-3 dark:border-slate-600 dark:bg-slate-800';
        const OK_BADGE = 'px-2 py-0.5 rounded-md text-xs font-semibold border bg-emerald-50 border-emerald-300 text-emerald-700 dark:bg-emerald-900/30 dark:border-emerald-700 dark:text-emerald-300';
        const BAD_BADGE = 'px-2 py-0.5 rounded-md text-xs font-semibold border bg-red-50 border-red-300 text-red-700 dark:bg-red-900/30 dark:border-red-700 dark:text-red-300';
        const ROW_BAD = 'border-red-300 bg-red-50 dark:border-red-700 dark:bg-red-900/20';

        const DEFAULT_PRESETS = [
            {
                title: 'Префиксный код',
                codes: [['А', '0'], ['Б', '10'], ['В', '110'], ['Г', '111']],
                message: '0110100111'
            },
            {
                title: 'Ловушка',
                codes: [['А', '0'], ['Б', '1'], ['В', '01'], ['Г', '10']],
                message: '0101'
            },
            {
                title: 'Обратное условие',
                codes: [['А', '0'], ['Б', '01'], ['В', '011']],
                message: '011010'
            },
            {
                title: 'Метки UTF-8',
                codes: [['1Б', '0'], ['прод', '10'], ['2Б', '110'], ['3Б', '1110'], ['4Б', '11110']],
                message: '011010'
            }
        ];

        function plural(n, one, few, many) {
            const tail = Math.abs(n) % 100;
            if (tail >= 11 && tail <= 14) return many;
            const last = tail % 10;
            if (last === 1) return one;
            if (last >= 2 && last <= 4) return few;
            return many;
        }

        function cleanCode(s) {
            return String(s == null ? '' : s).replace(/[^01]/g, '').slice(0, MAX_CODE);
        }

        function cleanTape(s) {
            return String(s == null ? '' : s).replace(/[^01]/g, '').slice(0, MAX_TAPE);
        }

        function normalizeRows(src) {
            const out = [];
            if (Array.isArray(src)) {
                src.forEach(function (item) {
                    if (Array.isArray(item)) {
                        out.push({ sym: String(item[0]), code: cleanCode(item[1]) });
                    } else if (item && typeof item === 'object') {
                        out.push({ sym: String(item.symbol || item.sym || '?'), code: cleanCode(item.code) });
                    }
                });
            } else if (src && typeof src === 'object') {
                Object.keys(src).forEach(function (k) {
                    out.push({ sym: k, code: cleanCode(src[k]) });
                });
            }
            return out.slice(0, MAX_ROWS);
        }

        const presets = (Array.isArray(config.presets) && config.presets.length
            ? config.presets
            : DEFAULT_PRESETS).slice(0, 6);

        let rows = normalizeRows(config.codes);
        if (!rows.length) rows = normalizeRows(presets[0].codes);
        let tape = cleanTape(config.message !== undefined ? config.message : presets[0].message);

        // Стартовая таблица часто совпадает с одним из примеров — подсветим его
        function matchingPreset() {
            const key = rows.map(function (r) { return r.sym + ':' + r.code; }).join(',');
            for (let i = 0; i < presets.length; i++) {
                const p = normalizeRows(presets[i].codes)
                    .map(function (r) { return r.sym + ':' + r.code; }).join(',');
                if (p === key && cleanTape(presets[i].message) === tape) return i;
            }
            return -1;
        }
        let activePreset = matchingPreset();

        // ── анализ таблицы ───────────────────────────────────────
        // prefix: пары [короткий, длинный], где короткий — начало длинного;
        // suffix: то же для окончаний; same: совпавшие коды.
        function analyze() {
            const valid = [];
            rows.forEach(function (r, i) { if (r.code) valid.push(i); });
            const prefix = [];
            const suffix = [];
            const same = [];
            for (let a = 0; a < valid.length; a++) {
                for (let b = 0; b < valid.length; b++) {
                    if (a === b) continue;
                    const x = rows[valid[a]].code;
                    const y = rows[valid[b]].code;
                    if (x === y) {
                        if (a < b) same.push([valid[a], valid[b]]);
                        continue;
                    }
                    if (y.slice(0, x.length) === x) prefix.push([valid[a], valid[b]]);
                    if (y.slice(y.length - x.length) === x) suffix.push([valid[a], valid[b]]);
                }
            }
            return {
                valid: valid,
                prefix: prefix,
                suffix: suffix,
                same: same,
                fanoOk: prefix.length === 0 && same.length === 0,
                reverseOk: suffix.length === 0 && same.length === 0
            };
        }

        // Самое короткое слово, которое можно добавить, не нарушив условие Фано.
        function shortestFree() {
            const codes = rows.filter(function (r) { return r.code; }).map(function (r) { return r.code; });
            if (!codes.length) return '0';
            let queue = ['0', '1'];
            while (queue.length) {
                const next = [];
                for (let i = 0; i < queue.length; i++) {
                    const c = queue[i];
                    let under = false;   // существующий код — начало кандидата
                    let over = false;    // кандидат — начало существующего кода
                    for (let k = 0; k < codes.length; k++) {
                        if (c.slice(0, codes[k].length) === codes[k]) under = true;
                        if (codes[k].slice(0, c.length) === c) over = true;
                    }
                    if (!under && !over) return c;
                    // ветка ниже занятого кода мертва целиком — не растим её
                    if (!under && c.length < MAX_CODE) {
                        next.push(c + '0');
                        next.push(c + '1');
                    }
                }
                queue = next;
            }
            return null;
        }

        // Все прочтения ленты. Больше одного — код неоднозначен на этой ленте.
        function decodeAll(bits) {
            const valid = [];
            rows.forEach(function (r, i) { if (r.code) valid.push({ i: i, sym: r.sym, code: r.code }); });
            const results = [];
            let guard = 0;
            let stopped = false;
            if (!bits || !valid.length) return { results: results, stopped: false };
            (function walk(pos, acc) {
                if (stopped) return;
                if (results.length > MAX_VARIANTS || guard > GUARD) { stopped = true; return; }
                guard++;
                if (pos === bits.length) { results.push(acc.slice()); return; }
                for (let i = 0; i < valid.length; i++) {
                    const c = valid[i].code;
                    if (bits.slice(pos, pos + c.length) === c) {
                        acc.push(valid[i]);
                        walk(pos + c.length, acc);
                        acc.pop();
                    }
                }
            })(0, []);
            return { results: results, stopped: stopped };
        }

        // ── кодовое дерево ───────────────────────────────────────
        function buildTree() {
            const root = { code: '', bit: '', depth: 0, children: {}, symbols: [] };
            rows.forEach(function (r, i) {
                if (!r.code) return;
                let node = root;
                for (let k = 0; k < r.code.length; k++) {
                    const b = r.code.charAt(k);
                    if (!node.children[b]) {
                        node.children[b] = {
                            code: node.code + b, bit: b, depth: node.depth + 1,
                            children: {}, symbols: []
                        };
                    }
                    node = node.children[b];
                }
                node.symbols.push(i);
            });

            // свободные ветки — только под узлами, которые сами не символы
            (function addFree(node) {
                const kids = Object.keys(node.children);
                if (!kids.length) return;
                if (!node.symbols.length) {
                    ['0', '1'].forEach(function (b) {
                        if (!node.children[b]) {
                            node.children[b] = {
                                code: node.code + b, bit: b, depth: node.depth + 1,
                                children: {}, symbols: [], free: true
                            };
                        }
                    });
                }
                Object.keys(node.children).forEach(function (b) {
                    if (!node.children[b].free) addFree(node.children[b]);
                });
            })(root);

            return root;
        }

        function svgEl(name, attrs) {
            const node = document.createElementNS(SVG_NS, name);
            Object.keys(attrs || {}).forEach(function (k) {
                node.setAttribute(k, attrs[k]);
            });
            return node;
        }

        function renderTree(host) {
            host.innerHTML = '';
            const hasCodes = rows.some(function (r) { return r.code; });
            if (!hasCodes) {
                host.innerHTML = '<p class="text-sm text-gray-500 dark:text-slate-400 text-center py-4">' +
                    'Задайте хотя бы один код — и здесь вырастет дерево.</p>';
                return;
            }
            const root = buildTree();
            const STEP = 78;
            const ROW = 58;

            let leaves = 0;
            let maxDepth = 0;
            let sideCaps = false;
            (function layout(node) {
                const kids = ['0', '1'].map(function (b) { return node.children[b]; })
                    .filter(function (n) { return n; });
                if (node.symbols.length && kids.length) sideCaps = true;
                if (!kids.length) {
                    node.x = 40 + leaves * STEP;
                    leaves++;
                } else {
                    kids.forEach(layout);
                    node.x = (kids[0].x + kids[kids.length - 1].x) / 2;
                }
                node.y = 28 + node.depth * ROW;
                if (node.depth > maxDepth) maxDepth = node.depth;
            })(root);

            const width = Math.max(240, 80 + (leaves - 1) * STEP) + (sideCaps ? 44 : 0);
            const height = 28 + maxDepth * ROW + 52;
            const svg = svgEl('svg', {
                width: width, height: height,
                viewBox: '0 0 ' + width + ' ' + height,
                class: 'mx-auto block'
            });

            // рёбра и подписи 0/1
            (function edges(node) {
                ['0', '1'].forEach(function (b) {
                    const kid = node.children[b];
                    if (!kid) return;
                    svg.appendChild(svgEl('line', {
                        x1: node.x, y1: node.y + 12, x2: kid.x, y2: kid.y - 14,
                        class: 'stroke-gray-300 dark:stroke-slate-600',
                        'stroke-width': 2,
                        'stroke-dasharray': kid.free ? '4 3' : ''
                    }));
                    // Метку отводим по нормали к ребру, а не просто влево/вправо:
                    // на крутых рёбрах горизонтальный сдвиг кладёт цифру на саму линию.
                    const dx = kid.x - node.x;
                    const dy = kid.y - node.y;
                    const len = Math.sqrt(dx * dx + dy * dy) || 1;
                    const off = 13;
                    const label = svgEl('text', {
                        x: (node.x + kid.x) / 2 + (b === '0' ? -dy : dy) / len * off,
                        y: (node.y + kid.y) / 2 + (b === '0' ? dx : -dx) / len * off + 4,
                        'text-anchor': 'middle',
                        class: 'fill-gray-400 dark:fill-slate-500',
                        'font-size': 12, 'font-family': 'monospace'
                    });
                    label.textContent = b;
                    svg.appendChild(label);
                    edges(kid);
                });
            })(root);

            // узлы
            (function nodes(node) {
                const kids = Object.keys(node.children);
                const isSymbol = node.symbols.length > 0;
                const broken = isSymbol && kids.length > 0;   // символ не в листе
                let w = 30;

                if (isSymbol) {
                    const text = node.symbols.map(function (i) { return rows[i].sym; }).join('/');
                    w = Math.max(30, text.length * 9 + 12);
                    svg.appendChild(svgEl('rect', {
                        x: node.x - w / 2, y: node.y - 14, width: w, height: 28, rx: 8,
                        class: (broken
                            ? 'fill-red-100 stroke-red-500 dark:fill-red-900 dark:stroke-red-400'
                            : SVG_TONE[node.symbols[0] % SVG_TONE.length]),
                        'stroke-width': broken ? 2.5 : 1.5
                    }));
                    const t = svgEl('text', {
                        x: node.x, y: node.y + 5, 'text-anchor': 'middle',
                        class: broken ? 'fill-red-700 dark:fill-red-100' : 'fill-gray-800 dark:fill-slate-100',
                        'font-size': 13, 'font-weight': 600
                    });
                    t.textContent = text;
                    svg.appendChild(t);
                } else {
                    svg.appendChild(svgEl('circle', {
                        cx: node.x, cy: node.y, r: node.free ? 11 : 6,
                        class: node.free
                            ? 'fill-transparent stroke-gray-300 dark:stroke-slate-600'
                            : 'fill-gray-300 stroke-gray-300 dark:fill-slate-600 dark:stroke-slate-600',
                        'stroke-width': 1.5,
                        'stroke-dasharray': node.free ? '3 3' : ''
                    }));
                }

                if (node.code && (isSymbol || node.free)) {
                    // Под узлом с детьми уже идёт ребро со своей меткой 0/1 –
                    // код там налезает на цифру, поэтому уводим его вправо от плашки.
                    const cap = svgEl('text', kids.length ? {
                        x: node.x + w / 2 + 5, y: node.y + 4, 'text-anchor': 'start',
                        class: 'fill-gray-500 dark:fill-slate-400',
                        'font-size': 11, 'font-family': 'monospace'
                    } : {
                        x: node.x, y: node.y + 30, 'text-anchor': 'middle',
                        class: node.free ? 'fill-gray-400 dark:fill-slate-500' : 'fill-gray-500 dark:fill-slate-400',
                        'font-size': 11, 'font-family': 'monospace'
                    });
                    cap.textContent = node.code;
                    svg.appendChild(cap);
                }

                Object.keys(node.children).forEach(function (b) { nodes(node.children[b]); });
            })(root);

            host.appendChild(svg);
        }

        // ── разметка ─────────────────────────────────────────────
        const body = widgetFrame(el, el.dataset.title);

        const presetRow = document.createElement('div');
        presetRow.className = 'flex flex-wrap items-center gap-2 justify-center mb-4';
        const presetBtns = [];
        presets.forEach(function (p, index) {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.textContent = p.title || ('Пример ' + (index + 1));
            btn.addEventListener('click', function () {
                rows = normalizeRows(p.codes);
                tape = cleanTape(p.message);
                activePreset = index;
                renderTable();
                refresh();
            });
            presetBtns.push(btn);
            presetRow.appendChild(btn);
        });

        const grid = document.createElement('div');
        grid.className = 'grid gap-3 md:grid-cols-2';

        const tableCard = document.createElement('div');
        tableCard.className = CARD;
        const tableHead = document.createElement('div');
        tableHead.className = 'text-xs text-gray-500 dark:text-slate-400 mb-2';
        tableHead.textContent = 'Таблица кодов — правьте прямо здесь (только 0 и 1)';
        const tableBody = document.createElement('div');
        const tableFoot = document.createElement('div');
        tableFoot.className = 'mt-2 flex flex-wrap items-center gap-2';
        tableCard.appendChild(tableHead);
        tableCard.appendChild(tableBody);
        tableCard.appendChild(tableFoot);

        // Два ряда: таблица и дерево сверху, лента и вердикт снизу.
        // Вердикт стоит справа от ленты, на узком экране уезжает под неё.
        const verdictCard = document.createElement('div');
        verdictCard.className = 'pt-3 border-t md:pt-0 md:border-t-0 md:border-l md:pl-4 border-gray-200 dark:border-slate-600';

        const treeCard = document.createElement('div');
        treeCard.className = CARD;
        const treeCap = document.createElement('div');
        treeCap.className = 'text-xs text-gray-500 dark:text-slate-400 mb-1 text-center';
        treeCap.textContent = 'Кодовое дерево: шаг влево — 0, шаг вправо — 1. ' +
            'Символы обязаны стоять в листьях; пунктиром показаны свободные ветки.';
        const treeHost = document.createElement('div');
        treeHost.className = 'overflow-x-auto';
        treeCard.appendChild(treeCap);
        treeCard.appendChild(treeHost);

        grid.appendChild(tableCard);
        grid.appendChild(treeCard);

        const decodeCard = document.createElement('div');
        decodeCard.className = 'mt-3 ' + CARD;
        const tapeRow = document.createElement('div');
        tapeRow.className = 'flex flex-wrap items-center gap-2 mb-2';
        const tapeLabel = document.createElement('span');
        tapeLabel.className = 'text-xs text-gray-500 dark:text-slate-400';
        tapeLabel.textContent = 'Лента битов';
        const tapeInput = document.createElement('input');
        tapeInput.type = 'text';
        tapeInput.maxLength = MAX_TAPE;
        tapeInput.className = INPUT + ' w-56';
        const backBtn = document.createElement('button');
        backBtn.type = 'button';
        backBtn.className = CHIP;
        backBtn.textContent = 'Стереть бит';
        const clearBtn = document.createElement('button');
        clearBtn.type = 'button';
        clearBtn.className = CHIP;
        clearBtn.textContent = 'Очистить';
        tapeRow.appendChild(tapeLabel);
        tapeRow.appendChild(tapeInput);
        tapeRow.appendChild(backBtn);
        tapeRow.appendChild(clearBtn);

        const encodeRow = document.createElement('div');
        encodeRow.className = 'flex flex-wrap items-center gap-2 mb-3';
        const decodeOut = document.createElement('div');

        const decodeLeft = document.createElement('div');
        decodeLeft.appendChild(tapeRow);
        decodeLeft.appendChild(encodeRow);
        decodeLeft.appendChild(decodeOut);

        const decodeGrid = document.createElement('div');
        decodeGrid.className = 'grid gap-3 md:grid-cols-2';
        decodeGrid.appendChild(decodeLeft);
        decodeGrid.appendChild(verdictCard);
        decodeCard.appendChild(decodeGrid);

        body.appendChild(presetRow);
        body.appendChild(grid);
        body.appendChild(decodeCard);

        // ── таблица кодов ────────────────────────────────────────
        const rowEls = [];

        function renderTable() {
            tableBody.innerHTML = '';
            tableFoot.innerHTML = '';
            rowEls.length = 0;

            rows.forEach(function (r, i) {
                const line = document.createElement('div');
                line.className = 'flex items-center gap-2 mb-1.5 rounded-md border border-transparent px-1.5 py-1';

                const chip = document.createElement('span');
                chip.className = 'px-2 h-8 rounded-md border inline-flex items-center justify-center ' +
                    'text-sm font-semibold ' + TONE[i % TONE.length];
                chip.textContent = r.sym;

                const input = document.createElement('input');
                input.type = 'text';
                input.value = r.code;
                input.maxLength = MAX_CODE;
                input.className = INPUT + ' w-24';
                input.addEventListener('input', function () {
                    const cleaned = cleanCode(input.value);
                    if (input.value !== cleaned) input.value = cleaned;
                    rows[i].code = cleaned;
                    activePreset = -1;
                    refresh();
                });

                const len = document.createElement('span');
                len.className = 'text-xs text-gray-500 dark:text-slate-400 w-16';

                line.appendChild(chip);
                line.appendChild(input);
                line.appendChild(len);

                if (rows.length > 2) {
                    const del = document.createElement('button');
                    del.type = 'button';
                    del.className = 'ml-auto px-2 text-gray-400 hover:text-red-500 dark:text-slate-500';
                    del.textContent = '×';
                    del.title = 'Убрать символ';
                    del.addEventListener('click', function () {
                        rows.splice(i, 1);
                        activePreset = -1;
                        renderTable();
                        refresh();
                    });
                    line.appendChild(del);
                }

                rowEls.push({ line: line, len: len });
                tableBody.appendChild(line);
            });

            if (rows.length < MAX_ROWS) {
                const add = document.createElement('button');
                add.type = 'button';
                add.className = CHIP;
                add.addEventListener('click', function () {
                    const used = rows.map(function (r) { return r.sym; });
                    const letter = LETTERS.filter(function (l) { return used.indexOf(l) < 0; })[0] ||
                        ('С' + (rows.length + 1));
                    rows.push({ sym: letter, code: shortestFree() || '' });
                    activePreset = -1;
                    renderTable();
                    refresh();
                });
                add.textContent = '+ добавить символ';
                tableFoot.appendChild(add);
            }
        }

        // ── вердикт ──────────────────────────────────────────────
        function pairText(pair, kind) {
            const a = rows[pair[0]];
            const b = rows[pair[1]];
            if (kind === 'same') {
                return 'у ' + a.sym + ' и ' + b.sym + ' один и тот же код ' + a.code;
            }
            if (kind === 'prefix') {
                return 'код ' + b.sym + ' = ' + b.code + ' начинается с кода ' + a.sym + ' = ' + a.code;
            }
            return 'код ' + b.sym + ' = ' + b.code + ' оканчивается кодом ' + a.sym + ' = ' + a.code;
        }

        function reasons(info, kind) {
            const list = (kind === 'prefix' ? info.prefix : info.suffix).slice(0, 3)
                .map(function (p) { return pairText(p, kind); });
            info.same.slice(0, 2).forEach(function (p) { list.unshift(pairText(p, 'same')); });
            return list;
        }

        function renderVerdict(info) {
            verdictCard.innerHTML = '';

            function block(titleText, ok, okText, badText, list) {
                const wrap = document.createElement('div');
                wrap.className = 'mb-3 last:mb-0';
                const head = document.createElement('div');
                head.className = 'flex items-center gap-2 mb-1';
                const name = document.createElement('span');
                name.className = 'text-sm font-semibold text-gray-700 dark:text-slate-200';
                name.textContent = titleText;
                const badge = document.createElement('span');
                badge.className = ok ? OK_BADGE : BAD_BADGE;
                badge.textContent = ok ? 'выполняется' : 'нарушено';
                head.appendChild(name);
                head.appendChild(badge);
                const note = document.createElement('div');
                note.className = 'text-xs text-gray-600 dark:text-slate-300';
                note.textContent = ok ? okText : badText;
                wrap.appendChild(head);
                wrap.appendChild(note);
                if (!ok && list.length) {
                    const ul = document.createElement('ul');
                    ul.className = 'mt-1 text-xs text-red-600 dark:text-red-300 list-disc list-inside';
                    list.forEach(function (t) {
                        const li = document.createElement('li');
                        li.textContent = t;
                        ul.appendChild(li);
                    });
                    wrap.appendChild(ul);
                }
                return wrap;
            }

            verdictCard.appendChild(block(
                'Условие Фано', info.fanoOk,
                'Ни одно кодовое слово не является началом другого — код префиксный. ' +
                'Любая лента читается однозначно, слева направо, за один проход.',
                'Есть кодовое слово, которое является началом другого. Дочитав его, ' +
                'декодер не знает: символ уже кончился или это только начало следующего.',
                reasons(info, 'prefix')
            ));

            verdictCard.appendChild(block(
                'Обратное условие Фано', info.reverseOk,
                'Ни одно кодовое слово не является окончанием другого. Такая лента ' +
                'тоже читается однозначно, но с конца.',
                'Есть кодовое слово, которое является окончанием другого — с конца ' +
                'лента читается неоднозначно.',
                reasons(info, 'suffix')
            ));

            const hint = document.createElement('div');
            hint.className = 'text-xs text-gray-500 dark:text-slate-400 border-t border-gray-200 pt-2 dark:border-slate-600';

            if (info.fanoOk) {
                const free = shortestFree();
                const line = document.createElement('div');
                line.textContent = free
                    ? ('Самое короткое свободное слово — ' + free +
                       ': его можно отдать новому символу, не сломав код.')
                    : 'Свободных слов в дереве не осталось — все ветки заняты.';
                hint.appendChild(line);
            }

            const note = document.createElement('div');
            note.className = info.fanoOk ? 'mt-1' : '';
            if (info.fanoOk && !info.reverseOk) {
                note.textContent = 'Прямого условия достаточно: код читается слева направо. ' +
                    'Именно поэтому на практике берут префиксные коды — символ выдаётся сразу, ' +
                    'не дожидаясь конца сообщения.';
            } else if (!info.fanoOk && info.reverseOk) {
                note.textContent = 'Условие Фано нарушено, но код всё равно однозначен — читать нужно с конца. ' +
                    'Это и означает, что условие Фано достаточно, но не необходимо.';
            } else if (!info.fanoOk && !info.reverseOk) {
                note.textContent = 'Оба условия нарушены — однозначность не гарантирована ни в одну сторону. ' +
                    'Проверьте ленту внизу: скорее всего, у неё найдётся несколько прочтений.';
            } else {
                note.textContent = 'Код читается однозначно в обе стороны: и слева направо, и с конца.';
            }
            hint.appendChild(note);
            verdictCard.appendChild(hint);
        }

        // ── лента и её прочтения ─────────────────────────────────
        function renderEncodeButtons() {
            encodeRow.innerHTML = '';
            const cap = document.createElement('span');
            cap.className = 'text-xs text-gray-500 dark:text-slate-400';
            cap.textContent = 'Собрать ленту:';
            encodeRow.appendChild(cap);
            rows.forEach(function (r, i) {
                if (!r.code) return;
                const btn = document.createElement('button');
                btn.type = 'button';
                btn.className = 'px-2 py-1 rounded-md border text-xs font-mono ' + TONE[i % TONE.length];
                btn.textContent = r.sym + ' → ' + r.code;
                btn.addEventListener('click', function () {
                    tape = cleanTape(tape + r.code);
                    tapeInput.value = tape;
                    refresh();
                });
                encodeRow.appendChild(btn);
            });
        }

        function variantStrip(variant) {
            const strip = document.createElement('div');
            strip.className = 'flex flex-wrap items-center gap-1';
            variant.forEach(function (item) {
                const chunk = document.createElement('span');
                chunk.className = 'px-2 py-1 rounded-md border text-center ' + TONE[item.i % TONE.length];
                chunk.innerHTML = '<span class="font-mono text-sm">' + item.code + '</span>' +
                    '<span class="block text-[11px] font-semibold leading-none">' + escapeHtml(item.sym) + '</span>';
                strip.appendChild(chunk);
            });
            return strip;
        }

        function renderDecode(info) {
            decodeOut.innerHTML = '';
            if (!tape) {
                decodeOut.innerHTML = '<p class="text-sm text-gray-500 dark:text-slate-400">' +
                    'Наберите ленту битов или соберите её кнопками выше.</p>';
                return;
            }

            const res = decodeAll(tape);
            const shown = res.results.slice(0, MAX_VARIANTS);
            const more = res.results.length > MAX_VARIANTS || res.stopped;

            const head = document.createElement('div');
            head.className = 'text-sm mb-2';
            if (!res.results.length) {
                head.className += ' text-gray-600 dark:text-slate-300';
                head.textContent = 'Эта лента не разбирается на кодовые слова целиком: ' +
                    'где-то остаётся хвост, которому не соответствует ни один символ.';
            } else if (res.results.length === 1) {
                head.className += ' text-emerald-700 dark:text-emerald-300';
                head.textContent = 'Лента читается единственным способом — декодирование однозначно.';
            } else {
                head.className += ' text-red-600 dark:text-red-300 font-semibold';
                head.textContent = 'Лента читается ' + (more ? 'более чем ' : '') +
                    shown.length + ' ' + plural(shown.length, 'способом', 'способами', 'способами') +
                    ' — однозначного декодирования нет.';
            }
            decodeOut.appendChild(head);

            shown.forEach(function (variant) {
                const line = document.createElement('div');
                line.className = 'flex flex-wrap items-center gap-2 mb-2';
                line.appendChild(variantStrip(variant));
                const word = document.createElement('span');
                word.className = 'text-sm text-gray-700 dark:text-slate-200';
                word.textContent = '= ' + variant.map(function (v) { return v.sym; }).join('');
                line.appendChild(word);
                decodeOut.appendChild(line);
            });

            if (res.results.length > 1) {
                const why = document.createElement('p');
                why.className = 'text-xs text-gray-500 dark:text-slate-400 mt-1';
                why.textContent = 'Ни одно из прочтений не «более правильное»: сама лента не содержит ' +
                    'информации о том, где границы символов. Разделителей в ней нет.';
                decodeOut.appendChild(why);
            } else if (res.results.length === 1 && info.fanoOk) {
                const bits = document.createElement('p');
                bits.className = 'text-xs text-gray-500 dark:text-slate-400 mt-1';
                const n = shown[0].length;
                bits.textContent = n + ' ' + plural(n, 'символ', 'символа', 'символов') + ' → ' +
                    tape.length + ' ' + plural(tape.length, 'бит', 'бита', 'битов') + ', в среднем ' +
                    (tape.length / n).toFixed(2).replace('.', ',') + ' бита на символ.';
                decodeOut.appendChild(bits);
            }
        }

        // ── общий пересчёт ───────────────────────────────────────
        function refresh() {
            const info = analyze();

            const bad = {};
            info.prefix.forEach(function (p) { bad[p[0]] = true; bad[p[1]] = true; });
            info.same.forEach(function (p) { bad[p[0]] = true; bad[p[1]] = true; });

            rowEls.forEach(function (ref, i) {
                ref.line.className = 'flex items-center gap-2 mb-1.5 rounded-md border px-1.5 py-1 ' +
                    (bad[i] ? ROW_BAD : 'border-transparent');
                const n = rows[i].code.length;
                ref.len.textContent = n ? (n + ' ' + plural(n, 'бит', 'бита', 'битов')) : '—';
            });

            presetBtns.forEach(function (btn, index) {
                btn.className = index === activePreset ? CHIP_ON : CHIP;
            });

            tapeInput.value = tape;
            renderVerdict(info);
            renderTree(treeHost);
            renderEncodeButtons();
            renderDecode(info);
        }

        tapeInput.addEventListener('input', function () {
            const cleaned = cleanTape(tapeInput.value);
            if (tapeInput.value !== cleaned) tapeInput.value = cleaned;
            tape = cleaned;
            refresh();
        });
        backBtn.addEventListener('click', function () {
            tape = tape.slice(0, -1);
            refresh();
        });
        clearBtn.addEventListener('click', function () {
            tape = '';
            refresh();
        });

        renderTable();
        refresh();
    });

    // ─────────────────────────────────────────────────────────────
    // Виджет: huffman-tree — сборка дерева Хаффмана своими руками.
    // Ученик сам выбирает два узла для слияния, виджет растит дерево,
    // снимает с него коды и считает выигрыш. Неоптимальный ход не
    // запрещается: он помечается, а в итоге видно, что дерево вышло
    // дороже минимума — это и есть главный урок виджета.
    // Конфиг: {"text":"АБРАКАДАБРА"} или {"freqs":[["А",5],["Б",2]]},
    // плюс необязательные "presets": [{"title":"…","text":"…"}] либо
    // [{"title":"…","freqs":[["А",5],…]}]. До 8 символов, частота 1–99.
    // ─────────────────────────────────────────────────────────────
    register('huffman-tree', function (el, config) {
        const MAX_SYMBOLS = 8;
        const MAX_FREQ = 99;
        const MAX_TEXT = 40;
        const SVG_NS = 'http://www.w3.org/2000/svg';
        const LETTERS = ['А', 'Б', 'В', 'Г', 'Д', 'Е', 'Ж', 'З'];

        // Цвет закреплён за символом: одна и та же буква одинаково выглядит
        // в редакторе частот, в очереди узлов, в дереве и в таблице кодов.
        const TONE = [
            'bg-amber-50 border-amber-300 text-amber-900 dark:bg-amber-900/40 dark:border-amber-700 dark:text-amber-100',
            'bg-emerald-50 border-emerald-300 text-emerald-900 dark:bg-emerald-900/40 dark:border-emerald-700 dark:text-emerald-100',
            'bg-violet-50 border-violet-300 text-violet-900 dark:bg-violet-900/40 dark:border-violet-700 dark:text-violet-100',
            'bg-sky-50 border-sky-300 text-sky-900 dark:bg-sky-900/40 dark:border-sky-700 dark:text-sky-100',
            'bg-rose-50 border-rose-300 text-rose-900 dark:bg-rose-900/40 dark:border-rose-700 dark:text-rose-100',
            'bg-lime-50 border-lime-300 text-lime-900 dark:bg-lime-900/40 dark:border-lime-700 dark:text-lime-100',
            'bg-orange-50 border-orange-300 text-orange-900 dark:bg-orange-900/40 dark:border-orange-700 dark:text-orange-100',
            'bg-teal-50 border-teal-300 text-teal-900 dark:bg-teal-900/40 dark:border-teal-700 dark:text-teal-100'
        ];
        const SVG_TONE = [
            'fill-amber-100 stroke-amber-400 dark:fill-amber-800 dark:stroke-amber-500',
            'fill-emerald-100 stroke-emerald-400 dark:fill-emerald-800 dark:stroke-emerald-500',
            'fill-violet-100 stroke-violet-400 dark:fill-violet-800 dark:stroke-violet-500',
            'fill-sky-100 stroke-sky-400 dark:fill-sky-800 dark:stroke-sky-500',
            'fill-rose-100 stroke-rose-400 dark:fill-rose-800 dark:stroke-rose-500',
            'fill-lime-100 stroke-lime-400 dark:fill-lime-800 dark:stroke-lime-500',
            'fill-orange-100 stroke-orange-400 dark:fill-orange-800 dark:stroke-orange-500',
            'fill-teal-100 stroke-teal-400 dark:fill-teal-800 dark:stroke-teal-500'
        ];

        const CHIP = 'px-2.5 py-1 rounded-full text-xs border transition-colors bg-gray-50 text-gray-500 border-gray-200 hover:bg-gray-100 dark:bg-slate-700 dark:border-slate-600 dark:text-slate-300';
        const CHIP_ON = 'px-2.5 py-1 rounded-full text-xs border transition-colors bg-brand-600 text-white border-brand-600 dark:bg-cyan-500 dark:border-cyan-500';
        const INPUT = 'rounded-md border px-2 py-1 font-mono text-sm border-gray-200 bg-white text-gray-900 dark:border-slate-600 dark:bg-slate-800 dark:text-white';
        const CARD = 'rounded-lg border border-gray-200 bg-gray-50 p-3 dark:border-slate-600 dark:bg-slate-800';
        const BTN = 'px-3 py-1.5 rounded-md border text-sm transition-colors bg-white text-gray-700 border-gray-200 hover:bg-gray-100 disabled:opacity-40 dark:bg-slate-700 dark:border-slate-600 dark:text-slate-200';
        const BTN_MAIN = 'px-3 py-1.5 rounded-md border text-sm font-semibold transition-colors bg-brand-600 text-white border-brand-600 hover:bg-brand-700 disabled:opacity-40 dark:bg-cyan-500 dark:border-cyan-500';
        const OK_BADGE = 'px-2 py-0.5 rounded-md text-xs font-semibold border bg-emerald-50 border-emerald-300 text-emerald-700 dark:bg-emerald-900/30 dark:border-emerald-700 dark:text-emerald-300';
        const BAD_BADGE = 'px-2 py-0.5 rounded-md text-xs font-semibold border bg-amber-50 border-amber-300 text-amber-700 dark:bg-amber-900/30 dark:border-amber-700 dark:text-amber-300';

        const DEFAULT_PRESETS = [
            { title: 'АБРАКАДАБРА', text: 'АБРАКАДАБРА' },
            { title: 'Все частоты равны', freqs: [['А', 1], ['Б', 1], ['В', 1], ['Г', 1]] },
            { title: 'Одна буква правит', freqs: [['А', 20], ['Б', 3], ['В', 2], ['Г', 1]] }
        ];

        function plural(n, one, few, many) {
            const tail = Math.abs(n) % 100;
            if (tail >= 11 && tail <= 14) return many;
            const last = tail % 10;
            if (last === 1) return one;
            if (last >= 2 && last <= 4) return few;
            return many;
        }

        function fmt(x) {
            return x.toFixed(2).replace('.', ',');
        }

        // То же число внутри $…$: голая запятая в математике – знак пунктуации
        // и тянет за собой пробел, поэтому её прячут в скобки.
        function mfmt(x) {
            return fmt(x).replace(',', '{,}');
        }

        // ── исходные данные: частоты символов ────────────────────
        function countText(src) {
            const text = String(src == null ? '' : src).replace(/\s+/g, '').slice(0, MAX_TEXT);
            const seen = [];
            const map = {};
            for (let i = 0; i < text.length; i++) {
                const ch = text.charAt(i);
                if (map[ch] === undefined) { map[ch] = 0; seen.push(ch); }
                map[ch]++;
            }
            // при переборе символов оставляем самые частые, порядок — по убыванию
            const out = seen.map(function (ch) { return { sym: ch, freq: map[ch] }; });
            out.sort(function (a, b) { return b.freq - a.freq; });
            return out.slice(0, MAX_SYMBOLS);
        }

        function normalizeFreqs(src) {
            const out = [];
            if (Array.isArray(src)) {
                src.forEach(function (item) {
                    let sym = '?';
                    let freq = 1;
                    if (Array.isArray(item)) {
                        sym = String(item[0]);
                        freq = parseInt(item[1], 10);
                    } else if (item && typeof item === 'object') {
                        sym = String(item.symbol || item.sym || '?');
                        freq = parseInt(item.freq !== undefined ? item.freq : item.count, 10);
                    }
                    if (!(freq >= 1)) freq = 1;
                    out.push({ sym: sym.slice(0, 3), freq: Math.min(freq, MAX_FREQ) });
                });
            } else if (src && typeof src === 'object') {
                Object.keys(src).forEach(function (k) {
                    const freq = parseInt(src[k], 10);
                    out.push({ sym: k.slice(0, 3), freq: (freq >= 1 ? Math.min(freq, MAX_FREQ) : 1) });
                });
            }
            return out.slice(0, MAX_SYMBOLS);
        }

        function fromSource(src) {
            if (src && src.freqs) {
                const f = normalizeFreqs(src.freqs);
                if (f.length >= 2) return f;
            }
            if (src && src.text) {
                const f = countText(src.text);
                if (f.length >= 2) return f;
            }
            return null;
        }

        const presets = (Array.isArray(config.presets) && config.presets.length
            ? config.presets
            : DEFAULT_PRESETS).slice(0, 5);

        let leaves = fromSource(config) || fromSource(presets[0]) ||
            normalizeFreqs([['А', 5], ['Б', 2], ['В', 1]]);
        let sourceText = config.text ? String(config.text).replace(/\s+/g, '').slice(0, MAX_TEXT) : '';

        function matchingPreset() {
            const key = leaves.map(function (l) { return l.sym + ':' + l.freq; }).join(',');
            for (let i = 0; i < presets.length; i++) {
                const f = fromSource(presets[i]);
                if (!f) continue;
                if (f.map(function (l) { return l.sym + ':' + l.freq; }).join(',') === key) return i;
            }
            return -1;
        }
        let activePreset = matchingPreset();

        // ── состояние сборки ─────────────────────────────────────
        let nodes = [];      // текущий лес: узлы, которые ещё не объединены
        let steps = [];      // журнал слияний
        let history = [];    // снимки для «шага назад»
        let selected = [];   // выбранные узлы (не более двух)
        let bornSeq = 0;

        function resetBuild() {
            bornSeq = 0;
            nodes = leaves.map(function (lf, i) {
                return { w: lf.freq, sym: lf.sym, idx: i, left: null, right: null, born: bornSeq++ };
            });
            steps = [];
            history = [];
            selected = [];
        }

        // Очередь: по возрастанию частоты, при равенстве — кто раньше появился.
        function queueOrder() {
            return nodes.slice().sort(function (a, b) {
                return a.w - b.w || a.born - b.born;
            });
        }

        // Пара считается верной, если совпали сами веса двух самых лёгких
        // узлов: при ничьей подходит любой из равных, и это не ошибка.
        function isOptimalPair(a, b) {
            const q = queueOrder();
            if (q.length < 2) return false;
            const want = [q[0].w, q[1].w].sort(function (x, y) { return x - y; });
            const got = [a.w, b.w].sort(function (x, y) { return x - y; });
            return want[0] === got[0] && want[1] === got[1];
        }

        function merge(a, b) {
            if (!a || !b || a === b) return;
            history.push({ nodes: nodes.slice(), steps: steps.slice() });
            const ok = isOptimalPair(a, b);
            // левым делаем более лёгкий узел, при равенстве — выбранный первым
            let left = a;
            let right = b;
            if (b.w < a.w) { left = b; right = a; }
            const node = {
                w: a.w + b.w, sym: null, idx: -1,
                left: left, right: right, born: bornSeq++
            };
            nodes = nodes.filter(function (n) { return n !== a && n !== b; });
            nodes.push(node);
            steps.push({ left: left, right: right, node: node, ok: ok });
            selected = [];
        }

        function autoStep() {
            const q = queueOrder();
            if (q.length < 2) return;
            merge(q[0], q[1]);
        }

        // ── подсчёты ─────────────────────────────────────────────
        // Суммарная длина записи = сумма весов всех внутренних узлов.
        function costOf(node) {
            if (node.sym !== null) return 0;
            return node.w + costOf(node.left) + costOf(node.right);
        }

        function optimalCost() {
            const arr = leaves.map(function (l) { return l.freq; });
            let total = 0;
            while (arr.length > 1) {
                arr.sort(function (x, y) { return x - y; });
                const a = arr.shift();
                const b = arr.shift();
                total += a + b;
                arr.push(a + b);
            }
            return total;
        }

        function totalFreq() {
            return leaves.reduce(function (s, l) { return s + l.freq; }, 0);
        }

        function uniformBits() {
            let b = 1;
            while ((1 << b) < leaves.length) b++;
            return b;
        }

        function collectCodes(root) {
            const map = {};
            (function walk(n, path) {
                if (n.sym !== null) { map[n.sym] = path || '0'; return; }
                walk(n.left, path + '0');
                walk(n.right, path + '1');
            })(root, '');
            return map;
        }

        function labelOf(n) {
            if (n.sym !== null) return n.sym;
            const syms = [];
            (function walk(x) {
                if (x.sym !== null) syms.push(x.sym);
                else { walk(x.left); walk(x.right); }
            })(n);
            const s = syms.join('');
            return s.length > 6 ? s.slice(0, 6) + '…' : s;
        }

        // ── разметка ─────────────────────────────────────────────
        const body = widgetFrame(el, el.dataset.title);

        const presetRow = document.createElement('div');
        presetRow.className = 'flex flex-wrap items-center gap-2 justify-center mb-4';
        const presetBtns = [];
        presets.forEach(function (p, index) {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.textContent = p.title || ('Пример ' + (index + 1));
            btn.addEventListener('click', function () {
                const f = fromSource(p);
                if (!f) return;
                leaves = f;
                sourceText = p.text ? String(p.text).replace(/\s+/g, '').slice(0, MAX_TEXT) : '';
                activePreset = index;
                resetBuild();
                renderEditor();
                refresh();
            });
            presetBtns.push(btn);
            presetRow.appendChild(btn);
        });

        const editorCard = document.createElement('div');
        editorCard.className = CARD;
        const editorHead = document.createElement('div');
        editorHead.className = 'text-xs text-gray-500 dark:text-slate-400 mb-2';
        editorHead.textContent = 'Символы и их частоты — правьте прямо здесь';
        const editorBody = document.createElement('div');
        editorBody.className = 'flex flex-wrap items-center gap-2';
        const editorFoot = document.createElement('div');
        editorFoot.className = 'mt-2 flex flex-wrap items-center gap-2';
        editorCard.appendChild(editorHead);
        editorCard.appendChild(editorBody);
        editorCard.appendChild(editorFoot);

        const queueCard = document.createElement('div');
        queueCard.className = 'mt-3 ' + CARD;
        const queueHead = document.createElement('div');
        queueHead.className = 'text-xs text-gray-500 dark:text-slate-400 mb-2';
        queueHead.textContent = 'Очередь узлов — выберите два и объедините их';
        const queueBody = document.createElement('div');
        queueBody.className = 'flex flex-wrap items-center gap-2';
        const controlRow = document.createElement('div');
        controlRow.className = 'mt-3 flex flex-wrap items-center gap-2';

        const mergeBtn = document.createElement('button');
        mergeBtn.type = 'button';
        mergeBtn.className = BTN_MAIN;
        mergeBtn.textContent = 'Объединить';
        const stepBtn = document.createElement('button');
        stepBtn.type = 'button';
        stepBtn.className = BTN;
        stepBtn.textContent = 'Шаг за меня';
        const allBtn = document.createElement('button');
        allBtn.type = 'button';
        allBtn.className = BTN;
        allBtn.textContent = 'Собрать всё';
        const undoBtn = document.createElement('button');
        undoBtn.type = 'button';
        undoBtn.className = BTN;
        undoBtn.textContent = 'Шаг назад';
        const resetBtn = document.createElement('button');
        resetBtn.type = 'button';
        resetBtn.className = BTN;
        resetBtn.textContent = 'Заново';
        [mergeBtn, stepBtn, allBtn, undoBtn, resetBtn].forEach(function (b) {
            controlRow.appendChild(b);
        });

        const statusBox = document.createElement('div');
        statusBox.className = 'mt-3';

        queueCard.appendChild(queueHead);
        queueCard.appendChild(queueBody);
        queueCard.appendChild(controlRow);
        queueCard.appendChild(statusBox);

        const treeCard = document.createElement('div');
        treeCard.className = 'mt-3 ' + CARD;
        const treeCap = document.createElement('div');
        treeCap.className = 'text-xs text-gray-500 dark:text-slate-400 mb-1 text-center';
        treeCap.textContent = 'Дерево растёт снизу вверх: шаг влево — 0, шаг вправо — 1. ' +
            'В кружках — частоты, символы всегда остаются в листьях.';
        const treeHost = document.createElement('div');
        treeHost.className = 'overflow-x-auto';
        treeCard.appendChild(treeCap);
        treeCard.appendChild(treeHost);

        const resultCard = document.createElement('div');
        resultCard.className = 'mt-3 ' + CARD;

        body.appendChild(presetRow);
        body.appendChild(editorCard);
        body.appendChild(queueCard);
        body.appendChild(treeCard);
        body.appendChild(resultCard);

        // ── редактор частот ──────────────────────────────────────
        function renderEditor() {
            editorBody.innerHTML = '';
            editorFoot.innerHTML = '';

            leaves.forEach(function (lf, i) {
                const chip = document.createElement('span');
                chip.className = 'inline-flex items-center gap-1.5 rounded-md border px-2 py-1 ' +
                    TONE[i % TONE.length];

                const name = document.createElement('span');
                name.className = 'text-sm font-semibold';
                name.textContent = lf.sym;

                const input = document.createElement('input');
                input.type = 'number';
                input.min = '1';
                input.max = String(MAX_FREQ);
                input.value = String(lf.freq);
                input.className = INPUT + ' w-16';
                input.addEventListener('input', function () {
                    const v = parseInt(input.value, 10);
                    if (!(v >= 1) || v > MAX_FREQ) return;
                    leaves[i].freq = v;
                    sourceText = '';
                    activePreset = matchingPreset();
                    resetBuild();
                    refresh();
                });

                chip.appendChild(name);
                chip.appendChild(input);

                if (leaves.length > 2) {
                    const del = document.createElement('button');
                    del.type = 'button';
                    del.className = 'px-1 text-gray-400 hover:text-red-500 dark:text-slate-400';
                    del.textContent = '×';
                    del.title = 'Убрать символ';
                    del.addEventListener('click', function () {
                        leaves.splice(i, 1);
                        sourceText = '';
                        activePreset = matchingPreset();
                        resetBuild();
                        renderEditor();
                        refresh();
                    });
                    chip.appendChild(del);
                }

                editorBody.appendChild(chip);
            });

            if (leaves.length < MAX_SYMBOLS) {
                const add = document.createElement('button');
                add.type = 'button';
                add.className = CHIP;
                add.textContent = '+ добавить символ';
                add.addEventListener('click', function () {
                    const used = leaves.map(function (l) { return l.sym; });
                    const letter = LETTERS.filter(function (l) { return used.indexOf(l) < 0; })[0] ||
                        ('С' + (leaves.length + 1));
                    leaves.push({ sym: letter, freq: 1 });
                    sourceText = '';
                    activePreset = matchingPreset();
                    resetBuild();
                    renderEditor();
                    refresh();
                });
                editorFoot.appendChild(add);
            }

            const cap = document.createElement('span');
            cap.className = 'text-xs text-gray-500 dark:text-slate-400 ml-1';
            cap.textContent = 'или посчитать по тексту:';
            const textInput = document.createElement('input');
            textInput.type = 'text';
            textInput.maxLength = MAX_TEXT;
            textInput.value = sourceText;
            textInput.className = INPUT + ' w-44';
            const countBtn = document.createElement('button');
            countBtn.type = 'button';
            countBtn.className = CHIP;
            countBtn.textContent = 'Посчитать';
            countBtn.addEventListener('click', function () {
                const f = countText(textInput.value);
                if (f.length < 2) {
                    statusBox.innerHTML = '<p class="text-sm text-red-600 dark:text-red-300">' +
                        'В тексте должно быть хотя бы два разных символа.</p>';
                    return;
                }
                leaves = f;
                sourceText = String(textInput.value).replace(/\s+/g, '').slice(0, MAX_TEXT);
                activePreset = matchingPreset();
                resetBuild();
                renderEditor();
                refresh();
            });
            editorFoot.appendChild(cap);
            editorFoot.appendChild(textInput);
            editorFoot.appendChild(countBtn);
        }

        // ── очередь узлов ────────────────────────────────────────
        function toggleSelect(node) {
            const at = selected.indexOf(node);
            if (at >= 0) selected.splice(at, 1);
            else {
                selected.push(node);
                if (selected.length > 2) selected.shift();
            }
            refresh();
        }

        function renderQueue() {
            queueBody.innerHTML = '';
            const q = queueOrder();
            if (q.length === 1) {
                const done = document.createElement('span');
                done.className = 'text-sm text-gray-600 dark:text-slate-300';
                done.textContent = 'Остался один узел — это корень дерева, сборка закончена.';
                queueBody.appendChild(done);
                return;
            }
            q.forEach(function (n) {
                const btn = document.createElement('button');
                btn.type = 'button';
                const tone = n.sym !== null
                    ? TONE[n.idx % TONE.length]
                    : 'bg-white border-gray-300 text-gray-700 dark:bg-slate-700 dark:border-slate-500 dark:text-slate-200';
                btn.className = 'inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-sm ' +
                    'transition-colors ' + tone +
                    (selected.indexOf(n) >= 0 ? ' ring-2 ring-brand-500 dark:ring-cyan-400' : '');
                btn.innerHTML = '<span class="font-semibold">' +
                    escapeHtml(n.sym !== null ? n.sym : '[' + labelOf(n) + ']') +
                    '</span><span class="font-mono text-xs opacity-70">' + n.w + '</span>';
                btn.addEventListener('click', function () { toggleSelect(n); });
                queueBody.appendChild(btn);
            });
        }

        // ── дерево ───────────────────────────────────────────────
        function svgEl(name, attrs) {
            const node = document.createElementNS(SVG_NS, name);
            Object.keys(attrs || {}).forEach(function (k) {
                node.setAttribute(k, attrs[k]);
            });
            return node;
        }

        function renderTree(host) {
            host.innerHTML = '';
            const roots = queueOrder();
            // Геометрия, размеры плашек и палитра – те же, что у дерева
            // в виджете fano-code: два дерева стоят в одном уроке рядом.
            const STEP = 78;
            const ROW = 58;

            let cursor = 0;
            let maxDepth = 0;
            roots.forEach(function (root, ri) {
                (function layout(n, depth) {
                    n.depth = depth;
                    if (n.sym !== null) {
                        n.x = 40 + cursor * STEP;
                        cursor++;
                    } else {
                        layout(n.left, depth + 1);
                        layout(n.right, depth + 1);
                        n.x = (n.left.x + n.right.x) / 2;
                    }
                    n.y = 28 + depth * ROW;
                    if (depth > maxDepth) maxDepth = depth;
                })(root, 0);
                if (ri < roots.length - 1) cursor += 0.55;   // зазор между деревьями
            });

            const width = Math.max(240, 80 + (cursor - 1) * STEP);
            const height = 28 + maxDepth * ROW + 52;
            const svg = svgEl('svg', {
                width: width, height: height,
                viewBox: '0 0 ' + width + ' ' + height,
                class: 'mx-auto block'
            });

            roots.forEach(function (root) {
                (function edges(n) {
                    if (n.sym !== null) return;
                    [[n.left, '0'], [n.right, '1']].forEach(function (pair) {
                        const kid = pair[0];
                        svg.appendChild(svgEl('line', {
                            x1: n.x, y1: n.y + 12, x2: kid.x, y2: kid.y - 14,
                            class: 'stroke-gray-300 dark:stroke-slate-600',
                            'stroke-width': 2
                        }));
                        // Метку отводим по нормали к ребру, а не просто влево/вправо:
                        // на крутых рёбрах горизонтальный сдвиг кладёт цифру на саму линию.
                        const dx = kid.x - n.x;
                        const dy = kid.y - n.y;
                        const len = Math.sqrt(dx * dx + dy * dy) || 1;
                        const off = 13;
                        const label = svgEl('text', {
                            x: (n.x + kid.x) / 2 + (pair[1] === '0' ? -dy : dy) / len * off,
                            y: (n.y + kid.y) / 2 + (pair[1] === '0' ? dx : -dx) / len * off + 4,
                            'text-anchor': 'middle',
                            class: 'fill-gray-400 dark:fill-slate-500',
                            'font-size': 12, 'font-family': 'monospace'
                        });
                        label.textContent = pair[1];
                        svg.appendChild(label);
                        edges(kid);
                    });
                })(root);
            });

            roots.forEach(function (root) {
                (function draw(n, isRoot) {
                    const g = svgEl('g', {});
                    if (isRoot && roots.length > 1) {
                        g.setAttribute('class', 'cursor-pointer');
                        g.addEventListener('click', function () { toggleSelect(n); });
                    }

                    if (n.sym !== null) {
                        const w = Math.max(30, String(n.sym).length * 9 + 12);
                        g.appendChild(svgEl('rect', {
                            x: n.x - w / 2, y: n.y - 14, width: w, height: 28, rx: 8,
                            class: SVG_TONE[n.idx % SVG_TONE.length],
                            'stroke-width': selected.indexOf(n) >= 0 ? 3 : 1.5
                        }));
                        const t = svgEl('text', {
                            x: n.x, y: n.y + 5, 'text-anchor': 'middle',
                            class: 'fill-gray-800 dark:fill-slate-100',
                            'font-size': 13, 'font-weight': 600
                        });
                        t.textContent = n.sym;
                        g.appendChild(t);
                        const cap = svgEl('text', {
                            x: n.x, y: n.y + 30, 'text-anchor': 'middle',
                            class: 'fill-gray-500 dark:fill-slate-400',
                            'font-size': 11, 'font-family': 'monospace'
                        });
                        cap.textContent = String(n.w);
                        g.appendChild(cap);
                    } else {
                        // Обводка серая, как у fano-code; выделенный узел берёт
                        // цвет кольца из очереди – иначе на сером фоне его не видно.
                        const picked = selected.indexOf(n) >= 0;
                        g.appendChild(svgEl('circle', {
                            cx: n.x, cy: n.y, r: 14,
                            class: picked
                                ? 'fill-gray-200 stroke-brand-500 dark:fill-slate-600 dark:stroke-cyan-400'
                                : 'fill-gray-200 stroke-gray-300 dark:fill-slate-600 dark:stroke-slate-500',
                            'stroke-width': picked ? 3 : 1.5
                        }));
                        const t = svgEl('text', {
                            x: n.x, y: n.y + 4, 'text-anchor': 'middle',
                            class: 'fill-gray-700 dark:fill-slate-100',
                            'font-size': 12, 'font-family': 'monospace'
                        });
                        t.textContent = String(n.w);
                        g.appendChild(t);
                    }

                    svg.appendChild(g);
                    if (n.sym === null) { draw(n.left, false); draw(n.right, false); }
                })(root, true);
            });

            host.appendChild(svg);
        }

        // ── статус сборки ────────────────────────────────────────
        function renderStatus() {
            statusBox.innerHTML = '';
            const left = nodes.length;
            const line = document.createElement('div');
            line.className = 'text-sm text-gray-700 dark:text-slate-200';

            if (left > 1) {
                const total = leaves.length - 1;
                line.textContent = 'Шаг ' + (steps.length + 1) + ' из ' + total + '. ' +
                    (selected.length === 2
                        ? 'Пара выбрана — жмите «Объединить».'
                        : 'Выберите два узла с наименьшими частотами.');
            } else {
                line.textContent = 'Дерево собрано за ' + steps.length + ' ' +
                    plural(steps.length, 'шаг', 'шага', 'шагов') + '.';
            }
            statusBox.appendChild(line);

            const last = steps[steps.length - 1];
            if (last && !last.ok) {
                const warn = document.createElement('div');
                warn.className = 'mt-1 text-xs text-amber-700 dark:text-amber-300';
                warn.textContent = 'На прошлом шаге объединены узлы с частотами ' +
                    last.left.w + ' и ' + last.right.w + ', а самые лёгкие были другими. ' +
                    'Запрещать не будем — доведите сборку до конца и посмотрите на итог.';
                statusBox.appendChild(warn);
            }
        }

        // ── итог: коды и выигрыш ─────────────────────────────────
        function renderResult() {
            resultCard.innerHTML = '';

            if (nodes.length > 1) {
                resultCard.innerHTML = '<p class="text-sm text-gray-500 dark:text-slate-400">' +
                    'Когда останется один узел, здесь появятся коды символов и подсчёт выигрыша.</p>';
                return;
            }

            const root = nodes[0];
            const codes = collectCodes(root);
            const bits = costOf(root);
            const best = optimalCost();
            const freq = totalFreq();
            const ub = uniformBits();
            const uniform = freq * ub;

            const head = document.createElement('div');
            head.className = 'flex items-center gap-2 mb-2';
            const headName = document.createElement('span');
            headName.className = 'text-sm font-semibold text-gray-700 dark:text-slate-200';
            headName.textContent = 'Коды, снятые с дерева';
            const badge = document.createElement('span');
            const optimal = bits <= best;
            badge.className = optimal ? OK_BADGE : BAD_BADGE;
            badge.textContent = optimal ? 'минимум достигнут' : 'можно короче';
            head.appendChild(headName);
            head.appendChild(badge);
            resultCard.appendChild(head);

            const table = document.createElement('div');
            table.className = 'overflow-x-auto';
            let html = '<table class="w-full text-sm"><thead><tr class="text-xs text-gray-500 dark:text-slate-400">' +
                '<th class="text-left font-normal py-1">Символ</th>' +
                '<th class="text-left font-normal py-1">Частота</th>' +
                '<th class="text-left font-normal py-1">Код</th>' +
                '<th class="text-left font-normal py-1">Длина</th>' +
                '<th class="text-left font-normal py-1">Битов</th></tr></thead><tbody>';
            leaves.forEach(function (lf, i) {
                const code = codes[lf.sym] || '';
                html += '<tr class="border-t border-gray-200 dark:border-slate-600">' +
                    '<td class="py-1"><span class="inline-flex items-center justify-center rounded-md border px-2 ' +
                    TONE[i % TONE.length] + '">' + escapeHtml(lf.sym) + '</span></td>' +
                    '<td class="py-1 font-mono">' + lf.freq + '</td>' +
                    '<td class="py-1 font-mono">' + escapeHtml(code) + '</td>' +
                    '<td class="py-1 font-mono">' + code.length + '</td>' +
                    '<td class="py-1 font-mono">' + (lf.freq * code.length) + '</td></tr>';
            });
            html += '</tbody></table>';
            table.innerHTML = html;
            resultCard.appendChild(table);

            const sum = document.createElement('div');
            sum.className = 'mt-2 text-sm text-gray-700 dark:text-slate-200';
            sum.innerHTML = 'Всего <b>' + bits + '</b> ' + plural(bits, 'бит', 'бита', 'битов') +
                ' против <b>' + uniform + '</b> у равномерного кода (' + ub + ' ' +
                plural(ub, 'бит', 'бита', 'битов') + ' на символ). ' +
                'Средняя длина $L = ' + mfmt(bits / freq) + '$ бита на символ, ' +
                'коэффициент сжатия $k = ' + mfmt(uniform / bits) + '$.';
            resultCard.appendChild(sum);

            const note = document.createElement('div');
            note.className = 'mt-1 text-xs';
            const strayed = steps.some(function (s) { return !s.ok; });
            if (bits > best) {
                note.className += ' text-amber-700 dark:text-amber-300';
                note.textContent = 'Оптимум для этих частот — ' + best + ' ' +
                    plural(best, 'бит', 'бита', 'битов') + ', у вас получилось ' + bits +
                    '. Значит, где-то объединялись не самые лёгкие узлы. Нажмите «Заново» ' +
                    'и попробуйте строго по правилу.';
            } else if (strayed) {
                note.className += ' text-gray-500 dark:text-slate-400';
                note.textContent = 'Любопытно: вы отступали от правила, но суммарная длина всё равно ' +
                    'вышла минимальной. Так бывает при равных частотах — деревьев несколько, ' +
                    'а длина у них одна.';
            } else {
                note.className += ' text-gray-500 dark:text-slate-400';
                note.textContent = 'Это минимально возможная длина для таких частот: короче ' +
                    'не сумеет ни один префиксный код, назначающий каждому символу своё кодовое слово.';
            }
            resultCard.appendChild(note);
        }

        // ── общий пересчёт ───────────────────────────────────────
        function refresh() {
            presetBtns.forEach(function (btn, index) {
                btn.className = index === activePreset ? CHIP_ON : CHIP;
            });
            mergeBtn.disabled = selected.length !== 2;
            stepBtn.disabled = nodes.length < 2;
            allBtn.disabled = nodes.length < 2;
            undoBtn.disabled = history.length === 0;
            renderQueue();
            renderStatus();
            renderTree(treeHost);
            renderResult();
        }

        mergeBtn.addEventListener('click', function () {
            if (selected.length === 2) {
                merge(selected[0], selected[1]);
                refresh();
            }
        });
        stepBtn.addEventListener('click', function () {
            autoStep();
            refresh();
        });
        allBtn.addEventListener('click', function () {
            let guard = MAX_SYMBOLS + 2;
            while (nodes.length > 1 && guard-- > 0) autoStep();
            refresh();
        });
        undoBtn.addEventListener('click', function () {
            const prev = history.pop();
            if (!prev) return;
            nodes = prev.nodes;
            steps = prev.steps;
            selected = [];
            refresh();
        });
        resetBtn.addEventListener('click', function () {
            resetBuild();
            refresh();
        });

        resetBuild();
        renderEditor();
        refresh();
    });

    // ─────────────────────────────────────────────────────────────
    // Виджет: sampling-wave — оцифровка синусоиды.
    // Показывает обе операции сразу: дискретизацию по времени (сетка
    // отсчётов) и квантование по уровню (сетка уровней). Видно, что
    // именно теряется: между отсчётами о сигнале не остаётся ничего, а
    // каждый отсчёт «прилипает» к ближайшему уровню — красный отрезок и
    // есть ошибка квантования.
    // Окно всегда 1 секунда, поэтому «частота сигнала» — это число
    // колебаний в окне, а «частота дискретизации» — число отсчётов.
    // Третья линия — восстановленная волна: честная периодическая
    // sinc-интерполяция по отсчётам (то, что делает сглаживающий фильтр на
    // выходе ЦАП). Без неё виджет вводил в заблуждение: ступеньки на
    // исходную волну не похожи даже тогда, когда условие Котельникова
    // выполнено, — теорема обещает восстановление фильтром, а не забором из
    // ступенек. При нехватке отсчётов та же линия показывает наложение
    // частот: она проходит ровно через те же точки, но частота у неё другая.
    // Наведение (или клик) на отсчёт раскрывает его арифметику: момент
    // времени, истинное значение, номер уровня, записанное значение и
    // ошибку.
    // Конфиг: { "signal": 3, "rate": 16, "bits": 3, "quant": true,
    //           "steps": true, "restored": true,
    //           "presets": [{"title": "…", "signal": 10, "rate": 12,
    //                        "bits": 4}] }
    // signal 1–12 Гц, rate 2–48 Гц, bits 1–5 (уровней 2^bits).
    // ─────────────────────────────────────────────────────────────
    register('sampling-wave', function (el, config) {
        const SVG_NS = 'http://www.w3.org/2000/svg';
        const SIG_MIN = 1, SIG_MAX = 12;
        const RATE_MIN = 2, RATE_MAX = 48;
        const BITS_MIN = 1, BITS_MAX = 5;   // 6 битов — 64 линии, в сетку уже не влезает

        function clampInt(raw, lo, hi, fallback) {
            const n = parseInt(raw, 10);
            if (isNaN(n)) return fallback;
            return Math.min(Math.max(n, lo), hi);
        }

        let signal = clampInt(config.signal, SIG_MIN, SIG_MAX, 3);
        let rate = clampInt(config.rate, RATE_MIN, RATE_MAX, 16);
        let bits = clampInt(config.bits, BITS_MIN, BITS_MAX, 3);
        let showQuant = config.quant !== false;
        let showSteps = config.steps !== false;
        let showRestored = config.restored !== false && config.alias !== false;
        let selected = -1;

        const presets = (Array.isArray(config.presets) ? config.presets : [])
            .filter(function (p) { return p && p.title; })
            .slice(0, 6);

        const chip = 'px-2.5 py-1 rounded-full text-xs border transition-colors bg-gray-50 text-gray-500 border-gray-200 hover:bg-gray-100 dark:bg-slate-700 dark:border-slate-600 dark:text-slate-300';
        const chipActive = 'px-2.5 py-1 rounded-full text-xs border transition-colors bg-brand-600 text-white border-brand-600 dark:bg-cyan-500 dark:border-cyan-500';

        function svgEl(name, attrs) {
            const node = document.createElementNS(SVG_NS, name);
            Object.keys(attrs || {}).forEach(function (k) {
                node.setAttribute(k, attrs[k]);
            });
            return node;
        }

        function fmt(x, digits) {
            return x.toFixed(digits).replace('.', ',').replace('-', '−');
        }

        function bitWord(n) {
            const d10 = n % 10, d100 = n % 100;
            if (d10 === 1 && d100 !== 11) return 'бит';
            if (d10 >= 2 && d10 <= 4 && (d100 < 12 || d100 > 14)) return 'бита';
            return 'битов';
        }

        // ── арифметика оцифровки ─────────────────────────────────
        function levelCount() { return 1 << bits; }

        function levelIndex(v) {
            const last = levelCount() - 1;
            return Math.min(Math.max(Math.round((v + 1) / 2 * last), 0), last);
        }

        function levelValue(idx) {
            return idx / (levelCount() - 1) * 2 - 1;
        }

        function wave(t) {
            return Math.sin(2 * Math.PI * signal * t);
        }

        // Частота, которую на самом деле запишут отсчёты: sin(2πFt) в точках
        // t = k/rate совпадает с sin(2πdt), где d = F − m·rate. При d < 0
        // волна просто перевёрнута, поэтому знак сохраняем.
        function aliasShift() {
            return signal - Math.round(signal / rate) * rate;
        }

        function samples() {
            const out = [];
            for (let k = 0; k < rate; k++) {
                const t = k / rate;
                const v = wave(t);
                const idx = levelIndex(v);
                out.push({ k: k, t: t, v: v, idx: idx, q: levelValue(idx) });
            }
            return out;
        }

        // Восстановление сигнала по отсчётам — то, что делает сглаживающий
        // фильтр на выходе ЦАП. Ступеньки к этому отношения не имеют: они
        // лишь показывают, что лежит в памяти. Здесь честная периодическая
        // sinc-интерполяция (ядро Дирихле): окно ровно 1 секунда, отсчёты
        // равномерны, поэтому кривая проходит точно через них, а между ними
        // идёт настолько плавно, насколько это вообще возможно.
        function restore(pts, t) {
            const n = pts.length;
            let sum = 0;
            for (let i = 0; i < n; i++) {
                const x = t - pts[i].t;
                const s = Math.sin(Math.PI * x);
                let kernel;
                if (Math.abs(s) < 1e-9) {
                    kernel = 1;                                  // сам отсчёт
                } else if (n % 2 === 0) {
                    kernel = Math.sin(Math.PI * n * x) / Math.tan(Math.PI * x) / n;
                } else {
                    kernel = Math.sin(Math.PI * n * x) / s / n;
                }
                sum += (showQuant ? pts[i].q : pts[i].v) * kernel;
            }
            return sum;
        }

        // ── геометрия ────────────────────────────────────────────
        const W = 760, H = 336;
        const X0 = 58, X1 = 744, YT = 18, YB = 280;
        const MID = (YT + YB) / 2, AMP = (YB - YT) / 2;

        function px(t) { return X0 + t * (X1 - X0); }
        function py(v) { return MID - v * AMP; }

        // ── разметка ─────────────────────────────────────────────
        const body = widgetFrame(el, el.dataset.title);

        const presetRow = document.createElement('div');
        presetRow.className = 'flex flex-wrap items-center gap-2 justify-center mb-4';
        const presetBtns = presets.map(function (p) {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.textContent = p.title;
            btn.className = chip;
            btn.addEventListener('click', function () {
                signal = clampInt(p.signal, SIG_MIN, SIG_MAX, signal);
                rate = clampInt(p.rate, RATE_MIN, RATE_MAX, rate);
                bits = clampInt(p.bits, BITS_MIN, BITS_MAX, bits);
                if (p.quant !== undefined) showQuant = p.quant !== false;
                selected = -1;
                render();
            });
            presetRow.appendChild(btn);
            return btn;
        });

        function slider(labelText, lo, hi, get, set) {
            const row = document.createElement('div');
            row.className = 'flex items-center gap-3';
            const label = document.createElement('span');
            label.className = 'text-xs text-gray-500 dark:text-slate-400 w-44 shrink-0';
            label.textContent = labelText;
            const input = document.createElement('input');
            input.type = 'range';
            input.min = String(lo);
            input.max = String(hi);
            input.step = '1';
            input.className = 'flex-1 accent-brand-600 dark:accent-cyan-500';
            input.setAttribute('aria-label', labelText);
            input.addEventListener('input', function () {
                set(clampInt(input.value, lo, hi, get()));
                selected = -1;
                render();
            });
            const value = document.createElement('b');
            value.className = 'text-sm font-mono text-gray-900 dark:text-white w-28 text-right shrink-0';
            row.appendChild(label);
            row.appendChild(input);
            row.appendChild(value);
            row._refresh = function (text) {
                input.value = String(get());
                value.textContent = text;
            };
            return row;
        }

        const signalRow = slider('Частота сигнала', SIG_MIN, SIG_MAX,
            function () { return signal; }, function (v) { signal = v; });
        const rateRow = slider('Частота дискретизации', RATE_MIN, RATE_MAX,
            function () { return rate; }, function (v) { rate = v; });
        const bitsRow = slider('Разрядность', BITS_MIN, BITS_MAX,
            function () { return bits; }, function (v) { bits = v; });

        const sliders = document.createElement('div');
        sliders.className = 'flex flex-col gap-2 mb-4';
        sliders.appendChild(signalRow);
        sliders.appendChild(rateRow);
        sliders.appendChild(bitsRow);

        function toggle(labelText, get, set) {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.textContent = labelText;
            btn.addEventListener('click', function () {
                set(!get());
                selected = -1;
                render();
            });
            btn._refresh = function () {
                btn.className = get() ? chipActive : chip;
            };
            return btn;
        }

        const quantBtn = toggle('Квантование по уровню',
            function () { return showQuant; }, function (v) { showQuant = v; });
        const stepsBtn = toggle('Ступеньки записи',
            function () { return showSteps; }, function (v) { showSteps = v; });
        const restoredBtn = toggle('Восстановленная волна',
            function () { return showRestored; }, function (v) { showRestored = v; });

        const toggleRow = document.createElement('div');
        toggleRow.className = 'flex flex-wrap items-center gap-2 justify-center mb-4';
        toggleRow.appendChild(quantBtn);
        toggleRow.appendChild(stepsBtn);
        toggleRow.appendChild(restoredBtn);

        const plot = document.createElement('div');
        plot.className = 'overflow-x-auto';

        const legend = document.createElement('div');
        legend.className = 'mt-2 text-center text-xs text-gray-400 dark:text-slate-500';
        legend.innerHTML = 'Серая линия — исходный сигнал, синие ступеньки — что лежит в памяти, ' +
            'оранжевая — что даст сглаживающий фильтр из этих отсчётов. ' +
            'Теорема Котельникова обещает именно оранжевую линию, а не забор из ступенек.';

        const verdict = document.createElement('div');
        verdict.className = 'mt-3 flex flex-wrap items-center gap-2 justify-center text-sm';

        const stats = document.createElement('div');
        stats.className = 'mt-3 text-center text-sm text-gray-600 dark:text-slate-300';

        const note = document.createElement('div');
        note.className = 'mt-3 rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-sm text-gray-600 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-300 min-h-[2.75rem]';

        if (presets.length) body.appendChild(presetRow);
        body.appendChild(sliders);
        body.appendChild(toggleRow);
        body.appendChild(plot);
        body.appendChild(legend);
        body.appendChild(verdict);
        body.appendChild(stats);
        body.appendChild(note);

        // ── отрисовка ────────────────────────────────────────────
        function drawPlot(pts) {
            plot.innerHTML = '';
            const svg = svgEl('svg', {
                viewBox: '0 0 ' + W + ' ' + H,
                width: W, height: H,
                class: 'block mx-auto w-full h-auto min-w-[680px]'
            });

            // сетка уровней квантования
            const L = levelCount();
            if (showQuant) {
                for (let i = 0; i < L; i++) {
                    const y = py(levelValue(i));
                    svg.appendChild(svgEl('line', {
                        x1: X0, y1: y, x2: X1, y2: y,
                        class: 'stroke-gray-200 dark:stroke-slate-700',
                        'stroke-width': 1
                    }));
                    if (L <= 8) {
                        const cap = svgEl('text', {
                            x: X0 - 10, y: y + 4, 'text-anchor': 'end',
                            class: 'fill-gray-400 dark:fill-slate-500',
                            'font-size': 11, 'font-family': 'monospace'
                        });
                        cap.textContent = i;
                        svg.appendChild(cap);
                    }
                }
            }

            // ось времени
            svg.appendChild(svgEl('line', {
                x1: X0, y1: MID, x2: X1, y2: MID,
                class: 'stroke-gray-300 dark:stroke-slate-600',
                'stroke-width': 1
            }));

            // моменты отсчётов
            pts.forEach(function (p) {
                svg.appendChild(svgEl('line', {
                    x1: px(p.t), y1: YT, x2: px(p.t), y2: YB,
                    class: p.k === selected
                        ? 'stroke-brand-500 dark:stroke-cyan-400'
                        : 'stroke-gray-200 dark:stroke-slate-700',
                    'stroke-width': p.k === selected ? 1.5 : 1,
                    'stroke-dasharray': '3 4'
                }));
            });

            // ступеньки: то, что реально лежит в памяти
            if (showSteps) {
                const d = [];
                pts.forEach(function (p, i) {
                    const y = py(showQuant ? p.q : p.v);
                    const xa = px(p.t);
                    const xb = i + 1 < pts.length ? px(pts[i + 1].t) : X1;
                    d.push((i === 0 ? 'M' : 'L') + xa + ' ' + y);
                    d.push('L' + xb + ' ' + y);
                });
                svg.appendChild(svgEl('path', {
                    d: d.join(' '), fill: 'none',
                    class: 'stroke-brand-500/60 dark:stroke-cyan-400/60',
                    'stroke-width': 2
                }));
            }

            // исходная волна
            const curve = [];
            for (let i = 0; i <= 600; i++) {
                const t = i / 600;
                curve.push((i ? 'L' : 'M') + fmtNum(px(t)) + ' ' + fmtNum(py(wave(t))));
            }
            svg.appendChild(svgEl('path', {
                d: curve.join(' '), fill: 'none',
                class: 'stroke-gray-300 dark:stroke-slate-600',
                'stroke-width': 2
            }));

            // волна, которую даст фильтр из этих отсчётов
            if (showRestored) {
                const restored = [];
                for (let i = 0; i <= 400; i++) {
                    const t = i / 400;
                    restored.push((i ? 'L' : 'M') + fmtNum(px(t)) + ' ' +
                        fmtNum(py(restore(pts, t))));
                }
                svg.appendChild(svgEl('path', {
                    d: restored.join(' '), fill: 'none',
                    class: 'stroke-amber-500 dark:stroke-amber-400',
                    'stroke-width': 2.5,
                    'stroke-dasharray': '7 5'
                }));
            }

            // ошибка квантования, точки отсчётов и зоны наведения
            pts.forEach(function (p) {
                const x = px(p.t);
                const yTrue = py(p.v);
                const yQ = py(showQuant ? p.q : p.v);

                if (showQuant && Math.abs(yTrue - yQ) > 0.5) {
                    svg.appendChild(svgEl('line', {
                        x1: x, y1: yTrue, x2: x, y2: yQ,
                        class: 'stroke-red-400 dark:stroke-red-400',
                        'stroke-width': 2
                    }));
                    svg.appendChild(svgEl('circle', {
                        cx: x, cy: yTrue, r: 3,
                        class: 'fill-transparent stroke-gray-400 dark:stroke-slate-400',
                        'stroke-width': 1.5
                    }));
                }

                svg.appendChild(svgEl('circle', {
                    cx: x, cy: yQ, r: p.k === selected ? 6 : 4,
                    class: 'fill-brand-600 stroke-brand-600 dark:fill-cyan-400 dark:stroke-cyan-400',
                    'stroke-width': 1
                }));

                const hit = svgEl('circle', {
                    cx: x, cy: yQ, r: 11,
                    class: 'fill-transparent cursor-pointer'
                });
                hit.addEventListener('mouseenter', function () {
                    selected = p.k;
                    render();
                });
                hit.addEventListener('click', function () {
                    selected = p.k;
                    render();
                });
                svg.appendChild(hit);
            });

            // разметка времени
            [0, 0.5, 1].forEach(function (t) {
                const cap = svgEl('text', {
                    x: px(t), y: YB + 26, 'text-anchor': 'middle',
                    class: 'fill-gray-400 dark:fill-slate-500', 'font-size': 11
                });
                cap.textContent = t === 1 ? '1 с' : fmt(t, t === 0 ? 0 : 1) + ' с';
                svg.appendChild(cap);
            });

            plot.appendChild(svg);
        }

        function fmtNum(x) {
            return Math.round(x * 100) / 100;
        }

        // Число для формулы: разряды разделяет \, – обычный пробел внутри $…$
        // MathJax проглотит, и 1 411 200 склеится в 1411200.
        function mnum(n) {
            return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, '\\,');
        }

        function render() {
            const pts = samples();
            const L = levelCount();
            const shift = aliasShift();
            const aliased = rate < 2 * signal;
            const silent = pts.every(function (p) { return Math.abs(p.v) < 1e-9; });

            drawPlot(pts);

            signalRow._refresh(signal + ' Гц');
            rateRow._refresh(rate + ' Гц');
            bitsRow._refresh(bits + ' ' + bitWord(bits));
            [quantBtn, stepsBtn, restoredBtn].forEach(function (b) { b._refresh(); });
            presetBtns.forEach(function (b) { b.className = chip; });

            verdict.innerHTML = '';
            const badge = document.createElement('span');
            badge.className = 'px-2.5 py-1 rounded-md text-xs font-semibold border ' +
                (aliased
                    ? 'bg-red-50 border-red-300 text-red-700 dark:bg-red-900/30 dark:border-red-700 dark:text-red-200'
                    : 'bg-emerald-50 border-emerald-300 text-emerald-700 dark:bg-emerald-900/30 dark:border-emerald-700 dark:text-emerald-200');
            badge.textContent = aliased
                ? 'Котельников нарушен: $' + rate + ' < 2 \\cdot ' + signal + '$'
                : 'Котельников выполнен: $' + rate + ' \\ge 2 \\cdot ' + signal + '$';
            verdict.appendChild(badge);

            const verdictText = document.createElement('span');
            verdictText.className = 'text-gray-600 dark:text-slate-300';
            if (aliased && Math.abs(shift) < 1e-9) {
                verdictText.textContent = 'все отсчёты попали в одну фазу — записалась тишина.';
            } else if (aliased) {
                verdictText.textContent = 'сигнал ' + signal + ' Гц восстановится как ' +
                    Math.abs(shift) + ' Гц: оранжевая волна проходит ровно через те же отсчёты, ' +
                    'что и серая, но частота у неё уже другая.';
            } else if (silent) {
                verdictText.textContent = 'ровно на границе: отсчёты попали в нули волны, ' +
                    'и амплитуда потерялась — поэтому на практике частоту берут с запасом.';
            } else if (showQuant) {
                verdictText.textContent = 'оранжевая волна повторяет серую с точностью до ошибки ' +
                    'квантования: форма восстановилась, а мелкая рябь — это те самые ' +
                    'потерянные на ступеньках доли.';
            } else {
                verdictText.textContent = 'оранжевая волна в точности легла на серую: ' +
                    'по этим отсчётам сигнал восстанавливается без потерь.';
            }
            verdict.appendChild(verdictText);

            const perSecond = rate * bits;
            // Формулы – в том же виде, что и в тексте урока: LaTeX, который
            // наберёт MathJax после перерисовки виджета.
            stats.innerHTML = 'Отсчётов за секунду: <b class="text-gray-900 dark:text-white">$' + rate +
                '$</b> · уровней: <b class="text-gray-900 dark:text-white">$2^{' + bits + '} = ' + mnum(L) +
                '$</b> · поток: <b class="text-gray-900 dark:text-white">$' + rate + ' \\times ' + bits + ' = ' +
                mnum(perSecond) + '$</b> битов в секунду' +
                '<div class="text-xs text-gray-400 dark:text-slate-500 mt-1">' +
                'для сравнения, аудио-CD: $44\\,100 \\times 16 \\times 2 = 1\\,411\\,200$ битов в секунду</div>';

            if (selected >= 0 && selected < pts.length) {
                const p = pts[selected];
                let text = 'Отсчёт №' + p.k + ': момент t = ' + fmt(p.t, 3) + ' с, ' +
                    'значение сигнала ' + fmt(p.v, 3) + '.';
                if (showQuant) {
                    text += ' Ближайший уровень — номер ' + p.idx + ' (всего уровней ' + L +
                        ', его значение ' + fmt(p.q, 3) + '). В память уходит сам номер ' +
                        p.idx + ' — это ' + bits + ' ' + bitWord(bits) +
                        '. Ошибка квантования: ' + fmt(Math.abs(p.v - p.q), 3) + '.';
                } else {
                    text += ' Квантование выключено — значение записано точно, ' +
                        'но битов на такую запись нужно бесконечно много.';
                }
                note.textContent = text;
            } else {
                note.textContent = 'Наведите на отсчёт — покажу, что именно уходит в память: ' +
                    'момент времени, истинное значение, номер уровня и ошибку квантования.';
            }
        }

        render();
    });

    // ─────────────────────────────────────────────────────────────
    // Виджет: color-hex — цвет пикселя и его шестнадцатеричный код.
    // Три канала RGB ползунками, крупная плашка цвета с кодом #RRGGBB,
    // палитра готовых цветов и разбор кода по парам цифр. Под каждым
    // ползунком — полоса-градиент: во что превращается цвет, если гнать
    // именно этот канал от 0 до 255. Тумблер «показать биты» раскрывает
    // 8 битов канала (кликабельны) — связка «24 бита = 3 байта = 6
    // шестнадцатеричных цифр». Восьмеричной записи здесь нет намеренно:
    // цвет режется по байтам, а байт — это ровно две цифры основания 16.
    // Конфиг: { "value": "#FF8800", "bits": false,
    //           "palette": [["Оранжевый", "#FF8800"], …] }
    // ─────────────────────────────────────────────────────────────
    register('color-hex', function (el, config) {
        const CHANNELS = [
            { key: 'r', title: 'Красный', accent: 'accent-red-500 dark:accent-red-400' },
            { key: 'g', title: 'Зелёный', accent: 'accent-green-500 dark:accent-green-400' },
            { key: 'b', title: 'Синий', accent: 'accent-blue-500 dark:accent-blue-400' },
        ];

        const DEFAULT_PALETTE = [
            ['Чёрный', '#000000'], ['Белый', '#FFFFFF'],
            ['Красный', '#FF0000'], ['Зелёный', '#00FF00'], ['Синий', '#0000FF'],
            ['Жёлтый', '#FFFF00'], ['Голубой', '#00FFFF'], ['Пурпурный', '#FF00FF'],
            ['Оранжевый', '#FF8800'], ['Розовый', '#FF66CC'],
            ['Серый', '#808080'], ['Тёмно-зелёный', '#166534'],
        ];

        function parseHex(raw, fallback) {
            const m = /^#?([0-9a-fA-F]{6})$/.exec(String(raw || '').trim());
            if (!m) return fallback;
            const n = parseInt(m[1], 16);
            return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
        }

        function pair(v) {
            const s = Math.min(255, Math.max(0, Math.round(v))).toString(16).toUpperCase();
            return s.length < 2 ? '0' + s : s;
        }

        function hexOf(c) { return '#' + pair(c[0]) + pair(c[1]) + pair(c[2]); }
        function cssOf(c) { return 'rgb(' + c[0] + ',' + c[1] + ',' + c[2] + ')'; }

        // Тёмный или светлый текст поверх плашки — по воспринимаемой яркости.
        function isLight(c) {
            return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2] > 150;
        }

        let color = parseHex(config.value, [255, 136, 0]);
        let showBits = config.bits === true;

        const palette = (Array.isArray(config.palette) && config.palette.length
            ? config.palette : DEFAULT_PALETTE)
            .filter(function (p) { return Array.isArray(p) && p.length === 2; })
            .slice(0, 16);

        const chip = 'px-2.5 py-1 rounded-full text-xs border transition-colors bg-gray-50 text-gray-500 border-gray-200 hover:bg-gray-100 dark:bg-slate-700 dark:border-slate-600 dark:text-slate-300';
        const chipActive = 'px-2.5 py-1 rounded-full text-xs border transition-colors bg-brand-600 text-white border-brand-600 dark:bg-cyan-500 dark:border-cyan-500';

        const body = widgetFrame(el, el.dataset.title);

        // ── крупная плашка цвета ─────────────────────────────────
        const swatch = document.createElement('div');
        swatch.className = 'rounded-xl border border-gray-200 dark:border-slate-600 ' +
            'flex flex-col items-center justify-center gap-1 py-8 mb-4 transition-colors';
        const swatchCode = document.createElement('div');
        swatchCode.className = 'text-3xl font-mono font-bold tracking-wider';
        const swatchRgb = document.createElement('div');
        swatchRgb.className = 'text-sm font-mono opacity-80';
        swatch.appendChild(swatchCode);
        swatch.appendChild(swatchRgb);
        body.appendChild(swatch);

        // ── ползунки каналов ─────────────────────────────────────
        const rows = CHANNELS.map(function (ch, i) {
            const wrap = document.createElement('div');
            wrap.className = 'mb-3';

            const line = document.createElement('div');
            line.className = 'flex items-center gap-3';

            const label = document.createElement('span');
            label.className = 'text-xs text-gray-500 dark:text-slate-400 w-20 shrink-0';
            label.textContent = ch.title;

            const input = document.createElement('input');
            input.type = 'range';
            input.min = '0';
            input.max = '255';
            input.step = '1';
            input.className = 'flex-1 ' + ch.accent;
            input.setAttribute('aria-label', ch.title);
            input.addEventListener('input', function () {
                color[i] = Math.min(255, Math.max(0, parseInt(input.value, 10) || 0));
                render();
            });

            const value = document.createElement('b');
            value.className = 'text-sm font-mono text-gray-900 dark:text-white w-24 text-right shrink-0';

            line.appendChild(label);
            line.appendChild(input);
            line.appendChild(value);

            // Полоса-градиент: что делает именно этот канал. Обёрнута в такую
            // же flex-строку с распорками, чтобы точно совпасть по ширине с
            // дорожкой ползунка (иначе съезжает на величину gap).
            function alignedRow(inner, extraClass) {
                const line2 = document.createElement('div');
                line2.className = 'flex items-center gap-3 ' + (extraClass || '');
                const left = document.createElement('span');
                left.className = 'w-20 shrink-0';
                const right = document.createElement('span');
                right.className = 'w-24 shrink-0';
                line2.appendChild(left);
                line2.appendChild(inner);
                line2.appendChild(right);
                return line2;
            }

            const ramp = document.createElement('div');
            ramp.className = 'h-3 rounded flex-1 border border-gray-200 dark:border-slate-600';
            const rampLine = alignedRow(ramp, 'mt-1');

            // 8 битов канала — по кнопке «показать биты»
            const bits = document.createElement('div');
            bits.className = 'flex flex-wrap items-center gap-1 flex-1';
            const bitsRow = alignedRow(bits, 'mt-1.5');
            const bitBtns = [];
            for (let k = 7; k >= 0; k--) {
                const bit = document.createElement('button');
                bit.type = 'button';
                bit.dataset.bit = String(k);
                bit.addEventListener('click', function () {
                    color[i] ^= (1 << k);
                    render();
                });
                bits.appendChild(bit);
                bitBtns.push(bit);
            }
            const bitsHex = document.createElement('span');
            bitsHex.className = 'text-xs font-mono text-gray-500 dark:text-slate-400 ml-1';
            bits.appendChild(bitsHex);

            wrap.appendChild(line);
            wrap.appendChild(rampLine);
            wrap.appendChild(bitsRow);

            wrap._refresh = function () {
                input.value = String(color[i]);
                value.textContent = color[i] + ' = ' + pair(color[i]);
                const lo = color.slice(), hi = color.slice();
                lo[i] = 0; hi[i] = 255;
                ramp.style.background = 'linear-gradient(to right, ' + cssOf(lo) + ', ' + cssOf(hi) + ')';
                bitsRow.style.display = showBits ? '' : 'none';
                if (showBits) {
                    bitBtns.forEach(function (btn) {
                        const k = parseInt(btn.dataset.bit, 10);
                        const on = (color[i] >> k) & 1;
                        btn.textContent = on ? '1' : '0';
                        btn.className = 'w-6 h-6 rounded text-xs font-mono border transition-colors ' +
                            (on
                                ? 'bg-brand-600 text-white border-brand-600 dark:bg-cyan-500 dark:border-cyan-500'
                                : 'bg-gray-50 text-gray-400 border-gray-200 dark:bg-slate-700 dark:border-slate-600 dark:text-slate-400');
                    });
                    bitsHex.textContent = '= ' + color[i] + ' = ' + pair(color[i]) +
                        ' в шестнадцатеричной';
                }
            };
            return wrap;
        });

        const sliders = document.createElement('div');
        sliders.className = 'mb-2';
        rows.forEach(function (r) { sliders.appendChild(r); });
        body.appendChild(sliders);

        const bitsBtn = document.createElement('button');
        bitsBtn.type = 'button';
        bitsBtn.textContent = 'Показать биты канала';
        bitsBtn.addEventListener('click', function () {
            showBits = !showBits;
            render();
        });
        const toggleRow = document.createElement('div');
        toggleRow.className = 'flex flex-wrap items-center gap-2 justify-center mb-4';
        toggleRow.appendChild(bitsBtn);
        body.appendChild(toggleRow);

        // ── палитра готовых цветов ───────────────────────────────
        const paletteGrid = document.createElement('div');
        paletteGrid.className = 'flex flex-wrap justify-center gap-2 mb-4';
        const paletteCells = palette.map(function (p) {
            const rgb = parseHex(p[1], [0, 0, 0]);
            const cell = document.createElement('button');
            cell.type = 'button';
            cell.title = p[0];
            cell.className = 'flex flex-col items-center gap-1 w-20 group';
            const box = document.createElement('span');
            box.className = 'block w-full h-10 rounded-lg border transition-transform group-hover:scale-105';
            box.style.background = cssOf(rgb);
            const code = document.createElement('span');
            code.className = 'text-[11px] font-mono text-gray-500 dark:text-slate-400';
            code.textContent = hexOf(rgb);
            const name = document.createElement('span');
            name.className = 'text-[11px] text-gray-400 dark:text-slate-500 leading-tight';
            name.textContent = p[0];
            cell.appendChild(box);
            cell.appendChild(code);
            cell.appendChild(name);
            cell.addEventListener('click', function () {
                color = rgb.slice();
                render();
            });
            paletteGrid.appendChild(cell);
            return { cell: cell, box: box, rgb: rgb };
        });
        body.appendChild(paletteGrid);

        const note = document.createElement('div');
        note.className = 'rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-sm text-gray-600 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-300';
        body.appendChild(note);

        // ── отрисовка ────────────────────────────────────────────
        function share(v) {
            if (v === 0) return 'его нет совсем';
            if (v === 255) return 'на максимуме';
            if (v < 64) return 'совсем немного';
            if (v < 160) return 'примерно половина';
            return 'почти на максимуме';
        }

        function render() {
            const code = hexOf(color);
            swatch.style.background = cssOf(color);
            const light = isLight(color);
            swatchCode.className = 'text-3xl font-mono font-bold tracking-wider ' +
                (light ? 'text-gray-900' : 'text-white');
            swatchRgb.className = 'text-sm font-mono opacity-80 ' +
                (light ? 'text-gray-900' : 'text-white');
            swatchCode.textContent = code;
            swatchRgb.textContent = 'R ' + color[0] + ' · G ' + color[1] + ' · B ' + color[2];

            rows.forEach(function (r) { r._refresh(); });
            bitsBtn.className = showBits ? chipActive : chip;

            paletteCells.forEach(function (p) {
                const same = p.rgb[0] === color[0] && p.rgb[1] === color[1] && p.rgb[2] === color[2];
                p.box.className = 'block w-full h-10 rounded-lg border transition-transform group-hover:scale-105 ' +
                    (same
                        ? 'border-2 border-brand-600 dark:border-cyan-400'
                        : 'border-gray-200 dark:border-slate-600');
            });

            note.innerHTML = 'Код <b class="font-mono">' + code + '</b> читается парами цифр, ' +
                'по одной паре на канал: ' +
                '<b class="font-mono">' + pair(color[0]) + '</b> — красного (' + color[0] + ', ' +
                share(color[0]) + '), ' +
                '<b class="font-mono">' + pair(color[1]) + '</b> — зелёного (' + color[1] + ', ' +
                share(color[1]) + '), ' +
                '<b class="font-mono">' + pair(color[2]) + '</b> — синего (' + color[2] + ', ' +
                share(color[2]) + '). Две шестнадцатеричные цифры — это ровно один байт, ' +
                'восемь битов; три байта на пиксель и дают 24 бита True Color.';
        }

        render();
    });

    // ─────────────────────────────────────────────────────────────
    // Виджет: pixel-grid — оцифровка изображения. Два огрубления,
    // ровно как у sampling-wave: сетка пикселей (разрешение) и
    // конечный список цветов (глубина цвета). Слева — «сцена» в
    // мелкой сетке (роль оригинала), справа — то, что попадёт в
    // память при выбранных параметрах, плюс объём по формуле
    // V = W · H · b. Сцены рисуются процедурно (без файлов), цвет
    // пикселя — усреднение по 3×3 точкам внутри клетки, поэтому
    // мелкая деталь честно теряется, а не просто «прореживается».
    // Конфиг: { "scene": "sunset", "size": 32, "bits": 8,
    //           "grid": true, "presets": [{ "title": "…",
    //           "scene": "stripes", "size": 12, "bits": 24 }] }
    // scene: sunset | circle | stripes; size 4–64 (ширина в
    // пикселях, высота 3/4 от неё); bits — из ряда 1, 2, 3, 6, 8,
    // 12, 16, 24 (реальные исторические раскладки по каналам).
    // ─────────────────────────────────────────────────────────────
    register('pixel-grid', function (el, config) {
        const SVG_NS = 'http://www.w3.org/2000/svg';
        const SIZE_MIN = 4, SIZE_MAX = 64;
        const ORIG_W = 96;                 // «оригинал» слева: мелкая сетка
        const SUB = 3;                     // точек усреднения по стороне клетки

        // Раскладки битов по каналам — все взяты из реально существовавших
        // режимов: RGB332 (8 битов), RGB444, RGB565, TrueColor.
        const DEPTHS = [
            { bits: 1, split: null, note: 'чёрное и белое' },
            { bits: 2, split: null, note: 'оттенки серого' },
            { bits: 3, split: [1, 1, 1], note: 'по 1 биту на канал' },
            { bits: 6, split: [2, 2, 2], note: 'по 2 бита на канал' },
            { bits: 8, split: [3, 3, 2], note: 'R:G:B = 3:3:2, палитра 256' },
            { bits: 12, split: [4, 4, 4], note: 'по 4 бита на канал' },
            { bits: 16, split: [5, 6, 5], note: 'R:G:B = 5:6:5, High Color' },
            { bits: 24, split: [8, 8, 8], note: 'по 8 битов на канал, True Color' },
        ];

        const SCENES = [
            { key: 'sunset', title: 'Закат' },
            { key: 'circle', title: 'Фигуры' },
            { key: 'stripes', title: 'Мелкие полосы' },
        ];

        function clampInt(raw, lo, hi, fallback) {
            const n = parseInt(raw, 10);
            if (isNaN(n)) return fallback;
            return Math.min(Math.max(n, lo), hi);
        }

        function depthIndex(raw, fallback) {
            const n = parseInt(raw, 10);
            for (let i = 0; i < DEPTHS.length; i++) {
                if (DEPTHS[i].bits === n) return i;
            }
            return fallback;
        }

        function sceneKey(raw, fallback) {
            for (let i = 0; i < SCENES.length; i++) {
                if (SCENES[i].key === raw) return raw;
            }
            return fallback;
        }

        let scene = sceneKey(config.scene, 'sunset');
        let size = clampInt(config.size, SIZE_MIN, SIZE_MAX, 32);
        let depth = depthIndex(config.bits, 7);
        let showGrid = config.grid !== false;
        let hover = null;                  // { x, y } — клетка под курсором

        const presets = (Array.isArray(config.presets) ? config.presets : [])
            .filter(function (p) { return p && p.title; })
            .slice(0, 6);

        const chip = 'px-2.5 py-1 rounded-full text-xs border transition-colors bg-gray-50 text-gray-500 border-gray-200 hover:bg-gray-100 dark:bg-slate-700 dark:border-slate-600 dark:text-slate-300';
        const chipActive = 'px-2.5 py-1 rounded-full text-xs border transition-colors bg-brand-600 text-white border-brand-600 dark:bg-cyan-500 dark:border-cyan-500';

        function svgEl(name, attrs) {
            const node = document.createElementNS(SVG_NS, name);
            Object.keys(attrs || {}).forEach(function (k) {
                node.setAttribute(k, attrs[k]);
            });
            return node;
        }

        function num(n) {
            return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
        }

        // То же число, но для формулы: внутри $…$ обычный пробел не виден.
        function mnum(n) {
            return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, '\\,');
        }

        function plural(n, one, few, many) {
            const d10 = n % 10, d100 = n % 100;
            if (d10 === 1 && d100 !== 11) return one;
            if (d10 >= 2 && d10 <= 4 && (d100 < 12 || d100 > 14)) return few;
            return many;
        }

        function bitWord(n) { return plural(n, 'бит', 'бита', 'битов'); }
        function byteWord(n) { return plural(n, 'байт', 'байта', 'байтов'); }

        function height() { return Math.max(3, Math.round(size * 3 / 4)); }

        // ── сцены: цвет в точке (u, v), обе координаты 0…1 ────────
        function mix(a, b, t) {
            const k = Math.min(Math.max(t, 0), 1);
            return [a[0] + (b[0] - a[0]) * k,
                    a[1] + (b[1] - a[1]) * k,
                    a[2] + (b[2] - a[2]) * k];
        }

        function sunset(u, v) {
            const horizon = 0.66 + 0.035 * Math.sin(u * 7.5) + 0.02 * Math.sin(u * 3.1 + 1.2);
            if (v > horizon) {
                // земля: тёмный силуэт с лёгким уклоном к низу
                return mix([46, 38, 66], [22, 18, 34], (v - horizon) / (1 - horizon));
            }
            // небо: сверху фиолетовое, у горизонта раскалённое
            const t = v / horizon;
            let sky = mix([64, 40, 104], [214, 96, 78], Math.pow(t, 1.6));
            sky = mix(sky, [255, 196, 92], Math.pow(t, 5));
            // солнце
            const dx = (u - 0.5) * 1.0, dy = (v - 0.44) * 0.75;
            const d = Math.sqrt(dx * dx + dy * dy);
            if (d < 0.16) sky = mix([255, 246, 206], sky, Math.pow(d / 0.16, 6));
            return sky;
        }

        function circleScene(u, v) {
            const bg = mix([236, 243, 250], [206, 222, 240], v);
            // жёлтая полоса по диагонали
            const band = u * 0.8 + v * 0.6;
            let c = bg;
            if (band > 0.72 && band < 0.95) c = [245, 158, 11];
            // синий круг поверх
            const dx = u - 0.42, dy = (v - 0.5) * 0.75;
            if (Math.sqrt(dx * dx + dy * dy) < 0.24) c = [37, 99, 235];
            return c;
        }

        function stripes(u, v) {
            // Наклонные полосы, период которых уменьшается слева направо:
            // справа деталь мельче клетки — и в записи появляется муар.
            // Нижняя граница периода подобрана так, чтобы в мелкой сетке
            // «оригинала» (96 клеток) полосы ещё читались чисто: иначе муар
            // появлялся бы в обеих панелях и сравнивать было бы не с чем.
            const period = 0.17 - 0.115 * u;
            const s = (u * 0.94 + v * 0.34) / period;
            const on = (s - Math.floor(s)) < 0.5;
            return on ? [23, 94, 108] : [232, 240, 236];
        }

        function sceneColor(u, v) {
            if (scene === 'circle') return circleScene(u, v);
            if (scene === 'stripes') return stripes(u, v);
            return sunset(u, v);
        }

        // Цвет клетки — среднее по SUB×SUB точкам внутри неё.
        function cellColor(x, y, w, h) {
            let r = 0, g = 0, b = 0;
            for (let i = 0; i < SUB; i++) {
                for (let j = 0; j < SUB; j++) {
                    const u = (x + (i + 0.5) / SUB) / w;
                    const v = (y + (j + 0.5) / SUB) / h;
                    const c = sceneColor(u, v);
                    r += c[0]; g += c[1]; b += c[2];
                }
            }
            const n = SUB * SUB;
            return [r / n, g / n, b / n];
        }

        // ── квантование цвета ────────────────────────────────────
        function quantChannel(value, bitsPerChannel) {
            const last = (1 << bitsPerChannel) - 1;
            const idx = Math.min(Math.max(Math.round(value / 255 * last), 0), last);
            return { idx: idx, value: last === 0 ? (idx ? 255 : 0) : idx / last * 255 };
        }

        function quantize(rgb) {
            const d = DEPTHS[depth];
            if (!d.split) {
                const gray = 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2];
                const q = quantChannel(gray, d.bits);
                return { rgb: [q.value, q.value, q.value], idx: [q.idx], gray: true };
            }
            const qr = quantChannel(rgb[0], d.split[0]);
            const qg = quantChannel(rgb[1], d.split[1]);
            const qb = quantChannel(rgb[2], d.split[2]);
            return {
                rgb: [qr.value, qg.value, qb.value],
                idx: [qr.idx, qg.idx, qb.idx],
                gray: false,
            };
        }

        function hex(rgb) {
            return '#' + rgb.map(function (c) {
                const v = Math.min(255, Math.max(0, Math.round(c)));
                return (v < 16 ? '0' : '') + v.toString(16);
            }).join('').toUpperCase();
        }

        function rgbText(rgb) {
            return rgb.map(function (c) { return Math.round(c); }).join(', ');
        }

        // ── разметка ─────────────────────────────────────────────
        const body = widgetFrame(el, el.dataset.title);

        const sceneRow = document.createElement('div');
        sceneRow.className = 'flex flex-wrap items-center gap-2 justify-center mb-3';
        const sceneBtns = SCENES.map(function (s) {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.textContent = s.title;
            btn.className = chip;
            btn.addEventListener('click', function () {
                scene = s.key;
                hover = null;
                render();
            });
            sceneRow.appendChild(btn);
            return btn;
        });

        const presetRow = document.createElement('div');
        presetRow.className = 'flex flex-wrap items-center gap-2 justify-center mb-4';
        presets.forEach(function (p) {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.textContent = p.title;
            btn.className = chip;
            btn.addEventListener('click', function () {
                scene = sceneKey(p.scene, scene);
                size = clampInt(p.size, SIZE_MIN, SIZE_MAX, size);
                depth = depthIndex(p.bits, depth);
                hover = null;
                render();
            });
            presetRow.appendChild(btn);
        });

        function slider(labelText, lo, hi, get, set) {
            const row = document.createElement('div');
            row.className = 'flex items-center gap-3';
            const label = document.createElement('span');
            label.className = 'text-xs text-gray-500 dark:text-slate-400 w-44 shrink-0';
            label.textContent = labelText;
            const input = document.createElement('input');
            input.type = 'range';
            input.min = String(lo);
            input.max = String(hi);
            input.step = '1';
            input.className = 'flex-1 accent-brand-600 dark:accent-cyan-500';
            input.setAttribute('aria-label', labelText);
            input.addEventListener('input', function () {
                set(clampInt(input.value, lo, hi, get()));
                hover = null;
                render();
            });
            const value = document.createElement('b');
            value.className = 'text-sm font-mono text-gray-900 dark:text-white w-32 text-right shrink-0';
            row.appendChild(label);
            row.appendChild(input);
            row.appendChild(value);
            row._refresh = function (text) {
                input.value = String(get());
                value.textContent = text;
            };
            return row;
        }

        const sizeRow = slider('Разрешение', SIZE_MIN, SIZE_MAX,
            function () { return size; }, function (v) { size = v; });
        const depthRow = slider('Глубина цвета', 0, DEPTHS.length - 1,
            function () { return depth; }, function (v) { depth = v; });

        const sliders = document.createElement('div');
        sliders.className = 'flex flex-col gap-2 mb-4';
        sliders.appendChild(sizeRow);
        sliders.appendChild(depthRow);

        const gridBtn = document.createElement('button');
        gridBtn.type = 'button';
        gridBtn.textContent = 'Показывать сетку';
        gridBtn.addEventListener('click', function () {
            showGrid = !showGrid;
            render();
        });

        const toggleRow = document.createElement('div');
        toggleRow.className = 'flex flex-wrap items-center gap-2 justify-center mb-4';
        toggleRow.appendChild(gridBtn);

        const panels = document.createElement('div');
        panels.className = 'flex flex-wrap items-start justify-center gap-4';

        function panel(caption) {
            const wrap = document.createElement('div');
            wrap.className = 'flex-1 min-w-[260px] max-w-[360px]';
            const box = document.createElement('div');
            box.className = 'rounded-lg overflow-hidden border border-gray-200 dark:border-slate-600';
            const cap = document.createElement('div');
            cap.className = 'mt-1.5 text-center text-xs text-gray-400 dark:text-slate-500';
            cap.textContent = caption;
            wrap.appendChild(box);
            wrap.appendChild(cap);
            wrap._box = box;
            wrap._cap = cap;
            return wrap;
        }

        const origPanel = panel('Исходная сцена');
        const shotPanel = panel('Что уходит в память');
        panels.appendChild(origPanel);
        panels.appendChild(shotPanel);

        const stats = document.createElement('div');
        stats.className = 'mt-4 text-center text-sm text-gray-600 dark:text-slate-300';

        const note = document.createElement('div');
        note.className = 'mt-3 rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-sm text-gray-600 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-300 min-h-[2.75rem]';

        body.appendChild(sceneRow);
        if (presets.length) body.appendChild(presetRow);
        body.appendChild(sliders);
        body.appendChild(toggleRow);
        body.appendChild(panels);
        body.appendChild(stats);
        body.appendChild(note);

        // ── отрисовка ────────────────────────────────────────────
        function drawScene(host, w, h, quant) {
            host.innerHTML = '';
            const svg = svgEl('svg', {
                viewBox: '0 0 ' + w + ' ' + h,
                class: 'block w-full h-auto',
                'shape-rendering': 'crispEdges',
                preserveAspectRatio: 'xMidYMid meet',
            });
            const cells = [];
            let errSum = 0, errCount = 0;

            for (let y = 0; y < h; y++) {
                for (let x = 0; x < w; x++) {
                    const src = cellColor(x, y, w, h);
                    let fill = src;
                    if (quant) {
                        const q = quantize(src);
                        fill = q.rgb;
                        errSum += Math.abs(src[0] - fill[0]) + Math.abs(src[1] - fill[1]) +
                            Math.abs(src[2] - fill[2]);
                        errCount += 3;
                        cells.push({ x: x, y: y, src: src, q: q });
                    }
                    const rect = svgEl('rect', {
                        x: x, y: y, width: 1.02, height: 1.02, fill: hex(fill),
                    });
                    if (quant && showGrid && w <= 48) {
                        rect.setAttribute('stroke', 'rgba(148,163,184,0.55)');
                        rect.setAttribute('stroke-width', 0.04);
                    }
                    svg.appendChild(rect);
                }
            }

            host.appendChild(svg);
            return {
                svg: svg,
                cells: cells,
                error: errCount ? errSum / errCount : 0,
            };
        }

        function describe(cell) {
            const d = DEPTHS[depth];
            let text = 'Пиксель (' + cell.x + ', ' + cell.y + '). ' +
                'В сцене на этом месте цвет ' + hex(cell.src) + ' — RGB ' +
                rgbText(cell.src) + '. ';
            if (cell.q.gray) {
                text += 'Глубина ' + d.bits + ' ' + bitWord(d.bits) + ' на пиксель — доступно ' +
                    (1 << d.bits) + ' уровня серого; выбран номер ' + cell.q.idx[0] +
                    ', то есть ' + hex(cell.q.rgb) + '.';
            } else {
                text += 'В память уходят три номера — по каналам R:G:B = ' +
                    d.split.join(':') + ': ' +
                    cell.q.idx.join(', ') + '. Обратно они разворачиваются в ' +
                    hex(cell.q.rgb) + ' — RGB ' + rgbText(cell.q.rgb) + '.';
            }
            const diff = Math.round(Math.max(
                Math.abs(cell.src[0] - cell.q.rgb[0]),
                Math.abs(cell.src[1] - cell.q.rgb[1]),
                Math.abs(cell.src[2] - cell.q.rgb[2])));
            text += ' Разошлись с исходным цветом на ' + diff + ' из 255.';
            return text;
        }

        function hint() {
            return 'Наведите на любой пиксель справа — покажу, какой цвет был в сцене, ' +
                'какие номера уходят в память и насколько записанный цвет разошёлся с исходным.';
        }

        // Левая панель зависит только от сцены — на каждое движение ползунка
        // перерисовывать 7000 прямоугольников незачем.
        let origDrawn = null;

        function render() {
            const w = size, h = height();
            const d = DEPTHS[depth];

            if (origDrawn !== scene) {
                drawScene(origPanel._box, ORIG_W, Math.round(ORIG_W * 3 / 4), false);
                origDrawn = scene;
            }
            const shot = drawScene(shotPanel._box, w, h, true);

            origPanel._cap.textContent = 'Исходная сцена (мелкая сетка, полный цвет)';
            shotPanel._cap.textContent = w + ' × ' + h + ' пикселей, ' + d.bits + ' ' +
                bitWord(d.bits) + ' на пиксель';

            // наведение: считаем клетку из координат мыши, весь SVG не перерисовываем
            function pick(ev) {
                const box = shot.svg.getBoundingClientRect();
                if (!box || !box.width || !box.height) return;
                const x = Math.floor((ev.clientX - box.left) / box.width * w);
                const y = Math.floor((ev.clientY - box.top) / box.height * h);
                if (x < 0 || y < 0 || x >= w || y >= h) return;
                hover = { x: x, y: y };
                const cell = shot.cells[y * w + x];
                if (cell) note.textContent = describe(cell);
            }
            shot.svg.addEventListener('mousemove', pick);
            shot.svg.addEventListener('click', pick);
            shot.svg.addEventListener('mouseleave', function () {
                hover = null;
                note.textContent = hint();
            });
            shot.svg.classList.add('cursor-crosshair');

            sizeRow._refresh(w + ' × ' + h);
            depthRow._refresh(d.bits + ' ' + bitWord(d.bits));
            gridBtn.className = showGrid ? chipActive : chip;
            sceneBtns.forEach(function (btn, i) {
                btn.className = SCENES[i].key === scene ? chipActive : chip;
            });

            const pixels = w * h;
            const bits = pixels * d.bits;
            const bytes = Math.ceil(bits / 8);
            const colors = Math.pow(2, d.bits);
            const full = SIZE_MAX * Math.round(SIZE_MAX * 3 / 4) * 24 / 8;

            // Формулы – в том же виде, что и в тексте урока: LaTeX, который
            // наберёт MathJax после перерисовки виджета.
            stats.innerHTML =
                '<div>Пикселей: <b class="text-gray-900 dark:text-white">$' + w +
                ' \\times ' + h + ' = ' + mnum(pixels) + '$</b> · цветов: ' +
                '<b class="text-gray-900 dark:text-white">$2^{' + d.bits +
                '} = ' + mnum(colors) + '$</b> <span class="text-gray-400 dark:text-slate-500">(' +
                d.note + ')</span></div>' +
                '<div class="mt-1">Объём: <b class="text-gray-900 dark:text-white">$' +
                mnum(pixels) + ' \\times ' + d.bits + ' = ' + mnum(bits) + '$</b> битов = ' +
                '<b class="text-gray-900 dark:text-white">$' + mnum(bytes) +
                '$</b> ' + byteWord(bytes) + '</div>' +
                '<div class="text-xs text-gray-400 dark:text-slate-500 mt-1">' +
                'самая тяжёлая настройка (64 × 48, 24 бита) — ' + num(full) + ' байтов; ' +
                'средняя ошибка цвета сейчас — ' +
                shot.error.toFixed(1).replace('.', ',') + ' из 255</div>';

            if (hover) {
                const cell = shot.cells[hover.y * w + hover.x];
                note.textContent = cell ? describe(cell) : hint();
            } else {
                note.textContent = hint();
            }
        }

        render();
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

    // ─────────────────────────────────────────────────────────────
    // Виджет: loop-trace — пошаговая трассировка программы. Слева листинг
    // кода с подсветкой текущей строки, справа — состояние переменных
    // (изменившаяся на этом шаге подсвечена), под ними — накопленный вывод
    // программы. Шаги перелистываются кнопками или ползунком.
    //
    // Виджет ничего не вычисляет: трассу готовит автор урока (обычно
    // генерирует питоновским циклом прямо в seed-команде) и передаёт готовым
    // списком шагов. Поэтому виджет не привязан к while и годится для любого
    // кода — for, вложенных циклов, функций.
    //
    // Конфиг:
    //   {
    //     "code":  ["sec = 5", "while sec > 0:", "    print(sec)"],
    //     "vars":  ["sec"],                        // порядок колонок, необязателен
    //     "steps": [
    //       {"line": 1, "vars": {"sec": 5}, "note": "начальное значение"},
    //       {"line": 2, "vars": {"sec": 5}, "check": true, "note": "5 > 0"},
    //       {"line": 3, "vars": {"sec": 5}, "out": "5"}
    //     ]
    //   }
    // line  — номер строки в code, начиная с 1;
    // vars  — ПОЛНОЕ состояние после выполнения строки (поэтому шаг назад
    //         работает без пересчёта; переменная, которой ещё нет, — просто
    //         отсутствующий ключ);
    // out   — что добавилось в вывод программы на этом шаге;
    // check — результат проверки условия, рисует бейдж «истина»/«ложь».
    // ─────────────────────────────────────────────────────────────
    register('loop-trace', function (el, config) {
        const code = Array.isArray(config.code) ? config.code : [];
        const steps = Array.isArray(config.steps) ? config.steps : [];
        if (code.length === 0 || steps.length === 0) {
            el.innerHTML = '<p class="text-sm text-red-500">loop-trace: нужны непустые code и steps</p>';
            return;
        }

        // Порядок колонок задаётся явно; если не задан — собираем имена в
        // порядке первого появления в трассе.
        let varNames = Array.isArray(config.vars) ? config.vars.slice() : [];
        if (varNames.length === 0) {
            steps.forEach(function (s) {
                Object.keys(s.vars || {}).forEach(function (name) {
                    if (varNames.indexOf(name) === -1) varNames.push(name);
                });
            });
        }
        const hasOutput = steps.some(function (s) { return s.out !== undefined && s.out !== null; });

        // Значения показываем в питоновской записи: строки в кавычках,
        // True/False с заглавной, отсутствующая переменная — прочерком.
        // Тип, который здесь не собрать (множество, словарь), передаётся из
        // seed-команды готовой строкой: {"__raw": "{'А': 3}"} — печатаем как есть.
        function formatValue(v) {
            if (v === null || v === undefined) return '—';
            if (typeof v === 'boolean') return v ? 'True' : 'False';
            if (typeof v === 'string') return "'" + v + "'";
            if (Array.isArray(v)) return '[' + v.map(formatValue).join(', ') + ']';
            if (typeof v === 'object' && typeof v.__raw === 'string') return v.__raw;
            return String(v);
        }

        const body = widgetFrame(el, el.dataset.title || 'Пошаговое выполнение');

        const btnPrimary = 'px-3 py-1.5 rounded-full text-sm border transition-colors bg-brand-600 text-white border-brand-600 hover:bg-brand-700 dark:bg-cyan-500 dark:border-cyan-500 dark:hover:bg-cyan-400';
        const btnSecondary = 'px-3 py-1.5 rounded-full text-sm border transition-colors bg-gray-50 text-gray-500 border-gray-200 hover:bg-gray-100 dark:bg-slate-700 dark:border-slate-600 dark:text-slate-300';

        // pos: -1 — программа ещё не запущена, дальше индекс текущего шага.
        let pos = -1;

        // ---- листинг кода ----
        // Панель тёмная в обеих темах — как обычные code-блоки статьи: страница
        // подключает тему highlight.js atom-one-dark, и подсветка токенов
        // (.hljs-keyword и т.п.) приходит оттуда же. Фон и базовый цвет задаём
        // инлайном, чтобы листинг оставался читаемым, даже если CDN с темой
        // не доступен.
        const HLJS_BG = '#282c34';
        const HLJS_FG = '#abb2bf';
        const HLJS_GUTTER = '#5c6370';

        const lang = config.language || 'python';

        // Подсвечиваем построчно: строки трассы адресуются по номеру, поэтому
        // каждая — отдельный DOM-узел. Для многострочных конструкций (тройные
        // кавычки) построчная подсветка неточна, но в учебных примерах их нет.
        function highlightLine(line) {
            if (window.hljs && hljs.getLanguage && hljs.getLanguage(lang)) {
                try {
                    return hljs.highlight(line, { language: lang, ignoreIllegals: true }).value;
                } catch (e) {
                    /* тема или язык не загрузились — покажем как обычный текст */
                }
            }
            return escapeHtml(line);
        }

        const codePane = document.createElement('div');
        codePane.className = 'rounded-lg py-2 overflow-x-auto';
        codePane.style.background = HLJS_BG;
        codePane.style.color = HLJS_FG;
        const codeRows = code.map(function (line, i) {
            const row = document.createElement('div');
            row.className = 'flex items-start gap-3 pl-2 pr-4 py-0.5 font-mono text-sm whitespace-pre border-l-2 border-transparent';
            const num = document.createElement('span');
            num.className = 'w-5 shrink-0 text-right select-none';
            num.style.color = HLJS_GUTTER;
            num.textContent = String(i + 1);
            const text = document.createElement('span');
            text.innerHTML = highlightLine(line);
            row.appendChild(num);
            row.appendChild(text);
            codePane.appendChild(row);
            return row;
        });

        // ---- состояние переменных ----
        const statePane = document.createElement('div');
        statePane.className = 'flex flex-col gap-2';
        const stateTitle = document.createElement('div');
        stateTitle.className = 'text-xs uppercase tracking-wide text-gray-400 dark:text-slate-500';
        stateTitle.textContent = 'Переменные';
        statePane.appendChild(stateTitle);

        const varRows = varNames.map(function (name) {
            const row = document.createElement('div');
            row.className = 'flex items-center justify-between gap-3 px-3 py-1.5 rounded-md border font-mono text-sm';
            const key = document.createElement('span');
            key.className = 'text-gray-500 dark:text-slate-400';
            key.textContent = name;
            const val = document.createElement('b');
            val.className = 'text-gray-900 dark:text-white';
            row.appendChild(key);
            row.appendChild(val);
            statePane.appendChild(row);
            return { name: name, row: row, val: val };
        });

        const noteLine = document.createElement('div');
        noteLine.className = 'mt-1 text-sm text-gray-600 dark:text-slate-300 min-h-[2.75rem] flex flex-wrap items-center gap-2';
        statePane.appendChild(noteLine);

        const columns = document.createElement('div');
        columns.className = 'grid gap-4 md:grid-cols-2';
        columns.appendChild(codePane);
        columns.appendChild(statePane);

        // ---- вывод программы ----
        const outputPane = document.createElement('div');
        outputPane.className = 'mt-4 rounded-lg px-4 py-3 font-mono text-sm whitespace-pre-wrap break-words bg-slate-900 text-slate-100 min-h-[3.5rem] max-h-40 overflow-y-auto';
        const outputTitle = document.createElement('div');
        outputTitle.className = 'mt-4 mb-1 text-xs uppercase tracking-wide text-gray-400 dark:text-slate-500';
        outputTitle.textContent = 'Вывод программы';

        // ---- управление ----
        const slider = document.createElement('input');
        slider.type = 'range';
        slider.min = '0';
        slider.max = String(steps.length);
        slider.value = '0';
        slider.className = 'w-full accent-brand-600 dark:accent-cyan-500';
        slider.setAttribute('aria-label', 'Номер шага выполнения');

        const prevBtn = document.createElement('button');
        prevBtn.type = 'button';
        prevBtn.textContent = '← Назад';

        const nextBtn = document.createElement('button');
        nextBtn.type = 'button';
        nextBtn.textContent = 'Шаг вперёд →';

        const endBtn = document.createElement('button');
        endBtn.type = 'button';
        endBtn.textContent = 'В конец';
        endBtn.className = btnSecondary;

        const resetBtn = document.createElement('button');
        resetBtn.type = 'button';
        resetBtn.textContent = 'Сбросить';
        resetBtn.className = btnSecondary;

        const counter = document.createElement('span');
        counter.className = 'text-sm text-gray-400 dark:text-slate-400 ml-auto';

        const controls = document.createElement('div');
        controls.className = 'flex flex-wrap items-center gap-2 mt-4';
        controls.appendChild(prevBtn);
        controls.appendChild(nextBtn);
        controls.appendChild(endBtn);
        controls.appendChild(resetBtn);
        controls.appendChild(counter);

        body.appendChild(columns);
        if (hasOutput) {
            body.appendChild(outputTitle);
            body.appendChild(outputPane);
        }
        body.appendChild(controls);
        body.appendChild(slider);

        function render() {
            const step = pos >= 0 ? steps[pos] : null;
            const vars = step && step.vars ? step.vars : {};
            const prevVars = pos > 0 && steps[pos - 1].vars ? steps[pos - 1].vars : {};

            codeRows.forEach(function (row, i) {
                const active = step && step.line === i + 1;
                // Панель тёмная всегда, поэтому подсветка строки одна и та же в
                // обеих темах: полупрозрачная заливка и яркая полоса слева.
                row.className = 'flex items-start gap-3 pl-2 pr-4 py-0.5 font-mono text-sm whitespace-pre border-l-2 ' +
                    (active
                        ? 'border-cyan-400 bg-white/10'
                        : 'border-transparent');
            });

            varRows.forEach(function (v) {
                const has = Object.prototype.hasOwnProperty.call(vars, v.name);
                // Подсвечиваем переменную, которая изменилась именно на этом шаге.
                const changed = pos >= 0 && has &&
                    JSON.stringify(vars[v.name]) !== JSON.stringify(prevVars[v.name]);
                v.val.textContent = has ? formatValue(vars[v.name]) : '—';
                v.row.className = 'flex items-center justify-between gap-3 px-3 py-1.5 rounded-md border font-mono text-sm transition-colors ' +
                    (changed
                        ? 'bg-amber-50 border-amber-300 dark:bg-amber-900/25 dark:border-amber-700'
                        : 'bg-white border-gray-200 dark:bg-slate-800 dark:border-slate-600');
            });

            noteLine.innerHTML = '';
            if (step && step.check !== undefined && step.check !== null) {
                const badge = document.createElement('span');
                badge.className = 'px-2 py-0.5 rounded-md text-xs font-semibold border ' +
                    (step.check
                        ? 'bg-emerald-50 border-emerald-300 text-emerald-700 dark:bg-emerald-900/30 dark:border-emerald-700 dark:text-emerald-300'
                        : 'bg-gray-100 border-gray-300 text-gray-500 dark:bg-slate-700 dark:border-slate-500 dark:text-slate-300');
                badge.textContent = step.check ? 'условие истинно' : 'условие ложно';
                noteLine.appendChild(badge);
            }
            const noteText = document.createElement('span');
            noteText.textContent = step
                ? (step.note || '')
                : 'Программа ещё не запущена — нажмите «Шаг вперёд».';
            noteLine.appendChild(noteText);

            if (hasOutput) {
                const printed = [];
                for (let i = 0; i <= pos; i++) {
                    if (steps[i].out !== undefined && steps[i].out !== null) printed.push(steps[i].out);
                }
                outputPane.textContent = printed.join('\n');
                outputPane.scrollTop = outputPane.scrollHeight;
            }

            counter.textContent = pos < 0
                ? 'шаг 0 из ' + steps.length
                : 'шаг ' + (pos + 1) + ' из ' + steps.length;
            slider.value = String(pos + 1);

            prevBtn.disabled = pos < 0;
            prevBtn.className = btnSecondary + (pos < 0 ? ' opacity-50 cursor-not-allowed' : '');
            const atEnd = pos >= steps.length - 1;
            nextBtn.disabled = atEnd;
            nextBtn.className = btnPrimary + (atEnd ? ' opacity-50 cursor-not-allowed' : '');
            endBtn.disabled = atEnd;
            endBtn.className = btnSecondary + (atEnd ? ' opacity-50 cursor-not-allowed' : '');
        }

        prevBtn.addEventListener('click', function () {
            if (pos >= 0) { pos--; render(); }
        });
        nextBtn.addEventListener('click', function () {
            if (pos < steps.length - 1) { pos++; render(); }
        });
        endBtn.addEventListener('click', function () {
            pos = steps.length - 1;
            render();
        });
        resetBtn.addEventListener('click', function () {
            pos = -1;
            render();
        });
        slider.addEventListener('input', function () {
            pos = (parseInt(slider.value, 10) || 0) - 1;
            render();
        });

        render();
    });

    // ─────────────────────────────────────────────────────────────
    // Виджет: slice-ruler — индексы и срезы строки (урок 8.2).
    // Строка разложена по клеткам: над ней линейка прямых индексов, под ней —
    // отрицательных, так что видно, что s[2] и s[-4] — одно и то же место.
    // Поля start/stop/step задают срез (пустое поле = граница опущена):
    // попавшие символы подсвечены и пронумерованы по порядку в результате,
    // над лентой стоят метки start и stop, а клетка на позиции stop обведена
    // пунктиром — она не включается. Наведение на символ объясняет, почему
    // он попал или не попал.
    //
    // Границы вычисляются ровно по правилам Python (приведение отрицательных,
    // обрезка по краям, отрицательный шаг, пустой результат, ошибка при
    // шаге 0), поэтому виджет не врёт на краевых случаях вроде s[100:200].
    //
    // Конфиг: { "text": "Привет", "start": 1, "stop": 5, "step": null,
    //           "presets": [{"title": "год", "text": "2026-08-01", "stop": 4}] }
    // null или отсутствующий ключ = граница опущена (двоеточие без числа);
    // у пресета можно менять и текст, и любые границы. До 8 пресетов.
    // ─────────────────────────────────────────────────────────────
    register('slice-ruler', function (el, config) {
        const MAX_LEN = 24;

        function parseBound(v) {
            if (v === undefined || v === null || v === '') return null;
            const n = parseInt(v, 10);
            return isNaN(n) ? null : n;
        }

        function normText(v) {
            const s = (typeof v === 'string' && v.length) ? v : 'Привет';
            return Array.from(s).slice(0, MAX_LEN);
        }

        let chars = normText(config.text);
        let slStart = parseBound(config.start);
        let slStop = parseBound(config.stop);
        let slStep = parseBound(config.step);
        let hover = null;

        const body = widgetFrame(el, el.dataset.title || 'Индексы и срезы');

        const btnChip = 'px-2.5 py-1 rounded-full text-xs border transition-colors bg-gray-50 text-gray-500 border-gray-200 hover:bg-gray-100 dark:bg-slate-700 dark:border-slate-600 dark:text-slate-300';
        const btnActive = 'px-2.5 py-1 rounded-full text-xs border transition-colors bg-brand-600 text-white border-brand-600 dark:bg-cyan-500 dark:border-cyan-500';
        const numInput = 'w-16 text-center rounded-md border px-2 py-1 font-mono text-sm border-gray-200 bg-white text-gray-900 dark:border-slate-600 dark:bg-slate-800 dark:text-white';
        const textInput = 'w-52 rounded-md border px-2 py-1 font-mono text-base border-gray-200 bg-white text-gray-900 dark:border-slate-600 dark:bg-slate-800 dark:text-white';

        const CELL_BASE = 'w-8 h-10 shrink-0 rounded-md font-mono text-base flex items-center justify-center border transition-colors';
        const CELL_IN = 'bg-emerald-500 text-white border-emerald-500 dark:bg-emerald-500 dark:border-emerald-500';
        const CELL_OUT = 'bg-gray-50 text-gray-400 border-gray-200 dark:bg-slate-700 dark:border-slate-600';
        // Клетка на позиции stop: она первая, которую срез уже не берёт.
        const CELL_STOP = 'bg-white text-gray-400 border-dashed border-rose-400 dark:bg-slate-800 dark:border-rose-400 dark:text-slate-400';
        const HILITE = ' ring-2 ring-rose-400 dark:ring-rose-400';
        const COL_W = 'w-8 shrink-0 text-center';
        const EDGE_W = 'w-6 shrink-0 text-center';

        function num(n) { return String(n).replace('-', '−'); }
        function shown(ch) { return ch === ' ' ? '␣' : ch; }
        function repr(ch) { return "'" + shown(ch) + "'"; }

        // ── питоновская семантика среза ──────────────────────────
        // Ровно то, что делает CPython: отрицательная граница сдвигается на
        // длину, затем обрезается по краям — поэтому s[100:200] не ошибка,
        // а пустая строка.
        function clampForward(v, n) {
            let x = v < 0 ? v + n : v;
            if (x < 0) x = 0;
            if (x > n) x = n;
            return x;
        }

        function clampBackward(v, n) {
            let x = v < 0 ? v + n : v;
            if (x < -1) x = -1;
            if (x > n - 1) x = n - 1;
            return x;
        }

        function resolve() {
            const n = chars.length;
            const step = slStep === null ? 1 : slStep;
            if (step === 0) return { error: true, step: 0, idx: [] };
            let start;
            let stop;
            if (step > 0) {
                start = slStart === null ? 0 : clampForward(slStart, n);
                stop = slStop === null ? n : clampForward(slStop, n);
            } else {
                start = slStart === null ? n - 1 : clampBackward(slStart, n);
                stop = slStop === null ? -1 : clampBackward(slStop, n);
            }
            const idx = [];
            for (let i = start; step > 0 ? i < stop : i > stop; i += step) idx.push(i);
            return { error: false, step: step, start: start, stop: stop, idx: idx };
        }

        function exprText() {
            const a = slStart === null ? '' : String(slStart);
            const b = slStop === null ? '' : String(slStop);
            const c = slStep === null ? '' : ':' + String(slStep);
            return 's[' + a + ':' + b + c + ']';
        }

        // ── лента ────────────────────────────────────────────────
        const scroller = document.createElement('div');
        scroller.className = 'mt-4 overflow-x-auto';
        const tape = document.createElement('div');
        tape.className = 'inline-block min-w-full';
        scroller.appendChild(tape);

        const cells = [];        // клетки символов, по индексу
        const idxLabels = [];    // прямые индексы
        const negLabels = [];    // индексы с конца
        const ordLabels = [];    // номер символа в результате
        let markCells = {};      // метки start/stop, ключ — позиция от −1 до n

        function makeRow(labelText) {
            const row = document.createElement('div');
            row.className = 'flex items-center gap-1 justify-center';
            const label = document.createElement('div');
            label.className = 'w-24 shrink-0 pr-2 text-right font-mono text-xs text-gray-400 dark:text-slate-500';
            label.textContent = labelText;
            row.appendChild(label);
            tape.appendChild(row);
            return row;
        }

        function edgeSlot(row, cls) {
            const slot = document.createElement('div');
            slot.className = cls || EDGE_W;
            row.appendChild(slot);
            return slot;
        }

        function buildTape() {
            tape.innerHTML = '';
            cells.length = 0;
            idxLabels.length = 0;
            negLabels.length = 0;
            ordLabels.length = 0;
            markCells = {};
            const n = chars.length;

            const rowMark = makeRow('');
            markCells[-1] = edgeSlot(rowMark, EDGE_W + ' text-[9px] leading-tight');
            for (let i = 0; i < n; i++) {
                const m = document.createElement('div');
                m.className = COL_W + ' text-[9px] leading-tight';
                rowMark.appendChild(m);
                markCells[i] = m;
            }
            markCells[n] = edgeSlot(rowMark, EDGE_W + ' text-[9px] leading-tight');

            const rowIdx = makeRow('индекс');
            edgeSlot(rowIdx);
            for (let i = 0; i < n; i++) {
                const d = document.createElement('div');
                d.className = COL_W + ' text-[11px] text-gray-400 dark:text-slate-500';
                d.textContent = String(i);
                rowIdx.appendChild(d);
                idxLabels.push(d);
            }
            edgeSlot(rowIdx);

            const rowChar = makeRow('s =');
            edgeSlot(rowChar);
            for (let i = 0; i < n; i++) {
                const cell = document.createElement('div');
                cell.className = CELL_BASE + ' ' + CELL_OUT;
                cell.textContent = shown(chars[i]);
                (function (pos) {
                    cell.addEventListener('mouseenter', function () { hover = pos; paint(); });
                })(i);
                cell.addEventListener('mouseleave', function () { hover = null; paint(); });
                rowChar.appendChild(cell);
                cells.push(cell);
            }
            edgeSlot(rowChar);

            const rowNeg = makeRow('с конца');
            edgeSlot(rowNeg);
            for (let i = 0; i < n; i++) {
                const d = document.createElement('div');
                d.className = COL_W + ' text-[11px] text-gray-400 dark:text-slate-500';
                d.textContent = num(i - n);
                rowNeg.appendChild(d);
                negLabels.push(d);
            }
            edgeSlot(rowNeg);

            const rowOrd = makeRow('в срезе');
            edgeSlot(rowOrd);
            for (let i = 0; i < n; i++) {
                const d = document.createElement('div');
                d.className = COL_W + ' text-[11px] text-emerald-600 dark:text-emerald-400';
                rowOrd.appendChild(d);
                ordLabels.push(d);
            }
            edgeSlot(rowOrd);
        }

        // ── строка-результат и подсказки ─────────────────────────
        const resultLine = document.createElement('div');
        resultLine.className = 'mt-4 text-center font-mono text-lg text-gray-900 dark:text-white';

        const hintLine = document.createElement('div');
        hintLine.className = 'mt-2 text-center text-sm text-gray-500 dark:text-slate-400 min-h-[2.5rem]';

        // ── управление ───────────────────────────────────────────
        const controls = document.createElement('div');
        controls.className = 'mt-4 flex flex-wrap gap-3 justify-center items-center';

        const strInput = document.createElement('input');
        strInput.type = 'text';
        strInput.className = textInput;
        strInput.maxLength = MAX_LEN;
        strInput.setAttribute('aria-label', 'Строка');
        strInput.addEventListener('input', function () {
            chars = normText(strInput.value);
            hover = null;
            render(true, true);
        });
        const strLabel = document.createElement('label');
        strLabel.className = 'flex items-center gap-2 text-sm text-gray-500 dark:text-slate-400';
        strLabel.innerHTML = '<span class="font-mono">s =</span>';
        strLabel.appendChild(strInput);
        controls.appendChild(strLabel);

        const bounds = document.createElement('div');
        bounds.className = 'mt-3 flex flex-wrap gap-3 justify-center items-center';

        // Каждая граница — поле ввода плюс кнопка «пусто»: пустая граница
        // это отдельное состояние, а не ноль, и оно должно быть в один клик.
        function boundControl(name, get, set) {
            const wrap = document.createElement('label');
            wrap.className = 'flex items-center gap-1.5 text-sm text-gray-500 dark:text-slate-400';
            const cap = document.createElement('span');
            cap.className = 'font-mono';
            cap.textContent = name;
            const input = document.createElement('input');
            input.type = 'number';
            input.className = numInput;
            input.setAttribute('aria-label', name);
            input.addEventListener('input', function () {
                set(input.value === '' ? null : (parseInt(input.value, 10) || 0));
                paint(true);
            });
            const clear = document.createElement('button');
            clear.type = 'button';
            clear.textContent = 'пусто';
            clear.title = 'опустить границу — Python подставит край строки';
            clear.addEventListener('click', function () {
                set(null);
                render(false);
            });
            wrap.appendChild(cap);
            wrap.appendChild(input);
            wrap.appendChild(clear);
            bounds.appendChild(wrap);
            return { input: input, clear: clear, get: get };
        }

        const startCtl = boundControl('start', function () { return slStart; }, function (v) { slStart = v; });
        const stopCtl = boundControl('stop', function () { return slStop; }, function (v) { slStop = v; });
        const stepCtl = boundControl('step', function () { return slStep; }, function (v) { slStep = v; });

        const stepRow = document.createElement('div');
        stepRow.className = 'mt-3 flex flex-wrap gap-2 justify-center items-center';
        const stepLabel = document.createElement('span');
        stepLabel.className = 'text-sm text-gray-500 dark:text-slate-400';
        stepLabel.textContent = 'шаг:';
        stepRow.appendChild(stepLabel);
        const stepButtons = [];
        [-3, -2, -1, 1, 2, 3].forEach(function (v) {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.textContent = num(v);
            btn.addEventListener('click', function () {
                slStep = v;
                render(false);
            });
            stepButtons.push({ btn: btn, step: v });
            stepRow.appendChild(btn);
        });

        const presets = document.createElement('div');
        presets.className = 'mt-3 flex flex-wrap gap-2 justify-center items-center';

        function presetBtn(state) {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = btnChip;
            btn.textContent = state.title;
            if (state.hint) btn.title = state.hint;
            btn.addEventListener('click', function () {
                if (typeof state.text === 'string' && state.text.length) chars = normText(state.text);
                slStart = parseBound(state.start);
                slStop = parseBound(state.stop);
                slStep = parseBound(state.step);
                hover = null;
                render(true);
            });
            presets.appendChild(btn);
        }

        const presetList = Array.isArray(config.presets) && config.presets.length
            ? config.presets.slice(0, 8)
            : [
                { title: 's[:]', hint: 'обе границы опущены — вся строка целиком' },
                { title: 's[1:4]', start: 1, stop: 4, hint: 'позиции 1, 2, 3 — четвёртая уже не входит' },
                { title: 's[:3]', stop: 3, hint: 'первые три символа' },
                { title: 's[3:]', start: 3, hint: 'всё, начиная с позиции 3' },
                { title: 's[1:-1]', start: 1, stop: -1, hint: 'без первого и без последнего' },
                { title: 's[::2]', step: 2, hint: 'каждый второй символ' },
                { title: 's[::-1]', step: -1, hint: 'задом наперёд' },
                { title: 's[100:200]', start: 100, stop: 200, hint: 'за границей строки — не ошибка, а пустая строка' },
            ];
        presetList.forEach(presetBtn);

        const noteLine = document.createElement('div');
        noteLine.className = 'mt-4 text-sm text-gray-500 dark:text-slate-400';

        body.appendChild(scroller);
        body.appendChild(resultLine);
        body.appendChild(hintLine);
        body.appendChild(controls);
        body.appendChild(bounds);
        body.appendChild(stepRow);
        body.appendChild(presets);
        body.appendChild(noteLine);

        // ── отрисовка ────────────────────────────────────────────
        function paintTape(s) {
            const n = chars.length;
            const taken = {};
            s.idx.forEach(function (i, k) { taken[i] = k; });

            for (let i = 0; i < n; i++) {
                const isIn = taken[i] !== undefined;
                const isStop = !s.error && s.stop === i;
                let cls = CELL_BASE + ' ' + (isIn ? CELL_IN : (isStop ? CELL_STOP : CELL_OUT));
                if (hover === i) cls += HILITE;
                cells[i].className = cls;
                idxLabels[i].className = COL_W + ' text-[11px] ' + (isIn
                    ? 'text-emerald-600 dark:text-emerald-400'
                    : 'text-gray-400 dark:text-slate-500');
                negLabels[i].className = COL_W + ' text-[11px] ' + (isIn
                    ? 'text-emerald-600 dark:text-emerald-400'
                    : 'text-gray-400 dark:text-slate-500');
                ordLabels[i].textContent = isIn ? String(taken[i]) : '';
            }

            Object.keys(markCells).forEach(function (key) {
                markCells[key].innerHTML = '';
            });
            if (s.error) return;
            const marks = {};
            marks[s.start] = ['<span class="text-emerald-600 dark:text-emerald-400">start</span>'];
            if (marks[s.stop]) marks[s.stop].push('<span class="text-rose-500">stop</span>');
            else marks[s.stop] = ['<span class="text-rose-500">stop</span>'];
            Object.keys(marks).forEach(function (key) {
                const slot = markCells[key];
                if (slot) slot.innerHTML = marks[key].join('<br>');
            });
        }

        function paintResult(s) {
            if (s.error) {
                resultLine.innerHTML = '<span class="font-mono">' + escapeHtml(exprText()) +
                    '</span> → <span class="text-rose-500">ValueError: slice step cannot be zero</span>';
                return;
            }
            const out = s.idx.map(function (i) { return shown(chars[i]); }).join('');
            resultLine.innerHTML = '<span class="text-gray-500 dark:text-slate-400">' +
                escapeHtml(exprText()) + '</span> → <b>' + escapeHtml(repr(out)) +
                '</b> <span class="text-sm text-gray-400 dark:text-slate-500">(' +
                s.idx.length + ' симв.)</span>';
        }

        function paintHint(s) {
            if (hover === null) {
                hintLine.textContent = 'Наведите на символ — покажу его индексы и то, ' +
                    'почему он попал или не попал в срез.';
                return;
            }
            const n = chars.length;
            const i = hover;
            const head = 'Символ ' + repr(chars[i]) + ': это и <span class="font-mono">s[' + i +
                ']</span>, и <span class="font-mono">s[' + (i - n) + ']</span> — одно и то же место. ';
            if (s.error) {
                hintLine.innerHTML = head;
                return;
            }
            const k = s.idx.indexOf(i);
            if (k !== -1) {
                const how = s.step === 1
                    ? ''
                    : ' (' + num(s.start) + ' + ' + k + ' · ' + num(s.step) + ' = ' + i + ')';
                hintLine.innerHTML = head + 'В срез попал: это символ №' + k + ' результата' + how + '.';
                return;
            }
            let why;
            if (s.step > 0) {
                if (i < s.start) why = 'он левее start = ' + num(s.start) + '.';
                else if (i >= s.stop) why = 'stop = ' + num(s.stop) + ', а правая граница не включается.';
                else why = 'шаг ' + num(s.step) + ' перешагнул через него.';
            } else if (i > s.start) {
                why = 'при отрицательном шаге идём справа налево от start = ' + num(s.start) +
                    ', а он правее.';
            } else if (i <= s.stop) {
                why = 'stop = ' + num(s.stop) + ', а граница не включается.';
            } else {
                why = 'шаг ' + num(s.step) + ' перешагнул через него.';
            }
            hintLine.innerHTML = head + 'В срез не попал: ' + why;
        }

        function paintNote(s) {
            const n = chars.length;
            if (s.error) {
                noteLine.innerHTML = 'Шаг 0 запрещён: с нулевым шагом срез никогда не дошёл бы ' +
                    'до правой границы. Python сообщает об этом ошибкой ' +
                    '<span class="font-mono">ValueError</span>.';
                return;
            }
            const parts = [];

            parts.push(s.step > 0
                ? 'Идём <b>слева направо</b> от позиции ' + num(s.start) + ' и останавливаемся, ' +
                  'не дойдя до позиции ' + num(s.stop) + '; шаг ' + num(s.step) + '.'
                : 'Шаг отрицательный, поэтому идём <b>справа налево</b> от позиции ' + num(s.start) +
                  ' и останавливаемся, не дойдя до позиции ' + num(s.stop) + '.');

            if (slStart === null) {
                parts.push('Граница <span class="font-mono">start</span> опущена — Python взял ' +
                    (s.step > 0 ? 'начало строки.' : 'конец строки.'));
            } else if (slStart < 0 && slStart >= -n) {
                parts.push('<span class="font-mono">start = ' + slStart + '</span> — счёт с конца: ' +
                    'это позиция ' + n + ' − ' + Math.abs(slStart) + ' = ' + (slStart + n) + '.');
            }
            if (slStop === null) {
                parts.push('Граница <span class="font-mono">stop</span> опущена — срез идёт до ' +
                    (s.step > 0 ? 'конца строки.' : 'самого начала, включая нулевой символ.'));
            } else if (slStop < 0 && slStop >= -n) {
                parts.push('<span class="font-mono">stop = ' + slStop + '</span> — счёт с конца: ' +
                    'это позиция ' + n + ' − ' + Math.abs(slStop) + ' = ' + (slStop + n) + '.');
            }

            // Обрезка границ — самое неочевидное место: показываем её явно.
            const outOfRange = (slStart !== null && (slStart >= n || slStart < -n)) ||
                (slStop !== null && (slStop > n || slStop < -n));
            if (outOfRange) {
                parts.push('Граница вышла за пределы строки — это <b>не ошибка</b>: ' +
                    'в отличие от индекса, срез просто обрезается по краю строки.');
            }

            if (s.idx.length === 0) {
                parts.push('Результат <b>пустой</b>: при таких границах не нашлось ни одной позиции, ' +
                    'по которой можно было бы шагнуть.');
            } else if (s.step === 1 && slStart !== null && slStop !== null &&
                s.start === (slStart < 0 ? slStart + n : slStart) &&
                s.stop === (slStop < 0 ? slStop + n : slStop)) {
                parts.push('Длина среза — ровно <span class="font-mono">stop − start</span> = ' +
                    num(s.stop) + ' − ' + num(s.start) + ' = ' + s.idx.length + '.');
            }

            noteLine.innerHTML = parts.join(' ');
        }

        // fromInput: не трогаем поля ввода, чтобы не сбивать курсор.
        function paint(fromInput) {
            const s = resolve();
            paintTape(s);
            paintResult(s);
            paintHint(s);
            paintNote(s);
            stepButtons.forEach(function (item) {
                item.btn.className = (slStep === item.step) ? btnActive : btnChip;
            });
            [startCtl, stopCtl, stepCtl].forEach(function (ctl) {
                const v = ctl.get();
                if (!fromInput) ctl.input.value = v === null ? '' : String(v);
                ctl.clear.className = v === null ? btnActive : btnChip;
            });
            if (!fromInput) strInput.value = chars.join('');
        }

        // structural: длина строки изменилась, ленту надо пересобрать.
        function render(structural, fromInput) {
            if (structural || cells.length !== chars.length) buildTape();
            paint(fromInput);
        }

        render(true);
    });

    // ─────────────────────────────────────────────────────────────
    // Виджет: growth-curves — кривые роста числа действий.
    // Главная мысль: важна не величина числа действий, а форма роста.
    // Поэтому у виджета две шкалы и подвижная правая граница: на N ≤ 20
    // кривые лежат почти рядом (разницы «не видно»), а на N = 1000 они
    // расходятся необозримо. Логарифмическая шкала показывает, что дело
    // не в масштабе картинки: классы отличаются порядком величины.
    // Курсор (ползунок или мышь по графику) даёт таблицу: сколько действий
    // у каждого класса при этом N, сколько это времени при ~10^7 операций
    // в секунду и какой N этот класс успевает переварить за секунду.
    // Кривая «100·N» лежит в реестре отдельно от O(N) намеренно — на ней
    // видно, что постоянный множитель решает исход только до точки
    // пересечения с N², то есть только на маленьких данных.
    // Конфиг: { "curves": ["logn","n","nlogn","n2"], "maxN": 100,
    //           "cursor": 50, "log": false,
    //           "presets": [{"title":"…","curves":[…],"maxN":10,
    //                        "cursor":10,"log":true}] } — до 6 пресетов.
    // Доступные ключи кривых: 1, logn, n, nlogn, n2, 2n, 100n.
    // ─────────────────────────────────────────────────────────────
    register('growth-curves', function (el, config) {
        const SVG_NS = 'http://www.w3.org/2000/svg';
        const OPS_PER_SEC = 1e7;                       // грубая оценка из урока 10.1
        const STOPS = [10, 20, 50, 100, 200, 500, 1000, 10000, 1000000];
        const LOG2 = Math.LN2;
        const LG2 = Math.LOG10E * Math.LN2;            // log10(2) ≈ 0,30103

        function lb(n) { return Math.max(1, Math.log(n) / LOG2); }   // log2, но не меньше 1

        // f — число действий (может уйти в Infinity), l10 — его десятичный
        // логарифм. Рисуем и считаем по l10 везде, где f переполняется.
        const CURVES = [
            {
                key: '1', label: 'O(1)', color: 'emerald',
                f: function () { return 1; },
                l10: function () { return 0; },
            },
            {
                key: 'logn', label: 'O(log N)', color: 'cyan',
                f: function (n) { return lb(n); },
                l10: function (n) { return Math.log(lb(n)) * Math.LOG10E; },
            },
            {
                key: 'n', label: 'O(N)', color: 'blue',
                f: function (n) { return n; },
                l10: function (n) { return Math.log(n) * Math.LOG10E; },
            },
            {
                key: 'nlogn', label: 'O(N log N)', color: 'violet',
                f: function (n) { return n * lb(n); },
                l10: function (n) { return (Math.log(n) + Math.log(lb(n))) * Math.LOG10E; },
            },
            {
                key: 'n2', label: 'O(N²)', color: 'amber',
                f: function (n) { return n * n; },
                l10: function (n) { return 2 * Math.log(n) * Math.LOG10E; },
            },
            {
                key: '2n', label: 'O(2^N)', color: 'rose',
                f: function (n) { return Math.pow(2, n); },
                l10: function (n) { return n * LG2; },
            },
            {
                key: '100n', label: '100·N', color: 'slate', note: 'тоже O(N)',
                f: function (n) { return 100 * n; },
                l10: function (n) { return 2 + Math.log(n) * Math.LOG10E; },
            },
        ];

        const PALETTE = {
            emerald: {
                stroke: 'stroke-emerald-500 dark:stroke-emerald-400',
                fill: 'fill-emerald-500 dark:fill-emerald-400',
                text: 'text-emerald-600 dark:text-emerald-400',
                on: 'bg-emerald-500 text-white border-emerald-500',
            },
            cyan: {
                stroke: 'stroke-cyan-500 dark:stroke-cyan-400',
                fill: 'fill-cyan-500 dark:fill-cyan-400',
                text: 'text-cyan-600 dark:text-cyan-400',
                on: 'bg-cyan-500 text-white border-cyan-500',
            },
            blue: {
                stroke: 'stroke-blue-500 dark:stroke-blue-400',
                fill: 'fill-blue-500 dark:fill-blue-400',
                text: 'text-blue-600 dark:text-blue-400',
                on: 'bg-blue-500 text-white border-blue-500',
            },
            violet: {
                stroke: 'stroke-violet-500 dark:stroke-violet-400',
                fill: 'fill-violet-500 dark:fill-violet-400',
                text: 'text-violet-600 dark:text-violet-400',
                on: 'bg-violet-500 text-white border-violet-500',
            },
            amber: {
                stroke: 'stroke-amber-500 dark:stroke-amber-400',
                fill: 'fill-amber-500 dark:fill-amber-400',
                text: 'text-amber-600 dark:text-amber-400',
                on: 'bg-amber-500 text-white border-amber-500',
            },
            rose: {
                stroke: 'stroke-rose-500 dark:stroke-rose-400',
                fill: 'fill-rose-500 dark:fill-rose-400',
                text: 'text-rose-600 dark:text-rose-400',
                on: 'bg-rose-500 text-white border-rose-500',
            },
            slate: {
                stroke: 'stroke-slate-400 dark:stroke-slate-400',
                fill: 'fill-slate-400 dark:fill-slate-400',
                text: 'text-slate-500 dark:text-slate-400',
                on: 'bg-slate-500 text-white border-slate-500',
            },
        };

        const chip = 'px-2.5 py-1 rounded-full text-xs border transition-colors bg-gray-50 text-gray-500 border-gray-200 hover:bg-gray-100 dark:bg-slate-700 dark:border-slate-600 dark:text-slate-300';
        const chipOn = 'px-2.5 py-1 rounded-full text-xs border transition-colors ';
        const chipActive = 'px-2.5 py-1 rounded-full text-xs border transition-colors bg-brand-600 text-white border-brand-600 dark:bg-cyan-500 dark:border-cyan-500';

        function curveByKey(key) {
            for (let i = 0; i < CURVES.length; i++) {
                if (CURVES[i].key === String(key)) return CURVES[i];
            }
            return null;
        }

        function normCurves(raw, fallback) {
            const list = [];
            (Array.isArray(raw) ? raw : []).forEach(function (k) {
                const c = curveByKey(k);
                if (c && list.indexOf(c.key) === -1) list.push(c.key);
            });
            return list.length ? list : fallback.slice();
        }

        function snapStop(raw, fallback) {
            const n = parseInt(raw, 10);
            if (isNaN(n)) return fallback;
            let best = STOPS[0];
            for (let i = 0; i < STOPS.length; i++) {
                if (Math.abs(Math.log(STOPS[i]) - Math.log(Math.max(n, 1))) <
                    Math.abs(Math.log(best) - Math.log(Math.max(n, 1)))) best = STOPS[i];
            }
            return best;
        }

        let shown = normCurves(config.curves, ['logn', 'n', 'nlogn', 'n2']);
        let maxN = snapStop(config.maxN, 100);
        let logScale = config.log === true;
        let cursor = Math.min(Math.max(parseInt(config.cursor, 10) || Math.round(maxN / 2), 1), maxN);

        const presets = (Array.isArray(config.presets) ? config.presets : [])
            .filter(function (p) { return p && p.title; })
            .slice(0, 6);

        // ── числа и время ────────────────────────────────────────
        const SUPS = '⁰¹²³⁴⁵⁶⁷⁸⁹';

        function sup(n) {
            return String(Math.round(n)).split('').map(function (ch) {
                return ch === '-' ? '⁻' : SUPS[Number(ch)];
            }).join('');
        }

        function group(n) {
            const s = String(Math.round(n));
            let out = '';
            for (let i = 0; i < s.length; i++) {
                if (i > 0 && (s.length - i) % 3 === 0) out += ' ';
                out += s[i];
            }
            return out;
        }

        // Всё, что не влезает в обычную запись, показываем как 10^k:
        // «2 в степени миллион» цифрами не выписывают.
        function fmtOps(v, l) {
            if (l > 15 || !isFinite(v)) return '≈ 10' + sup(l);
            if (v < 10) return String(Math.round(v * 10) / 10).replace('.', ',');
            return group(v);
        }

        function one(x) { return (Math.round(x * 10) / 10).toString().replace('.', ','); }

        function fmtTime(v, l) {
            const ls = l - 7;                       // log10 секунд при 10^7 операций/с
            if (ls > 10) {
                const ly = ls - Math.log(3.15e7) * Math.LOG10E;
                return '≈ 10' + sup(ly) + ' лет';
            }
            const s = v / OPS_PER_SEC;
            if (s < 1e-6) return 'мгновенно';
            if (s < 1e-3) return Math.round(s * 1e6) + ' мкс';
            if (s < 1) return (s * 1e3 < 10 ? one(s * 1e3) : String(Math.round(s * 1e3))) + ' мс';
            if (s < 60) return one(s) + ' с';
            if (s < 3600) return Math.round(s / 60) + ' мин';
            if (s < 86400) return one(s / 3600) + ' ч';
            if (s < 86400 * 365) return Math.round(s / 86400) + ' дней';
            return group(s / 3.15e7) + ' лет';
        }

        // Наибольший N, который класс успевает обработать за секунду.
        // Кривые монотонны, поэтому обычная двоичная прикидка по l10.
        function feasibleN(c) {
            const limit = Math.log(OPS_PER_SEC) * Math.LOG10E;
            if (c.l10(1e18) <= limit) return Infinity;
            let lo = 1;
            let hi = 2;
            while (hi < 1e18 && c.l10(hi) <= limit) hi *= 2;
            while (hi - lo > 1) {
                const mid = Math.floor((lo + hi) / 2);
                if (c.l10(mid) <= limit) lo = mid; else hi = mid;
            }
            return lo;
        }

        // ── геометрия ────────────────────────────────────────────
        const W = 760, H = 320;
        const X0 = 68, X1 = 690, YT = 20, YB = 262;

        function xOf(n) { return X0 + (n - 1) / Math.max(1, maxN - 1) * (X1 - X0); }
        function nOf(x) { return 1 + (x - X0) / (X1 - X0) * Math.max(1, maxN - 1); }

        function niceUp(v) {
            if (!(v > 0)) return 100;
            const e = Math.floor(Math.log(v) * Math.LOG10E);
            const m = v / Math.pow(10, e);
            const nm = m <= 1 ? 1 : (m <= 2 ? 2 : (m <= 5 ? 5 : 10));
            return nm * Math.pow(10, e);
        }

        // Потолок линейной шкалы. Берём наибольшее значение в правом краю
        // графика, но если одна кривая улетела на порядки выше остальных
        // (типично для 2^N), она бы прижала все прочие к оси — тогда режем
        // потолок по срединной кривой, а выскочка честно уходит за верх поля.
        function yLimits() {
            if (logScale) {
                let top = 1;
                shown.forEach(function (k) { top = Math.max(top, curveByKey(k).l10(maxN)); });
                return { maxLog: Math.min(Math.max(Math.ceil(top), 2), 15) };
            }
            const vals = shown.map(function (k) { return curveByKey(k).f(maxN); })
                .filter(function (v) { return isFinite(v); })
                .sort(function (a, b) { return a - b; });
            if (!vals.length) return { max: 100 };
            const top = vals[vals.length - 1];
            const mid = vals[Math.floor(vals.length / 2)];
            return { max: niceUp(top > 30 * mid ? 3 * mid : top) };
        }

        function yOf(v, l, lim) {
            if (logScale) {
                const t = Math.min(Math.max(l, 0), lim.maxLog) / lim.maxLog;
                return YB - t * (YB - YT);
            }
            return YB - Math.min(v, lim.max) / lim.max * (YB - YT);
        }

        function svgEl(name, attrs) {
            const node = document.createElementNS(SVG_NS, name);
            Object.keys(attrs || {}).forEach(function (k) { node.setAttribute(k, attrs[k]); });
            return node;
        }

        function tickLabel(v) {
            if (v >= 1e6) return '10' + sup(Math.log(v) * Math.LOG10E);
            return group(v);
        }

        // ── разметка ─────────────────────────────────────────────
        const body = widgetFrame(el, el.dataset.title);

        const presetRow = document.createElement('div');
        presetRow.className = 'flex flex-wrap items-center gap-2 justify-center mb-4';
        presets.forEach(function (p) {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.textContent = p.title;
            btn.className = chip;
            btn.addEventListener('click', function () {
                shown = normCurves(p.curves, shown);
                maxN = snapStop(p.maxN, maxN);
                if (p.log !== undefined) logScale = p.log === true;
                cursor = Math.min(Math.max(parseInt(p.cursor, 10) || maxN, 1), maxN);
                render();
            });
            presetRow.appendChild(btn);
        });

        const curveRow = document.createElement('div');
        curveRow.className = 'flex flex-wrap items-center gap-2 justify-center mb-4';
        const curveBtns = CURVES.map(function (c) {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.textContent = c.label.replace('^N', 'ᴺ');
            btn.addEventListener('click', function () {
                const at = shown.indexOf(c.key);
                if (at === -1) shown.push(c.key); else shown.splice(at, 1);
                render();
            });
            btn._refresh = function () {
                btn.className = shown.indexOf(c.key) === -1
                    ? chip
                    : chipOn + PALETTE[c.color].on;
            };
            curveRow.appendChild(btn);
            return btn;
        });

        function slider(labelText, lo, hi, get, set) {
            const row = document.createElement('div');
            row.className = 'flex items-center gap-3';
            const label = document.createElement('span');
            label.className = 'text-xs text-gray-500 dark:text-slate-400 w-40 shrink-0';
            label.textContent = labelText;
            const input = document.createElement('input');
            input.type = 'range';
            input.min = String(lo);
            input.max = String(hi);
            input.step = '1';
            input.className = 'flex-1 accent-brand-600 dark:accent-cyan-500';
            input.setAttribute('aria-label', labelText);
            input.addEventListener('input', function () {
                set(parseInt(input.value, 10));
                render();
            });
            const value = document.createElement('b');
            value.className = 'text-sm font-mono text-gray-900 dark:text-white w-28 text-right shrink-0';
            row.appendChild(label);
            row.appendChild(input);
            row.appendChild(value);
            row._input = input;
            row._refresh = function (text, hiNow) {
                if (hiNow !== undefined) input.max = String(hiNow);
                input.value = String(get());
                value.textContent = text;
            };
            return row;
        }

        const rangeRow = slider('Правая граница графика', 0, STOPS.length - 1,
            function () { return STOPS.indexOf(maxN); },
            function (v) {
                maxN = STOPS[Math.min(Math.max(v, 0), STOPS.length - 1)];
                cursor = Math.min(cursor, maxN);
            });

        const cursorRow = slider('Размер данных N', 1, maxN,
            function () { return cursor; },
            function (v) { cursor = Math.min(Math.max(v, 1), maxN); });

        const sliders = document.createElement('div');
        sliders.className = 'flex flex-col gap-2 mb-4';
        sliders.appendChild(rangeRow);
        sliders.appendChild(cursorRow);

        const scaleBtn = document.createElement('button');
        scaleBtn.type = 'button';
        scaleBtn.textContent = 'Логарифмическая шкала';
        scaleBtn.addEventListener('click', function () {
            logScale = !logScale;
            render();
        });
        scaleBtn._refresh = function () {
            scaleBtn.className = logScale ? chipActive : chip;
        };

        const scaleRow = document.createElement('div');
        scaleRow.className = 'flex flex-wrap items-center gap-2 justify-center mb-4';
        scaleRow.appendChild(scaleBtn);

        const plot = document.createElement('div');
        plot.className = 'overflow-x-auto';

        const hint = document.createElement('div');
        hint.className = 'mt-2 text-center text-xs text-gray-400 dark:text-slate-500';

        const tableWrap = document.createElement('div');
        tableWrap.className = 'mt-4 overflow-x-auto';

        if (presets.length) body.appendChild(presetRow);
        body.appendChild(curveRow);
        body.appendChild(sliders);
        body.appendChild(scaleRow);
        body.appendChild(plot);
        body.appendChild(hint);
        body.appendChild(tableWrap);

        // ── график ───────────────────────────────────────────────
        function drawPlot(lim) {
            plot.innerHTML = '';
            const svg = svgEl('svg', {
                viewBox: '0 0 ' + W + ' ' + H,
                width: W, height: H,
                class: 'block mx-auto w-full h-auto min-w-[680px] cursor-crosshair'
            });

            // горизонтальные линии сетки с подписями
            const rows = [];
            if (logScale) {
                const stepDec = Math.ceil(lim.maxLog / 6);
                for (let d = 0; d <= lim.maxLog; d += stepDec) {
                    rows.push({ y: yOf(Math.pow(10, d), d, lim), text: d <= 5 ? group(Math.pow(10, d)) : '10' + sup(d) });
                }
            } else {
                for (let i = 0; i <= 4; i++) {
                    const v = lim.max * i / 4;
                    rows.push({ y: yOf(v, 0, lim), text: tickLabel(v) });
                }
            }
            rows.forEach(function (r) {
                svg.appendChild(svgEl('line', {
                    x1: X0, y1: r.y, x2: X1, y2: r.y,
                    class: 'stroke-gray-200 dark:stroke-slate-700', 'stroke-width': 1
                }));
                const cap = svgEl('text', {
                    x: X0 - 8, y: r.y + 4, 'text-anchor': 'end',
                    class: 'fill-gray-400 dark:fill-slate-500',
                    'font-size': 10, 'font-family': 'monospace'
                });
                cap.textContent = r.text;
                svg.appendChild(cap);
            });

            // «бюджет секунды» — 10^7 действий
            const budgetL = Math.log(OPS_PER_SEC) * Math.LOG10E;
            const budgetIn = logScale ? budgetL <= lim.maxLog : OPS_PER_SEC <= lim.max;
            if (budgetIn) {
                const y = yOf(OPS_PER_SEC, budgetL, lim);
                svg.appendChild(svgEl('line', {
                    x1: X0, y1: y, x2: X1, y2: y,
                    class: 'stroke-rose-400 dark:stroke-rose-400',
                    'stroke-width': 1.5, 'stroke-dasharray': '6 4'
                }));
                const cap = svgEl('text', {
                    x: X0 + 6, y: y - 6,
                    class: 'fill-rose-500 dark:fill-rose-400', 'font-size': 11
                });
                cap.textContent = '10 000 000 действий ≈ 1 секунда';
                svg.appendChild(cap);
            }

            // ось N
            svg.appendChild(svgEl('line', {
                x1: X0, y1: YB, x2: X1, y2: YB,
                class: 'stroke-gray-300 dark:stroke-slate-600', 'stroke-width': 1
            }));
            for (let i = 0; i <= 4; i++) {
                const n = Math.round(1 + (maxN - 1) * i / 4);
                const x = xOf(n);
                svg.appendChild(svgEl('line', {
                    x1: x, y1: YB, x2: x, y2: YB + 5,
                    class: 'stroke-gray-300 dark:stroke-slate-600', 'stroke-width': 1
                }));
                const cap = svgEl('text', {
                    x: x, y: YB + 18, 'text-anchor': 'middle',
                    class: 'fill-gray-400 dark:fill-slate-500',
                    'font-size': 10, 'font-family': 'monospace'
                });
                cap.textContent = tickLabel(n);
                svg.appendChild(cap);
            }
            const axisCap = svgEl('text', {
                x: (X0 + X1) / 2, y: H - 6, 'text-anchor': 'middle',
                class: 'fill-gray-400 dark:fill-slate-500', 'font-size': 11
            });
            axisCap.textContent = 'размер данных N';
            svg.appendChild(axisCap);

            const yCap = svgEl('text', {
                x: X0 - 8, y: YT - 6, 'text-anchor': 'end',
                class: 'fill-gray-400 dark:fill-slate-500', 'font-size': 11
            });
            yCap.textContent = 'действий';
            svg.appendChild(yCap);

            // курсор
            svg.appendChild(svgEl('line', {
                x1: xOf(cursor), y1: YT, x2: xOf(cursor), y2: YB,
                class: 'stroke-gray-400 dark:stroke-slate-500',
                'stroke-width': 1, 'stroke-dasharray': '3 4'
            }));

            // кривые
            const COLS = 200;
            const labels = [];
            shown.forEach(function (key) {
                const c = curveByKey(key);
                const pal = PALETTE[c.color];
                const d = [];
                let endX = X0, endY = YB;
                for (let i = 0; i <= COLS; i++) {
                    const n = 1 + (maxN - 1) * i / COLS;
                    const v = c.f(n);
                    const l = c.l10(n);
                    const over = logScale ? l > lim.maxLog : v > lim.max;
                    const x = xOf(n);
                    const y = yOf(v, l, lim);
                    d.push((d.length ? 'L' : 'M') + x.toFixed(1) + ' ' + y.toFixed(1));
                    endX = x;
                    endY = y;
                    if (over) break;              // кривая ушла за верх поля
                }
                svg.appendChild(svgEl('path', {
                    d: d.join(' '), fill: 'none',
                    class: pal.stroke, 'stroke-width': 2.5,
                    'stroke-linejoin': 'round', 'stroke-linecap': 'round'
                }));
                labels.push({ x: endX, y: endY, text: c.label.replace('^N', 'ᴺ'), cls: pal.fill });

                // точка на пересечении с курсором
                const cv = c.f(cursor);
                const cl = c.l10(cursor);
                const inside = logScale ? cl <= lim.maxLog : cv <= lim.max;
                if (inside) {
                    svg.appendChild(svgEl('circle', {
                        cx: xOf(cursor), cy: yOf(cv, cl, lim), r: 4, class: pal.fill
                    }));
                }
            });

            // подписи кривых у правого края, разведённые по вертикали
            labels.sort(function (a, b) { return a.y - b.y; });
            for (let i = 1; i < labels.length; i++) {
                if (labels[i].y - labels[i - 1].y < 13) labels[i].y = labels[i - 1].y + 13;
            }
            labels.forEach(function (lbl) {
                const t = svgEl('text', {
                    x: Math.min(lbl.x + 8, X1 + 8),
                    y: Math.min(Math.max(lbl.y + 4, YT + 4), H - 24),
                    class: lbl.cls, 'font-size': 11, 'font-family': 'monospace'
                });
                t.textContent = lbl.text;
                svg.appendChild(t);
            });

            svg.addEventListener('mousemove', function (e) {
                const rect = svg.getBoundingClientRect();
                if (!rect.width) return;
                const x = (e.clientX - rect.left) / rect.width * W;
                const n = Math.round(nOf(x));
                if (n < 1 || n > maxN || n === cursor) return;
                cursor = n;
                render();
            });

            plot.appendChild(svg);
        }

        // ── таблица под графиком ─────────────────────────────────
        function drawTable() {
            tableWrap.innerHTML = '';
            if (!shown.length) {
                tableWrap.innerHTML = '<p class="text-center text-sm text-gray-400 dark:text-slate-500">' +
                    'Выберите хотя бы одну кривую.</p>';
                return;
            }
            const table = document.createElement('table');
            table.className = 'w-full text-sm border-collapse';
            const head = document.createElement('thead');
            head.innerHTML =
                '<tr class="text-gray-400 dark:text-slate-500 text-xs">' +
                '<th class="text-left font-normal py-1 pr-3">сложность</th>' +
                '<th class="text-right font-normal py-1 pr-3">действий при N = ' + group(cursor) + '</th>' +
                '<th class="text-right font-normal py-1 pr-3">это примерно</th>' +
                '<th class="text-right font-normal py-1">N за 1 секунду</th>' +
                '</tr>';
            table.appendChild(head);

            const tbody = document.createElement('tbody');
            const rows = shown.map(function (k) { return curveByKey(k); });
            rows.sort(function (a, b) { return a.l10(cursor) - b.l10(cursor); });
            rows.forEach(function (c) {
                const v = c.f(cursor);
                const l = c.l10(cursor);
                const lim = feasibleN(c);
                const tr = document.createElement('tr');
                tr.className = 'border-t border-gray-100 dark:border-slate-700';
                tr.innerHTML =
                    '<td class="py-1.5 pr-3 font-mono ' + PALETTE[c.color].text + '">' +
                    escapeHtml(c.label.replace('^N', 'ᴺ')) +
                    (c.note ? ' <span class="text-xs text-gray-400 dark:text-slate-500">(' +
                        escapeHtml(c.note) + ')</span>' : '') + '</td>' +
                    '<td class="py-1.5 pr-3 text-right font-mono text-gray-900 dark:text-white">' +
                    escapeHtml(fmtOps(v, l)) + '</td>' +
                    '<td class="py-1.5 pr-3 text-right text-gray-600 dark:text-slate-300">' +
                    escapeHtml(fmtTime(v, l)) + '</td>' +
                    '<td class="py-1.5 text-right font-mono text-gray-600 dark:text-slate-300">' +
                    (lim === Infinity ? 'любой' : escapeHtml(group(lim))) + '</td>';
                tbody.appendChild(tr);
            });
            table.appendChild(tbody);
            tableWrap.appendChild(table);
        }

        function drawHint() {
            if (!shown.length) { hint.textContent = ''; return; }
            if (logScale) {
                hint.textContent = 'Логарифмическая шкала: каждая горизонталь больше предыдущей ' +
                    'в 10 раз. Прямая на такой шкале — не «медленный рост», а постоянная кратность.';
            } else if (maxN <= 20) {
                hint.textContent = 'Данных мало — кривые лежат почти рядом, и выбор алгоритма ' +
                    'ни на что не влияет. Сдвиньте правую границу вправо.';
            } else {
                hint.textContent = 'Красный пунктир — бюджет в 10 000 000 действий (≈ секунда работы). ' +
                    'Где кривая его пересекает, там для этого класса кончаются посильные данные.';
            }
        }

        function render() {
            const lim = yLimits();
            drawPlot(lim);
            drawTable();
            drawHint();
            curveBtns.forEach(function (b) { b._refresh(); });
            scaleBtn._refresh();
            rangeRow._refresh('N до ' + group(maxN));
            cursorRow._refresh('N = ' + group(cursor), maxN);
        }

        render();
    });

    // ─────────────────────────────────────────────────────────────
    // Виджет: sort-bars — сортировка на столбиках (блок 11).
    // Массив рисуется столбиками разной высоты; виджет сам прогоняет
    // алгоритм и раскладывает его в кадры: сравнение пары, обмен, конец
    // прохода, готово. В каждом кадре лежит полный снимок массива, поэтому
    // шаг назад и ползунок работают без пересчёта (как в loop-trace).
    //
    // Что видно: подсвеченные элементы с ролями (роль решает цвет столбика),
    // метки под ними — те же имена переменных, что в коде урока, — зелёная
    // зона уже расставленных элементов, счётчики сравнений и обменов, номер
    // прохода. Зона готового растёт с того края, с которого её наращивает
    // алгоритм: у пузырька справа (sortedFrom), у выбора слева (sortedTo).
    //
    // Конфиг: { "values": [5,1,4,2,8,3], "algo": "bubble", "flag": false,
    //           "speed": 600,
    //           "presets": [{"title": "Обратный порядок",
    //                        "values": [9,7,6,4,3,1], "flag": true}] }
    // values — от 3 до 16 чисел 1..99; algo — "bubble", "selection",
    // "insertion" или "quick"; flag — «выходить, если за проход не было ни
    // одного обмена» (тумблер доступен и мышью, показывается только у
    // алгоритмов с hasFlag); presets — до 6 наборов.
    //
    // Новый алгоритм блока добавляется одной функцией в ALGOS: она получает
    // массив и возвращает список кадров. Кадр — полный снимок:
    //   { arr, kind, note, comps, swaps, pass, sortedFrom, sortedTo,
    //     roles: {индекс: 'cur'|'min'|'swap'|'hole'},
    //     marks: {индекс: 'j'|'i=m'|…},
    //     hole: индекс дырки или -1, hand: значение «в руке» или null,
    //     done: {индекс: true}, seg: [lo, hi] или null }
    // kind используется только кнопкой «Проход целиком» ('pass'/'done').
    // Поля hole/hand нужны алгоритмам, которые вынимают элемент из списка
    // (вставки): у записи в ALGOS тогда стоит hand: true, столбик с ролью
    // 'hole' рисуется пунктирным контуром, а над полем видно, что в руке.
    // Поля done/seg нужны быстрой сортировке: окончательные места достаются
    // опорным элементам вразнобой (сплошного края, как sortedFrom/sortedTo,
    // не получается), а работа идёт по отрезку — всё вне seg притушено.
    // moveLabel меняет подпись счётчика: у вставок это не обмены, а сдвиги;
    // passWord/passIdle/passBtn меняют слово «проход» — у быстрой сортировки
    // единица работы называется разбиением.
    // ─────────────────────────────────────────────────────────────
    register('sort-bars', function (el, config) {
        const MINN = 3, MAXN = 16;
        const DEFAULT_VALUES = [5, 1, 4, 2, 8, 3];

        function normValues(raw, fallback) {
            const list = (Array.isArray(raw) ? raw : [])
                .map(function (v) { return Math.round(Number(v)); })
                .filter(function (v) { return isFinite(v) && v >= 1 && v <= 99; })
                .slice(0, MAXN);
            return list.length >= MINN ? list : fallback.slice();
        }

        // «1 сравнение», «2 сравнения», «5 сравнений»
        function plural(n, one, few, many) {
            const d10 = n % 10, d100 = n % 100;
            if (d10 === 1 && d100 !== 11) return n + ' ' + one;
            if (d10 >= 2 && d10 <= 4 && (d100 < 12 || d100 > 14)) return n + ' ' + few;
            return n + ' ' + many;
        }

        // Слова для второго счётчика: у пузырька и выбора это обмены,
        // у вставок — сдвиги (элемент едет вправо в одиночку, не меняясь
        // ни с кем местами).
        const WORDS_SWAP = ['обмен', 'обмена', 'обменов'];
        const WORDS_SHIFT = ['сдвиг', 'сдвига', 'сдвигов'];

        function totals(comps, moves, words) {
            const w = words || WORDS_SWAP;
            return plural(comps, 'сравнение', 'сравнения', 'сравнений') + ' и ' +
                plural(moves, w[0], w[1], w[2]);
        }

        // Роли столбиков: {индекс: роль}. Позже указанная роль перебивает
        // раньше указанную — это удобно, когда два имени смотрят в одну ячейку.
        function roleMap(pairs) {
            const out = {};
            pairs.forEach(function (p) {
                if (p[0] >= 0) out[p[0]] = p[1];
            });
            return out;
        }

        // Метки под столбиками. Если в одну ячейку смотрят два имени сразу
        // (j и m совпали), метки склеиваются: «j=m».
        function markMap(pairs) {
            const out = {};
            pairs.forEach(function (p) {
                if (p[0] < 0) return;
                out[p[0]] = out[p[0]] ? out[p[0]] + '=' + p[1] : p[1];
            });
            return out;
        }

        // Кадры строит алгоритм: каждый кадр — полное состояние массива плюс
        // пояснение, что именно на этом шаге произошло.
        function buildBubble(src, flagOn) {
            const arr = src.slice();
            const n = arr.length;
            const frames = [];
            let comps = 0, swaps = 0, pass = 0, sortedFrom = n;

            function push(kind, roles, marks, note) {
                frames.push({
                    arr: arr.slice(), kind: kind, note: note,
                    roles: roles, marks: marks,
                    comps: comps, swaps: swaps, pass: pass,
                    sortedFrom: sortedFrom, sortedTo: 0,
                });
            }

            push('start', {}, {},
                'Исходный список. Сравнивать и менять местами можно только соседей.');

            for (let i = 0; i < n - 1; i++) {
                pass = i + 1;
                let swappedHere = false;
                for (let j = 0; j < n - 1 - i; j++) {
                    comps++;
                    const x = arr[j], y = arr[j + 1];
                    const marks = markMap([[j, 'j'], [j + 1, 'j+1']]);
                    if (x > y) {
                        push('compare', roleMap([[j, 'cur'], [j + 1, 'cur']]), marks,
                            x + ' > ' + y + ' — порядок нарушен, меняем местами');
                        arr[j] = y;
                        arr[j + 1] = x;
                        swaps++;
                        swappedHere = true;
                        push('swap', roleMap([[j, 'swap'], [j + 1, 'swap']]), marks,
                            'Поменяли: теперь ' + y + ' стоит перед ' + x);
                    } else {
                        push('keep', roleMap([[j, 'cur'], [j + 1, 'cur']]), marks,
                            x + ' ≤ ' + y + ' — порядок не нарушен, идём дальше');
                    }
                }
                sortedFrom = n - 1 - i;
                push('pass', {}, {}, 'Проход ' + pass + ' закончен: число ' + arr[sortedFrom] +
                    ' встало на своё место, дальше хвост не трогаем');
                if (flagOn && !swappedHere) {
                    sortedFrom = 0;
                    push('done', {}, {}, 'За весь проход не было ни одного обмена — значит, ' +
                        'список уже отсортирован. Выходим досрочно, всего ' + totals(comps, swaps));
                    return frames;
                }
            }
            sortedFrom = 0;
            push('done', {}, {}, 'Список отсортирован: ' + totals(comps, swaps));
            return frames;
        }

        // Сортировка выбором (урок 11.3). Отличия от пузырька, которые и надо
        // увидеть: пока идёт поиск минимума, массив не меняется вообще, а
        // обмен случается один раз за проход. Готовая часть растёт слева.
        function buildSelection(src) {
            const arr = src.slice();
            const n = arr.length;
            const frames = [];
            let comps = 0, swaps = 0, pass = 0, sortedTo = 0;

            function push(kind, roles, marks, note) {
                frames.push({
                    arr: arr.slice(), kind: kind, note: note,
                    roles: roles, marks: marks,
                    comps: comps, swaps: swaps, pass: pass,
                    sortedFrom: n, sortedTo: sortedTo,
                });
            }

            push('start', {}, {},
                'Исходный список. Смотреть можно сразу на весь список: ищем в нём минимум.');

            for (let i = 0; i < n - 1; i++) {
                pass = i + 1;
                let m = i;
                push('scan', roleMap([[i, 'min']]), markMap([[i, 'i'], [i, 'm']]),
                    'Проход ' + pass + '. Пока считаем минимумом сам a[' + i + '] = ' + arr[i] +
                    ' — и проверяем весь остаток списка.');
                for (let j = i + 1; j < n; j++) {
                    comps++;
                    const cur = arr[j], best = arr[m];
                    if (cur < best) {
                        push('compare', roleMap([[m, 'min'], [j, 'cur']]),
                            markMap([[i, 'i'], [j, 'j'], [m, 'm']]),
                            cur + ' < ' + best + ' — нашёлся элемент поменьше, минимум переезжает');
                        m = j;
                        push('newmin', roleMap([[m, 'min']]),
                            markMap([[i, 'i'], [j, 'j'], [m, 'm']]),
                            'Теперь минимум — ' + cur + ' на позиции ' + m +
                            '. Столбики не двигались: мы пока только смотрим.');
                    } else {
                        push('keep', roleMap([[m, 'min'], [j, 'cur']]),
                            markMap([[i, 'i'], [j, 'j'], [m, 'm']]),
                            cur + ' ≥ ' + best + ' — минимум прежний, идём дальше');
                    }
                }
                if (m !== i) {
                    push('pick', roleMap([[i, 'cur'], [m, 'min']]),
                        markMap([[i, 'i'], [m, 'm']]),
                        'Остаток просмотрен целиком, минимум в нём — ' + arr[m] +
                        ' на позиции ' + m + '. Меняем его с a[' + i + '] = ' + arr[i] + '.');
                    const t = arr[i];
                    arr[i] = arr[m];
                    arr[m] = t;
                    swaps++;
                    push('swap', roleMap([[i, 'swap'], [m, 'swap']]),
                        markMap([[i, 'i'], [m, 'm']]),
                        'Поменяли: ' + arr[i] + ' сразу встал на своё окончательное место. ' +
                        'Обмен за весь проход один.');
                } else {
                    push('noswap', roleMap([[i, 'min']]), markMap([[i, 'i'], [i, 'm']]),
                        'Минимум остатка и так лежит на позиции ' + i +
                        ' — обмен не нужен, но все сравнения пришлось сделать.');
                }
                sortedTo = i + 1;
                push('pass', {}, {}, 'Проход ' + pass + ' закончен: число ' + arr[i] +
                    ' на своём месте, начало списка больше не трогаем');
            }
            sortedTo = n;
            push('done', {}, {}, 'Список отсортирован: ' + totals(comps, swaps) +
                '. Обменов ровно столько, сколько проходов.');
            return frames;
        }

        // Сортировка вставками (урок 11.4). Отличие, которое надо увидеть:
        // элемент вынимается из списка «в руку», на его месте остаётся
        // дырка, и соседи по одному переезжают в неё вправо. Поэтому здесь
        // считаются не обмены, а сдвиги, а зелёная зона слева — упорядоченное
        // начало, места в котором ещё не окончательные.
        function buildInsertion(src) {
            const arr = src.slice();
            const n = arr.length;
            const frames = [];
            let comps = 0, moves = 0, pass = 0, sortedTo = 1;
            let hole = -1, hand = null;

            function push(kind, roles, marks, note) {
                frames.push({
                    arr: arr.slice(), kind: kind, note: note,
                    roles: roles, marks: marks,
                    comps: comps, swaps: moves, pass: pass,
                    sortedFrom: n, sortedTo: sortedTo,
                    hole: hole, hand: hand,
                });
            }

            push('start', {}, {}, 'Исходный список. Начало из одного элемента ' +
                'уже упорядочено — само с собой оно не спорит.');

            for (let i = 1; i < n; i++) {
                pass = i;
                const key = arr[i];
                hole = i;
                hand = key;
                push('take', roleMap([[i, 'hole']]), markMap([[i, 'key']]),
                    'Проход ' + pass + '. Берём a[' + i + '] = ' + key + ' в руку — ' +
                    'на его месте осталась дырка. Ищем ему место в зелёном начале.');

                let j = i - 1;
                let shifted = 0;
                let stopped = 'edge';
                while (j >= 0) {
                    comps++;
                    if (arr[j] <= key) {
                        push('keep', roleMap([[hole, 'hole'], [j, 'cur']]),
                            markMap([[j, 'j'], [hole, 'key']]),
                            arr[j] + ' ≤ ' + key + ' — дальше влево идти незачем, ' +
                            'место для ' + key + ' найдено');
                        stopped = 'found';
                        break;
                    }
                    push('compare', roleMap([[hole, 'hole'], [j, 'cur']]),
                        markMap([[j, 'j'], [hole, 'key']]),
                        arr[j] + ' > ' + key + ' — значит, ' + arr[j] +
                        ' должен стоять правее, сдвигаем его в дырку');
                    arr[j + 1] = arr[j];
                    moves++;
                    shifted++;
                    hole = j;
                    push('shift', roleMap([[j + 1, 'swap'], [hole, 'hole']]),
                        markMap([[hole, 'key']]),
                        'Сдвинули: ' + arr[j + 1] + ' переехал на позицию ' + (j + 1) +
                        ', дырка сдвинулась влево');
                    j--;
                }

                const landed = hole;
                arr[landed] = key;
                hole = -1;
                hand = null;
                let note;
                if (shifted === 0) {
                    note = key + ' и так стоит правее того, что слева, — кладём его ' +
                        'обратно на своё же место. Сдвигов за проход ни одного.';
                } else if (stopped === 'edge') {
                    note = 'Слева места больше нет: ' + key +
                        ' меньше всего разобранного и встаёт в самое начало.';
                } else {
                    note = 'Кладём ' + key + ' в освободившуюся ячейку — позиция ' +
                        landed + '. Сдвигов на этом проходе: ' + shifted + '.';
                }
                push('place', roleMap([[landed, 'swap']]), markMap([[landed, 'key']]), note);

                sortedTo = i + 1;
                push('pass', {}, {}, 'Проход ' + pass + ' закончен: первые ' +
                    plural(i + 1, 'элемент', 'элемента', 'элементов') +
                    ' упорядочены между собой — но места ещё не окончательные.');
            }
            sortedTo = n;
            push('done', {}, {}, 'Список отсортирован: ' +
                totals(comps, moves, WORDS_SHIFT) + '.');
            return frames;
        }

        // Быстрая сортировка (урок 11.5). Два отличия от всего предыдущего,
        // ради которых виджет и нужен: работа идёт не по всему списку, а по
        // отрезку (остальное притушено), и окончательные места занимают
        // опорные элементы — вразнобой, а не подряд с края. Поэтому здесь
        // вместо sortedFrom/sortedTo заполняется done: {индекс: true}.
        function buildQuick(src) {
            const arr = src.slice();
            const n = arr.length;
            const frames = [];
            const done = {};
            let comps = 0, swaps = 0, pass = 0;
            let seg = null;

            function push(kind, roles, marks, note) {
                const doneCopy = {};
                Object.keys(done).forEach(function (k) { doneCopy[k] = true; });
                frames.push({
                    arr: arr.slice(), kind: kind, note: note,
                    roles: roles, marks: marks,
                    comps: comps, swaps: swaps, pass: pass,
                    sortedFrom: n, sortedTo: 0,
                    done: doneCopy, seg: seg ? seg.slice() : null,
                });
            }

            // Список ещё не разобранных отрезков — тот же, что в коде урока.
            function tasksNote(tasks) {
                if (tasks.length === 0) return 'Неразобранных отрезков не осталось.';
                return 'Ещё не разобрано: ' + tasks.map(function (t) {
                    return t[0] + '…' + t[1];
                }).join(', ') + '.';
            }

            push('start', {}, {}, 'Исходный список. Неразобранный отрезок пока ' +
                'один — весь список целиком.');

            const tasks = [[0, n - 1]];
            while (tasks.length > 0) {
                const task = tasks.pop();
                const lo = task[0], hi = task[1];
                if (lo >= hi) {
                    if (lo === hi) {
                        done[lo] = true;
                        seg = [lo, hi];
                        push('pass', {}, {}, 'Отрезок ' + lo + '…' + hi + ' — это один ' +
                            'элемент, он упорядочен сам по себе. ' + tasksNote(tasks));
                    }
                    continue;
                }

                pass++;
                seg = [lo, hi];
                const pivot = arr[hi];
                push('take', roleMap([[hi, 'min']]), markMap([[hi, 'p']]),
                    'Разбиение ' + pass + ': отрезок ' + lo + '…' + hi +
                    '. Опорным берём последний его элемент — a[' + hi + '] = ' + pivot + '.');

                let i = lo - 1;
                for (let j = lo; j < hi; j++) {
                    comps++;
                    const marks = markMap([[i, 'i'], [j, 'j'], [hi, 'p']]);
                    if (arr[j] < pivot) {
                        push('compare', roleMap([[hi, 'min'], [j, 'cur']]), marks,
                            arr[j] + ' < ' + pivot + ' — элемент меньше опорного, ' +
                            'его место в левой части');
                        i++;
                        const t = arr[i];
                        arr[i] = arr[j];
                        arr[j] = t;
                        swaps++;
                        const marks2 = markMap([[i, 'i'], [j, 'j'], [hi, 'p']]);
                        push('swap', roleMap([[hi, 'min'], [i, 'swap'], [j, 'swap']]), marks2,
                            i === j
                                ? 'Граница сдвинулась на сам этот элемент — он уже ' +
                                  'стоит в левой части, менять его не с кем.'
                                : 'Граница сдвинулась на позицию ' + i + ', и ' + arr[i] +
                                  ' переехал за неё, а ' + arr[j] + ' — на его место.');
                    } else {
                        push('keep', roleMap([[hi, 'min'], [j, 'cur']]), marks,
                            arr[j] + ' > ' + pivot + ' — элемент остаётся в правой ' +
                            'части, граница не двигается');
                    }
                }

                const p = i + 1;
                push('place', roleMap([[hi, 'min'], [p, 'cur']]),
                    markMap([[i, 'i'], [hi, 'p']]),
                    'Отрезок пройден: слева от границы всё меньше ' + pivot +
                    '. Меняем опорный с первым элементом справа от границы — ' +
                    'с a[' + p + '] = ' + arr[p] + '.');
                const t = arr[p];
                arr[p] = arr[hi];
                arr[hi] = t;
                swaps++;
                done[p] = true;

                tasks.push([lo, p - 1]);
                tasks.push([p + 1, hi]);
                push('pass', roleMap([[p, 'swap']]), markMap([[p, 'p']]),
                    'Опорный ' + pivot + ' встал на позицию ' + p + ' — это его ' +
                    'окончательное место, слева от него только меньшие, справа ' +
                    'только большие. ' + tasksNote(tasks));
            }

            seg = null;
            push('done', {}, {}, 'Список отсортирован: ' + totals(comps, swaps) +
                '. Разбиений понадобилось ' + pass + '.');
            return frames;
        }

        const ALGOS = {
            bubble: { title: 'пузырьком', build: buildBubble, hasFlag: true },
            selection: {
                title: 'выбором',
                build: function (src) { return buildSelection(src); },
                hasFlag: false,
            },
            insertion: {
                title: 'вставками',
                build: function (src) { return buildInsertion(src); },
                hasFlag: false,
                hand: true,
                moveLabel: 'сдвигов',
            },
            quick: {
                title: 'быстрая',
                build: function (src) { return buildQuick(src); },
                hasFlag: false,
                // У быстрой сортировки прохода по всему списку не бывает:
                // единица работы — разбиение одного отрезка.
                passWord: 'разбиение',
                passIdle: 'разбиение не начато',
                passBtn: 'Разбиение целиком',
            },
        };

        const algoKey = ALGOS[config.algo] ? config.algo : 'bubble';
        // У выбора досрочного выхода не бывает: чтобы назвать элемент
        // минимумом, надо сравнить его со всем остатком. Тумблер прячем.
        const hasFlag = ALGOS[algoKey].hasFlag === true;
        // Вставки вынимают элемент из списка: нужна строка «в руке» и
        // подпись счётчика «сдвигов» вместо «обменов».
        const usesHand = ALGOS[algoKey].hand === true;
        const moveLabel = ALGOS[algoKey].moveLabel || 'обменов';
        const passWord = ALGOS[algoKey].passWord || 'проход';
        const passIdle = ALGOS[algoKey].passIdle || 'проход не начат';
        const passBtnLabel = ALGOS[algoKey].passBtn || 'Проход целиком';
        let values = normValues(config.values, DEFAULT_VALUES);
        let useFlag = hasFlag && config.flag === true;
        const speed = Math.min(Math.max(parseInt(config.speed, 10) || 600, 150), 2000);

        const presets = (Array.isArray(config.presets) ? config.presets : [])
            .filter(function (p) { return p && p.title && Array.isArray(p.values); })
            .slice(0, 6);

        const btnPrimary = 'px-3 py-1.5 rounded-full text-sm border transition-colors bg-brand-600 text-white border-brand-600 hover:bg-brand-700 dark:bg-cyan-500 dark:border-cyan-500 dark:hover:bg-cyan-400';
        const btnSecondary = 'px-3 py-1.5 rounded-full text-sm border transition-colors bg-gray-50 text-gray-500 border-gray-200 hover:bg-gray-100 dark:bg-slate-700 dark:border-slate-600 dark:text-slate-300';
        const chip = 'px-2.5 py-1 rounded-full text-xs border transition-colors bg-gray-50 text-gray-500 border-gray-200 hover:bg-gray-100 dark:bg-slate-700 dark:border-slate-600 dark:text-slate-300';
        const chipActive = 'px-2.5 py-1 rounded-full text-xs border transition-colors bg-brand-600 text-white border-brand-600 dark:bg-cyan-500 dark:border-cyan-500';

        const body = widgetFrame(el, el.dataset.title || 'Сортировка по шагам');

        // ---- «в руке»: вынутый из списка элемент ----
        const handRow = document.createElement('div');
        handRow.className = 'flex items-center gap-2 mb-2 h-6';
        const handChip = document.createElement('span');
        handChip.className = 'px-2 py-0.5 rounded-md text-xs font-mono border border-amber-400 bg-amber-50 text-amber-700 dark:border-amber-500 dark:bg-slate-800 dark:text-amber-300';
        handRow.appendChild(handChip);

        // ---- поле со столбиками ----
        const barsRow = document.createElement('div');
        barsRow.className = 'flex items-end gap-1 sm:gap-2 h-48';
        const idxRow = document.createElement('div');
        idxRow.className = 'flex gap-1 sm:gap-2 mt-1';
        const markRow = document.createElement('div');
        markRow.className = 'flex gap-1 sm:gap-2 mt-0.5 h-4';

        let cells = [];

        // Столбики пересобираются, когда меняется длина списка (пресет).
        function layout() {
            barsRow.innerHTML = '';
            idxRow.innerHTML = '';
            markRow.innerHTML = '';
            cells = values.map(function (_, k) {
                const col = document.createElement('div');
                col.className = 'flex-1 min-w-0 flex flex-col items-center justify-end gap-1 h-full';
                const bar = document.createElement('div');
                const val = document.createElement('div');
                col.appendChild(bar);
                col.appendChild(val);
                barsRow.appendChild(col);

                const idx = document.createElement('div');
                idx.className = 'flex-1 min-w-0 text-center text-[10px] text-gray-400 dark:text-slate-500 font-mono';
                idx.textContent = String(k);
                idxRow.appendChild(idx);

                const mark = document.createElement('div');
                mark.className = 'flex-1 min-w-0 text-center text-[11px] font-mono text-amber-600 dark:text-amber-400';
                markRow.appendChild(mark);

                return { bar: bar, val: val, idx: idx, mark: mark };
            });
        }

        // ---- счётчики и пояснение ----
        function badge() {
            const b = document.createElement('span');
            b.className = 'px-2 py-0.5 rounded-md text-xs border bg-white border-gray-200 text-gray-600 dark:bg-slate-800 dark:border-slate-600 dark:text-slate-300';
            return b;
        }

        const passBadge = badge();
        const compBadge = badge();
        const swapBadge = badge();
        const stats = document.createElement('div');
        stats.className = 'flex flex-wrap items-center gap-2 mt-3';
        stats.appendChild(passBadge);
        stats.appendChild(compBadge);
        stats.appendChild(swapBadge);

        const noteLine = document.createElement('div');
        noteLine.className = 'mt-2 text-sm text-gray-600 dark:text-slate-300 min-h-[2.5rem]';

        // ---- управление ----
        const prevBtn = document.createElement('button');
        prevBtn.type = 'button';
        prevBtn.textContent = '← Назад';

        const nextBtn = document.createElement('button');
        nextBtn.type = 'button';
        nextBtn.textContent = 'Шаг вперёд →';

        const playBtn = document.createElement('button');
        playBtn.type = 'button';
        playBtn.className = btnSecondary;

        const passBtn = document.createElement('button');
        passBtn.type = 'button';
        passBtn.textContent = passBtnLabel;

        const endBtn = document.createElement('button');
        endBtn.type = 'button';
        endBtn.textContent = 'В конец';

        const resetBtn = document.createElement('button');
        resetBtn.type = 'button';
        resetBtn.textContent = 'Сбросить';
        resetBtn.className = btnSecondary;

        const controls = document.createElement('div');
        controls.className = 'flex flex-wrap items-center gap-2 mt-4';
        [prevBtn, nextBtn, playBtn, passBtn, endBtn, resetBtn].forEach(function (b) {
            controls.appendChild(b);
        });

        const counter = document.createElement('span');
        counter.className = 'text-sm text-gray-400 dark:text-slate-400 ml-auto';
        controls.appendChild(counter);

        const slider = document.createElement('input');
        slider.type = 'range';
        slider.min = '0';
        slider.value = '0';
        slider.className = 'w-full accent-brand-600 dark:accent-cyan-500';
        slider.setAttribute('aria-label', 'Номер шага сортировки');

        // ---- наборы данных и тумблер флага ----
        const setup = document.createElement('div');
        setup.className = 'flex flex-wrap items-center gap-2 mt-4 pt-3 border-t border-gray-100 dark:border-slate-700';

        const presetBtns = presets.map(function (p) {
            const b = document.createElement('button');
            b.type = 'button';
            b.className = chip;
            b.textContent = p.title;
            b.addEventListener('click', function () {
                values = normValues(p.values, values);
                if (hasFlag && p.flag !== undefined) useFlag = p.flag === true;
                layout();
                rebuild();
            });
            setup.appendChild(b);
            return b;
        });

        const shuffleBtn = document.createElement('button');
        shuffleBtn.type = 'button';
        shuffleBtn.className = chip;
        shuffleBtn.textContent = 'Перемешать';
        shuffleBtn.addEventListener('click', function () {
            const a = values.slice();
            for (let i = a.length - 1; i > 0; i--) {
                const j = Math.floor(Math.random() * (i + 1));
                const t = a[i]; a[i] = a[j]; a[j] = t;
            }
            values = a;
            rebuild();
        });
        setup.appendChild(shuffleBtn);

        const flagBtn = document.createElement('button');
        flagBtn.type = 'button';
        flagBtn.addEventListener('click', function () {
            useFlag = !useFlag;
            rebuild();
        });
        if (hasFlag) setup.appendChild(flagBtn);

        if (usesHand) body.appendChild(handRow);
        body.appendChild(barsRow);
        body.appendChild(idxRow);
        body.appendChild(markRow);
        body.appendChild(stats);
        body.appendChild(noteLine);
        body.appendChild(controls);
        body.appendChild(slider);
        body.appendChild(setup);

        // ---- состояние ----
        let frames = ALGOS[algoKey].build(values, useFlag);
        let pos = 0;
        let timer = null;

        function stopPlay() {
            if (timer) {
                clearInterval(timer);
                timer = null;
            }
        }

        function rebuild() {
            stopPlay();
            frames = ALGOS[algoKey].build(values, useFlag);
            pos = 0;
            render();
        }

        function render() {
            const f = frames[pos];
            let maxV = 1;
            f.arr.forEach(function (v) { if (v > maxV) maxV = v; });

            cells.forEach(function (c, k) {
                const v = f.arr[k];
                const role = f.roles[k];
                const mark = f.marks[k] || '';
                // Готовая часть у пузырька и выбора — сплошной край списка,
                // у быстрой сортировки окончательные места занимают опорные
                // элементы вразнобой: их перечисляет done.
                const sorted = k >= f.sortedFrom || k < f.sortedTo ||
                    (f.done !== undefined && f.done[k] === true);
                // Работа идёт по отрезку (быстрая сортировка) — всё, что вне
                // него, притушено: сейчас алгоритм туда не смотрит.
                const outside = f.seg !== undefined && f.seg !== null &&
                    (k < f.seg[0] || k > f.seg[1]);
                // Дырка: элемент отсюда вынут в руку, значения в ячейке нет.
                // Рисуем пустой пунктирный слот ростом с то, что в руке.
                const isHole = role === 'hole';
                let tint;
                if (isHole) {
                    tint = 'border-2 border-dashed border-amber-400 dark:border-amber-500';
                } else if (role === 'swap') {
                    tint = 'bg-brand-600 dark:bg-cyan-500';
                } else if (role === 'min') {
                    tint = 'bg-violet-500 dark:bg-violet-500';
                } else if (role === 'cur') {
                    tint = 'bg-amber-400 dark:bg-amber-500';
                } else if (sorted) {
                    tint = 'bg-emerald-500 dark:bg-emerald-500';
                } else {
                    tint = 'bg-gray-300 dark:bg-slate-600';
                }
                c.bar.className = 'w-full rounded-t-md transition-all duration-200 ' + tint +
                    (outside && !role ? ' opacity-40' : '');
                c.bar.style.height =
                    (16 + Math.round(120 * (isHole ? (f.hand || v) : v) / maxV)) + 'px';
                c.val.textContent = isHole ? '' : String(v);
                c.val.className = 'font-mono text-xs leading-none ' +
                    (role
                        ? 'font-bold text-gray-900 dark:text-white'
                        : 'text-gray-500 dark:text-slate-400');
                // Цвет метки повторяет цвет столбика, за который она отвечает:
                // m (минимум) и p (опорный) — фиолетовые, i — служебная серая,
                // j — янтарная.
                let markTint;
                if (mark.indexOf('m') >= 0 || mark.indexOf('p') >= 0) {
                    markTint = 'text-violet-600 dark:text-violet-400';
                } else if (mark === 'i') {
                    markTint = 'text-gray-400 dark:text-slate-500';
                } else {
                    markTint = 'text-amber-600 dark:text-amber-400';
                }
                c.mark.textContent = mark;
                c.mark.className = 'flex-1 min-w-0 text-center text-[11px] font-mono ' + markTint;
            });

            passBadge.textContent = f.pass > 0 ? passWord + ' ' + f.pass : passIdle;
            compBadge.textContent = 'сравнений: ' + f.comps;
            swapBadge.textContent = moveLabel + ': ' + f.swaps;
            noteLine.textContent = f.note;

            if (usesHand) {
                const inHand = f.hand !== null && f.hand !== undefined;
                handChip.textContent = inHand ? 'в руке: key = ' + f.hand : 'в руке пусто';
                // Прячем, но место оставляем, чтобы поле не подпрыгивало.
                handChip.style.visibility = inHand ? 'visible' : 'hidden';
            }

            counter.textContent = 'шаг ' + pos + ' из ' + (frames.length - 1);
            slider.max = String(frames.length - 1);
            slider.value = String(pos);

            const atStart = pos === 0;
            const atEnd = pos >= frames.length - 1;
            prevBtn.disabled = atStart;
            prevBtn.className = btnSecondary + (atStart ? ' opacity-50 cursor-not-allowed' : '');
            nextBtn.disabled = atEnd;
            nextBtn.className = btnPrimary + (atEnd ? ' opacity-50 cursor-not-allowed' : '');
            passBtn.disabled = atEnd;
            passBtn.className = btnSecondary + (atEnd ? ' opacity-50 cursor-not-allowed' : '');
            endBtn.disabled = atEnd;
            endBtn.className = btnSecondary + (atEnd ? ' opacity-50 cursor-not-allowed' : '');
            playBtn.textContent = timer ? '❚❚ Пауза' : '▶ Играть';
            playBtn.className = btnSecondary + (atEnd && !timer ? ' opacity-50 cursor-not-allowed' : '');
            playBtn.disabled = atEnd && !timer;

            presetBtns.forEach(function (b, i) {
                const p = presets[i];
                const same = p.values.length === values.length &&
                    p.values.every(function (v, k) { return Math.round(Number(v)) === values[k]; });
                b.className = same ? chipActive : chip;
            });
            if (hasFlag) {
                flagBtn.className = useFlag ? chipActive : chip;
                flagBtn.textContent = useFlag ? 'флаг обменов: включён' : 'флаг обменов: выключен';
            }
        }

        prevBtn.addEventListener('click', function () {
            stopPlay();
            if (pos > 0) { pos--; render(); }
        });
        nextBtn.addEventListener('click', function () {
            stopPlay();
            if (pos < frames.length - 1) { pos++; render(); }
        });
        // «Проход целиком» — до ближайшего кадра конца прохода включительно.
        passBtn.addEventListener('click', function () {
            stopPlay();
            do {
                pos++;
            } while (pos < frames.length - 1 &&
                     frames[pos].kind !== 'pass' && frames[pos].kind !== 'done');
            render();
        });
        endBtn.addEventListener('click', function () {
            stopPlay();
            pos = frames.length - 1;
            render();
        });
        resetBtn.addEventListener('click', function () {
            stopPlay();
            pos = 0;
            render();
        });
        playBtn.addEventListener('click', function () {
            if (timer) {
                stopPlay();
                render();
                return;
            }
            timer = setInterval(function () {
                if (pos >= frames.length - 1) {
                    stopPlay();
                    render();
                    return;
                }
                pos++;
                render();
            }, speed);
            render();
        });
        slider.addEventListener('input', function () {
            stopPlay();
            pos = Math.min(Math.max(parseInt(slider.value, 10) || 0, 0), frames.length - 1);
            render();
        });

        layout();
        render();
    });

    // ─────────────────────────────────────────────────────────────
    // Виджет: call-stack — рекурсия стопкой кадров вызовов (уроки 12.3–12.4).
    // Слева листинг с подсветкой текущей строки (как в loop-trace), справа —
    // стопка карточек: каждый начатый и ещё не законченный вызов занимает
    // свою карточку со своим значением параметра и своим незавершённым
    // выражением («4 · ? = ?»). На спуске стопка растёт вниз, на подъёме
    // верхняя карточка исчезает, а число, которое она вернула, подставляется
    // в «?» карточки под ней — видно, что умножения считаются на обратном
    // пути, а не по дороге вниз.
    //
    // Виджет ничего не вычисляет: шаги готовит автор урока в seed-команде
    // (рекурсивной функцией, повторяющей разбираемый алгоритм) и передаёт
    // готовым списком, где в каждом шаге лежит ПОЛНОЕ состояние стека.
    // Поэтому шаг назад и ползунок работают без пересчёта.
    //
    // Конфиг:
    //   {
    //     "code": ["def factorial(n):", "    if n == 0:", ...],
    //     "steps": [
    //       {"line": 4,
    //        "stack": [
    //          {"call": "factorial(4)", "vars": {"n": 4}, "expr": "4 · ? = ?"},
    //          {"call": "factorial(3)", "vars": {"n": 3}, "expr": "3 · ? = ?",
    //           "state": "active"}
    //        ],
    //        "returned": {"value": 1, "from": "factorial(0)", "to": "factorial(1)"},
    //        "note": "...", "out": "24", "check": false}
    //     ],
    //     "limit": 8
    //   }
    // stack    — снизу вверх по вложенности: первый элемент списка рисуется
    //            сверху (самый первый вызов), последний — самый глубокий;
    // state    — 'active' (сейчас выполняется), 'waiting' (ждёт, значение по
    //            умолчанию), 'base' (базовый случай), 'over' (за пределом
    //            глубины, красная карточка — для урока 12.4);
    // ret      — число, которое кадр возвращает прямо сейчас: рисует зелёный
    //            бейдж «вернул N» на карточке;
    // done     — то же для вызова без результата (countdown): бейдж
    //            «закончился» вместо «вернул N»;
    // returned — пояснение к подъёму: строка «↑ factorial(0) вернул 1»
    //            под стопкой; без ключа value — «↑ countdown(0) закончился»;
    // limit    — необязательный предел глубины: рядом с глубиной появляется
    //            «из N», а превышение подсвечивается красным.
    // ─────────────────────────────────────────────────────────────
    register('call-stack', function (el, config) {
        const code = Array.isArray(config.code) ? config.code : [];
        const steps = Array.isArray(config.steps) ? config.steps : [];
        if (code.length === 0 || steps.length === 0) {
            el.innerHTML = '<p class="text-sm text-red-500">call-stack: нужны непустые code и steps</p>';
            return;
        }
        const limit = typeof config.limit === 'number' && config.limit > 0 ? config.limit : 0;
        const hasOutput = steps.some(function (s) { return s.out !== undefined && s.out !== null; });
        // Шаг, на котором в стопке впервые появляется вызов: до него пустая
        // стопка значит «ещё не начали», после — «всё закончилось».
        const firstCallIdx = steps.findIndex(function (s) {
            return Array.isArray(s.stack) && s.stack.length > 0;
        });
        const firstCallStep = firstCallIdx === -1 ? Infinity : firstCallIdx;

        const body = widgetFrame(el, el.dataset.title || 'Стек вызовов');

        const btnPrimary = 'px-3 py-1.5 rounded-full text-sm border transition-colors bg-brand-600 text-white border-brand-600 hover:bg-brand-700 dark:bg-cyan-500 dark:border-cyan-500 dark:hover:bg-cyan-400';
        const btnSecondary = 'px-3 py-1.5 rounded-full text-sm border transition-colors bg-gray-50 text-gray-500 border-gray-200 hover:bg-gray-100 dark:bg-slate-700 dark:border-slate-600 dark:text-slate-300';

        // pos: -1 — программа ещё не запущена, дальше индекс текущего шага.
        let pos = -1;

        // ---- листинг кода (тёмная панель в обеих темах, как в loop-trace) ----
        const HLJS_BG = '#282c34';
        const HLJS_FG = '#abb2bf';
        const HLJS_GUTTER = '#5c6370';
        const lang = config.language || 'python';

        function highlightLine(line) {
            if (window.hljs && hljs.getLanguage && hljs.getLanguage(lang)) {
                try {
                    return hljs.highlight(line, { language: lang, ignoreIllegals: true }).value;
                } catch (e) {
                    /* тема или язык не загрузились — покажем как обычный текст */
                }
            }
            return escapeHtml(line);
        }

        const codePane = document.createElement('div');
        codePane.className = 'rounded-lg py-2 overflow-x-auto self-start';
        codePane.style.background = HLJS_BG;
        codePane.style.color = HLJS_FG;
        const codeRows = code.map(function (line, i) {
            const row = document.createElement('div');
            row.className = 'flex items-start gap-3 pl-2 pr-4 py-0.5 font-mono text-sm whitespace-pre border-l-2 border-transparent';
            const num = document.createElement('span');
            num.className = 'w-5 shrink-0 text-right select-none';
            num.style.color = HLJS_GUTTER;
            num.textContent = String(i + 1);
            const text = document.createElement('span');
            text.innerHTML = highlightLine(line);
            row.appendChild(num);
            row.appendChild(text);
            codePane.appendChild(row);
            return row;
        });

        // ---- стопка вызовов ----
        const stackHead = document.createElement('div');
        stackHead.className = 'flex items-center justify-between gap-2';
        const stackTitle = document.createElement('div');
        stackTitle.className = 'text-xs uppercase tracking-wide text-gray-400 dark:text-slate-500';
        stackTitle.textContent = 'Незаконченные вызовы';
        const depthBadge = document.createElement('span');
        depthBadge.className = 'px-2 py-0.5 rounded-md text-xs font-semibold border';
        stackHead.appendChild(stackTitle);
        stackHead.appendChild(depthBadge);

        const stackPane = document.createElement('div');
        stackPane.className = 'flex flex-col gap-1.5 mt-2';

        const returnLine = document.createElement('div');
        returnLine.className = 'mt-2 min-h-[1.75rem] flex flex-wrap items-center gap-2';

        const noteLine = document.createElement('div');
        noteLine.className = 'mt-1 text-sm text-gray-600 dark:text-slate-300 min-h-[2.75rem] flex flex-wrap items-center gap-2';

        const statePane = document.createElement('div');
        statePane.className = 'flex flex-col';
        statePane.appendChild(stackHead);
        statePane.appendChild(stackPane);
        statePane.appendChild(returnLine);
        statePane.appendChild(noteLine);

        const columns = document.createElement('div');
        columns.className = 'grid gap-4 md:grid-cols-2';
        columns.appendChild(codePane);
        columns.appendChild(statePane);

        // ---- вывод программы ----
        const outputTitle = document.createElement('div');
        outputTitle.className = 'mt-4 mb-1 text-xs uppercase tracking-wide text-gray-400 dark:text-slate-500';
        outputTitle.textContent = 'Вывод программы';
        const outputPane = document.createElement('div');
        outputPane.className = 'rounded-lg px-4 py-3 font-mono text-sm whitespace-pre-wrap break-words bg-slate-900 text-slate-100 min-h-[3.5rem] max-h-40 overflow-y-auto';

        // ---- управление (то же, что у loop-trace) ----
        const slider = document.createElement('input');
        slider.type = 'range';
        slider.min = '0';
        slider.max = String(steps.length);
        slider.value = '0';
        slider.className = 'w-full accent-brand-600 dark:accent-cyan-500';
        slider.setAttribute('aria-label', 'Номер шага выполнения');

        const prevBtn = document.createElement('button');
        prevBtn.type = 'button';
        prevBtn.textContent = '← Назад';

        const nextBtn = document.createElement('button');
        nextBtn.type = 'button';
        nextBtn.textContent = 'Шаг вперёд →';

        const endBtn = document.createElement('button');
        endBtn.type = 'button';
        endBtn.textContent = 'В конец';
        endBtn.className = btnSecondary;

        const resetBtn = document.createElement('button');
        resetBtn.type = 'button';
        resetBtn.textContent = 'Сбросить';
        resetBtn.className = btnSecondary;

        const counter = document.createElement('span');
        counter.className = 'text-sm text-gray-400 dark:text-slate-400 ml-auto';

        const controls = document.createElement('div');
        controls.className = 'flex flex-wrap items-center gap-2 mt-4';
        [prevBtn, nextBtn, endBtn, resetBtn, counter].forEach(function (node) {
            controls.appendChild(node);
        });

        body.appendChild(columns);
        if (hasOutput) {
            body.appendChild(outputTitle);
            body.appendChild(outputPane);
        }
        body.appendChild(controls);
        body.appendChild(slider);

        const FRAME_STYLES = {
            waiting: 'bg-white border-gray-200 dark:bg-slate-800 dark:border-slate-600',
            // В палитре brand нет оттенка 400 — активной рамке берём 500.
            active: 'bg-brand-50 border-brand-500 dark:bg-cyan-900/25 dark:border-cyan-600',
            base: 'bg-violet-50 border-violet-300 dark:bg-violet-900/25 dark:border-violet-700',
            over: 'bg-red-50 border-red-300 dark:bg-red-900/25 dark:border-red-700',
        };

        function formatVars(vars) {
            if (!vars) return '';
            return Object.keys(vars).map(function (name) {
                const v = vars[name];
                return name + ' = ' + (typeof v === 'string' ? "'" + v + "'" : String(v));
            }).join(', ');
        }

        // Карточка одного вызова. Отступ слева растёт с вложенностью — так
        // видно лесенку спуска; сам отступ задаём инлайном, чтобы не плодить
        // произвольные классы.
        function frameCard(frame, depth, exprChanged) {
            const card = document.createElement('div');
            card.className = 'rounded-md border px-3 py-1.5 transition-colors ' +
                (FRAME_STYLES[frame.state] || FRAME_STYLES.waiting);
            card.style.marginLeft = Math.min(depth, 8) * 14 + 'px';

            const head = document.createElement('div');
            head.className = 'flex items-center justify-between gap-3';
            const call = document.createElement('span');
            call.className = 'font-mono text-sm font-semibold text-gray-900 dark:text-white';
            call.textContent = frame.call || '';
            const vars = document.createElement('span');
            vars.className = 'font-mono text-xs text-gray-500 dark:text-slate-400';
            vars.textContent = formatVars(frame.vars);
            head.appendChild(call);
            head.appendChild(vars);
            card.appendChild(head);

            const returns = frame.ret !== undefined && frame.ret !== null;
            if (frame.expr || returns || frame.done) {
                const foot = document.createElement('div');
                foot.className = 'mt-0.5 flex items-center justify-between gap-3';
                const expr = document.createElement('span');
                expr.className = 'font-mono text-sm ' + (exprChanged
                    ? 'text-amber-700 dark:text-amber-300 font-semibold'
                    : 'text-gray-600 dark:text-slate-300');
                expr.textContent = frame.expr || '';
                foot.appendChild(expr);
                // Вызов, который ничего не возвращает (как countdown), всё равно
                // должен показывать момент своего закрытия — иначе на подъёме
                // карточка просто молча исчезает.
                if (returns || frame.done) {
                    const badge = document.createElement('span');
                    badge.className = 'shrink-0 px-2 py-0.5 rounded-md text-xs font-semibold border bg-emerald-50 border-emerald-300 text-emerald-700 dark:bg-emerald-900/30 dark:border-emerald-700 dark:text-emerald-300';
                    badge.textContent = returns ? '↑ вернул ' + frame.ret : '↑ закончился';
                    foot.appendChild(badge);
                }
                card.appendChild(foot);
            }
            return card;
        }

        function render() {
            const step = pos >= 0 ? steps[pos] : null;
            const stack = (step && Array.isArray(step.stack)) ? step.stack : [];
            const prevStack = (pos > 0 && Array.isArray(steps[pos - 1].stack)) ? steps[pos - 1].stack : [];

            codeRows.forEach(function (row, i) {
                const active = step && step.line === i + 1;
                row.className = 'flex items-start gap-3 pl-2 pr-4 py-0.5 font-mono text-sm whitespace-pre border-l-2 ' +
                    (active ? 'border-cyan-400 bg-white/10' : 'border-transparent');
            });

            stackPane.innerHTML = '';
            if (stack.length === 0) {
                const empty = document.createElement('div');
                empty.className = 'rounded-md border border-dashed px-3 py-2 text-sm text-gray-400 border-gray-200 dark:text-slate-500 dark:border-slate-600';
                // Пустая стопка означает разное до первого вызова и после
                // последнего — иначе на первых шагах написано «все вызовы
                // закончились», хотя ни один ещё не начинался.
                empty.textContent = pos < firstCallStep
                    ? 'Пока пусто: ни один вызов не начат.'
                    : 'Стек пуст — все вызовы закончились.';
                stackPane.appendChild(empty);
            } else {
                stack.forEach(function (frame, depth) {
                    // Выражение подсвечиваем, если оно изменилось именно на этом
                    // шаге, — так заметно, что «?» заменился пришедшим снизу числом.
                    const before = prevStack[depth];
                    const changed = !!(before && before.call === frame.call && before.expr !== frame.expr);
                    stackPane.appendChild(frameCard(frame, depth, changed));
                });
            }

            const over = limit > 0 && stack.length > limit;
            depthBadge.className = 'px-2 py-0.5 rounded-md text-xs font-semibold border ' + (over
                ? 'bg-red-50 border-red-300 text-red-700 dark:bg-red-900/30 dark:border-red-700 dark:text-red-300'
                : 'bg-gray-100 border-gray-200 text-gray-500 dark:bg-slate-700 dark:border-slate-600 dark:text-slate-300');
            depthBadge.textContent = 'глубина: ' + stack.length + (limit > 0 ? ' из ' + limit : '');

            returnLine.innerHTML = '';
            if (step && step.returned) {
                const pill = document.createElement('span');
                pill.className = 'px-2 py-0.5 rounded-md text-xs font-semibold border bg-emerald-50 border-emerald-300 text-emerald-700 dark:bg-emerald-900/30 dark:border-emerald-700 dark:text-emerald-300';
                const ret = step.returned;
                const who = ret.from ? ret.from + ' ' : '';
                if (ret.value === undefined || ret.value === null) {
                    // Вызов без возвращаемого значения: показываем сам факт выхода.
                    pill.textContent = '↑ ' + who + 'закончился' +
                        (ret.to ? ' → возвращаемся в ' + ret.to : '');
                } else {
                    pill.textContent = '↑ ' + (who ? who + 'вернул ' : 'вернулось ') + ret.value +
                        (ret.to ? ' → подставлено в ' + ret.to : '');
                }
                returnLine.appendChild(pill);
            }
            if (step && step.check !== undefined && step.check !== null) {
                const badge = document.createElement('span');
                badge.className = 'px-2 py-0.5 rounded-md text-xs font-semibold border ' + (step.check
                    ? 'bg-emerald-50 border-emerald-300 text-emerald-700 dark:bg-emerald-900/30 dark:border-emerald-700 dark:text-emerald-300'
                    : 'bg-gray-100 border-gray-300 text-gray-500 dark:bg-slate-700 dark:border-slate-500 dark:text-slate-300');
                badge.textContent = step.check ? 'условие истинно' : 'условие ложно';
                returnLine.appendChild(badge);
            }

            noteLine.textContent = step
                ? (step.note || '')
                : 'Программа ещё не запущена — нажмите «Шаг вперёд».';

            if (hasOutput) {
                const printed = [];
                for (let i = 0; i <= pos; i++) {
                    if (steps[i].out !== undefined && steps[i].out !== null) printed.push(steps[i].out);
                }
                outputPane.textContent = printed.join('\n');
                outputPane.scrollTop = outputPane.scrollHeight;
            }

            counter.textContent = pos < 0
                ? 'шаг 0 из ' + steps.length
                : 'шаг ' + (pos + 1) + ' из ' + steps.length;
            slider.value = String(pos + 1);

            prevBtn.disabled = pos < 0;
            prevBtn.className = btnSecondary + (pos < 0 ? ' opacity-50 cursor-not-allowed' : '');
            const atEnd = pos >= steps.length - 1;
            nextBtn.disabled = atEnd;
            nextBtn.className = btnPrimary + (atEnd ? ' opacity-50 cursor-not-allowed' : '');
            endBtn.disabled = atEnd;
            endBtn.className = btnSecondary + (atEnd ? ' opacity-50 cursor-not-allowed' : '');
        }

        prevBtn.addEventListener('click', function () {
            if (pos >= 0) { pos--; render(); }
        });
        nextBtn.addEventListener('click', function () {
            if (pos < steps.length - 1) { pos++; render(); }
        });
        endBtn.addEventListener('click', function () {
            pos = steps.length - 1;
            render();
        });
        resetBtn.addEventListener('click', function () {
            pos = -1;
            render();
        });
        slider.addEventListener('input', function () {
            pos = (parseInt(slider.value, 10) || 0) - 1;
            render();
        });

        render();
    });

    // ─────────────────────────────────────────────────────────────
    // Виджет: call-tree — дерево вызовов рекурсивной функции (урок 12.5).
    //
    // call-stack показывает срез: какие вызовы начаты прямо сейчас. call-tree
    // показывает картину целиком — кто кого вызвал за весь расчёт. Главное в
    // нём — повторы: цвет узла закреплён за аргументом, поэтому видно, что у
    // fib одна и та же подзадача попадает в дерево много раз. Для сравнения
    // рядом лежит factorial: у него дерево вырождается в цепочку, повторов нет.
    //
    // Конфиг:
    //   {
    //     "func": "fib",            // какая функция открыта: fib | fact
    //     "n": 5,                   // аргумент
    //     "funcs": ["fib", "fact"], // какие чипы показывать (по умолчанию обе)
    //     "values": false,          // сразу показывать результат каждого вызова
    //     "order": false            // сразу нумеровать вызовы по порядку
    //   }
    // Дерево виджет строит сам — в отличие от call-stack и loop-trace, Python
    // в seed-команде ничего не готовит: функций всего две и обе описаны в FUNCS.
    // ─────────────────────────────────────────────────────────────
    register('call-tree', function (el, config) {
        const SVG_NS = 'http://www.w3.org/2000/svg';

        // Цвет закреплён за аргументом: fib(2) выглядит одинаково во всех
        // местах дерева — на этом и держится вся мысль урока.
        const TONE = [
            'bg-amber-50 border-amber-300 text-amber-900 dark:bg-amber-900/40 dark:border-amber-700 dark:text-amber-100',
            'bg-emerald-50 border-emerald-300 text-emerald-900 dark:bg-emerald-900/40 dark:border-emerald-700 dark:text-emerald-100',
            'bg-violet-50 border-violet-300 text-violet-900 dark:bg-violet-900/40 dark:border-violet-700 dark:text-violet-100',
            'bg-sky-50 border-sky-300 text-sky-900 dark:bg-sky-900/40 dark:border-sky-700 dark:text-sky-100',
            'bg-rose-50 border-rose-300 text-rose-900 dark:bg-rose-900/40 dark:border-rose-700 dark:text-rose-100',
            'bg-lime-50 border-lime-300 text-lime-900 dark:bg-lime-900/40 dark:border-lime-700 dark:text-lime-100',
            'bg-orange-50 border-orange-300 text-orange-900 dark:bg-orange-900/40 dark:border-orange-700 dark:text-orange-100',
            'bg-teal-50 border-teal-300 text-teal-900 dark:bg-teal-900/40 dark:border-teal-700 dark:text-teal-100'
        ];
        const SVG_TONE = [
            'fill-amber-100 stroke-amber-400 dark:fill-amber-800 dark:stroke-amber-500',
            'fill-emerald-100 stroke-emerald-400 dark:fill-emerald-800 dark:stroke-emerald-500',
            'fill-violet-100 stroke-violet-400 dark:fill-violet-800 dark:stroke-violet-500',
            'fill-sky-100 stroke-sky-400 dark:fill-sky-800 dark:stroke-sky-500',
            'fill-rose-100 stroke-rose-400 dark:fill-rose-800 dark:stroke-rose-500',
            'fill-lime-100 stroke-lime-400 dark:fill-lime-800 dark:stroke-lime-500',
            'fill-orange-100 stroke-orange-400 dark:fill-orange-800 dark:stroke-orange-500',
            'fill-teal-100 stroke-teal-400 dark:fill-teal-800 dark:stroke-teal-500'
        ];

        const CHIP = 'px-2.5 py-1 rounded-full text-xs border transition-colors bg-gray-50 text-gray-500 border-gray-200 hover:bg-gray-100 dark:bg-slate-700 dark:border-slate-600 dark:text-slate-300';
        const CHIP_ON = 'px-2.5 py-1 rounded-full text-xs border transition-colors bg-brand-600 text-white border-brand-600 dark:bg-cyan-500 dark:border-cyan-500';
        const BADGE = 'px-2 py-0.5 rounded-md text-xs font-semibold border bg-gray-100 border-gray-200 text-gray-600 dark:bg-slate-700 dark:border-slate-600 dark:text-slate-300';
        const BADGE_WARN = 'px-2 py-0.5 rounded-md text-xs font-semibold border bg-amber-50 border-amber-300 text-amber-700 dark:bg-amber-900/30 dark:border-amber-700 dark:text-amber-300';
        const BADGE_OK = 'px-2 py-0.5 rounded-md text-xs font-semibold border bg-emerald-50 border-emerald-300 text-emerald-700 dark:bg-emerald-900/30 dark:border-emerald-700 dark:text-emerald-300';

        const FUNCS = {
            fib: {
                title: 'fib(n)',
                rule: 'fib(n) = fib(n − 1) + fib(n − 2),   fib(0) = 0,   fib(1) = 1',
                label: function (a) { return 'fib(' + a + ')'; },
                kids: function (a) { return a < 2 ? [] : [a - 1, a - 2]; },
                value: function (a, kids) { return kids.length ? kids[0] + kids[1] : a; },
                minN: 1, maxN: 7, defN: 5
            },
            fact: {
                title: 'factorial(n)',
                rule: 'factorial(n) = n · factorial(n − 1),   factorial(0) = 1',
                label: function (a) { return 'factorial(' + a + ')'; },
                kids: function (a) { return a <= 0 ? [] : [a - 1]; },
                value: function (a, kids) { return kids.length ? a * kids[0] : 1; },
                minN: 1, maxN: 7, defN: 4
            }
        };

        function plural(x, one, few, many) {
            const tail = Math.abs(x) % 100;
            if (tail >= 11 && tail <= 14) return many;
            const last = tail % 10;
            if (last === 1) return one;
            if (last >= 2 && last <= 4) return few;
            return many;
        }

        const funcKeys = (Array.isArray(config.funcs) && config.funcs.length
            ? config.funcs
            : ['fib', 'fact']).filter(function (k) { return !!FUNCS[k]; });
        if (funcKeys.length === 0) funcKeys.push('fib');

        let fnKey = funcKeys.indexOf(config.func) >= 0 ? config.func : funcKeys[0];
        let fn = FUNCS[fnKey];

        function clampN(raw, f) {
            const v = parseInt(raw, 10);
            if (isNaN(v)) return f.defN;
            return Math.min(Math.max(v, f.minN), f.maxN);
        }

        let n = clampN(config.n, fn);
        let showValues = config.values === true;
        let showOrder = config.order === true;
        let selected = null;   // аргумент подсвеченной подзадачи

        // ── построение дерева ────────────────────────────────────
        // Обход в том же порядке, в каком по дереву идёт сама программа:
        // сначала вход в вызов (номер по порядку), потом дети, и только на
        // обратном пути становится известен результат.
        function buildTree(f, arg) {
            const all = [];
            let counter = 0;
            function walk(a, depth) {
                const node = { arg: a, depth: depth, children: [], order: ++counter };
                all.push(node);
                f.kids(a).forEach(function (k) { node.children.push(walk(k, depth + 1)); });
                node.value = f.value(a, node.children.map(function (c) { return c.value; }));
                return node;
            }
            const root = walk(arg, 0);
            return { root: root, all: all };
        }

        function svgEl(name, attrs) {
            const node = document.createElementNS(SVG_NS, name);
            Object.keys(attrs || {}).forEach(function (k) {
                node.setAttribute(k, attrs[k]);
            });
            return node;
        }

        const body = widgetFrame(el, el.dataset.title || 'Дерево вызовов');

        // ── управление ───────────────────────────────────────────
        const funcRow = document.createElement('div');
        funcRow.className = 'flex flex-wrap items-center gap-2';
        const funcBtns = {};
        if (funcKeys.length > 1) {
            const cap = document.createElement('span');
            cap.className = 'text-xs uppercase tracking-wide text-gray-400 dark:text-slate-500';
            cap.textContent = 'функция';
            funcRow.appendChild(cap);
            funcKeys.forEach(function (key) {
                const btn = document.createElement('button');
                btn.type = 'button';
                btn.textContent = FUNCS[key].title;
                btn.addEventListener('click', function () {
                    fnKey = key;
                    fn = FUNCS[key];
                    n = clampN(n, fn);
                    selected = null;
                    render();
                });
                funcBtns[key] = btn;
                funcRow.appendChild(btn);
            });
        }

        const ruleLine = document.createElement('div');
        ruleLine.className = 'mt-2 font-mono text-xs text-gray-500 dark:text-slate-400';

        const nRow = document.createElement('div');
        nRow.className = 'mt-3 flex flex-wrap items-center gap-3';
        const nLabel = document.createElement('span');
        nLabel.className = 'font-mono text-sm text-gray-700 dark:text-slate-200 w-14';
        const nSlider = document.createElement('input');
        nSlider.type = 'range';
        nSlider.className = 'w-40 accent-brand-600 dark:accent-cyan-500';
        nSlider.setAttribute('aria-label', 'Аргумент n');
        nSlider.addEventListener('input', function () {
            n = clampN(nSlider.value, fn);
            selected = null;
            render();
        });
        nRow.appendChild(nLabel);
        nRow.appendChild(nSlider);

        const valuesBtn = document.createElement('button');
        valuesBtn.type = 'button';
        valuesBtn.textContent = 'результаты';
        valuesBtn.addEventListener('click', function () {
            showValues = !showValues;
            render();
        });

        const orderBtn = document.createElement('button');
        orderBtn.type = 'button';
        orderBtn.textContent = 'порядок вызова';
        orderBtn.addEventListener('click', function () {
            showOrder = !showOrder;
            render();
        });

        nRow.appendChild(valuesBtn);
        nRow.appendChild(orderBtn);

        // ── дерево ───────────────────────────────────────────────
        const treeHost = document.createElement('div');
        treeHost.className = 'mt-3 overflow-x-auto';

        const legendRow = document.createElement('div');
        legendRow.className = 'mt-3 flex flex-wrap items-center gap-1.5';

        const statsRow = document.createElement('div');
        statsRow.className = 'mt-3 flex flex-wrap items-center gap-2';

        const noteLine = document.createElement('div');
        noteLine.className = 'mt-2 text-sm text-gray-600 dark:text-slate-300';

        body.appendChild(funcRow);
        body.appendChild(ruleLine);
        body.appendChild(nRow);
        body.appendChild(treeHost);
        body.appendChild(legendRow);
        body.appendChild(statsRow);
        body.appendChild(noteLine);

        function toneOf(arg) {
            return TONE[((arg % TONE.length) + TONE.length) % TONE.length];
        }
        function svgToneOf(arg) {
            return SVG_TONE[((arg % SVG_TONE.length) + SVG_TONE.length) % SVG_TONE.length];
        }

        function pick(arg) {
            selected = (selected === arg) ? null : arg;
            render();
        }

        function renderTree(tree) {
            treeHost.innerHTML = '';

            const CHAR = 7.3;                 // ширина моноширинного символа при 12px
            const H = 26;                     // высота узла
            const ROW = 56;                   // расстояние между уровнями
            // Результат вызова пишем внутри плашки, а не под ней: под плашкой
            // проходят рёбра к детям, и подпись ложилась бы прямо на них.
            const textOf = function (node) {
                return fn.label(node.arg) + (showValues ? ' = ' + node.value : '');
            };
            const widthOf = function (node) {
                return textOf(node).length * CHAR + 14;
            };
            const maxW = Math.max.apply(null, tree.all.map(widthOf));
            const STEP = maxW + 10;           // шаг между листьями
            const PAD_X = maxW / 2 + 6;
            const PAD_TOP = 30;               // место под номера вызовов

            let cursor = 0;
            let maxDepth = 0;
            (function layout(node) {
                node.children.forEach(layout);
                if (node.children.length === 0) {
                    node.x = PAD_X + cursor * STEP;
                    cursor++;
                } else {
                    const xs = node.children.map(function (c) { return c.x; });
                    node.x = (Math.min.apply(null, xs) + Math.max.apply(null, xs)) / 2;
                }
                node.y = PAD_TOP + node.depth * ROW;
                if (node.depth > maxDepth) maxDepth = node.depth;
            })(tree.root);

            const width = Math.max(240, 2 * PAD_X + Math.max(cursor - 1, 0) * STEP);
            const height = PAD_TOP + maxDepth * ROW + 34;
            const svg = svgEl('svg', {
                width: width, height: height,
                viewBox: '0 0 ' + width + ' ' + height,
                class: 'mx-auto block'
            });

            (function edges(node) {
                node.children.forEach(function (kid) {
                    svg.appendChild(svgEl('line', {
                        x1: node.x, y1: node.y + H / 2, x2: kid.x, y2: kid.y - H / 2,
                        class: 'stroke-gray-300 dark:stroke-slate-600',
                        'stroke-width': 2
                    }));
                    edges(kid);
                });
            })(tree.root);

            tree.all.forEach(function (node) {
                const g = svgEl('g', { class: 'cursor-pointer' });
                // Затемняем всё, кроме выбранной подзадачи: так видно, в скольких
                // местах дерева она встречается.
                if (selected !== null && node.arg !== selected) g.setAttribute('opacity', '0.3');
                g.addEventListener('click', function () { pick(node.arg); });

                const label = textOf(node);
                const w = widthOf(node);
                const on = selected !== null && node.arg === selected;
                g.appendChild(svgEl('rect', {
                    x: node.x - w / 2, y: node.y - H / 2, width: w, height: H, rx: 7,
                    class: svgToneOf(node.arg),
                    'stroke-width': on ? 3 : 1.5
                }));

                const t = svgEl('text', {
                    x: node.x, y: node.y + 4, 'text-anchor': 'middle',
                    class: 'fill-gray-800 dark:fill-slate-100',
                    'font-size': 12, 'font-family': 'monospace', 'font-weight': 600
                });
                t.textContent = label;
                g.appendChild(t);

                if (showOrder) {
                    const num = svgEl('text', {
                        x: node.x, y: node.y - H / 2 - 5, 'text-anchor': 'middle',
                        class: 'fill-gray-400 dark:fill-slate-500',
                        'font-size': 11, 'font-family': 'monospace'
                    });
                    num.textContent = '№' + node.order;
                    g.appendChild(num);
                }

                const tip = svgEl('title', {});
                tip.textContent = fn.label(node.arg) + ' = ' + node.value +
                    ' · вызов №' + node.order + ' из ' + tree.all.length +
                    ' · глубина ' + (node.depth + 1);
                g.appendChild(tip);

                svg.appendChild(g);
            });

            treeHost.appendChild(svg);
        }

        function render() {
            const tree = buildTree(fn, n);

            funcKeys.forEach(function (key) {
                if (funcBtns[key]) funcBtns[key].className = (key === fnKey) ? CHIP_ON : CHIP;
            });
            ruleLine.textContent = fn.rule;

            nSlider.min = String(fn.minN);
            nSlider.max = String(fn.maxN);
            nSlider.value = String(n);
            nLabel.textContent = 'n = ' + n;

            valuesBtn.className = showValues ? CHIP_ON : CHIP;
            orderBtn.className = showOrder ? CHIP_ON : CHIP;

            renderTree(tree);

            // ── сколько раз встречается каждая подзадача ─────────
            const counts = {};
            tree.all.forEach(function (node) {
                counts[node.arg] = (counts[node.arg] || 0) + 1;
            });
            const args = Object.keys(counts).map(Number).sort(function (a, b) { return a - b; });

            legendRow.innerHTML = '';
            args.forEach(function (arg) {
                const chip = document.createElement('button');
                chip.type = 'button';
                chip.className = 'inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-xs transition-colors ' +
                    toneOf(arg) + (selected === arg ? ' ring-2 ring-brand-500 dark:ring-cyan-400' : '');
                chip.innerHTML = '<span class="font-mono font-semibold">' + escapeHtml(fn.label(arg)) +
                    '</span><span class="font-mono opacity-70">×' + counts[arg] + '</span>';
                chip.addEventListener('click', function () { pick(arg); });
                legendRow.appendChild(chip);
            });

            const total = tree.all.length;
            const distinct = args.length;
            const repeats = total - distinct;
            const depth = Math.max.apply(null, tree.all.map(function (node) { return node.depth; })) + 1;

            statsRow.innerHTML = '';
            [
                ['вызовов: ' + total, BADGE],
                ['разных подзадач: ' + distinct, BADGE],
                ['глубина: ' + depth, BADGE],
                [repeats > 0 ? 'повторных вызовов: ' + repeats : 'повторов нет',
                 repeats > 0 ? BADGE_WARN : BADGE_OK]
            ].forEach(function (pair) {
                const badge = document.createElement('span');
                badge.className = pair[1];
                badge.textContent = pair[0];
                statsRow.appendChild(badge);
            });

            if (selected !== null) {
                const c = counts[selected];
                noteLine.textContent = c > 1
                    ? fn.label(selected) + ' считается ' + c + ' ' + plural(c, 'раз', 'раза', 'раз') +
                      ', и каждый раз заново — результат прошлого раза нигде не сохранился.'
                    : fn.label(selected) + ' встречается в дереве один раз.';
            } else if (repeats > 0) {
                noteLine.textContent = 'Разных подзадач всего ' + distinct + ', а вызовов ' + total +
                    ': остальные ' + repeats + ' ' + plural(repeats, 'вызов посчитал', 'вызова посчитали', 'вызовов посчитали') +
                    ' то, что уже было посчитано. Нажмите на любой узел или на плашку под деревом — ' +
                    'подсветятся все места, где эта подзадача считается снова.';
            } else {
                noteLine.textContent = 'Каждая подзадача встречается ровно один раз: дерево вызовов ' +
                    'выродилось в цепочку, повторного счёта нет.';
            }
        }

        render();
    });

    // ─────────────────────────────────────────────────────────────
    // Виджет: graph-view — граф и его запись в памяти (блок 13).
    //
    // Слева граф на SVG, справа — те же данные в виде матрицы смежности,
    // списка смежности и списка рёбер. Картинка и панели связаны в обе
    // стороны: наведение на ребро подсвечивает обе клетки матрицы и обе
    // строки списка смежности (одно ребро — две записи), наведение на
    // вершину — её строку и столбец, наведение на клетку матрицы — само
    // ребро. Граф редактируется: вершину можно перетащить мышью, клик по
    // вершине и затем по второй добавляет или убирает ребро, клик по клетке
    // матрицы делает то же самое. Кнопка «перемешать» раскладывает вершины
    // по кругу в случайном порядке — рисунок меняется, а запись справа
    // остаётся прежней (главная мысль урока 13.1: граф — не картинка).
    //
    // Конфиг:
    //   {
    //     "labels": ["А","Б","В"],  // подписи вершин; без них — номера 0..n−1
    //     "n": 5,                    // сколько вершин, если labels не заданы
    //     "edges": [[0,1],[0,2,7]],  // пары вершин, третье число — вес ребра
    //     "directed": false,
    //     "weighted": false,
    //     "panels": ["matrix","adj","edges"],  // по умолчанию matrix+adj, [] — без панелей
    //     "editable": true,          // можно ли менять граф (по умолчанию да)
    //     "toggles": true,           // показывать переключатели «ориентированный»/«взвешенный»
    //     "stats": true,             // строка бейджей под виджетом
    //     "note": "…",               // пояснение под виджетом
    //     "presets": [{"title":"Дерево","labels":[…],"edges":[…],"note":"…"}]
    //   }
    // Вершину в рёбрах можно задавать и подписью: ["А","Б"] — ищется в labels.
    // Петли и кратные рёбра поддерживаются (мосты Кёнигсберга): в клетке
    // матрицы оказывается число рёбер, и виджет отдельно предупреждает об
    // этом бейджем — обычная матрица смежности кратные рёбра не хранит.
    // Вершин не больше 12: дальше матрица перестаёт читаться.
    // ─────────────────────────────────────────────────────────────
    let graphViewSeq = 0;

    register('graph-view', function (el, config) {
        const SVG_NS = 'http://www.w3.org/2000/svg';
        const uid = 'gv' + (++graphViewSeq);

        const CHIP = 'px-2.5 py-1 rounded-full text-xs border transition-colors bg-gray-50 text-gray-500 border-gray-200 hover:bg-gray-100 dark:bg-slate-700 dark:border-slate-600 dark:text-slate-300';
        const CHIP_ON = 'px-2.5 py-1 rounded-full text-xs border transition-colors bg-brand-600 text-white border-brand-600 dark:bg-cyan-500 dark:border-cyan-500';
        const BTN = 'px-2.5 py-1 rounded-md border text-xs transition-colors bg-white text-gray-700 border-gray-200 hover:bg-gray-100 disabled:opacity-40 dark:bg-slate-700 dark:border-slate-600 dark:text-slate-200';
        const BADGE = 'px-2 py-0.5 rounded-md text-xs font-semibold border bg-gray-100 border-gray-200 text-gray-600 dark:bg-slate-700 dark:border-slate-600 dark:text-slate-300';
        const BADGE_OK = 'px-2 py-0.5 rounded-md text-xs font-semibold border bg-emerald-50 border-emerald-300 text-emerald-700 dark:bg-emerald-900/30 dark:border-emerald-700 dark:text-emerald-300';
        const BADGE_WARN = 'px-2 py-0.5 rounded-md text-xs font-semibold border bg-amber-50 border-amber-300 text-amber-700 dark:bg-amber-900/30 dark:border-amber-700 dark:text-amber-300';
        const CAP = 'text-xs uppercase tracking-wide text-gray-400 dark:text-slate-500';

        const VBW = 430, VBH = 300;      // система координат SVG
        const NODE_H = 28;               // высота плашки вершины
        const MAX_V = 12;
        const LETTERS = 'АБВГДЕЖЗИКЛМ';

        function plural(n, one, few, many) {
            const d10 = n % 10, d100 = n % 100;
            if (d10 === 1 && d100 !== 11) return one;
            if (d10 >= 2 && d10 <= 4 && (d100 < 12 || d100 > 14)) return few;
            return many;
        }

        // ── чтение конфига в состояние ───────────────────────────
        function buildState(src) {
            let labels = Array.isArray(src.labels)
                ? src.labels.map(function (s) { return String(s); })
                : null;
            const rawEdges = Array.isArray(src.edges) ? src.edges : [];

            if (!labels) {
                let n = parseInt(src.n, 10);
                if (!(n > 0)) {
                    // Число вершин не задано — берём максимальный номер в рёбрах.
                    let mx = -1;
                    rawEdges.forEach(function (e) {
                        if (!Array.isArray(e)) return;
                        [e[0], e[1]].forEach(function (v) {
                            const num = parseInt(v, 10);
                            if (!isNaN(num) && num > mx) mx = num;
                        });
                    });
                    n = mx + 1;
                }
                labels = [];
                for (let i = 0; i < n; i++) labels.push(String(i));
            }
            labels = labels.slice(0, MAX_V);

            function idxOf(v) {
                const pos = labels.indexOf(String(v));
                if (pos >= 0) return pos;
                const num = parseInt(v, 10);
                return isNaN(num) ? -1 : num;
            }

            const edges = [];
            rawEdges.forEach(function (e) {
                if (!Array.isArray(e) || e.length < 2) return;
                const a = idxOf(e[0]), b = idxOf(e[1]);
                if (a < 0 || b < 0 || a >= labels.length || b >= labels.length) return;
                const w = e.length > 2 ? parseInt(e[2], 10) : 1;
                edges.push({ a: a, b: b, w: (isNaN(w) || w < 1) ? 1 : Math.min(w, 99) });
            });

            return {
                labels: labels,
                edges: edges,
                dir: src.directed === true,
                wt: src.weighted === true,
                note: src.note ? String(src.note) : ''
            };
        }

        const presets = (Array.isArray(config.presets) ? config.presets : []).slice(0, 6);
        const panels = (Array.isArray(config.panels) ? config.panels : ['matrix', 'adj'])
            .filter(function (p) { return p === 'matrix' || p === 'adj' || p === 'edges'; });
        const editable = config.editable !== false;
        const showToggles = config.toggles !== false;
        const showStats = config.stats !== false;

        let st = buildState(config);
        let presetIdx = -1;
        let pos = [];
        let sel = null;      // выбранная вершина
        let selE = null;     // выбранное ребро
        let hov = null;      // {t:'v'|'e', i} — что подсвечено
        let hovKey = '';
        let drag = null;

        // ── раскладка ────────────────────────────────────────────
        // По кругу. С shuffle вершины садятся в случайные места круга и на
        // разное расстояние от центра: список рёбер тот же, картинка другая.
        function layout(shuffle) {
            const n = st.labels.length;
            const cx = VBW / 2, cy = VBH / 2;
            const R = Math.min(VBW, VBH) / 2 - 36;
            const order = [];
            for (let i = 0; i < n; i++) order.push(i);
            if (shuffle) {
                for (let i = order.length - 1; i > 0; i--) {
                    const j = Math.floor(Math.random() * (i + 1));
                    const t = order[i]; order[i] = order[j]; order[j] = t;
                }
            }
            pos = [];
            order.forEach(function (v, slot) {
                const a = -Math.PI / 2 + 2 * Math.PI * slot / Math.max(n, 1);
                const rr = shuffle ? R * (0.68 + Math.random() * 0.36) : R;
                pos[v] = { x: cx + rr * Math.cos(a), y: cy + rr * Math.sin(a) * 0.84 };
            });
            if (n === 1) pos[0] = { x: cx, y: cy };
            for (let i = 0; i < n; i++) clampPos(i);
        }

        function nodeW(i) {
            return Math.max(34, String(st.labels[i]).length * 7.6 + 16);
        }
        function hasLoop(i) {
            return st.edges.some(function (e) { return e.a === i && e.b === i; });
        }
        function clampPos(i) {
            const hw = nodeW(i) / 2 + 4;
            const top = NODE_H / 2 + (hasLoop(i) ? 60 : 4);
            pos[i].x = Math.min(Math.max(pos[i].x, hw), VBW - hw);
            pos[i].y = Math.min(Math.max(pos[i].y, top), VBH - NODE_H / 2 - 4);
        }

        // ── операции над графом ──────────────────────────────────
        function edgeBetween(a, b) {
            for (let i = 0; i < st.edges.length; i++) {
                const e = st.edges[i];
                if (e.a === a && e.b === b) return i;
                if (!st.dir && e.a === b && e.b === a) return i;
            }
            return -1;
        }
        function toggleEdge(a, b) {
            const i = edgeBetween(a, b);
            if (i >= 0) {
                st.edges.splice(i, 1);
                if (selE === i) selE = null;
                else if (selE !== null && selE > i) selE--;
            } else {
                st.edges.push({ a: a, b: b, w: 1 });
            }
        }
        function nextLabel() {
            const n = st.labels.length;
            const numeric = st.labels.every(function (s, i) { return s === String(i); });
            if (numeric) return String(n);
            for (let i = 0; i < LETTERS.length; i++) {
                if (st.labels.indexOf(LETTERS[i]) < 0) return LETTERS[i];
            }
            return String(n);
        }
        function dropVertex(v) {
            st.edges = st.edges.filter(function (e) { return e.a !== v && e.b !== v; });
            st.edges.forEach(function (e) {
                if (e.a > v) e.a--;
                if (e.b > v) e.b--;
            });
            st.labels.splice(v, 1);
            sel = null; selE = null; hov = null; hovKey = '';
        }

        // ── считалки для бейджей ─────────────────────────────────
        function degOf(i) {
            let d = 0, din = 0, dout = 0;
            st.edges.forEach(function (e) {
                if (e.a === i) { dout++; d++; }
                if (e.b === i) { din++; d++; }   // петля даёт +2 — так и положено
            });
            return { d: d, in: din, out: dout };
        }
        function neighbours(i) {
            // Соседи без учёта направления — для связности и двудольности.
            const out = [];
            st.edges.forEach(function (e) {
                if (e.a === i && e.b !== i) out.push(e.b);
                else if (e.b === i && e.a !== i) out.push(e.a);
            });
            return out;
        }
        function components() {
            const n = st.labels.length;
            const seen = [];
            let count = 0;
            for (let s = 0; s < n; s++) {
                if (seen[s]) continue;
                count++;
                const stack = [s];
                seen[s] = true;
                while (stack.length) {
                    const v = stack.pop();
                    neighbours(v).forEach(function (u) {
                        if (!seen[u]) { seen[u] = true; stack.push(u); }
                    });
                }
            }
            return count;
        }
        function isBipartite() {
            const n = st.labels.length;
            if (n === 0) return false;
            if (st.edges.some(function (e) { return e.a === e.b; })) return false;
            const color = [];
            for (let s = 0; s < n; s++) {
                if (color[s] !== undefined) continue;
                color[s] = 0;
                const stack = [s];
                while (stack.length) {
                    const v = stack.pop();
                    const bad = neighbours(v).some(function (u) {
                        if (color[u] === undefined) {
                            color[u] = 1 - color[v];
                            stack.push(u);
                            return false;
                        }
                        return color[u] === color[v];
                    });
                    if (bad) return false;
                }
            }
            return true;
        }
        function multiCount() {
            const seen = {};
            let multi = 0, loops = 0;
            st.edges.forEach(function (e) {
                if (e.a === e.b) { loops++; return; }
                const k = st.dir ? e.a + '>' + e.b
                    : Math.min(e.a, e.b) + ':' + Math.max(e.a, e.b);
                if (seen[k]) multi++;
                seen[k] = true;
            });
            return { multi: multi, loops: loops };
        }
        function isTree() {
            const m = multiCount();
            return !st.dir && st.labels.length > 0 && m.multi === 0 && m.loops === 0 &&
                components() === 1 && st.edges.length === st.labels.length - 1;
        }

        // Клетка матрицы: сколько рёбер ведёт из r в c и с каким наименьшим весом.
        function cellOf(r, c) {
            let cnt = 0, w = null;
            st.edges.forEach(function (e) {
                const hit = (e.a === r && e.b === c) || (!st.dir && e.a === c && e.b === r);
                if (!hit) return;
                cnt++;
                w = (w === null) ? e.w : Math.min(w, e.w);
            });
            return { cnt: cnt, w: w };
        }
        // Строка списка смежности: соседи вершины и номера рёбер, по которым
        // они там оказались (номер нужен для подсветки).
        function adjOf(i) {
            const out = [];
            st.edges.forEach(function (e, ei) {
                if (e.a === i) out.push({ v: e.b, e: ei });
                else if (!st.dir && e.b === i) out.push({ v: e.a, e: ei });
            });
            out.sort(function (x, y) { return x.v - y.v; });
            return out;
        }

        // ── подсветка ────────────────────────────────────────────
        function setHov(h) {
            const k = h ? h.t + ':' + h.i : '';
            if (k === hovKey) return;   // без этой проверки перерисовка зациклится
            hovKey = k;
            hov = h;
            render();
        }
        function edgeHot(ei) {
            if (!hov) return false;
            if (hov.t === 'e') return hov.i === ei;
            const e = st.edges[ei];
            return !!e && (e.a === hov.i || e.b === hov.i);
        }
        function vertHot(v) {
            if (!hov) return false;
            if (hov.t === 'v') return hov.i === v;
            const e = st.edges[hov.i];
            return !!e && (e.a === v || e.b === v);
        }
        function cellHot(r, c) {
            if (!hov) return false;
            if (hov.t === 'v') return r === hov.i || c === hov.i;
            const e = st.edges[hov.i];
            if (!e) return false;
            return (r === e.a && c === e.b) || (!st.dir && r === e.b && c === e.a);
        }

        // ── рамка и управление ───────────────────────────────────
        const body = widgetFrame(el, el.dataset.title || 'Граф');

        const presetRow = document.createElement('div');
        presetRow.className = 'flex flex-wrap items-center gap-2';
        const presetBtns = [];
        if (presets.length) {
            const cap = document.createElement('span');
            cap.className = CAP;
            cap.textContent = 'примеры';
            presetRow.appendChild(cap);
            presets.forEach(function (p, i) {
                const btn = document.createElement('button');
                btn.type = 'button';
                btn.textContent = p.title || ('пример ' + (i + 1));
                btn.addEventListener('click', function () {
                    st = buildState(p);
                    presetIdx = i;
                    sel = null; selE = null; hov = null; hovKey = '';
                    layout(false);
                    render();
                });
                presetBtns.push(btn);
                presetRow.appendChild(btn);
            });
        }

        const ctrlRow = document.createElement('div');
        ctrlRow.className = 'mt-2 flex flex-wrap items-center gap-2';

        const dirBtn = document.createElement('button');
        dirBtn.type = 'button';
        dirBtn.textContent = 'ориентированный';
        dirBtn.addEventListener('click', function () {
            st.dir = !st.dir;
            render();
        });

        const wtBtn = document.createElement('button');
        wtBtn.type = 'button';
        wtBtn.textContent = 'взвешенный';
        wtBtn.addEventListener('click', function () {
            st.wt = !st.wt;
            render();
        });

        if (showToggles) {
            ctrlRow.appendChild(dirBtn);
            ctrlRow.appendChild(wtBtn);
        }

        function toolBtn(text, handler) {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = BTN;
            btn.textContent = text;
            btn.addEventListener('click', handler);
            ctrlRow.appendChild(btn);
            return btn;
        }

        let addBtn = null, delBtn = null;
        if (editable) {
            addBtn = toolBtn('+ вершина', function () {
                if (st.labels.length >= MAX_V) return;
                st.labels.push(nextLabel());
                layout(false);       // новая вершина садится на круг вместе со всеми
                render();
            });
            delBtn = toolBtn('− вершина', function () {
                if (!st.labels.length) return;
                dropVertex(sel !== null ? sel : st.labels.length - 1);
                layout(false);
                render();
            });
        }
        toolBtn('перемешать', function () {
            layout(true);
            render();
        });
        toolBtn('сброс', function () {
            st = buildState(presetIdx >= 0 ? presets[presetIdx] : config);
            sel = null; selE = null; hov = null; hovKey = '';
            layout(false);
            render();
        });

        // ── графическая часть и панели ───────────────────────────
        const mainRow = document.createElement('div');
        mainRow.className = 'mt-3 flex flex-wrap items-start gap-4';

        const graphHost = document.createElement('div');
        graphHost.className = 'flex-1 min-w-[260px]';

        const panelHost = document.createElement('div');
        panelHost.className = 'flex-1 min-w-[240px] flex flex-col gap-3';

        mainRow.appendChild(graphHost);
        if (panels.length) mainRow.appendChild(panelHost);

        const selRow = document.createElement('div');
        selRow.className = 'mt-3 flex flex-wrap items-center gap-2';

        const statsRow = document.createElement('div');
        statsRow.className = 'mt-3 flex flex-wrap items-center gap-2';

        const hintLine = document.createElement('div');
        hintLine.className = 'mt-2 text-sm text-gray-600 dark:text-slate-300';

        const noteLine = document.createElement('div');
        noteLine.className = 'mt-1 text-sm text-gray-500 dark:text-slate-400';

        if (presets.length) body.appendChild(presetRow);
        body.appendChild(ctrlRow);   // «перемешать» и «сброс» есть всегда
        body.appendChild(mainRow);
        body.appendChild(selRow);
        if (showStats) body.appendChild(statsRow);
        body.appendChild(hintLine);
        body.appendChild(noteLine);

        function svgEl(name, attrs) {
            const node = document.createElementNS(SVG_NS, name);
            Object.keys(attrs || {}).forEach(function (k) {
                node.setAttribute(k, attrs[k]);
            });
            return node;
        }

        // Точка выхода из прямоугольной плашки вершины в сторону (tx, ty):
        // луч из центра до границы рамки. Нужна, чтобы линия ребра не
        // заезжала под плашку и стрелка стояла у самого её края.
        function boxPoint(i, tx, ty) {
            const p = pos[i];
            const hw = nodeW(i) / 2 + 3, hh = NODE_H / 2 + 3;
            let dx = tx - p.x, dy = ty - p.y;
            const len = Math.sqrt(dx * dx + dy * dy) || 1;
            dx /= len; dy /= len;
            const sx = Math.abs(dx) < 1e-6 ? Infinity : hw / Math.abs(dx);
            const sy = Math.abs(dy) < 1e-6 ? Infinity : hh / Math.abs(dy);
            const s = Math.min(sx, sy);
            return { x: p.x + dx * s, y: p.y + dy * s };
        }

        // Кратные рёбра и пара «туда-обратно» разводятся дугами в разные стороны.
        function curvatures() {
            const groups = {};
            st.edges.forEach(function (e, i) {
                const k = Math.min(e.a, e.b) + ':' + Math.max(e.a, e.b);
                (groups[k] = groups[k] || []).push(i);
            });
            const out = [];
            Object.keys(groups).forEach(function (k) {
                const list = groups[k];
                list.forEach(function (ei, t) {
                    // Шаг подобран так, чтобы у пары рёбер не слипались плашки
                    // с весами: между серединами дуг остаётся около 23 px.
                    out[ei] = (t - (list.length - 1) / 2) * 46;
                });
            });
            return out;
        }

        function edgePath(e, off) {
            if (e.a === e.b) {
                const p = pos[e.a];
                const hw = nodeW(e.a) / 2, hh = NODE_H / 2;
                const x1 = p.x - hw * 0.45, x2 = p.x + hw * 0.45, y = p.y - hh;
                return {
                    d: 'M ' + x1 + ' ' + y +
                        ' C ' + (x1 - 22) + ' ' + (y - 48) +
                        ', ' + (x2 + 22) + ' ' + (y - 48) +
                        ', ' + x2 + ' ' + y,
                    lx: p.x, ly: y - 34
                };
            }
            const p1 = pos[e.a], p2 = pos[e.b];
            const dx = p2.x - p1.x, dy = p2.y - p1.y;
            const len = Math.sqrt(dx * dx + dy * dy) || 1;
            // Нормаль считаем от младшей вершины к старшей: иначе у пары
            // «туда-обратно» обе дуги уходят в одну сторону и сливаются.
            const dirSign = e.a <= e.b ? 1 : -1;
            const nx = -dy / len * dirSign, ny = dx / len * dirSign;
            const mx = (p1.x + p2.x) / 2 + nx * off;
            const my = (p1.y + p2.y) / 2 + ny * off;
            const s = boxPoint(e.a, mx, my), t = boxPoint(e.b, mx, my);
            return {
                d: 'M ' + s.x + ' ' + s.y + ' Q ' + mx + ' ' + my + ' ' + t.x + ' ' + t.y,
                lx: (s.x + 2 * mx + t.x) / 4, ly: (s.y + 2 * my + t.y) / 4
            };
        }

        function renderGraph() {
            graphHost.innerHTML = '';
            const svg = svgEl('svg', {
                viewBox: '0 0 ' + VBW + ' ' + VBH,
                class: 'w-full h-auto block select-none touch-none',
                role: 'img'
            });

            const defs = svgEl('defs', {});
            [['arrow-' + uid, 'fill-gray-400 dark:fill-slate-500'],
             ['arrowhl-' + uid, 'fill-brand-600 dark:fill-cyan-400'],
             ['arrowsel-' + uid, 'fill-amber-500 dark:fill-amber-400']].forEach(function (pair) {
                const m = svgEl('marker', {
                    id: pair[0], markerWidth: 9, markerHeight: 9, refX: 8.5, refY: 4.5,
                    orient: 'auto', markerUnits: 'userSpaceOnUse'
                });
                m.appendChild(svgEl('path', { d: 'M 0 0 L 9 4.5 L 0 9 z', class: pair[1] }));
                defs.appendChild(m);
            });
            svg.appendChild(defs);

            const curve = curvatures();

            st.edges.forEach(function (e, ei) {
                const geom = edgePath(e, curve[ei] || 0);
                const hot = edgeHot(ei), picked = selE === ei;
                const cls = picked
                    ? 'stroke-amber-500 dark:stroke-amber-400'
                    : (hot ? 'stroke-brand-600 dark:stroke-cyan-400'
                           : 'stroke-gray-400 dark:stroke-slate-500');
                const g = svgEl('g', { class: 'cursor-pointer' });

                // Широкая прозрачная линия поверх тонкой — чтобы в ребро было
                // легко попасть мышью.
                const line = svgEl('path', {
                    d: geom.d, fill: 'none', class: cls,
                    'stroke-width': (hot || picked) ? 3.5 : 2,
                    'stroke-linecap': 'round'
                });
                if (st.dir) {
                    line.setAttribute('marker-end', 'url(#' +
                        (picked ? 'arrowsel-' : hot ? 'arrowhl-' : 'arrow-') + uid + ')');
                }
                g.appendChild(line);
                g.appendChild(svgEl('path', {
                    d: geom.d, fill: 'none', stroke: 'transparent', 'stroke-width': 14
                }));

                if (st.wt) {
                    g.appendChild(svgEl('rect', {
                        x: geom.lx - 11, y: geom.ly - 9, width: 22, height: 18, rx: 5,
                        class: 'fill-white stroke-gray-200 dark:fill-slate-800 dark:stroke-slate-600'
                    }));
                    const t = svgEl('text', {
                        x: geom.lx, y: geom.ly + 4, 'text-anchor': 'middle',
                        class: 'fill-gray-700 dark:fill-slate-200',
                        'font-size': 11, 'font-family': 'monospace', 'font-weight': 600
                    });
                    t.textContent = e.w;
                    g.appendChild(t);
                }

                const tip = svgEl('title', {});
                tip.textContent = st.labels[e.a] + (st.dir ? ' → ' : ' — ') + st.labels[e.b] +
                    (st.wt ? ', вес ' + e.w : '');
                g.appendChild(tip);

                g.addEventListener('mouseenter', function () { setHov({ t: 'e', i: ei }); });
                g.addEventListener('mouseleave', function () { setHov(null); });
                g.addEventListener('click', function (evt) {
                    evt.stopPropagation();
                    selE = (selE === ei) ? null : ei;
                    sel = null;
                    render();
                });
                svg.appendChild(g);
            });

            st.labels.forEach(function (label, i) {
                const p = pos[i], w = nodeW(i);
                const hot = vertHot(i), picked = sel === i;
                const g = svgEl('g', { class: editable ? 'cursor-pointer' : 'cursor-default' });

                g.appendChild(svgEl('rect', {
                    x: p.x - w / 2, y: p.y - NODE_H / 2, width: w, height: NODE_H, rx: 9,
                    class: picked
                        ? 'fill-amber-100 stroke-amber-500 dark:fill-amber-800 dark:stroke-amber-400'
                        : (hot
                            ? 'fill-brand-50 stroke-brand-500 dark:fill-cyan-900 dark:stroke-cyan-400'
                            : 'fill-white stroke-gray-300 dark:fill-slate-700 dark:stroke-slate-500'),
                    'stroke-width': (hot || picked) ? 2.5 : 1.5
                }));

                const t = svgEl('text', {
                    x: p.x, y: p.y + 4, 'text-anchor': 'middle',
                    class: 'fill-gray-800 dark:fill-slate-100 pointer-events-none',
                    'font-size': 12, 'font-family': 'monospace', 'font-weight': 600
                });
                t.textContent = label;
                g.appendChild(t);

                const d = degOf(i);
                const tip = svgEl('title', {});
                tip.textContent = st.dir
                    ? label + ': входит ' + d.in + ', выходит ' + d.out
                    : label + ': степень ' + d.d;
                g.appendChild(tip);

                g.addEventListener('mouseenter', function () { setHov({ t: 'v', i: i }); });
                g.addEventListener('mouseleave', function () { setHov(null); });
                g.addEventListener('pointerdown', function (evt) {
                    evt.preventDefault();
                    drag = { v: i, moved: 0, svg: svg };
                });
                svg.appendChild(g);
            });

            svg.addEventListener('click', function () {
                // Клик по пустому месту снимает выделение.
                if (sel !== null || selE !== null) {
                    sel = null; selE = null;
                    render();
                }
            });

            graphHost.appendChild(svg);
        }

        // Перетаскивание слушаем на документе: во время перерисовки узел под
        // курсором заменяется новым, и обработчик на нём бы потерялся.
        function svgPoint(svg, evt) {
            const r = svg.getBoundingClientRect();
            const kx = VBW / (r.width || VBW), ky = VBH / (r.height || VBH);
            return { x: (evt.clientX - r.left) * kx, y: (evt.clientY - r.top) * ky };
        }
        document.addEventListener('pointermove', function (evt) {
            if (!drag) return;
            const p = svgPoint(drag.svg, evt);
            drag.moved++;
            pos[drag.v] = { x: p.x, y: p.y };
            clampPos(drag.v);
            render();
        });
        document.addEventListener('pointerup', function () {
            if (!drag) return;
            const v = drag.v, moved = drag.moved;
            drag = null;
            if (moved > 2) return;          // это было перетаскивание, а не клик
            if (!editable) {
                sel = null; selE = null; render(); return;
            }
            selE = null;
            if (sel === null) sel = v;
            else if (sel === v) sel = null;
            else { toggleEdge(sel, v); sel = null; }
            render();
        });

        // ── панели ───────────────────────────────────────────────
        function panelBox(caption) {
            const box = document.createElement('div');
            const cap = document.createElement('div');
            cap.className = CAP;
            cap.textContent = caption;
            box.appendChild(cap);
            const inner = document.createElement('div');
            inner.className = 'mt-1 overflow-x-auto';
            box.appendChild(inner);
            panelHost.appendChild(box);
            return inner;
        }

        function renderMatrix() {
            const host = panelBox('матрица смежности');
            const n = st.labels.length;
            const table = document.createElement('table');
            table.className = 'border-collapse font-mono text-xs';

            const head = document.createElement('tr');
            const corner = document.createElement('th');
            corner.className = 'w-7 h-7';
            head.appendChild(corner);
            st.labels.forEach(function (label, c) {
                const th = document.createElement('th');
                th.className = 'w-7 h-7 text-center font-semibold ' +
                    (vertHot(c) ? 'text-brand-600 dark:text-cyan-400'
                                : 'text-gray-400 dark:text-slate-500');
                th.textContent = label;
                head.appendChild(th);
            });
            table.appendChild(head);

            for (let r = 0; r < n; r++) {
                const tr = document.createElement('tr');
                const th = document.createElement('th');
                th.className = 'w-7 h-7 text-center font-semibold ' +
                    (vertHot(r) ? 'text-brand-600 dark:text-cyan-400'
                                : 'text-gray-400 dark:text-slate-500');
                th.textContent = st.labels[r];
                tr.appendChild(th);

                for (let c = 0; c < n; c++) {
                    const cell = cellOf(r, c);
                    const td = document.createElement('td');
                    const hot = cellHot(r, c);
                    let cls = 'w-7 h-7 text-center border align-middle transition-colors ';
                    if (cell.cnt > 0) {
                        cls += 'bg-brand-600 text-white border-brand-600 dark:bg-cyan-500 dark:border-cyan-500 ';
                    } else if (r === c) {
                        cls += 'bg-gray-50 text-gray-300 border-gray-100 dark:bg-slate-800 dark:text-slate-600 dark:border-slate-700 ';
                    } else {
                        cls += 'text-gray-300 border-gray-100 dark:text-slate-600 dark:border-slate-700 ';
                    }
                    if (hot) cls += 'ring-2 ring-amber-400 dark:ring-amber-300 ';
                    if (editable) cls += 'cursor-pointer';
                    td.className = cls;
                    td.textContent = st.wt
                        ? (cell.cnt ? String(cell.w) : (r === c ? '0' : '∞'))
                        : String(cell.cnt);

                    td.addEventListener('mouseenter', function () {
                        const ei = edgeBetween(r, c);
                        setHov(ei >= 0 ? { t: 'e', i: ei } : null);
                    });
                    td.addEventListener('mouseleave', function () { setHov(null); });
                    if (editable) {
                        td.addEventListener('click', function () {
                            toggleEdge(r, c);
                            sel = null;
                            hov = null; hovKey = '';
                            render();
                        });
                    }
                    tr.appendChild(td);
                }
                table.appendChild(tr);
            }
            host.appendChild(table);
        }

        function renderAdj() {
            const host = panelBox('список смежности');
            const wrap = document.createElement('div');
            wrap.className = 'font-mono text-xs leading-6';
            st.labels.forEach(function (label, i) {
                const row = document.createElement('div');
                const own = hov && hov.t === 'v' && hov.i === i;
                row.className = 'px-1 rounded ' + (own
                    ? 'bg-brand-50 dark:bg-cyan-900/40'
                    : '');
                const head = document.createElement('span');
                head.className = 'text-gray-400 dark:text-slate-500';
                head.textContent = label + ': ';
                row.appendChild(head);

                const list = adjOf(i);
                if (!list.length) {
                    const empty = document.createElement('span');
                    empty.className = 'text-gray-300 dark:text-slate-600';
                    empty.textContent = '—';
                    row.appendChild(empty);
                }
                list.forEach(function (item, k) {
                    const span = document.createElement('span');
                    const hot = hov && ((hov.t === 'e' && hov.i === item.e) ||
                        (hov.t === 'v' && hov.i === item.v));
                    span.className = 'px-0.5 rounded ' + (hot
                        ? 'bg-brand-600 text-white dark:bg-cyan-500'
                        : 'text-gray-700 dark:text-slate-200');
                    span.textContent = st.labels[item.v] + (st.wt ? '(' + st.edges[item.e].w + ')' : '');
                    span.addEventListener('mouseenter', function () { setHov({ t: 'e', i: item.e }); });
                    span.addEventListener('mouseleave', function () { setHov(null); });
                    row.appendChild(span);
                    if (k < list.length - 1) {
                        const comma = document.createElement('span');
                        comma.className = 'text-gray-400 dark:text-slate-500';
                        comma.textContent = ', ';
                        row.appendChild(comma);
                    }
                });
                wrap.appendChild(row);
            });
            host.appendChild(wrap);
        }

        function renderEdges() {
            const host = panelBox(st.dir ? 'рёбра (со стрелками)' : 'рёбра');
            const wrap = document.createElement('div');
            wrap.className = 'font-mono text-xs leading-6 flex flex-wrap gap-x-2';
            if (!st.edges.length) {
                wrap.innerHTML = '<span class="text-gray-300 dark:text-slate-600">рёбер нет</span>';
            }
            st.edges.forEach(function (e, ei) {
                const span = document.createElement('span');
                const hot = edgeHot(ei);
                span.className = 'px-1 rounded cursor-pointer ' + (hot
                    ? 'bg-brand-600 text-white dark:bg-cyan-500'
                    : 'text-gray-700 dark:text-slate-200');
                span.textContent = st.labels[e.a] + (st.dir ? '→' : '—') + st.labels[e.b] +
                    (st.wt ? ' (' + e.w + ')' : '');
                span.addEventListener('mouseenter', function () { setHov({ t: 'e', i: ei }); });
                span.addEventListener('mouseleave', function () { setHov(null); });
                wrap.appendChild(span);
            });
            host.appendChild(wrap);
        }

        // ── строка выбранного ребра ──────────────────────────────
        function renderSel() {
            selRow.innerHTML = '';
            if (selE === null || !st.edges[selE]) return;
            const e = st.edges[selE];

            const cap = document.createElement('span');
            cap.className = 'text-sm text-gray-600 dark:text-slate-300';
            cap.textContent = 'ребро ' + st.labels[e.a] + (st.dir ? ' → ' : ' — ') + st.labels[e.b];
            selRow.appendChild(cap);

            if (st.wt) {
                const minus = document.createElement('button');
                minus.type = 'button';
                minus.className = BTN;
                minus.textContent = '−';
                minus.addEventListener('click', function () {
                    e.w = Math.max(1, e.w - 1);
                    render();
                });
                const val = document.createElement('span');
                val.className = 'font-mono text-sm text-gray-800 dark:text-slate-100 w-8 text-center';
                val.textContent = 'вес ' + e.w;
                const plus = document.createElement('button');
                plus.type = 'button';
                plus.className = BTN;
                plus.textContent = '+';
                plus.addEventListener('click', function () {
                    e.w = Math.min(99, e.w + 1);
                    render();
                });
                selRow.appendChild(minus);
                selRow.appendChild(val);
                selRow.appendChild(plus);
            }

            if (editable) {
                const del = document.createElement('button');
                del.type = 'button';
                del.className = BTN;
                del.textContent = 'убрать ребро';
                del.addEventListener('click', function () {
                    st.edges.splice(selE, 1);
                    selE = null;
                    hov = null; hovKey = '';
                    render();
                });
                selRow.appendChild(del);
            }
        }

        // ── бейджи ───────────────────────────────────────────────
        function renderStats() {
            statsRow.innerHTML = '';
            const n = st.labels.length, m = st.edges.length;
            const items = [];

            items.push(['вершин: ' + n, BADGE]);
            items.push(['рёбер: ' + m, BADGE]);

            if (!st.dir && n > 0) {
                let sum = 0;
                for (let i = 0; i < n; i++) sum += degOf(i).d;
                items.push(['сумма степеней: ' + sum + ' = 2 · ' + m, BADGE]);
            }

            if (n > 0) {
                const comp = components();
                items.push(comp === 1
                    ? [st.dir ? 'связный (без учёта стрелок)' : 'связный', BADGE_OK]
                    : ['компонент связности: ' + comp, BADGE_WARN]);
            }

            if (isTree()) items.push(['это дерево: рёбер = вершин − 1', BADGE_OK]);
            if (!st.dir && n > 0 && m > 0 && isBipartite()) items.push(['двудольный', BADGE_OK]);

            const mc = multiCount();
            if (mc.multi) items.push(['кратные рёбра: в матрице стоит число, а не 0/1', BADGE_WARN]);
            if (mc.loops) items.push([mc.loops + ' ' + plural(mc.loops, 'петля', 'петли', 'петель'), BADGE_WARN]);

            // Бейдж про память показываем только там, где сами способы
            // хранения на экране: до их разбора он ничего не объясняет.
            if (panels.indexOf('matrix') >= 0 || panels.indexOf('adj') >= 0) {
                const cells = n * n;
                const nums = st.dir ? m : 2 * m;
                items.push(['матрица: ' + cells + ' ' + plural(cells, 'клетка', 'клетки', 'клеток') +
                    ' · списки: ' + nums + ' ' + plural(nums, 'число', 'числа', 'чисел'), BADGE]);
            }

            items.forEach(function (pair) {
                const badge = document.createElement('span');
                badge.className = pair[1];
                badge.textContent = pair[0];
                statsRow.appendChild(badge);
            });
        }

        function renderHint() {
            if (sel !== null) {
                hintLine.textContent = 'Выбрана вершина ' + st.labels[sel] +
                    '. Кликните по второй вершине — ребро между ними появится или исчезнет.';
            } else if (selE !== null && st.edges[selE]) {
                const e = st.edges[selE];
                hintLine.textContent = 'Выбрано ребро ' + st.labels[e.a] +
                    (st.dir ? ' → ' : ' — ') + st.labels[e.b] + '.';
            } else if (editable) {
                hintLine.textContent = 'Вершину можно перетащить мышью. Клик по вершине, ' +
                    'затем по другой — добавить или убрать ребро' +
                    (panels.indexOf('matrix') >= 0 ? '; клик по клетке матрицы делает то же самое' : '') +
                    '. Наведите курсор на ребро или вершину — подсветится, как они записаны.';
            } else {
                hintLine.textContent = 'Наведите курсор на ребро или вершину — подсветится, ' +
                    'как они записаны.';
            }
        }

        function render() {
            presetBtns.forEach(function (btn, i) {
                btn.className = (i === presetIdx) ? CHIP_ON : CHIP;
            });
            dirBtn.className = st.dir ? CHIP_ON : CHIP;
            wtBtn.className = st.wt ? CHIP_ON : CHIP;
            if (addBtn) addBtn.disabled = st.labels.length >= MAX_V;
            if (delBtn) delBtn.disabled = st.labels.length === 0;

            renderGraph();

            panelHost.innerHTML = '';
            panels.forEach(function (p) {
                if (p === 'matrix') renderMatrix();
                else if (p === 'adj') renderAdj();
                else if (p === 'edges') renderEdges();
            });

            renderSel();
            if (showStats) renderStats();
            renderHint();

            const note = (presetIdx >= 0 && presets[presetIdx].note)
                ? presets[presetIdx].note
                : (config.note || '');
            noteLine.textContent = note;
        }

        layout(false);
        render();
    });

    // ─────────────────────────────────────────────────────────────
    // Виджет: graph-walk — обход графа по шагам (уроки 13.3–13.5).
    // Слева граф, справа лента очереди (или тропинки) и порядок обхода.
    // Виджет сам прогоняет обход и раскладывает его в кадры: взяли вершину,
    // посмотрели соседа, положили нового, пропустили уже посещённого, готово.
    // В каждом кадре лежит ПОЛНОЕ состояние (посещённые, расстояния, лента,
    // дерево обхода), поэтому шаг назад и ползунок работают без пересчёта.
    //
    // Раскладка «layers»: вершины стоят строками по слоям BFS от старта —
    // сверху старт, ниже те, до кого один переход, и так далее. Волна идёт
    // сверху вниз, и слой целиком разбирается прежде, чем начнётся следующий.
    // Раскладка «circle» ставит вершины по кругу и слоёв не выдаёт.
    //
    // Два режима, каждый — правильный обход целиком; переключателя в
    // интерфейсе нет, режим задаёт конфиг. Урок показывает один обход, а не
    // сравнение вариантов «а что будет, если взять с другого конца».
    //   queue — обход в ширину очередью, урок 13.3: лента очереди, слои,
    //           расстояния (они же кратчайшие), кнопка «Слой целиком»;
    //   dfs   — обход в глубину рекурсией, урок 13.4: пометка при заходе,
    //           фиолетовая тропинка от старта до текущей вершины (она же
    //           лента справа), отдельные кадры возврата, бейдж «глубина»,
    //           кнопка «До возврата». Число у вершины здесь — длина
    //           пройденного пути, а не расстояние, и виджет предупреждает
    //           бейджем, где она оказалась не кратчайшей.
    //
    // Конфиг:
    //   {"labels": ["Центр", "Парк"], "n": 5,
    //    "edges": [[0, 1], ["Центр", "Парк"]], "start": "Центр",
    //    "mode": "queue"|"dfs", "layout": "layers"|"circle",
    //    "dist": true, "tree": true, "speed": 700, "note": "…",
    //    "presets": [{"title": "…", "labels": […], "edges": […],
    //                 "start": "…", "layout": "circle", "note": "…"}]}
    // Вершину в рёбрах можно задавать подписью или номером, вершин не больше
    // 14, пресетов до 6. Граф неориентированный; петли и кратные рёбра
    // отбрасываются — обходу они ничего не добавляют.
    // ─────────────────────────────────────────────────────────────
    register('graph-walk', function (el, config) {
        const SVG_NS = 'http://www.w3.org/2000/svg';

        const CHIP = 'px-2.5 py-1 rounded-full text-xs border transition-colors bg-gray-50 text-gray-500 border-gray-200 hover:bg-gray-100 dark:bg-slate-700 dark:border-slate-600 dark:text-slate-300';
        const CHIP_ON = 'px-2.5 py-1 rounded-full text-xs border transition-colors bg-brand-600 text-white border-brand-600 dark:bg-cyan-500 dark:border-cyan-500';
        const BTN_MAIN = 'px-3 py-1.5 rounded-full text-sm border transition-colors bg-brand-600 text-white border-brand-600 hover:bg-brand-700 dark:bg-cyan-500 dark:border-cyan-500 dark:hover:bg-cyan-400';
        const BTN_SEC = 'px-3 py-1.5 rounded-full text-sm border transition-colors bg-gray-50 text-gray-500 border-gray-200 hover:bg-gray-100 dark:bg-slate-700 dark:border-slate-600 dark:text-slate-300';
        const BADGE = 'px-2 py-0.5 rounded-md text-xs font-semibold border bg-gray-100 border-gray-200 text-gray-600 dark:bg-slate-700 dark:border-slate-600 dark:text-slate-300';
        const BADGE_OK = 'px-2 py-0.5 rounded-md text-xs font-semibold border bg-emerald-50 border-emerald-300 text-emerald-700 dark:bg-emerald-900/30 dark:border-emerald-700 dark:text-emerald-300';
        const BADGE_WARN = 'px-2 py-0.5 rounded-md text-xs font-semibold border bg-rose-50 border-rose-300 text-rose-700 dark:bg-rose-900/30 dark:border-rose-700 dark:text-rose-300';
        const CAP = 'text-xs uppercase tracking-wide text-gray-400 dark:text-slate-500';

        const MAX_V = 14;
        const VBW = 470;
        const NODE_H = 28;
        const LEFT = 58;          // поле слева под подписи слоёв
        let VBH = 300;

        function plural(n, one, few, many) {
            const d10 = n % 10, d100 = n % 100;
            if (d10 === 1 && d100 !== 11) return one;
            if (d10 >= 2 && d10 <= 4 && (d100 < 12 || d100 > 14)) return few;
            return many;
        }
        function q(s) {
            return '«' + s + '»';
        }

        // ── чтение конфига в состояние ───────────────────────────
        function buildState(src) {
            let labels = Array.isArray(src.labels)
                ? src.labels.map(function (s) { return String(s); })
                : null;
            const rawEdges = Array.isArray(src.edges) ? src.edges : [];

            if (!labels) {
                let n = parseInt(src.n, 10);
                if (!(n > 0)) {
                    let mx = -1;
                    rawEdges.forEach(function (e) {
                        if (!Array.isArray(e)) return;
                        [e[0], e[1]].forEach(function (v) {
                            const num = parseInt(v, 10);
                            if (!isNaN(num) && num > mx) mx = num;
                        });
                    });
                    n = mx + 1;
                }
                labels = [];
                for (let i = 0; i < n; i++) labels.push(String(i));
            }
            labels = labels.slice(0, MAX_V);

            function idxOf(v) {
                const pos = labels.indexOf(String(v));
                if (pos >= 0) return pos;
                const num = parseInt(v, 10);
                return isNaN(num) ? -1 : num;
            }

            // Петли и кратные рёбра обходу ничего не дают: сосед либо есть,
            // либо нет. Молча выбрасываем, чтобы лента не засорялась.
            const edges = [];
            const seen = {};
            rawEdges.forEach(function (e) {
                if (!Array.isArray(e) || e.length < 2) return;
                const a = idxOf(e[0]), b = idxOf(e[1]);
                if (a < 0 || b < 0 || a >= labels.length || b >= labels.length || a === b) return;
                const k = Math.min(a, b) + ':' + Math.max(a, b);
                if (seen[k]) return;
                seen[k] = true;
                edges.push({ a: a, b: b });
            });

            let start = src.start === undefined ? 0 : idxOf(src.start);
            if (!(start >= 0 && start < labels.length)) start = 0;

            return {
                labels: labels,
                edges: edges,
                start: start,
                layout: src.layout === 'circle' ? 'circle' : 'layers',
                note: src.note ? String(src.note) : ''
            };
        }

        // Соседи в том же порядке, в каком рёбра перечислены в конфиге, —
        // чтобы трасса виджета совпадала со списком смежности в листинге урока.
        function buildAdj(state) {
            const adj = state.labels.map(function () { return []; });
            state.edges.forEach(function (e, ei) {
                adj[e.a].push({ v: e.b, e: ei });
                adj[e.b].push({ v: e.a, e: ei });
            });
            return adj;
        }

        // Настоящие кратчайшие расстояния — нужны и для раскладки по слоям,
        // и для проверки «а что записал обход в глубину».
        function bfsDist(adj, start) {
            const d = {};
            d[start] = 0;
            const queue = [start];
            for (let h = 0; h < queue.length; h++) {
                const v = queue[h];
                adj[v].forEach(function (it) {
                    if (d[it.v] === undefined) {
                        d[it.v] = d[v] + 1;
                        queue.push(it.v);
                    }
                });
            }
            return d;
        }

        // Вершина, на которой видно, что путь, которым до неё добрался обход
        // в глубину, кратчайшим не был. У обхода в ширину такого не бывает.
        function findWrong(adj, start, dist) {
            const ref = bfsDist(adj, start);
            let wrong = null;
            Object.keys(dist).forEach(function (k) {
                if (wrong === null && dist[k] !== ref[k]) {
                    wrong = { v: parseInt(k, 10), got: dist[k], real: ref[k] };
                }
            });
            return wrong;
        }

        // ── прогон обхода в глубину рекурсией ────────────────────
        // Обход повторяет рекурсивную программу урока: заходим в вершину,
        // помечаем, сразу уходим в первого непосещённого соседа, а когда идти
        // некуда — сматываем тропинку на шаг назад. Тропинка (путь от старта
        // до текущей вершины) живёт в кадре списком `cont` и рёбрами
        // `pathEdges`, возврат — отдельный кадр `kind: 'back'`.
        function buildDfsFrames(state, adj) {
            const frames = [];
            const visited = {}, dist = {}, parent = {}, tree = {};
            const distList = [], order = [];
            const path = [];            // тропинка: путь от старта до текущей
            const pathEdges = {};       // рёбра, по которым мы сейчас стоим
            let looks = 0;

            function snap(kind, cur, look, edge, note) {
                frames.push({
                    kind: kind, cur: cur, look: look, edge: edge,
                    note: note, layer: path.length ? path.length - 1 : 0,
                    looks: looks,
                    visited: Object.assign({}, visited),
                    dist: Object.assign({}, dist),
                    parent: Object.assign({}, parent),
                    tree: Object.assign({}, tree),
                    pathEdges: Object.assign({}, pathEdges),
                    distList: distList.slice(),
                    cont: path.slice(),
                    head: 0,
                    order: order.slice()
                });
            }

            function walk(v, from, edgeIn) {
                visited[v] = true;
                dist[v] = from === null ? 0 : dist[from] + 1;
                if (from !== null) parent[v] = from;
                if (edgeIn !== null) {
                    tree[edgeIn] = true;
                    pathEdges[edgeIn] = true;
                }
                path.push(v);
                distList.push({ v: v, d: dist[v] });
                order.push(v);

                snap('enter', v, null, edgeIn, from === null
                    ? ('Заходим в старт ' + q(state.labels[v]) + ' и сразу помечаем ' +
                       'его посещённым. Тропинка справа — это путь от старта до ' +
                       'той вершины, где мы сейчас стоим.')
                    : ('Зашли в ' + q(state.labels[v]) + ': помечаем и записываем в ' +
                       'порядок обхода. Тропинка удлинилась, глубина — ' + dist[v] + '.'));

                /* eslint-disable no-loop-func */
                adj[v].forEach(function (it) {
                    looks++;
                    const nm = q(state.labels[it.v]);
                    if (visited[it.v]) {
                        snap('skip', v, it.v, it.e,
                            nm + ' уже посещена — заходить туда незачем, смотрим ' +
                            'следующего соседа. Без этой проверки обход ходил бы ' +
                            'по циклу кругами.');
                        return;
                    }
                    snap('look', v, it.v, it.e,
                        nm + ' ещё не встречалась — уходим в неё прямо сейчас, не ' +
                        'глядя на остальных соседей ' + q(state.labels[v]) + '. ' +
                        'Сама ' + q(state.labels[v]) + ' остаётся на тропинке: ' +
                        'будет куда вернуться.');
                    walk(it.v, v, it.e);
                });
                /* eslint-enable no-loop-func */

                path.pop();
                if (edgeIn !== null) delete pathEdges[edgeIn];

                if (from === null) return;
                snap('back', from, null, edgeIn,
                    'У ' + q(state.labels[v]) + ' соседи кончились — идти отсюда ' +
                    'некуда. Вот он, возврат: сматываем тропинку на шаг назад, в ' +
                    q(state.labels[from]) + ', и продолжаем с того соседа, на ' +
                    'котором остановились.');
            }

            snap('init', null, null, null,
                'Обход в глубину: заходим в вершину, помечаем её и сразу ныряем ' +
                'в первого непосещённого соседа. Возвращаемся, только когда идти ' +
                'больше некуда.');
            walk(state.start, null, null);

            const total = state.labels.length;
            const far = total - order.length;
            let maxL = 0;
            Object.keys(dist).forEach(function (k) {
                if (dist[k] > maxL) maxL = dist[k];
            });

            let note = 'Тропинка смоталась до конца: вернулись в старт, соседей ' +
                'больше нет. Обошли ' + order.length + ' ' +
                plural(order.length, 'вершину', 'вершины', 'вершин') + ' из ' + total +
                ', просмотров соседей ' + looks + ' — каждое ребро внутри обхода ' +
                'разглядывали дважды, по разу с каждого конца. Самая длинная ' +
                'тропинка была в ' + maxL + ' ' +
                plural(maxL, 'ребро', 'ребра', 'рёбер') + '.';
            if (far > 0) {
                note += ' До ' + far + ' ' + plural(far, 'вершины', 'вершин', 'вершин') +
                    ' из старта дойти нельзя: они в другой компоненте связности.';
            }
            snap('done', null, null, null, note);

            return {
                list: frames,
                wrong: findWrong(adj, state.start, dist),
                maxLayer: maxL,
                far: far
            };
        }

        // ── прогон обхода в ширину в кадры ───────────────────────
        function buildFrames(state, adj, mode) {
            if (mode === 'dfs') return buildDfsFrames(state, adj);
            const frames = [];
            const visited = {}, dist = {}, parent = {}, tree = {};
            const distList = [], order = [];
            let cont = [state.start], head = 0, looks = 0;

            visited[state.start] = true;
            dist[state.start] = 0;
            distList.push({ v: state.start, d: 0 });

            function snap(kind, cur, look, edge, note, layer) {
                frames.push({
                    kind: kind, cur: cur, look: look, edge: edge,
                    note: note, layer: layer, looks: looks,
                    visited: Object.assign({}, visited),
                    dist: Object.assign({}, dist),
                    parent: Object.assign({}, parent),
                    tree: Object.assign({}, tree),
                    distList: distList.slice(),
                    cont: cont.slice(),
                    head: head,
                    order: order.slice()
                });
            }

            snap('init', null, null, null,
                'Старт — ' + q(state.labels[state.start]) + '. Кладём его в очередь ' +
                'и сразу помечаем посещённым: расстояние до самого себя равно нулю.',
                0);

            while (head < cont.length) {
                const v = cont[head];
                head++;
                order.push(v);
                const L = dist[v];

                snap('take', v, null, null,
                    'Берём из начала очереди ' + q(state.labels[v]) + ': расстояние до неё ' +
                    L + '. Все её ещё не встреченные соседи попадут в слой ' + (L + 1) + '.',
                    L);

                /* eslint-disable no-loop-func */
                adj[v].forEach(function (it) {
                    looks++;
                    const nm = q(state.labels[it.v]);
                    if (visited[it.v]) {
                        snap('skip', v, it.v, it.e,
                            nm + ' уже посещена — второй раз в очередь она не попадёт. ' +
                            'Без этой проверки программа пошла бы по циклу кругами.', L);
                        return;
                    }
                    visited[it.v] = true;
                    dist[it.v] = L + 1;
                    distList.push({ v: it.v, d: L + 1 });
                    parent[it.v] = v;
                    tree[it.e] = true;
                    cont.push(it.v);
                    snap('push', v, it.v, it.e,
                        nm + ' ещё не встречалась: помечаем её, записываем расстояние ' +
                        (L + 1) + ' = ' + L + ' + 1 и ставим в конец очереди.', L);
                });
                /* eslint-enable no-loop-func */
            }

            const total = state.labels.length;
            const far = total - order.length;
            let maxL = 0;
            Object.keys(dist).forEach(function (k) {
                if (dist[k] > maxL) maxL = dist[k];
            });

            let note = 'Очередь опустела — обход закончен. ' +
                'Посещено ' + order.length + ' ' +
                plural(order.length, 'вершина', 'вершины', 'вершин') + ' из ' + total +
                ', просмотров соседей ' + looks + ' — каждое ребро внутри обхода ' +
                'разглядывали дважды, по разу с каждого конца.';
            if (far > 0) {
                note += ' До ' + far + ' ' + plural(far, 'вершины', 'вершин', 'вершин') +
                    ' из старта дойти нельзя: они в другой компоненте связности.';
            }
            snap('done', null, null, null, note, maxL + 1);

            // Обход в ширину записывает именно кратчайшие расстояния, поэтому
            // предупреждать здесь не о чем: wrong нужен только режиму dfs.
            return { list: frames, wrong: null, maxLayer: maxL, far: far };
        }

        // ── состояние виджета ────────────────────────────────────
        const presets = (Array.isArray(config.presets) ? config.presets : []).slice(0, 6);
        const speed = Math.min(Math.max(parseInt(config.speed, 10) || 700, 200), 2500);

        let st = buildState(config);
        let adj = buildAdj(st);
        // Режим задаётся конфигом и в интерфейсе не переключается: урок
        // показывает один обход, а не сравнение вариантов.
        const mode = config.mode === 'dfs' ? 'dfs' : 'queue';
        let showDist = config.dist !== false;
        let showTree = config.tree !== false;
        let presetIdx = -1;
        let built = buildFrames(st, adj, mode);
        let pos = 0;
        let timer = null;
        let pts = [];
        let rows = [];
        let drag = null;

        // ── раскладка ────────────────────────────────────────────
        function nodeW(i) {
            return Math.max(34, String(st.labels[i]).length * 7.6 + 16);
        }
        function clampPos(i) {
            const hw = nodeW(i) / 2 + 4;
            pts[i].x = Math.min(Math.max(pts[i].x, hw), VBW - hw);
            pts[i].y = Math.min(Math.max(pts[i].y, NODE_H / 2 + 4), VBH - NODE_H / 2 - 4);
        }
        function layout() {
            const n = st.labels.length;
            pts = [];
            rows = [];
            if (st.layout === 'circle' || n === 0) {
                VBH = 300;
                const cx = VBW / 2, cy = VBH / 2;
                const R = Math.min(VBW, VBH) / 2 - 40;
                for (let i = 0; i < n; i++) {
                    const a = -Math.PI / 2 + 2 * Math.PI * i / Math.max(n, 1);
                    pts[i] = { x: cx + R * Math.cos(a) * 1.25, y: cy + R * Math.sin(a) };
                }
                if (n === 1) pts[0] = { x: cx, y: cy };
            } else {
                const d = bfsDist(adj, st.start);
                const groups = [], far = [];
                for (let i = 0; i < n; i++) {
                    if (d[i] === undefined) far.push(i);
                    else (groups[d[i]] = groups[d[i]] || []).push(i);
                }
                groups.forEach(function (g, L) {
                    if (g) rows.push({ layer: L, list: g });
                });
                if (far.length) rows.push({ layer: null, list: far });

                const step = 54;
                VBH = 66 + (rows.length - 1) * step;
                rows.forEach(function (row, ri) {
                    const y = 26 + ri * step;
                    row.y = y;
                    row.list.forEach(function (v, k) {
                        pts[v] = {
                            x: LEFT + (VBW - LEFT - 16) * (k + 1) / (row.list.length + 1),
                            y: y
                        };
                    });
                });
            }
            for (let i = 0; i < n; i++) clampPos(i);
        }

        // ── рамка ────────────────────────────────────────────────
        const body = widgetFrame(el, el.dataset.title || 'Обход графа');

        const presetRow = document.createElement('div');
        presetRow.className = 'flex flex-wrap items-center gap-2 mb-3';
        const presetBtns = [];
        if (presets.length) {
            const cap = document.createElement('span');
            cap.className = CAP;
            cap.textContent = 'примеры';
            presetRow.appendChild(cap);
            presets.forEach(function (p, i) {
                const btn = document.createElement('button');
                btn.type = 'button';
                btn.textContent = p.title || ('пример ' + (i + 1));
                btn.addEventListener('click', function () {
                    stopPlay();
                    st = buildState(p);
                    adj = buildAdj(st);
                    presetIdx = i;
                    layout();
                    rebuild();
                });
                presetBtns.push(btn);
                presetRow.appendChild(btn);
            });
            body.appendChild(presetRow);
        }

        const mainRow = document.createElement('div');
        mainRow.className = 'flex flex-wrap items-start gap-4';
        const graphHost = document.createElement('div');
        graphHost.className = 'flex-1 min-w-[280px]';
        const panelHost = document.createElement('div');
        panelHost.className = 'flex-1 min-w-[240px] flex flex-col gap-3';
        mainRow.appendChild(graphHost);
        mainRow.appendChild(panelHost);
        body.appendChild(mainRow);

        const statsRow = document.createElement('div');
        statsRow.className = 'mt-3 flex flex-wrap items-center gap-2';
        body.appendChild(statsRow);

        const noteLine = document.createElement('div');
        noteLine.className = 'mt-2 text-sm text-gray-600 dark:text-slate-300 min-h-[2.75rem]';
        body.appendChild(noteLine);

        // ── управление ───────────────────────────────────────────
        const prevBtn = document.createElement('button');
        prevBtn.type = 'button';
        prevBtn.textContent = '← Назад';

        const nextBtn = document.createElement('button');
        nextBtn.type = 'button';
        nextBtn.textContent = 'Шаг вперёд →';

        const playBtn = document.createElement('button');
        playBtn.type = 'button';

        const layerBtn = document.createElement('button');
        layerBtn.type = 'button';
        layerBtn.textContent = 'Слой целиком';

        const endBtn = document.createElement('button');
        endBtn.type = 'button';
        endBtn.textContent = 'В конец';

        const resetBtn = document.createElement('button');
        resetBtn.type = 'button';
        resetBtn.textContent = 'Сбросить';
        resetBtn.className = BTN_SEC;

        const counter = document.createElement('span');
        counter.className = 'text-sm text-gray-400 dark:text-slate-400 ml-auto';

        const controls = document.createElement('div');
        controls.className = 'flex flex-wrap items-center gap-2 mt-3';
        [prevBtn, nextBtn, playBtn, layerBtn, endBtn, resetBtn, counter].forEach(function (b) {
            controls.appendChild(b);
        });
        body.appendChild(controls);

        const slider = document.createElement('input');
        slider.type = 'range';
        slider.min = '0';
        slider.value = '0';
        slider.className = 'w-full accent-brand-600 dark:accent-cyan-500';
        slider.setAttribute('aria-label', 'Номер шага обхода');
        body.appendChild(slider);

        const setup = document.createElement('div');
        setup.className = 'flex flex-wrap items-center gap-2 mt-4 pt-3 border-t border-gray-100 dark:border-slate-700';
        body.appendChild(setup);

        const distBtn = document.createElement('button');
        distBtn.type = 'button';
        distBtn.textContent = 'расстояния';
        distBtn.addEventListener('click', function () {
            showDist = !showDist;
            render();
        });
        setup.appendChild(distBtn);

        const treeBtn = document.createElement('button');
        treeBtn.type = 'button';
        treeBtn.textContent = 'дерево обхода';
        treeBtn.addEventListener('click', function () {
            showTree = !showTree;
            render();
        });
        setup.appendChild(treeBtn);

        const hintLine = document.createElement('div');
        hintLine.className = 'mt-2 text-sm text-gray-500 dark:text-slate-400';
        hintLine.textContent = 'Кликните по вершине — обход пойдёт от неё. ' +
            'Вершину можно перетащить мышью.';
        body.appendChild(hintLine);

        const cfgNote = document.createElement('div');
        cfgNote.className = 'mt-1 text-sm text-gray-500 dark:text-slate-400';
        body.appendChild(cfgNote);

        // ── граф ─────────────────────────────────────────────────
        function svgEl(name, attrs) {
            const node = document.createElementNS(SVG_NS, name);
            Object.keys(attrs || {}).forEach(function (k) {
                node.setAttribute(k, attrs[k]);
            });
            return node;
        }

        // Точка выхода линии из плашки вершины — чтобы ребро не заезжало
        // под подпись.
        function boxPoint(i, tx, ty) {
            const p = pts[i];
            const hw = nodeW(i) / 2 + 3, hh = NODE_H / 2 + 3;
            let dx = tx - p.x, dy = ty - p.y;
            const len = Math.sqrt(dx * dx + dy * dy) || 1;
            dx /= len; dy /= len;
            const sx = Math.abs(dx) < 1e-6 ? Infinity : hw / Math.abs(dx);
            const sy = Math.abs(dy) < 1e-6 ? Infinity : hh / Math.abs(dy);
            const s = Math.min(sx, sy);
            return { x: p.x + dx * s, y: p.y + dy * s };
        }

        function renderGraph(f) {
            graphHost.innerHTML = '';
            const svg = svgEl('svg', {
                viewBox: '0 0 ' + VBW + ' ' + VBH,
                class: 'w-full h-auto block select-none touch-none',
                role: 'img'
            });

            // Подписи слоёв слева. У обхода в глубину их не рисуем: слои
            // считаются обходом в ширину и к глубине отношения не имеют.
            (mode === 'dfs' ? [] : rows).forEach(function (row) {
                const t = svgEl('text', {
                    x: 6, y: row.y + 4,
                    class: 'fill-gray-400 dark:fill-slate-500',
                    'font-size': 11
                });
                t.textContent = row.layer === null ? 'не дойти' : 'слой ' + row.layer;
                svg.appendChild(t);
            });

            st.edges.forEach(function (e, ei) {
                const hot = f.edge === ei;
                const isTree = showTree && f.tree[ei];
                // Тропинка (только у режима рекурсии): путь от старта до
                // вершины, в которой мы стоим. Ради неё виджет и переделан —
                // на ней видно и спуск, и возврат.
                const onPath = !!(f.pathEdges && f.pathEdges[ei]);
                const s = boxPoint(e.a, pts[e.b].x, pts[e.b].y);
                const t = boxPoint(e.b, pts[e.a].x, pts[e.a].y);
                let cls, w;
                if (hot) {
                    cls = 'stroke-amber-500 dark:stroke-amber-400';
                    w = 3.5;
                } else if (onPath) {
                    cls = 'stroke-violet-500 dark:stroke-violet-400';
                    w = 4;
                } else if (isTree) {
                    cls = 'stroke-brand-600 dark:stroke-cyan-400';
                    w = 2.5;
                } else {
                    cls = 'stroke-gray-300 dark:stroke-slate-600';
                    w = 1.5;
                }
                svg.appendChild(svgEl('line', {
                    x1: s.x, y1: s.y, x2: t.x, y2: t.y, class: cls,
                    'stroke-width': w, 'stroke-linecap': 'round'
                }));
            });

            st.labels.forEach(function (label, i) {
                const p = pts[i], w = nodeW(i);
                // Вершина ждёт своей очереди: лежит в ленте правее головы.
                // У тропинки head всегда 0, поэтому проверка годится обоим.
                const inBox = f.cont.slice(f.head).indexOf(i) >= 0;
                const isCur = f.cur === i;
                const isLook = f.look === i;
                const doneV = f.order.indexOf(i) >= 0;

                let cls;
                if (isCur) {
                    cls = 'fill-brand-600 stroke-brand-700 dark:fill-cyan-500 dark:stroke-cyan-300';
                } else if (isLook) {
                    cls = 'fill-amber-100 stroke-amber-500 dark:fill-amber-800 dark:stroke-amber-400';
                } else if (inBox) {
                    cls = 'fill-amber-50 stroke-amber-400 dark:fill-slate-700 dark:stroke-amber-500';
                } else if (doneV) {
                    cls = 'fill-emerald-50 stroke-emerald-500 dark:fill-emerald-900 dark:stroke-emerald-500';
                } else {
                    cls = 'fill-white stroke-gray-300 dark:fill-slate-700 dark:stroke-slate-500';
                }

                const g = svgEl('g', { class: 'cursor-pointer' });
                g.appendChild(svgEl('rect', {
                    x: p.x - w / 2, y: p.y - NODE_H / 2, width: w, height: NODE_H, rx: 9,
                    class: cls, 'stroke-width': (isCur || isLook) ? 2.5 : 1.5
                }));

                const t = svgEl('text', {
                    x: p.x, y: p.y + 4, 'text-anchor': 'middle',
                    class: (isCur ? 'fill-white' : 'fill-gray-800 dark:fill-slate-100') +
                        ' pointer-events-none',
                    'font-size': 12, 'font-family': 'monospace', 'font-weight': 600
                });
                t.textContent = label;
                g.appendChild(t);

                if (showDist && f.dist[i] !== undefined) {
                    const d = svgEl('text', {
                        x: p.x + w / 2 + 5, y: p.y + 4,
                        class: 'fill-brand-600 dark:fill-cyan-400 pointer-events-none',
                        'font-size': 11, 'font-family': 'monospace', 'font-weight': 700
                    });
                    d.textContent = String(f.dist[i]);
                    g.appendChild(d);
                }

                const tip = svgEl('title', {});
                // У рекурсии число рядом с вершиной — не расстояние, а глубина
                // тропинки, на которой её нашли: называть вещи своими именами.
                const numWord = mode === 'dfs' ? 'глубина ' : 'расстояние ';
                tip.textContent = label +
                    (f.dist[i] === undefined
                        ? ': пока не встречалась'
                        : ': ' + numWord + f.dist[i] +
                          (f.parent[i] === undefined
                              ? ' (старт)'
                              : ', пришли из ' + q(st.labels[f.parent[i]])));
                g.appendChild(tip);

                g.addEventListener('pointerdown', function (evt) {
                    evt.preventDefault();
                    drag = { v: i, moved: 0, svg: svg };
                });
                svg.appendChild(g);
            });

            graphHost.appendChild(svg);
        }

        function svgPoint(svg, evt) {
            const r = svg.getBoundingClientRect();
            const kx = VBW / (r.width || VBW), ky = VBH / (r.height || VBH);
            return { x: (evt.clientX - r.left) * kx, y: (evt.clientY - r.top) * ky };
        }
        document.addEventListener('pointermove', function (evt) {
            if (!drag) return;
            const p = svgPoint(drag.svg, evt);
            drag.moved++;
            pts[drag.v] = { x: p.x, y: p.y };
            clampPos(drag.v);
            render();
        });
        document.addEventListener('pointerup', function () {
            if (!drag) return;
            const v = drag.v, moved = drag.moved;
            drag = null;
            if (moved > 2) return;      // это было перетаскивание, а не клик
            if (v === st.start) return;
            stopPlay();
            st.start = v;
            layout();
            rebuild();
        });

        // ── панели справа ────────────────────────────────────────
        function panelBox(caption) {
            const box = document.createElement('div');
            const cap = document.createElement('div');
            cap.className = CAP;
            cap.textContent = caption;
            box.appendChild(cap);
            const inner = document.createElement('div');
            inner.className = 'mt-1';
            box.appendChild(inner);
            panelHost.appendChild(box);
            return inner;
        }

        function renderPanels(f) {
            panelHost.innerHTML = '';
            const isDfs = mode === 'dfs';
            // У обхода в глубину лента — не очередь, а тропинка: вершины, в
            // которые мы зашли и ещё не вышли.
            const host = panelBox(isDfs ? 'тропинка' : 'очередь');
            const strip = document.createElement('div');
            strip.className = 'flex flex-wrap items-center gap-1';
            if (!f.cont.length) {
                const empty = document.createElement('span');
                empty.className = 'font-mono text-xs text-gray-400 dark:text-slate-500';
                empty.textContent = 'пусто';
                strip.appendChild(empty);
            }
            f.cont.forEach(function (v, k) {
                const cell = document.createElement('span');
                // У очереди разобранные вершины уходят влево и гасятся, у
                // тропинки гасить нечего — там все вершины ещё в работе.
                const gone = !isDfs && k < f.head;
                const next = !isDfs && k === f.head;
                const top = isDfs && k === f.cont.length - 1;
                cell.className = 'px-2 py-0.5 rounded-md border font-mono text-xs ' +
                    (gone
                        ? 'border-dashed border-gray-200 text-gray-300 line-through dark:border-slate-700 dark:text-slate-600'
                        : (next || top
                            ? 'border-brand-500 bg-brand-50 text-brand-700 font-bold dark:border-cyan-400 dark:bg-slate-700 dark:text-cyan-300'
                            : 'border-amber-300 bg-amber-50 text-amber-700 dark:border-amber-600 dark:bg-slate-700 dark:text-amber-300'));
                cell.textContent = st.labels[v];
                strip.appendChild(cell);
            });
            host.appendChild(strip);

            const ends = document.createElement('div');
            ends.className = 'mt-1 flex items-center justify-between text-[11px] text-gray-400 dark:text-slate-500';
            if (isDfs) {
                ends.innerHTML = '<span>старт</span><span>здесь мы сейчас →</span>';
            } else {
                ends.innerHTML = '<span>← берём отсюда</span><span>кладём сюда →</span>';
            }
            host.appendChild(ends);

            const oHost = panelBox('порядок обхода');
            const oLine = document.createElement('div');
            oLine.className = 'font-mono text-xs leading-6 text-gray-700 dark:text-slate-200';
            oLine.textContent = f.order.length
                ? f.order.map(function (v) { return st.labels[v]; }).join(' → ')
                : '—';
            oHost.appendChild(oLine);

            if (showDist) {
                const dHost = panelBox(isDfs ? 'глубина' : 'dist');
                const dLine = document.createElement('div');
                dLine.className = 'font-mono text-xs leading-6 break-words text-gray-700 dark:text-slate-200';
                dLine.textContent = '{' + f.distList.map(function (it) {
                    return "'" + st.labels[it.v] + "': " + it.d;
                }).join(', ') + '}';
                dHost.appendChild(dLine);
            }
        }

        function renderStats(f) {
            statsRow.innerHTML = '';
            const items = [];
            const isDfs = mode === 'dfs';
            const live = isDfs ? f.cont.length : f.cont.length - f.head;
            items.push([(isDfs ? 'на тропинке: ' : 'в очереди: ') + live, BADGE]);
            items.push(['посещено: ' + Object.keys(f.visited).length + ' из ' +
                st.labels.length, BADGE]);
            items.push(['просмотров соседей: ' + f.looks, BADGE]);
            if (f.kind !== 'done' && f.kind !== 'init') {
                items.push([(isDfs ? 'глубина: ' : 'разбираем слой ') + f.layer, BADGE_OK]);
            }
            if (f.kind === 'done' && built.far === 0 && !isDfs) {
                items.push(['все расстояния кратчайшие', BADGE_OK]);
            }
            // Число у вершины в режиме глубины — длина пройденного пути, и
            // кратчайшей она быть не обязана. Виджет показывает, где именно.
            if (built.wrong && f.dist[built.wrong.v] !== undefined) {
                items.push(['кратчайших путей это не даёт: до ' +
                    q(st.labels[built.wrong.v]) + ' дошли за ' + built.wrong.got +
                    ' ' + plural(built.wrong.got, 'ребро', 'ребра', 'рёбер') +
                    ', а хватило бы ' + built.wrong.real, BADGE_WARN]);
            }
            items.forEach(function (pair) {
                const b = document.createElement('span');
                b.className = pair[1];
                b.textContent = pair[0];
                statsRow.appendChild(b);
            });
        }

        // ── общий рендер ─────────────────────────────────────────
        function render() {
            const frames = built.list;
            const f = frames[pos];

            renderGraph(f);
            renderPanels(f);
            renderStats(f);
            noteLine.textContent = f.note;

            counter.textContent = 'шаг ' + pos + ' из ' + (frames.length - 1);
            slider.max = String(frames.length - 1);
            slider.value = String(pos);

            const atStart = pos === 0;
            const atEnd = pos >= frames.length - 1;
            prevBtn.disabled = atStart;
            prevBtn.className = BTN_SEC + (atStart ? ' opacity-50 cursor-not-allowed' : '');
            nextBtn.disabled = atEnd;
            nextBtn.className = BTN_MAIN + (atEnd ? ' opacity-50 cursor-not-allowed' : '');
            endBtn.disabled = atEnd;
            endBtn.className = BTN_SEC + (atEnd ? ' opacity-50 cursor-not-allowed' : '');
            // У обхода в ширину кнопка доигрывает слой, у обхода в глубину —
            // спуск до ближайшего возврата.
            layerBtn.textContent = mode === 'dfs' ? 'До возврата' : 'Слой целиком';
            layerBtn.disabled = atEnd;
            layerBtn.className = BTN_SEC + (atEnd ? ' opacity-50 cursor-not-allowed' : '');
            playBtn.textContent = timer ? '❚❚ Пауза' : '▶ Играть';
            playBtn.disabled = atEnd && !timer;
            playBtn.className = BTN_SEC + (atEnd && !timer ? ' opacity-50 cursor-not-allowed' : '');

            distBtn.className = showDist ? CHIP_ON : CHIP;
            treeBtn.className = showTree ? CHIP_ON : CHIP;
            presetBtns.forEach(function (b, i) {
                b.className = i === presetIdx ? CHIP_ON : CHIP;
            });

            cfgNote.textContent = (presetIdx >= 0 && presets[presetIdx].note)
                ? presets[presetIdx].note
                : (st.note || config.note || '');
        }

        function stopPlay() {
            if (timer) {
                clearInterval(timer);
                timer = null;
            }
        }
        function rebuild() {
            stopPlay();
            built = buildFrames(st, adj, mode);
            pos = 0;
            render();
        }

        prevBtn.addEventListener('click', function () {
            stopPlay();
            if (pos > 0) { pos--; render(); }
        });
        nextBtn.addEventListener('click', function () {
            stopPlay();
            if (pos < built.list.length - 1) { pos++; render(); }
        });
        // Слой целиком: шагаем вперёд и идём, пока следующий кадр относится к
        // тому же слою, — останавливаемся на последнем кадре этого слоя.
        // Слой берём у кадра, В КОТОРЫЙ перешли: иначе на границе слоёв кнопка
        // делала бы ровно один шаг.
        // У рекурсии та же кнопка доигрывает до ближайшего возврата: спуск
        // идёт молча, а останавливаемся ровно там, где обход упёрся в тупик.
        layerBtn.addEventListener('click', function () {
            stopPlay();
            const frames = built.list;
            if (pos < frames.length - 1) pos++;
            if (mode === 'dfs') {
                while (pos < frames.length - 1 && frames[pos].kind !== 'back') pos++;
            } else {
                const L = frames[pos].layer;
                while (pos < frames.length - 1 && frames[pos + 1].layer <= L) pos++;
            }
            render();
        });
        endBtn.addEventListener('click', function () {
            stopPlay();
            pos = built.list.length - 1;
            render();
        });
        resetBtn.addEventListener('click', function () {
            stopPlay();
            pos = 0;
            render();
        });
        playBtn.addEventListener('click', function () {
            if (timer) {
                stopPlay();
                render();
                return;
            }
            timer = setInterval(function () {
                if (pos >= built.list.length - 1) {
                    stopPlay();
                    render();
                    return;
                }
                pos++;
                render();
            }, speed);
            render();
        });
        slider.addEventListener('input', function () {
            stopPlay();
            pos = Math.min(Math.max(parseInt(slider.value, 10) || 0, 0), built.list.length - 1);
            render();
        });

        layout();
        render();
    });

    document.addEventListener('DOMContentLoaded', function () {
        init();
    });
})();
