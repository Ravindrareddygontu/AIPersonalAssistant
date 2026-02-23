import json
import logging
import asyncio
from typing import Optional

from fastapi import APIRouter
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel

from backend.config import DEFAULT_WORKSPACE_PATH

log = logging.getLogger('debate')
debate_router = APIRouter()


class DebateRequest(BaseModel):
    topic: str
    workspace: Optional[str] = None
    rounds: Optional[int] = 2
    with_moderator: Optional[bool] = True


@debate_router.post("/debate/start")
async def start_debate(request: DebateRequest):
    workspace = request.workspace or DEFAULT_WORKSPACE_PATH

    async def generate():
        try:
            from backend.services.multi_agent import MultiAgentOrchestrator, AgentRole

            orchestrator = MultiAgentOrchestrator(
                workspace=workspace,
                model=None
            )

            yield f"data: {json.dumps({'type': 'status', 'message': 'Starting debate...'})}\n\n"

            messages_queue = asyncio.Queue()
            debate_complete = asyncio.Event()

            def on_message(msg):
                asyncio.get_event_loop().call_soon_threadsafe(
                    messages_queue.put_nowait,
                    {
                        'type': 'message',
                        'agent': msg.agent_name,
                        'content': msg.content,
                        'role': msg.role.value
                    }
                )

            loop = asyncio.get_event_loop()

            def run_debate():
                try:
                    result = orchestrator.run_debate(
                        topic=request.topic,
                        rounds=request.rounds,
                        with_moderator=request.with_moderator,
                        on_message=on_message
                    )
                    loop.call_soon_threadsafe(
                        messages_queue.put_nowait,
                        {
                            'type': 'complete',
                            'total_time': result.total_time,
                            'rounds': result.rounds_completed,
                            'summary': result.summary
                        }
                    )
                except Exception as e:
                    loop.call_soon_threadsafe(
                        messages_queue.put_nowait,
                        {'type': 'error', 'message': str(e)}
                    )
                finally:
                    loop.call_soon_threadsafe(debate_complete.set)

            import threading
            thread = threading.Thread(target=run_debate, daemon=True)
            thread.start()

            while not debate_complete.is_set() or not messages_queue.empty():
                try:
                    msg = await asyncio.wait_for(messages_queue.get(), timeout=0.5)
                    yield f"data: {json.dumps(msg)}\n\n"
                except asyncio.TimeoutError:
                    continue

            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        except Exception as e:
            log.exception(f"Debate error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@debate_router.get("/debate/status")
async def debate_status():
    return JSONResponse({"status": "ready", "available": True})

