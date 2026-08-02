// 系统日志页面模块
(function () {
  'use strict';
  const { API, toast, register } = window.QM;

  const ACTION_TAG = {
    '登录': 'tag-login', '登出': 'tag-login',
    '新增台账': 'tag-add', '编辑台账': 'tag-edit', '删除台账': 'tag-del',
    '新增类型': 'tag-add', '重命名类型': 'tag-edit', '删除类型': 'tag-del',
    '导入': 'tag-add', '导出': 'tag-edit', '备份恢复': 'tag-edit',
    '重建索引': 'tag-edit',
    '新增用户': 'tag-add', '删除用户': 'tag-del', '重置密码': 'tag-edit', '修改密码': 'tag-edit',
    '系统设置': 'tag-edit',
    '智能总结-免费': 'tag-ai', '智能总结-AI': 'tag-ai',
  };

  async function loadLogs() {
    const params = { limit: 500 };
    const a = document.getElementById('logAction').value;
    const s = document.getElementById('logStart').value;
    const e = document.getElementById('logEnd').value;
    if (a) params.action = a;
    if (s) params.start = s;
    if (e) params.end = e + ' 23:59:59';
    const r = await API('GET', '/api/logs?' + new URLSearchParams(params).toString());
    const body = document.getElementById('logBody');
    const empty = document.getElementById('logEmpty');
    const count = document.getElementById('logCount');
    body.innerHTML = '';
    if (!r || !r.ok || !r.logs || r.logs.length === 0) {
      empty.style.display = 'block';
      count.textContent = '';
      return;
    }
    empty.style.display = 'none';
    count.textContent = '共 ' + r.total + ' 条';
    r.logs.forEach(function (row) {
      const tr = document.createElement('tr');
      const tag = ACTION_TAG[row.action] || 'tag-default';
      tr.innerHTML =
        '<td>' + esc(row.ts) + '</td>' +
        '<td>' + esc(row.user) + '</td>' +
        '<td><span class="log-tag ' + tag + '">' + esc(row.action) + '</span></td>' +
        '<td>' + esc(row.target) + '</td>' +
        '<td class="log-detail">' + esc(row.detail) + '</td>' +
        '<td>' + esc(row.ip) + '</td>';
      body.appendChild(tr);
    });
  }

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>]/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c];
    });
  }

  async function deleteByRange() {
    const a = document.getElementById('logAction').value;
    const s = document.getElementById('logStart').value;
    const e = document.getElementById('logEnd').value;
    if (!a && !s && !e) {
      QM.toast('请先设置操作类型或起止日期', 'warn');
      return;
    }
    let tip = '确定要删除';
    const parts = [];
    if (a) parts.push('操作类型「' + a + '」');
    if (s || e) parts.push('日期 ' + (s || '最早') + ' ~ ' + (e || '最新'));
    tip += parts.join('、') + ' 的日志吗？此操作不可恢复。';
    QM.confirm(tip, async function () {
      const r = await API('POST', '/api/logs/delete', { mode: 'range', action: a, start: s, end: e });
      if (r && r.ok) {
        QM.toast('已删除 ' + r.deleted + ' 条日志', 'success');
        await loadLogs();
      } else {
        QM.toast((r && r.msg) || '删除失败', 'error');
      }
    }, '删除所选日志');
  }

  async function deleteAll() {
    QM.confirm('确定要清空全部系统日志吗？此操作不可恢复，将删除所有历史记录。', async function () {
      const r = await API('POST', '/api/logs/delete', { mode: 'all' });
      if (r && r.ok) {
        QM.toast('已清空 ' + r.deleted + ' 条日志', 'success');
        await loadLogs();
      } else {
        QM.toast((r && r.msg) || '删除失败', 'error');
      }
    }, '清空全部日志');
  }

  async function initLogs() {
    document.getElementById('logQuery').addEventListener('click', loadLogs);
    document.getElementById('logStart').addEventListener('change', loadLogs);
    document.getElementById('logEnd').addEventListener('change', loadLogs);
    document.getElementById('logDeleteRange').addEventListener('click', deleteByRange);
    document.getElementById('logDeleteAll').addEventListener('click', deleteAll);
    await loadLogs();
  }

  register('logs', initLogs);
})();
