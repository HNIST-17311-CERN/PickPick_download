"""
哔咔漫画 API 客户端
用法：
    python manga_api.py favourites     # 获取全部收藏漫画
    python manga_api.py covers         # 下载全部收藏封面
    python manga_api.py comic <id>     # 获取漫画详情
"""

import sys
import json
import time
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.request import Request, urlopen, ProxyHandler, build_opener, install_opener
from urllib.error import HTTPError, URLError
from http.client import RemoteDisconnected, IncompleteRead

import yaml

from app.core.signature import compute_signature


# ===== API 客户端 =====

class PicaClient:
    """哔咔漫画 Web API 客户端"""

    def __init__(self, config: dict):
        self.base = config.get("api_base", "https://picaapi.go2778.com")
        self.token = config.get("token", "")
        self.nonce = config.get("nonce", "")
        self.request_delay = config.get("request_delay", 1.5)

    def _build_headers(self, path: str, method: str = "GET") -> dict:
        ts = str(int(time.time()))
        sig = compute_signature(path, ts, self.nonce, method)
        return {
            "accept": "application/vnd.picacomic.com.v1+json",
            "app-channel": "1",
            "app-platform": "android",
            "app-uuid": "webUUIDv2",
            "app-version": "20251017",
            "authorization": self.token,
            "content-type": "application/json; charset=UTF-8",
            "image-quality": "medium",
            "nonce": self.nonce,
            "origin": "https://manhuapica.com",
            "referer": "https://manhuapica.com/",
            "signature": sig,
            "time": ts,
            "user-agent": "Mozilla/5.0 (Linux; Android 15; Pixel 9) AppleWebKit/537.36",
        }

    def _request(self, path: str, method: str = "GET", data: dict = None, max_retries: int = 30) -> dict:
        url = self.base + path
        body = json.dumps(data).encode() if data else None

        for attempt in range(max_retries):
            try:
                headers = self._build_headers(path, method)
                req = Request(url, data=body, headers=headers, method=method)
                with urlopen(req, timeout=30) as resp:
                    result = json.loads(resp.read().decode("utf-8"))
                    return result
            except HTTPError as e:
                body_text = e.read().decode("utf-8", errors="replace")
                if e.code in (500, 502, 503, 504):
                    pass  # 5xx 临时故障，重试
                else:
                    raise RuntimeError(f"HTTP {e.code}: {body_text[:500]}")
            except (RemoteDisconnected, IncompleteRead, URLError, ConnectionResetError, TimeoutError):
                pass

            if attempt < max_retries - 1:
                if attempt < 3:
                    wait = (2 ** attempt) * 2  # 2s, 4s, 8s
                else:
                    wait = 600  # 10分钟
                print(f"  [等待{wait}秒后重试，第{attempt+1}/{max_retries}次]")
                # 分段等待，可被停止信号中断
                for _ in range(wait):
                    if _download_stop_flag:
                        print("  [用户手动停止]")
                        return {"code": -1, "message": "stopped"}
                    time.sleep(1)

        raise RuntimeError(f"请求失败（已重试{max_retries}次）: {url}")

    # ---- 收藏列表 ----
    def get_favourites(self, page: int = 1, sort: str = "dd", limit: int = 20) -> dict:
        path = f"/users/favourite?page={page}&s={sort}&limit={limit}"
        return self._request(path)

    def get_all_favourites(self, sort: str = "dd") -> list[dict]:
        """获取全部收藏漫画"""
        comics = []
        page = 1
        while True:
            data = self.get_favourites(page=page, sort=sort)
            page_data = data.get("data", {}).get("comics", {})
            items = page_data.get("docs", [])
            total_pages = page_data.get("pages", 1)
            total = page_data.get("total", 0)
            comics.extend(items)
            print(f"第 {page}/{total_pages} 页 ({len(comics)}/{total})")
            if page >= total_pages:
                break
            page += 1
            time.sleep(self.request_delay)
        return comics

    # ---- 漫画详情 ----
    def get_comic_info(self, comic_id: str) -> dict:
        return self._request(f"/comics/{comic_id}")

    # ---- 章节列表 ----
    def get_episodes(self, comic_id: str, page: int = 1) -> dict:
        return self._request(f"/comics/{comic_id}/eps?page={page}")

    # ---- 章节图片 ----
    def get_pages(self, comic_id: str, ep_order: int, page: int = 1) -> dict:
        return self._request(f"/comics/{comic_id}/order/{ep_order}/pages?page={page}")

    # ---- 搜索 ----
    def search(self, keyword: str, page: int = 1, sort: str = "dd") -> dict:
        return self._request(f"/comics/advanced-search?page={page}&s={sort}&keyword={keyword}")

    # ---- 分类列表 ----
    def get_categories(self) -> dict:
        return self._request("/categories")

    # ---- 登录 ----
    def login(self, email: str, password: str) -> dict:
        """模拟 App 登录，返回包含 token 的响应"""
        return self._request("/auth/sign-in", method="POST", data={
            "email": email,
            "password": password,
        })


