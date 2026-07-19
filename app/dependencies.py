"""FastAPI 依赖注入"""
from fastapi import Request

from app.repositories.comic_repo import ComicsMetadataRepo, ComicsDetailRepo, LastSeenRepo
from app.repositories.config_repo import ConfigRepo
from app.repositories.download_repo import DownloadProgressRepo
from app.services.comic_service import ComicService
from app.services.favorite_service import FavoriteService
from app.services.download_service import DownloadService, DownloadStateManager
from app.services.config_service import ConfigService
from app.services.auth_service import AuthService
from app.services.export_service import ExportService
from app.services.search_service import SearchService
from app.services.category_service import CategoryService


def get_download_state(request: Request) -> DownloadStateManager:
    return request.app.state.download_state


def get_config_repo() -> ConfigRepo:
    return ConfigRepo()


def get_comic_repo() -> ComicsMetadataRepo:
    return ComicsMetadataRepo()


def get_detail_repo() -> ComicsDetailRepo:
    return ComicsDetailRepo()


def get_seen_repo() -> LastSeenRepo:
    return LastSeenRepo()


def get_progress_repo() -> DownloadProgressRepo:
    return DownloadProgressRepo()


def get_config_service() -> ConfigService:
    return ConfigService(ConfigRepo())


def get_auth_service() -> AuthService:
    return AuthService(ConfigRepo())


def get_comic_service() -> ComicService:
    return ComicService(ComicsDetailRepo())


def get_favorite_service() -> FavoriteService:
    return FavoriteService(ComicsMetadataRepo(), ComicsDetailRepo(), LastSeenRepo())


def get_download_service() -> DownloadService:
    return DownloadService(ComicsMetadataRepo(), ComicsDetailRepo(), DownloadProgressRepo())


def get_export_service() -> ExportService:
    return ExportService()


def get_search_service() -> SearchService:
    return SearchService()


def get_category_service() -> CategoryService:
    return CategoryService(ComicsDetailRepo(), ComicsMetadataRepo())
