import { state } from './state.js';
import { DOM, autoResize } from './dom.js';
import { showNotification } from './ui.js';

export async function handleImageSelect(event) {
    if (window.electronAPI && window.electronAPI.selectImages) {
        try {
            const result = await window.electronAPI.selectImages();
            console.log('[IMAGES] Dialog result:', result);

            if (result.canceled || !result.images || result.images.length === 0) {
                console.log('[IMAGES] Selection canceled or empty');
                return;
            }

            for (const img of result.images) {
                if (state.selectedImages.find(existing => existing.path === img.path)) {
                    continue;
                }

                state.selectedImages.push({
                    path: img.path,
                    name: img.name,
                    previewUrl: `file://${img.path}`
                });
            }

            updateImagePreview();
            console.log(`[IMAGES] Total selected: ${state.selectedImages.length}`);
        } catch (err) {
            console.error('[IMAGES] Error selecting images:', err);
        }
    } else {
        const files = event?.target?.files;
        if (!files || files.length === 0) return;

        for (const file of files) {
            let filePath = file.path || file.name;
            if (state.selectedImages.find(img => img.path === filePath)) continue;

            state.selectedImages.push({
                path: filePath,
                name: file.name,
                previewUrl: URL.createObjectURL(file)
            });
        }

        updateImagePreview();
        event.target.value = '';
    }
}

export function updateImagePreview() {
    const previewArea = DOM.get('imagePreviewArea');
    const container = DOM.get('imagePreviewContainer');
    const inputWrapper = document.querySelector('.chat-input-wrapper');
    const imageBtn = DOM.get('imageBtn');

    const hasImages = state.selectedImages.length > 0;

    if (previewArea) previewArea.style.display = hasImages ? 'flex' : 'none';
    if (inputWrapper) inputWrapper.classList.toggle('has-images', hasImages);
    if (imageBtn) imageBtn.classList.toggle('has-images', hasImages);

    if (!hasImages || !container) return;

    container.innerHTML = state.selectedImages.map((img, index) => `
        <div class="image-preview-item">
            <img src="${img.previewUrl}" alt="${img.name}">
            <button class="remove-image" onclick="window.removeImage(${index})" title="Remove">
                <i class="fas fa-times"></i>
            </button>
            <div class="image-name">${img.name}</div>
        </div>
    `).join('');
}

export function removeImage(index) {
    if (index >= 0 && index < state.selectedImages.length) {
        URL.revokeObjectURL(state.selectedImages[index].previewUrl);
        state.selectedImages.splice(index, 1);
        updateImagePreview();
    }
}

export function clearSelectedImages() {
    state.selectedImages.forEach(img => URL.revokeObjectURL(img.previewUrl));
    state.selectedImages = [];
    updateImagePreview();
}

export function formatMessageWithImages(message, images) {
    if (images.length === 0) return message;
    const imagePath = images[0].path;
    return `/images ${imagePath}|||${message}`;
}

export function toggleVoiceRecording() {
    if (state.isRecording) {
        stopVoiceRecording();
    } else {
        startVoiceRecording();
    }
}

export async function startVoiceRecording() {
    try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });

        state.mediaRecorder = new MediaRecorder(stream, {
            mimeType: MediaRecorder.isTypeSupported('audio/webm') ? 'audio/webm' : 'audio/mp4'
        });

        state.audioChunks = [];

        state.mediaRecorder.ondataavailable = (event) => {
            if (event.data.size > 0) {
                state.audioChunks.push(event.data);
            }
        };

        state.mediaRecorder.onstop = async () => {
            stream.getTracks().forEach(track => track.stop());

            if (state.audioChunks.length === 0) {
                showNotification('No audio recorded', 'error');
                return;
            }

            const audioBlob = new Blob(state.audioChunks, { type: state.mediaRecorder.mimeType });
            await transcribeAudio(audioBlob);
        };

        state.mediaRecorder.start();
        state.isRecording = true;
        updateVoiceButtonState();
        console.log('[VOICE] Recording started');

    } catch (error) {
        console.error('[VOICE] Error starting recording:', error);
        if (error.name === 'NotAllowedError') {
            showNotification('Microphone access denied', 'error');
        } else {
            showNotification('Error starting recording: ' + error.message, 'error');
        }
    }
}

export function stopVoiceRecording() {
    if (state.mediaRecorder && state.isRecording) {
        state.mediaRecorder.stop();
    }
    state.isRecording = false;
    updateVoiceButtonState();
}

async function transcribeAudio(audioBlob) {
    const voiceBtn = document.getElementById('voiceBtn');
    const voiceIcon = document.getElementById('voiceIcon');

    if (voiceBtn) voiceBtn.classList.add('processing');
    if (voiceIcon) {
        voiceIcon.classList.remove('fa-microphone');
        voiceIcon.classList.add('fa-spinner', 'fa-spin');
    }

    try {
        const formData = new FormData();
        formData.append('audio', audioBlob, 'recording.webm');

        const response = await fetch('/api/speech-to-text', {
            method: 'POST',
            body: formData
        });

        const result = await response.json();

        if (result.success && result.text) {
            const input = document.getElementById('messageInput');
            if (input) {
                const existingText = input.value.trim();
                input.value = existingText ? existingText + ' ' + result.text : result.text;
                autoResize(input);
                input.focus();
            }
            console.log('[VOICE] Transcribed:', result.text);
        } else {
            showNotification(result.error || 'Transcription failed', 'error');
        }
    } catch (error) {
        showNotification('Error transcribing audio', 'error');
    } finally {
        if (voiceBtn) voiceBtn.classList.remove('processing');
        if (voiceIcon) {
            voiceIcon.classList.remove('fa-spinner', 'fa-spin');
            voiceIcon.classList.add('fa-microphone');
        }
    }
}

function updateVoiceButtonState() {
    const voiceBtn = document.getElementById('voiceBtn');
    const voiceIcon = document.getElementById('voiceIcon');

    if (!voiceBtn || !voiceIcon) return;

    if (state.isRecording) {
        voiceBtn.classList.add('recording');
        voiceIcon.classList.remove('fa-microphone');
        voiceIcon.classList.add('fa-microphone-slash');
    } else {
        voiceBtn.classList.remove('recording');
        voiceIcon.classList.remove('fa-microphone-slash');
        voiceIcon.classList.add('fa-microphone');
    }
}

window.removeImage = removeImage;
window.handleImageSelect = handleImageSelect;
window.clearSelectedImages = clearSelectedImages;
window.toggleVoiceRecording = toggleVoiceRecording;

