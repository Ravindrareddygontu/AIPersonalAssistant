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

export function autoResize(element, smooth = true) {
    if (!element) return;

    const maxHeight = 200;
    const currentHeight = element.offsetHeight;

    // Temporarily disable transition for measurement
    element.style.transition = 'none';
    element.style.height = 'auto';
    const targetHeight = Math.min(element.scrollHeight, maxHeight);

    // Reset to current height immediately
    element.style.height = currentHeight + 'px';

    // Force reflow to ensure the transition works
    element.offsetHeight;

    // Re-enable transition and animate to target
    if (smooth) {
        element.style.transition = 'height 0.15s ease-out';
    }
    element.style.height = targetHeight + 'px';

    // Handle overflow when at max height
    element.style.overflowY = targetHeight >= maxHeight ? 'auto' : 'hidden';
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

