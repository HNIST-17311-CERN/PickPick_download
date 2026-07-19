"""收藏路由"""
from fastapi import APIRouter, HTTPException, Depends, Query

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
):
    fav_svc.mark_seen()
    return {"ok": True}
