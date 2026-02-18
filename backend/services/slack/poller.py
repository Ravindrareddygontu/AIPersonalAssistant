import os
import time
import logging
import threading
from typing import Optional, Set
from dataclasses import dataclass, field

log = logging.getLogger('slack.poller')


@dataclass
class SlackPoller:

    bot_token: str = None
    channel_id: str = None  # DM channel with the bot
    workspace: str = None
    model: str = None
    poll_interval: float = 2.0  # seconds
    
    # Internal state
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
        
        log.info(f"[SLACK] Processing: {text[:50]}...")
        
        # Mark as processed immediately to avoid duplicates
        self._processed_messages.add(ts)
        
        # Send acknowledgment
        self._send_reply("⏳ Working on it...", thread_ts=ts)
        
        # Execute via Auggie
        try:
            response = self._executor.execute(
                message=text,
                workspace=self.workspace,
                model=self.model
            )
            
            if response.success:
                summary = self._summarizer.summarize(response.content)
                self._send_reply(
                    f"{summary}\n\n⏱️ _Completed in {response.execution_time:.1f}s_",
                    thread_ts=ts
                )
                log.info(f"[SLACK] Responded: {summary[:100]}...")
            else:
                self._send_reply(f"❌ Error: {response.error}", thread_ts=ts)
                
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

