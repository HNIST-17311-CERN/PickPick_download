"""漫画浏览业务逻辑"""
import asyncio
import json
from pathlib import Path

from app.repositories.comic_repo import ComicsDetailRepo, DETAIL_DIR
from app.core.file_utils import safe_filename


class ComicService:
    def __init__(self, detail_repo: ComicsDetailRepo):
        self._detail = detail_repo

    def _read_folder_info(self, folder: Path) -> dict:
        chapters = self._detail.read_chapters(folder)
        done = sum(1 for ch in chapters if ch.get("downloaded", 0) >= ch.get("totalPages", 1))
        errors = sum(1 for ch in chapters if ch.get("error"))
        return {
            "folder": folder.name,
            "has_cover": self._detail.has_cover(folder),
            "chapter_done": done,
            "chapter_total": len(chapters),
            "chapter_errors": errors,
        }

    async def list_comics(
        self, categories: list[str] | None = None, page: int = 1, per_page: int = 35, match_mode: str = "or"
    ) -> dict:
        """列出本地已下载的漫画"""
        if categories is None:
            categories = []
        categories = [c for c in categories if c]
        folders = await self._detail.list_folders()
        items = []
        for folder in folders:
            meta = self._detail.read_metadata(folder)
            if not meta:
                continue
            chapters = self._detail.read_chapters(folder)
            done = sum(1 for ch in chapters if ch.get("downloaded", 0) >= ch.get("totalPages", 1))
            errors = sum(1 for ch in chapters if ch.get("error"))
            cats = meta.get("categories", [])
            if categories:
                if match_mode == "and":
                    if not all(c in cats for c in categories):
                        continue
                else:
                    if not any(c in cats for c in categories):
                        continue
            items.append({
                "folder": folder.name,
                "title": meta.get("title", folder.name[4:]),
                "author": meta.get("author", ""),
                "categories": cats,
                "tags": meta.get("tags", []),
                "status": meta.get("status", ""),
                "epsCount": meta.get("epsCount", len(chapters)),
                "pagesCount": meta.get("pagesCount", 0),
                "totalViews": meta.get("totalViews", 0),
                "totalLikes": meta.get("totalLikes", 0),
                "chapter_done": done,
                "chapter_total": len(chapters),
                "chapter_errors": errors,
                "has_cover": self._detail.has_cover(folder),
            })

        total = len(items)
        start = (page - 1) * per_page
        return {
            "items": items[start:start + per_page],
            "total": total,
            "page": page,
            "per_page": per_page,
        }

    async def get_detail(self, folder_name: str) -> dict | None:
        """获取单部漫画详情（本地文件夹）"""
        folder = DETAIL_DIR / folder_name
        if not folder.is_dir():
            return None
        meta = self._detail.read_metadata(folder) or {}
        chapters = self._detail.read_chapters(folder)
        return {
            "folder": folder_name,
            "meta": meta,
            "chapters": chapters,
            "has_cover": self._detail.has_cover(folder),
        }

    async def get_api_detail(self, folder_name: str) -> dict | None:
        """从 Pica API 获取未下载漫画的详情"""
        import asyncio as _asyncio
        from app.repositories.config_repo import ConfigRepo
        from app.core.pica_client import AsyncPicaClient

        if not folder_name.startswith("idx_"):
            return None
        try:
            idx = int(folder_name.split("_")[1]) - 1
        except (ValueError, IndexError):
            return None

        cfg = ConfigRepo().read()
        if not cfg.get("token"):
            return None

        client = AsyncPicaClient(cfg)
        try:
            from app.repositories.comic_repo import ComicsMetadataRepo
            comics = ComicsMetadataRepo().load_all()
            if not (0 <= idx < len(comics)):
                await client.close()
                return None
            c = comics[idx]
            cid = c.get("_id", "")
            detail = await client.get_comic_info(cid)
            api_comic = detail.get("data", {}).get("comic", {})

            # 获取章节列表
            api_chapters = []
            ep_page = 1
            while True:
                ep_data = await client.get_episodes(cid, page=ep_page)
                eps_block = ep_data.get("data", {}).get("eps", {})
                for ep in eps_block.get("docs", []):
                    api_chapters.append({
                        "order": ep["order"],
                        "title": ep.get("title", f"第{ep['order']}话"),
                        "totalPages": 0,
                        "downloaded": 0,
                    })
                if ep_page >= eps_block.get("pages", 1):
                    break
                ep_page += 1

            thumb = api_comic.get("thumb", {}) or c.get("thumb", {})
            cover_url = thumb.get("url") or thumb.get("proxyUrl") or ""
            if not cover_url:
                fs = thumb.get("fileServer", "")
                path = thumb.get("path", "")
                if fs and path:
                    cover_url = f"{fs}/static/{path}"

            return {
                "folder": f"idx_{idx + 1}",
                "comic_idx": idx + 1,
                "from_api": True,
                "meta": {
                    "_id": api_comic.get("_id", cid),
                    "title": api_comic.get("title") or c.get("title"),
                    "author": api_comic.get("author", ""),
                    "chineseTeam": api_comic.get("chineseTeam", ""),
                    "categories": api_comic.get("categories", []),
                    "tags": api_comic.get("tags", []),
                    "status": "已完结" if api_comic.get("finished") else "连载中",
                    "finished": api_comic.get("finished", False),
                    "epsCount": api_comic.get("epsCount", 0),
                    "pagesCount": api_comic.get("pagesCount", 0),
                    "totalViews": api_comic.get("totalViews", 0),
                    "totalLikes": api_comic.get("totalLikes", 0),
                    "description": api_comic.get("description", ""),
                    "thumb": thumb,
                },
                "chapters": api_chapters,
                "has_cover": bool(cover_url),
                "cover_url": cover_url,
            }
        except Exception:
            return None
        finally:
            await client.close()

    async def get_detail_by_id(self, comic_id: str) -> dict | None:
        """直接用漫画 _id 从 Pica API 获取详情"""
        from app.core.pica_client import AsyncPicaClient
        from app.repositories.config_repo import ConfigRepo

        cfg = ConfigRepo().read()
        if not cfg.get("token") or not comic_id:
            return None

        client = AsyncPicaClient(cfg)
        try:
            detail = await client.get_comic_info(comic_id)
            api_comic = detail.get("data", {}).get("comic", {})
            if not api_comic:
                return None

            # 获取章节列表
            api_chapters = []
            ep_page = 1
            while True:
                ep_data = await client.get_episodes(comic_id, page=ep_page)
                eps_block = ep_data.get("data", {}).get("eps", {})
                for ep in eps_block.get("docs", []):
                    api_chapters.append({
                        "order": ep["order"],
                        "title": ep.get("title", f"第{ep['order']}话"),
                        "totalPages": 0,
                        "downloaded": 0,
                    })
                if ep_page >= eps_block.get("pages", 1):
                    break
                ep_page += 1

            thumb = api_comic.get("thumb", {})
            cover_url = thumb.get("url") or thumb.get("proxyUrl") or ""
            if not cover_url:
                fs = thumb.get("fileServer", "")
                path = thumb.get("path", "")
                if fs and path:
                    cover_url = f"{fs}/static/{path}"

            return {
                "folder": f"_id-{comic_id}",
                "from_api": True,
                "meta": {
                    "_id": api_comic.get("_id", comic_id),
                    "title": api_comic.get("title", ""),
                    "author": api_comic.get("author", ""),
                    "chineseTeam": api_comic.get("chineseTeam", ""),
                    "categories": api_comic.get("categories", []),
                    "tags": api_comic.get("tags", []),
                    "status": "已完结" if api_comic.get("finished") else "连载中",
                    "finished": api_comic.get("finished", False),
                    "epsCount": api_comic.get("epsCount", 0),
                    "pagesCount": api_comic.get("pagesCount", 0),
                    "totalViews": api_comic.get("totalViews", 0),
                    "totalLikes": api_comic.get("totalLikes", 0),
                    "description": api_comic.get("description", ""),
                    "thumb": thumb,
                },
                "chapters": api_chapters,
                "has_cover": bool(cover_url),
                "cover_url": cover_url,
            }
        except Exception:
            return None
        finally:
            await client.close()

    async def get_chapter_images(self, folder_name: str, order: int) -> dict:
        """获取章节所有图片文件"""
        folder = DETAIL_DIR / folder_name
        if not folder.is_dir():
            return {"images": [], "total": 0}
        # 从 chapters.json 找到章节文件夹名
        chapters = self._detail.read_chapters(folder)
        ch_folder = None
        for ch in chapters:
            if ch.get("order") == order:
                # chapters.json 不存 folder_name，尝试匹配
                for d in sorted(folder.glob("*")):
                    if d.is_dir() and d.name == safe_filename(ch.get("title", f"第{order}话"), max_len=40):
                        ch_folder = d
                        break
                # fallback：旧格式匹配
                if not ch_folder:
                    for d in sorted(folder.glob("*")):
                        if d.is_dir() and d.name.startswith(f"{order:02d}_"):
                            ch_folder = d
                            break
                break
        if not ch_folder:
            return {"images": [], "total": 0}
        images = sorted(ch_folder.glob("*"))
        result = [{
            "filename": img.name,
            "url": f"/images/{folder_name}/{ch_folder.name}/{img.name}",
        } for img in images if img.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp", ".gif")]
        return {"images": result, "total": len(result)}

    async def delete_comic(self, folder_name: str) -> None:
        await self._detail.delete_folder_async(folder_name)

    async def get_categories(self) -> list[str]:
        """收集所有分类"""
        cats = set()
        folders = await self._detail.list_folders()
        for folder in folders:
            meta = self._detail.read_metadata(folder)
            if meta:
                for c in meta.get("categories", []):
                    cats.add(c)
        return sorted(cats)

    async def get_comic_by_idx(self, idx: int) -> dict | None:
        """按索引获取漫画（从 comics_metadata.json）"""
        from app.repositories.comic_repo import ComicsMetadataRepo
        comics = ComicsMetadataRepo().load_all()
        if 0 <= idx < len(comics):
            return comics[idx]
        return None
