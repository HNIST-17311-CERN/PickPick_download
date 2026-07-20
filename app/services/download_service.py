"""下载管理 — async 状态管理 + 业务逻辑"""
import asyncio
import base64
import json
import re
import time
from pathlib import Path

from app.repositories.comic_repo import ComicsMetadataRepo, ComicsDetailRepo
from app.repositories.config_repo import ConfigRepo
from app.repositories.download_repo import DownloadProgressRepo
from app.core.file_utils import safe_filename, build_image_url, download_image_async


def _to_original_url(fs: str, pv: str) -> str:
    """将 CDN 缩略图 URL 转为原画 URL"""
    if "tobeimg" not in pv:
        return f"{fs}/static/{pv}"
    m = re.search(r'/(aHR0[a-zA-Z0-9+/=]{20,})(?:$|[?/])', pv)
    if m:
        try:
            b64 = m.group(1)
            pad = len(b64) % 4
            if pad:
                b64 += "=" * (4 - pad)
            decoded = base64.b64decode(b64).decode("utf-8")
            if decoded.startswith("http"):
                return decoded
        except Exception:
            pass
    return f"{fs}/static/{pv}"


class DownloadState:
    """下载状态容器"""
    def __init__(self):
        self.running: bool = False
        self.current: str = ""
        self.progress_done: int = 0
        self.progress_total: int = 0
        self.progress_title: str = ""
        self.logs: list[str] = []
        self.skips: list[dict] = []


class DownloadStateManager:
    """Async-safe 下载状态管理器"""

    def __init__(self):
        self.state = DownloadState()
        self.lock = asyncio.Lock()
        self.log_queue: asyncio.Queue[str] = asyncio.Queue()
        self.stop_event = asyncio.Event()
        self._task: asyncio.Task = None

    async def start(self, current: str = "") -> None:
        async with self.lock:
            self.state = DownloadState()
            self.state.running = True
            self.state.current = current
        self.stop_event.clear()
        # 清空上次下载残留的消息，防止 SSE 立即读到旧 __DONE__
        while not self.log_queue.empty():
            try:
                self.log_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

    async def stop(self) -> None:
        self.stop_event.set()
        if self._task and not self._task.done():
            self._task.cancel()
        async with self.lock:
            self.state.running = False
            self.state.current = ""
        await self.log_queue.put("__DONE__")

    async def log(self, msg: str) -> None:
        await self.log_queue.put(msg)
        async with self.lock:
            self.state.logs.append(msg)
            if len(self.state.logs) > 200:
                self.state.logs = self.state.logs[-100:]
            # 解析跳过/进度信息
            skip = self._parse_skip(msg)
            if skip:
                self.state.skips.append({"item": skip[0], "reason": skip[1]})
            if msg.startswith("__PROGRESS__"):
                parts = msg.split()
                if len(parts) >= 2:
                    dt = parts[1].split("/")
                    if len(dt) == 2:
                        self.state.progress_done = int(dt[0])
                        self.state.progress_total = int(dt[1])
                    self.state.progress_title = " ".join(parts[2:]) if len(parts) > 2 else ""

    def _parse_skip(self, line: str) -> tuple[str, str] | None:
        m = re.search(r'\[(\d+)\]\s*SKIP:\s*(.+?)\s*[—–-]\s*(.+)', line)
        if m:
            return (f"[{m.group(1)}] {m.group(2).strip()}", m.group(3).strip())
        m = re.search(r'(第\d+话)\s*SKIP:\s*(.+)', line)
        if m:
            return (m.group(1), m.group(2).strip())
        return None

    async def get_status(self) -> dict:
        async with self.lock:
            s = self.state
            return {
                "running": s.running,
                "current": s.current,
                "progress_done": s.progress_done,
                "progress_total": s.progress_total,
                "progress_title": s.progress_title,
            }


