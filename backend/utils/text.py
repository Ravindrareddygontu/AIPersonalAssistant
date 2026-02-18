import re
from typing import Optional

# =============================================================================
# Regex Patterns for Terminal Output Cleaning
# =============================================================================

# ANSI escape sequences: CSI, OSC, DCS, PM, APC sequences and single-byte escapes
# Matches: ESC[ sequences, ESC] (OSC), ESC P/X/^/_ (DCS/PM/APC), and single char escapes
_ANSI_RE = re.compile(
    r'\x1B(?:'
    r'[@-Z\\-_]|'                     # Single-byte escape (ESC @, ESC A, etc.)
    r'\[[0-?]*[ -/]*[@-~]|'           # CSI sequences (ESC [ ... final)
    r'\[[0-9;]*[a-zA-Z]|'             # CSI with parameters (ESC [ n;m H)
    r'\][^\x07]*\x07|'                # OSC sequences ending with BEL
    r'[PX^_][^\x1B]*\x1B\\'           # DCS/PM/APC terminated by ST
    r'|.)'                            # Single char after ESC
)

# Extra terminal artifacts: RGB color codes, Braille chars, status messages
# Matches: 256-color/truecolor codes (38;2;R;G;B), Braille pattern chars, status text
_EXTRA_RE = re.compile(
    r'\b\d+;2;\d+(?:;\d+;\d+)?\b|'    # Truecolor: 38;2;R;G;B or 48;2;R;G;B
    r'[34]8;5;\d+|'                   # 256-color: 38;5;N or 48;5;N
    r'[\u2800-\u28FF]|'               # Braille pattern characters (⠀-⣿)
    r'(?:Processing response|Sending request)\.\.\. \([^)]+\)|'  # Status with timing
    r'\([^)]*esc to interrupt[^)]*\)|'  # Interrupt hint in parens
    r'[-–—]?\s*esc to interrupt',     # Interrupt hint standalone
    re.IGNORECASE
)

# UI elements to remove: box chars, model tags, shortcuts, spinner + status lines
_CLEAN_RE = re.compile(
    r'[╭╮╯╰│─╗╔║╚╝═]+|'               # Box drawing characters
    r'\[Claude.*?\].*?~|'             # Model tag like [Claude 4] ...
    r'\? to show shortcuts.*|'         # Shortcut hint
    r'Ctrl\+[A-Z].*|'                  # Keyboard shortcuts
    r'[⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏].*?Sending request[^\n]*|'  # Spinner + sending status
    r'[^\n]*esc to interrupt[^\n]*|'   # Lines with interrupt hint
    r'›\s*$|'                          # Trailing prompt character
    r'\s*\n\s*›.*$'                    # Lines starting with prompt
)

# Automation/vim mode hints that shouldn't appear in responses
_AUTOMATION_RE = re.compile(
    r'Use vim mode with /vim.*|'
    r'For automation.*auggie.*|'
    r'auggie --print.*',
    re.IGNORECASE
)

# Standalone "Copy" button text from terminal UI
_COPY_RE = re.compile(r'^\s*Copy\s*$', re.MULTILINE)

# Collapse excessive newlines (3+ → 2)
_NEWLINES_RE = re.compile(r'\n{3,}')


class TextCleaner:

    @staticmethod
    def strip_ansi(text: str) -> str:
        return _EXTRA_RE.sub('', _ANSI_RE.sub('', text))

    @staticmethod
    def clean_response(text: str) -> str:
        text = _CLEAN_RE.sub('', text)
        text = _AUTOMATION_RE.sub('', text)
        text = _COPY_RE.sub('', text)
        return _NEWLINES_RE.sub('\n\n', text).strip()

