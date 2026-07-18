"""搜索路由"""
from fastapi import APIRouter, Query, Depends

from app.dependencies import get_search_service
from app.services.search_service import SearchService

router = APIRouter(prefix="/api", tags=["search"])


@router.get("/search")
async def api_search(
    keyword: str = Query("", description="搜索关键词"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    search_svc: SearchService = Depends(get_search_service),
):
    return await search_svc.search(keyword, page, per_page)