class DownloadService:
    def __init__(
        self,
        comic_repo: ComicsMetadataRepo,
        detail_repo: ComicsDetailRepo,
        progress_repo: DownloadProgressRepo,
    ):
        self._comic = comic_repo
        self._detail = detail_repo
        self._progress = progress_repo

    def parse_target(self, target: str, total: int) -> list[int]:
        if target == "all":
            return list(range(total))
        if "-" in target:
            parts = target.split("-")
            start, end = int(parts[0]) - 1, int(parts[1]) - 1
            return list(range(max(0, start), min(total, end + 1)))
        return [int(target) - 1]

    def get_queue(self) -> dict:
        """构建未完成的下载队列"""
        completed = self._progress.get_completed_ids()
        comics = self._comic.load_all()

        # 构建 _id → folder 映射
        id_map = {}
        if self._detail._base.exists():
            for d in self._detail._base.glob("*"):
                if not d.is_dir():
                    continue
                mp = d / "metadata.json"
                if not mp.exists():
                    continue
                try:
                    with open(mp, "r", encoding="utf-8") as f:
                        cid = json.load(f).get("_id")
                    if cid:
                        chapters = self._detail.read_chapters(d)
                        done = sum(1 for ch in chapters if ch.get("downloaded", 0) >= ch.get("totalPages", 1))
                        id_map[cid] = (d, done, len(chapters))
                except Exception:
                    pass

        result = []
        for idx, c in enumerate(comics):
            cid = c.get("_id", "")
            entry = id_map.get(cid)
            # 已完成的检查是否有新章节：API epsCount > 本地章节数 → 放回队列
            if cid in completed:
                api_eps = c.get("epsCount", 0)
                local_eps = entry[2] if entry else 0
                if api_eps <= local_eps:
                    continue
            if entry:
                d, ch_done, ch_total = entry
                result.append({
                    "idx": idx + 1,
                    "title": c.get("title", "?"),
                    "author": c.get("author", ""),
                    "epsCount": c.get("epsCount", 0),
                    "ch_done": ch_done,
                    "ch_total": ch_total,
                    "has_detail": True,
                    "folder": d.name,
                    "is_new": False,
                })
            else:
                result.append({
                    "idx": idx + 1,
                    "title": c.get("title", "?"),
                    "author": c.get("author", ""),
                    "epsCount": c.get("epsCount", 0),
                    "ch_done": 0,
                    "ch_total": c.get("epsCount", 0),
                    "has_detail": False,
                    "folder": None,
                    "is_new": False,
                })

        return {"items": result, "total": len(result)}

    async def run_download(
        self,
        target: str = None,
        indices: list[int] = None,
        page_concurrency: int = 3,
        chapter_concurrency: int = 1,
        comic_concurrency: int = 1,
        image_quality: str = "standard",
        state_mgr: DownloadStateManager = None,
    ) -> None:
        """主下载入口 — 作为 asyncio.Task 后台运行

        target: "all" / "3" / "1-50" — 字符串格式，与 indices 二选一
        indices: 0-based 索引列表 — 用于前端批量下载，与 target 二选一
        """
        from app.core.pica_client import AsyncPicaClient
        from app.repositories.config_repo import ConfigRepo

        cfg = ConfigRepo().read()
        client = AsyncPicaClient(cfg, stop_event=state_mgr.stop_event, log_func=state_mgr.log)

        try:
            comics = self._comic.load_all()
            if indices is not None:
                actual_indices = indices
            else:
                actual_indices = self.parse_target(target or "all", len(comics))
            completed = self._progress.get_completed_ids()

            remaining = [i for i in actual_indices if comics[i].get("_id", f"idx_{i}") not in completed]
            if len(remaining) < len(actual_indices):
                await state_mgr.log(f"跳过 {len(actual_indices) - len(remaining)} 部已完成，剩余 {len(remaining)} 部")

            # 构建 _id → folder 映射
            id_map = {}
            if self._detail._base.exists():
                for d in self._detail._base.glob("*"):
                    if not d.is_dir():
                        continue
                    mp = d / "metadata.json"
                    if mp.exists():
                        try:
                            with open(mp, "r", encoding="utf-8") as f:
                                id_map[json.load(f).get("_id")] = d
                        except Exception:
                            pass

            comic_sem = asyncio.Semaphore(comic_concurrency)

            async def _do_comic(progress_n, idx):
                nonlocal id_map
                if state_mgr.stop_event.is_set():
                    await state_mgr.log("__STOPPED__ 用户手动停止")
                    return

                c = comics[idx]
                cid = c.get("_id", "")
                folder = id_map.get(cid)
                if not folder:
                    new_num = len(comics) - idx
                    folder = self._detail._base / f"{new_num:03d}_{safe_filename(c['title'])}"

                # 首次下载：获取详情
                if not folder.exists():
                    await state_mgr.log(f"[{idx + 1}] 首次下载，获取详情...")
                    try:
                        detail = await client.get_comic_info(c["_id"])
                        comic_data = detail.get("data", {}).get("comic", {})
                        folder.mkdir(parents=True, exist_ok=True)
                        meta = {
                            "_id": comic_data.get("_id"),
                            "title": comic_data.get("title"),
                            "author": comic_data.get("author"),
                            "description": comic_data.get("description"),
                            "finished": comic_data.get("finished"),
                            "categories": comic_data.get("categories", []),
                            "tags": comic_data.get("tags", []),
                            "epsCount": comic_data.get("epsCount"),
                            "pagesCount": comic_data.get("pagesCount"),
                            "thumb": comic_data.get("thumb"),
                        }
                        self._detail.save_metadata(folder, meta)
                        thumb = comic_data.get("thumb", {})
                        fs = thumb.get("fileServer", "")
                        path = thumb.get("path", "")
                        if fs and path:
                            try:
                                await download_image_async(f"{fs}/static/{path}", folder / "cover.jpg", stop_event=state_mgr.stop_event)
                            except Exception:
                                pass
                        id_map[c["_id"]] = folder
                        await state_mgr.log(f"[{idx + 1}] 详情获取完成")
                    except Exception as e:
                        await state_mgr.log(f"[{idx + 1}] SKIP: 无法获取详情 — {e}")
                        return

                await state_mgr.log(f"\n{'=' * 60}")
                await state_mgr.log(f"[{idx + 1}/{len(comics)}] {c['title']} ({c.get('epsCount', '?')}话)")
                await state_mgr.log(f"__PROGRESS__ {progress_n + 1}/{len(remaining)} {c['title']}")

                # 获取章节列表
                all_eps = []
                ep_page = 1
                try:
                    while True:
                        ep_data = await client.get_episodes(c["_id"], page=ep_page)
                        eps_block = ep_data.get("data", {}).get("eps", {})
                        all_eps.extend(eps_block.get("docs", []))
                        if ep_page >= eps_block.get("pages", 1):
                            break
                        ep_page += 1
                except Exception as e:
                    await state_mgr.log(f"  SKIP: 无法获取章节列表 — {e}")
                    return

                # 加载已有进度
                chapters_file = folder / "chapters.json"
                existing = {}
                if chapters_file.exists():
                    with open(chapters_file, "r", encoding="utf-8") as cf:
                        existing = {ch["order"]: ch for ch in json.load(cf).get("chapters", [])}

                ep_lock = asyncio.Lock()
                total_eps = len(all_eps)
                completed_eps = [0]  # 用列表包装，方便 nonlocal 修改

                async def _download_chapter(ep):
                    if state_mgr.stop_event.is_set():
                        return None
                    order = ep["order"]
                    ep_title = ep.get("title", f"第{order}话")
                    ep_folder = folder / safe_filename(ep_title, max_len=40)
                    ep_folder.mkdir(parents=True, exist_ok=True)

                    # 获取图片元数据
                    all_pages = []
                    pg_page = 1
                    total_pages = 0
                    try:
                        while True:
                            pg_data = await client.get_pages(c["_id"], order, page=pg_page)
                            pages_block = pg_data.get("data", {}).get("pages", {})
                            docs = pages_block.get("docs", [])
                            all_pages.extend(docs)
                            total_pages = pages_block.get("total", 0)
                            if pg_page >= pages_block.get("pages", 1):
                                break
                            pg_page += 1
                    except Exception as e:
                        await state_mgr.log(f"  第{order:02d}话 SKIP: 无法获取图片列表 — {e}")
                        return {"order": order, "title": ep_title, "totalPages": 0, "downloaded": 0, "error": f"API错误-图片列表: {e}"}

                    async with ep_lock:
                        prev = existing.get(order, {})
                    if prev.get("downloaded", 0) >= total_pages and total_pages > 0:
                        return None

                    # 下载图片 — worker pool，最多 page_concurrency 个协程
                    downloaded = prev.get("downloaded", 0)
                    failed = 0
                    dl_lock = asyncio.Lock()

                    async def _dl_one(pi: int, p: dict):
                        nonlocal downloaded, failed
                        if state_mgr.stop_event.is_set():
                            return
                        media = p.get("media", {})
                        fs = media.get("fileServer", "")
                        pv = media.get("path", "")
                        if not fs or not pv:
                            return
                        img_url = f"{fs}/static/{pv}"
                        if image_quality == "original":
                            img_url = _to_original_url(fs, pv)
                        ext = Path(pv.split("?")[0]).suffix or ".jpg"
                        img_path = ep_folder / f"{pi + 1:03d}{ext}"
                        if img_path.exists() and img_path.stat().st_size > 0:
                            async with dl_lock:
                                downloaded += 1
                            return
                        try:
                            await download_image_async(img_url, img_path, stop_event=state_mgr.stop_event)
                            async with dl_lock:
                                downloaded += 1
                                total = len(all_pages)
                                await state_mgr.log(f"  [{downloaded}/{total}] {ep_title}")
                                await state_mgr.log(f"__PROGRESS__ {completed_eps[0]}/{total_eps} {c['title']} — {ep_title} {downloaded}/{total}P")
                        except Exception as e:
                            await state_mgr.log(f"    [{pi + 1}/{len(all_pages)}] ERROR: {e}")
                            async with dl_lock:
                                failed += 1

                    page_queue = asyncio.Queue()
                    for pi, p in enumerate(all_pages):
                        await page_queue.put((pi, p))

                    async def _page_worker():
                        while not page_queue.empty():
                            if state_mgr.stop_event.is_set():
                                return
                            try:
                                pi, p = page_queue.get_nowait()
                            except asyncio.QueueEmpty:
                                return
                            await _dl_one(pi, p)

                    page_workers = [asyncio.create_task(_page_worker()) for _ in range(page_concurrency)]
                    await asyncio.gather(*page_workers)

                    await state_mgr.log(f"  第{order:02d}话 完成: {downloaded}/{total_pages}P")
                    completed_eps[0] += 1
                    await state_mgr.log(f"__PROGRESS__ {completed_eps[0]}/{total_eps} {c['title']}")
                    entry = {"order": order, "title": ep_title, "totalPages": total_pages, "downloaded": downloaded}
                    if failed > 0:
                        entry["error"] = f"{failed}张图片下载失败"
                    async with ep_lock:
                        existing[order] = entry
                        progress_data = {
                            "comicId": c["_id"],
                            "title": c["title"],
                            "chapters": sorted(existing.values(), key=lambda x: x["order"]),
                        }
                        with open(chapters_file, "w", encoding="utf-8") as cf:
                            json.dump(progress_data, cf, indent=2, ensure_ascii=False)
                    return entry

                # 章节 worker pool：只创建 chapter_concurrency 个 task，不会撑爆事件循环
                chapter_queue = asyncio.Queue()
                for ep in all_eps:
                    await chapter_queue.put(ep)

                async def _chapter_worker():
                    while not chapter_queue.empty():
                        if state_mgr.stop_event.is_set():
                            return
                        try:
                            ep = chapter_queue.get_nowait()
                        except asyncio.QueueEmpty:
                            return
                        await _download_chapter(ep)

                chapter_workers = [asyncio.create_task(_chapter_worker()) for _ in range(chapter_concurrency)]
                await asyncio.gather(*chapter_workers)

                # 只有每话都下完才算真正完成
                all_done = all(
                    ch.get("downloaded", 0) >= ch.get("totalPages", 1)
                    for ch in existing.values()
                )
                if all_done and existing and not state_mgr.stop_event.is_set():
                    self._progress.mark_completed(cid or f"idx_{idx}", len(comics))
                    await state_mgr.log(f"完成: {c['title']}")
                else:
                    done_count = sum(1 for ch in existing.values() if ch.get("downloaded", 0) >= ch.get("totalPages", 1))
                    await state_mgr.log(f"部分完成: {done_count}/{len(existing)}话 {c['title']}")

            # 漫画级 worker pool（替代 asyncio.gather，限制同时创建的协程数）
            comic_queue = asyncio.Queue()
            for pn, i in enumerate(remaining):
                await comic_queue.put((pn, i))

            async def _comic_worker():
                while not comic_queue.empty():
                    if state_mgr.stop_event.is_set():
                        return
                    try:
                        pn, i = comic_queue.get_nowait()
                    except asyncio.QueueEmpty:
                        return
                    async with comic_sem:
                        await _do_comic(pn, i)

            comic_workers = [asyncio.create_task(_comic_worker()) for _ in range(comic_concurrency)]
            await asyncio.gather(*comic_workers)

        except asyncio.CancelledError:
            for w in comic_workers:
                if not w.done():
                    w.cancel()
            await state_mgr.log("__STOPPED__ 下载已终止")
            raise
        except Exception as e:
            await state_mgr.log(f"ERROR: {e}")
        finally:
            from app.core.file_utils import close_image_client
            await client.close()
            await close_image_client()
            async with state_mgr.lock:
                state_mgr.state.running = False
                state_mgr.state.current = ""
            await state_mgr.log_queue.put("__DONE__")
