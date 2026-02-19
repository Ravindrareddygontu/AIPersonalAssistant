import {
    getWorkspaceSlots,
    setWorkspaceSlots,
    initWorkspaceSlots,
    saveWorkspaceToSlot,
    getNextWorkspace,
    activateSlot,
    resetWorkspaceSlots,
    hasActiveConversation,
    shouldShowWorkspaceDialog
} from '../modules/workspace.js';

describe('Workspace Module', () => {
    beforeEach(() => {
        resetWorkspaceSlots();
    });

    describe('getWorkspaceSlots', () => {
        it('returns default slots when localStorage is empty', () => {
            const slots = getWorkspaceSlots();
            expect(slots).toEqual({ slot1: '', slot2: '', active: 1 });
        });

        it('returns stored slots from localStorage', () => {
            const stored = { slot1: '/path/one', slot2: '/path/two', active: 2 };
            localStorage.setItem('workspaceSlots', JSON.stringify(stored));
            
            const slots = getWorkspaceSlots();
            expect(slots).toEqual(stored);
        });
    });

    describe('setWorkspaceSlots', () => {
        it('saves slots to localStorage', () => {
            const slots = { slot1: '/test/path', slot2: '', active: 1 };
            setWorkspaceSlots(slots);
            
            const stored = JSON.parse(localStorage.getItem('workspaceSlots'));
            expect(stored).toEqual(slots);
        });
    });

    describe('initWorkspaceSlots', () => {
        it('sets slot1 when it is empty and workspace is provided', () => {
            initWorkspaceSlots('/my/workspace');
            
            const slots = getWorkspaceSlots();
            expect(slots.slot1).toBe('/my/workspace');
        });

        it('does not overwrite slot1 if already set', () => {
            setWorkspaceSlots({ slot1: '/existing', slot2: '', active: 1 });
            initWorkspaceSlots('/new/workspace');
            
            const slots = getWorkspaceSlots();
            expect(slots.slot1).toBe('/existing');
        });

        it('does nothing when workspace is empty', () => {
            initWorkspaceSlots('');
            
            const slots = getWorkspaceSlots();
            expect(slots.slot1).toBe('');
        });
    });

    describe('saveWorkspaceToSlot', () => {
        it('saves to slot1 when active is 1', () => {
            saveWorkspaceToSlot('/workspace/one');
            
            const slots = getWorkspaceSlots();
            expect(slots.slot1).toBe('/workspace/one');
        });

        it('saves to slot2 when active is 2', () => {
            activateSlot(2);
            saveWorkspaceToSlot('/workspace/two');
            
            const slots = getWorkspaceSlots();
            expect(slots.slot2).toBe('/workspace/two');
        });
    });

    describe('getNextWorkspace', () => {
        it('returns slot2 info when currently on slot1', () => {
            setWorkspaceSlots({ slot1: '/first', slot2: '/second', active: 1 });
            
            const { newActive, targetWorkspace } = getNextWorkspace();
            expect(newActive).toBe(2);
            expect(targetWorkspace).toBe('/second');
        });

        it('returns slot1 info when currently on slot2', () => {
            setWorkspaceSlots({ slot1: '/first', slot2: '/second', active: 2 });
            
            const { newActive, targetWorkspace } = getNextWorkspace();
            expect(newActive).toBe(1);
            expect(targetWorkspace).toBe('/first');
        });

        it('returns empty targetWorkspace when target slot is not set', () => {
            setWorkspaceSlots({ slot1: '/first', slot2: '', active: 1 });
            
            const { newActive, targetWorkspace } = getNextWorkspace();
            expect(newActive).toBe(2);
            expect(targetWorkspace).toBe('');
        });
    });

    describe('activateSlot', () => {
        it('activates slot 1', () => {
            setWorkspaceSlots({ slot1: '/a', slot2: '/b', active: 2 });
            activateSlot(1);
            
            const slots = getWorkspaceSlots();
            expect(slots.active).toBe(1);
        });

        it('activates slot 2', () => {
            activateSlot(2);
            
            const slots = getWorkspaceSlots();
            expect(slots.active).toBe(2);
        });
    });

    describe('resetWorkspaceSlots', () => {
        it('clears workspace slots from localStorage', () => {
            setWorkspaceSlots({ slot1: '/test', slot2: '/test2', active: 1 });
            resetWorkspaceSlots();
            
            const slots = getWorkspaceSlots();
            expect(slots).toEqual({ slot1: '', slot2: '', active: 1 });
        });
    });

    describe('workspace switching workflow', () => {
        it('supports full workflow of setting two workspaces and switching', () => {
            initWorkspaceSlots('/project/one');
            expect(getWorkspaceSlots().slot1).toBe('/project/one');
            
            activateSlot(2);
            saveWorkspaceToSlot('/project/two');
            expect(getWorkspaceSlots().slot2).toBe('/project/two');
            
            const { newActive, targetWorkspace } = getNextWorkspace();
            expect(newActive).toBe(1);
            expect(targetWorkspace).toBe('/project/one');
            
            activateSlot(1);
            const afterSwitch = getNextWorkspace();
            expect(afterSwitch.newActive).toBe(2);
            expect(afterSwitch.targetWorkspace).toBe('/project/two');
        });
    });

    describe('hasActiveConversation', () => {
        it('returns false for null chatHistory', () => {
            expect(hasActiveConversation(null)).toBe(false);
        });

        it('returns false for undefined chatHistory', () => {
            expect(hasActiveConversation(undefined)).toBe(false);
        });

        it('returns false for empty chatHistory', () => {
            expect(hasActiveConversation([])).toBe(false);
        });

        it('returns true for chatHistory with messages', () => {
            const chatHistory = [{ role: 'user', content: 'Hello' }];
            expect(hasActiveConversation(chatHistory)).toBe(true);
        });

        it('returns true for chatHistory with multiple messages', () => {
            const chatHistory = [
                { role: 'user', content: 'Hello' },
                { role: 'assistant', content: 'Hi there!' }
            ];
            expect(hasActiveConversation(chatHistory)).toBe(true);
        });
    });

    describe('shouldShowWorkspaceDialog', () => {
        it('returns show: false when target is same as current workspace', () => {
            const result = shouldShowWorkspaceDialog([], '/path/one', '/path/one');
            expect(result.show).toBe(false);
            expect(result.reason).toBe('same_workspace');
        });

        it('returns show: false when no active conversation', () => {
            const result = shouldShowWorkspaceDialog([], '/path/one', '/path/two');
            expect(result.show).toBe(false);
            expect(result.reason).toBe('no_conversation');
        });

        it('returns show: true when there is active conversation', () => {
            const chatHistory = [{ role: 'user', content: 'Hello' }];
            const result = shouldShowWorkspaceDialog(chatHistory, '/path/one', '/path/two');
            expect(result.show).toBe(true);
            expect(result.reason).toBe('active_conversation');
        });

        it('returns show: false for same workspace even with active conversation', () => {
            const chatHistory = [{ role: 'user', content: 'Hello' }];
            const result = shouldShowWorkspaceDialog(chatHistory, '/path/one', '/path/one');
            expect(result.show).toBe(false);
            expect(result.reason).toBe('same_workspace');
        });
    });
});
