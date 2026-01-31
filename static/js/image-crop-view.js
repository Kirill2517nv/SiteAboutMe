(() => {
    const toFloat = (value) => {
        const parsed = parseFloat(value);
        return Number.isFinite(parsed) ? parsed : 0;
    };

    const toInt = (value) => {
        const parsed = parseInt(value, 10);
        return Number.isFinite(parsed) ? parsed : 0;
    };

    const applyCrop = (blockEl) => {
        const cropWidth = toFloat(blockEl.dataset.blockImageCropWidth);
        const cropHeight = toFloat(blockEl.dataset.blockImageCropHeight);
        const cropX = toFloat(blockEl.dataset.blockImageCropX);
        const cropY = toFloat(blockEl.dataset.blockImageCropY);
        const naturalWidth = toInt(blockEl.dataset.blockImageNaturalWidth);
        const naturalHeight = toInt(blockEl.dataset.blockImageNaturalHeight);

        if (!cropWidth || !cropHeight || !naturalWidth || !naturalHeight) {
            return;
        }

        const container = blockEl.querySelector('.block-image-container, .home-card-image-container');
        const img = container ? container.querySelector('img') : null;
        if (!container || !img) {
            return;
        }

        const containerWidth = container.getBoundingClientRect().width;
        if (!containerWidth) {
            return;
        }

        let containerHeight = toInt(blockEl.dataset.blockImageHeight);
        if (!containerHeight) {
            containerHeight = Math.round(containerWidth * (cropHeight / cropWidth));
        }

        container.style.position = 'relative';
        container.style.overflow = 'hidden';
        container.style.height = `${containerHeight}px`;

        const scale = containerWidth / cropWidth;
        const imgWidth = naturalWidth * scale;
        const imgHeight = naturalHeight * scale;

        img.style.position = 'absolute';
        img.style.top = '0';
        img.style.left = '0';
        img.style.width = `${imgWidth}px`;
        img.style.height = `${imgHeight}px`;
        img.style.maxWidth = 'none';
        img.style.maxHeight = 'none';
        img.style.transform = `translate(${-cropX * scale}px, ${-cropY * scale}px)`;
    };

    const applyAll = () => {
        document.querySelectorAll('[data-block-id]').forEach((blockEl) => {
            applyCrop(blockEl);
            applyFreeLayout(blockEl);
        });
    };

    const applyFreeLayout = (blockEl) => {
        const rawTextPosX = blockEl.dataset.blockTextPosX;
        const rawTextPosY = blockEl.dataset.blockTextPosY;
        const rawImagePosX = blockEl.dataset.blockImagePosX;
        const rawImagePosY = blockEl.dataset.blockImagePosY;

        const hasTextPos = rawTextPosX !== undefined && rawTextPosX !== '' && rawTextPosY !== undefined && rawTextPosY !== '';
        const hasImagePos = rawImagePosX !== undefined && rawImagePosX !== '' && rawImagePosY !== undefined && rawImagePosY !== '';

        const textPosX = hasTextPos ? toFloat(rawTextPosX) : null;
        const textPosY = hasTextPos ? toFloat(rawTextPosY) : null;
        const imagePosX = hasImagePos ? toFloat(rawImagePosX) : null;
        const imagePosY = hasImagePos ? toFloat(rawImagePosY) : null;

        if (!hasTextPos && !hasImagePos) {
            return;
        }

        const wrapper = blockEl.querySelector('.block-content-wrapper');
        if (!wrapper) {
            return;
        }

        wrapper.className = 'block-content-wrapper layout-free';
        wrapper.style.position = 'relative';

        const textContainer = wrapper.querySelector('.block-text-container, .home-card-content');
        const imageContainer = wrapper.querySelector('.block-image-container, .home-card-image-container');

        if (textContainer && hasTextPos) {
            textContainer.style.position = 'absolute';
            textContainer.style.left = `${textPosX}px`;
            textContainer.style.top = `${textPosY}px`;
        }

        if (imageContainer && hasImagePos) {
            imageContainer.style.position = 'absolute';
            imageContainer.style.left = `${imagePosX}px`;
            imageContainer.style.top = `${imagePosY}px`;
        }

        const elements = [textContainer, imageContainer].filter(Boolean);
        if (!elements.length) {
            return;
        }

        let maxBottom = 0;
        elements.forEach((el) => {
            const rect = el.getBoundingClientRect();
            const wrapperRect = wrapper.getBoundingClientRect();
            const bottom = rect.bottom - wrapperRect.top;
            maxBottom = Math.max(maxBottom, bottom);
        });
        if (maxBottom) {
            wrapper.style.minHeight = `${Math.ceil(maxBottom)}px`;
        }
    };

    document.addEventListener('DOMContentLoaded', () => {
        applyAll();
        window.addEventListener('resize', applyAll);
    });
    window.addEventListener('load', applyAll);
})();
