"""FastAPI 应用工厂"""
import sys
import traceback
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response

from app.services.download_service import DownloadStateManager
from app.services.config_service import get_detail_dir
from app.routers import comics, favorites, download, config, auth, local_comics, search, categories, similar, leaderboard


def _bundle_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).parent.parent


FRONTEND_DIR = _bundle_dir() / "frontend"

print(f"[Pica] FRONTEND_DIR = {FRONTEND_DIR}")
print(f"[Pica] FRONTEND_DIR.exists() = {FRONTEND_DIR.exists()}")
print(f"[Pica] sys.frozen = {getattr(sys, 'frozen', False)}")
print(f"[Pica] sys._MEIPASS = {getattr(sys, '_MEIPASS', 'N/A')}")


def create_app() -> FastAPI:

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        import asyncio
        from app.core.database import init_db
        from app.repositories.comic_repo import ComicsMetadataRepo, ComicsDetailRepo, LastSeenRepo
        await init_db()

        async def _auto_sync_favorites():
            try:
                from app.services.favorite_service import FavoriteService
                svc = FavoriteService(ComicsMetadataRepo(), ComicsDetailRepo(), LastSeenRepo())
                result = await svc.refresh_from_api()
                if result.get("ok"):
                    print(f"[Pica] 启动时自动同步收藏完成，共 {result.get('total', 0)} 部")
                else:
                    print(f"[Pica] 启动时自动同步跳过: {result.get('error', '未登录')}")
            except Exception as e:
                print(f"[Pica] 启动时自动同步失败: {e}")

        asyncio.create_task(_auto_sync_favorites())
        yield

    app = FastAPI(title="哔咔漫画爬虫", lifespan=lifespan)

    # CORS
    @app.middleware("http")
    async def cors_middleware(request: Request, call_next):
        if request.method == "OPTIONS":
            resp = Response(status_code=200)
        else:
            resp = await call_next(request)
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Access-Control-Allow-Methods"] = "*"
        resp.headers["Access-Control-Allow-Headers"] = "*"
        return resp

    # 共享状态放 app.state
    app.state.download_state = DownloadStateManager()

    # 注册路由
    app.include_router(comics.router)
    app.include_router(favorites.router)
    app.include_router(download.router)
    app.include_router(config.router)
    app.include_router(auth.router)
    app.include_router(local_comics.router)
    app.include_router(search.router)
    app.include_router(categories.router)
    app.include_router(similar.router)
    app.include_router(leaderboard.router)

    # 静态资源 — 用 FileResponse 代替 StaticFiles，解决 PyInstaller 打包后 CSS/JS 丢失问题
    if not FRONTEND_DIR.exists():
        print(f"[Pica] 错误: FRONTEND_DIR 不存在，跳过静态资源注册！路径: {FRONTEND_DIR}")
    else:
        static_mime = {
            ".css": "text/css",
            ".js": "application/javascript",
        }
        for static_file in ["css/style.css", "css/theme.css", "js/common.js"]:
            fp = FRONTEND_DIR / static_file
            if not fp.exists():
                print(f"[Pica] 错误: 静态文件不存在，跳过: {static_file} (完整路径: {fp})")
                continue
            ext = Path(static_file).suffix
            mimetype = static_mime.get(ext, "application/octet-stream")
            def _make_static_route(path, urlpath, media_type):
                @app.get(f"/{urlpath}")
                async def _static():
                    try:
                        return FileResponse(str(path), media_type=media_type)
                    except Exception:
                        traceback.print_exc()
                        return Response(content=b"", status_code=500)
                return _static
            _make_static_route(fp, static_file, mimetype)
            print(f"[Pica] 已注册静态路由: /{static_file}")

    detail_dir = get_detail_dir()
    if detail_dir.exists():
        app.mount("/images", StaticFiles(directory=str(detail_dir)), name="images")

    # 页面路由
    for page in ["index.html", "favorites.html", "download.html", "settings.html", "detail.html", "detail-api.html", "reader.html", "search.html", "categories.html", "leaderboard.html"]:
        fp = FRONTEND_DIR / page
        if fp.exists():
            def _make_route(path, pagename):
                @app.get(f"/{pagename}")
                async def _page():
                    resp = FileResponse(str(path))
                    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
                    resp.headers["Pragma"] = "no-cache"
                    resp.headers["Expires"] = "0"
                    return resp
                return _page
            _make_route(fp, page)

    @app.get("/")
    async def index():
        return FileResponse(str(FRONTEND_DIR / "index.html"))

    return app


app = create_app()
