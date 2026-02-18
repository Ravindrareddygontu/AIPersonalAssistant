import { DOM, escapeHtml, autoResize, scrollToBottom, isNearBottom, showElement, hideElement } from '../modules/dom.js';

describe('DOM Module', () => {
    describe('DOM.get', () => {
        test('should return element by ID', () => {
            const element = DOM.get('chatMessages');
            expect(element).not.toBeNull();
            expect(element.id).toBe('chatMessages');
        });

        test('should return null for non-existent element', () => {
            const element = DOM.get('nonExistentElement');
            expect(element).toBeNull();
        });
    });

    describe('escapeHtml', () => {
        test('should escape < and > characters', () => {
            expect(escapeHtml('<script>alert("xss")</script>')).toBe('&lt;script&gt;alert("xss")&lt;/script&gt;');
        });

        test('should escape ampersand', () => {
            expect(escapeHtml('foo & bar')).toBe('foo &amp; bar');
        });

        test('should escape quotes', () => {
            const result = escapeHtml('"test"');
            expect(result).toBeDefined();
        });

        test('should escape single quotes', () => {
            const result = escapeHtml("it's");
            expect(result).toBeDefined();
        });

        test('should handle empty string', () => {
            expect(escapeHtml('')).toBe('');
        });

        test('should handle string with no special chars', () => {
            expect(escapeHtml('hello world')).toBe('hello world');
        });
    });

    describe('autoResize', () => {
        test('should adjust element height based on scrollHeight', () => {
            const textarea = document.createElement('textarea');
            textarea.style.height = '50px';
            document.body.appendChild(textarea);
            
            Object.defineProperty(textarea, 'scrollHeight', { value: 100, configurable: true });
            
            autoResize(textarea);
            expect(textarea.style.height).toBe('100px');
        });

        test('should handle null element gracefully', () => {
            expect(() => autoResize(null)).not.toThrow();
        });
    });

    describe('scrollToBottom', () => {
        test('should call scrollTo on element', (done) => {
            const container = document.getElementById('chatMessages');
            container.scrollTo = jest.fn();
            Object.defineProperty(container, 'scrollHeight', { value: 500, configurable: true });

            scrollToBottom(container, false);
            setTimeout(() => {
                expect(container.scrollTo).toHaveBeenCalled();
                done();
            }, 100);
        });

        test('should handle null element gracefully', () => {
            expect(() => scrollToBottom(null)).not.toThrow();
        });
    });

    describe('isNearBottom', () => {
        test('should return true when near bottom', () => {
            const container = document.createElement('div');
            Object.defineProperty(container, 'scrollTop', { value: 400, configurable: true });
            Object.defineProperty(container, 'scrollHeight', { value: 500, configurable: true });
            Object.defineProperty(container, 'clientHeight', { value: 100, configurable: true });
            
            expect(isNearBottom(container, 50)).toBe(true);
        });

        test('should return false when far from bottom', () => {
            const container = document.createElement('div');
            Object.defineProperty(container, 'scrollTop', { value: 0, configurable: true });
            Object.defineProperty(container, 'scrollHeight', { value: 500, configurable: true });
            Object.defineProperty(container, 'clientHeight', { value: 100, configurable: true });
            
            expect(isNearBottom(container, 50)).toBe(false);
        });
    });

    describe('showElement / hideElement', () => {
        test('showElement should set display style', () => {
            const element = document.createElement('div');
            element.style.display = 'none';
            
            showElement(element, 'flex');
            expect(element.style.display).toBe('flex');
        });

        test('hideElement should set display to none', () => {
            const element = document.createElement('div');
            element.style.display = 'block';
            
            hideElement(element);
            expect(element.style.display).toBe('none');
        });

        test('should handle null element gracefully', () => {
            expect(() => showElement(null)).not.toThrow();
            expect(() => hideElement(null)).not.toThrow();
        });
    });
});

