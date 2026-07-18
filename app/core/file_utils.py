"""文件工具函数"""
import asyncio
import re
from pathlib import Path

import httpx


def safe_filename(name: str, max_len: int = 60) -> str:
    """清洗文件名，移除非法字符和首尾空格"""
    name = name.strip().rstrip(".")
    name = re.sub(r'[\\/:*?"<>|]', "_", name)
    name = re.sub(r"\s+", " ", name)
    return name[:max_len].strip()


def safe_print(s: str):
    """防止 Windows GBK 终端报错"""
    try:
        print(s)
    except UnicodeEncodeError:
        print(s.encode("ascii", errors="replace").decode("ascii"))


def build_image_url(thumb: dict) -> str:
    """从 thumb 对象拼接完整图片 URL"""
    url = thumb.get("url") or thumb.get("proxyUrl", "")
    if url:
        return url
    fs = thumb.get("fileServer", "")
    path = thumb.get("path", "")
    if fs and path:
        return f"{fs}/static/{path}"
    return ""


_img_client: httpx.AsyncClient = None
_img_lock = asyncio.Lock()


async def _get_image_client() -> httpx.AsyncClient:
    global _img_client
    if _img_client is not None and not _img_client.is_closed:
        return _img_client
    async with _img_lock:
        if _img_client is not None and not _img_client.is_closed:
            return _img_client
        _img_client = httpx.AsyncClient(
            timeout=httpx.Timeout(15.0),
            follow_redirects=True,
            limits=httpx.Limits(max_connections=200, max_keepalive_connections=100),
            headers={
                "Referer": "https://manhuapica.com/",
                "User-Agent": "Mozilla/5.0 (Linux; Android 15; Pixel 9) AppleWebKit/537.36",
            },
        )
    return _img_client


async def close_image_client() -> None:
    global _img_client
    if _img_client is not None and not _img_client.is_closed:
        await _img_client.aclose()
        _img_client = None


async def download_image_async(
    url: str, filepath: Path, max_retries: int = 5, stop_event: asyncio.Event = None
) -> bool:
    """异步下载单张图片（自动跳过已存在文件）"""
    if filepath.exists() and filepath.stat().st_size > 0:
        return False
    client = await _get_image_client()
    last_err = ""
    for attempt in range(max_retries):
        if stop_event and stop_event.is_set():
            return False
        try:
            resp = await client.get(url)
            if resp.status_code == 200 and len(resp.content) > 0:
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, filepath.write_bytes, resp.content)
                return True
            last_err = f"HTTP {resp.status_code}"
        except Exception as e:
            last_err = f"{type(e).__name__}: {e}"
        if attempt < max_retries - 1:
            await asyncio.sleep(1)
    raise RuntimeError(f"下载失败（已重试{max_retries}次）: {url} [{last_err}]")
