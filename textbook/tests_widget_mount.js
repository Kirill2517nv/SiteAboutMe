// Монтирование виджетов учебника вне браузера.
//
// Зачем: `node --check` проверяет синтаксис и молчит про то, что виджет
// падает при первом же рендере – ReferenceError на снесённой константе,
// опечатка в имени функции, обращение к полю конфига, которого нет. В браузере
// это выглядит как пустая рамка с заголовком: TextbookWidgets.init() ловит
// исключение фабрики и пишет в console.error, а страница остаётся целой.
// Именно так дважды уезжала в статью нерабочая таблица.
//
// Запускается из WidgetMountTests (textbook/tests.py), конфиги получает первым
// аргументом – JSON вида {"<widget_key>": <widget_config>, …}, собранный
// seed-командой, то есть ровно то, что окажется в базе.
//
// Ключ можно уточнить суффиксом после «#» («fano-code#minimal»): до решётки –
// data-widget, после – только имя в отчёте. Так один виджет проверяется на
// двух конфигах сразу, например полный и урезанный.
//
// Для каждого смонтированного виджета печатается строка «text <имя> <всё, что
// он написал>»: по ней тест проверяет не только что виджет нарисовал что-то,
// но и что урезанный вид не нарисовал лишнего.
//
// DOM здесь заглушечный: виджеты строят разметку через createElement /
// appendChild / addEventListener, и этого набора им хватает. Настоящий браузер
// заменять не пытаемся – проверяем, что фабрика доработала до конца и что-то
// нарисовала.
const fs = require('fs');

function makeElement(tag) {
    return {
        tagName: tag,
        dataset: {},
        style: {},
        children: [],
        className: '',
        title: '',
        type: '',
        value: '',
        hidden: false,
        disabled: false,
        spellcheck: false,
        textContent: '',
        innerHTML: '',
        appendChild(child) { this.children.push(child); return child; },
        removeChild(child) {
            this.children = this.children.filter(function (c) { return c !== child; });
            return child;
        },
        addEventListener() {},
        removeEventListener() {},
        setAttribute() {},
        getAttribute() { return null; },
        querySelectorAll() { return []; },
        querySelector() { return null; },
        focus() {},
        blur() {},
    };
}

const documentStub = {
    createElement: makeElement,
    createElementNS(ns, tag) { return makeElement(tag); },
    addEventListener() {},          // DOMContentLoaded: монтируем сами, ниже
    querySelectorAll() { return []; },
};

const errors = [];
const consoleStub = {
    log() {},
    warn(...args) { errors.push('warn: ' + args.join(' ')); },
    error(...args) { errors.push('error: ' + args.join(' ')); },
};

const windowStub = {};
const source = fs.readFileSync('static/js/textbook-widgets.js', 'utf8');
new Function('window', 'document', 'console', source)(windowStub, documentStub, consoleStub);

if (!windowStub.TextbookWidgets) {
    console.log('FAIL виджеты не зарегистрировались: window.TextbookWidgets пуст');
    process.exit(1);
}

// Весь текст, который виджет написал: заглушечный элемент хранит его в
// textContent и innerHTML, детей обходим сами.
function collectText(node) {
    const own = [node.textContent, node.innerHTML].filter(Boolean).join(' ');
    return [own].concat((node.children || []).map(collectText))
        .filter(Boolean).join(' ');
}

// Первый <svg> виджета и заданные ему размеры. По ним тест проверяет, что
// картинка живёт в rem: показ с проектора масштабирует страницу корневым
// кеглем, и SVG в пикселях остался бы на стене прежним.
function findSvg(node) {
    if (node.tagName === 'svg') return node;
    for (const kid of node.children || []) {
        const found = findSvg(kid);
        if (found) return found;
    }
    return null;
}

const configs = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
let fails = 0;

Object.keys(configs).forEach(function (name) {
    const el = makeElement('div');
    el.dataset.widget = name.split('#')[0];
    el.dataset.title = 'Проверка';
    el.dataset.config = JSON.stringify(configs[name]);

    errors.length = 0;
    windowStub.TextbookWidgets.init({ querySelectorAll() { return [el]; } });

    if (errors.length) {
        fails++;
        console.log('FAIL ' + name + ': ' + errors.join(' | '));
        return;
    }
    if (el.dataset.mounted !== '1') {
        fails++;
        console.log('FAIL ' + name + ': не смонтировался');
        return;
    }
    if (!el.children.length) {
        fails++;
        console.log('FAIL ' + name + ': ничего не нарисовал');
        return;
    }
    console.log('ok   ' + name + ' смонтировался');
    console.log('text ' + name + ' ' + collectText(el).replace(/\s+/g, ' '));

    const svg = findSvg(el);
    if (svg) {
        console.log('svg  ' + name + ' ' +
            (svg.style.width || '-') + ' ' + (svg.style.height || '-'));
    }
});

console.log(fails ? '\nПРОВАЛОВ: ' + fails : '\nвсё смонтировалось');
process.exit(fails ? 1 : 0);
