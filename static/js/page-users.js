// 用户管理页面模块（逻辑与原单文件版本保持一致）
(function () {
  'use strict';
  const { $, el, API, toast, openModal, closeModal } = window.QM;
  const QM = window.QM;

  async function initUsers() {
    const tbody = $('#userTbody');
    const res = await API('GET', '/api/users');
    const users = res.users || [];
    tbody.innerHTML = '';
    users.forEach(u => {
      const isAdmin = u === 'admin';
      const tr = el('tr', {}, [
        el('td', { text: u }),
        el('td', {}, [
          el('button', { class: 'btn btn-sm', onclick: () => resetUser(u) }, ['重置密码']),
          isAdmin
            ? el('button', { class: 'btn btn-sm btn-danger', disabled: true, title: '默认管理员不可删除' }, ['删除'])
            : el('button', { class: 'btn btn-sm btn-danger', onclick: () => delUser(u) }, ['删除'])
        ])
      ]);
      tbody.appendChild(tr);
    });

    $('#btnAddUser').addEventListener('click', () => { $('#userForm').reset(); $('#userMsg').textContent = ''; openModal('userModal'); });
    $('#userForm').addEventListener('submit', async e => {
      e.preventDefault();
      const f = new FormData($('#userForm'));
      const r = await API('POST', '/api/users', { username: f.get('username'), password: f.get('password') });
      $('#userMsg').textContent = r.msg || '';
      if (r.ok) { closeModal('userModal'); toast('已添加', true); initUsers(); }
    });
  }

  async function delUser(u) {
    if (u === 'admin') { toast('默认管理员 admin 不可删除', false); return; }
    if (!confirm('确定删除用户 ' + u + '？')) return;
    const r = await API('DELETE', '/api/users/' + encodeURIComponent(u));
    toast(r.msg, r.ok);
    if (r.ok) initUsers();
  }

  async function resetUser(u) {
    const pw = prompt('为 ' + u + ' 设置新密码：');
    if (!pw) return;
    const r = await API('POST', '/api/users/' + encodeURIComponent(u) + '/reset', { password: pw });
    toast(r.msg, r.ok);
  }

  QM.register('users', initUsers);
})();
