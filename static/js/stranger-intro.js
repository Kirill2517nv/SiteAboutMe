// Пасхалка «Очень странные задачи» (stranger, accounts/easter_eggs.py).
// Партиал – templates/quizzes/_stranger_intro.html, контекст – classwork.stranger_context.
//
// Обычный скрипт без Alpine: сцена целиком на Web Animations API, состояние
// живёт в замыкании и после заставки исчезает вместе с ним. Ключ localStorage
// – «вид:id работы»: одну и ту же работу второй раз заставка не встречает.
// Суперпользователь смотрит её только по явной просьбе (?intro=1) и тогда
// ключ не трогает – иначе своя проверка съела бы показ ученику на этой машине.

(function () {
    'use strict';

    // Вся сцена ~15 с: буквы съезжаются медленно, как в титрах сериала, –
    // на короткой анимации эффект не успевал проявиться.
    var TITLE_MS = 8000;         // полёт одной буквы
    var LETTER_STAGGER = 1500;   // буквы стартуют вразнобой в этом окне
    var TITLE_FADE_AT = 10500;   // надпись постояла – слой начинает гаснуть
    var TITLE_FADE_MS = 1500;
    var SCENE_TWO_AT = 11500;    // квадраты задач выезжают, пока слой гаснет
    var TILE_MS = 2800;

    function randomSpread(spread) {
        return (Math.random() * 2 - 1) * spread;
    }

    // Каждая буква – отдельный span: двигаться они должны порознь. Буквы одного
    // слова сидят в неразрывной обёртке, а между словами – обычный пробел:
    // иначе на узком экране строка рвалась посреди слова («СТРАННЫ / Е»), а так
    // переносится целым словом.
    function splitLetters(root) {
        var letters = [];
        root.querySelectorAll('[data-stranger-text]').forEach(function (line) {
            var words = line.textContent.trim().split(/\s+/);
            line.textContent = '';
            words.forEach(function (word, i) {
                if (i) line.appendChild(document.createTextNode(' '));
                var wrap = document.createElement('span');
                wrap.className = 'stranger-word';
                Array.from(word).forEach(function (ch) {
                    var span = document.createElement('span');
                    span.className = 'stranger-letter';
                    span.textContent = ch;
                    wrap.appendChild(span);
                    letters.push(span);
                });
                line.appendChild(wrap);
            });
        });
        return letters;
    }

    // Откуда букве лететь, как в титрах сериала: из-за края экрана с той
    // стороны, где она стоит в надписи (левая – слева, верхняя – сверху),
    // огромной, почти у камеры. Направление – от центра экрана к месту буквы,
    // с небольшим разбросом угла, чтобы соседки не шли строем.
    function startFrame(el) {
        var r = el.getBoundingClientRect();
        var w = window.innerWidth, h = window.innerHeight;
        var dx = r.left + r.width / 2 - w / 2;
        var dy = r.top + r.height / 2 - h / 2;
        var angle = (dx || dy) ? Math.atan2(dy, dx) : Math.random() * 2 * Math.PI;
        angle += randomSpread(0.5);
        var dist = Math.max(w, h) * (0.6 + Math.random() * 0.3);
        var scale = 5 + Math.random() * 3;
        return 'translate(' + Math.round(Math.cos(angle) * dist) + 'px, '
            + Math.round(Math.sin(angle) * dist) + 'px) scale(' + scale.toFixed(2) + ')';
    }

    function play() {
        var layer = document.getElementById('stranger-intro');
        if (!layer) return;
        if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

        var key = layer.dataset.key || '';
        var debug = layer.dataset.debug === '1';

        if (debug) {
            // ?intro=1 – и ключ не читаем, и не пишем.
            if (!new URLSearchParams(window.location.search).has('intro')) return;
        } else {
            var storeKey = 'stranger-intro:' + key;
            var seen = false;
            try { seen = window.localStorage.getItem(storeKey) === '1'; } catch (e) { seen = false; }
            if (seen) return;
            try { window.localStorage.setItem(storeKey, '1'); } catch (e) { /* играем без памяти */ }
        }

        var animations = [];
        var letters = splitLetters(layer);
        layer.style.display = 'flex';

        // Места букв меряем до первого кадра: слой уже виден, трансформаций ещё нет.
        var starts = letters.map(startFrame);
        letters.forEach(function (el, i) {
            animations.push(el.animate([
                // Только transform и opacity: их двигает видеокарта готовой
                // картинкой. filter: blur на букве с обводкой и тройным
                // свечением, увеличенной в 5–8 раз, браузер перерисовывал
                // каждый кадр – заставка шла рывками.
                { transform: starts[i], opacity: 0 },
                // Буква проявляется быстро и дальше видна всю дорогу – в
                // оригинале она огромная и обрезана краем кадра, а не прозрачная.
                { offset: 0.12, opacity: 1 },
                { transform: 'none', opacity: 1 },
            ], {
                duration: TITLE_MS,
                delay: Math.random() * LETTER_STAGGER,
                easing: 'cubic-bezier(.2,.7,.2,1)',
                fill: 'both',
            }));
        });

        // Слой гаснет, пока квадраты ещё летят: между сценами нет чёрной паузы.
        animations.push(layer.animate(
            [{ opacity: 1 }, { opacity: 0 }],
            { duration: TITLE_FADE_MS, delay: TITLE_FADE_AT, easing: 'ease-out', fill: 'both' }
        ));

        var tiles = Array.from(document.querySelectorAll('[data-stranger-tile]'))
            .filter(function (el) { return el.offsetParent !== null; });
        var step = tiles.length ? Math.min(60, 600 / tiles.length) : 0;

        tiles.forEach(function (el, i) {
            animations.push(el.animate([
                {
                    transform: 'translate(' + randomSpread(30) + 'vw, ' + randomSpread(25) + 'vh) scale(3)',
                    opacity: 0,
                    boxShadow: '0 0 18px 4px rgba(229,9,20,.9)',
                    outline: '2px solid #e50914',
                },
                {
                    offset: .75,
                    transform: 'none',
                    opacity: 1,
                    boxShadow: '0 0 18px 4px rgba(229,9,20,.9)',
                    outline: '2px solid #e50914',
                },
                {
                    transform: 'none',
                    opacity: 1,
                    boxShadow: 'none',
                    outline: '2px solid transparent',
                },
            ], {
                duration: TILE_MS,
                delay: SCENE_TWO_AT + step * i,
                easing: 'cubic-bezier(.2,.7,.2,1)',
                // backwards, а не both: после сцены квадрат возвращается к своим
                // цветам «решена / ошибка», которые ставит приложение.
                fill: 'backwards',
            }));
        });

        var active = true;

        function stop() {
            if (!active) return;
            active = false;
            animations.forEach(function (animation) {
                try { animation.finish(); } catch (e) { /* уже закончилась */ }
            });
            layer.style.display = 'none';
            document.removeEventListener('pointerdown', skip, true);
            document.removeEventListener('keydown', skipKey, true);
        }

        function skip() {
            stop();
        }

        function skipKey(event) {
            // Пока идёт заставка, клавиша означает «пропустить», а не ввод ответа.
            event.preventDefault();
            stop();
        }

        document.addEventListener('pointerdown', skip, { capture: true, once: false });
        document.addEventListener('keydown', skipKey, { capture: true, once: false });
        window.setTimeout(stop, SCENE_TWO_AT + TILE_MS + step * Math.max(tiles.length - 1, 0) + 100);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', play);
    } else {
        play();
    }
})();
