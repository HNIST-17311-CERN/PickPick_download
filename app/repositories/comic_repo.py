"""漫画元数据 — comics_metadata.json + comics_detail/* 文件系统"""
import asyncio
import json
import time
from pathlib import Path

from app.services.config_service import get_detail_dir

DETAIL_DIR = get_detail_dir()


class ComicsMetadataRepo:
    """comics_metadata.json — API 收藏缓存"""

    def __init__(self, path: Path = Path("comics_metadata.json")):
        self._path = path

    def load_all(self) -> list[dict]:
        if not self._path.exists():
            return []
        with open(self._path, "r", encoding="utf-8") as f:
            return json.load(f)

    def save_all(self, comics: list[dict]) -> None:
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(comics, f, indent=2, ensure_ascii=False)

    async def load_all_async(self) -> list[dict]:
        return await asyncio.to_thread(self.load_all)

    def get_all_ids(self) -> set[str]:
        return {c["_id"] for c in self.load_all() if "_id" in c}


class ComicsDetailRepo:
    """comics_detail/* — 本地漫画文件夹"""

    def __init__(self, base_dir: Path | None = None):
        self._base = base_dir or get_detail_dir()

    async def list_folders(self) -> list[Path]:
        if not self._base.exists():
            return []
        return sorted(
            [d for d in await asyncio.to_thread(lambda: list(self._base.glob("*"))) if d.is_dir()],
            reverse=True,
        )

    def read_metadata(self, folder: Path) -> dict | None:
        mp = folder / "metadata.json"
        if not mp.exists():
            return None
        with open(mp, "r", encoding="utf-8") as f:
            return json.load(f)

    async def read_metadata_async(self, folder: Path) -> dict | None:
        return await asyncio.to_thread(self.read_metadata, folder)

    def read_chapters(self, folder: Path) -> list[dict]:
        cf = folder / "chapters.json"
        if not cf.exists():
            return []
        with open(cf, "r", encoding="utf-8") as f:
            return json.load(f).get("chapters", [])

    def save_metadata(self, folder: Path, meta: dict) -> None:
        folder.mkdir(parents=True, exist_ok=True)
        with open(folder / "metadata.json", "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)

    def save_chapters(self, folder: Path, chapters: list[dict], comic_id: str = "", title: str = "") -> None:
        with open(folder / "chapters.json", "w", encoding="utf-8") as f:
            json.dump(
                {"comicId": comic_id, "title": title, "chapters": chapters},
                f,
                indent=2,
                ensure_ascii=False,
            )

    def has_cover(self, folder: Path) -> bool:
        return (folder / "cover.jpg").exists()

    def delete_folder(self, folder_name: str) -> None:
        import shutil
        fp = self._base / folder_name
        if fp.is_dir():
            shutil.rmtree(fp)

    async def delete_folder_async(self, folder_name: str) -> None:
        await asyncio.to_thread(self.delete_folder, folder_name)

    def folder_count(self) -> int:
        if not self._base.exists():
            return 0
        return len([d for d in self._base.glob("*") if d.is_dir()])


class LastSeenRepo:
    """comics_last_seen.json — 新漫画追踪"""

    def __init__(self, path: Path = Path("comics_last_seen.json")):
        self._path = path

    def get_seen_ids(self) -> set[str]:
        if not self._path.exists():
            return set()
        return set(json.loads(self._path.read_text(encoding="utf-8")).get("ids", []))

    def get_new_ids(self, current_ids: set[str]) -> set[str]:
        seen = self.get_seen_ids()
        return current_ids - seen

    def mark_all_seen(self, ids: list[str]) -> None:
        self._path.write_text(
            json.dumps(
                {"ids": ids, "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S")},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
