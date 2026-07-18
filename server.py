"""
哔咔漫画爬虫 — FastAPI 启动入口
启动: python server.py
"""
import shutil
import sys
from pathlib import Path

import uvicorn


def first_run_setup() -> None:
    """首次运行：从 config.example.yaml 自动创建 config.yaml"""
    config_path = Path("config.yaml")
    example_path = Path("config.example.yaml")

    if not example_path.exists():
        return

    if config_path.exists():
        return

    shutil.copy(example_path, config_path)
    print("=" * 60)
    print("  首次运行 — 已从 config.example.yaml 创建 config.yaml")
    print("  请编辑 config.yaml 填入你的 token 和 nonce（获取方式见下方说明）")
    print()
    print("  获取方式：")
    print("  1. 浏览器登录 https://manhuapica.com")
    print("  2. F12 → Application → Local Storage → manhuapica.com")
    print("  3. 复制 token 和 nonce 的值")
    print()
    print("  也可以启动后在 Web 设置页直接邮箱登录自动获取")
    print("=" * 60)
    print()


if __name__ == "__main__":
    first_run_setup()
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_dirs=["app"],
        reload_excludes=["*.json", "comics_detail/*", "__pycache__/*"],
    )
