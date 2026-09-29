/**
 * Маркер поверх страницы: учитель обводит условие у проектора, ученик черкает
 * на уроке у себя. Подмешивается в presentMode() (present-mode.js), поэтому
 * есть везде, где есть режим проектора: статья, тренировка, вариант, практикум.
 * Разметка – слой и панель – в _present_mode.html.
 *
 * Слой – SVG внутри .present-root размером со всё содержимое, и едет он вместе
 * с текстом сам, силами браузера. Первая версия держала холст размером с окно
 * и перерисовывала его на scroll – но браузер прокручивает страницу в своём
 * потоке и сообщает скрипту кадром позже, и рисунок заметно отставал от
 * текста, пока крутят колесо. Холст же во всю высоту длинной статьи упирается
 * в предел около 16 000 px; у SVG предела нет – контуры не хранят пикселей.
 *
 * Ластик – штрих в <mask>: всё нарисованное до него заворачивается в
 * <g mask>, нарисованное после лежит снаружи. Так «Отменить» снимает ластик
 * как обычный штрих, а по стёртому можно рисовать заново.
 *
 * Все имена с префиксом marker: состояние родителя Alpine ищет через общий
 * прокси, и поле `color` у компонента страницы молча перекрыло бы наше.
 *
 * ponytail: рисунок живёт до перезагрузки, на сервер и в localStorage не
 * уходит – так решено; сохранять, если попросят, – сериализовать `sheets`.
 */
const MARKER_COLORS = ['#ef4444', '#f97316', '#eab308', '#22c55e', '#3b82f6', '#a855f7', '#111827', '#ffffff'];
const MARKER_SIZES = [2, 4, 8, 14, 24];
const SVG_NS = 'http://www.w3.org/2000/svg';

