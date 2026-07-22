"""下载进度 — download_progress.json + chapters.json"""
import json
import time
from pathlib import Path


class DownloadProgressRepo:
    """download_progress.json — 全局下载进度"""

    def __init__(self, path: Path = Path("download_progress.json")):
        self._path = path

    def load(self) -> dict:
        if not self._path.exists():
            return {"total": 0, "completed": [], "last_update": ""}
        with open(self._path, "r", encoding="utf-8") as f:
            return json.load(f)

    def save(self, data: dict) -> None:
        data["last_update"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def get_completed_ids(self) -> set[str]:
        return set(self.load().get("completed", []))

    def mark_completed(self, comic_id: str, total: int) -> None:
        """添加 comic_id 到已完成列表"""
        data = self.load()
        completed = set(data.get("completed", []))
        completed.add(comic_id)
        self.save({"total": total, "completed": sorted(completed)})


class DownloadQueueRepo:
    """download_queue.json — 手动下载队列"""

    def __init__(self, path: Path = Path("download_queue.json")):
        self._path = path

    def load(self) -> dict:
        if not self._path.exists():
            return {"ids": []}
        with open(self._path, "r", encoding="utf-8") as f:
            return json.load(f)

    def save(self, data: dict) -> None:
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def get_ids(self) -> list[str]:
        return self.load().get("ids", [])

    def add(self, comic_id: str) -> None:
        data = self.load()
        ids = data.get("ids", [])
        if comic_id not in ids:
            ids.append(comic_id)
        self.save({"ids": ids})

    def remove(self, comic_id: str) -> None:
        data = self.load()
        ids = [i for i in data.get("ids", []) if i != comic_id]
        self.save({"ids": ids})

    def clear(self) -> None:
        self.save({"ids": []})
