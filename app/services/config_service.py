"""配置管理业务逻辑"""
from pathlib import Path

from app.repositories.config_repo import ConfigRepo


def get_detail_dir() -> Path:
    """读取 download_dir 配置，返回实际路径；空则回退 comics_detail"""
    cfg = ConfigRepo().read()
    val = str(cfg.get("download_dir", "")).strip()
    return Path(val) if val else Path("comics_detail")


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
            "max_retries", "api_base", "image_proxy_domain", "download_dir",
            "embedding_api_key", "embedding_api_base", "similar_enabled",
        ]:
            if key in data and data[key] is not None:
                cfg[key] = data[key]
        for key in ["token", "nonce"]:
            if key in data and data[key] and "..." not in str(data[key]):
                cfg[key] = data[key]
        self._repo.write(cfg)
