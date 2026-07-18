"""下载管理路由 — 队列、启动、停止、状态、SSE 流"""
import asyncio
import json

from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import StreamingResponse

from app.dependencies import (
    get_download_service, get_download_state, get_favorite_service,
)
from app.services.download_service import DownloadService, DownloadStateManager
from app.services.favorite_service import FavoriteService

router = APIRouter(prefix="/api/download", tags=["download"])


@router.get("/queue")
async def api_download_queue(
    dl_svc: DownloadService = Depends(get_download_service),
    fav_svc: FavoriteService = Depends(get_favorite_service),
):
    from app.repositories.config_repo import ConfigRepo
    cfg = ConfigRepo().read()
    if not cfg.get("token"):
        return {"items": [], "total": 0}

    result = dl_svc.get_queue()
    # 标记新增漫画
    new_ids = fav_svc.get_new_ids()
    from app.repositories.comic_repo import ComicsMetadataRepo
    comics = ComicsMetadataRepo().load_all()
    for item in result["items"]:
        idx = item["idx"] - 1
        if idx < len(comics) and comics[idx].get("_id") in new_ids:
            item["is_new"] = True
    return result


@router.post("/start")
async def api_download_start(
    data: dict,
    state_mgr: DownloadStateManager = Depends(get_download_state),
    dl_svc: DownloadService = Depends(get_download_service),
):
    if state_mgr.state.running:
        raise HTTPException(409, "下载已在运行")

    target = data.get("target", "all")
    targets = data.get("targets")  # list[int], 1-based 索引
    from app.repositories.config_repo import ConfigRepo
    cfg = ConfigRepo().read()
    if not cfg.get("token"):
        raise HTTPException(401, "请先登录")
    page_conc = int(data.get("page_concurrency", cfg.get("page_concurrency", 3)))
    chapter_conc = int(data.get("chapter_concurrency", cfg.get("chapter_concurrency", 1)))
    comic_conc = int(data.get("comic_concurrency", cfg.get("comic_concurrency", 1)))

    if targets and isinstance(targets, list) and len(targets) > 0:
        # 批量下载：前端一次性传入 1-based 索引列表，后端全程处理
        indices = [i - 1 for i in targets]  # 1-based → 0-based
        label = f"批量 {len(indices)} 部"
        await state_mgr.start(label)
        task = asyncio.create_task(
            dl_svc.run_download(indices=indices, page_concurrency=page_conc,
                                chapter_concurrency=chapter_conc, comic_concurrency=comic_conc,
                                state_mgr=state_mgr)
        )
    else:
        await state_mgr.start(target)
        task = asyncio.create_task(
            dl_svc.run_download(target=target, page_concurrency=page_conc,
                                chapter_concurrency=chapter_conc, comic_concurrency=comic_conc,
                                state_mgr=state_mgr)
        )
    state_mgr._task = task
    return {"ok": True}


@router.get("/status")
async def api_download_status(
    state_mgr: DownloadStateManager = Depends(get_download_state),
):
    return await state_mgr.get_status()


@router.post("/stop")
async def api_download_stop(
    state_mgr: DownloadStateManager = Depends(get_download_state),
):
    await state_mgr.stop()
    async with state_mgr.lock:
        state_mgr.state.progress_title = "已停止"
    return {"ok": True}


@router.post("/check")
async def api_download_check():
    from app.repositories.comic_repo import ComicsMetadataRepo, ComicsDetailRepo
    from app.repositories.download_repo import DownloadProgressRepo

    comics = ComicsMetadataRepo().load_all()
    detail_repo = ComicsDetailRepo()
    id_map = {}
    if detail_repo._base.exists():
        for d in detail_repo._base.glob("*"):
            if not d.is_dir():
                continue
            meta = detail_repo.read_metadata(d)
            if meta and meta.get("_id"):
                id_map[meta["_id"]] = d

    completed = []
    missing = []
    for idx in range(len(comics)):
        c = comics[idx]
        cid = c.get("_id", "")
        folder = id_map.get(cid)
        if not folder:
            missing.append({"idx": idx + 1, "title": c.get("title", "?"), "id": cid or f"idx_{idx}"})
            continue
        chapters = detail_repo.read_chapters(folder)
        all_done = all(
            ch.get("downloaded", 0) >= ch.get("totalPages", 1)
            for ch in chapters
        )
        if all_done and chapters:
            completed.append(cid or f"idx_{idx}")

    DownloadProgressRepo().save({
        "total": len(comics),
        "completed": completed,
    })

    return {
        "ok": True,
        "total": len(comics),
        "completed": len(completed),
        "missing": missing,
    }


@router.get("/stream")
async def api_download_stream(
    request: Request,
    state_mgr: DownloadStateManager = Depends(get_download_state),
):
    client_ip = request.client.host if request.client else "?"
    print(f"[SSE] 客户端连接: {client_ip}")

    async def event_generator():
        try:
            while True:
                if await request.is_disconnected():
                    print(f"[SSE] 客户端断开: {client_ip}")
                    break
                try:
                    msg = await asyncio.wait_for(state_mgr.log_queue.get(), timeout=1.0)
                    if msg == "__DONE__":
                        async with state_mgr.lock:
                            skips = list(state_mgr.state.skips)
                        yield f"data: {json.dumps({'type': 'done', 'skips': skips})}\n\n"
                        break
                    yield f"data: {json.dumps({'type': 'log', 'text': msg})}\n\n"
                except asyncio.TimeoutError:
                    async with state_mgr.lock:
                        running = state_mgr.state.running
                    if not running:
                        try:
                            msg = state_mgr.log_queue.get_nowait()
                            if msg == "__DONE__":
                                async with state_mgr.lock:
                                    skips = list(state_mgr.state.skips)
                                yield f"data: {json.dumps({'type': 'done', 'skips': skips})}\n\n"
                            else:
                                yield f"data: {json.dumps({'type': 'log', 'text': msg})}\n\n"
                        except asyncio.QueueEmpty:
                            pass
                        break
                    yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"
        except Exception as e:
            print(f"[SSE] 异常: {e}")
            raise

    return StreamingResponse(event_generator(), media_type="text/event-stream")
