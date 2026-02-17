import re

_ANSI_RE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~]|\[[0-9;]*[a-zA-Z]|\][^\x07]*\x07|[PX^_][^\x1B]*\x1B\\|.)')
_EXTRA_RE = re.compile(r'\b\d+;2;\d+(?:;\d+;\d+)?\b|[34]8;5;\d+|[\u2800-\u28FF]|(?:Processing response|Sending request)\.\.\. \([^)]+\)|\([^)]*esc to interrupt[^)]*\)|[-–—]?\s*esc to interrupt', re.IGNORECASE)
_CLEAN_RE = re.compile(r'[╭╮╯╰│─╗╔║╚╝═]+|\[Claude.*?\].*?~|\? to show shortcuts.*|Ctrl\+[A-Z].*|[⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏].*?Sending request[^\n]*|[^\n]*esc to interrupt[^\n]*|›\s*$|\s*\n\s*›.*$')
_AUTOMATION_RE = re.compile(r'Use vim mode with /vim.*|For automation.*auggie.*|auggie --print.*', re.IGNORECASE)
_COPY_RE = re.compile(r'^\s*Copy\s*$', re.MULTILINE)
_NEWLINES_RE = re.compile(r'\n{3,}')


class TextCleaner:
    @staticmethod
    def strip_ansi(text):
        return _EXTRA_RE.sub('', _ANSI_RE.sub('', text))

    @staticmethod
    def clean_response(text):
        text = _CLEAN_RE.sub('', text)
        text = _AUTOMATION_RE.sub('', text)
        text = _COPY_RE.sub('', text)
        return _NEWLINES_RE.sub('\n\n', text).strip()

