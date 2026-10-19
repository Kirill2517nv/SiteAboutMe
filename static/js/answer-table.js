// Поле ответа задачи ЕГЭ: одно поле или таблица, как в бланке КИМ.
// Форму (строк × столбцов) считает сервер по эталону (ege_scoring.answer_shape),
// чисел эталона в браузере нет. Значение наружу – одна строка: строки таблицы
// через перевод строки, ячейки через пробел. Её же понимает check_answer, и в
// том же виде ответ лежит в PracticeItem.text_answer / UserAnswer.text_answer.
// Компонент вешается с x-modelable="answerValue" и x-model на ответ страницы.
function answerTable(shape) {
    return {
        answerShape: shape,
        answerValue: '',
        answerCells: [],

        init() {
            if (!this.answerShape) return;
            this._answerSplit(this.answerValue);
            // Снаружи значение меняется при восстановлении черновика и при
            // «Показать ответ» – раскладываем по ячейкам, если это не наше же эхо.
            this.$watch('answerValue', (v) => {
                if (v !== this._answerJoin()) this._answerSplit(v);
            });
        },

        _answerSplit(value) {
            const [rows, cols] = this.answerShape;
            const lines = String(value || '').split('\n');
            this.answerCells = Array.from({ length: rows }, (_, r) => {
                const parts = (lines[r] || '').trim().split(/\s+/).filter(Boolean);
                return Array.from({ length: cols }, (_, c) => parts[c] || '');
            });
        },

        // ponytail: пустая первая ячейка при заполненной второй сдвигает число
        // влево («_ 36» читается как «36»). Для частичного балла 26/27 это 0
        // вместо 1; заводить маркер пустой ячейки – если ученики на это наткнутся.
        _answerJoin() {
            const lines = this.answerCells.map((row) => row.map((c) => c.trim()).join(' ').trim());
            while (lines.length && !lines[lines.length - 1]) lines.pop();
            return lines.join('\n');
        },

        answerSync() {
            this.answerValue = this._answerJoin();
        },

        answerClear() {
            this._answerSplit('');
            this.answerSync();
        },

        // Вставка вывода программы целиком: строки идут по строкам таблицы,
        // числа (через пробел или табуляцию) – по ячейкам, начиная с той, куда
        // вставили. Одно значение браузер вставит сам.
        answerPaste(event, r, c) {
            const text = (event.clipboardData || window.clipboardData).getData('text');
            if (!/[\s]/.test(text.trim())) return;
            event.preventDefault();
            const [rows, cols] = this.answerShape;
            text.trim().split(/\r?\n/).forEach((line, i) => {
                if (r + i >= rows) return;
                line.trim().split(/\s+/).forEach((part, j) => {
                    if (c + j < cols) this.answerCells[r + i][c + j] = part;
                });
            });
            this.answerSync();
        },
    };
}
