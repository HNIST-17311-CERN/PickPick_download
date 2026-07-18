"""SQLite 数据库 — 初始化 + 连接管理"""
from pathlib import Path

import aiosqlite

DB_PATH = Path("pica.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS comics (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    author      TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    finished    INTEGER NOT NULL DEFAULT 0,
    categories  TEXT NOT NULL DEFAULT '[]',
    tags        TEXT NOT NULL DEFAULT '[]',
    folder_path TEXT NOT NULL DEFAULT '',
    cover_path  TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS chapters (
    comic_id    TEXT NOT NULL REFERENCES comics(id) ON DELETE CASCADE,
    "order"     INTEGER NOT NULL,
    title       TEXT NOT NULL DEFAULT '',
    page_count  INTEGER NOT NULL DEFAULT 0,
    folder_name TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (comic_id, "order")
);

CREATE INDEX IF NOT EXISTS idx_chapters_comic ON chapters(comic_id);
"""


async def init_db() -> None:
    """首次运行时建表"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(SCHEMA)
        await db.commit()


async def get_db() -> aiosqlite.Connection:
    """获取数据库连接"""
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA foreign_keys = ON")
    return db
