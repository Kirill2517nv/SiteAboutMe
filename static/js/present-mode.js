/**
 * Режим проектора: страница уходит в нативный полный экран, обвязка прячется,
 * а масштаб задаётся корневым font-size. Вся вёрстка проекта на Tailwind, то
 * есть в rem, поэтому вместе с текстом растут отступы, кнопки и поля ввода, а
 * строки переливаются под новую ширину – длинное условие становится выше, но не
 * уезжает за край экрана.
 *
 * Через CSS zoom так делать нельзя: CodeMirror меряет ширину символа сам и под
 * zoom смешивает масштабированные rect'ы с немасштабированными offset'ами –
 * шрифт кода остаётся мелким, а каретка уезжает от буквы.
 *
 * Подключение (см. templates/_present_mode.html):
 *   <div class="present-root ..." x-data="presentMode()">
 *       {% include '_present_mode.html' %}   – стили, панель управления, этот файл
 *       ... {% include '_present_button.html' %} – кнопка «На экран» в шапке
 *       <div class="present-hide">...</div>  – всё, чего на проекторе быть не должно
 */
function presentMode() {
    return {
        presenting: false,   // страница отдана проектору
        zoom: 1.6,           // масштаб: доля от кегля, выбранного в браузере

        // Корень ищем по классу, а не через $root: кнопки живут во вложенном
        // компоненте страницы, и $root там указывает уже на него – полный экран
        // уходил бы не на тот элемент. Хранить ссылку в состоянии тоже нельзя:
        // Alpine оборачивает данные в Proxy, и сравнение с document.fullscreenElement
        // перестало бы совпадать.
        _root() {
            return document.querySelector('.present-root');
        },

        init() {
            // Масштаб подбирают под конкретный проектор один раз – в кабинете он
            // не меняется, поэтому храним в браузере, а не в настройках страницы.
            // Ключ общий на все страницы: проектор-то один.
            this.zoom = parseFloat(localStorage.getItem('egePresentZoom')) || 1.6;
            // Выйти можно и по Esc мимо нашей кнопки – состояние берём у браузера.
            document.addEventListener('fullscreenchange', () => {
                this.presenting = document.fullscreenElement === this._root();
                this._applyZoom();
            });
        },

        togglePresent() {
            if (document.fullscreenElement) document.exitFullscreen();
            else this._root().requestFullscreen().catch(() => {});
        },

        setZoom(z) {
            this.zoom = Math.min(3, Math.max(1, Math.round(z * 10) / 10));
            localStorage.setItem('egePresentZoom', this.zoom);
            this._applyZoom();
        },

        // Проценты, а не пиксели: 160% – это в полтора раза больше того кегля,
        // который выбрал сам пользователь в браузере, а не «16px × 1.6».
        _applyZoom() {
            document.documentElement.style.fontSize = this.presenting ? (this.zoom * 100) + '%' : '';
            // Картинка условия – единственное, что живёт в своих пикселях и на
            // rem не реагирует; её масштабирует CSS по этой переменной.
            this._root().style.setProperty('--present-zoom', this.presenting ? this.zoom : 1);
            this._resetEditorMetrics();
        },

        /**
         * Каретка редактора кода после смены кегля.
         *
         * CodeMirror рисует каретку сам, по своим замерам строки, и о смене
         * шрифта не узнаёт: после выхода из полного экрана она остаётся
         * проекторного размера и не на своём месте – до первой набранной буквы.
         * Перемерить его штатно нельзя: refresh(), setOption и пересоздание
         * инстанса в этот момент рушат редактор наглухо – он молча перестаёт
         * принимать ввод (клик отдаёт фокус textarea, а буквы в документ уже не
         * попадают). Всё это проверено в браузере, каждый вариант отдельно.
         *
         * Единственная безопасная перерисовка – правка документа, и только
         * внутри жеста пользователя: та же правка по таймеру или в кадре ломает
         * редактор так же, как refresh. Поэтому здесь два шага: снимаем фокус –
         * и каретка не показывается вовсе, пока замеры устарели, – и чиним
         * геометрию первым же кликом в редактор, тем самым, которым учитель
         * возвращается к коду.
         */
        _resetEditorMetrics() {
            // Редактор ищем в DOM, а не в состоянии страницы: у вариантов,
            // практикума и тренировки оно устроено по-разному, а видимый
            // CodeMirror на всех трёх один и тот же.
            const el = [...this._root().querySelectorAll('.CodeMirror')].find(e => e.offsetParent !== null);
            const cm = el && el.CodeMirror;
            if (!cm) return;
            cm.getInputField().blur();
            el.addEventListener('mousedown', () => {
                const pos = cm.getCursor(), n = pos.line, str = cm.getLine(n);
                // Строка заменяется сама на себя: текст тот же, но CM
                // перерисовывает её и заново меряет, а с ней и каретку.
                cm.replaceRange(str, { line: n, ch: 0 }, { line: n, ch: str.length }, '+zoom');
                cm.setCursor(pos);
            }, { once: true });
        },
    };
}
