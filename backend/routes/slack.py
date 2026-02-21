import os
import re
import hmac
import hashlib
import time
import logging
from typing import Optional

from fastapi import APIRouter, Request, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel

log = logging.getLogger('slack.routes')


def _extract_summary(content: str) -> tuple[str, str | None]:
    """Extract summary from content. Returns (content_without_summary, summary)"""
    # Try with END_SUMMARY tag first - must be at start of line
    pattern = r'(?:^|\n)-{2,3}SUMMARY-{2,3}\s*(.*?)\s*-{2,3}END_SUMMARY-{2,3}'
    matches = re.findall(pattern, content, re.DOTALL)
    if matches:
        summary = matches[-1].strip()
        clean_content = re.sub(pattern, '', content, count=1, flags=re.DOTALL).strip()
        return clean_content, summary

    # Fallback: SUMMARY tag at start of line without END_SUMMARY - find last occurrence
    pattern_no_end = r'(?:^|\n)-{2,3}SUMMARY-{2,3}\s*'
    all_matches = list(re.finditer(pattern_no_end, content))
    if all_matches:
        last_match = all_matches[-1]
        summary = content[last_match.end():].strip()
        clean_content = content[:last_match.start()].strip()
        return clean_content, summary

    return content, None

slack_router = APIRouter(prefix="/api/slack", tags=["Slack"])

# Slack bot instance (initialized lazily)
_slack_bot = None


def get_slack_bot():
    global _slack_bot
    if _slack_bot is None:
        from backend.services.bots.slack import create_slack_bot
        _slack_bot = create_slack_bot()
    return _slack_bot


