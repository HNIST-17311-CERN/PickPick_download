// ==== API ====
const BASE = location.protocol === 'file:' ? 'http://127.0.0.1:8000' : '';
const API = BASE + '/api';

function resolveUrl(url) {
  if (!url || url.startsWith('http://') || url.startsWith('https://') || url.startsWith('data:')) return url;
  return BASE + url;
}

async function fetchJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(r.status);
  return r.json();
}

// ==== 状态 ====
function _loadState(key, defaults) {
  try {
    const raw = sessionStorage.getItem(key);
    if (raw) return JSON.parse(raw);
  } catch(e) {}
  return {...defaults};
}
function _saveState(key, state) {
  try { sessionStorage.setItem(key, JSON.stringify(state)); } catch(e) {}
}

// ==== 顶栏 ====
async function updateTokenStatus() {
  const el = document.getElementById('tokenStatus');
  if (!el) return;
  const cache = JSON.parse(sessionStorage.getItem('tokenStatus') || '{}');
  if (cache.ts && Date.now() - cache.ts < 300000) {
    el.innerHTML = cache.html; return;
  }
  try {
    const r = await fetch(`${API}/config/test-token`, {method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'});
    const j = await r.json();
    if (j.ok) {
      const h = j.remaining_hours;
      const dot = h > 48 ? '#4ade80' : h > 0 ? '#fbbf24' : '#f87171';
      const html = `<span style="color:${dot}">●</span> ${j.user} · ${h > 48 ? h+'h' : h > 0 ? h+'h⚠' : '已过期'}`;
      el.innerHTML = html;
      sessionStorage.setItem('tokenStatus', JSON.stringify({html, ts: Date.now()}));
    } else {
      el.innerHTML = '<span style="color:#f87171">● 未登录</span>';
    }
  } catch(e) {
    el.innerHTML = '<span style="color:#666">● 离线</span>';
  }
}

function renderTopbar(active) {
  const pages = [
    { label: '\u{1F4DA} \u6536\u85CF', href: 'favorites.html' },
    { label: '\u{1F4CB} \u672C\u5730\u6D4F\u89C8', href: 'index.html' },
    { label: '\u{1F4E5} \u4E0B\u8F7D\u7BA1\u7406', href: 'download.html' },
    { label: '\u{1F4C2} \u5206\u7C7B', href: 'categories.html' },
    { label: '\u{1F50D} \u641C\u7D22', href: 'search.html' },
    { label: '\u2699\uFE0F \u8BBE\u7F6E', href: 'settings.html' },
  ];
  const nav = document.getElementById('topnav');
  if (!nav) return;
  nav.innerHTML = pages.map(p =>
    `<a href="${p.href}" class="${active === p.href ? 'active' : ''}">${p.label}</a>`
  ).join('');

  const searchWrap = document.getElementById('searchWrap');
  if (searchWrap) {
    const params = new URLSearchParams(location.search);
    const q = params.get('keyword') || '';
    searchWrap.innerHTML = `
      <div class="search-box">
        <input type="text" class="header-search" placeholder="搜索漫画..." value="${escapeHTML(q)}"
          onkeydown="if(event.key==='Enter'){const kw=this.value.trim();if(kw)location.href='search.html?keyword='+encodeURIComponent(kw)}">
      </div>`;
  }

  updateTokenStatus();
}

function escapeHTML(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// ==== 阅读器入口：在当前页全屏 + iframe 浮层，避免跨页导航丢失全屏手势 ====
function goReader(url) {
  // 如果已经在阅读器 iframe 中，通知父窗口更新 src
  if (window.parent !== window && window.parent._updateReaderFrame) {
    window.parent._updateReaderFrame(url);
    return;
  }
  // 如果已有浮层（说明已在阅读模式），直接更新 iframe src
  const existingFrame = document.getElementById('readerFrame');
  if (existingFrame) {
    existingFrame.src = url;
    return;
  }
  // 首次进入：全屏 → 浮层
  document.documentElement.requestFullscreen()
    .then(() => { _showReaderOverlay(url); })
    .catch(() => { location.href = url; });
}

function _showReaderOverlay(url) {
  history.pushState({ readerOverlay: true }, '', url);
  const overlay = document.createElement('div');
  overlay.id = 'readerOverlay';
  overlay.innerHTML = '<iframe id="readerFrame" style="width:100%;height:100%;border:none" allowfullscreen allow="fullscreen"></iframe>';
  overlay.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;z-index:99999;background:#1a1a2e';
  document.body.appendChild(overlay);
  document.getElementById('readerFrame').src = url;
}

// 父窗口暴露给 iframe 内更新地址的方法
window._updateReaderFrame = function(url) {
  const frame = document.getElementById('readerFrame');
  if (frame) {
    frame.src = url;
    history.replaceState({ readerOverlay: true }, '', url);
  }
};

// 退出全屏时清理浮层
document.addEventListener('fullscreenchange', () => {
  if (!document.fullscreenElement) {
    const overlay = document.getElementById('readerOverlay');
    if (overlay) {
      overlay.remove();
      if (history.state && history.state.readerOverlay) history.back();
    }
  }
});

// 浏览器后退时清理
window.addEventListener('popstate', (e) => {
  if (!e.state || !e.state.readerOverlay) {
    const overlay = document.getElementById('readerOverlay');
    if (overlay) {
      overlay.remove();
      if (document.fullscreenElement) document.exitFullscreen();
    }
  }
});

// ==== 模糊模式 ====
if (_loadState('blur', {on: false}).on) {
  document.body.classList.add('blur-mode');
}
