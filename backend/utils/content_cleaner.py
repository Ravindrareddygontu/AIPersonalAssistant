import re


class ContentCleaner:

    BOX_CHARS = '─│╭╮╰╯┌┐└┘├┤┬┴┼'
    BOX_CHARS = '─│╭╮╰╯┌┐└┘├┤┬┴┼'

    @classmethod
    def clean_assistant_content(cls, content: str) -> str:
        if not content:
            return content

        lines = content.split('\n')
        cleaned_lines = []

        for line in lines:
            stripped = line.strip()

            # Stop at prompt artifacts (marks end of AI response)
            if cls._is_prompt_line(stripped):
                break

            # Stop at path-like lines (terminal prompt showing directory)
            if cls._is_path_line(stripped):
                break

            # Skip empty box lines
            if cls._is_empty_box_line(line):
                continue

            # Skip lines that are ONLY box drawing characters
            if cls._is_box_only_line(stripped):
                continue

            # Skip garbage escape code remnants
            if cls._is_garbage_line(stripped):
                continue

            # Clean partial escape sequences (e.g., [2K, [1A) from mid-line
            line = cls._clean_partial_escapes(line)

            # Clean trailing garbage characters
            stripped = line.strip()  # Re-strip after escape removal
            line = cls._clean_trailing_garbage(line, stripped)
            cleaned_lines.append(line)

        result = '\n'.join(cleaned_lines).rstrip()
        # Final cleanup: remove trailing semicolons followed by numbers (escape code remnants)
        # Only strip if it looks like escape code garbage: ends with ;NN pattern
        result = re.sub(r';[0-9]+$', '', result)
        return result

    @classmethod
    def _is_prompt_line(cls, stripped: str) -> bool:
        if stripped.startswith('›'):
            return True
        if stripped == '│' or stripped.startswith('│ ›'):
            return True
        return False

    @classmethod
    def _is_path_line(cls, stripped: str) -> bool:
        if not stripped.startswith('/'):
            return False
        if '/' not in stripped[1:]:
            return False
        if len(stripped) >= 100:
            return False

        # If it ends with shell prompt characters, it's a terminal prompt
        if stripped.rstrip().endswith(('$', '%', '#', '>')):
            return True

        # If there's text after the path (space + more content), it's valid content
        # A bare path has no spaces, or only trailing spaces
        parts = stripped.split()
        if len(parts) > 1:
            # Has content after path - likely valid content, not a prompt
            return False

        # Bare path only - likely terminal prompt
        return True

    @classmethod
    def _is_empty_box_line(cls, line: str) -> bool:
        return '│                                                                          │' in line

    @classmethod
    def _is_box_only_line(cls, stripped: str) -> bool:
        return stripped and all(c in cls.BOX_CHARS for c in stripped)

    # Terminal UI garbage patterns (escape code remnants, status area artifacts)
    _GARBAGE_PATTERNS = re.compile(
        r'^(?:'
        r'[;0-9]{1,5}|'              # Escape code number remnants (;38, 255, etc)
        r'SA|'                        # Scroll/Status Area remnants from Auggie UI
        r'[A-Z]{1,2}|'                # Single/double uppercase (cursor codes: A, H, K, SA, etc)
        r'[0-9]+;[0-9]+|'             # Coordinate remnants (row;col)
        r'm|'                         # SGR terminator remnant
        r'\?[0-9]+[hl]'               # DEC mode remnants (?25h, ?25l)
        r')$'
    )

    # Partial escape sequence remnants that appear mid-line when chunks split
    # Matches patterns like: [2K, [1A, [?25h, [0m, [38;2;...m etc
    _PARTIAL_ESCAPE_RE = re.compile(
        r'\[(?:'
        r'[0-9;]*[A-Za-z]|'           # CSI sequences: [2K, [1A, [0m, [38;2;255;255;255m
        r'\?[0-9]+[hl]'               # DEC mode: [?25h, [?25l
        r')'
    )

    @classmethod
    def _is_garbage_line(cls, stripped: str) -> bool:
        if not stripped:
            return False
        if len(stripped) <= 5 and stripped.lstrip(';').isdigit():
            return True
        if cls._GARBAGE_PATTERNS.match(stripped):
            return True
        return False

    @classmethod
    def _clean_partial_escapes(cls, line: str) -> str:
        return cls._PARTIAL_ESCAPE_RE.sub('', line)

    @classmethod
    def _clean_trailing_garbage(cls, line: str, stripped: str) -> str:
        if stripped.endswith(';'):
            return line.rstrip(';0123456789')
        if (len(stripped) > 2 and 
            stripped[-1].isdigit() and 
            stripped[-2].isdigit() and 
            stripped[-3] in ';│'):
            return line.rstrip(';0123456789')
        return line

    @classmethod
    def strip_previous_response(cls, content: str, previous_response: str) -> str:
        if previous_response and content and content.startswith(previous_response):
            return content[len(previous_response):].lstrip('\n')
        return content

