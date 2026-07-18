"""
哔咔漫画爬虫 - Streamlit 图形化界面
启动: streamlit run app.py
"""

import base64
import json
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import streamlit as st
import yaml

from manga_api import (
    PicaClient, compute_signature,
    download_image, download_covers,
    safe_print, safe_filename, _build_image_url,
)
from urllib.request import ProxyHandler, build_opener, install_opener

st.set_page_config(page_title="哔咔漫画爬虫", page_icon="📚", layout="wide")
st.title("📚 哔咔漫画爬虫")

# ---- 加载配置 ----
@st.cache_resource
def load_config():
    with open("config.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

config = load_config()

proxy = config.get("proxy", "")
if proxy:
    install_opener(build_opener(ProxyHandler({"http": proxy, "https": proxy})))

client = PicaClient(config)

# ---- 数据加载 ----
@st.cache_data(ttl=300)
def load_comics():
    with open("comics_metadata.json", "r", encoding="utf-8") as f:
        return json.load(f)

def load_progress():
    pf = Path("download_progress.json")
    if pf.exists():
        with open(pf, "r", encoding="utf-8") as f:
            return json.load(f)
    return None

def load_chapter_progress(comic_idx):
    """读取某部漫画的章节进度，返回 (已下载话数, 总话数)"""
    detail_base = Path("comics_detail")
    folder = None
    for f in detail_base.glob(f"{comic_idx+1:03d}_*"):
        folder = f
        break
    if not folder:
        return 0, 0, "no_detail"

    chapters_file = folder / "chapters.json"
    if not chapters_file.exists():
        return 0, 0, "no_data"

    try:
        with open(chapters_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        chapters = data.get("chapters", [])
        total = len(chapters)
        done = sum(1 for ch in chapters if ch.get("downloaded", 0) >= ch.get("totalPages", 1))
        status = "done" if done >= total else "partial"
        return done, total, status
    except Exception:
        return 0, 0, "error"


# ---- 本地漫画数据 ----
@st.cache_data(ttl=60)
def load_local_comics():
    """扫描 comics_detail，返回 {folder_name: {meta, chapters, images_count}}"""
    result = {}
    detail_base = Path("comics_detail")
    if not detail_base.exists():
        return result
    for folder in sorted(detail_base.glob("*")):
        if not folder.is_dir():
            continue
        info = {"folder": str(folder), "name": folder.name}
        meta_path = folder / "metadata.json"
        if meta_path.exists():
            with open(meta_path, "r", encoding="utf-8") as f:
                info["meta"] = json.load(f)
        chapters_file = folder / "chapters.json"
        if chapters_file.exists():
            with open(chapters_file, "r", encoding="utf-8") as f:
                ch_data = json.load(f)
            info["chapters"] = ch_data.get("chapters", [])
        else:
            info["chapters"] = []
        # 统计图片总数
        total_imgs = 0
        for d in folder.glob("*"):
            if d.is_dir():
                total_imgs += len(list(d.glob("*")))
        info["local_images"] = total_imgs
        result[folder.name] = info
    return result

@st.cache_data(ttl=60)
def get_category_list():
    """收集所有 metadata 中的 categories"""
    cats = set()
    for info in load_local_comics().values():
        for c in info.get("meta", {}).get("categories", []):
            cats.add(c)
    return sorted(cats)

# 初始化浏览状态
if "local_view" not in st.session_state:
    st.session_state.local_view = "grid"
if "local_folder" not in st.session_state:
    st.session_state.local_folder = None
if "local_chapter_idx" not in st.session_state:
    st.session_state.local_chapter_idx = 0
if "reader_mode" not in st.session_state:
    st.session_state.reader_mode = "scroll"
if "reader_page" not in st.session_state:
    st.session_state.reader_page = 0

# ---- 侧边栏 ----
st.sidebar.title("📊 总览")

try:
    comics = load_comics()
except FileNotFoundError:
    st.sidebar.warning("请先获取漫画列表")
    comics = []

total_comics = len(comics)
st.sidebar.metric("收藏漫画", total_comics)

detail_base = Path("comics_detail")
detail_count = len(list(detail_base.glob("*"))) if detail_base.exists() else 0

progress = load_progress()
if progress:
    completed_set = set(progress.get("completed", []))
    done_count = len(completed_set)
    missing = set(range(total_comics)) - set(range(detail_count))  # 缺详情的=有metadata但无detail文件夹
    # 实际缺详情：在comics列表里但comics_detail里没文件夹
    missing_detail = [i for i in range(total_comics) if not any(
        detail_base.glob(f"{i+1:03d}_*")
    )]
    missing_count = len(missing_detail)
    incomplete_count = total_comics - done_count - missing_count
else:
    done_count = 0
    missing_detail = [i for i in range(total_comics) if not any(
        detail_base.glob(f"{i+1:03d}_*")
    )]
    missing_count = len(missing_detail)
    incomplete_count = total_comics - missing_count
    completed_set = set()

# 进度条
if total_comics > 0:
    pct = done_count / total_comics
    st.sidebar.progress(pct, text=f"已完成 {done_count}/{total_comics} ({pct:.1%})")

col_s1, col_s2, col_s3 = st.sidebar.columns(3)
col_s1.metric("✅ 完成", done_count)
col_s2.metric("🔄 待下载", incomplete_count)
col_s3.metric("⚠️ 缺详情", missing_count)

st.sidebar.divider()
st.sidebar.caption(f"详情覆盖率: {detail_count}/{total_comics}")

# 最近更新
if progress:
    st.sidebar.caption(f"进度更新: {progress.get('last_update', '?')[:16]}")

# 刷新按钮
if st.sidebar.button("🔄 刷新数据", width='stretch'):
    st.cache_data.clear()
    st.rerun()

# ---- 主区域 ----
# 自定义标签（session_state 控制，页面刷新不丢失）
if "active_tab" not in st.session_state:
    st.session_state.active_tab = 0

# 封面点击跳转检测（仅首次处理，不覆盖后续操作）
if "open" in st.query_params and not st.session_state.get("_open_handled"):
    target = st.query_params["open"]
    if target and Path(target).exists():
        st.session_state.local_folder = target
        st.session_state.local_view = "detail"
        st.session_state.active_tab = 2
        st.session_state._open_handled = True

# ====== 本地浏览辅助函数 ======
def _get_chapter_images(folder_path: str, chapter_order: int):
    """返回章节所有图片路径列表"""
    folder = Path(folder_path)
    for d in sorted(folder.glob("*")):
        if d.is_dir() and d.name.startswith(f"{chapter_order:02d}_"):
            images = sorted(d.glob("*"))
            return [img for img in images if img.suffix.lower() in
                    (".jpg", ".jpeg", ".png", ".webp", ".gif")]
    return []

def _render_reader(folder_path: str, chapters: list, ch_idx: int):
    """沉浸式阅读器"""
    ch = chapters[ch_idx]
    order = ch.get("order", 1)
    title = ch.get("title", f"第{order}话")
    images = _get_chapter_images(folder_path, order)

    # ---- 顶部导航栏 ----
    nav_col1, nav_col2, nav_col3, nav_col4, nav_col5 = st.columns([1, 2, 2, 1, 1])
    with nav_col1:
        if st.button("← 返回详情", key=f"back_detail_{folder_path}"):
            st.session_state.local_view = "detail"
            st.rerun()
    with nav_col2:
        ch_labels = [
            f"第{ch.get('order', '?'):02d}话 - {ch.get('title', '?')}"
            for ch in chapters
        ]
        new_ch_idx = st.selectbox(
            "章节", range(len(chapters)),
            index=ch_idx,
            format_func=lambda i: ch_labels[i],
            label_visibility="collapsed",
            key=f"ep_select_{folder_path}"
        )
        if new_ch_idx != ch_idx:
            st.session_state.local_chapter_idx = new_ch_idx
            st.session_state.reader_page = 0
            st.rerun()
    with nav_col3:
        st.caption(f"{title}  |  {len(images)} 张")
    with nav_col4:
        if st.button("⬅ 上一章", disabled=(ch_idx <= 0), key=f"prev_ch_{folder_path}"):
            st.session_state.local_chapter_idx = ch_idx - 1
            st.session_state.reader_page = 0
            st.rerun()
    with nav_col5:
        if st.button("下一章 ➡", disabled=(ch_idx >= len(chapters) - 1), key=f"next_ch_{folder_path}"):
            st.session_state.local_chapter_idx = ch_idx + 1
            st.session_state.reader_page = 0
            st.rerun()

    if not images:
        st.info("该章节暂无图片")
        return

    # 阅读模式
    mode = st.radio(
        "阅读模式", ["📜 滚动", "📖 翻页"],
        horizontal=True,
        index=0 if st.session_state.reader_mode == "scroll" else 1,
        key=f"mode_{folder_path}"
    )
    if "📜 滚动" in mode:
        st.session_state.reader_mode = "scroll"
    else:
        st.session_state.reader_mode = "flip"

    st.divider()

    if st.session_state.reader_mode == "scroll":
        # 滚动模式：全宽纵向排列
        for img_path in images:
            st.image(str(img_path), width='stretch')
    else:
        # 翻页模式：单张 + 左右翻页
        total_pages = len(images)
        page = st.session_state.get("reader_page", 0)
        page = max(0, min(page, total_pages - 1))

        col_l, col_img, col_r = st.columns([1, 8, 1])
        with col_l:
            st.text("")
            st.text("")
            if st.button("◀", key=f"prev_page_{folder_path}", disabled=(page <= 0), width='stretch'):
                st.session_state.reader_page = page - 1
                st.rerun()
        with col_img:
            st.image(str(images[page]), width='stretch')
            st.caption(f"{page + 1} / {total_pages}")
        with col_r:
            st.text("")
            st.text("")
            if st.button("▶", key=f"next_page_{folder_path}", disabled=(page >= total_pages - 1), width='stretch'):
                st.session_state.reader_page = page + 1
                st.rerun()

        # 底部页码跳转
        jump_page = st.number_input(
            "跳转到", 1, total_pages, page + 1,
            key=f"jump_{folder_path}"
        )
        if jump_page != page + 1:
            st.session_state.reader_page = jump_page - 1
            st.rerun()


def _render_detail(folder_path: str):
    """漫画详情页"""
    folder = Path(folder_path)
    meta_path = folder / "metadata.json"
    meta = {}
    if meta_path.exists():
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)

    chapters_file = folder / "chapters.json"
    chapters = []
    if chapters_file.exists():
        with open(chapters_file, "r", encoding="utf-8") as f:
            chapters = json.load(f).get("chapters", [])

    # 返回按钮
    if st.button("← 返回列表", key=f"back_{folder_path}"):
        st.session_state.local_view = "grid"
        st.session_state.local_folder = None
        st.session_state._open_handled = False
        st.query_params.clear()
        st.rerun()

    # 封面 + 元数据
    col1, col2 = st.columns([1, 3])
    with col1:
        cover_path = folder / "cover.jpg"
        if cover_path.exists():
            st.image(str(cover_path), width=220)
    with col2:
        st.markdown(f"## {meta.get('title', folder.name[4:])}")
        st.caption(f"作者: {meta.get('author', '?')} | {meta.get('status', '?')}")
        st.caption(f"{meta.get('pagesCount', 0)}P | {meta.get('epsCount', 0)}话 | "
                   f"👁 {meta.get('totalViews', 0):,} | ❤️ {meta.get('totalLikes', 0):,}")
        cats = meta.get("categories", [])
        tags = meta.get("tags", [])
        if cats:
            st.caption(f"分类: {', '.join(cats)}")
        if tags:
            st.caption(f"标签: {', '.join(tags[:15])}{'...' if len(tags) > 15 else ''}")

    # 简介
    desc = meta.get("description", "")
    if desc:
        with st.expander("📝 简介"):
            st.text(desc)

    # 开始阅读
    if chapters:
        st.button("▶ 开始阅读", type="primary", key=f"start_read_{folder_path}",
                  on_click=lambda: (setattr(st.session_state, "local_chapter_idx", 0),
                                    setattr(st.session_state, "reader_page", 0),
                                    setattr(st.session_state, "local_view", "reader")))

    st.divider()

    # 章节列表
    if chapters:
        st.subheader(f"📑 章节列表 ({len(chapters)} 话)")
        cols_per = 4
        for row_start in range(0, len(chapters), cols_per):
            cols = st.columns(cols_per)
            for j in range(cols_per):
                idx = row_start + j
                if idx >= len(chapters):
                    break
                ch = chapters[idx]
                order = ch.get("order", idx + 1)
                ch_title = ch.get("title", f"第{order}话")
                total = ch.get("totalPages", 0)
                downloaded = ch.get("downloaded", 0)
                pct = downloaded / total if total > 0 else 0

                with cols[j]:
                    with st.container(border=True):
                        st.caption(f"第{order:02d}话")
                        if len(ch_title) > 12:
                            st.markdown(f"*{ch_title[:12]}...*")
                        else:
                            st.markdown(f"*{ch_title}*")
                        if total > 0:
                            st.progress(pct, text=f"{downloaded}/{total}P")
                        else:
                            st.caption("未下载")
                        if st.button("📖 阅读", key=f"read_ch_{folder_path}_{idx}"):
                            st.session_state.local_chapter_idx = idx
                            st.session_state.reader_page = 0
                            st.session_state.local_view = "reader"
                            st.rerun()
    else:
        st.info("暂无章节数据，请先运行下载")


def _render_grid():
    """网格首页"""
    all_comics = load_local_comics()
    if not all_comics:
        st.info("暂无本地漫画，请先运行 `detail_all`")
        return

    category_list = get_category_list()

    # 控制栏
    c1, c2, c3 = st.columns([2, 1, 1])
    with c1:
        cat_filter = st.selectbox("分类筛选", ["全部"] + category_list, key="cat_filter")
    with c2:
        per_page = st.selectbox("每页数量", [10, 35, 60], index=1, key="per_page")

    # 筛选
    items = list(all_comics.values())
    if cat_filter != "全部":
        items = [
            info for info in items
            if cat_filter in info.get("meta", {}).get("categories", [])
        ]

    total_pages = max(1, len(items) // per_page + (1 if len(items) % per_page else 0))
    with c3:
        grid_page = st.number_input(
            "页码", 1, total_pages, 1,
            key="grid_page"
        )
    st.caption(f"共 {len(items)} 部 | 第 {grid_page}/{total_pages} 页")

    start = (grid_page - 1) * per_page
    end = min(start + per_page, len(items))
    page_items = items[start:end]

    # 网格 — 封面可点
    from urllib.parse import quote

    cols_per_row = 5
    for row_start in range(0, len(page_items), cols_per_row):
        cols = st.columns(cols_per_row)
        for j in range(cols_per_row):
            idx = row_start + j
            if idx >= len(page_items):
                break
            info = page_items[idx]
            meta = info.get("meta", {})
            folder = Path(info["folder"])
            title = meta.get("title", folder.name[4:])
            chapters = info.get("chapters", [])

            if chapters:
                done = sum(1 for ch in chapters if ch.get("downloaded", 0) >= ch.get("totalPages", 1))
            else:
                done = 0

            with cols[j]:
                cover = folder / "cover.jpg"
                if cover.exists():
                    try:
                        img_b64 = base64.b64encode(cover.read_bytes()).decode()
                        url = f"?open={quote(str(folder))}"
                        st.markdown(
                            f'<a href="{url}" target="_self">'
                            f'<img src="data:image/jpeg;base64,{img_b64}" '
                            f'style="width:100%;border-radius:4px;cursor:pointer" '
                            f'title="{title}"/>'
                            f'</a>',
                            unsafe_allow_html=True
                        )
                    except Exception:
                        st.image(str(cover), width='stretch')
                else:
                    st.caption("无封面")
                if chapters:
                    st.caption(f"{done}/{len(chapters)}话")
                st.markdown(
                    f"<span style='color:#111;font-weight:600'>{title[:18]}</span>",
                    unsafe_allow_html=True
                )
tab_labels = ["📋 漫画列表", "📥 下载管理", "📖 本地浏览", "📊 进度详情"]
tab_cols = st.columns(4)
for i, label in enumerate(tab_labels):
    with tab_cols[i]:
        btn_type = "primary" if st.session_state.active_tab == i else "secondary"
        if st.button(label, key=f"tab_btn_{i}", type=btn_type, width='stretch'):
            st.session_state.active_tab = i
            st.rerun()

st.divider()

if st.session_state.active_tab == 0:
    st.subheader(f"收藏漫画列表 ({len(comics)} 部)")

    col_search, col_filter, col_page = st.columns([3, 2, 1])

    with col_search:
        search = st.text_input("🔍 搜索", placeholder="标题、作者或 ID...", label_visibility="collapsed")

    with col_filter:
        status_filter = st.selectbox(
            "状态筛选",
            ["全部", "已完成", "未完成", "缺详情"],
            label_visibility="collapsed"
        )

    with col_page:
        page_size = 50
        page = st.number_input(
            "页码", 1, max(1, len(comics) // page_size + 1), 1,
            label_visibility="collapsed"
        ) - 1

    # 筛选逻辑
    filtered = comics
    if search:
        filtered = [c for c in comics if
            search.lower() in c.get("title", "").lower() or
            search.lower() in c.get("author", "").lower() or
            search in c.get("_id", "")
        ]

    if status_filter == "已完成":
        filtered = [c for i, c in enumerate(comics) if i in completed_set and c in filtered]
    elif status_filter == "未完成":
        filtered = [c for i, c in enumerate(comics) if i not in completed_set and i not in missing_detail and c in filtered]
    elif status_filter == "缺详情":
        filtered = [c for i, c in enumerate(comics) if i in missing_detail and c in filtered]

    start = page * page_size
    end = min(start + page_size, len(filtered))
    st.caption(f"显示 {start+1}-{end} / 共 {len(filtered)} 部")

    for i, c in enumerate(filtered[start:end]):
        idx = start + i + 1
        # 找到原始索引
        try:
            orig_idx = comics.index(c)
        except ValueError:
            orig_idx = idx - 1

        # 状态判定
        if orig_idx in completed_set:
            status_badge = "✅"
            status_label = "已完成"
        elif orig_idx in missing_detail:
            status_badge = "⚠️"
            status_label = "缺详情"
        else:
            # 检查是否有部分下载
            ch_done, ch_total, ch_status = load_chapter_progress(orig_idx)
            if ch_status == "partial" or (ch_status == "done" and ch_done > 0):
                status_badge = "🔄"
                status_label = f"{ch_done}/{ch_total}话"
            elif ch_status == "no_detail":
                status_badge = "⚠️"
                status_label = "缺详情"
            else:
                status_badge = "⬜"
                status_label = "未开始"

        col1, col2, col3 = st.columns([1, 6, 2])
        with col1:
            thumb = c.get("thumb", {})
            cover_url = _build_image_url(thumb)
            if cover_url:
                st.image(cover_url, width=80)
        with col2:
            st.markdown(f"**{idx}. {c['title']}**  {status_badge}")
            st.caption(f"作者: {c.get('author', '?')} | {c.get('pagesCount', 0)}P | {c.get('epsCount', 0)}话 | {status_label}")
            if status_label not in ("已完成", "缺详情", "未开始"):
                ch_done, ch_total, _ = load_chapter_progress(orig_idx)
                if ch_total > 0:
                    st.progress(ch_done / ch_total, text=f"{ch_done}/{ch_total} 话")
        with col3:
            st.caption(f"👁 {c.get('totalViews', 0):,}")
            st.caption(f"❤️ {c.get('totalLikes', 0):,}")
        st.divider()

elif st.session_state.active_tab == 1:
    st.subheader("📥 图片下载")

    col_a, col_b = st.columns(2)
    with col_a:
        download_range = st.text_input("下载范围", value="1", help="单个编号 / 范围(1-5) / all")
    with col_b:
        st.text(" ")
        start_btn = st.button("🚀 开始下载", type="primary", width='stretch')

    if start_btn and comics:
        if download_range == "all":
            indices = list(range(len(comics)))
        elif "-" in download_range:
            parts = download_range.split("-")
            s, e = int(parts[0]) - 1, int(parts[1]) - 1
            indices = list(range(max(0, s), min(len(comics), e + 1)))
        else:
            indices = [int(download_range) - 1]

        # 过滤缺详情和已完成的
        skip_no_detail = [i for i in indices if i in missing_detail]
        skip_done = [i for i in indices if i in completed_set and i not in skip_no_detail]
        remaining = [i for i in indices if i not in missing_detail and i not in completed_set]

        if skip_no_detail:
            st.warning(f"跳过 {len(skip_no_detail)} 部缺详情")
        if skip_done:
            st.info(f"跳过 {len(skip_done)} 部已完成")

        indices = remaining
        if not indices:
            st.success("没有需要下载的漫画！")
            st.stop()

        total_comics_to_dl = len(indices)

        # 进度显示区域
        col_prog1, col_prog2 = st.columns(2)
        with col_prog1:
            overall_bar = st.progress(0, text="准备开始...")
        with col_prog2:
            chapter_bar = st.progress(0, text="")

        status_text = st.empty()
        log_area = st.empty()
        log_lines = []

        page_concurrency = config.get("page_concurrency", 3)

        for ci, idx in enumerate(indices):
            c = comics[idx]
            safe_title = safe_filename(c["title"])
            folder = detail_base / f"{idx+1:03d}_{safe_title}"

            if not folder.exists():
                log_lines.append(f"⚠️ [{idx+1}] {c['title']} — 缺详情，跳过")
                log_area.text("\n".join(log_lines[-8:]))
                continue

            overall_bar.progress(
                ci / total_comics_to_dl,
                text=f"📖 [{ci+1}/{total_comics_to_dl}] {c['title']}"
            )
            status_text.info(f"正在获取章节列表...")
            chapter_bar.progress(0, text="")

            # 获取章节
            all_eps = []
            ep_page = 1
            try:
                while True:
                    ep_data = client.get_episodes(c["_id"], page=ep_page)
                    eps_block = ep_data.get("data", {}).get("eps", {})
                    all_eps.extend(eps_block.get("docs", []))
                    if ep_page >= eps_block.get("pages", 1):
                        break
                    ep_page += 1
            except RuntimeError as e:
                log_lines.append(f"❌ [{idx+1}] {c['title']} — {e}")
                log_area.text("\n".join(log_lines[-8:]))
                continue

            total_eps = len(all_eps)

            for ei, ep in enumerate(all_eps):
                order = ep["order"]
                ep_title = ep.get("title", f"第{order}话")
                safe_ep = safe_filename(ep_title, max_len=40)
                ep_folder = folder / f"{order:02d}_{safe_ep}"
                ep_folder.mkdir(parents=True, exist_ok=True)

                chapter_bar.progress(
                    ei / max(total_eps, 1),
                    text=f"第{order}/{total_eps}话: {ep_title}"
                )

                # 获取图片列表
                all_pages = []
                pg_page = 1
                total_pages = 0
                try:
                    while True:
                        pg_data = client.get_pages(c["_id"], order, page=pg_page)
                        pages_block = pg_data.get("data", {}).get("pages", {})
                        docs = pages_block.get("docs", [])
                        all_pages.extend(docs)
                        total_pages = pages_block.get("total", 0)
                        if pg_page >= pages_block.get("pages", 1):
                            break
                        pg_page += 1
                except RuntimeError as e:
                    log_lines.append(f"⚠️ [{idx+1}] 第{order}话: {e}")
                    log_area.text("\n".join(log_lines[-8:]))
                    continue

                existing_count = len(list(ep_folder.glob("*")))
                if existing_count >= total_pages and total_pages > 0:
                    continue

                # 收集下载任务
                tasks = []
                for pi, p in enumerate(all_pages):
                    media = p.get("media", {})
                    fs = media.get("fileServer", "")
                    path_val = media.get("path", "")
                    if not fs or not path_val:
                        continue

                    img_url = f"{fs}/static/{path_val}"
                    ext = Path(path_val.split("?")[0]).suffix or ".jpg"
                    img_path = ep_folder / f"{pi+1:03d}{ext}"

                    if img_path.exists() and img_path.stat().st_size > 0:
                        continue

                    tasks.append((pi, img_url, img_path))

                if tasks:
                    status_text.info(f"📥 {c['title']} — 第{order}话: 下载 {len(tasks)} 张")
                    with ThreadPoolExecutor(max_workers=page_concurrency) as executor:
                        future_map = {
                            executor.submit(download_image, url, path): (pi, path)
                            for pi, url, path in tasks
                        }
                        for future in as_completed(future_map):
                            try:
                                future.result()
                            except Exception:
                                pass

                time.sleep(client.request_delay)

            overall_bar.progress(
                (ci + 1) / total_comics_to_dl,
                text=f"✅ [{ci+1}/{total_comics_to_dl}] {c['title']}"
            )
            log_lines.append(f"✅ [{idx+1}] {c['title']} — 完成 {total_eps} 话")
            log_area.text("\n".join(log_lines[-8:]))

        chapter_bar.progress(1.0, text="全部完成!")
        overall_bar.progress(1.0, text=f"🎉 下载完成！共 {total_comics_to_dl} 部漫画")
        status_text.success(f"下载完成！共 {total_comics_to_dl} 部漫画")



# ====== Tab3 主入口 ======
elif st.session_state.active_tab == 2:
    st.subheader("📖 本地漫画浏览")

    view = st.session_state.get("local_view", "grid")
    if view == "reader":
        folder_path = st.session_state.get("local_folder")
        if not folder_path:
            st.warning("请先选择一部漫画")
            st.session_state.local_view = "grid"
            st.rerun()

        chapters_file = Path(folder_path) / "chapters.json"
        if chapters_file.exists():
            with open(chapters_file, "r", encoding="utf-8") as f:
                chapters = json.load(f).get("chapters", [])
        else:
            chapters = []
        ch_idx = st.session_state.get("local_chapter_idx", 0)
        _render_reader(folder_path, chapters, ch_idx)

    elif view == "detail":
        folder_path = st.session_state.get("local_folder")
        if not folder_path:
            st.warning("请先选择一部漫画")
            st.session_state.local_view = "grid"
            st.rerun()
        _render_detail(folder_path)

    else:
        _render_grid()

elif st.session_state.active_tab == 3:
    st.subheader("📊 下载进度详情")

    if total_comics == 0:
        st.info("请先获取漫画列表 (favourites)")
    else:
        # 汇总统计
        col_k1, col_k2, col_k3, col_k4 = st.columns(4)
        col_k1.metric("总漫画", total_comics)
        col_k2.metric("已完成", done_count, delta=f"{done_count - (done_count-1) if done_count > 0 else 0}")
        col_k3.metric("未完成", incomplete_count)
        col_k4.metric("缺详情", missing_count)

        st.divider()

        # 未完成列表 (带章节进度)
        incomplete_indices = [
            i for i in range(total_comics)
            if i not in completed_set and i not in missing_detail
        ]

        if incomplete_indices:
            st.subheader(f"🔄 未完成 ({len(incomplete_indices)} 部)")
            # 只显示前100个避免卡顿
            show_incomplete = incomplete_indices[:100]

            for idx in show_incomplete:
                c = comics[idx]
                ch_done, ch_total, _ = load_chapter_progress(idx)

                col_a, col_b = st.columns([4, 1])
                with col_a:
                    st.markdown(f"**{idx+1}. {c['title']}**")
                    if ch_total > 0:
                        st.progress(ch_done / ch_total, text=f"{ch_done}/{ch_total} 话")
                    else:
                        st.caption("等待下载")
                with col_b:
                    st.caption(f"{c.get('epsCount', '?')}话")
                st.divider()

            if len(incomplete_indices) > 100:
                st.caption(f"... 还有 {len(incomplete_indices) - 100} 部未显示")
        else:
            st.success("全部下载完成！")

        # 缺详情列表
        if missing_detail:
            with st.expander(f"⚠️ 缺少详情 ({missing_count} 部)", expanded=False):
                for idx in missing_detail:
                    c = comics[idx]
                    st.markdown(f"**{idx+1}.** {c['title']} — 请运行 `detail_all`")
