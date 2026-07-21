"""
哔咔漫画爬虫 — FastAPI 启动入口
启动: python server.py
"""
import shutil
import sys
from pathlib import Path

import uvicorn


def _bundle_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(".")


def first_run_setup() -> None:
    """首次运行：从 config.example.yaml 自动创建 config.yaml 和基础目录"""
    config_path = Path("config.yaml")
    example_path = _bundle_dir() / "config.example.yaml"

    if not example_path.exists():
        return

    if not config_path.exists():
        shutil.copy(example_path, config_path)
        print("=" * 60)
        print("  首次运行 — 已从 config.example.yaml 创建 config.yaml")
        print("  请编辑 config.yaml 填入你的 token 和 nonce（获取方式见下方说明）")
        print()
        print("  获取方式：")
        print("  1. 浏览器登录 https://manhuapica.com")
        print("  2. F12 → Application → Local Storage → manhuapica.com")
        print("  3. 复制 token 和 nonce 的值")
        print("=" * 60)
        print()

    # 确保下载目录存在
    dl = Path("comics_detail")
    try:
        if config_path.exists():
            import yaml
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
            dd = str(cfg.get("download_dir", "")).strip()
            if dd:
                dl = Path(dd)
    except Exception:
        pass
    dl.mkdir(parents=True, exist_ok=True)


if __name__ == "__main__":
    import app.main  # 确保 PyInstaller 追踪所有 app 子模块
    first_run_setup()
    is_frozen = getattr(sys, "frozen", False)
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
        reload=not is_frozen,
        reload_dirs=["app"] if not is_frozen else [],
        reload_excludes=["*.json", "comics_detail/*", "__pycache__/*"] if not is_frozen else [],
    )
