"""漫画浏览路由 — 本地漫画列表、详情、章节图片、删除"""
import asyncio
from fastapi import APIRouter, HTTPException, Request, Depends

from app.dependencies import get_comic_service, get_download_state
from app.services.comic_service import ComicService
from app.services.download_service import DownloadStateManager
from app.repositories.comic_repo import DETAIL_DIR

router = APIRouter(prefix="/api/comics", tags=["comics"])


@router.get("")
async def api_comics(
    category: str = "",
    page: int = 1,
    per_page: int = 35,
    comic_svc: ComicService = Depends(get_comic_service),
):
    return await comic_svc.list_comics(category, page, per_page)


@router.get("/{folder_name}")
async def api_comic_detail(
    folder_name: str,
    comic_svc: ComicService = Depends(get_comic_service),
):
    # 先查本地
    info = await comic_svc.get_detail(folder_name)
    if info:
        return info

    # _id-xxx 或 _id/xxx → 直接用漫画 ID 从 API 获取
    if folder_name.startswith("_id-") or folder_name.startswith("_id/"):
        comic_id = folder_name[4:]
        api_info = await comic_svc.get_detail_by_id(comic_id)
        if api_info:
            return api_info

    # 未下载漫画 → 从 API 实时获取
    api_info = await comic_svc.get_api_detail(folder_name)
    if api_info:
        return api_info

    raise HTTPException(404, "漫画不存在")


@router.get("/{folder_name}/chapters/{order}")
async def api_chapter_images(
    folder_name: str,
    order: int,
    comic_svc: ComicService = Depends(get_comic_service),
):
    return await comic_svc.get_chapter_images(folder_name, order)


@router.delete("/{folder_name}")
async def api_delete_comic(
    folder_name: str,
    comic_svc: ComicService = Depends(get_comic_service),
):
    await comic_svc.delete_comic(folder_name)
    return {"ok": True}


@router.post("/batch-delete")
async def api_batch_delete(
    data: dict,
    comic_svc: ComicService = Depends(get_comic_service),
    state_mgr: DownloadStateManager = Depends(get_download_state),
):
    import shutil
    folders = data.get("folders", [])
    if not folders:
        raise HTTPException(400, "请选择要删除的漫画")
    if state_mgr.state.running:
        raise HTTPException(409, "已有任务在运行")

    await state_mgr.start("delete")
    await state_mgr.log(f"开始批量删除 {len(folders)} 部")

    async def _batch_delete():
        deleted = 0
        for i, folder_name in enumerate(folders):
            folder = DETAIL_DIR / folder_name
            if folder.is_dir():
                try:
                    shutil.rmtree(folder, ignore_errors=True)
                    deleted += 1
                    await state_mgr.log(f"已删除: {folder_name}")
                except Exception as e:
                    await state_mgr.log(f"删除失败: {folder_name} — {e}")
            async with state_mgr.lock:
                state_mgr.state.progress_done = i + 1
                state_mgr.state.progress_total = len(folders)
                state_mgr.state.progress_title = f"批量删除 {i + 1}/{len(folders)}"
        async with state_mgr.lock:
            state_mgr.state.running = False
        await state_mgr.log(f"__DONE_BATCH__ {deleted}")
        await state_mgr.log_queue.put("__DONE__")

    asyncio.create_task(_batch_delete())
    return {"ok": True}
