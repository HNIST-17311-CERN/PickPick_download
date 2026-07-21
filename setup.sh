#!/usr/bin/env bash
set -e

echo ""
echo "============================================================"
echo "  PicaDownload — 一键环境安装"
echo "============================================================"
echo ""

# 检查 Python
if ! command -v python3 &>/dev/null && ! command -v python &>/dev/null; then
    echo "[错误] 未检测到 Python，请先安装 Python 3.10+"
    exit 1
fi
PYTHON=$(command -v python3 || command -v python)
echo "[✓] Python 已检测: $($PYTHON --version)"
echo ""

# 创建虚拟环境
if [ ! -d ".venv" ]; then
    echo "[1/3] 创建虚拟环境..."
    $PYTHON -m venv .venv
    echo "[✓] 虚拟环境创建成功"
else
    echo "[1/3] 虚拟环境已存在，跳过"
fi
echo ""

# 激活 + 安装依赖
echo "[2/3] 安装 Python 依赖..."
source .venv/bin/activate
pip install -r requirements.txt -q
echo "[✓] 依赖安装完成"
echo ""

# 配置
echo "[3/3] 初始化配置..."
if [ ! -f "config.yaml" ]; then
    if [ -f "config.example.yaml" ]; then
        cp config.example.yaml config.yaml
        echo "[✓] 已创建 config.yaml（从示例模板复制）"
        echo ""
        echo "  !!!  请编辑 config.yaml 填入你的 token 和 nonce  !!!"
        echo ""
        echo "  获取方式:"
        echo "  1. 浏览器登录 https://manhuapica.com"
        echo "  2. F12 → Application → Local Storage → manhuapica.com"
        echo "  3. 复制 token 和 nonce 的值填入 config.yaml"
        echo ""
    else
        echo "[警告] config.example.yaml 不存在，请手动创建 config.yaml"
    fi
else
    echo "[✓] config.yaml 已存在"
fi
echo ""

echo "============================================================"
echo "  安装完成！"
echo ""
echo "  启动服务: source .venv/bin/activate && python server.py"
echo "  浏览器访问: http://localhost:8000"
echo "============================================================"
echo ""
