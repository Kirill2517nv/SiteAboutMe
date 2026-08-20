/**
 * Выбор фрагмента фото под круглый аватар.
 *
 * Кроп целиком на клиенте: пользователь двигает фото и меняет масштаб, а по
 * кнопке результат перерисовывается в <canvas> и подставляется обратно в тот же
 * <input type="file">. Сервер получает обычную загрузку квадратной картинки и
 * про кроп ничего не знает — Python-код трогать не пришлось.
 */
(function () {
    const input = document.getElementById('avatar-input');
    const modal = document.getElementById('avatar-crop');
    if (!input || !modal) return;

    const stage = document.getElementById('avatar-crop-stage');
    const img = document.getElementById('avatar-crop-img');
    const zoom = document.getElementById('avatar-crop-zoom');

    const BOX = 256;   // диаметр круга в модалке, px
    const OUT = 512;   // сторона итогового квадрата, px

    let base = 1;      // масштаб «вписать по короткой стороне» (как object-fit: cover)
    let dx = 0, dy = 0;

    function size() {
        const scale = base * parseFloat(zoom.value);
        return { w: img.naturalWidth * scale, h: img.naturalHeight * scale };
    }

    /** Смещение левого-верхнего угла фото относительно круга. */
    function offset(w, h) {
        return { x: (BOX - w) / 2 + dx, y: (BOX - h) / 2 + dy };
    }

    function draw() {
        const { w, h } = size();
        // Не даём утащить фото так, чтобы в круге появилась пустота
        const limX = (w - BOX) / 2, limY = (h - BOX) / 2;
        dx = Math.max(-limX, Math.min(limX, dx));
        dy = Math.max(-limY, Math.min(limY, dy));

        const { x, y } = offset(w, h);
        img.style.width = w + 'px';
        img.style.height = h + 'px';
        img.style.left = x + 'px';
        img.style.top = y + 'px';
    }

    function close() {
        modal.classList.add('hidden');
        modal.classList.remove('flex');
        if (img.src.startsWith('blob:')) URL.revokeObjectURL(img.src);
        input.value = '';   // иначе повторный выбор того же файла не даст change
    }

    input.addEventListener('change', function () {
        const file = input.files[0];
        if (!file) return;
        img.onload = function () {
            base = Math.max(BOX / img.naturalWidth, BOX / img.naturalHeight);
            zoom.value = 1;
            dx = dy = 0;
            draw();
            modal.classList.remove('hidden');
            modal.classList.add('flex');
        };
        img.src = URL.createObjectURL(file);
    });

    zoom.addEventListener('input', draw);

    // ponytail: перетаскивание одним пальцем/мышью, зум — ползунком.
    // Щипок двумя пальцами добавить, если попросят.
    let last = null;
    stage.addEventListener('pointerdown', function (event) {
        last = { x: event.clientX, y: event.clientY };
        stage.setPointerCapture(event.pointerId);
    });
    stage.addEventListener('pointermove', function (event) {
        if (!last) return;
        dx += event.clientX - last.x;
        dy += event.clientY - last.y;
        last = { x: event.clientX, y: event.clientY };
        draw();
    });
    stage.addEventListener('pointerup', function () { last = null; });
    stage.addEventListener('pointercancel', function () { last = null; });

    document.getElementById('avatar-crop-cancel').addEventListener('click', close);
    modal.addEventListener('click', function (event) {
        if (event.target === modal) close();
    });

    document.getElementById('avatar-crop-save').addEventListener('click', function () {
        const { w, h } = size();
        const { x, y } = offset(w, h);
        const k = OUT / BOX;   // модалка показывает 256px, отдаём 512px

        const canvas = document.createElement('canvas');
        canvas.width = canvas.height = OUT;
        canvas.getContext('2d').drawImage(img, x * k, y * k, w * k, h * k);

        canvas.toBlob(function (blob) {
            // Подменяем содержимое того же поля: DataTransfer — единственный
            // способ программно положить файл в <input type="file">
            const data = new DataTransfer();
            data.items.add(new File([blob], 'avatar.jpg', { type: 'image/jpeg' }));
            input.files = data.files;
            input.form.submit();
        }, 'image/jpeg', 0.9);
    });
})();
