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
        categories: list[str] | None = None,
        page: int = 1,
        per_page: int = 35,
        status: str = "",
        sort: str = "dd",
        match_mode: str = "or",
    ) -> dict:
        """收藏列表。有筛选时走本地缓存全量过滤，无筛选时走 API 分页。"""
        from app.core.pica_client import AsyncPicaClient

        if categories is None:
            categories = []
        categories = [c for c in categories if c]

        cfg = ConfigRepo().read()
        if not cfg.get("token") or not cfg.get("nonce"):
            return {"items": [], "total": 0, "new_count": 0, "page": page, "per_page": per_page, "categories": []}

        need_filter = bool(categories or status)
        api_total = 0
        if need_filter:
            all_comics = self._comic.load_all()
            api_total = len(all_comics)
            id_map = self._build_id_map() if DETAIL_DIR.exists() else {}
        else:
            client = AsyncPicaClient(cfg)
            try:
                data = await client.get_favourites(page=page, sort=sort, limit=per_page)
                pd = data.get("data", {}).get("comics", {})
                all_comics = pd.get("docs", [])
                api_total = pd.get("total", 0)
            finally:
                await client.close()
            id_map = self._build_id_map() if DETAIL_DIR.exists() else {}

        items = []
        new_ids = self._seen.get_new_ids({c.get("_id", "") for c in all_comics})
        for i, c in enumerate(all_comics):
            cid = c.get("_id", "")
            scan = id_map.get(cid)
            if scan:
                if scan["chapter_total"] > 0 and scan["chapter_done"] >= scan["chapter_total"]:
                    dl_status = "downloaded"
                elif scan["chapter_done"] > 0:
                    dl_status = "partial"
                else:
                    dl_status = "none"
            else:
                dl_status = "none"

            if status and dl_status != status:
                continue

            if categories:
                comic_cats = c.get("categories", [])
                if match_mode == "and":
                    if not all(cat in comic_cats for cat in categories):
                        continue
                else:
                    if not any(cat in comic_cats for cat in categories):
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
                "is_new": cid in new_ids,
                "folder": scan["folder"] if scan else None,
                "cover_url": cover_url,
                "has_cover": bool(cover_url),
                "chapter_done": scan["chapter_done"] if scan else 0,
                "chapter_total": scan["chapter_total"] if scan else 0,
                "chapter_errors": scan["chapter_errors"] if scan else 0,
            })

        # 本地分页
        if need_filter:
            filtered_total = len(items)
            new_count = sum(1 for it in items if it["is_new"])
            start = (page - 1) * per_page
            paged_items = items[start:start + per_page]
        else:
            filtered_total = api_total
            new_count = sum(1 for it in items if it["is_new"])
            paged_items = items

        # 收集所有分类
        all_cats = set()
        for c in all_comics:
            for cat_name in c.get("categories", []):
                all_cats.add(cat_name)

        return {
            "items": paged_items,
            "total": filtered_total,
            "new_count": new_count,
            "page": page,
            "per_page": per_page,
            "categories": sorted(all_cats),
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

    def mark_one_seen(self, comic_id: str) -> None:
        self._seen.mark_one_seen(comic_id)

    def get_new_ids(self) -> set[str]:
        current = self._comic.get_all_ids()
        return self._seen.get_new_ids(current)
