"""本地漫画仓库 — SQLite CRUD"""
import json
import uuid
from pathlib import Path

from app.core.database import get_db


class LocalComicRepo:

    async def list_all(self, page: int = 1, per_page: int = 35, category: str = "",
                       search: str = "") -> dict:
        where = []
        params = []
        if category:
            where.append("categories LIKE ?")
            params.append(f'%"{category}"%')
        if search:
            where.append("(title LIKE ? OR author LIKE ? OR categories LIKE ? OR tags LIKE ? OR description LIKE ?)")
            s = f"%{search}%"
            params.extend([s, s, s, s, s])
        where_clause = f"WHERE {' AND '.join(where)}" if where else ""
        offset = (page - 1) * per_page

        async with await get_db() as db:
            rows = await db.execute_fetchall(
                f"""SELECT c.*,
                    (SELECT COUNT(*) FROM chapters WHERE comic_id=c.id) AS ch_count,
                    (SELECT COALESCE(SUM(page_count),0) FROM chapters WHERE comic_id=c.id) AS total_pages
                FROM comics c {where_clause}
                ORDER BY c.created_at DESC
                LIMIT ? OFFSET ?""",
                [*params, per_page, offset],
            )
            total_row = await db.execute_fetchall(
                f"SELECT COUNT(*) FROM comics c {where_clause}", params
            )
        total = total_row[0][0] if total_row else 0

        return {
            "items": [self._row_to_dict(r) for r in rows],
            "total": total,
            "page": page,
            "per_page": per_page,
        }

    async def get(self, comic_id: str) -> dict | None:
        async with await get_db() as db:
            row = await db.execute_fetchall(
                """SELECT c.*,
                    (SELECT COUNT(*) FROM chapters WHERE comic_id=c.id) AS ch_count,
                    (SELECT COALESCE(SUM(page_count),0) FROM chapters WHERE comic_id=c.id) AS total_pages
                FROM comics c WHERE c.id=?""",
                (comic_id,),
            )
            if not row:
                return None
            comic = self._row_to_dict(row[0])
            ch_rows = await db.execute_fetchall(
                'SELECT * FROM chapters WHERE comic_id=? ORDER BY "order"', (comic_id,)
            )
            comic["chapters"] = [dict(r) for r in ch_rows]
            return comic

    async def add(self, folder_path: Path | str) -> dict | None:
        """扫描文件夹，添加一部本地漫画"""
        folder = Path(folder_path)
        if not folder.is_dir():
            return None
        comic_id = str(uuid.uuid4())
        title = folder.name
        cover_path = folder.name + "/cover.jpg" if (folder / "cover.jpg").exists() else ""
        if not cover_path and (folder / "cover.png").exists():
            cover_path = folder.name + "/cover.png"

        chapters = []
        for ch_dir in sorted(folder.iterdir()):
            if not ch_dir.is_dir():
                continue
            imgs = [f for f in ch_dir.iterdir()
                    if f.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp", ".gif")]
            if not imgs:
                continue
            chapters.append({
                "comic_id": comic_id,
                "order": len(chapters) + 1,
                "title": ch_dir.name,
                "page_count": len(imgs),
                "folder_name": ch_dir.name,
            })

        if not chapters:
            return None

        async with await get_db() as db:
            await db.execute(
                """INSERT INTO comics (id, title, folder_path, cover_path)
                VALUES (?, ?, ?, ?)""",
                (comic_id, title, str(folder), cover_path),
            )
            for ch in chapters:
                await db.execute(
                    """INSERT INTO chapters (comic_id, "order", title, page_count, folder_name)
                    VALUES (?, ?, ?, ?, ?)""",
                    (ch["comic_id"], ch["order"], ch["title"], ch["page_count"], ch["folder_name"]),
                )
            await db.commit()

        comic = await self.get(comic_id)
        return comic

    async def update(self, comic_id: str, data: dict) -> bool:
        fields = ["title", "author", "description", "finished", "categories", "tags", "folder_path", "cover_path"]
        updates = []
        params = []
        for f in fields:
            if f in data:
                updates.append(f"{f}=?")
                val = data[f]
                params.append(json.dumps(val, ensure_ascii=False) if isinstance(val, list) else val)
        if not updates:
            return False
        params.append(comic_id)
        params.append(comic_id)
        updates.append("updated_at=datetime('now','localtime')")
        async with await get_db() as db:
            await db.execute(
                f"UPDATE comics SET {', '.join(updates)} WHERE id=?",
                params,
            )
            await db.commit()
        return True

    async def delete(self, comic_id: str) -> bool:
        async with await get_db() as db:
            cursor = await db.execute("DELETE FROM comics WHERE id=?", (comic_id,))
            await db.commit()
            return cursor.rowcount > 0

    async def get_categories(self) -> list[str]:
        async with await get_db() as db:
            rows = await db.execute_fetchall("SELECT DISTINCT categories FROM comics")
        cats: set[str] = set()
        for r in rows:
            try:
                for c in json.loads(r[0]):
                    cats.add(c)
            except (json.JSONDecodeError, TypeError):
                pass
        return sorted(cats)

    async def bulk_add(self, root_dir: Path | str) -> int:
        """批量扫描根目录，添加所有子文件夹为漫画"""
        root = Path(root_dir)
        if not root.is_dir():
            return 0
        added = 0
        for folder in sorted(root.iterdir()):
            if folder.is_dir():
                result = await self.add(folder)
                if result:
                    added += 1
        return added

    def _row_to_dict(self, row) -> dict:
        d = dict(row)
        for key in ("categories", "tags"):
            if key in d and isinstance(d[key], str):
                try:
                    d[key] = json.loads(d[key])
                except (json.JSONDecodeError, TypeError):
                    d[key] = []
        return d
