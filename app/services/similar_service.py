"""相似推荐业务逻辑"""
import asyncio
import json
from pathlib import Path

from app.core.vector_store import VectorStore
from app.services.config_service import get_detail_dir


class SyncStateManager:
    def __init__(self):
        self.running = False
        self.lock = asyncio.Lock()
        self.log_queue: asyncio.Queue[str] = asyncio.Queue()
        self._task: asyncio.Task | None = None

    async def log(self, msg: str) -> None:
        await self.log_queue.put(msg)

    async def start(self) -> None:
        async with self.lock:
            self.running = True
        while not self.log_queue.empty():
            try:
                self.log_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

    async def stop(self) -> None:
        async with self.lock:
            self.running = False
        await self.log_queue.put("__DONE__")

    async def get_status(self) -> dict:
        async with self.lock:
            return {"running": self.running}


_sync_state: SyncStateManager | None = None


def get_sync_state() -> SyncStateManager:
    global _sync_state
    if _sync_state is None:
        _sync_state = SyncStateManager()
    return _sync_state


class SimilarService:
    def __init__(self):
        self._store = VectorStore()

    def get_similar(self, folder_name: str, top_k: int = 18) -> dict:
        detail_dir = get_detail_dir()
        folder = detail_dir / folder_name
        if not folder.is_dir():
            return {"error": "漫画不存在", "items": []}

        hits = self._store.search_by_folder(folder_name, top_k)
        items = []
        for h in hits:
            has_cover = (detail_dir / h["folder"] / "cover.jpg").exists()
            items.append({
                "folder": h["folder"],
                "title": h["title"],
                "author": h["author"],
                "categories": h["categories"],
                "eps_count": h["eps_count"],
                "similarity": h["similarity"],
                "has_cover": has_cover,
            })
        return {"items": items, "source": folder_name}

    async def start_sync(self) -> dict:
        state = get_sync_state()
        if state.running:
            return {"ok": False, "detail": "同步已在运行"}

        await state.start()
        state._task = asyncio.create_task(self._run_sync())
        return {"ok": True}

    async def _run_sync(self) -> None:
        state = get_sync_state()
        loop = asyncio.get_running_loop()
        detail_dir = get_detail_dir()

        total = sum(1 for d in detail_dir.glob("*") if d.is_dir())
        await state.log(f"共 {total} 部本地漫画，开始同步...")

        def _do_sync() -> int:
            store = VectorStore()
            folders = sorted([d for d in detail_dir.glob("*") if d.is_dir()], reverse=True)
            count = 0
            for i, d in enumerate(folders):
                mp = d / "metadata.json"
                if not mp.exists():
                    continue
                try:
                    with open(mp, "r", encoding="utf-8") as f:
                        meta = json.load(f)
                    store.upsert(
                        folder=d.name,
                        title=meta.get("title", ""),
                        author=meta.get("author", ""),
                        categories=meta.get("categories", []),
                        tags=meta.get("tags", []),
                        description=meta.get("description", ""),
                        eps_count=meta.get("epsCount", 0),
                    )
                    count += 1
                    asyncio.run_coroutine_threadsafe(
                        state.log(f"  [{i + 1}/{total}] 已同步 {count} 部  {d.name}"),
                        loop,
                    )
                except Exception:
                    pass
            return count

        try:
            count = await asyncio.to_thread(_do_sync)
            await state.log(f"__RESULT__ 同步完成，共 {count} 部漫画")
        except Exception as e:
            await state.log(f"__ERROR__ {e}")
        finally:
            await state.stop()

    def get_stats(self) -> dict:
        detail_dir = get_detail_dir()
        local_count = len([d for d in detail_dir.glob("*") if d.is_dir()]) if detail_dir.exists() else 0
        vector_count = self._store.count()
        return {
            "local_count": local_count,
            "vector_count": vector_count,
            "synced": vector_count >= local_count,
        }
