import { formatMessage, addCodeCopyButtons, TOOL_CONFIG } from '../modules/markdown.js';

describe('Markdown Module', () => {
    describe('TOOL_CONFIG', () => {
        test('should have tools array defined', () => {
            expect(TOOL_CONFIG.tools).toBeInstanceOf(Array);
            expect(TOOL_CONFIG.tools.length).toBeGreaterThan(0);
        });

        test('should have Terminal tool', () => {
            const terminal = TOOL_CONFIG.tools.find(t => t.name === 'Terminal');
            expect(terminal).toBeDefined();
            expect(terminal.icon).toBe('fa-terminal');
        });
    });

    describe('formatMessage', () => {
        test('should handle empty string', () => {
            expect(formatMessage('')).toBe('');
        });

        test('should handle null', () => {
            expect(formatMessage(null)).toBe('');
        });

        test('should wrap content in paragraph tags', () => {
            const result = formatMessage('Hello world');
            expect(result).toContain('<p>');
            expect(result).toContain('Hello world');
        });

        test('should format inline code', () => {
            const result = formatMessage('Use `console.log()` for debugging');
            expect(result).toContain('<code class="inline-code">console.log()</code>');
        });

        test('should format bold text', () => {
            const result = formatMessage('This is **bold** text');
            expect(result).toContain('<strong>bold</strong>');
        });

        test('should format italic text', () => {
            const result = formatMessage('This is *italic* text');
            expect(result).toContain('<em>italic</em>');
        });

        test('should format headers', () => {
            expect(formatMessage('# Heading 1')).toContain('<h2>Heading 1</h2>');
            expect(formatMessage('## Heading 2')).toContain('<h3>Heading 2</h3>');
            expect(formatMessage('### Heading 3')).toContain('<h4>Heading 3</h4>');
        });

        test('should format lists', () => {
            const result = formatMessage('- Item 1\n- Item 2');
            expect(result).toContain('<li>Item 1</li>');
            expect(result).toContain('<li>Item 2</li>');
            expect(result).toContain('<ul>');
        });

        test('should format links', () => {
            const result = formatMessage('[Google](https://google.com)');
            expect(result).toContain('<a href="https://google.com" target="_blank">Google</a>');
        });

        test('should format code blocks', () => {
            const result = formatMessage('```javascript\nconsole.log("hello");\n```');
            expect(result).toContain('<pre>');
            expect(result).toContain('<code class="language-javascript">');
        });

        test('should show streaming cursor when streaming', () => {
            const result = formatMessage('```javascript\nconst x = 1;', true);
            expect(result).toContain('code-cursor');
        });

        test('should format blockquotes', () => {
            const result = formatMessage('> This is a quote');
            expect(result).toContain('<blockquote>');
            expect(result).toContain('This is a quote');
        });
    });

    describe('addCodeCopyButtons', () => {
        test('should add copy button to code blocks', () => {
            const container = document.createElement('div');
            container.innerHTML = '<pre><code>const x = 1;</code></pre>';
            
            addCodeCopyButtons(container);
            
            const button = container.querySelector('.copy-code-btn');
            expect(button).not.toBeNull();
        });

        test('should not add duplicate buttons', () => {
            const container = document.createElement('div');
            container.innerHTML = '<pre><code>const x = 1;</code></pre>';
            
            addCodeCopyButtons(container);
            addCodeCopyButtons(container);
            
            const buttons = container.querySelectorAll('.copy-code-btn');
            expect(buttons.length).toBe(1);
        });
    });
});

