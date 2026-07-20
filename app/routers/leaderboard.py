"""排行榜路由"""
from fastapi import APIRouter, HTTPException, Query

from app.repositories.config_repo import ConfigRepo
from app.core.pica_client import AsyncPicaClient

router = APIRouter(prefix="/api/leaderboard", tags=["leaderboard"])

TT_LABELS = {
    "H24": "24小时榜",
    "D7": "周榜",
    "D30": "月榜",
}
CT_LABELS = {
    "VC": "",
}


@router.get("")
async def api_leaderboard(
    tt: str = Query("H24", description="时间类型: H24/D7/D30"),
    ct: str = Query("VC", description="排行类型: VC(人气)/BY(收藏)"),
):
    cfg = ConfigRepo().read()
    if not cfg.get("token") or not cfg.get("nonce"):
        raise HTTPException(401, "请先登录")

    client = AsyncPicaClient(cfg)
    try:
        data = await client.get_leaderboard(tt=tt, ct=ct)
        comics = data.get("data", {}).get("comics", [])
        items = []
        for c in comics:
            thumb = c.get("thumb", {})
            cover = thumb.get("url") or thumb.get("proxyUrl") or ""
            if not cover:
                fs = thumb.get("fileServer", "")
                path = thumb.get("path", "")
                if fs and path:
                    cover = f"{fs}/static/{path}"
            items.append({
                "_id": c.get("_id", ""),
                "title": c.get("title", ""),
                "author": c.get("author", ""),
                "categories": c.get("categories", []),
                "epsCount": c.get("epsCount", 0),
                "finished": c.get("finished", False),
                "cover_url": cover,
                "totalViews": c.get("totalViews", 0),
                "totalLikes": c.get("totalLikes", 0),
            })
        return {
            "items": items,
            "tt": tt,
            "ct": ct,
            "tt_label": TT_LABELS.get(tt, tt),
            "ct_label": CT_LABELS.get(ct, ct),
            "tabs": [
                {"tt": k, "ct": "VC", "label": TT_LABELS[k]}
                for k in TT_LABELS
            ],
        }
    finally:
        await client.close()
