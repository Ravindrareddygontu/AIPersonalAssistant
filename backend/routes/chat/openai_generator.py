import time
import logging
from typing import List

from backend.config import settings
from backend.services.chat_repository import ChatRepository
from backend.ai_middleware.providers.openai.chat import OpenAIChatProvider
from backend.ai_middleware.models.chat import ChatMessage, MessageRole
from backend.ai_middleware.config import get_settings as get_middleware_settings
from backend.services.bots.slack.notifier import notify_completion

from .utils import SSEFormatter, _abort_flag

log = logging.getLogger('chat')


class OpenAIStreamGenerator:

    def __init__(self, message: str, chat_id: str = None, history: List[dict] = None):
        self.message = message
        self.chat_id = chat_id
        self.history = history or []
        self.start_time = time.time()
        self.repository = ChatRepository(chat_id) if (chat_id and settings.history_enabled) else None
        self.sse = SSEFormatter()
        self._provider = None

    def _get_provider(self) -> OpenAIChatProvider:
        if self._provider is None:
            middleware_settings = get_middleware_settings()
            if not middleware_settings.openai_api_key:
                raise ValueError("OpenAI API key not configured. Set OPENAI_API_KEY in environment.")
            self._provider = OpenAIChatProvider(api_key=middleware_settings.openai_api_key)
        return self._provider

    SYSTEM_PROMPT = """You are a helpful AI assistant. Format responses using markdown:

**Structure:**
- Use ## for section headers (renders as h3)
- Use bullet points (-) for unordered lists
- Use numbered lists (1. 2. 3.) for sequential steps
- Keep paragraphs short with blank lines between them

**Code:**
- Use ```language for code blocks (python, javascript, bash, etc.)
- Use `backticks` for inline code, commands, filenames

**Emphasis:**
- Use **bold** for key terms and important info
- Use *italic* sparingly for emphasis

**Tables:** Use markdown tables for structured data comparison

Keep responses concise, well-organized, and easy to scan. Do not use more than two consecutive line breaks."""

    def _build_messages(self) -> List[ChatMessage]:
        messages = [ChatMessage(role=MessageRole.SYSTEM, content=self.SYSTEM_PROMPT)]
        for msg in self.history:
            role_str = msg.get('role', 'user')
            try:
                role = MessageRole(role_str)
            except ValueError:
                role = MessageRole.USER if role_str == 'user' else MessageRole.ASSISTANT
            messages.append(ChatMessage(role=role, content=msg.get('content', '')))
        messages.append(ChatMessage(role=MessageRole.USER, content=self.message))
        return messages

    async def generate(self):
        model = settings.openai_model
        log.info(f"[OPENAI] Starting stream for model: {model}")

        if self.repository:
            self.repository.set_streaming_status('streaming')

        yield self.sse.padding()
        yield self.sse.send({'type': 'status', 'message': f'Connecting to OpenAI ({model})...'})
        yield self.sse.send({'type': 'stream_start'})

        full_content = ""
        try:
            provider = self._get_provider()
            messages = self._build_messages()

            async for chunk in provider.chat_stream(messages=messages, model=model):
                if _abort_flag.is_set():
                    log.info("[OPENAI] Abort signal received")
                    _abort_flag.clear()
                    if self.repository:
                        self.repository.set_streaming_status(None)
                    yield self.sse.send({'type': 'aborted', 'message': 'Request aborted'})
                    yield self.sse.send({'type': 'done'})
                    return
                for choice in chunk.choices:
                    if choice.delta.content:
                        content = choice.delta.content
                        full_content += content
                        yield self.sse.send({'type': 'stream', 'content': content})
                    if choice.finish_reason:
                        log.info(f"[OPENAI] Stream finished: {choice.finish_reason}")

            if self.repository:
                message_id = self.repository.save_question(self.message)
                if message_id:
                    self.repository.save_answer(message_id, full_content)
                self.repository.set_streaming_status(None)

            execution_time = time.time() - self.start_time
            notify_completion(
                question=self.message,
                content=full_content,
                success=True,
                error=None,
                stopped=False,
                execution_time=execution_time
            )

            yield self.sse.send({'type': 'stream_end', 'content': full_content})
            yield self.sse.send({'type': 'response', 'message': full_content})
            yield self.sse.send({'type': 'done'})

        except Exception as e:
            log.error(f"[OPENAI] Streaming error: {e}")
            if self.repository:
                self.repository.set_streaming_status(None)
            execution_time = time.time() - self.start_time
            notify_completion(
                question=self.message,
                content="",
                success=False,
                error=str(e),
                stopped=False,
                execution_time=execution_time
            )
            yield self.sse.send({'type': 'error', 'message': str(e)})
            yield self.sse.send({'type': 'done'})

