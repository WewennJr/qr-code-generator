const I18N = JSON.parse(document.getElementById('i18n-data').textContent || '{}');

/* ---------------- Theme toggle ---------------- */
const themeToggle = document.getElementById('theme-toggle');

function syncThemeIcon() {
    themeToggle.classList.toggle('is-dark', document.documentElement.dataset.theme === 'dark');
}

themeToggle.addEventListener('click', () => {
    const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem('qr-theme', next); } catch (e) { /* private mode */ }
    syncThemeIcon();
});
syncThemeIcon();

/* ---------------- Gradient mode ---------------- */
function toggleGradientMode() {
    const useGradient = document.getElementById('use_gradient').checked;
    document.getElementById('solid-colors').classList.toggle('hidden', useGradient);
    document.getElementById('gradient-colors').classList.toggle('hidden', !useGradient);
}

function updateGradientStops() {
    const container = document.getElementById('gradient-stops');
    const stops = container.querySelectorAll('.gradient-stop');

    stops.forEach((stop, index) => {
        stop.dataset.index = index;
        stop.querySelector('label').textContent = `${I18N.colorStop} ${index + 1}`;

        const colorInput = stop.querySelector('input[type="color"]');
        colorInput.name = `gradient_color_${index}`;

        const removeBtn = stop.querySelector('.remove-stop');
        removeBtn.disabled = stops.length <= 2;
        removeBtn.style.opacity = stops.length <= 2 ? '0.3' : '1';
        removeBtn.style.cursor = stops.length <= 2 ? 'not-allowed' : 'pointer';
    });
}

function addGradientStop() {
    const container = document.getElementById('gradient-stops');
    const stops = container.querySelectorAll('.gradient-stop');

    if (stops.length >= 5) return;

    const lastStop = stops[stops.length - 1];
    const lastColor = lastStop.querySelector('input[type="color"]').value;

    const newStop = document.createElement('div');
    newStop.className = 'gradient-stop';
    newStop.draggable = true;
    newStop.innerHTML = `
        <span class="drag-handle">⋮⋮</span>
        <div class="stop-content">
            <label>${I18N.colorStop} ${stops.length + 1}</label>
            <div class="color-input-wrapper">
                <input type="color" name="gradient_color_${stops.length}" value="${lastColor}">
                <input type="text" class="color-hex" value="${lastColor}" readonly>
            </div>
            <button type="button" class="btn btn-icon remove-stop">−</button>
        </div>
    `;

    container.appendChild(newStop);
    setupDragAndDrop(newStop);
    setupColorSync(newStop.querySelector('input[type="color"]'));
    updateGradientStops();
    schedulePreview();
}

function removeGradientStop(button) {
    const container = document.getElementById('gradient-stops');
    const stops = container.querySelectorAll('.gradient-stop');

    if (stops.length <= 2) return;

    button.closest('.gradient-stop').remove();
    updateGradientStops();
    schedulePreview();
}

function setupColorSync(colorInput) {
    colorInput.addEventListener('input', function() {
        this.parentElement.querySelector('.color-hex').value = this.value;
        schedulePreview();
    });
}

/* ---------------- Drag & drop reorder ---------------- */
let draggedElement = null;

function setupDragAndDrop(element) {
    element.addEventListener('dragstart', handleDragStart);
    element.addEventListener('dragend', handleDragEnd);
    element.addEventListener('dragover', handleDragOver);
    element.addEventListener('drop', handleDrop);
}

function handleDragStart(e) {
    draggedElement = this;
    this.classList.add('dragging');
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', this.dataset.index);
}

function handleDragEnd() {
    this.classList.remove('dragging');
    document.querySelectorAll('.gradient-stop').forEach(stop => {
        stop.classList.remove('drag-over');
    });
    draggedElement = null;
}

function handleDragOver(e) {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';

    const container = document.getElementById('gradient-stops');
    const stops = container.querySelectorAll('.gradient-stop:not(.dragging)');

    stops.forEach(stop => stop.classList.remove('drag-over'));

    const afterElement = getDragAfterElement(container, e.clientY);
    if (afterElement) {
        afterElement.classList.add('drag-over');
    }
}

function handleDrop(e) {
    e.preventDefault();

    if (!draggedElement) return;

    const container = document.getElementById('gradient-stops');
    const afterElement = getDragAfterElement(container, e.clientY);

    if (afterElement) {
        container.insertBefore(draggedElement, afterElement);
    } else {
        container.appendChild(draggedElement);
    }

    updateGradientStops();
    schedulePreview();
}

