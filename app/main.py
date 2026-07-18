"""FastAPI 应用工厂"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response

from app.services.download_service import DownloadStateManager
from app.routers import comics, favorites, download, config, auth, local_comics

FRONTEND_DIR = Path("frontend")
DETAIL_DIR = Path("comics_detail")


def create_app() -> FastAPI:

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        from app.core.database import init_db
        await init_db()
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

    # 静态文件挂载
    if FRONTEND_DIR.exists():
        app.mount("/css", StaticFiles(directory=str(FRONTEND_DIR / "css")), name="css")
        app.mount("/js", StaticFiles(directory=str(FRONTEND_DIR / "js")), name="js")
    if DETAIL_DIR.exists():
        app.mount("/images", StaticFiles(directory=str(DETAIL_DIR)), name="images")

    # 页面路由
    for page in ["index.html", "favorites.html", "download.html", "settings.html", "detail.html", "detail-api.html", "reader.html"]:
        fp = FRONTEND_DIR / page
        if fp.exists():
            def _make_route(path):
                @app.get(f"/{page}")
                async def _page():
                    return FileResponse(str(path))
                return _page
            _make_route(fp)

    @app.get("/")
    async def index():
        return FileResponse(str(FRONTEND_DIR / "index.html"))

    return app


app = create_app()
