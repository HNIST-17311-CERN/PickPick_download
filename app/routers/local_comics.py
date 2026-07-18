"""本地漫画路由 — SQLite 数据库"""
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.repositories.local_repo import LocalComicRepo

router = APIRouter(prefix="/api/local", tags=["local"])


def _repo() -> LocalComicRepo:
    return LocalComicRepo()


@router.get("")
async def list_comics(page: int = 1, per_page: int = 35, category: str = "", search: str = ""):
    return await _repo().list_all(page, per_page, category, search)


@router.get("/categories")
async def get_categories():
    return {"categories": await _repo().get_categories()}


@router.get("/{comic_id}")
async def get_comic(comic_id: str):
    comic = await _repo().get(comic_id)
    if not comic:
        raise HTTPException(404, "漫画不存在")
    return comic


@router.post("/scan")
async def scan_folder(data: dict):
    """扫描文件夹导入漫画，data.path 为文件夹路径或根目录"""
    path = Path(data.get("path", ""))
    if not path.exists():
        raise HTTPException(400, "路径不存在")
    repo = _repo()
    if path.is_file():
        path = path.parent
    # 判断是单部漫画还是根目录
    subdirs = [d for d in path.iterdir() if d.is_dir()]
    has_images = any(f.suffix.lower() in (".jpg", ".png", ".jpeg") for f in path.iterdir() if f.is_file())
    if has_images or not subdirs:
        result = await repo.add(path)
        return {"ok": True, "added": 1 if result else 0}
    added = await repo.bulk_add(path)
    return {"ok": True, "added": added}


@router.put("/{comic_id}")
async def update_comic(comic_id: str, data: dict):
    ok = await _repo().update(comic_id, data)
    if not ok:
        raise HTTPException(404, "漫画不存在")
    return {"ok": True}


@router.delete("/{comic_id}")
async def delete_comic(comic_id: str):
    ok = await _repo().delete(comic_id)
    if not ok:
        raise HTTPException(404, "漫画不存在")
    return {"ok": True}


@router.get("/{comic_id}/chapters/{order}")
async def get_chapter_images(comic_id: str, order: int):
    comic = await _repo().get(comic_id)
    if not comic:
        raise HTTPException(404, "漫画不存在")
    chapter = next((ch for ch in comic.get("chapters", []) if ch["order"] == order), None)
    if not chapter:
        raise HTTPException(404, "章节不存在")

    folder = Path(comic["folder_path"]) / chapter["folder_name"]
    if not folder.is_dir():
        return {"images": [], "total": 0}

    images = sorted(
        f for f in folder.iterdir()
        if f.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp", ".gif")
    )
    return {
        "images": [{"filename": img.name, "url": f"/api/local/{comic_id}/images/{order}/{img.name}"} for img in images],
        "total": len(images),
    }


@router.get("/{comic_id}/images/{order}/{filename:path}")
async def serve_image(comic_id: str, order: int, filename: str):
    comic = await _repo().get(comic_id)
    if not comic:
        raise HTTPException(404)
    chapter = next((ch for ch in comic.get("chapters", []) if ch["order"] == order), None)
    if not chapter:
        raise HTTPException(404)
    path = Path(comic["folder_path"]) / chapter["folder_name"] / filename
    if not path.is_file():
        raise HTTPException(404)
    return FileResponse(str(path))
