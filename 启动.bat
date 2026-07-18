@echo off
title 哔咔漫画爬虫
cd /d "%~dp0"

:: 首次运行自动安装
if not exist ".venv" (
    echo 正在安装环境...
    call setup.bat
)

:: 启动服务
echo 正在启动服务...
call .venv\Scripts\activate.bat
python server.py
pause
