"""相似推荐路由"""
import asyncio
import json

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.services.similar_service import SimilarService, get_sync_state

router = APIRouter(prefix="/api/similar", tags=["similar"])


@router.post("/sync")
async def api_sync():
    return await SimilarService().start_sync()


@router.get("/sync/stream")
async def api_sync_stream(request: Request):
    state = get_sync_state()

    async def event_generator():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    msg = await asyncio.wait_for(state.log_queue.get(), timeout=1.0)
                    if msg == "__DONE__":
                        yield f"data: {json.dumps({'type': 'done'})}\n\n"
                        break
                    if msg.startswith("__RESULT__"):
                        yield f"data: {json.dumps({'type': 'result', 'text': msg[10:]})}\n\n"
                        continue
                    if msg.startswith("__ERROR__"):
                        yield f"data: {json.dumps({'type': 'error', 'text': msg[9:]})}\n\n"
                        continue
                    yield f"data: {json.dumps({'type': 'log', 'text': msg})}\n\n"
                except asyncio.TimeoutError:
                    async with state.lock:
                        running = state.running
                    if not running:
                        try:
                            msg = state.log_queue.get_nowait()
                            if msg == "__DONE__":
                                yield f"data: {json.dumps({'type': 'done'})}\n\n"
                            elif msg.startswith("__RESULT__"):
                                yield f"data: {json.dumps({'type': 'result', 'text': msg[10:]})}\n\n"
                            elif msg.startswith("__ERROR__"):
                                yield f"data: {json.dumps({'type': 'error', 'text': msg[9:]})}\n\n"
                        except asyncio.QueueEmpty:
                            pass
                        break
                    yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"
        except Exception:
            pass

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/stats")
def api_stats():
    return SimilarService().get_stats()


@router.post("/clear")
def api_clear():
    from app.core.vector_store import get_vector_store
    get_vector_store().clear()
    return {"ok": True}
    return SimilarService().get_similar(folder_name, top_k)
