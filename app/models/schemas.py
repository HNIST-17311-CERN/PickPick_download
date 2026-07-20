"""Pydantic v2 请求/响应模型 — 与前端 API 契约保持一致"""
from typing import Optional
from pydantic import BaseModel


# ==== 通用 ====

class SuccessResponse(BaseModel):
    ok: bool = True


# ==== 漫画浏览 ====

class ComicItem(BaseModel):
    folder: str
    title: str = ""
    author: str = ""
    categories: list[str] = []
    tags: list[str] = []
    status: str = ""
    epsCount: int = 0
    pagesCount: int = 0
    totalViews: int = 0
    totalLikes: int = 0
    chapter_done: int = 0
    chapter_total: int = 0
    chapter_errors: int = 0
    has_cover: bool = False


class ComicListResponse(BaseModel):
    items: list[ComicItem] = []
    total: int = 0
    page: int = 1
    per_page: int = 35


class ChapterEntry(BaseModel):
    order: int
    title: str = ""
    totalPages: int = 0
    downloaded: int = 0
    error: Optional[str] = None


class ComicDetailResponse(BaseModel):
    folder: str
    meta: dict = {}
    chapters: list[ChapterEntry] = []
    has_cover: bool = False
    cover_url: str = ""
    from_api: bool = False
    comic_idx: int = 0


class ChapterImage(BaseModel):
    filename: str
    url: str


class ChapterImagesResponse(BaseModel):
    images: list[ChapterImage] = []
    total: int = 0


# ==== 分类 ====

class CategoriesResponse(BaseModel):
    categories: list[str] = []


# ==== 收藏 ====

class FavoriteItem(BaseModel):
    idx: int
    title: str = "?"
    author: str = ""
    categories: list[str] = []
    epsCount: int = 0
    dl_status: str = "none"
    is_new: bool = False
    folder: Optional[str] = None
    cover_url: str = ""
    has_cover: bool = False
    chapter_done: int = 0
    chapter_total: int = 0
    chapter_errors: int = 0


class FavoriteListResponse(BaseModel):
    items: list[FavoriteItem] = []
    total: int = 0
    new_count: int = 0
    page: int = 1
    per_page: int = 35
    categories: list[str] = []


class RefreshResponse(BaseModel):
    ok: bool = True
    total: int = 0
    new_count: int = 0
    error: str = ""


# ==== 下载 ====

class DownloadQueueItem(BaseModel):
    idx: int
    title: str = "?"
    author: str = ""
    epsCount: int = 0
    ch_done: int = 0
    ch_total: int = 0
    has_detail: bool = False
    folder: Optional[str] = None
    is_new: bool = False


class DownloadQueueResponse(BaseModel):
    items: list[DownloadQueueItem] = []
    total: int = 0


class DownloadStartRequest(BaseModel):
    target: str = "all"
    page_concurrency: int = 3
    chapter_concurrency: int = 1
    request_delay: float = 1.5


class DownloadStatusResponse(BaseModel):
    running: bool = False
    current: str = ""
    progress_done: int = 0
    progress_total: int = 0
    progress_title: str = ""


# ==== 配置 / 认证 ====

class ConfigResponse(BaseModel):
    token: str = ""
    nonce: str = ""
    proxy: str = ""
    api_base: str = "https://picaapi.go2778.com"
    request_delay: float = 1.5
    page_concurrency: int = 3
    chapter_concurrency: int = 1
    max_retries: int = 30
    download_dir: str = "comics_detail"
    image_proxy_domain: str = ""


class ConfigUpdateRequest(BaseModel):
    token: Optional[str] = None
    nonce: Optional[str] = None
    proxy: Optional[str] = None
    api_base: Optional[str] = None
    request_delay: Optional[float] = None
    page_concurrency: Optional[int] = None
    chapter_concurrency: Optional[int] = None
    max_retries: Optional[int] = None
    download_dir: Optional[str] = None
    image_proxy_domain: Optional[str] = None


class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    ok: bool = False
    user: str = "?"
    email: str = ""
    expires: str = ""
    remaining_hours: float = 0
    error: str = ""
    debug: str = ""


class TokenTestRequest(BaseModel):
    token: Optional[str] = None
    nonce: Optional[str] = None
    api_base: Optional[str] = None


class TokenTestResponse(BaseModel):
    ok: bool = False
    user: str = "?"
    email: str = ""
    expires: str = ""
    remaining_hours: float = 0
    error: str = ""
    favourites_total: int = 0


class PickDirectoryRequest(BaseModel):
    initial: str = ""


class PickDirectoryResponse(BaseModel):
    ok: bool = True
    path: str = ""
    error: str = ""


# ==== 文件操作 ====

class BatchDeleteRequest(BaseModel):
    folders: list[str] = []


class ExportRequest(BaseModel):
    folders: list[str] = []


class ImportResponse(BaseModel):
    ok: bool = True
    imported: int = 0
    error: str = ""


# ==== 进度 ====

class ProgressResponse(BaseModel):
    total: int = 0
    completed: list[str] = []
    incomplete: list[str] = []
    missing_detail: list[str] = []
    last_update: str = ""
