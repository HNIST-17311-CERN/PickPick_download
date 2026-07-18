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
