import { state } from '../modules/state.js';
import { DOM } from '../modules/dom.js';
import {
    handleImageSelect,
    updateImagePreview,
    removeImage,
    clearSelectedImages,
    formatMessageWithImages,
    toggleVoiceRecording
} from '../modules/media.js';

describe('Media Module', () => {
    beforeEach(() => {
        state.selectedImages = [];
        state.isRecording = false;
        DOM.clear();
    });

    describe('updateImagePreview', () => {
        test('should hide preview area when no images', () => {
            state.selectedImages = [];
            updateImagePreview();
            
            const previewArea = document.getElementById('imagePreviewArea');
            expect(previewArea.style.display).toBe('none');
        });

        test('should show preview area when images exist', () => {
            state.selectedImages = [{ path: '/test.jpg', name: 'test.jpg', previewUrl: 'blob:test' }];
            updateImagePreview();
            
            const previewArea = document.getElementById('imagePreviewArea');
            expect(previewArea.style.display).toBe('flex');
        });

        test('should render image previews', () => {
            state.selectedImages = [
                { path: '/test1.jpg', name: 'test1.jpg', previewUrl: 'blob:test1' },
                { path: '/test2.jpg', name: 'test2.jpg', previewUrl: 'blob:test2' }
            ];
            updateImagePreview();
            
            const container = document.getElementById('imagePreviewContainer');
            expect(container.querySelectorAll('.image-preview-item').length).toBe(2);
        });
    });

    describe('removeImage', () => {
        test('should remove image at given index', () => {
            state.selectedImages = [
                { path: '/test1.jpg', name: 'test1.jpg', previewUrl: 'blob:test1' },
                { path: '/test2.jpg', name: 'test2.jpg', previewUrl: 'blob:test2' }
            ];
            
            removeImage(0);
            
            expect(state.selectedImages.length).toBe(1);
            expect(state.selectedImages[0].name).toBe('test2.jpg');
        });

        test('should revoke object URL when removing', () => {
            state.selectedImages = [{ path: '/test.jpg', name: 'test.jpg', previewUrl: 'blob:test' }];
            
            removeImage(0);
            
            expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:test');
        });

        test('should handle invalid index gracefully', () => {
            state.selectedImages = [{ path: '/test.jpg', name: 'test.jpg', previewUrl: 'blob:test' }];
            
            expect(() => removeImage(5)).not.toThrow();
            expect(state.selectedImages.length).toBe(1);
        });
    });

    describe('clearSelectedImages', () => {
        test('should clear all selected images', () => {
            state.selectedImages = [
                { path: '/test1.jpg', name: 'test1.jpg', previewUrl: 'blob:test1' },
                { path: '/test2.jpg', name: 'test2.jpg', previewUrl: 'blob:test2' }
            ];
            
            clearSelectedImages();
            
            expect(state.selectedImages.length).toBe(0);
        });

        test('should revoke all object URLs', () => {
            state.selectedImages = [
                { path: '/test1.jpg', name: 'test1.jpg', previewUrl: 'blob:test1' },
                { path: '/test2.jpg', name: 'test2.jpg', previewUrl: 'blob:test2' }
            ];
            
            clearSelectedImages();
            
            expect(URL.revokeObjectURL).toHaveBeenCalledTimes(2);
        });
    });

    describe('formatMessageWithImages', () => {
        test('should return plain message when no images', () => {
            const result = formatMessageWithImages('Hello', []);
            expect(result).toBe('Hello');
        });

        test('should format message with image path', () => {
            const images = [{ path: '/path/to/image.jpg', name: 'image.jpg' }];
            const result = formatMessageWithImages('Describe this', images);
            expect(result).toBe('/images /path/to/image.jpg|||Describe this');
        });
    });

    describe('window global assignments', () => {
        test('removeImage should be on window', () => {
            expect(window.removeImage).toBeDefined();
        });

        test('handleImageSelect should be on window', () => {
            expect(window.handleImageSelect).toBeDefined();
        });

        test('clearSelectedImages should be on window', () => {
            expect(window.clearSelectedImages).toBeDefined();
        });

        test('toggleVoiceRecording should be on window', () => {
            expect(window.toggleVoiceRecording).toBeDefined();
        });
    });
});

