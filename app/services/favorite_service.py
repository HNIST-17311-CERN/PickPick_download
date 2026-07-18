"""收藏管理业务逻辑"""
import json
from pathlib import Path

from app.repositories.comic_repo import ComicsMetadataRepo, ComicsDetailRepo, LastSeenRepo, DETAIL_DIR
from app.repositories.config_repo import ConfigRepo
from app.core.file_utils import build_image_url


class FavoriteService:
    def __init__(
        self,
        comic_repo: ComicsMetadataRepo,
        detail_repo: ComicsDetailRepo,
        seen_repo: LastSeenRepo,
    ):
        self._comic = comic_repo
        self._detail = detail_repo
        self._seen = seen_repo

    def _build_id_map(self) -> dict:
        mapping = {}
        if DETAIL_DIR.exists():
            for d in DETAIL_DIR.glob("*"):
                if not d.is_dir():
                    continue
                mp = d / "metadata.json"
                if not mp.exists():
                    continue
                try:
                    with open(mp, "r", encoding="utf-8") as f:
                        meta = json.load(f)
                    cid = meta.get("_id")
                    if not cid:
                        continue
                    chapters = self._detail.read_chapters(d)
                    done = sum(1 for ch in chapters if ch.get("downloaded", 0) >= ch.get("totalPages", 1))
                    errors = sum(1 for ch in chapters if ch.get("error"))
                    mapping[cid] = {
                        "folder": d.name,
                        "has_cover": self._detail.has_cover(d),
                        "chapter_done": done,
                        "chapter_total": len(chapters),
                        "chapter_errors": errors,
                    }
                except Exception:
                    pass
        return mapping

    async def list_favorites(
        self,
        category: str = "",
        page: int = 1,
        per_page: int = 35,
        status: str = "",
        sort: str = "dd",
    ) -> dict:
        """实时从 Pica API 拉取收藏列表（不依赖本地缓存）"""
        from app.core.pica_client import AsyncPicaClient

        cfg = ConfigRepo().read()
        if not cfg.get("token") or not cfg.get("nonce"):
            return {"items": [], "total": 0, "new_count": 0, "page": page, "per_page": per_page, "categories": []}

        # Pica API 每页最多返回 page_data["limit"] 条，前端 per_page 直接当 limit
        client = AsyncPicaClient(cfg)
        try:
            data = await client.get_favourites(page=page, sort=sort, limit=per_page)
        finally:
            await client.close()

        page_data = data.get("data", {}).get("comics", {})
        comics = page_data.get("docs", [])
        total = page_data.get("total", 0)

        id_map = self._build_id_map() if DETAIL_DIR.exists() else {}

        items = []
        for i, c in enumerate(comics):
            cid = c.get("_id", "")
            scan = id_map.get(cid)
            if scan:
                dl_status = "downloaded" if (scan["chapter_total"] > 0 and scan["chapter_done"] >= scan["chapter_total"]) else "partial"
            else:
                dl_status = "none"

            if status and dl_status != status:
                continue

            # 封面：本地优先，否则用 CDN
            cover_url = ""
            if scan and scan["has_cover"]:
                cover_url = f"/images/{scan['folder']}/cover.jpg"
            else:
                thumb = c.get("thumb", {})
                cover_url = build_image_url(thumb)

            items.append({
                "idx": (page - 1) * per_page + i + 1,
                "_id": cid,
                "title": c.get("title", "?"),
                "author": c.get("author", ""),
                "categories": c.get("categories", []),
                "epsCount": c.get("epsCount", 0),
                "dl_status": dl_status,
                "is_new": False,
                "folder": scan["folder"] if scan else None,
                "cover_url": cover_url,
                "has_cover": bool(cover_url),
                "chapter_done": scan["chapter_done"] if scan else 0,
                "chapter_total": scan["chapter_total"] if scan else 0,
                "chapter_errors": scan["chapter_errors"] if scan else 0,
            })

        return {
            "items": items,
            "total": total,
            "new_count": 0,
            "page": page,
            "per_page": per_page,
            "categories": [],  # 实时模式下按需加载分类，前端已有 /api/categories
        }

    async def refresh_from_api(self) -> dict:
        """从 Pica API 同步收藏 → comics_metadata.json，返回结果包含计数信息"""
        from app.core.pica_client import AsyncPicaClient

        cfg = ConfigRepo().read()
        if not cfg.get("token") or not cfg.get("nonce"):
            return {"ok": False, "error": "请先登录（设置页填写 token 或账号登录）"}

        client = AsyncPicaClient(cfg)
        try:
            comics = await client.get_all_favourites()
        finally:
            await client.close()

        self._comic.save_all(comics)
        current_ids = {c["_id"] for c in comics if "_id" in c}
        new_count = len(self._seen.get_new_ids(current_ids))
        return {"ok": True, "total": len(comics), "new_count": new_count}

    def mark_seen(self) -> None:
        comics = self._comic.load_all()
        ids = [c["_id"] for c in comics if "_id" in c]
        self._seen.mark_all_seen(ids)

    def get_new_ids(self) -> set[str]:
        current = self._comic.get_all_ids()
        return self._seen.get_new_ids(current)
