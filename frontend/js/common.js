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
    { label: '📚 收藏', href: 'favorites.html' },
    { label: '📋 本地浏览', href: 'index.html' },
    { label: '📥 下载管理', href: 'download.html' },
    { label: '⚙️ 设置', href: 'settings.html' },
  ];
  const nav = document.getElementById('topnav');
  if (!nav) return;
  nav.innerHTML = pages.map(p =>
    `<a href="${p.href}" class="${active === p.href ? 'active' : ''}">${p.label}</a>`
  ).join('');
  updateTokenStatus();
}

// ==== 阅读器入口：在点击手势内先全屏再跳转（全屏状态跨同源导航保持） ====
function goReader(url) {
  if (!document.fullscreenElement) {
    document.documentElement.requestFullscreen()
      .then(() => { location.href = url; })
      .catch(() => { location.href = url; });
  } else {
    location.href = url;
  }
}

// ==== 模糊模式 ====
if (_loadState('blur', {on: false}).on) {
  document.body.classList.add('blur-mode');
}
