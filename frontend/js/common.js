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
    { label: '<svg style="width:16px;height:16px;vertical-align:-3px;margin-right:4px" viewBox="0 0 512 512"><path d="M462.3 62.6C407.5 15.9 326 24.3 275.7 76.2L256 96.5l-19.7-20.3C186.1 24.3 104.5 15.9 49.7 62.6c-62.8 53.6-66.1 149.8-9.9 207.9l193.5 199.8c12.5 12.9 32.8 12.9 45.3 0l193.5-199.8c56.3-58.1 53-154.3-9.8-207.9z" fill="currentColor"/></svg>\u6536\u85CF', href: 'favorites.html' },
    { label: '<svg style="width:16px;height:16px;vertical-align:-3px;margin-right:4px" viewBox="0 0 384 512"><path d="M216 23.86c0-23.8-30.65-32.77-44.15-13.04C48 191.85 224 200 224 288c0 35.63-29.11 64.46-64.85 63.99-35.17-.45-63.15-29.77-63.15-64.94v-85.51c0-21.7-26.47-32.23-41.43-16.5C27.8 213.16 0 261.33 0 320c0 105.87 86.13 192 192 192s192-86.13 192-192c0-170.29-168-193-168-296.14z" fill="currentColor"/></svg>\u6392\u884C\u699C', href: 'leaderboard.html' },
    { label: '<svg style="width:16px;height:16px;vertical-align:-3px;margin-right:4px" viewBox="0 0 24 24"><rect x="3" y="3" width="18" height="18" rx="2" ry="2" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="8.5" cy="8.5" r="1.5" fill="currentColor" stroke="none"/><polyline points="21 15 16 10 5 21" fill="none" stroke="currentColor" stroke-width="2"/></svg>\u672C\u5730\u6D4F\u89C8', href: 'index.html' },
    { label: '<svg style="width:16px;height:16px;vertical-align:-3px;margin-right:4px" viewBox="0 0 512 512"><path d="M288 32c0-17.7-14.3-32-32-32s-32 14.3-32 32v242.7l-73.4-73.4c-12.5-12.5-32.8-12.5-45.3 0s-12.5 32.8 0 45.3l128 128c12.5 12.5 32.8 12.5 45.3 0l128-128c12.5-12.5 12.5-32.8 0-45.3s-32.8-12.5-45.3 0L320 274.7V32zM64 352c-35.3 0-64 28.7-64 64v32c0 35.3 28.7 64 64 64h384c35.3 0 64-28.7 64-64v-32c0-35.3-28.7-64-64-64H346.5l-45.3 45.3c-25 25-65.5 25-90.5 0L165.5 352H64zm368 56a24 24 0 1 1 0 48 24 24 0 1 1 0-48z" fill="currentColor"/></svg>\u4E0B\u8F7D\u7BA1\u7406', href: 'download.html' },
    { label: '<svg style="width:16px;height:16px;vertical-align:-3px;margin-right:4px" viewBox="0 0 24 24"><path d="M10 3H4a1 1 0 0 0-1 1v6a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1V4a1 1 0 0 0-1-1zM9 9H5V5h4v4zm11-6h-6a1 1 0 0 0-1 1v6a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1V4a1 1 0 0 0-1-1zm-1 6h-4V5h4v4zm-9 4H4a1 1 0 0 0-1 1v6a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1v-6a1 1 0 0 0-1-1zm-1 6H5v-4h4v4zm8-6c-2.206 0-4 1.794-4 4s1.794 4 4 4 4-1.794 4-4-1.794-4-4-4zm0 6c-1.103 0-2-.897-2-2s.897-2 2-2 2 .897 2 2-.897 2-2 2z" fill="currentColor"/></svg>\u5206\u7C7B', href: 'categories.html' },
    { label: '<svg style="width:16px;height:16px;vertical-align:-3px;margin-right:4px" viewBox="0 0 512 512"><path d="M505 442.7L405.3 343c-4.5-4.5-10.6-7-17-7H372c27.6-35.3 44-79.7 44-128C416 93.1 322.9 0 208 0S0 93.1 0 208s93.1 208 208 208c48.3 0 92.7-16.4 128-44v16.3c0 6.4 2.5 12.5 7 17l99.7 99.7c9.4 9.4 24.6 9.4 33.9 0l28.3-28.3c9.4-9.4 9.4-24.6.1-34zM208 336c-70.7 0-128-57.2-128-128 0-70.7 57.2-128 128-128 70.7 0 128 57.2 128 128 0 70.7-57.2 128-128 128z" fill="currentColor"/></svg>\u641C\u7D22', href: 'search.html' },
    { label: '<svg style="width:16px;height:16px;vertical-align:-3px;margin-right:4px" viewBox="0 0 512 512"><path d="M487.4 315.7l-42.6-24.6c4.3-23.2 4.3-47 0-70.2l42.6-24.6c4.9-2.8 7.1-8.6 5.5-14-11.1-35.6-30-67.8-54.7-94.6-3.8-4.1-10-5.1-14.8-2.3L380.8 110c-17.9-15.4-38.5-27.3-60.8-35.1V25.8c0-5.6-3.9-10.5-9.4-11.7-36.7-8.2-74.3-7.8-109.2 0-5.5 1.2-9.4 6.1-9.4 11.7V75c-22.2 7.9-42.8 19.8-60.8 35.1L88.7 85.5c-4.9-2.8-11-1.9-14.8 2.3-24.7 26.7-43.6 58.9-54.7 94.6-1.7 5.4.6 11.2 5.5 14L67.3 221c-4.3 23.2-4.3 47 0 70.2l-42.6 24.6c-4.9 2.8-7.1 8.6-5.5 14 11.1 35.6 30 67.8 54.7 94.6 3.8 4.1 10 5.1 14.8 2.3l42.6-24.6c17.9 15.4 38.5 27.3 60.8 35.1v49.2c0 5.6 3.9 10.5 9.4 11.7 36.7 8.2 74.3 7.8 109.2 0 5.5-1.2 9.4-6.1 9.4-11.7v-49.2c22.2-7.9 42.8-19.8 60.8-35.1l42.6 24.6c4.9 2.8 11 1.9 14.8-2.3 24.7-26.7 43.6-58.9 54.7-94.6 1.5-5.5-.7-11.3-5.6-14.1zM256 336c-44.1 0-80-35.9-80-80s35.9-80 80-80 80 35.9 80 80-35.9 80-80 80z" fill="currentColor"/></svg>\u8BBE\u7F6E', href: 'settings.html' },
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

// ==== 主题 ====
(function() {
  const theme = _loadState('theme', {name: ''}).name;
  if (theme) document.documentElement.setAttribute('data-theme', theme);
})();

function changeTheme(name) {
  if (name) {
    document.documentElement.setAttribute('data-theme', name);
  } else {
    document.documentElement.removeAttribute('data-theme');
  }
  _saveState('theme', {name: name});
}

// ==== 模糊模式 ====
if (_loadState('blur', {on: false}).on) {
  document.body.classList.add('blur-mode');
}
