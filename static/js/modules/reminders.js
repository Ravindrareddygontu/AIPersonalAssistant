import { api, logRequest, logResponse } from './api.js';
import { showNotification } from './ui.js';

let reminders = [];
let reminderTimers = {};
const DAY_TO_NUM = { sun: 0, mon: 1, tue: 2, wed: 3, thu: 4, fri: 5, sat: 6 };
const NUM_TO_DAY = ['sun', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat'];

export async function loadReminders() {
    const url = '/api/reminders';
    logRequest('GET', url);
    try {
        const response = await fetch(url);
        const data = await response.json();
        logResponse('GET', url, response.status, data);
        reminders = data;
        renderReminders();
        scheduleAllReminders();
    } catch (error) {
        console.error('Failed to load reminders:', error);
    }
}

function getMsUntilNextTrigger(reminder) {
    if (!reminder.enabled) return null;

    const [hour, minute] = reminder.time.split(':').map(Number);
    const now = new Date();
    const currentDay = now.getDay();

    for (let i = 0; i < 7; i++) {
        const checkDay = (currentDay + i) % 7;
        const dayName = NUM_TO_DAY[checkDay];

        if (reminder.days.includes(dayName)) {
            const triggerDate = new Date(now);
            triggerDate.setDate(now.getDate() + i);
            triggerDate.setHours(hour, minute, 0, 0);

            const msUntil = triggerDate.getTime() - now.getTime();
            if (msUntil > 0) {
                return msUntil;
            }
        }
    }
    return null;
}

function scheduleReminder(reminder) {
    if (reminderTimers[reminder.id]) {
        clearTimeout(reminderTimers[reminder.id]);
        delete reminderTimers[reminder.id];
    }

    if (!reminder.enabled) return;

    const msUntil = getMsUntilNextTrigger(reminder);
    if (msUntil === null) return;

    console.log(`[Reminder] Scheduled "${reminder.title}" in ${Math.round(msUntil / 60000)} minutes`);

    reminderTimers[reminder.id] = setTimeout(() => {
        showDesktopNotification(reminder.title, reminder.message || 'Reminder!');
        scheduleReminder(reminder);
    }, msUntil);
}

function scheduleAllReminders() {
    Object.keys(reminderTimers).forEach(id => clearTimeout(reminderTimers[id]));
    reminderTimers = {};
    reminders.filter(r => r.enabled).forEach(scheduleReminder);
}

export async function addReminder() {
    const titleInput = document.getElementById('reminderTitle');
    const messageInput = document.getElementById('reminderMessage');
    const timeInput = document.getElementById('reminderTime');
    const dayCheckboxes = document.querySelectorAll('.day-checkbox input:checked');

    const title = titleInput?.value.trim();
    if (!title) {
        showNotification('Please enter a reminder title');
        return;
    }

    const days = Array.from(dayCheckboxes).map(cb => cb.value);
    if (days.length === 0) {
        showNotification('Please select at least one day');
        return;
    }

    const url = '/api/reminders';
    const requestBody = {
        title,
        message: messageInput?.value.trim() || '',
        time: timeInput?.value || '09:00',
        days
    };

    try {
        const response = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(requestBody)
        });

        if (response.ok) {
            titleInput.value = '';
            messageInput.value = '';
            await loadReminders();
            showNotification('Reminder added!');
        }
    } catch (error) {
        showNotification('Error adding reminder');
    }
}

export async function toggleReminder(id) {
    try {
        const response = await fetch(`/api/reminders/${id}/toggle`, { method: 'POST' });
        if (response.ok) {
            await loadReminders();
        }
    } catch (error) {
        console.error('Failed to toggle reminder:', error);
    }
}

export async function deleteReminder(id) {
    try {
        const response = await fetch(`/api/reminders/${id}`, { method: 'DELETE' });
        if (response.ok) {
            await loadReminders();
            showNotification('Reminder deleted');
        }
    } catch (error) {
        console.error('Failed to delete reminder:', error);
    }
}

function renderReminders() {
    const list = document.getElementById('remindersList');
    if (!list) return;

    if (reminders.length === 0) {
        list.innerHTML = '<div class="no-reminders">No reminders yet</div>';
        return;
    }

    list.innerHTML = reminders.map(r => `
        <div class="reminder-item ${r.enabled ? '' : 'disabled'}" data-id="${r.id}">
            <div class="reminder-info">
                <div class="reminder-title">${r.title}</div>
                <div class="reminder-details">${r.time} • ${r.days.join(', ')}</div>
            </div>
            <div class="reminder-actions">
                <button onclick="window.toggleReminder('${r.id}')" title="${r.enabled ? 'Disable' : 'Enable'}">
                    <i class="fas fa-${r.enabled ? 'pause' : 'play'}"></i>
                </button>
                <button class="delete" onclick="window.deleteReminder('${r.id}')" title="Delete">
                    <i class="fas fa-trash"></i>
                </button>
            </div>
        </div>
    `).join('');
}

function showDesktopNotification(title, message) {
    if (window.electronAPI?.showNotification) {
        window.electronAPI.showNotification(title, message);
        return;
    }

    if ('Notification' in window) {
        if (Notification.permission === 'granted') {
            new Notification(title, { body: message, icon: '/static/icon.png' });
        } else if (Notification.permission !== 'denied') {
            Notification.requestPermission().then(permission => {
                if (permission === 'granted') {
                    new Notification(title, { body: message, icon: '/static/icon.png' });
                }
            });
        }
    }

    showNotification(`🔔 ${title}: ${message}`);
}

window.toggleReminder = toggleReminder;
window.deleteReminder = deleteReminder;
window.addReminder = addReminder;

