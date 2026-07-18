# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

哔咔漫画 (PicaWeb) 爬虫 — 通过逆向工程的 API 签名算法调用哔咔漫画 Web API，实现收藏列表同步、漫画详情获取、图片批量下载和本地浏览。
git
## 常用命令

```bash
# CLI 命令（manga_api.py）
python manga_api.py favourites          # 获取全量收藏列表 → comics_metadata.json
python manga_api.py detail_all          # 获取每部漫画详情（封面+metadata）→ comics_detail/
python manga_api.py download all        # 下载全部漫画图片（支持 3 / 1-50 / all）
python manga_api.py check               # 检查下载进度 → download_progress.json

# Web 服务
python server.py                        # 启动 FastAPI 服务，浏览器访问 http://localhost:8000
streamlit run app.py                    # Streamlit 界面（已弃用，保留参考）
```

典型流程：`favourites` → `detail_all` → `download all` → `check`

## 架构

### 三层结构

1. **`manga_api.py`** — 核心层。所有功能的基础模块，server.py 和 app.py 都依赖它
2. **`server.py`** — Web 服务层。FastAPI + 静态文件，当前主力界面。下载任务在后台线程执行，通过 SSE 推送日志到前端
3. **`app.py`** — Streamlit GUI（已弃用，但下载逻辑和进度追踪代码仍有参考价值）

### API 客户端 (`PicaClient`)

`manga_api.py:65` — 封装了哔咔漫画 Web API 的全部接口。关键实现细节：

- **签名算法** (`compute_signature`, line 56)：HMAC-SHA256，输入为 `path + timestamp + nonce + method + api_key`（去斜杠后转小写）。两个密钥 (`_API_KEY`, `_SIGN_KEY`) 从 JS bundle 通过 `_ue()` 解码得到，硬编码在模块中
- **请求头**需要伪装成 Android App（`app-platform: android`, `app-uuid: webUUIDv2`），同时带 `origin` 和 `referer` 指向 `manhuapica.com`
- **自动重试**：5xx 错误指数退避重试（2s/4s/8s/10min），最多 30 次，处理限流封禁
- **图片下载**需要 `Referer: https://manhuapica.com/` 头，否则会被防盗链拦截
- `config.yaml` 中只需配置 `token` 和 `nonce`（从浏览器 localStorage 获取），`cookie` 字段未实际使用

### 数据流

```
config.yaml (token+nonce)
  → PicaClient 签名请求 API
    → comics_metadata.json (收藏列表缓存, 734部)
      → detail_all: API获取每部详情 → comics_detail/{编号}_{标题}/metadata.json + cover.jpg
        → download: API获取章节列表+图片URL，并发下载 → comics_detail/{编号}_{标题}/{章节}/xxx.jpg
          → chapters.json (章节级进度) + download_progress.json (全局进度)
```

### 断点续传

两层进度追踪：
- **`download_progress.json`**：全局级，记录哪些漫画已完成（`completed` 数组存索引）。`cmd_download` 和 `cmd_check` 都会读写
- **`chapters.json`**：漫画级，每部漫画一个，记录每话的 `totalPages` 和 `downloaded`。单张图片级跳过通过文件存在 + 大小 > 0 判断

### 前端架构

`frontend/index.html` 是纯 HTML/CSS/JS SPA（无框架），通过 Fetch API 调用 server.py 的 REST 端点，支持网格浏览、详情页、滚动/翻页阅读器、分类筛选和实时下载日志（SSE）。

## 技术要点

- **签名密钥不可变**：`_API_KEY` 和 `_SIGN_KEY` 是从 JS bundle 逆向提取的常量，不需要也不应该从配置文件读取
- **API 分页**：章节列表和图片列表都可能分页（每页 40 张），需要用 while 循环拉取全部页面（`manga_api.py` line 238, 478）
- **并发模型**：章节之间串行（需间隔 1.5s 避免限流），单话内图片并发下载（`ThreadPoolExecutor`，默认 3 线程）
- **Windows 兼容**：`safe_print()` 和 `safe_filename()` 处理 Windows GBK 终端编码和文件名非法字符问题
- **server.py 的下载状态**是模块级全局变量 `_download_state`，非进程安全，仅适用于单用户场景
