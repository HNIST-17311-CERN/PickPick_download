# 哔咔漫画爬虫

通过逆向工程的 API 签名算法调用哔咔漫画 Web API，实现收藏列表同步、漫画详情获取、图片批量下载和本地浏览。

## 获取凭证

两种方式任选其一：

1. **浏览器提取**：登录 https://manhuapica.com → F12 → Application → Local Storage → 复制 `token` 和 `nonce` → 填入 `config.yaml`
2. **邮箱登录**（推荐）：启动后在设置页直接用邮箱密码登录，自动获取

## 功能

- **收藏同步** — 从 Pica API 实时拉取收藏列表，支持增量新增检测
- **批量下载** — 三级并发（漫画/章节/图片），断点续传，自动跳过已下载
- **收藏页直接阅读** — 已下载漫画的详情页直接显示"本地阅读"按钮，无需二次跳转
- **本地浏览** — 网格视图、详情页、分类筛选、搜索、滚动/翻页阅读器
- **进度管理** — 实时下载日志（SSE 推送），全局+章节级双层进度追踪
- **导入导出** — 漫画打包 ZIP 导出/导入
- **本地扫描** — 扫描任意文件夹导入本地漫画到 SQLite 数据库

## 使用

| 页面 | 功能 |
|------|------|
| 收藏页 | API 实时收藏列表，分类/状态下拉筛选，已下载直接跳阅读 |
| 下载页 | 待下载队列，勾选批量下载，实时 SSE 日志 |
| 本地浏览 | 已下载漫画网格，搜索和分类过滤 |
| 分类页 | 按标签分组浏览全部已下载漫画 |
| 搜索页 | 三源搜索（收藏 + 本地 + 导入） |
| 设置页 | Token/Nonce 配置，并发数调整，邮箱登录，下载目录配置 |

典型流程：**设置页配置凭证 → 收藏页刷新同步 → 下载页勾选启动 → 本地浏览阅读**

## 配置说明

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `token` / `nonce` | — | API 凭证，可通过邮箱登录自动获取 |
| `download_dir` | `comics_detail` | 漫画下载目录，修改后需重启 |
| `page_concurrency` | 3 | 图片并发下载数 |
| `chapter_concurrency` | 1 | 章节并发数 |
| `comic_concurrency` | 1 | 漫画并发数 |
| `max_retries` | 30 | API 请求最大重试次数 |
| `request_delay` | 1.5 | API 请求间隔（秒） |
| `proxy` | — | HTTP 代理地址 |

## 项目结构

```
.
├── server.py                  # FastAPI 启动入口
├── PicaScraper.spec           # PyInstaller 打包配置
├── app/                       # FastAPI 模块化架构
│   ├── main.py                # 应用工厂 + 路由注册
│   ├── dependencies.py        # 依赖注入容器
│   ├── core/                  # 签名算法、API客户端、文件工具、数据库
│   ├── services/              # 下载引擎、漫画浏览、收藏、认证、配置、导出
│   ├── routers/               # REST API 端点
│   ├── repositories/          # 数据访问（JSON + SQLite）
│   └── models/                # Pydantic 请求/响应模型
├── frontend/                  # 纯 HTML/CSS/JS SPA（无框架）
│   ├── index.html             # 本地浏览
│   ├── favorites.html         # 收藏页
│   ├── download.html          # 下载管理（SSE 实时日志）
│   ├── settings.html          # 设置页
│   ├── detail.html            # 本地漫画详情
│   ├── detail-api.html        # API 漫画详情（已下载→显示本地阅读入口）
│   ├── reader.html            # 图片阅读器
│   ├── categories.html        # 分类页
│   └── search.html            # 搜索页
└── docs/                      # 文档
```

## API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/comics` | 本地漫画列表（分类筛选、分页） |
| GET | `/api/comics/{folder}` | 漫画详情+章节（含本地下载状态） |
| GET | `/api/comics/{folder}/chapters/{order}` | 章节图片列表 |
| DELETE | `/api/comics/{folder}` | 删除漫画 |
| GET | `/api/favorites` | 实时收藏列表（分类/状态筛选） |
| POST | `/api/favorites/refresh` | 从 API 同步收藏 |
| GET | `/api/download/queue` | 待下载队列 |
| POST | `/api/download/start` | 启动下载 |
| POST | `/api/download/stop` | 停止下载 |
| GET | `/api/download/status` | 下载状态 |
| GET | `/api/download/stream` | SSE 实时日志流 |
| GET/POST | `/api/config` | 配置读写 |
| POST | `/api/login` | 邮箱登录 |
| POST | `/api/logout` | 退出登录 |
| GET | `/api/search` | 三源搜索 |
| GET | `/api/categories/full` | 分类分组 |
| POST | `/api/comics/export` | 导出 ZIP |
| POST | `/api/comics/import` | 导入 ZIP |
| GET/POST/DELETE | `/api/local/*` | 本地导入漫画 CRUD |

## 技术要点

- **签名算法**：HMAC-SHA256，密钥从 JS bundle 逆向提取
- **请求伪装**：Android App 请求头（`app-platform: android`），带 `origin`/`referer`
- **自动重试**：5xx 错误指数退避重试（2s/4s/8s/...上限 30s），最多 30 次
- **三层并发**：漫画级/章节级/图片级 worker pool，协程+队列控制并发数
- **断点续传**：文件存在 + 大小 > 0 判重，chapters.json 记录每话进度
- **SSE 推送**：下载日志实时推送到前端，支持心跳和断线重连
- **单文件分发**：PyInstaller 打包为独立 EXE，无需安装 Python

## 免责声明

本工具仅用于个人学习研究，请勿用于商业用途或侵犯他人权益。使用者需自行承担合规风险。

## License

MIT
