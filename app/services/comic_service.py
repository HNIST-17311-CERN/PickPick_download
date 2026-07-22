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

    def _find_local_by_id(self, comic_id: str) -> tuple[Path | None, list[dict]]:
        """通过 _id 查找本地已下载的漫画文件夹，返回 (folder, chapters)"""
        if not DETAIL_DIR.exists() or not comic_id:
            return None, []
        for d in DETAIL_DIR.glob("*"):
            if not d.is_dir():
                continue
            mp = d / "metadata.json"
            if not mp.exists():
                continue
            try:
                with open(mp, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                if meta.get("_id") == comic_id:
                    return d, self._detail.read_chapters(d)
            except Exception:
                pass
        return None, []

    @staticmethod
    def _merge_chapter_status(api_chapters: list[dict], local_chapters: list[dict]) -> list[dict]:
        """将本地下载状态合并到 API 获取的章节列表中"""
        local_map = {ch.get("order"): ch for ch in local_chapters}
        for ch in api_chapters:
            lc = local_map.get(ch.get("order"))
            if lc:
                ch["totalPages"] = lc.get("totalPages", 0)
                ch["downloaded"] = lc.get("downloaded", 0)
                ch["error"] = lc.get("error", False)
        return api_chapters

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
        has_cover = self._detail.has_cover(folder)
        eps = meta.get("epsCount", 0)
        is_dl = len(chapters) > 0 and len(chapters) >= eps and all(ch.get("downloaded", 0) >= ch.get("totalPages", 1) for ch in chapters)
        return {
            "folder": folder_name,
            "local_folder": folder_name,
            "is_downloaded": is_dl,
            "meta": meta,
            "chapters": chapters,
            "has_cover": has_cover,
            "cover_url": f"/images/{folder_name}/cover.jpg" if has_cover else "",
        }

    async def get_api_detail(self, folder_name: str) -> dict | None:
        """从 Pica API 获取未下载漫画的详情，同时合并本地下载状态"""
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

            local_folder, local_chapters = self._find_local_by_id(cid)

            detail = await client.get_comic_info(cid)
            api_comic = detail.get("data", {}).get("comic", {})

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

            self._merge_chapter_status(api_chapters, local_chapters)

            thumb = api_comic.get("thumb", {}) or c.get("thumb", {})
            cover_url = thumb.get("url") or thumb.get("proxyUrl") or ""
            if not cover_url:
                fs = thumb.get("fileServer", "")
                path = thumb.get("path", "")
                if fs and path:
                    cover_url = f"{fs}/static/{path}"

            eps_count = api_comic.get("epsCount", 0)
            is_dl = local_folder is not None and len(local_chapters) > 0 and len(local_chapters) >= eps_count and all(ch.get("downloaded", 0) >= ch.get("totalPages", 1) for ch in local_chapters)
            return {
                "folder": f"idx_{idx + 1}",
                "comic_idx": idx + 1,
                "from_api": True,
                "is_favourited": True,
                "local_folder": local_folder.name if local_folder else None,
                "is_downloaded": is_dl,
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
        """直接用漫画 _id 从 Pica API 获取详情，同时合并本地下载状态"""
        from app.core.pica_client import AsyncPicaClient
        from app.repositories.config_repo import ConfigRepo
        from app.repositories.comic_repo import ComicsMetadataRepo

        cfg = ConfigRepo().read()
        if not cfg.get("token") or not comic_id:
            return None

        local_folder, local_chapters = self._find_local_by_id(comic_id)
        is_fav = comic_id in ComicsMetadataRepo().get_all_ids()

        client = AsyncPicaClient(cfg)
        try:
            detail = await client.get_comic_info(comic_id)
            api_comic = detail.get("data", {}).get("comic", {})
            if not api_comic:
                if local_folder:
                    return await self.get_detail(local_folder.name)
                return None

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

            self._merge_chapter_status(api_chapters, local_chapters)

            thumb = api_comic.get("thumb", {})
            cover_url = thumb.get("url") or thumb.get("proxyUrl") or ""
            if not cover_url:
                fs = thumb.get("fileServer", "")
                path = thumb.get("path", "")
                if fs and path:
                    cover_url = f"{fs}/static/{path}"

            eps_count = api_comic.get("epsCount", 0)
            is_dl = local_folder is not None and len(local_chapters) > 0 and len(local_chapters) >= eps_count and all(ch.get("downloaded", 0) >= ch.get("totalPages", 1) for ch in local_chapters)
            return {
                "folder": f"_id-{comic_id}",
                "from_api": True,
                "is_favourited": is_fav,
                "local_folder": local_folder.name if local_folder else None,
                "is_downloaded": is_dl,
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
