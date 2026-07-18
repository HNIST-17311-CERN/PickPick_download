# 数据库设计

SQLite 单文件 `pica.db`。**只存本地漫画**，API 漫画保持现状（实时接口 + JSON 文件）。

---

## 表结构

### 1. `comics` — 本地漫画

```sql
CREATE TABLE comics (
    id          TEXT PRIMARY KEY,        -- UUID，本地生成
    title       TEXT NOT NULL,
    author      TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    categories  TEXT NOT NULL DEFAULT '[]',   -- JSON，如 '["冒险","热血"]'
    tags        TEXT NOT NULL DEFAULT '[]',   -- JSON
    cover_path  TEXT NOT NULL DEFAULT '',     -- 封面相对路径，如 '钢炼/cover.jpg'
    created_at  TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
```

### 2. `chapters` — 章节进度

```sql
CREATE TABLE chapters (
    comic_id    TEXT NOT NULL REFERENCES comics(id) ON DELETE CASCADE,
    "order"     INTEGER NOT NULL,        -- 序号，从1开始
    title       TEXT NOT NULL DEFAULT '',
    page_count  INTEGER NOT NULL DEFAULT 0,   -- 总页数
    folder_name TEXT NOT NULL DEFAULT '',     -- 文件夹名，如 'Vol.01'
    PRIMARY KEY (comic_id, "order")
);

CREATE INDEX idx_chapters_comic ON chapters(comic_id);
```

---

## 样例

```sql
INSERT INTO comics (id, title, author, categories, cover_path) VALUES
('a1b2c3d4-e5f6-7890-abcd-ef1234567890', '钢の錬金術師', '荒川弘', '["冒险","奇幻"]', '钢炼/cover.jpg'),
('b2c3d4e5-f6a7-8901-bcde-f12345678901', 'SLAM DUNK',    '井上雄彦', '["运动","校园"]', '灌篮高手/cover.jpg');

-- 钢炼 27卷全
INSERT INTO chapters (comic_id, "order", title, page_count, folder_name) VALUES
('a1b2c3d4-e5f6-7890-abcd-ef1234567890',  1, '第1巻',  180, 'Vol.01'),
('a1b2c3d4-e5f6-7890-abcd-ef1234567890',  2, '第2巻',  180, 'Vol.02'),
...
('a1b2c3d4-e5f6-7890-abcd-ef1234567890', 27, '第27巻', 180, 'Vol.27');

-- 灌篮高手 31卷
INSERT INTO chapters (comic_id, "order", title, page_count, folder_name) VALUES
('b2c3d4e5-f6a7-8901-bcde-f12345678901',  1, '第1巻',  188, 'Vol.01'),
('b2c3d4e5-f6a7-8901-bcde-f12345678901',  2, '第2巻',  188, 'Vol.02');
```

---

## 查询

| 需求 | SQL |
|------|-----|
| 漫画列表+章节数 | `SELECT c.*, (SELECT COUNT(*) FROM chapters WHERE comic_id=c.id) AS ch_total FROM comics c` |
| 某漫画章节 | `SELECT * FROM chapters WHERE comic_id=? ORDER BY "order"` |
| 分类列表 | `SELECT DISTINCT json_each.value FROM comics, json_each(categories)` |
| 搜索 | `SELECT * FROM comics WHERE title LIKE ? OR author LIKE ?` |
| 删除漫画 | `DELETE FROM comics WHERE id=?` (章节自动级联删除) |

---

## 分工

| | 数据库 (pica.db) | 文件系统 |
|---|---|---|
| 本地漫画元数据 | `comics` 表 | — |
| 本地章节列表 | `chapters` 表 | — |
| API 收藏数据 | — | 实时 API |
| API 下载进度 | — | `comics_detail/{folder}/chapters.json` |
| API 全局进度 | — | `download_progress.json` |
| 新增追踪 | — | `comics_last_seen.json` |
| 设置 | — | `config.yaml` |
