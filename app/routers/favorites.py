"""收藏路由"""
from fastapi import APIRouter, HTTPException, Depends, Query, Body

from app.dependencies import get_favorite_service, get_comic_service
from app.services.favorite_service import FavoriteService
from app.services.comic_service import ComicService

router = APIRouter(prefix="/api", tags=["favorites"])


@router.get("/favorites")
async def api_favorites(
    category: list[str] = Query([]),
    page: int = 1,
    per_page: int = 35,
    status: str = "",
    sort: str = "dd",
    match_mode: str = "or",
    fav_svc: FavoriteService = Depends(get_favorite_service),
):
    return await fav_svc.list_favorites(category, page, per_page, status, sort, match_mode)


@router.post("/favorites/refresh")
async def api_favorites_refresh(
    fav_svc: FavoriteService = Depends(get_favorite_service),
):
    try:
        result = await fav_svc.refresh_from_api()
        if not result.get("ok"):
            raise HTTPException(400, result.get("error", "同步失败"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@router.get("/categories")
async def api_categories(
    comic_svc: ComicService = Depends(get_comic_service),
):
    cats = await comic_svc.get_categories()
    return {"categories": cats}


@router.post("/mark-seen")
def api_mark_seen(
    fav_svc: FavoriteService = Depends(get_favorite_service),
    comic_id: str | None = Body(None, embed=True),
):
    if comic_id:
        fav_svc.mark_one_seen(comic_id)
    else:
        fav_svc.mark_seen()
    return {"ok": True}


@router.post("/favourite")
async def api_favourite(
    comic_id: str = Body(..., embed=True),
):
    from app.core.pica_client import AsyncPicaClient
    from app.repositories.config_repo import ConfigRepo

    cfg = ConfigRepo().read()
    if not cfg.get("token"):
        raise HTTPException(400, "请先登录")

    client = AsyncPicaClient(cfg)
    try:
        result = await client.favourite_comic(comic_id)
        print(f"[Favourite] comic_id={comic_id}, result={result.get('code')}, msg={result.get('message', '')}")
        if result.get("code") != 200:
            raise HTTPException(400, result.get("message", "收藏失败"))
    finally:
        await client.close()
    return {"ok": True, "comic_id": comic_id}
