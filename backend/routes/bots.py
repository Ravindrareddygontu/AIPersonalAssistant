import subprocess
import logging
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

log = logging.getLogger('bots')
bots_router = APIRouter()

SERVICES = {
    'slack': 'digistant-slack',
    'telegram': 'digistant-telegram',
    'backend': 'digistant-backend'
}


def _run_systemctl(action: str, service: str) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            ['systemctl', '--user', action, service],
            capture_output=True,
            text=True,
            timeout=10
        )
        success = result.returncode == 0
        message = result.stdout or result.stderr or f"{action} completed"
        return success, message.strip()
    except subprocess.TimeoutExpired:
        return False, "Command timed out"
    except Exception as e:
        return False, str(e)


def _get_service_status(service: str) -> dict:
    try:
        result = subprocess.run(
            ['systemctl', '--user', 'is-active', service],
            capture_output=True,
            text=True,
            timeout=5
        )
        is_active = result.stdout.strip() == 'active'
        return {'running': is_active, 'status': result.stdout.strip()}
    except Exception as e:
        return {'running': False, 'status': 'unknown', 'error': str(e)}


class BotAction(BaseModel):
    bot: str
    action: str


@bots_router.get('/api/bots/status')
async def get_bots_status():
    statuses = {}
    for bot_name, service_name in SERVICES.items():
        if bot_name == 'backend':
            continue
        statuses[bot_name] = _get_service_status(service_name)
    log.info(f"[BOTS] Status check: {statuses}")
    return statuses


@bots_router.post('/api/bots/control')
async def control_bot(data: BotAction):
    bot = data.bot.lower()
    action = data.action.lower()
    
    if action not in ['start', 'stop', 'restart']:
        return {'success': False, 'error': f'Invalid action: {action}'}
    
    if bot == 'all':
        results = {}
        for bot_name, service_name in SERVICES.items():
            if bot_name == 'backend':
                continue
            success, message = _run_systemctl(action, service_name)
            results[bot_name] = {'success': success, 'message': message}
        log.info(f"[BOTS] {action} all: {results}")
        return {'success': True, 'results': results}
    
    if bot not in SERVICES:
        return {'success': False, 'error': f'Unknown bot: {bot}'}
    
    service_name = SERVICES[bot]
    success, message = _run_systemctl(action, service_name)
    log.info(f"[BOTS] {action} {bot}: success={success}, message={message}")
    return {'success': success, 'bot': bot, 'action': action, 'message': message}

