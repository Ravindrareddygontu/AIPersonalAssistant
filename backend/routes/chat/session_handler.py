import os
import time
import queue
import logging
import threading

from backend.session.auggie import SessionManager
from .utils import SSEFormatter, sanitize_message

log = logging.getLogger('chat')


class SessionHandler:
    def __init__(self, workspace: str, model: str, session_id: str = None, force_new: bool = False):
        self.workspace = workspace if os.path.isdir(workspace) else os.path.expanduser('~')
        self.model = model
        self.session_id = session_id
        self.force_new = force_new
        self._status_queue = []

    def get_session(self):
        return SessionManager.get_or_create(self.workspace, self.model, self.session_id, self.force_new)

    def _status_callback(self, message: str):
        self._status_queue.append(message)

    def start_session(self, session, status_msg: str):
        yield SSEFormatter.send({'type': 'status', 'message': status_msg})
        session.start()
        yield SSEFormatter.send({'type': 'status', 'message': 'Initializing Augment...'})

        self._status_queue = []

        status_q = queue.Queue()
        result_holder = {'success': False, 'output': ''}

        def callback(msg):
            status_q.put(msg)

        def wait_thread():
            success, output = session.wait_for_prompt(status_callback=callback)
            result_holder['success'] = success
            result_holder['output'] = output
            status_q.put(None)

        thread = threading.Thread(target=wait_thread, daemon=True)
        thread.start()

        while True:
            try:
                msg = status_q.get(timeout=0.5)
                if msg is None:
                    break
                yield SSEFormatter.send({'type': 'status', 'message': msg})
            except queue.Empty:
                pass

        thread.join(timeout=5)

        if not result_holder['success']:
            session.cleanup()
            yield SSEFormatter.send({'type': 'error', 'message': 'Failed to start Augment'})
            return False

        session.initialized = True
        return True

    def send_message(self, session, message: str):
        try:
            drained = session.drain_output(timeout=0.1)
            if drained > 0:
                log.info(f"Drained {drained} bytes before sending")

            if message.startswith('/images '):
                return self._send_image_message(session, message)

            sanitized_message = sanitize_message(message)

            os.write(session.master_fd, sanitized_message.encode('utf-8'))
            time.sleep(0.1)
            os.write(session.master_fd, b'\r')
            time.sleep(0.05)
            log.info(f"Message sent: {sanitized_message[:30]}...")
            return (True, message)
        except (BrokenPipeError, OSError) as e:
            log.error(f"Write error: {e}")
            session.cleanup()
            return (False, message)

    def _send_image_message(self, session, message: str):
        log.info(f"[IMAGE] ========== _send_image_message CALLED ==========")
        log.info(f"[IMAGE] Full message: {message[:100]}...")
        try:
            parts = message[8:].strip()

            if '|||' in parts:
                image_path, question = parts.split('|||', 1)
                image_path = image_path.strip()
                question = question.strip()
            else:
                image_path = parts
                question = ''

            if not image_path:
                log.warning("No image path found in /images command, sending as regular message")
                success = self._send_regular_message(session, message)
                return (success, message)

            log.info(f"[IMAGE] Sending image: {image_path}")
            log.info(f"[IMAGE] Question: {question[:50] if question else '(none)'}...")

            os.write(session.master_fd, b'/image')
            time.sleep(0.5)
            os.write(session.master_fd, b'\r')
            time.sleep(2.0)
            drained1 = session.drain_output(timeout=0.5)
            log.info(f"[IMAGE] After /image command, drained {drained1} bytes")

            log.info(f"[IMAGE] Now sending path: {image_path}")
            os.write(session.master_fd, image_path.encode('utf-8'))
            time.sleep(0.3)
            os.write(session.master_fd, b'\r')
            time.sleep(2.0)
            drained2 = session.drain_output(timeout=0.5)
            log.info(f"[IMAGE] After path, drained {drained2} bytes")

            if question:
                sanitized_question = sanitize_message(question)
                os.write(session.master_fd, sanitized_question.encode('utf-8'))
                time.sleep(0.1)
                os.write(session.master_fd, b'\r')
                time.sleep(0.1)
                log.info(f"[IMAGE] Sent question: {sanitized_question[:50]}...")
            else:
                log.warning("[IMAGE] No question provided with image")

            return (True, question if question else image_path)

        except (BrokenPipeError, OSError) as e:
            log.error(f"Write error during image send: {e}")
            session.cleanup()
            return (False, message)

    def _send_regular_message(self, session, message: str) -> bool:
        sanitized_message = sanitize_message(message)
        os.write(session.master_fd, sanitized_message.encode('utf-8'))
        time.sleep(0.1)
        os.write(session.master_fd, b'\r')
        time.sleep(0.05)
        log.info(f"Message sent: {sanitized_message[:30]}...")
        return True

