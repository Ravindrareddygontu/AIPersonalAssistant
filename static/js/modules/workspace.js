const STORAGE_KEY = 'workspaceSlots';

export function getWorkspaceSlots() {
    const slots = localStorage.getItem(STORAGE_KEY);
    return slots ? JSON.parse(slots) : { slot1: '', slot2: '', active: 1 };
}

export function setWorkspaceSlots(slots) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(slots));
}

export function initWorkspaceSlots(workspace) {
    const slots = getWorkspaceSlots();
    if (!slots.slot1 && workspace) {
        slots.slot1 = workspace;
        setWorkspaceSlots(slots);
    }
}

export function saveWorkspaceToSlot(workspace) {
    const slots = getWorkspaceSlots();
    if (slots.active === 1) {
        slots.slot1 = workspace;
    } else {
        slots.slot2 = workspace;
    }
    setWorkspaceSlots(slots);
}

export function getNextWorkspace() {
    const slots = getWorkspaceSlots();
    const newActive = slots.active === 1 ? 2 : 1;
    const targetWorkspace = newActive === 1 ? slots.slot1 : slots.slot2;
    return { newActive, targetWorkspace, slots };
}

export function activateSlot(slotNumber) {
    const slots = getWorkspaceSlots();
    slots.active = slotNumber;
    setWorkspaceSlots(slots);
}

export function resetWorkspaceSlots() {
    localStorage.removeItem(STORAGE_KEY);
}

export function hasActiveConversation(chatHistory) {
    return !!(chatHistory && chatHistory.length > 0);
}

export function shouldShowWorkspaceDialog(chatHistory, currentWorkspace, targetWorkspace) {
    if (targetWorkspace === currentWorkspace) {
        return { show: false, reason: 'same_workspace' };
    }
    if (hasActiveConversation(chatHistory)) {
        return { show: true, reason: 'active_conversation' };
    }
    return { show: false, reason: 'no_conversation' };
}