function markerMode() {
    // Штрихи и узлы – в замыкании, не в состоянии Alpine: тысячи точек в
    // реактивном Proxy тормозят, а DOM-узел в нём перестаёт равняться себе
    // (та же грабля, что в present-mode.js про fullscreenElement).
    const sheets = {};          // ключ задачи/слайда -> массив штрихов
    let key = '';
    let stroke = null;          // штрих, который сейчас ведут
    let svg = null, root = null, offset = 0;
    const paths = new WeakMap(); // штрих -> его <path>, чтобы дописывать точки

    const strokes = () => (sheets[key] ||= []);
    const editable = (el) => el && (el.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName));
    const node = (tag, attrs) => {
        const n = document.createElementNS(SVG_NS, tag);
        for (const k in attrs) n.setAttribute(k, attrs[k]);
        return n;
    };
    // Точка без движения – тоже штрих: круглый конец рисует кружок.
    const pathD = (pts) => 'M' + pts.map(p => p[0] + ' ' + p[1]).join('L') + (pts.length === 1 ? 'l0.01 0' : '');

    // Точки храним от левого края .present-root, а слой растянут на всю
    // ширину окна: у страниц задач корень – центрированная колонка
    // max-w-7xl, и без этого поля слева и справа от неё были бы не для
    // рисования. Сдвиг колонки возвращает transform группы.
    function point(e) {
        const r = svg.getBoundingClientRect();
        return [Math.round(e.clientX - r.left - offset), Math.round(e.clientY - r.top)];
    }

    // Слой по размеру содержимого. У полноэкранного корня своя прокрутка, и
    // высота берётся из scrollHeight – но слой сам входит в него, поэтому
    // сначала сжимаем его в ноль, иначе он никогда не станет короче.
    function sync() {
        svg.style.width = svg.style.height = '0';
        const r = root.getBoundingClientRect();
        offset = Math.max(0, r.left);
        svg.style.left = -offset + 'px';
        svg.style.width = Math.max(root.scrollWidth + offset, document.documentElement.clientWidth) + 'px';
        svg.style.height = root.scrollHeight + 'px';
        if (svg.lastChild) svg.lastChild.setAttribute('transform', `translate(${offset} 0)`);
    }

    function render() {
        const defs = node('defs');
        let group = node('g');
        strokes().forEach((s, i) => {
            const p = node('path', { d: pathD(s.pts), 'stroke-width': s.size });
            paths.set(s, p);
            if (!s.erase) {
                p.setAttribute('stroke', s.color);
                group.append(p);
                return;
            }
            // Белое – видно, чёрное – стёрто. Прямоугольник с запасом во все
            // стороны: координаты маски живут в сдвинутой группе.
            const mask = node('mask', { id: 'marker-m' + i, maskUnits: 'userSpaceOnUse', x: -1e5, y: -1e5, width: 2e5, height: 2e5 });
            p.setAttribute('stroke', '#000');
            mask.append(node('rect', { x: -1e5, y: -1e5, width: 2e5, height: 2e5, fill: '#fff' }), p);
            defs.append(mask);
            const wrapped = node('g', { mask: `url(#marker-m${i})` });
            wrapped.append(group);
            group = node('g');
            group.append(wrapped);
        });
        group.setAttribute('transform', `translate(${offset} 0)`);
        svg.replaceChildren(defs, group);
    }

    return {
        markerOn: false,
        markerColor: MARKER_COLORS[0],
        markerSize: MARKER_SIZES[1],
        markerErase: false,
        markerColors: MARKER_COLORS,
        markerSizes: MARKER_SIZES,

        markerInit() {
            root = document.querySelector('.present-root');
            svg = root && root.querySelector('.marker-layer');
            if (!svg) return;
            sync();

            svg.addEventListener('pointerdown', (e) => {
                if (!this.markerOn || e.button > 0) return;
                svg.setPointerCapture(e.pointerId);
                // Ластик шире маркера: линия с круглыми концами шире своей
                // середины, и ластик той же толщины оставлял бы ореол.
                stroke = {
                    color: this.markerColor, erase: this.markerErase,
                    size: this.markerErase ? Math.max(20, this.markerSize * 3) : this.markerSize,
                    pts: [point(e)],
                };
                strokes().push(stroke);
                render();
            });
            svg.addEventListener('pointermove', (e) => {
                if (!stroke) return;
                // Быстрое движение браузер склеивает в одно событие – без
                // промежуточных точек окружность выходит многоугольником.
                const evs = e.getCoalescedEvents ? e.getCoalescedEvents() : [];
                for (const ev of (evs.length ? evs : [e])) stroke.pts.push(point(ev));
                paths.get(stroke).setAttribute('d', pathD(stroke.pts));
            });
            const end = () => { stroke = null; };
            svg.addEventListener('pointerup', end);
            svg.addEventListener('pointercancel', end);

            // Содержимое растёт без смены размера окна: открыли разбор,
            // догрузилась картинка, сменилась задача. Корень в полном экране
            // размером с окно и сам не растёт – следим и за его детьми.
            const ro = new ResizeObserver(() => sync());
            ro.observe(root);
            [...root.children].forEach(c => ro.observe(c));
            window.addEventListener('resize', sync);
            document.addEventListener('fullscreenchange', sync);

            document.addEventListener('keydown', (e) => {
                if (editable(e.target) || e.target.closest?.('.CodeMirror')) return;
                if (e.code === 'KeyM' && !e.ctrlKey && !e.metaKey && !e.altKey) {
                    e.preventDefault();
                    this.markerToggle();
                } else if (this.markerOn && (e.ctrlKey || e.metaKey) && e.code === 'KeyZ') {
                    e.preventDefault();
                    this.markerUndo();
                }
            });
        },

        markerToggle() {
            this.markerOn = !this.markerOn;
            stroke = null;
            if (svg) sync();
        },

        // Ключ собирает _present_mode.html: полный экран или нет + номер
        // задачи/слайда. Рисунок у доски и рисунок в обычной вёрстке – разные:
        // текст там лежит в других местах.
        markerKey(k) {
            key = String(k);
            stroke = null;
            if (svg) { sync(); render(); }
        },

        markerPick(color) { this.markerColor = color; this.markerErase = false; },
        markerUndo() { strokes().pop(); render(); },
        markerClear() { sheets[key] = []; if (svg) render(); },
    };
}
