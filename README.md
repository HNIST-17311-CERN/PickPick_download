# 哔咔漫画爬虫

通过逆向工程的 API 签名算法调用哔咔漫画 Web API，实现收藏列表同步、漫画详情获取、图片批量下载和本地浏览。

## 快速上手

### 方式一：一键安装（推荐）

**Windows** — 双击 `setup.bat`

**macOS / Linux** — 终端运行 `bash setup.sh`

脚本会自动：创建虚拟环境 → 安装依赖 → 从模板复制配置文件。

然后编辑 `config.yaml` 填入你的 token 和 nonce（也可跳过，在 Web 设置页直接用邮箱登录），最后：

```bash
python server.py
# 浏览器打开 http://localhost:8000
```

### 方式二：手动安装

```bash
git clone https://github.com/yourname/pica-manga-scraper.git
cd pica-manga-scraper

python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp config.example.yaml config.yaml  # 编辑填入 token/nonce
python server.py
```

## 获取凭证

两种方式任选其一：

1. **浏览器提取**（推荐）：登录 https://manhuapica.com → F12 → Application → Local Storage → 复制 `token` 和 `nonce` → 填入 `config.yaml`
2. **邮箱登录**：启动后在 Web 设置页直接用邮箱密码登录，自动获取

## 功能

- **收藏同步** — 从 Pica API 实时拉取收藏列表，支持增量新增检测
- **批量下载** — 三级并发（漫画/章节/图片），断点续传，自动跳过已下载
- **本地浏览** — 网格视图、详情页、分类筛选、搜索、滚动/翻页阅读器
- **进度管理** — 实时下载日志（SSE 推送），全局+章节级双层进度追踪
- **导入导出** — 漫画打包 ZIP 导出/导入
- **本地扫描** — 扫描任意文件夹导入本地漫画到 SQLite 数据库

## 使用

| 页面 | 功能 |
|------|------|
| 收藏页 | API 实时收藏列表，分类/状态下拉筛选，一键同步 |
| 下载页 | 待下载队列，勾选批量下载，实时 SSE 日志 |
| 本地浏览 | 已下载漫画网格，搜索和分类过滤 |
| 设置页 | Token/Nonce 配置，并发数调整，邮箱登录 |

典型流程：**设置页配置凭证 → 收藏页刷新同步 → 下载页勾选启动 → 本地浏览阅读**

## 项目结构

```
.
├── server.py                  # FastAPI 启动入口（首次运行自动建配置）
├── app/                       # FastAPI 模块化架构
│   ├── main.py                # 应用工厂 + 路由注册
│   ├── dependencies.py        # 依赖注入容器
│   ├── core/                  # 签名算法、API客户端、文件工具、数据库
│   ├── services/              # 下载引擎、漫画浏览、收藏、认证、配置、导出
│   ├── routers/               # REST API 端点（comics/favorites/download/config/auth）
│   ├── repositories/          # 数据访问（JSON + SQLite）
│   └── models/                # Pydantic 请求/响应模型
├── frontend/                  # 纯 HTML/CSS/JS SPA（无框架）
│   ├── index.html             # 本地浏览
│   ├── favorites.html         # 收藏页
│   ├── download.html          # 下载管理（SSE 实时日志）
│   ├── settings.html          # 设置页
│   ├── detail.html            # 漫画详情
│   └── reader.html            # 图片阅读器
└── docs/                      # 数据库设计文档
```

## API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/comics` | 本地漫画列表（分类、分页） |
| GET | `/api/comics/{folder}` | 漫画详情 + 章节列表 |
| GET | `/api/comics/{folder}/chapters/{order}` | 章节图片列表 |
| GET | `/api/favorites` | 实时收藏列表 |
| POST | `/api/favorites/refresh` | 同步收藏到本地 |
| GET | `/api/download/queue` | 待下载队列 |
| POST | `/api/download/start` | 启动下载 |
| POST | `/api/download/stop` | 停止下载 |
| GET | `/api/download/stream` | SSE 实时日志流 |
| GET/POST | `/api/config` | 配置读写 |
| POST | `/api/login` | 邮箱登录 |
| POST | `/api/comics/export` | 导出 ZIP |
| POST | `/api/comics/import` | 导入 ZIP |

## 技术要点

- **签名算法**：HMAC-SHA256，密钥从 JS bundle 逆向提取，Python 中 1:1 复现
- **请求伪装**：Android App 请求头（`app-platform: android`），带 `origin`/`referer`
- **自动重试**：5xx 错误指数退避重试（2s/4s/8s/...上限 30s），最多 30 次
- **三层并发**：漫画级/章节级/图片级 worker pool，协程+队列控制并发数
- **断点续传**：文件存在 + 大小 > 0 判重，chapters.json 记录每话进度
- **SSE 推送**：下载日志实时推送到前端，支持心跳和断线重连

## 免责声明

本工具仅用于个人学习研究，请勿用于商业用途或侵犯他人权益。使用者需自行承担合规风险。

## License

MIT
