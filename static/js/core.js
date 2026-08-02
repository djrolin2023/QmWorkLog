// 乾明工作台账系统 - 核心基础设施与公共组件
// 提供共享 helpers、全局状态、页面注册表、调度与启动逻辑。
// 各 page-*.js 模块通过 window.QM 访问共享能力，并调用 QM.register 注册 init。
(function () {
  'use strict';

  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));

  function el(tag, attrs, children) {
    const e = document.createElement(tag);
    if (attrs) for (const k in attrs) {
      if (k === 'class') e.className = attrs[k];
      else if (k === 'html') e.innerHTML = attrs[k];
      else if (k === 'text') e.textContent = attrs[k];
      else if (k.startsWith('on') && typeof attrs[k] === 'function') e.addEventListener(k.slice(2), attrs[k]);
      else e.setAttribute(k, attrs[k]);
    }
    (children || []).forEach(c => e.appendChild(typeof c === 'string' ? document.createTextNode(c) : c));
    return e;
  }

  async function API(method, url, data, isForm) {
    const opt = { method, credentials: 'same-origin' };
    if (data !== undefined) {
      if (isForm) opt.body = data;
      else { opt.headers = { 'Content-Type': 'application/json' }; opt.body = JSON.stringify(data); }
    }
    const res = await fetch(url, opt);
    let json;
    try { json = await res.json(); } catch (e) { json = {}; }
    return json;
  }

  function toast(msg, ok) {
    let t = $('#toast');
    if (!t) { t = el('div', { id: 'toast', class: 'toast' }); document.body.appendChild(t); }
    t.textContent = msg;
    t.className = 'toast show' + (ok === false ? ' err' : ok === true ? ' ok' : '');
    clearTimeout(t._t);
    t._t = setTimeout(() => { t.className = 'toast'; }, 2600);
  }

  function openModal(id) { const m = $('#' + id); if (m) m.style.display = 'flex'; }
  function closeModal(id) { const m = $('#' + id); if (m) m.style.display = 'none'; }

  // 通用确认弹窗：QM.confirm(text, onYes, title?)
  function confirmModal(text, onYes, title) {
    const t = $('#confirmText'), h = $('#confirmTitle'), ok = $('#confirmOk'), cancel = $('#confirmCancel');
    if (t) t.textContent = text || '确定执行该操作？';
    if (h) h.textContent = title || '确认操作';
    if (ok) ok.onclick = () => { closeModal('confirmModal'); try { onYes && onYes(); } catch (e) {} };
    if (cancel) cancel.onclick = () => closeModal('confirmModal');
    openModal('confirmModal');
  }

  // 全局状态
  const state = { types: [], type: '', year: 0, month: 0, day: 0, date: '', content: '' };

  async function loadTypes() {
    const res = await API('GET', '/api/types');
    if (!res.ok) return;
    state.types = res.types || [];
    ['#typeSelect', '#sumType', '#expType'].forEach(sel => {
      const node = $(sel);
      if (!node) return;
      const cur = node.value;
      node.innerHTML = '';
      state.types.forEach(t => node.appendChild(el('option', { value: t.name }, [t.name])));
      if (cur) node.value = cur;
    });
    buildTypeChildren();
  }

  function buildTypeChildren() {
    const box = $('#typeChildren');
    if (!box) return;
    const cur = new URLSearchParams(location.search).get('type');
    box.innerHTML = '';
    state.types.forEach(t => {
      const a = el('a', { class: 'menu-child', href: '/ledger?type=' + encodeURIComponent(t.name) }, [t.name]);
      if (t.name === cur) a.classList.add('active');
      box.appendChild(a);
    });
  }

  function highlightMenu() {
    const page = document.body.dataset.page;
    $$('.menu-parent[data-page]').forEach(b => {
      b.classList.toggle('active', b.dataset.page === page);
    });
  }

  // ---------------- 公共组件：顶栏日期 / 账号下拉 / 版本历史 / 面包屑 / 密码弹窗 ----------------

  const WEEK = ['日', '一', '二', '三', '四', '五', '六'];
  const pad = (n) => String(n).padStart(2, '0');
  function renderTopbarDate() {
    const elDate = document.getElementById('topbarDate');
    if (!elDate) return;
    const n = new Date();
    elDate.textContent = `${n.getFullYear()}年${n.getMonth() + 1}月${n.getDate()}日 星期${WEEK[n.getDay()]} ${pad(n.getHours())}:${pad(n.getMinutes())}:${pad(n.getSeconds())}`;
  }

  function toggleUserMenu() {
    const dd = document.getElementById('userDropdown');
    if (dd) dd.classList.toggle('open');
  }
  document.addEventListener('click', (e) => {
    const um = document.getElementById('userMenu');
    if (um && !um.contains(e.target)) {
      const dd = document.getElementById('userDropdown');
      if (dd) dd.classList.remove('open');
    }
  });

  async function showVersionHistory() {
    const box = document.getElementById('verList');
    if (!box) return;
    box.innerHTML = '<div class="ver-loading">加载中…</div>';
    openModal('verModal');
    try {
      const r = await API('GET', '/api/version');
      if (!r.ok) { box.innerHTML = '<div class="ver-loading">加载失败</div>'; return; }
      const hist = (r.history || []).slice().reverse();
      if (!hist.length) { box.innerHTML = '<div class="ver-loading">暂无记录</div>'; return; }
      box.innerHTML = hist.map(h => {
        const tag = h.type === 'major'
          ? '<span class="ver-tag major">大改动</span>'
          : '<span class="ver-tag minor">小改动</span>';
        const reason = (h.reason || '').replace(/</g, '&lt;');
        return `<div class="ver-item">
          <div class="ver-row"><span class="ver-no">V${h.ver}</span>${tag}<span class="ver-date">${h.date}</span></div>
          <div class="ver-reason">${reason}</div>
        </div>`;
      }).join('');
    } catch (e) {
      box.innerHTML = '<div class="ver-loading">加载失败</div>';
    }
  }

  const PAGE_TITLES = {
    dashboard: '数据大屏', ledger: '工作台账', types: '台账管理', summary: '智能总结',
    archive: '归档管理', impexp: '导入导出', users: '用户管理', logs: '系统日志',
    settings: '系统设置', manual: '使用手册', about: '关于系统'
  };
  function renderBreadcrumb() {
    const bc = document.getElementById('breadcrumb');
    if (!bc) return;
    const page = document.body.dataset.page;
    const title = PAGE_TITLES[page] || '';
    bc.innerHTML = '<span class="bc-item">首页</span>';
    if (title) {
      const s = document.createElement('span');
      s.className = 'bc-item';
      s.textContent = title;
      bc.appendChild(s);
    }
  }

  function changePassword() { $('#pwdMsg').textContent = ''; openModal('pwdModal'); }
  function initPwdModal() {
    const f = $('#pwdForm');
    if (!f) return;
    f.addEventListener('submit', async e => {
      e.preventDefault();
      const d = new FormData(f);
      if (d.get('new') !== d.get('confirm')) { $('#pwdMsg').textContent = '两次密码不一致'; return; }
      const r = await API('POST', '/api/account/password', { old: d.get('old'), new: d.get('new') });
      $('#pwdMsg').textContent = r.msg || '';
      if (r.ok) { toast('密码已修改', true); closeModal('pwdModal'); f.reset(); }
    });
  }

  function zoom(src) {
    const m = $('#zoomModal');
    if (!m) {
      const d = el('div', { id: 'zoomModal', class: 'modal', onclick: function () { this.style.display = 'none'; } });
      d.appendChild(el('img', { src }));
      document.body.appendChild(d);
    } else { m.querySelector('img').src = src; }
    $('#zoomModal').style.display = 'flex';
  }

  // ---------------- 页面注册表与调度 ----------------
  const registry = {};
  function register(name, fn) {
    registry[name] = fn;
    // 同时挂到 window.App，兼容模板内联 App.initXxx() 调用
    window.App['init' + name.charAt(0).toUpperCase() + name.slice(1)] = fn;
  }

  let dispatched = false;
  function dispatch() {
    if (dispatched) return;
    dispatched = true;
    const page = document.body.dataset.page;
    renderBreadcrumb();
    renderTopbarDate();
    setInterval(renderTopbarDate, 1000);
    if (registry[page]) registry[page]();
  }

  // ---------------- SPA 局部加载：菜单点击不整页刷新，顶栏/面包屑常驻固定 ----------------
  async function navigate(url, push = true) {
    try {
      const res = await fetch(url, { credentials: 'same-origin' });
      const html = await res.text();
      const doc = new DOMParser().parseFromString(html, 'text/html');
      const newPage = doc.getElementById('pageContent');
      if (!newPage) { // 目标非 SPA 页（如登录页）→ 整页跳转
        window.location.href = url;
        return;
      }
      const pc = document.getElementById('pageContent');
      pc.innerHTML = newPage.innerHTML;                       // 仅替换内容区，topbar 保留
      const page = doc.body.dataset.page || '';
      document.body.dataset.page = page;                      // 更新页面标识
      if (push) history.pushState({ page: page }, '', url);   // 更新地址栏（不刷新）
      highlightMenu();                                        // 高亮菜单
      renderBreadcrumb();                                     // 仅更新面包屑文字，DOM 不重建 → 视觉固定
      if (registry[page]) registry[page]();                   // 重新初始化当前页
      window.scrollTo(0, 0);
    } catch (e) {
      window.location.href = url;                             // 异常回退整页跳转
    }
  }

  // 拦截侧边栏菜单（含动态生成的台账子项）左键点击 → SPA 局部加载
  document.addEventListener('click', (e) => {
    if (e.defaultPrevented) return;
    if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    const a = e.target.closest('a.menu-parent, a.menu-child');
    if (!a) return;
    const href = a.getAttribute('href');
    if (!href || href === '#' || href.startsWith('javascript:') || href.startsWith('http')) return;
    e.preventDefault();
    navigate(href);
  });

  // 浏览器前进/后退
  window.addEventListener('popstate', () => {
    navigate(location.pathname + location.search, false);
  });

  // 暴露共享能力，供 page-*.js 模块使用
  window.QM = { $, $$, el, API, toast, openModal, closeModal, confirm: confirmModal, state, loadTypes, buildTypeChildren, highlightMenu, zoom, register, dispatch, navigate };
  // 暴露公共方法，供模板内联事件调用
  window.App = {
    changePassword, closeModal, zoom, showVersionHistory, toggleUserMenu
  };

  document.addEventListener('DOMContentLoaded', () => {
    highlightMenu();
    loadTypes().then(dispatch);
    initPwdModal();
  });
})();
