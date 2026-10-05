// Язык решения в редакторе кода – общий кусок трёх страниц с CodeMirror
// (вариант ЕГЭ, сессия тренировки, квиз). По умолчанию везде Python.
// Режим C++ строится поверх mode/clike, его страница подключает рядом с python.
const CODE_LANG_MODES = { python: 'python', cpp: 'text/x-cpp-vs' };
const CODE_LANG_THEMES = { python: 'material-darker', cpp: 'vscode-dark' };

function codeLangMode(lang) {
    return CODE_LANG_MODES[lang] || 'python';
}

function codeLangTheme(lang) {
    return CODE_LANG_THEMES[lang] || 'material-darker';
}

// Переключить язык у живого редактора. Экземпляр CodeMirror лежит в данных
// Alpine, и через них приходит обёрнутым в Proxy: setOption, вызванный через
// обёртку, складывает во внутреннее состояние редактора проксированные
// объекты, после чего пропадает каретка и перестаёт работать выделение.
// Поэтому – только через Alpine.raw.
function codeLangApply(cm, lang) {
    if (!cm) return;
    cm = Alpine.raw(cm);
    cm.setOption('mode', codeLangMode(lang));
    cm.setOption('theme', codeLangTheme(lang));
    cm.focus();
}

// Выбор хранится рядом с ответами в localStorage: код экзамена уходит на
// проверку только при завершении, и после перезагрузки C++ иначе ушёл бы
// проверяться как Python.
function loadCodeLangs(key) {
    try { return JSON.parse(localStorage.getItem(key)) || {}; } catch (e) { return {}; }
}

function saveCodeLangs(key, langs) {
    try { localStorage.setItem(key, JSON.stringify(langs)); } catch (e) { /* приватное окно */ }
}

// C++ «как в Visual Studio». Штатный text/x-c++src красит всю строку
// `#include <iostream>` одним цветом, не знает типов STL и не отличает вызов
// функции от переменной. Доопределяем его тем же clike, не меняя редактор.
(function defineVsCpp() {
    if (!window.CodeMirror || !CodeMirror.mimeModes['text/x-c++src']) return;
    const base = CodeMirror.mimeModes['text/x-c++src'];
    const words = (s) => Object.fromEntries(s.split(' ').map((w) => [w, true]));
    // Классы и пространства имён – бирюзовые в VS. cin/cout там – переменные.
    const stl = words('std vector string map set multiset multimap unordered_map ' +
        'unordered_set pair deque queue stack priority_queue array bitset tuple list ' +
        'ifstream ofstream fstream istream ostream stringstream istringstream ' +
        'ostringstream function greater less optional');
    // Управление потоком – фиолетовое, остальные ключевые – синие.
    const control = words('if else for while do switch case default break continue ' +
        'return goto try catch throw co_return co_yield co_await');

    function includeTarget(stream, state) {
        state.tokenize = null;
        if (stream.match(/^<[^>]*>?/) || stream.match(/^"[^"]*"?/)) return 'string';
        return null;
    }

    function preprocessor(stream, state) {
        if (!state.startOfLine) return false;
        stream.eatSpace();
        const directive = stream.match(/^\w+/);
        if (directive && directive[0] === 'include') {
            state.tokenize = includeTarget;  // пробел перед <...> clike съест сам
        }
        return 'meta';
    }

    CodeMirror.defineMIME('text/x-cpp-vs', Object.assign({}, base, {
        builtin: stl,
        hooks: Object.assign({}, base.hooks, {
            '#': preprocessor,
            token(stream, state, style) {
                const own = base.hooks.token(stream, state, style);
                if (own !== undefined) return own;
                if (style === 'keyword' && control[stream.current()]) return 'keyword control';
                // ponytail: вызов – это имя перед «(», кроме объявлений с
                // конструктором: `int a(5)` (после типа) и `vector<int> a(5)`
                // (после «>» шаблона). Точнее различает только парсер.
                if (style === 'variable' && state.prevToken !== 'type'
                        && !/>\s*$/.test(stream.string.slice(0, stream.start))
                        && stream.match(/^\s*\(/, false)) {
                    return 'function';
                }
            },
        }),
    }));
})();
