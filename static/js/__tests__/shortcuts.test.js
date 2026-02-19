import {
    generateId,
    getShortcuts,
    setShortcuts,
    getEditingShortcutId,
    setEditingShortcutId,
    toggleAddShortcutModal,
    saveShortcut,
    initDefaultShortcuts,
    migrateShortcutsWithIds,
    deleteShortcut,
    reorderShortcuts,
    isModalOpen,
    resetShortcutsCache
} from '../modules/shortcuts.js';

jest.mock('../modules/ui.js', () => ({
    showNotification: jest.fn()
}));

import { showNotification } from '../modules/ui.js';

describe('Shortcuts Module', () => {
    beforeEach(() => {
        localStorage.clear();
        resetShortcutsCache();
        jest.clearAllMocks();
    });

    describe('generateId', () => {
        test('should generate a unique string ID', () => {
            const id1 = generateId();
            const id2 = generateId();
            expect(typeof id1).toBe('string');
            expect(id1.length).toBeGreaterThan(5);
            expect(id1).not.toBe(id2);
        });
    });

    describe('getShortcuts / setShortcuts', () => {
        test('should return empty array when no shortcuts exist', () => {
            expect(getShortcuts()).toEqual([]);
        });

        test('should save and retrieve shortcuts', () => {
            const shortcuts = [{ id: 'abc', label: 'test', prompt: 'test prompt' }];
            setShortcuts(shortcuts);
            expect(getShortcuts()).toEqual(shortcuts);
        });
    });

    describe('initDefaultShortcuts', () => {
        test('should create default shortcuts when none exist', () => {
            initDefaultShortcuts();
            const shortcuts = getShortcuts();
            expect(shortcuts.length).toBe(2);
            expect(shortcuts[0].label).toBe('commit');
            expect(shortcuts[1].label).toBe('yes');
        });

        test('should not overwrite existing shortcuts', () => {
            const existing = [{ id: 'custom', label: 'custom', prompt: 'custom prompt' }];
            setShortcuts(existing);
            initDefaultShortcuts();
            const shortcuts = getShortcuts();
            expect(shortcuts.length).toBe(1);
            expect(shortcuts[0].label).toBe('custom');
        });

        test('default shortcuts should have IDs', () => {
            initDefaultShortcuts();
            const shortcuts = getShortcuts();
            expect(shortcuts[0].id).toBeDefined();
            expect(shortcuts[1].id).toBeDefined();
        });
    });

    describe('saveShortcut', () => {
        test('should return false and show error when both fields empty', () => {
            document.getElementById('shortcutLabel').value = '';
            document.getElementById('shortcutPrompt').value = '';
            const result = saveShortcut();
            expect(result).toBe(false);
            expect(showNotification).toHaveBeenCalledWith('Please fill in at least one field', 'error');
        });

        test('should create shortcut with both label and prompt', () => {
            document.getElementById('shortcutLabel').value = 'deploy';
            document.getElementById('shortcutPrompt').value = 'deploy to production';
            const result = saveShortcut();
            expect(result).toBe(true);
            const shortcuts = getShortcuts();
            expect(shortcuts.length).toBe(1);
            expect(shortcuts[0].label).toBe('deploy');
            expect(shortcuts[0].prompt).toBe('deploy to production');
            expect(showNotification).toHaveBeenCalledWith('Shortcut added');
        });

        test('should use first word of prompt as label when label is empty', () => {
            document.getElementById('shortcutLabel').value = '';
            document.getElementById('shortcutPrompt').value = 'build the project';
            saveShortcut();
            const shortcuts = getShortcuts();
            expect(shortcuts[0].label).toBe('build');
            expect(shortcuts[0].prompt).toBe('build the project');
        });

        test('should use label as prompt when prompt is empty', () => {
            document.getElementById('shortcutLabel').value = 'yes';
            document.getElementById('shortcutPrompt').value = '';
            saveShortcut();
            const shortcuts = getShortcuts();
            expect(shortcuts[0].label).toBe('yes');
            expect(shortcuts[0].prompt).toBe('yes');
        });

        test('should update existing shortcut when editing', () => {
            const existing = [{ id: 'edit-me', label: 'old', prompt: 'old prompt' }];
            setShortcuts(existing);
            setEditingShortcutId('edit-me');
            document.getElementById('shortcutLabel').value = 'new';
            document.getElementById('shortcutPrompt').value = 'new prompt';
            saveShortcut();
            const shortcuts = getShortcuts();
            expect(shortcuts.length).toBe(1);
            expect(shortcuts[0].label).toBe('new');
            expect(shortcuts[0].prompt).toBe('new prompt');
            expect(shortcuts[0].id).toBe('edit-me');
            expect(showNotification).toHaveBeenCalledWith('Shortcut updated');
        });
    });

    describe('deleteShortcut', () => {
        test('should remove shortcut by ID', () => {
            const shortcuts = [
                { id: 'a', label: 'first', prompt: 'first' },
                { id: 'b', label: 'second', prompt: 'second' }
            ];
            setShortcuts(shortcuts);
            deleteShortcut('a');
            const remaining = getShortcuts();
            expect(remaining.length).toBe(1);
            expect(remaining[0].id).toBe('b');
            expect(showNotification).toHaveBeenCalledWith('Shortcut deleted');
        });
    });

    describe('reorderShortcuts', () => {
        test('should move shortcut from one position to another', () => {
            const shortcuts = [
                { id: 'a', label: 'first', prompt: 'first' },
                { id: 'b', label: 'second', prompt: 'second' },
                { id: 'c', label: 'third', prompt: 'third' }
            ];
            setShortcuts(shortcuts);
            reorderShortcuts(0, 2);
            const reordered = getShortcuts();
            expect(reordered[0].id).toBe('b');
            expect(reordered[1].id).toBe('c');
            expect(reordered[2].id).toBe('a');
        });

        test('should move shortcut backwards', () => {
            const shortcuts = [
                { id: 'a', label: 'first', prompt: 'first' },
                { id: 'b', label: 'second', prompt: 'second' },
                { id: 'c', label: 'third', prompt: 'third' }
            ];
            setShortcuts(shortcuts);
            reorderShortcuts(2, 0);
            const reordered = getShortcuts();
            expect(reordered[0].id).toBe('c');
            expect(reordered[1].id).toBe('a');
            expect(reordered[2].id).toBe('b');
        });
    });

    describe('migrateShortcutsWithIds', () => {
        test('should add IDs to shortcuts without them', () => {
            const shortcuts = [
                { label: 'no-id', prompt: 'no id prompt' },
                { id: 'has-id', label: 'with-id', prompt: 'with id prompt' }
            ];
            const migrated = migrateShortcutsWithIds(shortcuts);
            expect(migrated[0].id).toBeDefined();
            expect(migrated[1].id).toBe('has-id');
        });

        test('should save to localStorage when migration needed', () => {
            const shortcuts = [{ label: 'no-id', prompt: 'test' }];
            migrateShortcutsWithIds(shortcuts);
            const saved = getShortcuts();
            expect(saved[0].id).toBeDefined();
        });

        test('should not save when no migration needed', () => {
            const shortcuts = [{ id: 'exists', label: 'test', prompt: 'test' }];
            setShortcuts([]);
            migrateShortcutsWithIds(shortcuts);
            expect(getShortcuts()).toEqual([]);
        });
    });

    describe('toggleAddShortcutModal', () => {
        test('should toggle modal active class', () => {
            const modal = document.getElementById('addShortcutModal');
            expect(modal.classList.contains('active')).toBe(false);
            toggleAddShortcutModal();
            expect(modal.classList.contains('active')).toBe(true);
            toggleAddShortcutModal();
            expect(modal.classList.contains('active')).toBe(false);
        });

        test('should clear fields when opening for new shortcut', () => {
            document.getElementById('shortcutLabel').value = 'existing';
            document.getElementById('shortcutPrompt').value = 'existing prompt';
            toggleAddShortcutModal();
            expect(document.getElementById('shortcutLabel').value).toBe('');
            expect(document.getElementById('shortcutPrompt').value).toBe('');
        });

        test('should populate fields when editing', () => {
            const shortcuts = [{ id: 'edit-id', label: 'edit-label', prompt: 'edit-prompt' }];
            setShortcuts(shortcuts);
            toggleAddShortcutModal('edit-id');
            expect(document.getElementById('shortcutLabel').value).toBe('edit-label');
            expect(document.getElementById('shortcutPrompt').value).toBe('edit-prompt');
        });

        test('should set modal title to Edit when editing', () => {
            const shortcuts = [{ id: 'edit-id', label: 'test', prompt: 'test' }];
            setShortcuts(shortcuts);
            toggleAddShortcutModal('edit-id');
            const title = document.querySelector('#addShortcutModal .modal-header h2');
            expect(title.textContent).toBe('Edit Shortcut');
        });

        test('should set modal title to Add when creating new', () => {
            toggleAddShortcutModal();
            const title = document.querySelector('#addShortcutModal .modal-header h2');
            expect(title.textContent).toBe('Add Shortcut');
        });

        test('should reset editingShortcutId when closing', () => {
            setEditingShortcutId('some-id');
            toggleAddShortcutModal();
            toggleAddShortcutModal();
            expect(getEditingShortcutId()).toBeNull();
        });
    });

    describe('duplicate shortcuts', () => {
        test('should allow duplicate labels', () => {
            document.getElementById('shortcutLabel').value = 'deploy';
            document.getElementById('shortcutPrompt').value = 'deploy to staging';
            saveShortcut();
            setEditingShortcutId(null);
            document.getElementById('shortcutLabel').value = 'deploy';
            document.getElementById('shortcutPrompt').value = 'deploy to production';
            saveShortcut();
            const shortcuts = getShortcuts();
            expect(shortcuts.length).toBe(2);
            expect(shortcuts[0].id).not.toBe(shortcuts[1].id);
        });
    });

    describe('isModalOpen', () => {
        test('should return false when modal is closed', () => {
            expect(isModalOpen()).toBe(false);
        });

        test('should return true when modal is open', () => {
            toggleAddShortcutModal();
            expect(isModalOpen()).toBe(true);
        });

        test('should return false after modal is closed', () => {
            toggleAddShortcutModal();
            toggleAddShortcutModal();
            expect(isModalOpen()).toBe(false);
        });
    });
});

