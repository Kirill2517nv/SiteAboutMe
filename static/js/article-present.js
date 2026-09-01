/**
 * Показ статьи учебника с проектора.
 *
 * Надстройка над общим presentMode() (static/js/present-mode.js): тот даёт
 * полный экран и масштаб, здесь добавляется листание блоков статьи. Слайд –
 * это уже существующий <article> блока урока (см. article_detail.html), новых
 * сущностей в базе нет: статья и презентация – один и тот же материал, и
 * расходиться им негде.
 *
 * Листание включается только в полном экране. Вне его страница остаётся
 * обычной статьёй, которую ученик читает дома скроллом.
 */
function articlePresent() {
    const base = presentMode();

    // Узлы слайдов держим в замыкании, а не в состоянии Alpine: Alpine
    // оборачивает данные в Proxy, и DOM-элемент внутри него перестаёт быть
    // равным самому себе (та же грабля описана в present-mode.js про
    // fullscreenElement). В состояние кладём только простые значения.
    let slideEls = [];

    return {
        ...base,
        slide: 0,
        slideList: [],   // индексы слайдов: панели нужен только счётчик «3 / 15»

        init() {
            base.init.call(this);
            slideEls = [...document.querySelectorAll('[data-slide]')];
            this.slideList = slideEls.map((_, i) => i);
            // Вход и выход из полного экрана – единственное, что включает и
            // выключает режим слайдов. Начинаем всегда с первого блока.
            this.$watch('presenting', () => this.goSlide(0));
            document.addEventListener('keydown', (e) => this._onKey(e));
        },

        goSlide(i) {
            this.slide = Math.min(slideEls.length - 1, Math.max(0, i));
            slideEls.forEach((el, n) => {
                el.hidden = this.presenting && n !== this.slide;
            });
            // Скроллится сам корень: у .present-root:fullscreen свой overflow-y,
            // а окно в полном экране не прокручивается вовсе.
            if (this.presenting) this._root().scrollTop = 0;
        },

        /**
         * Клавиши у доски. Пульт-презентер шлёт не стрелки, а PageUp/PageDown
         * (реже – пробел), поэтому ловим все три пары: иначе учитель привязан
         * к клавиатуре ноутбука.
         */
        _onKey(e) {
            if (!this.presenting || e.ctrlKey || e.altKey || e.metaKey) return;
            // В поле масштаба и внутри виджетов стрелки принадлежат им.
            const t = e.target;
            if (t.isContentEditable || (t.matches && t.matches('input, textarea, select'))) return;

            if (['ArrowRight', 'ArrowDown', 'PageDown', ' '].includes(e.key)) {
                e.preventDefault();
                this.goSlide(this.slide + 1);
            } else if (['ArrowLeft', 'ArrowUp', 'PageUp'].includes(e.key)) {
                e.preventDefault();
                this.goSlide(this.slide - 1);
            } else if (e.key === 'Home') {
                e.preventDefault();
                this.goSlide(0);
            } else if (e.key === 'End') {
                e.preventDefault();
                this.goSlide(slideEls.length - 1);
            }
        },
    };
}
