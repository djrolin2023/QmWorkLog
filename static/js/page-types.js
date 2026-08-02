// 台账管理（类型）页面模块（逻辑与原单文件版本保持一致）
(function () {
  'use strict';
  const { $, el, API, toast, openModal, closeModal } = window.QM;
  const QM = window.QM;
  let renameTarget = null;

  async function initTypes() {
    const list = $('#typeList');
    const res = await API('GET', '/api/types');
    const types = res.types || [];
    list.innerHTML = '';
    types.forEach(t => {
      const li = el('li', { class: 'type-item' }, [
        el('span', { text: t.name }),
        el('div', { class: 'type-ops' }, [
          el('button', { class: 'btn btn-sm', onclick: () => openRename(t) }, ['重命名']),
          el('button', { class: 'btn btn-sm btn-danger', onclick: () => delType(t) }, ['删除'])
        ])
      ]);
      list.appendChild(li);
    });
    $('#btnAddType').addEventListener('click', () => {
      $('#typeForm').reset(); $('#typeMsg').textContent = '';
      openModal('typeModal');
      const inp = $('#typeForm input[name=name]'); if (inp) setTimeout(() => inp.focus(), 50);
    });
    $('#typeForm').addEventListener('submit', async e => {
      e.preventDefault();
      const name = $('#typeForm input[name=name]').value.trim();
      if (!name) return;
      const r = await API('POST', '/api/types', { name });
      $('#typeMsg').textContent = r.msg || '';
      if (r.ok) { closeModal('typeModal'); toast('已添加', true); initTypes(); }
      else $('#typeMsg').style.color = 'var(--danger)';
    });
    $('#renameForm').addEventListener('submit', async e => {
      e.preventDefault();
      const name = $('#renameForm input[name=name]').value.trim();
      if (!name || !renameTarget) return;
      if (name === renameTarget.name) { closeModal('renameModal'); return; }
      const r = await API('PUT', '/api/types/' + renameTarget.id, { name });
      $('#renameMsg').textContent = r.msg || '';
      if (r.ok) { closeModal('renameModal'); toast('已重命名', true); initTypes(); }
      else $('#renameMsg').style.color = 'var(--danger)';
    });
  }

  function openRename(t) {
    renameTarget = t;
    const inp = $('#renameForm input[name=name]');
    inp.value = t.name;
    $('#renameMsg').textContent = '';
    openModal('renameModal');
    setTimeout(() => inp.focus(), 50);
  }

  async function delType(t) {
    if (!confirm('确定删除类型 ' + t.name + '？相关台账文件不会被移动。')) return;
    const r = await API('DELETE', '/api/types/' + t.id);
    toast(r.msg, r.ok);
    if (r.ok) initTypes();
  }

  QM.register('types', initTypes);
})();
