"""
SlackBot - Slack integration for remote command execution via Auggie.

Uses Socket Mode for local development (no public URL needed).
Completely isolated from frontend code.

Setup:
1. Create a Slack app at https://api.slack.com/apps
2. Enable Socket Mode
3. Add Bot Token Scopes: chat:write, app_mentions:read, im:history, im:read, im:write
4. Install to workspace
5. Set environment variables: SLACK_BOT_TOKEN, SLACK_APP_TOKEN
"""

import os
import logging
import threading
from typing import Optional, Callable

log = logging.getLogger('slack.bot')


class SlackBot:
    """
    Slack bot that executes commands via Auggie and reports summaries.
    
    This is completely isolated from the frontend - it uses the generic
    AuggieExecutor interface for all AI interactions.
    """
    
    def __init__(
        self,
        bot_token: str = None,
        app_token: str = None,
        workspace: str = None,
        model: str = None
    ):
        """
        Initialize SlackBot.
        
        Args:
            bot_token: Slack Bot Token (xoxb-...)
            app_token: Slack App Token for Socket Mode (xapp-...)
            workspace: Default workspace directory
            model: Default AI model to use
        """
        self.bot_token = bot_token or os.environ.get('SLACK_BOT_TOKEN')
        self.app_token = app_token or os.environ.get('SLACK_APP_TOKEN')
        self.workspace = workspace or os.environ.get('SLACK_WORKSPACE', os.path.expanduser('~'))
        self.model = model or os.environ.get('SLACK_MODEL')
        
        self._app = None
        self._handler = None
        self._thread = None
        self._running = False
        
        # Lazy import to avoid dependency issues if slack_bolt not installed
        self._slack_bolt = None
        self._slack_sdk = None
    
    def _ensure_dependencies(self):
        """Ensure Slack dependencies are installed."""
        if self._slack_bolt is None:
            try:
                from slack_bolt import App
                from slack_bolt.adapter.socket_mode import SocketModeHandler
                from slack_sdk import WebClient
                self._slack_bolt = {'App': App, 'SocketModeHandler': SocketModeHandler}
                self._slack_sdk = {'WebClient': WebClient}
            except ImportError:
                raise ImportError(
                    "Slack dependencies not installed. Run: pip install slack-bolt slack-sdk"
                )
    
    def _create_app(self):
        """Create and configure the Slack app."""
        self._ensure_dependencies()
        
        App = self._slack_bolt['App']
        self._app = App(token=self.bot_token)
        
        # Import executor here to avoid circular imports
        from backend.services.auggie import AuggieExecutor, ResponseSummarizer
        self._executor = AuggieExecutor()
        self._summarizer = ResponseSummarizer
        
        # Register event handlers
        @self._app.event("message")
        def handle_message(event, say, client):
            self._handle_message(event, say, client)
        
        @self._app.event("app_mention")
        def handle_mention(event, say, client):
            self._handle_message(event, say, client)
        
        log.info("[SLACK] App created and handlers registered")
    
    def _handle_message(self, event: dict, say: Callable, client):
        """Handle incoming Slack message."""
        # Ignore bot messages to prevent loops
        if event.get('bot_id') or event.get('subtype') == 'bot_message':
            return
        
        text = event.get('text', '').strip()
        user = event.get('user')
        channel = event.get('channel')
        
        if not text:
            return
        
        log.info(f"[SLACK] Received from {user} in {channel}: {text[:50]}...")
        
        # Send acknowledgment
        say("⏳ Working on it...", thread_ts=event.get('ts'))
        
        # Execute via Auggie
        try:
            response = self._executor.execute(
                message=text,
                workspace=self.workspace,
                model=self.model
            )
            
            if response.success:
                # Generate summary
                summary = self._summarizer.summarize(response.content)
                
                # Send summary
                say(
                    f"{summary}\n\n⏱️ _Completed in {response.execution_time:.1f}s_",
                    thread_ts=event.get('ts')
                )
                log.info(f"[SLACK] Response sent: {summary[:100]}...")
            else:
                say(
                    f"❌ Error: {response.error or 'Unknown error'}",
                    thread_ts=event.get('ts')
                )
                log.error(f"[SLACK] Execution failed: {response.error}")
                
        except Exception as e:
            log.exception(f"[SLACK] Error handling message: {e}")
            say(f"❌ Error: {str(e)}", thread_ts=event.get('ts'))
    
    def start(self, blocking: bool = False):
        """
        Start the Slack bot.
        
        Args:
            blocking: If True, blocks the current thread. If False, runs in background.
        """
        if not self.bot_token or not self.app_token:
            raise ValueError(
                "Missing Slack tokens. Set SLACK_BOT_TOKEN and SLACK_APP_TOKEN environment variables."
            )
        
        self._create_app()
        
        SocketModeHandler = self._slack_bolt['SocketModeHandler']
        self._handler = SocketModeHandler(self._app, self.app_token)
        
        self._running = True
        log.info(f"[SLACK] Starting bot (workspace: {self.workspace})")
        
        if blocking:
            self._handler.start()
        else:
            self._thread = threading.Thread(target=self._handler.start, daemon=True)
            self._thread.start()
            log.info("[SLACK] Bot started in background thread")
    
    def stop(self):
        """Stop the Slack bot."""
        self._running = False
        if self._handler:
            try:
                self._handler.close()
            except:
                pass
        log.info("[SLACK] Bot stopped")
    
    @property
    def is_running(self) -> bool:
        return self._running