function getDragAfterElement(container, y) {
    const draggableElements = [...container.querySelectorAll('.gradient-stop:not(.dragging)')];

    return draggableElements.reduce((closest, child) => {
        const box = child.getBoundingClientRect();
        const offset = y - box.top - box.height / 2;

        if (offset < 0 && offset > closest.offset) {
            return { offset: offset, element: child };
        } else {
            return closest;
        }
    }, { offset: Number.NEGATIVE_INFINITY }).element;
}

/* ---------------- Palette presets ---------------- */
function setSolidColor(inputId, value) {
    const input = document.getElementById(inputId);
    if (!input) return;
    input.value = value;
    input.parentElement.querySelector('.color-hex').value = value;
}

document.querySelectorAll('.palette-chip').forEach(chip => {
    if (chip.dataset.presetGradient) {
        const colors = chip.dataset.presetGradient.split(',');
        chip.style.background = `linear-gradient(135deg, ${colors[0]}, ${colors[1]})`;
    } else {
        chip.style.background = `linear-gradient(135deg, ${chip.dataset.presetFill} 50%, ${chip.dataset.presetBack} 50%)`;
    }

    chip.addEventListener('click', function() {
        if (this.dataset.presetGradient) {
            const colors = this.dataset.presetGradient.split(',');
            if (!document.getElementById('use_gradient').checked) {
                document.getElementById('use_gradient').checked = true;
                toggleGradientMode();
            }
            const stops = document.querySelectorAll('#gradient-stops .gradient-stop');
            stops.forEach((stop, i) => {
                if (colors[i]) {
                    const input = stop.querySelector('input[type="color"]');
                    input.value = colors[i];
                    input.parentElement.querySelector('.color-hex').value = colors[i];
                }
            });
        } else {
            if (document.getElementById('use_gradient').checked) {
                document.getElementById('use_gradient').checked = false;
                toggleGradientMode();
            }
            setSolidColor('fill_color', this.dataset.presetFill);
            setSolidColor('back_color', this.dataset.presetBack);
        }
        schedulePreview();
    });
});

/* ---------------- Style selection ---------------- */
function setupOptionGroup(groupId) {
    const options = document.querySelectorAll(`#${groupId} .style-option`);
    options.forEach(option => {
        option.addEventListener('click', function() {
            options.forEach(opt => opt.classList.remove('selected'));
            this.classList.add('selected');
            this.querySelector('input[type="radio"]').checked = true;
            schedulePreview();
        });
    });
}

/* ---------------- Eye color ---------------- */
function toggleEyeColor() {
    const useEyeColor = document.getElementById('use_eye_color').checked;
    document.getElementById('eye-color-options').classList.toggle('hidden', !useEyeColor);
}

/* ---------------- Logos ---------------- */
const logoInput = document.getElementById('logo');
const logoPreviewImg = document.getElementById('logo-preview-img');
const logoPreviewPlaceholder = document.getElementById('logo-preview-placeholder');
const logoRemoveBtn = document.getElementById('logo-remove-btn');
const logoDataInput = document.getElementById('logo-data-input');

function setLogoPreview(src) {
    logoDataInput.value = src;
    if (src) {
        logoPreviewImg.src = src;
        logoPreviewImg.hidden = false;
        logoPreviewPlaceholder.hidden = true;
        logoRemoveBtn.hidden = false;
    } else {
        logoPreviewImg.src = '';
        logoPreviewImg.hidden = true;
        logoPreviewPlaceholder.hidden = false;
        logoRemoveBtn.hidden = true;
    }
}

async function setBrandLogo(brandId) {
    try {
        const response = await fetch(`/static/brands/${brandId}.svg`);
        if (!response.ok) throw new Error('fetch failed');
        const svgText = await response.text();
        const dataUrl = `data:image/svg+xml;base64,${btoa(unescape(encodeURIComponent(svgText)))}`;

        const img = new Image();
        await new Promise((resolve, reject) => {
            img.onload = resolve;
            img.onerror = reject;
            img.src = dataUrl;
        });

        const canvas = document.createElement('canvas');
        canvas.width = 512;
        canvas.height = 512;
        const ctx = canvas.getContext('2d');
        const padding = 512 * 0.06;
        ctx.drawImage(img, padding, padding, 512 - 2 * padding, 512 - 2 * padding);

        ctx.globalCompositeOperation = 'source-in';
        const color = getComputedStyle(document.querySelector(`.brand-icon[data-brand="${brandId}"]`)).color;
        ctx.fillStyle = color;
        ctx.fillRect(0, 0, 512, 512);

        setLogoPreview(canvas.toDataURL('image/png'));
        document.querySelectorAll('.brand-icon').forEach(btn => btn.classList.remove('selected'));
        document.querySelector(`.brand-icon[data-brand="${brandId}"]`).classList.add('selected');
        logoInput.value = '';
        schedulePreview();
    } catch (e) {
        console.error(e);
    }
}

