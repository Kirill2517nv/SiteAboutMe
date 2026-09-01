// Прогон парсера виджета truth-table вне браузера.
//
// Виджет обещает питоновский синтаксис и питоновский приоритет операций, а
// значит обязан считать ровно то же, что посчитает интерпретатор. Поэтому
// эталоны не выдуманы: TruthTableParserTests (textbook/tests.py) прогоняет
// список выражений через настоящий eval() и передаёт результат первым
// аргументом – JSON вида [{"src": "...", "rows": [[0,0,1], …]}, …]. Первое
// выражение в списке – функция задания 2, и её таблицу Python дополнительно
// сверяет с seed_ege_theory_2._rows(), той самой, что записана в статью.
//
// Самодостаточный кусок виджета (SYMBOLS…tableFor) вырезается по границам –
// DOM ему не нужен, а грузить весь файл в node нечем.
const fs = require('fs');
const src = fs.readFileSync('static/js/textbook-widgets.js', 'utf8');
const from = src.indexOf('        const SYMBOLS = [');
const to = src.indexOf('        // ── Данные ─');
if (from < 0 || to < 0) throw new Error('не нашёл границы куска парсера');
const chunk = src.slice(from, to);

const mod = new Function(chunk + '\nreturn { parse: parse, tableFor: tableFor };')();

function table(expr) {
    return mod.tableFor(mod.parse(expr));
}

let fails = 0;
function eq(got, want, label) {
    const a = JSON.stringify(got), b = JSON.stringify(want);
    if (a !== b) { fails++; console.log('FAIL ' + label + '\n  got  ' + a + '\n  want ' + b); }
    else console.log('ok   ' + label);
}

// 1. Главное: то же, что настоящий Python, на каждом выражении из списка.
JSON.parse(fs.readFileSync(process.argv[2], 'utf8')).forEach(function (item) {
    eq(table(item.src), item.rows, 'как Python: ' + item.src);
});

// 2. Порядок наборов: старший разряд – первая переменная, по возрастанию.
eq(table('x or y').map(function (r) { return r.slice(0, 2); }),
    [[0, 0], [0, 1], [1, 0], [1, 1]], 'порядок наборов');

// 3. Ошибки не роняют виджет, а называются – и называют питоновскую замену.
[
    ['x and', 'обрыв'],
    ['(x or y', 'скобка'],
    ['foo or x', 'длинное имя'],
    ['True or False', 'нет переменных'],
    ['a and b and c and d and e and f', 'слишком много переменных'],
    ['x & y', 'и-символ'],
    ['x | y', 'или-символ'],
    ['!x', 'восклицательный знак'],
    ['x -> y', 'стрелка'],
    ['x ∨ y', 'юникод'],
    ['x == not y', 'not без скобок'],
    ['true or x', 'true с маленькой'],
].forEach(function (t) {
    try { table(t[0]); fails++; console.log('FAIL не заметил ошибку: ' + t[0]); }
    catch (e) { console.log('ok   ошибка «' + t[1] + '»: ' + e.message); }
});

console.log(fails ? '\nПРОВАЛОВ: ' + fails : '\nвсё сошлось');
process.exit(fails ? 1 : 0);
