"""哔咔漫画异步 API 客户端 — 基于 httpx"""
import asyncio
import json
import time
from typing import Optional

import httpx

from app.core.signature import compute_signature


class AsyncPicaClient:
    """哔咔漫画 Web API 客户端 — 异步版"""

    def __init__(
        self,
        config: dict,
        http_client: Optional[httpx.AsyncClient] = None,
        stop_event: Optional[asyncio.Event] = None,
        log_func = None,
    ):
        self.base = config.get("api_base", "https://picaapi.go2778.com")
        self.token = config.get("token", "")
        self.nonce = config.get("nonce", "")
        self.request_delay = config.get("request_delay", 1.5)
        self._http = http_client
        self._owns_client = http_client is None
        self._stop_event = stop_event
        self._log_func = log_func

    async def close(self) -> None:
        if self._owns_client and self._http is not None:
            await self._http.aclose()
            self._http = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=httpx.Timeout(30.0))
            self._owns_client = True
        return self._http

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

    async def _request(
        self,
        path: str,
        method: str = "GET",
        data: dict = None,
        max_retries: int = 30,
    ) -> dict:
        url = self.base + path
        body = json.dumps(data).encode() if data else None
        client = await self._get_client()

        for attempt in range(max_retries):
            try:
                headers = self._build_headers(path, method)
                resp = await client.request(method, url, content=body, headers=headers)
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPStatusError as e:
                if e.response.status_code in (500, 502, 503, 504):
                    pass  # 5xx 重试
                else:
                    raise RuntimeError(
                        f"HTTP {e.response.status_code}: {e.response.text[:500]}"
                    )
            except (
                httpx.RemoteProtocolError,
                httpx.ConnectError,
                httpx.TimeoutException,
            ):
                pass

            if attempt < max_retries - 1:
                wait = min((2 ** attempt) * 2, 30)  # 指数退避，上限 30 秒
                msg = f"  [API重试] 等待{wait}s后重试 (第{attempt+1}/{max_retries}次)"
                print(msg)
                if self._log_func:
                    await self._log_func(msg)
                for _ in range(wait):
                    if self._stop_event and self._stop_event.is_set():
                        print("  [用户手动停止]")
                        return {"code": -1, "message": "stopped"}
                    await asyncio.sleep(1)

        raise RuntimeError(f"请求失败（已重试{max_retries}次）: {url}")

    # ==== 收藏列表 ====

    async def get_favourites(
        self, page: int = 1, sort: str = "dd", limit: int = 20
    ) -> dict:
        return await self._request(
            f"/users/favourite?page={page}&s={sort}&limit={limit}"
        )

    async def get_all_favourites(self, sort: str = "dd") -> list[dict]:
        comics = []
        page = 1
        while True:
            data = await self.get_favourites(page=page, sort=sort)
            page_data = data.get("data", {}).get("comics", {})
            items = page_data.get("docs", [])
            total_pages = page_data.get("pages", 1)
            total = page_data.get("total", 0)
            comics.extend(items)
            print(f"第 {page}/{total_pages} 页 ({len(comics)}/{total})")
            if page >= total_pages:
                break
            page += 1
        return comics

    async def favourite_comic(self, comic_id: str) -> dict:
        return await self._request(
            f"/comics/{comic_id}/favourite", method="POST"
        )

    # ==== 漫画详情 ====

    async def get_comic_info(self, comic_id: str) -> dict:
        return await self._request(f"/comics/{comic_id}")

    # ==== 章节列表 ====

    async def get_episodes(self, comic_id: str, page: int = 1) -> dict:
        return await self._request(f"/comics/{comic_id}/eps?page={page}")

    # ==== 章节图片 ====

    async def get_pages(self, comic_id: str, ep_order: int, page: int = 1) -> dict:
        return await self._request(
            f"/comics/{comic_id}/order/{ep_order}/pages?page={page}"
        )

    # ==== 搜索 ====

    async def search(self, keyword: str, page: int = 1, sort: str = "dd") -> dict:
        return await self._request(
            f"/comics/advanced-search?page={page}&s={sort}&keyword={keyword}"
        )

    # ==== 分类 ====

    async def get_categories(self) -> dict:
        return await self._request("/categories")

    # ==== 登录 ====

    async def login(self, email: str, password: str) -> dict:
        return await self._request(
            "/auth/sign-in",
            method="POST",
            data={"email": email, "password": password},
        )

    # ==== 排行榜 ====

    async def get_leaderboard(self, tt: str = "H24", ct: str = "VC") -> dict:
        return await self._request(
            f"/comics/leaderboard?tt={tt}&ct={ct}"
        )