def verify_slack_signature(request_body: bytes, timestamp: str, signature: str) -> bool:
    signing_secret = os.environ.get('SLACK_SIGNING_SECRET', '')
    if not signing_secret:
        log.warning("[SLACK] No signing secret configured, skipping verification")
        return True  # Allow in dev mode
    
    # Check timestamp to prevent replay attacks
    if abs(time.time() - int(timestamp)) > 60 * 5:
        return False
    
    sig_basestring = f"v0:{timestamp}:{request_body.decode('utf-8')}"
    my_signature = 'v0=' + hmac.new(
        signing_secret.encode(),
        sig_basestring.encode(),
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(my_signature, signature)


class SlackEventPayload(BaseModel):
    type: str
    token: Optional[str] = None
    challenge: Optional[str] = None
    event: Optional[dict] = None
    team_id: Optional[str] = None
    api_app_id: Optional[str] = None
    event_id: Optional[str] = None
    event_time: Optional[int] = None


class SlashCommandPayload(BaseModel):
    token: str
    team_id: str
    channel_id: str
    user_id: str
    user_name: str
    command: str
    text: str
    response_url: str
    trigger_id: Optional[str] = None


@slack_router.post("/events")
async def handle_slack_events(request: Request):
    body = await request.body()
    
    # Verify request signature
    timestamp = request.headers.get('X-Slack-Request-Timestamp', '')
    signature = request.headers.get('X-Slack-Signature', '')
    
    if not verify_slack_signature(body, timestamp, signature):
        raise HTTPException(status_code=401, detail="Invalid signature")
    
    # Parse payload
    payload = await request.json()
    
    # Handle URL verification challenge
    if payload.get('type') == 'url_verification':
        return JSONResponse({'challenge': payload.get('challenge')})
    
    # Handle events
    event = payload.get('event', {})
    event_type = event.get('type')
    
    log.info(f"[SLACK] Received event: {event_type}")
    
    # Process event asynchronously to respond quickly
    if event_type == 'app_mention':
        # Handle app mention
        await _process_message_event(event, payload)
    elif event_type == 'message' and event.get('channel_type') == 'im':
        # Handle DM (but not bot's own messages)
        if not event.get('bot_id'):
            await _process_message_event(event, payload)
    
    return JSONResponse({'ok': True})


async def _process_message_event(event: dict, payload: dict):
    import re
    import urllib.request
    import json
    
    bot = get_slack_bot()
    bot._ensure_initialized()
    
    # Extract message text (remove bot mention)
    text = event.get('text', '')
    text = re.sub(r'<@[A-Z0-9]+>\s*', '', text).strip()
    
    channel = event.get('channel')
    thread_ts = event.get('thread_ts') or event.get('ts')
    
    if not text:
        return
    
    log.info(f"[SLACK] Processing: {text[:50]}...")
    
    # Send thinking indicator
    try:
        bot._app.client.chat_postMessage(
            channel=channel,
            text="⏳ Executing...",
            thread_ts=thread_ts
        )
    except Exception as e:
        log.error(f"[SLACK] Failed to send thinking message: {e}")
    
    # Execute via Auggie
    try:
        response = bot._executor.execute(
            message=text,
            workspace=bot.config.workspace,
            model=bot.config.model,
            source='bot'
        )

        if response.success:
            content = response.content or ""
            clean_content, summary = _extract_summary(content)

            if summary:
                reply = f"{summary}\n\n⏱️ _{response.execution_time:.1f}s_"
            elif len(clean_content) > 2900:
                reply = f"{clean_content[:2900]}\n\n... _(truncated)_\n\n⏱️ _{response.execution_time:.1f}s_"
            else:
                reply = f"{clean_content}\n\n⏱️ _{response.execution_time:.1f}s_"
        else:
            reply = f"❌ Error: {response.error}"

        bot._app.client.chat_postMessage(
            channel=channel,
            text=reply,
            thread_ts=thread_ts
        )

    except Exception as e:
        log.exception(f"[SLACK] Execution error: {e}")
        try:
            bot._app.client.chat_postMessage(
                channel=channel,
                text=f"❌ Error: {str(e)}",
                thread_ts=thread_ts
            )
        except:
            pass


@slack_router.post("/command")
async def handle_slash_command(request: Request, background_tasks: BackgroundTasks):
    body = await request.body()

    # Verify request signature
    timestamp = request.headers.get('X-Slack-Request-Timestamp', '')
    signature = request.headers.get('X-Slack-Signature', '')

    if not verify_slack_signature(body, timestamp, signature):
        raise HTTPException(status_code=401, detail="Invalid signature")

    # Parse form data
    from urllib.parse import parse_qs
    form_data = parse_qs(body.decode('utf-8'))

    text = form_data.get('text', [''])[0].strip()
    user_name = form_data.get('user_name', ['user'])[0]
    response_url = form_data.get('response_url', [''])[0]

    log.info(f"[SLACK] Slash command from {user_name}: {text[:50]}...")

    # Handle help/empty command immediately
    if not text or text.lower() == 'help':
        return JSONResponse({
            'response_type': 'ephemeral',
            'text': _get_help_text()
        })

    # Handle status command
    if text.lower() == 'status':
        bot = get_slack_bot()
        return JSONResponse({
            'response_type': 'ephemeral',
            'text': f"🤖 Auggie Bot is running\n📁 Workspace: `{bot.config.workspace}`"
        })

    # Process other commands in background
    background_tasks.add_task(_process_slash_command, text, response_url)

    return JSONResponse({
        'response_type': 'in_channel',
        'text': '⏳ Processing your request...'
    })


async def _process_slash_command(text: str, response_url: str):
    import urllib.request
    import json

    bot = get_slack_bot()
    bot._ensure_initialized()

    try:
        response = bot._executor.execute(
            message=text,
            workspace=bot.config.workspace,
            model=bot.config.model,
            source='bot'
        )

        if response.success:
            content = response.content
            if len(content) > 2900:
                content = content[:2900] + "\n\n... (truncated)"
            reply = f"✅ *Result:*\n{content}\n\n⏱️ _{response.execution_time:.1f}s_"
        else:
            reply = f"❌ *Error:* {response.error}"

    except Exception as e:
        log.exception(f"[SLACK] Slash command error: {e}")
        reply = f"❌ Error: {str(e)}"

    # Send response via response_url
    if response_url:
        try:
            data = json.dumps({
                'response_type': 'in_channel',
                'text': reply,
                'replace_original': True
            }).encode('utf-8')

            req = urllib.request.Request(
                response_url,
                data=data,
                headers={'Content-Type': 'application/json'}
            )
            urllib.request.urlopen(req, timeout=30)
        except Exception as e:
            log.error(f"[SLACK] Failed to send response: {e}")


def _get_help_text() -> str:
    return """🤖 *Auggie Bot - AI Code Assistant*

*Usage:*
• `/auggie <question>` - Ask Auggie anything
• `/auggie help` - Show this help
• `/auggie status` - Check bot status

*Examples:*
• `/auggie list all Python files`
• `/auggie explain the main function`
• `/auggie what does this project do?`
"""


class SendMessageRequest(BaseModel):
    message: str
    channel: Optional[str] = None  # Uses default channel if not specified


@slack_router.post("/send")
async def send_slack_message(request: SendMessageRequest):
    import json
    import urllib.request

    message = request.message
    channel = request.channel

    # Try bot token first (more flexible)
    bot_token = os.environ.get('SLACK_BOT_TOKEN')
    if bot_token and bot_token.startswith('xoxb-'):
        try:
            from slack_sdk import WebClient
            client = WebClient(token=bot_token)

            # Use provided channel or default
            target_channel = channel or os.environ.get('SLACK_CHANNEL_ID')
            if not target_channel:
                return JSONResponse({
                    'ok': False,
                    'error': 'No channel specified and SLACK_CHANNEL_ID not set'
                }, status_code=400)

            result = client.chat_postMessage(channel=target_channel, text=message)
            return JSONResponse({
                'ok': True,
                'channel': result['channel'],
                'ts': result['ts'],
                'message': 'Sent via Bot Token'
            })
        except Exception as e:
            log.error(f"[SLACK] Bot send failed: {e}")
            # Fall through to webhook

    # Fallback to webhook
    webhook_url = os.environ.get('SLACK_WEBHOOK_URL')
    if webhook_url and webhook_url.startswith('https://hooks.slack.com/'):
        try:
            data = json.dumps({'text': message}).encode('utf-8')
            req = urllib.request.Request(
                webhook_url,
                data=data,
                headers={'Content-Type': 'application/json'}
            )
            urllib.request.urlopen(req, timeout=10)
            return JSONResponse({
                'ok': True,
                'message': 'Sent via Webhook'
            })
        except Exception as e:
            log.error(f"[SLACK] Webhook send failed: {e}")
            return JSONResponse({
                'ok': False,
                'error': str(e)
            }, status_code=500)

    return JSONResponse({
        'ok': False,
        'error': 'No valid SLACK_BOT_TOKEN or SLACK_WEBHOOK_URL configured'
    }, status_code=400)


@slack_router.get("/test")
async def test_slack_connection():
    import json
    import urllib.request

    results = {
        'bot_token': False,
        'webhook': False,
        'errors': []
    }

    # Test bot token
    bot_token = os.environ.get('SLACK_BOT_TOKEN')
    if bot_token and bot_token.startswith('xoxb-'):
        try:
            from slack_sdk import WebClient
            client = WebClient(token=bot_token)
            auth = client.auth_test()
            results['bot_token'] = True
            results['bot_user'] = auth.get('user')
            results['team'] = auth.get('team')
        except Exception as e:
            results['errors'].append(f"Bot token: {str(e)}")
    else:
        results['errors'].append("Bot token: Not configured or invalid")

    # Test webhook
    webhook_url = os.environ.get('SLACK_WEBHOOK_URL')
    if webhook_url and webhook_url.startswith('https://hooks.slack.com/'):
        try:
            data = json.dumps({'text': '🔧 Test connection from AI Chat App'}).encode('utf-8')
            req = urllib.request.Request(
                webhook_url,
                data=data,
                headers={'Content-Type': 'application/json'}
            )
            urllib.request.urlopen(req, timeout=10)
            results['webhook'] = True
        except Exception as e:
            results['errors'].append(f"Webhook: {str(e)}")
    else:
        results['errors'].append("Webhook: Not configured or invalid")

    status_code = 200 if (results['bot_token'] or results['webhook']) else 400
    return JSONResponse(results, status_code=status_code)