# ===== 下载工具 =====

def download_image(url: str, filepath: Path, max_retries: int = 3) -> bool:
    """下载单张图片（自动重试）"""
    if filepath.exists():
        return False
    for attempt in range(max_retries):
        try:
            req = Request(url, headers={
                "Referer": "https://manhuapica.com/",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            })
            with urlopen(req, timeout=30) as resp:
                filepath.write_bytes(resp.read())
            return True
        except Exception:
            if attempt < max_retries - 1:
                time.sleep(1)
    raise RuntimeError(f"下载失败（已重试{max_retries}次）")


def _build_image_url(thumb: dict) -> str:
    """从 thumb 对象拼接完整图片 URL"""
    url = thumb.get("url") or thumb.get("proxyUrl", "")
    if url:
        return url
    fs = thumb.get("fileServer", "")
    path = thumb.get("path", "")
    if fs and path:
        return f"{fs}/static/{path}"
    return ""


def download_covers(comics: list[dict], output_dir: str):
    """下载漫画封面"""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    for i, comic in enumerate(comics):
        url = _build_image_url(comic.get("thumb", {}))
        if not url:
            print(f"[{i+1}/{len(comics)}] SKIP: {comic.get('title', '?')} — 无封面")
            continue

        safe_title = re.sub(r'[\\/:*?"<>|]', "_", comic.get("title", "unknown"))[:80]
        ext = Path(url.split("?")[0]).suffix or ".jpg"
        filename = f"{i+1:03d}_{safe_title}{ext}"
        filepath = out / filename

        try:
            is_new = download_image(url, filepath)
            status = "NEW" if is_new else "SKIP"
            print(f"[{i+1}/{len(comics)}] {status}  {comic.get('title', '?')}")
        except Exception as e:
            print(f"[{i+1}/{len(comics)}] ERROR: {e}")


def download_chapter(comic_title: str, chapter: dict, output_dir: Path, client: PicaClient):
    """下载单话全部图片"""
    comic_id = chapter.get("comicId") or chapter["_id"]
    ep_order = chapter.get("order", 1)
    ep_title = chapter.get("title", f"第{ep_order}话")

    safe_comic = re.sub(r'[\\/:*?"<>|]', "_", comic_title)[:50]
    safe_ep = re.sub(r'[\\/:*?"<>|]', "_", ep_title)[:50]
    chapter_dir = output_dir / safe_comic / f"{ep_order:03d}_{safe_ep}"
    chapter_dir.mkdir(parents=True, exist_ok=True)

    all_pages = []
    page = 1
    while True:
        data = client.get_pages(comic_id, ep_order, page)
        pages_data = data.get("data", {}).get("pages", {})
        docs = pages_data.get("docs", [])
        all_pages.extend(docs)
        if page >= pages_data.get("pages", 1):
            break
        page += 1
        time.sleep(client.request_delay)

    for i, p in enumerate(all_pages):
        media = p.get("media", {})
        url = f"{media.get('fileServer', '')}/static/{media.get('path', '')}"
        if not url.startswith("http"):
            continue

        ext = Path(media.get("path", ".jpg")).suffix or ".jpg"
        filepath = chapter_dir / f"{i+1:03d}{ext}"

        try:
            download_image(url, filepath)
            print(f"  [{i+1}/{len(all_pages)}] {comic_title} - {ep_title}")
        except Exception as e:
            print(f"  [{i+1}/{len(all_pages)}] ERROR: {e}")
        time.sleep(0.3)

    print(f"  完成: {chapter_dir}")


