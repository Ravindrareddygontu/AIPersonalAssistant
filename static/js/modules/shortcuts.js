import { showNotification, closeModalWithAnimation } from './ui.js';

const STORAGE_KEY = 'customShortcuts';

let editingShortcutId = null;
let cachedElements = null;

export function resetShortcutsCache() {
    cachedElements = null;
    editingShortcutId = null;
}

function getElements() {
    if (!cachedElements) {
        cachedElements = {
            modal: document.getElementById('addShortcutModal'),
            labelInput: document.getElementById('shortcutLabel'),
            promptInput: document.getElementById('shortcutPrompt'),
            modalTitle: null,
            saveBtn: null
        };
        if (cachedElements.modal) {
            cachedElements.modalTitle = cachedElements.modal.querySelector('.modal-header h2');
            cachedElements.saveBtn = cachedElements.modal.querySelector('.save-shortcut-btn');
        }
    }
    return cachedElements;
}

export function generateId() {
    return Date.now().toString(36) + Math.random().toString(36).substr(2, 5);
}

export function getShortcuts() {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]');
}

export function setShortcuts(shortcuts) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(shortcuts));
}

export function getEditingShortcutId() {
    return editingShortcutId;
}

export function setEditingShortcutId(id) {
    editingShortcutId = id;
}

export function isModalOpen() {
    const { modal } = getElements();
    return modal?.classList.contains('active') || false;
}

export function toggleAddShortcutModal(editId = null) {
    const { modal, labelInput, promptInput, modalTitle, saveBtn } = getElements();
    if (!modal) return;

    if (modal.classList.contains('active')) {
        closeModalWithAnimation(modal);
        editingShortcutId = null;
        return;
    }

    modal.classList.add('active');
    editingShortcutId = editId;

    if (editId !== null) {
        const shortcut = getShortcuts().find(s => s.id === editId);
        if (shortcut) {
            labelInput.value = shortcut.label;
            promptInput.value = shortcut.prompt;
        }
        if (modalTitle) modalTitle.textContent = 'Edit Shortcut';
        if (saveBtn) saveBtn.textContent = 'Update';
    } else {
        labelInput.value = '';
        promptInput.value = '';
        if (modalTitle) modalTitle.textContent = 'Add Shortcut';
        if (saveBtn) saveBtn.textContent = 'Save';
    }
    labelInput?.focus();
}

export function saveShortcut() {
    const { labelInput, promptInput } = getElements();
    const label = labelInput.value.trim();
    const prompt = promptInput.value.trim();

    if (!label && !prompt) {
        showNotification('Please fill in at least one field', 'error');
        return false;
    }

    const finalLabel = label || prompt.split(/\s+/)[0];
    const finalPrompt = prompt || label;

    const shortcuts = getShortcuts();

    if (editingShortcutId !== null) {
        const index = shortcuts.findIndex(s => s.id === editingShortcutId);
        if (index !== -1) {
            shortcuts[index] = { ...shortcuts[index], label: finalLabel, prompt: finalPrompt };
        }
        showNotification('Shortcut updated');
    } else {
        shortcuts.push({ id: generateId(), label: finalLabel, prompt: finalPrompt });
        showNotification('Shortcut added');
    }

    setShortcuts(shortcuts);
    return true;
}

export function initDefaultShortcuts() {
    const existing = localStorage.getItem('customShortcuts');
    if (!existing) {
        const defaults = [
            { id: generateId(), label: 'commit', prompt: 'commit the changes with small message' },
            { id: generateId(), label: 'yes', prompt: 'yes' }
        ];
        setShortcuts(defaults);
    }
}

export function migrateShortcutsWithIds(shortcuts) {
    let needsSave = false;
    shortcuts = shortcuts.map(s => {
        if (!s.id) {
            needsSave = true;
            return { ...s, id: generateId() };
        }
        return s;
    });
    if (needsSave) {
        setShortcuts(shortcuts);
    }
    return shortcuts;
}

export function deleteShortcut(id) {
    let shortcuts = getShortcuts();
    shortcuts = shortcuts.filter(s => s.id !== id);
    setShortcuts(shortcuts);
    showNotification('Shortcut deleted');
}

export function reorderShortcuts(fromIndex, toIndex) {
    const shortcuts = getShortcuts();
    const [moved] = shortcuts.splice(fromIndex, 1);
    shortcuts.splice(toIndex, 0, moved);
    setShortcuts(shortcuts);
}

