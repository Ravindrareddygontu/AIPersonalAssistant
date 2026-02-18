import { escapeHtml } from './dom.js';

export const TOOL_CONFIG = {
    tools: [
        { name: 'Terminal', icon: 'fa-terminal', type: 'terminal' },
        { name: 'Read Directory', icon: 'fa-folder-open', type: 'read' },
        { name: 'Read directory', icon: 'fa-folder-open', type: 'read' },
        { name: 'Read File', icon: 'fa-file-code', type: 'read' },
        { name: 'Read file', icon: 'fa-file-code', type: 'read' },
        { name: 'Read Process', icon: 'fa-stream', type: 'read' },
        { name: 'Write File', icon: 'fa-file-pen', type: 'action' },
        { name: 'Edit File', icon: 'fa-edit', type: 'action' },
        { name: 'Search', icon: 'fa-search', type: 'action' },
        { name: 'Codebase Search', icon: 'fa-code', type: 'action' },
        { name: 'Codebase search', icon: 'fa-code', type: 'action' },
        { name: 'Web Search', icon: 'fa-globe', type: 'action' },
        { name: 'Web Fetch', icon: 'fa-download', type: 'action' },
        { name: 'Fetch URL', icon: 'fa-download', type: 'action' },
        { name: 'Add Tasks', icon: 'fa-list-check', type: 'task' },
        { name: 'Update Tasks', icon: 'fa-tasks', type: 'task' },
    ],
    resultPrefix: '↳',
    resultEndKeywords: [
        'command completed', 'command error', 'listed', 'read',
        'process completed', 'wrote', 'edited', 'found', 'no results',
        'added tasks successfully', 'updated tasks'
    ],
};

let _cachedToolStartRegex = null;
let _cachedToolEndRegex = null;

function getToolStartRegex() {
    if (!_cachedToolStartRegex) {
        const toolNames = TOOL_CONFIG.tools.map(t => t.name).join('|');
        _cachedToolStartRegex = new RegExp(`^(${toolNames})\\s+-\\s+(.+)$`, 'i');
    }
    return _cachedToolStartRegex;
}

function getToolEndRegex() {
    if (!_cachedToolEndRegex) {
        const toolNames = TOOL_CONFIG.tools.map(t => t.name).join('|');
        _cachedToolEndRegex = new RegExp(`^(.+?)\\s+-\\s+(${toolNames})$`, 'i');
    }
    return _cachedToolEndRegex;
}

function matchToolLine(line) {
    const startRegex = getToolStartRegex();
    let match = line.match(startRegex);
    if (match) {
        const toolConfig = TOOL_CONFIG.tools.find(t => t.name.toLowerCase() === match[1].toLowerCase());
        if (toolConfig) return { toolConfig, content: match[2] };
    }
    const endRegex = getToolEndRegex();
    match = line.match(endRegex);
    if (match) {
        const toolConfig = TOOL_CONFIG.tools.find(t => t.name.toLowerCase() === match[2].toLowerCase());
        if (toolConfig) return { toolConfig, content: match[1] };
    }
    const lineRangeMatch = line.match(/^(.+?)\s+-\s+lines\s+(\d+)-(\d+)$/i);
    if (lineRangeMatch) {
        const toolConfig = TOOL_CONFIG.tools.find(t => t.name.toLowerCase() === 'read file');
        if (toolConfig) return { toolConfig, content: lineRangeMatch[1], lineRange: { start: lineRangeMatch[2], end: lineRangeMatch[3] } };
    }
    const fileSearchMatch = line.match(/^(.+?)\s+-\s+read\s+filesearch:\s*(.+)$/i);
    if (fileSearchMatch) {
        const toolConfig = TOOL_CONFIG.tools.find(t => t.name.toLowerCase() === 'read file');
        if (toolConfig) return { toolConfig, content: fileSearchMatch[1], searchQuery: fileSearchMatch[2] };
    }
    return null;
}

function isSuccessEndLine(text) {
    const lower = text.toLowerCase().trim();
    const exactPhrases = ['command completed', 'process completed', 'added tasks successfully', 'updated tasks', 'no results'];
    if (exactPhrases.some(phrase => lower.includes(phrase))) return true;
    const startPatterns = ['read ', 'listed ', 'wrote ', 'found '];
    return startPatterns.some(p => lower.startsWith(p));
}

function isCodeDiffLine(text) {
    return /^\d+\s*[+-](\s|$)/.test(text.trim());
}