def safe_print(s: str):
    """防止 Windows GBK 终端报错"""
    try:
        print(s)
    except UnicodeEncodeError:
        print(s.encode("ascii", errors="replace").decode("ascii"))


def safe_filename(name: str, max_len: int = 60) -> str:
    """清洗文件名，移除非法字符和首尾空格"""
    name = name.strip().rstrip(".")
    name = re.sub(r'[\\/:*?"<>|]', "_", name)
    name = re.sub(r'\s+', " ", name)
    return name[:max_len].strip()


def cmd_detail_all(client: PicaClient):
    """获取每部漫画详情，创建文件夹存封面+JSON"""
    with open("comics_metadata.json", "r", encoding="utf-8") as f:
        comics = json.load(f)

    base = Path("comics_detail")
    base.mkdir(parents=True, exist_ok=True)

    for i, c in enumerate(comics):
        safe_title = safe_filename(c["title"])
        folder = base / f"{i+1:03d}_{safe_title}"
        folder.mkdir(parents=True, exist_ok=True)

        metadata_path = folder / "metadata.json"
        cover_path = folder / "cover.jpg"

        # 已存在则跳过
        if metadata_path.exists() and cover_path.exists():
            safe_print(f"[{i+1}/{len(comics)}] SKIP: {c['title']}")
            continue

        try:
            detail = client.get_comic_info(c["_id"])
            comic_data = detail.get("data", {}).get("comic", {})

            metadata = {
                "_id": comic_data.get("_id"),
                "title": comic_data.get("title"),
                "author": comic_data.get("author"),
                "chineseTeam": comic_data.get("chineseTeam"),
                "description": comic_data.get("description"),
                "finished": comic_data.get("finished"),
                "status": "已完结" if comic_data.get("finished") else "连载中",
                "language": "中文",
                "updated_at": comic_data.get("updated_at"),
                "created_at": comic_data.get("created_at"),
                "pagesCount": comic_data.get("pagesCount"),
                "epsCount": comic_data.get("epsCount"),
                "totalViews": comic_data.get("totalViews"),
                "totalLikes": comic_data.get("totalLikes"),
                "categories": comic_data.get("categories", []),
                "tags": comic_data.get("tags", []),
                "thumb": comic_data.get("thumb"),
            }

            with open(metadata_path, "w", encoding="utf-8") as mf:
                json.dump(metadata, mf, indent=2, ensure_ascii=False)

            if not cover_path.exists():
                thumb = comic_data.get("thumb", {})
                cover_url = _build_image_url(thumb)
                if cover_url:
                    download_image(cover_url, cover_path)

            safe_print(f"[{i+1}/{len(comics)}] OK: {c['title']}")

        except Exception as e:
            safe_print(f"[{i+1}/{len(comics)}] ERROR: {c['title']} — {e}")

        time.sleep(client.request_delay)

    safe_print(f"\n完成！共 {len(comics)} 部，保存在 {base.absolute()}")


