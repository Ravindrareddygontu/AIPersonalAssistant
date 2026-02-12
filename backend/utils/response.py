import re
from backend.config import SKIP_PATTERNS, BOX_CHARS_PATTERN
from backend.utils.text import TextCleaner

_CTRL_CHARS_RE = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')
_SECTION_RE = re.compile(r'─{10,}')
_STATUS_PATTERNS = frozenset(['Sending request', 'esc to interrupt', 'Processing response'])


class ResponseExtractor:
    @staticmethod
    def extract_full(raw_output, user_message):
        text = _CTRL_CHARS_RE.sub('', TextCleaner.strip_ansi(raw_output))
        for section in reversed([s for s in _SECTION_RE.split(text) if user_message in s and '●' in s]):
            pos = section.rfind(user_message)
            if pos < 0:
                continue
            lines, found = [], False
            for line in section[pos + len(user_message):].split('\n'):
                s = line.strip()
                if not s and not lines:
                    continue
                if found and s.startswith('╭') and '─' in s:
                    break
                if any(p in s for p in SKIP_PATTERNS):
                    continue
                if s.startswith('~'):
                    c = s[1:].strip()
                    if c:
                        lines.append(f"*{c}*")
                elif s.startswith('●'):
                    found = True
                    c = s[1:].strip()
                    if c:
                        lines.append(c)
                elif s.startswith('⎿'):
                    c = s[1:].strip()
                    if c:
                        lines.append(f"  ↳ {c}")
                elif s and s[0] not in '╭╰' and not (s.startswith('│') and ('›' in s or len(s) < 5)) and not BOX_CHARS_PATTERN.match(s):
                    lines.append(s)
            if lines and found:
                result = TextCleaner.clean_response('\n'.join(lines))
                if not (len(result.replace('\n', ' ').strip()) < 100 and any(p in result for p in _STATUS_PATTERNS)):
                    return result

        matches = list(re.finditer(r'›\s*' + re.escape(user_message), text))
        if matches:
            m = re.search(r'●\s*([^╭╰]+)', text[matches[-1].end():])
            if m:
                lines = [l.strip() for l in m.group(1).split('\n') if l.strip() and not any(p in l for p in _STATUS_PATTERNS)]
                if lines:
                    result = TextCleaner.clean_response('\n'.join(lines))
                    if not (len(result.replace('\n', ' ').strip()) < 100 and any(p in result for p in _STATUS_PATTERNS)):
                        return result
        return ""

