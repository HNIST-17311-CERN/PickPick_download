"""搜索服务 — 合并三源搜索 + 分页"""
from pathlib import Path

from app.repositories.comic_repo import ComicsMetadataRepo, ComicsDetailRepo, DETAIL_DIR
from app.repositories.local_repo import LocalComicRepo
from app.core.file_utils import build_image_url


class SearchService:

    def __init__(self):
        self._comic_repo = ComicsMetadataRepo()
        self._detail_repo = ComicsDetailRepo()
        self._local_repo = LocalComicRepo()

    async def search(self, keyword: str, page: int = 1, per_page: int = 20) -> dict:
        results = []
        kw = keyword.strip().lower()
        if not kw:
            return {"keyword": keyword, "results": [], "total": 0, "page": 1, "per_page": per_page}

        # 1. 收藏缓存 (comics_metadata.json)
        try:
            favorites = self._comic_repo.load_all()
            for i, c in enumerate(favorites):
                title = (c.get("title") or "").lower()
                author = (c.get("author") or "").lower()
                tags = " ".join((c.get("tags") or [])).lower()
                desc = (c.get("description") or "").lower()
                team = (c.get("chineseTeam") or "").lower()
                if kw in title or kw in author or kw in tags or kw in desc or kw in team:
                    thumb = c.get("thumb", {})
                    results.append({
                        "title": c.get("title", "?"),
                        "author": c.get("author", ""),
                        "cover": build_image_url(thumb) or "",
                        "source": "favorite",
                        "idx": i + 1,
                        "folder": None,
                        "categories": c.get("categories", []),
                        "epsCount": c.get("epsCount", 0),
                        "chapter_done": 0,
                        "chapter_total": 0,
                    })
        except Exception:
            pass

        # 2. 已下载漫画 (comics_detail/*/metadata.json)
        try:
            if DETAIL_DIR.exists():
                for d in DETAIL_DIR.glob("*"):
                    if not d.is_dir():
                        continue
                    meta = self._detail_repo.read_metadata(d)
                    if not meta:
                        continue
                    title = (meta.get("title") or "").lower()
                    author = (meta.get("author") or "").lower()
                    cats = " ".join(c.lower() for c in meta.get("categories", []))
                    tags = " ".join((meta.get("tags") or [])).lower()
                    desc = (meta.get("description") or "").lower()
                    team = (meta.get("chineseTeam") or "").lower()
                    if kw in title or kw in author or kw in cats or kw in tags or kw in desc or kw in team:
                        chapters = self._detail_repo.read_chapters(d)
                        done = sum(1 for ch in chapters if ch.get("downloaded", 0) >= ch.get("totalPages", 1))
                        results.append({
                            "title": meta.get("title", d.name[4:]),
                            "author": meta.get("author", ""),
                            "cover": f"/images/{d.name}/cover.jpg" if (d / "cover.jpg").exists() else "",
                            "source": "downloaded",
                            "idx": None,
                            "folder": d.name,
                            "categories": meta.get("categories", []),
                            "epsCount": meta.get("epsCount", len(chapters)),
                            "chapter_done": done,
                            "chapter_total": len(chapters),
                        })
        except Exception:
            pass

        # 3. 本地导入 (pica.db SQLite)
        try:
            local_data = await self._local_repo.list_all(page=1, per_page=9999, search=keyword)
            for item in local_data.get("items", []):
                cover = ""
                if item.get("cover_path"):
                    cover = f"/api/local/{item['id']}/images/1/{Path(item['cover_path']).name}" if item.get("cover_path") else ""
                results.append({
                    "title": item.get("title", "?"),
                    "author": item.get("author", ""),
                    "cover": cover,
                    "source": "local",
                    "idx": None,
                    "folder": None,
                    "local_id": item.get("id"),
                    "categories": item.get("categories", []),
                    "epsCount": item.get("ch_count", 0),
                    "chapter_done": 0,
                    "chapter_total": item.get("ch_count", 0),
                })
        except Exception:
            pass

        # 去重排序
        seen = set()
        deduped = []
        for r in results:
            key = (r["title"].strip().lower(), r["author"].strip().lower(), r["source"])
            if key in seen:
                continue
            seen.add(key)
            deduped.append(r)
        deduped.sort(key=lambda r: r["title"])

        total = len(deduped)
        start = (page - 1) * per_page
        paged = deduped[start:start + per_page]

        return {
            "keyword": keyword,
            "results": paged,
            "total": total,
            "page": page,
            "per_page": per_page,
        }