function isErrorStartLine(text) {
    const lower = text.toLowerCase();
    return lower.includes('command error') || lower.includes('traceback');
}

function isExplanatoryText(text) {
    const trimmed = text.trim();
    if (!trimmed) return false;
    const lower = trimmed.toLowerCase();
    const explanatoryStarts = ['this ', 'the ', 'let me', "i'll", 'there', 'it ', 'now ', 'would you', 'you can', 'no ', 'yes', 'i ', "i'm", 'that ', 'here ', 'based on', 'looks like', 'appears', 'seems', 'unfortunately', 'however', 'note:', 'please', 'to ', 'for ', 'if ', 'when ', 'since ', 'because ', 'as ', 'currently', 'nothing', 'none', 'all ', 'any ', 'some '];
    if (explanatoryStarts.some(s => lower.startsWith(s))) return true;
    const isProperSentence = /^[A-Z][a-z]/.test(trimmed) && trimmed.includes(' ') && !trimmed.includes('Error:') && !trimmed.includes('Exception:') && !trimmed.includes('.py') && !trimmed.startsWith('File ');
    return isProperSentence;
}

function cleanGarbageCharacters(text) {
    if (!text) return '';
    text = text.replace(/;[\d;]+\s*$/gm, '');
    text = text.replace(/;\s*$/gm, '');
    text = text.replace(/[╭╮╰╯│─┌┐└┘├┤┬┴┼]+\d*\s*$/gm, '');
    text = text.replace(/^[╭╮╰╯│─┌┐└┘├┤┬┴┼]+\d*\s*/gm, '');
    text = text.replace(/\x1b\[[0-9;]*[a-zA-Z]/g, '');
    text = text.replace(/\[\d+;\d+[Hm]/g, '');
    text = text.replace(/[\x00-\x08\x0B\x0C\x0E-\x1F]/g, '');
    text = text.replace(/\n{3,}/g, '\n\n');
    text = text.split('\n').map(line => line.trimEnd()).join('\n');
    return text.trim();
}

function formatSectionHeaders(text) {
    return text;
}

function parseToolBlocks(text) {
    const lines = text.split('\n');
    const result = [];
    let i = 0;
    while (i < lines.length) {
        const line = lines[i];
        const toolMatch = matchToolLine(line);
        if (toolMatch) {
            const { toolConfig, content: firstLine, lineRange, searchQuery } = toolMatch;
            let commandLines = [firstLine];
            let resultLines = [];
            let hasError = false;
            let inStackTrace = false;
            let foundEndResult = false;
            let toolLineRange = lineRange;
            let toolSearchQuery = searchQuery;
            i++;
            let inCodeDiff = false;
            let codeDiffLines = [];
            let expectingResultContent = false;
            while (i < lines.length && !foundEndResult) {
                const nextLine = lines[i];
                const trimmed = nextLine.trim();
                if (trimmed.startsWith(TOOL_CONFIG.resultPrefix)) {
                    const resultContent = trimmed.substring(1).trim();
                    if (resultContent) { resultLines.push(resultContent); expectingResultContent = false; }
                    else { expectingResultContent = true; }
                    if (isErrorStartLine(resultContent)) { hasError = true; inStackTrace = resultContent.toLowerCase().includes('traceback'); }
                    if (resultContent.toLowerCase().includes('edited') && (resultContent.toLowerCase().includes('addition') || resultContent.toLowerCase().includes('removal'))) inCodeDiff = true;
                    if (isSuccessEndLine(resultContent) && !hasError && !inCodeDiff) foundEndResult = true;
                    i++;
                } else if (expectingResultContent && trimmed && !matchToolLine(nextLine)) {
                    resultLines.push(trimmed);
                    expectingResultContent = false;
                    if (isErrorStartLine(trimmed)) hasError = true;
                    if (trimmed.toLowerCase().includes('edited') && (trimmed.toLowerCase().includes('addition') || trimmed.toLowerCase().includes('removal'))) inCodeDiff = true;
                    if (isSuccessEndLine(trimmed) && !hasError && !inCodeDiff) foundEndResult = true;
                    i++;
                } else if (matchToolLine(nextLine)) { break; }
                else if (inCodeDiff && isCodeDiffLine(trimmed)) { codeDiffLines.push(trimmed); i++; }
                else if (trimmed === '') { if (inCodeDiff && codeDiffLines.length > 0) break; if (resultLines.length > 0 && !inStackTrace) break; i++; }
                else if (inStackTrace) { if (isExplanatoryText(trimmed)) { inStackTrace = false; break; } resultLines.push(trimmed); i++; }
                else if (resultLines.length === 0) { commandLines.push(nextLine); i++; }
                else if (inCodeDiff) { break; }
                else { break; }
            }
            result.push({ type: 'tool', toolType: toolConfig.type, name: toolConfig.name, icon: toolConfig.icon, command: commandLines.join('\n').trim(), results: resultLines, codeDiff: codeDiffLines, hasError, lineRange: toolLineRange, searchQuery: toolSearchQuery });
            continue;
        }
        if (line.trim().startsWith(TOOL_CONFIG.resultPrefix)) { result.push({ type: 'result', content: line.trim().substring(1).trim() }); i++; continue; }
        result.push({ type: 'text', content: line });
        i++;
    }
    return result;
}

function renderToolBlock(tool) {
    const typeClass = `tool-${tool.toolType}`;
    const errorClass = tool.hasError ? ' has-error' : '';
    let html = `<br><div class="tool-block ${typeClass}${errorClass}">`;
    if (tool.lineRange) {
        const fileName = tool.command.split('/').pop();
        html += `<div class="tool-header"><i class="fas ${tool.icon}"></i> ${tool.name}</div>`;
        html += `<div class="tool-command"><code>${escapeHtml(fileName)}</code><span class="line-range">lines ${tool.lineRange.start}-${tool.lineRange.end}</span></div>`;
    } else if (tool.searchQuery) {
        const fileName = tool.command.split('/').pop();
        html += `<div class="tool-header"><i class="fas ${tool.icon}"></i> ${tool.name}</div>`;
        html += `<div class="tool-command"><code>${escapeHtml(fileName)}</code><span class="search-query"><i class="fas fa-search"></i> ${escapeHtml(tool.searchQuery)}</span></div>`;
    } else {
        html += `<div class="tool-header"><i class="fas ${tool.icon}"></i> ${tool.name}`;
        if (tool.toolType === 'terminal') {
            const encodedCommand = btoa(unescape(encodeURIComponent(tool.command)));
            html += `<button class="tool-copy-btn" data-command="${encodedCommand}" title="Copy command"><i class="fas fa-copy"></i></button>`;
        }
        html += `</div>`;
        html += `<div class="tool-command"><code>${escapeHtml(tool.command)}</code></div>`;
    }
    if (tool.results.length > 0) {
        const hasStackTrace = tool.results.some(r => r.toLowerCase().includes('traceback') || r.toLowerCase().includes('file "') || r.match(/^\s*(File|Line|\w+Error:)/i));
        if (tool.hasError && hasStackTrace) {
            html += `<div class="tool-result error-block"><div class="error-header"><i class="fas fa-exclamation-triangle"></i> Error Output</div><pre class="stack-trace">`;
            tool.results.forEach(r => { html += escapeHtml(r) + '\n'; });
            html += `</pre></div>`;
        } else if (tool.toolType === 'task') {
            html += `<div class="tool-result task-list">`;
            tool.results.filter(r => r && r.trim()).forEach(r => {
                let resultHtml = escapeHtml(r);
                const lower = r.toLowerCase();
                if (lower.includes('added tasks') || lower.includes('updated tasks')) resultHtml = `<span class="result-success">${resultHtml}</span>`;
                else if (lower.includes('→')) resultHtml = `<span class="task-status">${resultHtml}</span>`;
                else if (r.includes('(') && r.includes(')')) {
                    const parts = r.match(/^([^(]+)\(([^)]+)\)$/);
                    if (parts) resultHtml = `<span class="task-name">${escapeHtml(parts[1].trim())}</span><span class="task-desc">${escapeHtml(parts[2])}</span>`;
                }
                html += `<div class="result-line"><span class="result-arrow">↳</span> ${resultHtml}</div>`;
            });
            html += `</div>`;
        } else {
            html += `<div class="tool-result">`;
            tool.results.forEach(r => {
                let resultHtml = escapeHtml(r);
                if (r.toLowerCase().includes('error')) resultHtml = `<span class="result-error">${resultHtml}</span>`;
                else if (r.toLowerCase().includes('completed') || r.toLowerCase().includes('successfully')) resultHtml = `<span class="result-success">${resultHtml}</span>`;
                html += `<div class="result-line"><span class="result-arrow">↳</span> ${resultHtml}</div>`;
            });
            html += `</div>`;
        }
    }
    if (tool.codeDiff && tool.codeDiff.length > 0) {
        html += `</div>`;
        html += renderCodeDiffBlock(tool.codeDiff);
        return html + `<br>`;
    }
    html += `</div>`;
    return html + `<br>`;
}

function renderCodeDiffBlock(codeDiffLines, isStreaming = false) {
    let additions = 0, removals = 0;
    codeDiffLines.forEach(line => { if (/^\d+\s*\+/.test(line)) additions++; else if (/^\d+\s*-/.test(line)) removals++; });
    const streamingClass = isStreaming ? ' streaming' : '';
    const collapsedClass = isStreaming ? '' : ' collapsed';
    let html = `<div class="tool-code-diff-wrapper${streamingClass}${collapsedClass}" onclick="toggleCodeDiff(event, this)">`;
    html += `<div class="tool-code-diff-header"><span class="diff-arrow">↳</span><span class="diff-label">Code Changes</span><span class="diff-stats">`;
    if (additions > 0) html += `<span class="diff-stat-add">+${additions}</span>`;
    if (removals > 0) html += `<span class="diff-stat-remove">-${removals}</span>`;
    html += `</span><i class="fas fa-chevron-down diff-toggle-icon"></i></div>`;
    html += `<div class="tool-code-diff">`;
    codeDiffLines.forEach(line => {
        const escaped = escapeHtml(line);
        if (/^\d+\s*\+/.test(line)) html += `<div class="diff-line diff-add">${escaped}</div>`;
        else if (/^\d+\s*-/.test(line)) html += `<div class="diff-line diff-remove">${escaped}</div>`;
        else html += `<div class="diff-line">${escaped}</div>`;
    });
    html += `</div></div>`;
    return html;
}

export function formatMessage(text, isStreaming = false) {
    if (!text) return '';
    text = cleanGarbageCharacters(text);
    text = text.replace(/\r\n/g, '\n').replace(/\r/g, '\n');

    const codeBlocks = [];
    text = text.replace(/```(\w+)?\n([\s\S]*?)```/g, (match, lang, code) => {
        const index = codeBlocks.length;
        codeBlocks.push(`<pre><code class="language-${lang || 'plaintext'}">${escapeHtml(code)}</code></pre>`);
        return `__CODE_BLOCK_${index}__`;
    });
    if (isStreaming) {
        text = text.replace(/```(\w+)?\n([\s\S]*)$/g, (match, lang, code) => {
            const index = codeBlocks.length;
            codeBlocks.push(`<pre class="streaming-code"><code class="language-${lang || 'plaintext'}">${escapeHtml(code)}</code><span class="code-cursor">▋</span></pre>`);
            return `__CODE_BLOCK_${index}__`;
        });
    }

    const inlineCodes = [];
    text = text.replace(/`([^`]+)`/g, (match, code) => {
        const index = inlineCodes.length;
        inlineCodes.push(`<code>${escapeHtml(code)}</code>`);
        return `__INLINE_CODE_${index}__`;
    });

    const parsed = parseToolBlocks(text);
    const toolBlocks = [];
    const rebuiltLines = [];
    for (const item of parsed) {
        if (item.type === 'tool') {
            toolBlocks.push(renderToolBlock(item));
            rebuiltLines.push(`__TOOL_BLOCK_${toolBlocks.length - 1}__`);
        } else if (item.type === 'result') {
            toolBlocks.push(`<div class="tool-result standalone"><span class="result-arrow">↳</span> ${escapeHtml(item.content)}</div>`);
            rebuiltLines.push(`__TOOL_BLOCK_${toolBlocks.length - 1}__`);
        } else {
            rebuiltLines.push(escapeHtml(item.content));
        }
    }
    text = rebuiltLines.join('\n');

    text = text.replace(/^(\|.+\|)\n(\|[-:\s|]+\|)\n((?:\|.+\|\n?)+)/gm, (match, header, separator, body) => {
        try {
            const headerParts = header.split('|').slice(1, -1);
            const headerCells = headerParts.map(c => `<th align="left">${c.trim()}</th>`).join('');
            const bodyRows = body.trim().split('\n').map(row => {
                if (!row.includes('|')) return null;
                const cellParts = row.split('|').slice(1, -1);
                const cells = cellParts.map(c => `<td align="left">${c.trim()}</td>`).join('');
                return cells ? `<tr>${cells}</tr>` : null;
            }).filter(Boolean).join('');
            const encodedTable = btoa(unescape(encodeURIComponent(match.trim())));
            return `<br><div class="table-container"><table><thead><tr>${headerCells}</tr></thead><tbody>${bodyRows}</tbody></table></div><br><br>`;
        } catch (e) { return match; }
    });

    text = text.replace(/^### (.+)$/gm, '<h4>$1</h4>');
    text = text.replace(/^## (.+)$/gm, '<h3>$1</h3>');
    text = text.replace(/^# (.+)$/gm, '<h2>$1</h2>');
    text = text.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    text = text.replace(/(?<!\*)\*([^*]+)\*(?!\*)/g, '<em>$1</em>');
    text = formatSectionHeaders(text);


    const lines = text.split('\n');
    const processedLines = [];
    const listStack = [];
    for (const line of lines) {
        const bulletMatch = line.match(/^([\s]*)[•\-\*]\s+(.+)$/);
        const numberedMatch = line.match(/^([\s]*)(\d+)\.\s+(.+)$/);
        if (bulletMatch || numberedMatch) {
            const indent = (bulletMatch ? bulletMatch[1] : numberedMatch[1]).length;
            const itemType = bulletMatch ? 'ul' : 'ol';
            const content = bulletMatch ? bulletMatch[2] : numberedMatch[3];
            const num = numberedMatch ? parseInt(numberedMatch[2], 10) : null;
            while (listStack.length > 0 && listStack[listStack.length - 1].indent >= indent) {
                const closed = listStack.pop();
                processedLines.push(closed.type === 'ul' ? '</ul></li>' : '</ol></li>');
            }
            const currentList = listStack.length > 0 ? listStack[listStack.length - 1] : null;
            if (!currentList || indent > currentList.indent) {
                if (currentList && indent > currentList.indent) {
                    const lastLine = processedLines[processedLines.length - 1];
                    if (lastLine && lastLine.endsWith('</li>')) processedLines[processedLines.length - 1] = lastLine.slice(0, -5);
                }
                processedLines.push(itemType === 'ul' ? '<ul class="md-list">' : `<ol class="md-list" start="${num}">`);
                listStack.push({ type: itemType, indent });
            } else if (currentList.type !== itemType) {
                processedLines.push(currentList.type === 'ul' ? '</ul>' : '</ol>');
                listStack.pop();
                processedLines.push(itemType === 'ul' ? '<ul class="md-list">' : `<ol class="md-list" start="${num}">`);
                listStack.push({ type: itemType, indent });
            }
            processedLines.push(itemType === 'ul' ? `<li>${content}</li>` : `<li value="${num}">${content}</li>`);
        } else {
            while (listStack.length > 0) {
                const closed = listStack.pop();
                processedLines.push(listStack.length > 0 ? (closed.type === 'ul' ? '</ul></li>' : '</ol></li>') : (closed.type === 'ul' ? '</ul>' : '</ol>'));
            }
            processedLines.push(line);
        }
    }
    while (listStack.length > 0) {
        const closed = listStack.pop();
        processedLines.push(listStack.length > 0 ? (closed.type === 'ul' ? '</ul></li>' : '</ol></li>') : (closed.type === 'ul' ? '</ul>' : '</ol>'));
    }
    text = processedLines.join('\n');

    text = text.replace(/\n\n+/g, '</p><p>');
    text = text.replace(/(?<!<\/(?:h[1-6]|p|ul|ol|li|table|thead|tbody|tr|th|td|pre|div)>)\n(?!<)/g, '<br>');
    text = '<p>' + text + '</p>';
    text = text.replace(/<p>\s*<\/p>/g, '');
    text = text.replace(/<p>\s*<(ul|ol|table|h[1-6]|pre|div)/g, '<$1');
    text = text.replace(/<\/(ul|ol|table|h[1-6]|pre|div)>\s*<\/p>/g, '</$1>');

    toolBlocks.forEach((block, i) => { text = text.replace(`__TOOL_BLOCK_${i}__`, block); });
    codeBlocks.forEach((block, i) => { text = text.replace(`__CODE_BLOCK_${i}__`, block); });
    inlineCodes.forEach((code, i) => { text = text.replace(`__INLINE_CODE_${i}__`, code); });

    text = text.replace(/<p>(<div class="tool-block)/g, '$1');
    text = text.replace(/(<\/div>)<\/p>/g, '$1');
    text = text.replace(/(<br>)+(<br><div class="tool-block)/g, '$2');
    text = text.replace(/(<\/div><br>)(<br>)+/g, '$1');
    text = text.replace(/(<br>)+(<br><div class="table-container)/g, '$2');
    text = text.replace(/(<\/div><br><br>)(<br>)+/g, '$1');

    return text;
}

export function addCodeCopyButtons(messageElement) {
    const codeBlocks = messageElement.querySelectorAll('pre');

    codeBlocks.forEach(pre => {
        if (pre.querySelector('.copy-code-btn')) return;

        const button = document.createElement('button');
        button.className = 'copy-code-btn';
        button.innerHTML = '<i class="fas fa-copy"></i>';
        button.title = 'Copy code';

        button.onclick = () => {
            const code = pre.querySelector('code');
            if (code) {
                navigator.clipboard.writeText(code.textContent);
                button.innerHTML = '<i class="fas fa-check"></i>';
                setTimeout(() => {
                    button.innerHTML = '<i class="fas fa-copy"></i>';
                }, 2000);
            }
        };

        pre.appendChild(button);
    });
}

function toggleCodeDiff(event, wrapper) {
    if (event.target.closest('.tool-code-diff')) return;
    wrapper.classList.toggle('collapsed');
}

function copyToolCommand(btn) {
    const encodedCommand = btn.getAttribute('data-command');
    if (!encodedCommand) return;
    const command = decodeURIComponent(escape(atob(encodedCommand)));
    navigator.clipboard.writeText(command).then(() => {
        btn.innerHTML = '<i class="fas fa-check"></i>';
        setTimeout(() => { btn.innerHTML = '<i class="fas fa-copy"></i>'; }, 2000);
    });
}

function copyTable(btn) {
    const encodedTable = btn.getAttribute('data-table');
    if (!encodedTable) return;
    const tableMarkdown = decodeURIComponent(escape(atob(encodedTable)));
    navigator.clipboard.writeText(tableMarkdown).then(() => {
        btn.innerHTML = '<i class="fas fa-check"></i>';
        setTimeout(() => { btn.innerHTML = '<i class="fas fa-copy"></i>'; }, 2000);
    });
}

document.addEventListener('click', function(e) {
    const toolCopyBtn = e.target.closest('.tool-copy-btn');
    if (toolCopyBtn) { e.preventDefault(); e.stopPropagation(); copyToolCommand(toolCopyBtn); return; }
    const tableCopyBtn = e.target.closest('.table-copy-btn');
    if (tableCopyBtn) { e.preventDefault(); e.stopPropagation(); copyTable(tableCopyBtn); return; }
});

window.toggleCodeDiff = toggleCodeDiff;

let incrementalFormatCache = { lastInput: '', lastOutput: '', completedBlocks: 0 };

export function resetIncrementalFormatCache() {
    incrementalFormatCache = { lastInput: '', lastOutput: '', completedBlocks: 0 };
}

export function formatMessageIncremental(text) {
    if (!text) return '';
    if (text.length < incrementalFormatCache.lastInput.length) {
        incrementalFormatCache = { lastInput: '', lastOutput: '', completedBlocks: 0 };
    }
    if (text === incrementalFormatCache.lastInput) {
        return incrementalFormatCache.lastOutput;
    }
    const lines = text.split('\n');
    const hasIncompleteLastLine = !text.endsWith('\n');
    const incompleteLine = hasIncompleteLastLine ? lines.pop() : '';
    const completeText = lines.join('\n');
    let formatted = formatCompleteStructures(completeText);
    if (incompleteLine) {
        formatted += (formatted ? '<br>' : '') + escapeHtml(incompleteLine);
    }
    incrementalFormatCache.lastInput = text;
    incrementalFormatCache.lastOutput = formatted;
    return formatted;
}

function formatCompleteStructures(text) {
    if (!text) return '';
    let result = text;
    const codeBlocks = [];
    result = result.replace(/```(\w+)?\n([\s\S]*?)```/g, (match, lang, code) => {
        const idx = codeBlocks.length;
        codeBlocks.push(`<pre><code class="language-${lang || 'plaintext'}">${escapeHtml(code)}</code></pre>`);
        return `__CODEBLOCK_${idx}__`;
    });
    result = result.replace(/```(\w+)?\n([\s\S]*)$/g, (match, lang, code) => {
        const idx = codeBlocks.length;
        const langLabel = lang ? `<span class="code-lang">${lang}</span>` : '';
        codeBlocks.push(`<pre class="streaming-code">${langLabel}<code>${escapeHtml(code)}</code><span class="code-cursor">▋</span></pre>`);
        return `__CODEBLOCK_${idx}__`;
    });
    const toolBlocks = [];
    result = formatStreamingToolBlocks(result, toolBlocks);
    const inlineCodes = [];
    result = result.replace(/`([^`\n]+)`/g, (match, code) => {
        const idx = inlineCodes.length;
        inlineCodes.push(`<code>${escapeHtml(code)}</code>`);
        return `__INLINECODE_${idx}__`;
    });
    const parts = result.split(/(__CODEBLOCK_\d+__|__TOOLBLOCK_\d+__|__INLINECODE_\d+__)/);
    result = parts.map(part => {
        if (part.match(/__CODEBLOCK_\d+__|__TOOLBLOCK_\d+__|__INLINECODE_\d+__/)) return part;
        return escapeHtml(part);
    }).join('');
    result = result.replace(/^(\|.+\|)\n(\|[-:\s|]+\|)\n((?:\|.+\|\n?)+)/gm, (match, header, separator, body) => {
        try {
            const headerParts = header.split('|').slice(1, -1);
            const headerCells = headerParts.map(c => `<th align="left">${c.trim()}</th>`).join('');
            const bodyRows = body.trim().split('\n').map(row => {
                if (!row.includes('|')) return null;
                const cellParts = row.split('|').slice(1, -1);
                const cells = cellParts.map(c => `<td align="left">${c.trim()}</td>`).join('');
                return cells ? `<tr>${cells}</tr>` : null;
            }).filter(Boolean).join('');
            const encodedTable = btoa(unescape(encodeURIComponent(match.trim())));
            return `<br><div class="table-container"><table><thead><tr>${headerCells}</tr></thead><tbody>${bodyRows}</tbody></table></div><br><br>`;
        } catch (e) { return match; }
    });
    result = result.replace(/^### (.+)$/gm, '<h4>$1</h4>');
    result = result.replace(/^## (.+)$/gm, '<h3>$1</h3>');
    result = result.replace(/^# (.+)$/gm, '<h2>$1</h2>');
    result = result.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    result = result.replace(/(?<!\*)\*([^*]+)\*(?!\*)/g, '<em>$1</em>');

    result = result.replace(/^[\s]*[-•]\s+(.+)$/gm, '<li class="stream-li">$1</li>');
    result = result.replace(/^[\s]*(\d+)\.\s+(.+)$/gm, '<li class="stream-li-num">$1. $2</li>');
    result = result.replace(/\n{3,}/g, '\n\n');
    result = result.replace(/\n/g, '<br>');
    result = result.replace(/(<br>){3,}/g, '<br><br>');
    codeBlocks.forEach((block, idx) => { result = result.replace(`__CODEBLOCK_${idx}__`, block); });
    toolBlocks.forEach((block, idx) => { result = result.replace(new RegExp(`(<br>)*__TOOLBLOCK_${idx}__(<br>)*`, 'g'), block); });
    inlineCodes.forEach((code, idx) => { result = result.replace(`__INLINECODE_${idx}__`, code); });
    return result;
}

function formatStreamingToolBlocks(text, toolBlocksArray) {
    const lines = text.split('\n');
    const resultLines = [];
    let i = 0;
    while (i < lines.length) {
        const line = lines[i];
        const toolMatch = matchToolLine(line);
        if (toolMatch) {
            const { toolConfig, content: firstLine, lineRange, searchQuery } = toolMatch;
            let commandLines = [firstLine];
            let toolLineRange = lineRange;
            let toolSearchQuery = searchQuery;
            let resultLines_tool = [];
            let codeDiffLines = [];
            let hasResult = false;
            let isComplete = false;
            let hasError = false;
            let inCodeDiff = false;
            i++;
            let expectingResultContent = false;
            while (i < lines.length) {
                const nextLine = lines[i];
                const trimmed = nextLine.trim();
                if (trimmed.startsWith(TOOL_CONFIG.resultPrefix)) {
                    hasResult = true;
                    const resultContent = trimmed.substring(1).trim();
                    if (resultContent) { resultLines_tool.push(resultContent); expectingResultContent = false; }
                    else { expectingResultContent = true; }
                    if (resultContent.toLowerCase().includes('error') || resultContent.toLowerCase().includes('traceback')) hasError = true;
                    if (resultContent.toLowerCase().includes('edited') && (resultContent.toLowerCase().includes('addition') || resultContent.toLowerCase().includes('removal'))) inCodeDiff = true;
                    const lower = resultContent.toLowerCase();
                    const isEnd = TOOL_CONFIG.resultEndKeywords.some(kw => lower.includes(kw));
                    if (isEnd && !inCodeDiff) { isComplete = true; i++; break; }
                    i++;
                } else if (expectingResultContent && trimmed && !matchToolLine(nextLine)) {
                    resultLines_tool.push(trimmed);
                    expectingResultContent = false;
                    const lower = trimmed.toLowerCase();
                    if (lower.includes('error') || lower.includes('traceback')) hasError = true;
                    if (lower.includes('edited') && (lower.includes('addition') || lower.includes('removal'))) inCodeDiff = true;
                    const isEnd = TOOL_CONFIG.resultEndKeywords.some(kw => lower.includes(kw));
                    if (isEnd && !inCodeDiff) { isComplete = true; i++; break; }
                    i++;
                } else if (matchToolLine(nextLine)) { isComplete = hasResult; break; }
                else if (inCodeDiff && isCodeDiffLine(trimmed)) { codeDiffLines.push(trimmed); i++; }
                else if (trimmed === '' && hasResult) { isComplete = true; i++; break; }
                else if (!hasResult) { commandLines.push(nextLine); i++; }
                else if (inCodeDiff) { isComplete = true; break; }
                else { isComplete = true; break; }
            }
            const idx = toolBlocksArray.length;
            const html = renderStreamingToolBlock({ toolType: toolConfig.type, name: toolConfig.name, icon: toolConfig.icon, command: commandLines.join('\n').trim(), results: resultLines_tool, codeDiff: codeDiffLines, hasError: hasError, isStreaming: !isComplete, lineRange: toolLineRange, searchQuery: toolSearchQuery });
            toolBlocksArray.push(html);
            resultLines.push(`__TOOLBLOCK_${idx}__`);
            continue;
        }
        resultLines.push(line);
        i++;
    }
    return resultLines.join('\n');
}

function renderStreamingToolBlock(tool) {
    const typeClass = `tool-${tool.toolType}`;
    const errorClass = tool.hasError ? ' has-error' : '';
    const streamingClass = tool.isStreaming ? ' streaming' : '';
    let html = `<br><div class="tool-block ${typeClass}${errorClass}${streamingClass}">`;
    if (tool.lineRange) {
        const fileName = tool.command.split('/').pop();
        html += `<div class="tool-header"><i class="fas ${tool.icon}"></i> ${tool.name}</div>`;
        html += `<div class="tool-command"><code>${escapeHtml(fileName)}</code><span class="line-range">lines ${tool.lineRange.start}-${tool.lineRange.end}</span></div>`;
    } else if (tool.searchQuery) {
        const fileName = tool.command.split('/').pop();
        html += `<div class="tool-header"><i class="fas ${tool.icon}"></i> ${tool.name}</div>`;
        html += `<div class="tool-command"><code>${escapeHtml(fileName)}</code><span class="search-query"><i class="fas fa-search"></i> ${escapeHtml(tool.searchQuery)}</span></div>`;
    } else {
        html += `<div class="tool-header"><i class="fas ${tool.icon}"></i> ${tool.name}`;
        if (tool.toolType === 'terminal') {
            const encodedCommand = btoa(unescape(encodeURIComponent(tool.command)));
            html += `<button class="tool-copy-btn" data-command="${encodedCommand}" title="Copy command"><i class="fas fa-copy"></i></button>`;
        }
        html += `</div>`;
        html += `<div class="tool-command"><code>${escapeHtml(tool.command)}</code></div>`;
    }
    const filteredResults = tool.results ? tool.results.filter(r => r && r.trim()) : [];
    if (filteredResults.length > 0) {
        html += `<div class="tool-result">`;
        filteredResults.forEach(r => {
            let resultHtml = escapeHtml(r);
            if (r.toLowerCase().includes('error')) resultHtml = `<span class="result-error">${resultHtml}</span>`;
            else if (r.toLowerCase().includes('completed')) resultHtml = `<span class="result-success">${resultHtml}</span>`;
            html += `<div class="result-line"><span class="result-arrow">↳</span> ${resultHtml}</div>`;
        });
        html += `</div>`;
    }
    html += `</div>`;
    if (tool.codeDiff && tool.codeDiff.length > 0) {
        html += renderCodeDiffBlock(tool.codeDiff, tool.isStreaming);
    }
    return html + `<br>`;
}