def cmd_check():
    """检查下载进度——扫描文件夹用 _id 匹配，生成 download_progress.json"""
    with open("comics_metadata.json", "r", encoding="utf-8") as f:
        comics = json.load(f)

    detail_base = Path("comics_detail")

    # 构建 _id → folder 映射
    id_map = {}
    if detail_base.exists():
        for d in detail_base.glob("*"):
            if not d.is_dir():
                continue
            mp = d / "metadata.json"
            if not mp.exists():
                continue
            try:
                with open(mp, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                cid = meta.get("_id")
                if cid:
                    id_map[cid] = d
            except Exception:
                pass

    completed = []
    incomplete = []
    missing_detail = []

    for idx in range(len(comics)):
        c = comics[idx]
        cid = c.get("_id", "")

        folder = id_map.get(cid) or detail_base / f"{idx+1:03d}_{safe_filename(c['title'])}"
        chapters_file = folder / "chapters.json"

        if not folder.exists() or cid not in id_map:
            missing_detail.append(cid or f"idx_{idx}")
            continue

        if not chapters_file.exists():
            incomplete.append(cid or f"idx_{idx}")
            continue

        with open(chapters_file, "r", encoding="utf-8") as cf:
            ch_data = json.load(cf)

        chapters = ch_data.get("chapters", [])
        all_done = all(
            ch.get("downloaded", 0) >= ch.get("totalPages", 1)
            for ch in chapters
        )
        if all_done and chapters:
            completed.append(cid or f"idx_{idx}")
        else:
            incomplete.append(cid or f"idx_{idx}")

    progress = {
        "total": len(comics),
        "completed": completed,
        "incomplete": incomplete,
        "missing_detail": missing_detail,
        "last_update": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    with open("download_progress.json", "w", encoding="utf-8") as f:
        json.dump(progress, f, indent=2, ensure_ascii=False)

    safe_print(f"总漫画: {len(comics)}")
    safe_print(f"文件夹映射: {len(id_map)}")
    safe_print(f"已完成: {len(completed)}")
    safe_print(f"未完成: {len(incomplete)}")
    safe_print(f"缺少详情: {len(missing_detail)}")
    safe_print("进度已保存到 download_progress.json")


_download_stop_flag = False

def stop_download():
    global _download_stop_flag
    _download_stop_flag = True

def cmd_download(client: PicaClient, target: str, page_concurrency: int = 3, chapter_concurrency: int = 1):
    """下载漫画图片（自动跳过已完成）"""
    global _download_stop_flag
    _download_stop_flag = False

    with open("comics_metadata.json", "r", encoding="utf-8") as f:
        comics = json.load(f)

    # 解析目标范围
    if target == "all":
        indices = list(range(len(comics)))
    elif "-" in target:
        parts = target.split("-")
        start, end = int(parts[0]) - 1, int(parts[1]) - 1
        indices = list(range(max(0, start), min(len(comics), end + 1)))
    else:
        idx = int(target) - 1
        indices = [idx]

    # 加载全局进度，用 _id 匹配跳过已完成
    progress_file = Path("download_progress.json")
    completed_ids = set()
    if progress_file.exists():
        with open(progress_file, "r", encoding="utf-8") as pf:
            completed_ids = set(json.load(pf).get("completed", []))

    remaining = [i for i in indices if comics[i].get("_id", f"idx_{i}") not in completed_ids]
    skipped = len(indices) - len(remaining)
    if skipped:
        safe_print(f"跳过 {skipped} 部已完成，剩余 {len(remaining)} 部")

    detail_base = Path("comics_detail")
    # 构建 _id → folder 映射
    id_map = {}
    if detail_base.exists():
        for d in detail_base.glob("*"):
            if not d.is_dir(): continue
            mp = d / "metadata.json"
            if mp.exists():
                try:
                    with open(mp, "r", encoding="utf-8") as f:
                        id_map[json.load(f).get("_id")] = d
                except Exception: pass

    total_remaining = len(remaining)
    for progress_n, idx in enumerate(remaining):
        if _download_stop_flag:
            safe_print("__STOPPED__ 用户手动停止")
            break
        c = comics[idx]
        cid = c.get("_id", "")
        folder = id_map.get(cid)
        if not folder:
            # 新漫画：编号 = total - idx（收藏第一位=最大编号，最老=001）
            new_num = len(comics) - idx
            folder = detail_base / f"{new_num:03d}_{safe_filename(c['title'])}"
        chapters_file = folder / "chapters.json"

        if not folder.exists():
            safe_print(f"[{idx+1}] 首次下载，获取详情...")
            try:
                detail = client.get_comic_info(c["_id"])
                comic_data = detail.get("data", {}).get("comic", {})
                folder.mkdir(parents=True, exist_ok=True)
                # 保存 metadata
                metadata = {
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
                with open(folder / "metadata.json", "w", encoding="utf-8") as mf:
                    json.dump(metadata, mf, indent=2, ensure_ascii=False)
                # 下载封面
                thumb = comic_data.get("thumb", {})
                fs = thumb.get("fileServer", "")
                path = thumb.get("path", "")
                if fs and path:
                    try:
                        cover_url = f"{fs}/static/{path}"
                        download_image(cover_url, folder / "cover.jpg")
                    except Exception:
                        pass
                id_map[c["_id"]] = folder
                safe_print(f"[{idx+1}] 详情获取完成")
            except Exception as e:
                safe_print(f"[{idx+1}] SKIP: 无法获取详情 — {e}")
                continue
            time.sleep(client.request_delay)

        safe_print(f"\n{'='*60}")
        safe_print(f"[{idx+1}/{len(comics)}] {c['title']} ({c.get('epsCount', '?')}话)")
        safe_print(f"__PROGRESS__ {progress_n+1}/{total_remaining} {c['title']}")

        # 获取章节列表
        all_eps = []
        ep_page = 1
        try:
            while True:
                ep_data = client.get_episodes(c["_id"], page=ep_page)
                eps_block = ep_data.get("data", {}).get("eps", {})
                all_eps.extend(eps_block.get("docs", []))
                if ep_page >= eps_block.get("pages", 1):
                    break
                ep_page += 1
        except RuntimeError as e:
            safe_print(f"  SKIP: 无法获取章节列表 — {e}")
            continue

        # 加载已有进度
        existing = {}
        if chapters_file.exists():
            with open(chapters_file, "r", encoding="utf-8") as cf:
                existing = {ch["order"]: ch for ch in json.load(cf).get("chapters", [])}

        def _download_chapter(ep):
            if _download_stop_flag:
                return None
            order = ep["order"]
            ep_title = ep.get("title", f"第{order}话")
            safe_ep = safe_filename(ep_title, max_len=40)

            ep_folder = folder / f"{order:02d}_{safe_ep}"
            ep_folder.mkdir(parents=True, exist_ok=True)

            # 获取图片元数据
            all_pages = []
            pg_page = 1
            total_pages = 0
            try:
                while True:
                    pg_data = client.get_pages(c["_id"], order, page=pg_page)
                    pages_block = pg_data.get("data", {}).get("pages", {})
                    docs = pages_block.get("docs", [])
                    all_pages.extend(docs)
                    total_pages = pages_block.get("total", 0)
                    if pg_page >= pages_block.get("pages", 1):
                        break
                    pg_page += 1
            except RuntimeError as e:
                safe_print(f"  第{order:02d}话 SKIP: 无法获取图片列表 — {e}")
                return {"order": order, "title": ep_title, "totalPages": 0, "downloaded": 0, "error": f"API错误-图片列表: {e}"}

            # 用 chapters.json 判断是否已完整
            with ep_lock:
                prev = existing.get(order, {})
            if prev.get("downloaded", 0) >= total_pages and total_pages > 0:
                safe_print(f"  第{order:02d}话 SKIP (已完整 {prev['downloaded']}/{total_pages}P)")
                return None

            # 下载图片（并发）
            downloaded = prev.get("downloaded", 0)
            failed = 0
            img_lock = threading.Lock()

            tasks = []
            for pi, p in enumerate(all_pages):
                media = p.get("media", {})
                fs = media.get("fileServer", "")
                path_val = media.get("path", "")
                if not fs or not path_val:
                    continue
                img_url = f"{fs}/static/{path_val}"
                ext = Path(path_val.split("?")[0]).suffix or ".jpg"
                img_path = ep_folder / f"{pi+1:03d}{ext}"
                if img_path.exists() and img_path.stat().st_size > 0:
                    if prev.get("downloaded", 0) == 0:
                        with img_lock:
                            downloaded += 1
                    continue
                tasks.append((pi, img_url, img_path))

            if tasks:
                safe_print(f"  第{order:02d}话: {len(all_pages)}P, 需下载 {len(tasks)} 张 (并发 {page_concurrency})")
                with ThreadPoolExecutor(max_workers=page_concurrency) as img_executor:
                    future_map = {img_executor.submit(download_image, url, path): (pi, path) for pi, url, path in tasks}
                    for future in as_completed(future_map):
                        pi, path = future_map[future]
                        try:
                            future.result()
                            with img_lock:
                                downloaded += 1
                        except Exception as e:
                            safe_print(f"    [{pi+1}/{len(all_pages)}] ERROR: {e}")
                            with img_lock:
                                failed += 1
            else:
                downloaded = total_pages

            safe_print(f"  第{order:02d}话 完成: {downloaded}/{total_pages}P")

            entry = {"order": order, "title": ep_title, "totalPages": total_pages, "downloaded": downloaded}
            if failed > 0:
                entry["error"] = f"{failed}张图片下载失败"
            with ep_lock:
                existing[order] = entry
                progress_data = {"comicId": c["_id"], "title": c["title"], "chapters": sorted(existing.values(), key=lambda x: x["order"])}
                with open(chapters_file, "w", encoding="utf-8") as cf:
                    json.dump(progress_data, cf, indent=2, ensure_ascii=False)
            return entry

        ep_lock = threading.Lock()
        with ThreadPoolExecutor(max_workers=chapter_concurrency) as ep_executor:
            futures = [ep_executor.submit(_download_chapter, ep) for ep in all_eps]
            for future in as_completed(futures):
                future.result()
                if _download_stop_flag:
                    break
                time.sleep(client.request_delay / max(chapter_concurrency, 1))

        # 该漫画全部章节完成，标记为已完成
        completed_ids.add(c.get("_id", f"idx_{idx}"))
        with open(progress_file, "w", encoding="utf-8") as pf:
            json.dump({
                "total": len(comics),
                "completed": sorted(completed_ids),
                "last_update": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }, pf, indent=2, ensure_ascii=False)

        safe_print(f"完成: {c['title']}")


# ===== CLI =====

def cmd_favourites(client: PicaClient):
    comics = client.get_all_favourites()
    with open("comics_metadata.json", "w", encoding="utf-8") as f:
        json.dump(comics, f, indent=2, ensure_ascii=False)
    print(f"\n共 {len(comics)} 部漫画，已保存到 comics_metadata.json")


def cmd_covers(client: PicaClient):
    comics = client.get_all_favourites()
    download_covers(comics, "covers")


def cmd_comic(client: PicaClient, comic_id: str):
    data = client.get_comic_info(comic_id)
    print(json.dumps(data, indent=2, ensure_ascii=False))


def cmd_renumber():
    """重命名 comics_detail 文件夹，使其序号匹配 comics_metadata.json 的当前顺序"""
    with open("comics_metadata.json", "r", encoding="utf-8") as f:
        comics = json.load(f)

    detail_base = Path("comics_detail")
    if not detail_base.exists():
        print("comics_detail 目录不存在")
        sys.exit(1)

    # 构建 _id → 当前文件夹名 映射
    id_to_folder = {}
    for d in detail_base.glob("*"):
        if not d.is_dir(): continue
        mp = d / "metadata.json"
        if mp.exists():
            try:
                with open(mp, "r", encoding="utf-8") as f:
                    cid = json.load(f).get("_id")
                if cid:
                    id_to_folder[cid] = d
            except Exception: pass

    print(f"文件夹映射: {len(id_to_folder)}")

    renames = []
    total = len(comics)
    for idx, c in enumerate(comics):
        cid = c.get("_id", "")
        folder = id_to_folder.get(cid)
        if not folder: continue

        # 编号反转：最老的=001，最新的=max
        new_num = total - idx
        new_name = f"{new_num:03d}_{safe_filename(c['title'])}"
        if folder.name == new_name: continue
        renames.append((folder, detail_base / new_name))

    if not renames:
        print("所有文件夹序号已是正确的，无需重命名")
        return

    print(f"需要重命名 {len(renames)} 个文件夹")
    answer = input("确认？[y/N] ").strip().lower()
    if answer != 'y':
        print("取消")
        return

    for old, new in renames:
        try:
            old.rename(new)
            print(f"  {old.name} → {new.name}")
        except Exception as e:
            print(f"  失败: {old.name} — {e}")

    print(f"\n完成！重命名了 {len(renames)} 个文件夹")


def cmd_login():
    """模拟登录，获取新 token 并写入 config.yaml"""
    import random
    import string

    email = input("邮箱: ").strip()
    password = input("密码: ").strip()
    if not email or not password:
        print("邮箱和密码不能为空")
        sys.exit(1)

    # 生成随机 nonce（32位小写字母数字）
    new_nonce = ''.join(random.choices(string.ascii_lowercase + string.digits, k=32))

    # 用临时 nonce 发登录请求
    client = PicaClient({"token": "", "nonce": new_nonce, "api_base": "https://picaapi.go2778.com"})
    print("正在登录...")
    try:
        resp = client.login(email, password)
    except RuntimeError as e:
        print(f"登录失败: {e}")
        sys.exit(1)

    code = resp.get("code", -1)
    if code != 200:
        msg = resp.get("message", f"未知错误 code={code}")
        print(f"登录失败: {msg}")
        sys.exit(1)

    token = resp.get("data", {}).get("token", "")
    if not token:
        print("登录失败: 响应中没有 token")
        print(json.dumps(resp, indent=2, ensure_ascii=False)[:500])
        sys.exit(1)

    # 写回 config.yaml
    with open("config.yaml", "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    config["token"] = token
    config["nonce"] = new_nonce
    with open("config.yaml", "w", encoding="utf-8") as f:
        yaml.dump(config, f, allow_unicode=True, default_flow_style=False)

    print(f"登录成功! token 已保存到 config.yaml")
    # 解析显示 token 信息
    try:
        parts = token.split(".")
        if len(parts) == 3:
            payload = json.loads(base64.urlsafe_b64decode(parts[1] + "==="))
            print(f"  用户: {payload.get('name', '?')}")
            print(f"  邮箱: {payload.get('email', '?')}")
            exp = payload.get("exp", 0)
            if exp:
                print(f"  过期: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(exp))}")
    except Exception:
        pass


def main():
    with open("config.yaml", "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    proxy = config.get("proxy", "")
    if proxy:
        install_opener(build_opener(ProxyHandler({"http": proxy, "https": proxy})))
        print(f"已启用代理: {proxy}")

    cmd = sys.argv[1] if len(sys.argv) > 1 else ""

    # login 不需要已有 token
    if cmd == "login":
        cmd_login()
        return

    if cmd == "renumber":
        cmd_renumber()
        return

    if not config.get("token") or not config.get("nonce"):
        print("错误：请在 config.yaml 中填写 token 和 nonce（或运行 python manga_api.py login）")
        sys.exit(1)

    client = PicaClient(config)

    if cmd == "favourites":
        cmd_favourites(client)
    elif cmd == "covers":
        cmd_covers(client)
    elif cmd == "comic":
        cmd_comic(client, sys.argv[2])
    elif cmd == "detail_all":
        cmd_detail_all(client)
    elif cmd == "download":
        target = sys.argv[2] if len(sys.argv) > 2 else "all"
        cmd_download(client, target, config.get("page_concurrency", 3), config.get("chapter_concurrency", 1))
    elif cmd == "check":
        cmd_check()
    else:
        print(f"未知命令: {cmd}")
        print("可用命令: favourites | covers | detail_all | download [编号] | check | login | comic <id>")


if __name__ == "__main__":
    main()
