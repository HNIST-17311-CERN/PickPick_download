"""分类路由"""
from fastapi import APIRouter, Depends

from app.dependencies import get_category_service
from app.services.category_service import CategoryService

router = APIRouter(prefix="/api/categories", tags=["categories"])


@router.get("/full")
async def api_full_categories(
    cat_svc: CategoryService = Depends(get_category_service),
):
    groups = await cat_svc.get_full_categories()
    return {"groups": groups}
