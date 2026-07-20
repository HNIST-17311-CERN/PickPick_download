"""config.yaml 读写"""
from pathlib import Path

import yaml


class ConfigRepo:
    def __init__(self, path: Path = Path("config.yaml")):
        self._path = path

    def read(self) -> dict:
        if not self._path.exists():
            return {}
        with open(self._path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def write(self, data: dict) -> None:
        with open(self._path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False)

    def read_masked(self) -> dict:
        """读取配置，脱敏 token/nonce"""
        cfg = self.read()
        if cfg.get("token") and len(cfg["token"]) > 20:
            cfg["token"] = cfg["token"][:20] + "..."
        if cfg.get("nonce") and len(cfg["nonce"]) > 8:
            cfg["nonce"] = cfg["nonce"][:8] + "..."
        if cfg.get("embedding_api_key") and len(cfg["embedding_api_key"]) > 8:
            cfg["embedding_api_key"] = cfg["embedding_api_key"][:8] + "..."
        return cfg
