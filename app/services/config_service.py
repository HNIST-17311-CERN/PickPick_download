"""配置管理业务逻辑"""
from pathlib import Path

from app.repositories.config_repo import ConfigRepo


class ConfigService:
    def __init__(self, config_repo: ConfigRepo):
        self._repo = config_repo

    def get_masked(self) -> dict:
        return self._repo.read_masked()

    def get_raw(self) -> dict:
        return self._repo.read()

    def update(self, data: dict) -> None:
        cfg = self._repo.read()
        for key in [
            "proxy", "page_concurrency", "chapter_concurrency", "comic_concurrency",
            "max_retries", "api_base", "image_proxy_domain", "download_dir", "cover_dir",
        ]:
            if key in data and data[key] is not None:
                cfg[key] = data[key]
        for key in ["token", "nonce"]:
            if key in data and data[key] and "..." not in str(data[key]):
                cfg[key] = data[key]
        self._repo.write(cfg)
