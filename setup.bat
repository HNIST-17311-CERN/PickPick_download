@echo off
title PicaDownload — 环境安装
cd /d "%~dp0"

echo.
echo ============================================================
echo   PicaDownload — 一键环境安装
echo ============================================================
echo.

:: 检查 Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未检测到 Python，请先安装 Python 3.10+
    echo 下载: https://www.python.org/downloads/
    pause
    exit /b 1
)
echo [✓] Python 已检测:
python --version
echo.

:: 创建虚拟环境
if not exist ".venv" (
    echo [1/3] 创建虚拟环境...
    python -m venv .venv
    if %errorlevel% neq 0 (
        echo [错误] 虚拟环境创建失败
        pause
        exit /b 1
    )
    echo [✓] 虚拟环境创建成功
) else (
    echo [1/3] 虚拟环境已存在，跳过
)
echo.

:: 安装依赖
echo [2/3] 安装 Python 依赖...
call .venv\Scripts\activate.bat
pip install -r requirements.txt -q
if %errorlevel% neq 0 (
    echo [错误] 依赖安装失败，请检查网络连接后重试
    pause
    exit /b 1
)
echo [✓] 依赖安装完成
echo.

:: 配置
echo [3/3] 初始化配置...
if not exist "config.yaml" (
    if exist "config.example.yaml" (
        copy config.example.yaml config.yaml >nul
        echo [✓] 已创建 config.yaml（从示例模板复制）
        echo.
        echo   !!!  请编辑 config.yaml 填入你的 token 和 nonce  !!!
        echo.
        echo   获取方式:
        echo   1. 浏览器登录 https://manhuapica.com
        echo   2. F12 - Application - Local Storage - manhuapica.com
        echo   3. 复制 token 和 nonce 的值填入 config.yaml
        echo.
    ) else (
        echo [警告] config.example.yaml 不存在，请手动创建 config.yaml
    )
) else (
    echo [✓] config.yaml 已存在
)
echo.

echo ============================================================
echo   安装完成！
echo.
echo   启动服务: python server.py
echo   浏览器访问: http://localhost:8000
echo ============================================================
echo.

pause
