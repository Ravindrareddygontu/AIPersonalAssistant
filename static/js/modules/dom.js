export const DOM = {
    _cache: {},
    get(id) {
        if (!this._cache[id]) {
            this._cache[id] = document.getElementById(id);
        }
        return this._cache[id];
    },
    clear() {
        this._cache = {};
    }
};

export function escapeHtml(text) {
    if (!text) return '';
    return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

export function autoResize(element) {
    if (!element) return;
    element.style.height = 'auto';
    const newHeight = Math.min(element.scrollHeight, 200);
    element.style.height = newHeight + 'px';
}

export function scrollToBottom(element, smooth = true) {
    if (!element) return;
    setTimeout(() => {
        element.scrollTo({
            top: element.scrollHeight,
            behavior: smooth ? 'smooth' : 'auto'
        });
    }, 50);
}

export function isNearBottom(element, threshold = 100) {
    if (!element) return true;
    return element.scrollHeight - element.scrollTop - element.clientHeight < threshold;
}

export function showElement(element, display = 'block') {
    if (!element) return;
    element.classList.remove('hidden');
    element.style.display = display;
}

export function hideElement(element) {
    if (!element) return;
    element.classList.add('hidden');
    element.style.display = 'none';
}