function handleLogoSelect(input) {
    const file = input.files[0];
    if (!file) return;

    if (!file.type.startsWith('image/') || file.type === 'image/svg+xml') {
        alert(I18N.logoInvalidType);
        input.value = '';
        return;
    }
    if (file.size > 2 * 1024 * 1024) {
        alert(I18N.logoTooLarge);
        input.value = '';
        return;
    }

    const reader = new FileReader();
    reader.onload = (e) => {
        document.querySelectorAll('.brand-icon').forEach(btn => btn.classList.remove('selected'));
        setLogoPreview(e.target.result);
        schedulePreview();
    };
    reader.readAsDataURL(file);
}

function removeLogo() {
    logoInput.value = '';
    setLogoPreview('');
    document.querySelectorAll('.brand-icon').forEach(btn => btn.classList.remove('selected'));
    schedulePreview();
}

/* ---------------- Live preview ---------------- */
const form = document.getElementById('qr-form');
let previewTimer = null;
let lastPreviewKey = '';

function schedulePreview() {
    clearTimeout(previewTimer);
    previewTimer = setTimeout(runPreview, 450);
}

form.addEventListener('input', schedulePreview);
form.addEventListener('change', schedulePreview);

async function runPreview() {
    const urlInput = document.getElementById('url');
    if (!urlInput.value || !urlInput.checkValidity()) return;

    const fd = new FormData(form);
    const key = JSON.stringify([...fd.entries()]);
    if (key === lastPreviewKey) return;
    lastPreviewKey = key;

    try {
        const response = await fetch('/', { method: 'POST', body: fd });
        if (!response.ok) return;
        const html = await response.text();
        const doc = new DOMParser().parseFromString(html, 'text/html');

        const errorEl = doc.querySelector('#form-error');
        const localError = document.getElementById('form-error');
        if (errorEl && errorEl.textContent.trim()) {
            localError.textContent = errorEl.textContent.trim();
            localError.classList.remove('hidden');
        } else {
            localError.textContent = '';
            localError.classList.add('hidden');
        }

        const resultWrap = doc.querySelector('#qr-result-wrap');
        const localWrap = document.getElementById('qr-result-wrap');
        if (resultWrap && resultWrap.innerHTML.trim()) {
            localWrap.innerHTML = resultWrap.innerHTML;
        }
    } catch (e) {
        /* network error: keep previous preview */
    }
}

/* ---------------- Download & copy ---------------- */
document.addEventListener('submit', async function(e) {
    const downloadForm = e.target.closest('form[action="/download"]');
    if (!downloadForm) return;
    e.preventDefault();

    const fd = new FormData(form);
    fd.delete('logo_data');

    const qrLogoInput = downloadForm.querySelector('input[name="logo_data"]');
    if (qrLogoInput && qrLogoInput.value) fd.append('logo_data', qrLogoInput.value);

    try {
        const response = await fetch('/download', { method: 'POST', body: fd });
        if (!response.ok) throw new Error('download failed');
        const blob = await response.blob();
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = 'qrcode.png';
        a.click();
        URL.revokeObjectURL(a.href);
    } catch (err) {
        downloadForm.submit();
    }
});

async function copyToClipboard() {
    const img = document.querySelector('#qr-image img');
    if (!img) return;

    try {
        const response = await fetch(img.src);
        const blob = await response.blob();

        await navigator.clipboard.write([
            new ClipboardItem({ 'image/png': blob })
        ]);

        alert(I18N.copySuccess);
    } catch (err) {
        console.error(I18N.copyErrorConsole, err);
        alert(I18N.copyError);
    }
}

/* ---------------- Init ---------------- */
setupOptionGroup('style-options');
setupOptionGroup('eye-style-options');

document.getElementById('use_gradient').addEventListener('change', toggleGradientMode);
document.getElementById('use_eye_color').addEventListener('change', toggleEyeColor);
document.getElementById('add-stop').addEventListener('click', addGradientStop);
document.getElementById('gradient-stops').addEventListener('click', (e) => {
    const btn = e.target.closest('.remove-stop');
    if (btn) removeGradientStop(btn);
});
document.getElementById('logo').addEventListener('change', function() {
    handleLogoSelect(this);
});
document.getElementById('logo-remove-btn').addEventListener('click', removeLogo);
document.addEventListener('click', (e) => {
    if (e.target.closest('[data-action="copy"]')) copyToClipboard();
});
document.querySelectorAll('.brand-icon').forEach(btn => {
    btn.addEventListener('click', () => setBrandLogo(btn.dataset.brand));
});
document.querySelectorAll('#qr-form input[type="color"]').forEach(setupColorSync);
document.querySelectorAll('.gradient-stop').forEach(setupDragAndDrop);
updateGradientStops();
toggleGradientMode();
toggleEyeColor();
