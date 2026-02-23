import re
import json
import logging
import threading

log = logging.getLogger('chat')

_SPINNER_CHARS_RE = re.compile(r'[⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏⠛⠓⠚⠖⠲⠳⠞]')

_UNICODE_TO_ASCII_MAP = {
    '●': '*',
    '•': '-',
    '⎿': '|',
    '›': '>',
    '╭': '+',
    '╮': '+',
    '╯': '+',
    '╰': '+',
    '│': '|',
    '─': '-',
}

_abort_flag = threading.Event()


def sanitize_message(message: str) -> str:
    sanitized = message.replace('\n', ' ').replace('\r', ' ')
    sanitized = _SPINNER_CHARS_RE.sub('', sanitized)
    for unicode_char, ascii_char in _UNICODE_TO_ASCII_MAP.items():
        sanitized = sanitized.replace(unicode_char, ascii_char)
    return sanitized


def chat_log(msg: str) -> None:
    log.info(msg)
    print(f"[CHAT] {msg}", flush=True)


class SSEFormatter:
    @staticmethod
    def send(data: dict) -> str:
        return f"data: {json.dumps(data)}\n\n"

    @staticmethod
    def padding() -> str:
        return ": " + " " * 2048 + "\n\n"

