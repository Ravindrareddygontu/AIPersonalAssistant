import os
import re
import time
import logging
import threading
from typing import Optional, Set
from dataclasses import dataclass, field

log = logging.getLogger('slack.poller')


def _extract_summary(content: str) -> tuple[str, str | None]:
    """Extract summary from content. Returns (content_without_summary, summary)"""
    pattern = r'-{2,3}SUMMARY-{2,3}\s*(.*?)\s*-{2,3}END_SUMMARY-{2,3}'
    match = re.search(pattern, content, re.DOTALL)
    if match:
        summary = match.group(1).strip()
        clean_content = re.sub(pattern, '', content, flags=re.DOTALL).strip()
        return clean_content, summary
    return content, None


@dataclass
class SlackPoller:

    bot_token: str = None
    channel_id: str = None
    workspace: str = None
    model: str = None
    poll_interval: float = 2.0
    repository: object = None

    _processed_messages: Set[str] = field(default_factory=set)
    _running: bool = False
    _thread: Optional[threading.Thread] = None
    _client = None
    _executor = None
    _summarizer = None

    def __post_init__(self):
        self.bot_token = self.bot_token or os.environ.get('SLACK_BOT_TOKEN')
        self.channel_id = self.channel_id or os.environ.get('SLACK_CHANNEL_ID')
        self.workspace = self.workspace or os.environ.get(
            'SLACK_WORKSPACE',
            os.path.expanduser("~/Projects/POC'S/ai-chat-app")
        )
        self.model = self.model or os.environ.get('SLACK_MODEL')

    def _ensure_client(self):
        if self._client is None:
            try:
                from slack_sdk import WebClient
                self._client = WebClient(token=self.bot_token)
            except ImportError:
                raise ImportError("Run: pip install slack-sdk")

        if self._executor is None:
            from backend.services.auggie import AuggieExecutor, ResponseSummarizer
            self._executor = AuggieExecutor()
            self._summarizer = ResponseSummarizer

        if self.repository is None:
            from backend.services.slack.bot_chat_repository import BotChatRepository
            self.repository = BotChatRepository()
    
    def _get_bot_user_id(self) -> str:
        response = self._client.auth_test()
        return response['user_id']
    
    def _fetch_new_messages(self, bot_user_id: str) -> list:
        try:
            response = self._client.conversations_history(
                channel=self.channel_id,
                limit=10  # Check last 10 messages
            )
            
            messages = []
            for msg in response.get('messages', []):
                ts = msg.get('ts')
                user = msg.get('user')
                text = msg.get('text', '').strip()
                
                # Skip: already processed, bot's own messages, empty
                if ts in self._processed_messages:
                    continue
                if user == bot_user_id:
                    continue
                if not text:
                    continue
                
                messages.append({'ts': ts, 'text': text, 'user': user})
            
            return messages
            
        except Exception as e:
            log.error(f"[SLACK] Error fetching messages: {e}")
            return []
    
    def _send_reply(self, text: str, thread_ts: str = None):
        try:
            self._client.chat_postMessage(
                channel=self.channel_id,
                text=text,
                thread_ts=thread_ts
            )
        except Exception as e:
            log.error(f"[SLACK] Error sending reply: {e}")
    
    def _process_message(self, msg: dict):
        ts = msg['ts']
        text = msg['text']
        user_id = msg.get('user')

        log.info(f"[SLACK] Processing: {text[:50]}...")

        self._processed_messages.add(ts)

        chat_ctx = None
        if self.repository and user_id:
            chat_ctx = self.repository.get_or_create_chat(user_id, self.channel_id, ts)

        self._send_reply("⏳ Working on it...", thread_ts=ts)

        try:
            response = self._executor.execute(
                message=text,
                workspace=self.workspace,
                model=self.model,
                source='bot'
            )

            if response.success:
                content = response.content or ""
                clean_content, summary = _extract_summary(content)

                if not summary:
                    summary = self._summarizer.summarize(clean_content)

                self._send_reply(
                    f"{summary}\n\n⏱️ _Completed in {response.execution_time:.1f}s_",
                    thread_ts=ts
                )
                log.info(f"[SLACK] Responded: {summary[:100]}...")

                if chat_ctx:
                    self.repository.save_message(chat_ctx.chat_id, text, response.content, response.execution_time)
                    if response.session_id and response.session_id != chat_ctx.auggie_session_id:
                        self.repository.save_auggie_session_id(chat_ctx.chat_id, response.session_id)
            else:
                error_reply = f"❌ Error: {response.error}"
                self._send_reply(error_reply, thread_ts=ts)

                if chat_ctx:
                    self.repository.save_message(chat_ctx.chat_id, text, error_reply, response.execution_time)

        except Exception as e:
            log.exception(f"[SLACK] Execution error: {e}")
            self._send_reply(f"❌ Error: {str(e)}", thread_ts=ts)
    
    def _poll_loop(self):
        self._ensure_client()
        bot_user_id = self._get_bot_user_id()
        log.info(f"[SLACK] Polling started (channel: {self.channel_id}, interval: {self.poll_interval}s)")
        
        while self._running:
            messages = self._fetch_new_messages(bot_user_id)
            
            # Process oldest first
            for msg in reversed(messages):
                if self._running:
                    self._process_message(msg)
            
            time.sleep(self.poll_interval)
    
    def start(self, blocking: bool = False):
        if not self.bot_token:
            raise ValueError("Set SLACK_BOT_TOKEN environment variable")
        if not self.channel_id:
            raise ValueError("Set SLACK_CHANNEL_ID environment variable")
        
        self._running = True
        
        if blocking:
            self._poll_loop()
        else:
            self._thread = threading.Thread(target=self._poll_loop, daemon=True)
            self._thread.start()
            log.info("[SLACK] Poller started in background")
    
    def stop(self):
        self._running = False
        log.info("[SLACK] Poller stopped")

