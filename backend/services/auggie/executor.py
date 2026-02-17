"""
AuggieExecutor - Generic interface for executing commands via Auggie.

This is the core abstraction that can be used by:
- Slack bot
- CLI tools
- Webhooks
- Any other integration
"""

import os
import time
import select
import logging
from dataclasses import dataclass
from typing import Optional

from backend.session import SessionManager
from backend.utils.text import TextCleaner
from backend.utils.response import ResponseExtractor
from backend.utils.content_cleaner import ContentCleaner
from backend.services.stream_processor import StreamProcessor
from backend.models.stream_state import StreamState

log = logging.getLogger('auggie.executor')


@dataclass
class AuggieResponse:
    """Response from Auggie execution."""
    success: bool
    content: str
    error: Optional[str] = None
    execution_time: float = 0.0


class AuggieExecutor:
    """
    Concrete implementation that executes commands via PTY session.
    
    This is a non-streaming executor - it waits for the complete response
    before returning. Ideal for integrations that don't need real-time streaming.
    """
    
    # Timeouts
    MAX_EXECUTION_TIME = 300  # 5 minutes max
    SILENCE_TIMEOUT = 10.0    # No data for 10s after response = done
    DATA_SILENCE_TIMEOUT = 3.0  # No data for 3s = check completion
    PROMPT_WAIT_TIMEOUT = 60  # Wait for initial prompt
    
    def __init__(self):
        self.processor = None
    
    def execute(self, message: str, workspace: str, model: str = None) -> AuggieResponse:
        """
        Execute a message and wait for complete response.
        
        Args:
            message: The command/question to send
            workspace: Working directory for auggie
            model: Optional model override
            
        Returns:
            AuggieResponse with the result
        """
        start_time = time.time()
        workspace = os.path.expanduser(workspace)
        
        if not os.path.isdir(workspace):
            return AuggieResponse(
                success=False,
                content="",
                error=f"Workspace not found: {workspace}"
            )
        
        try:
            # Get or create session
            session, is_new = SessionManager.get_or_create(workspace, model)
            
            with session.lock:
                session.in_use = True
                try:
                    # Initialize session if needed
                    if is_new or not session.initialized:
                        session.start()
                        ready, _ = session.wait_for_prompt(self.PROMPT_WAIT_TIMEOUT)
                        if not ready:
                            return AuggieResponse(
                                success=False,
                                content="",
                                error="Failed to initialize Auggie session"
                            )
                        session.initialized = True
                    elif not session.is_alive():
                        session.cleanup()
                        session.start()
                        ready, _ = session.wait_for_prompt(self.PROMPT_WAIT_TIMEOUT)
                        if not ready:
                            return AuggieResponse(
                                success=False,
                                content="",
                                error="Failed to reconnect Auggie session"
                            )
                        session.initialized = True
                    
                    # Send message and get response
                    response = self._send_and_wait(session, message)
                    response.execution_time = time.time() - start_time
                    return response
                    
                finally:
                    session.in_use = False
                    
        except Exception as e:
            log.exception(f"Error executing message: {e}")
            return AuggieResponse(
                success=False,
                content="",
                error=str(e),
                execution_time=time.time() - start_time
            )
    
    def _sanitize_message(self, message: str) -> str:
        """Sanitize message for terminal input.

        Also strips braille spinner characters that auggie uses for status indicators.
        """
        import re
        sanitized = message.replace('\n', ' ').replace('\r', ' ')
        # Remove braille spinner characters
        sanitized = re.sub(r'[⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏⠛⠓⠚⠖⠲⠳⠞]', '', sanitized)
        return (sanitized
            .replace('●', '*')
            .replace('•', '-')
            .replace('⎿', '|')
            .replace('›', '>')
            .replace('╭', '+')
            .replace('╮', '+')
            .replace('╯', '+')
            .replace('╰', '+')
            .replace('│', '|')
            .replace('─', '-'))
    
    def _send_and_wait(self, session, message: str) -> AuggieResponse:
        """Send message and wait for complete response."""
        # Drain any pending output
        session.drain_output(timeout=0.2)

        # Send message
        sanitized = self._sanitize_message(message)
        try:
            os.write(session.master_fd, sanitized.encode('utf-8'))
            time.sleep(0.1)
            os.write(session.master_fd, b'\r')
        except (BrokenPipeError, OSError) as e:
            return AuggieResponse(success=False, content="", error=f"Write error: {e}")

        # Initialize processor and state with sanitized message (what's actually sent to terminal)
        self.processor = StreamProcessor(sanitized)
        state = StreamState(prev_response=session.last_response or "")

        fd = session.master_fd
        start_time = time.time()
        last_data_time = time.time()

        log.info(f"[EXECUTOR] Waiting for response to: {message[:50]}...")

        # Read loop - wait for complete response
        while True:
            elapsed = time.time() - start_time
            silence = time.time() - last_data_time

            # Timeout checks
            if elapsed > self.MAX_EXECUTION_TIME:
                log.warning(f"[EXECUTOR] Max execution time reached ({elapsed:.1f}s)")
                break

            # After response marker, use shorter timeout
            if state.saw_response_marker:
                # If tools are executing, use longer timeout
                if state.is_tool_executing():
                    if silence > 60.0:  # 60s timeout for tool execution
                        log.info(f"[EXECUTOR] Tool execution timeout ({silence:.1f}s)")
                        break
                    continue  # Keep waiting

                # If content looks complete and no data for a bit, we're done
                if state.content_looks_complete() and silence > self.DATA_SILENCE_TIMEOUT:
                    log.info(f"[EXECUTOR] Content complete + {silence:.1f}s silence")
                    break
                # Fallback: no data for longer period
                if silence > self.SILENCE_TIMEOUT:
                    log.info(f"[EXECUTOR] Silence timeout after response ({silence:.1f}s)")
                    break

            # Read from terminal
            ready = select.select([fd], [], [], 0.1)[0]
            if ready:
                try:
                    chunk = os.read(fd, 8192).decode('utf-8', errors='ignore')
                    if chunk:
                        state.all_output += chunk
                        last_data_time = time.time()
                except (BlockingIOError, OSError):
                    pass

            # Check for end pattern
            if state.all_output:
                clean = TextCleaner.strip_ansi(state.all_output)

                # Check message echo
                if not state.saw_message_echo:
                    msg_prefix = sanitized[:30]
                    if msg_prefix in clean:
                        state.mark_message_echo_found(clean.rfind(msg_prefix))

                # Process content
                if state.saw_message_echo:
                    self.processor.process_chunk(clean, state)

                    # Check for end pattern (empty prompt)
                    if self.processor.check_end_pattern(clean, state):
                        log.info(f"[EXECUTOR] End pattern detected")
                        break

        # Extract final response
        session.drain_output(0.3)
        clean_all = TextCleaner.strip_ansi(state.all_output)
        relevant = clean_all[state.output_start_pos:] if state.output_start_pos > 0 else clean_all

        # Use sanitized message for extraction since that's what was sent to terminal
        response_text = ResponseExtractor.extract_full(relevant, sanitized)

        # Debug logging
        log.debug(f"[EXECUTOR] state.current_full_content: {repr(state.current_full_content[:200] if state.current_full_content else None)}")
        log.debug(f"[EXECUTOR] state.last_streamed_content: {repr(state.last_streamed_content[:200] if state.last_streamed_content else None)}")
        log.debug(f"[EXECUTOR] response_text: {repr(response_text[:200] if response_text else None)}")

        # Prefer response_text if it's longer (more complete)
        content = state.current_full_content or state.last_streamed_content or ""
        if response_text and len(response_text) > len(content):
            content = response_text

        content = ContentCleaner.strip_previous_response(content, state.prev_response)
        final_content = ContentCleaner.clean_assistant_content(content)

        # Update session
        session.last_message = message
        session.last_response = final_content or ""

        if final_content:
            log.info(f"[EXECUTOR] Response complete: {len(final_content)} chars")
            return AuggieResponse(success=True, content=final_content)
        else:
            return AuggieResponse(
                success=False,
                content="",
                error="Could not extract response"
            )

