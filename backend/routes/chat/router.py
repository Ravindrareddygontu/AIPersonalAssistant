import os
import logging

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse, JSONResponse
from typing import Optional

from backend.config import settings, TERMINAL_AGENT_PROVIDERS
from backend.session import SessionManager
from backend.database import get_chats_collection

from .models import ChatStreamRequest, ChatResetRequest
from .utils import _abort_flag
from .auggie_generator import AuggieStreamGenerator
from .openai_generator import OpenAIStreamGenerator
from .terminal_generator import TerminalAgentStreamGenerator

log = logging.getLogger('chat')
chat_router = APIRouter()


@chat_router.post('/api/chat/stream')
async def chat_stream(request: Request, data: ChatStreamRequest):
    _abort_flag.clear()

    message = data.message
    workspace = data.workspace or settings.workspace
    chat_id = data.chatId

    provider = data.provider or settings.ai_provider
    if chat_id:
        try:
            chats_collection = get_chats_collection()
            if chats_collection is not None:
                chat_doc = chats_collection.find_one({'id': chat_id})
                if chat_doc:
                    if data.provider:
                        provider = data.provider
                        chats_collection.update_one(
                            {'id': chat_id},
                            {'$set': {'provider': provider}}
                        )
                        log.debug(f"[PROVIDER] Using request provider: {provider}")
                    elif chat_doc.get('provider'):
                        provider = chat_doc['provider']
                        log.debug(f"[PROVIDER] Using chat's stored provider: {provider}")
                    else:
                        chats_collection.update_one(
                            {'id': chat_id},
                            {'$set': {'provider': provider}}
                        )
                        log.info(f"[PROVIDER] Stored provider '{provider}' for chat {chat_id}")
        except Exception as e:
            log.warning(f"[PROVIDER] Failed to get/set chat provider, using global: {e}")

    log.info(f"[REQUEST] POST /api/chat/stream | provider: {provider} | chat: {chat_id} | message: '{message[:100]}...'")

    if provider == 'openai':
        generator = OpenAIStreamGenerator(message, chat_id=chat_id, history=data.history)

        async def openai_stream():
            async for chunk in generator.generate():
                if await request.is_disconnected():
                    log.warning("[OPENAI] Client disconnected")
                    return
                yield chunk

        log.info("[RESPONSE] POST /api/chat/stream | Status: 200 | OpenAI SSE stream initiated")

        return StreamingResponse(
            openai_stream(),
            media_type='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'X-Accel-Buffering': 'no',
                'Connection': 'keep-alive'
            }
        )

    if provider in TERMINAL_AGENT_PROVIDERS and provider != 'auggie':
        from backend.services.terminal_agent.registry import TerminalAgentRegistry
        terminal_provider = TerminalAgentRegistry.get(provider)
        provider_model = terminal_provider.config.default_model if terminal_provider else settings.model
        generator = TerminalAgentStreamGenerator(
            provider_name=provider,
            message=message,
            workspace=os.path.expanduser(workspace),
            chat_id=chat_id,
            model=provider_model
        )

        def terminal_agent_stream():
            for chunk in generator.generate():
                yield chunk

        log.info(f"[RESPONSE] POST /api/chat/stream | Status: 200 | {provider.title()} SSE stream initiated")

        return StreamingResponse(
            terminal_agent_stream(),
            media_type='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'X-Accel-Buffering': 'no',
                'Connection': 'keep-alive'
            }
        )

    generator = AuggieStreamGenerator(message, os.path.expanduser(workspace), chat_id=chat_id)

    async def stream_generator():
        gen = generator.generate()
        try:
            for chunk in gen:
                if await request.is_disconnected():
                    log.warning("[STREAM] Client disconnected, calling cleanup")
                    generator._continue_in_background()
                    return
                yield chunk
        except GeneratorExit:
            log.warning("[STREAM] GeneratorExit caught, client disconnected")
            generator._continue_in_background()
        finally:
            try:
                gen.close()
            except:
                pass

    log.info("[RESPONSE] POST /api/chat/stream | Status: 200 | Auggie SSE stream initiated")

    return StreamingResponse(
        stream_generator(),
        media_type='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
            'Connection': 'keep-alive'
        }
    )


@chat_router.post('/api/chat/abort')
async def chat_abort():
    log.info("[REQUEST] POST /api/chat/abort")
    _abort_flag.set()
    response_data = {'status': 'ok', 'message': 'Abort signal sent'}
    log.info(f"[RESPONSE] POST /api/chat/abort | Status: 200 | {response_data}")
    return response_data


@chat_router.post('/api/chat/reset')
async def chat_reset(data: Optional[ChatResetRequest] = None):
    workspace = data.workspace if data and data.workspace else settings.workspace
    workspace = os.path.expanduser(workspace)
    provider_name = data.provider if data and data.provider else None

    log.info(f"[REQUEST] POST /api/chat/reset | workspace: '{workspace}' | provider: '{provider_name}'")

    reset_success = SessionManager.reset(workspace)

    if provider_name:
        from backend.services.terminal_agent.registry import TerminalAgentRegistry
        provider = TerminalAgentRegistry.get(provider_name)
        if provider and hasattr(provider, 'clear_session'):
            provider.clear_session(workspace)
            log.info(f"[RESET] Cleared {provider_name} session for workspace: {workspace}")

    if not reset_success:
        response_data = {'status': 'error', 'message': 'Cannot reset: terminal is currently in use'}
        log.info(f"[RESPONSE] POST /api/chat/reset | Status: 409 | {response_data}")
        return JSONResponse(content=response_data, status_code=409)

    response_data = {'status': 'ok', 'message': 'Session reset successfully'}
    log.info(f"[RESPONSE] POST /api/chat/reset | Status: 200 | {response_data}")
    return response_data

