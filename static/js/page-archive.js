// 归档管理页面模块
(function () {
  'use strict';
  const { $, el, API, toast, openModal, closeModal } = window.QM;
  const QM = window.QM;

  async function initArchive() {
    await window.QM.loadTypes();
    // 填充归档类型下拉
    const r = await API('GET', '/api/types');
    const arcType = $('#arcType');
    if (arcType) {
      arcType.innerHTML = '';
      (r.types || []).forEach(t => arcType.appendChild(el('option', { value: t.name }, [t.name])));
    }
    // 默认年份为当前年
    const y = new Date().getFullYear();
    const yearInput = $('#arcYear');
    if (yearInput && !yearInput.value) yearInput.value = y;

    await refreshList();

    // 打开创建归档模态框
    $('#btnCreateArchive').addEventListener('click', () => {
      $('#arcMsg').textContent = '';
      openModal('archiveModal');
      const inp = $('#arcType');
      if (inp) setTimeout(() => inp.focus(), 50);
    });

    // 提交创建归档
    $('#archiveForm').addEventListener('submit', async e => {
      e.preventDefault();
      const type = $('#arcType').value;
      const year = Number($('#arcYear').value) || y;
      const monthVal = $('#arcMonth').value; // 空=整年
      const payload = { type, year };
      if (monthVal) payload.month = Number(monthVal);
      const r = await API('POST', '/api/archive/create', payload);
      $('#arcMsg').textContent = r.msg || '';
      if (r.ok) {
        closeModal('archiveModal');
        toast('归档完成', true);
        refreshList();
      } else {
        $('#arcMsg').style.color = 'var(--danger)';
      }
    });
  }

  async function refreshList() {
    const res = await API('GET', '/api/archive/list');
    const tb = $('#archiveTbody');
    tb.innerHTML = '';
    const archives = res.archives || [];
    if (!archives.length) {
      tb.innerHTML = '<tr><td colspan="5" class="td-empty">（暂无归档文件）</td></tr>';
      return;
    }
    archives.forEach(a => {
      const type = a.type;
      const year = a.year;
      (a.months || []).forEach(mo => {
        const mm = mo.month;
        const name = `${type}-${year}-${String(mm).padStart(2, '0')}`;
        const tr = el('tr', {}, [
          el('td', { text: type }),
          el('td', { text: name }),
          el('td', { text: mo.count + ' 个文件' }),
          el('td', { text: `${year}-${String(mm).padStart(2, '0')}` }),
          el('td', { class: 'op-cell' }, [
            el('a', {
              href: `/api/archive/download?type=${encodeURIComponent(type)}&year=${year}&month=${mm}`,
              class: 'btn btn-sm'
            }, ['下载']),
            el('button', {
              type: 'button', class: 'btn btn-sm btn-danger',
              onclick: () => deleteArchive(type, year, mm)
            }, ['删除'])
          ])
        ]);
        tb.appendChild(tr);
      });
      // 整年归档（汇总所有月份为一个压缩包）
      const allCount = (a.months || []).reduce((s, m) => s + (m.count || 0), 0);
      if (allCount > 0) {
        const name = `${type}-${year}（全年）`;
        const tr = el('tr', {}, [
          el('td', { text: type }),
          el('td', { text: name }),
          el('td', { text: allCount + ' 个文件' }),
          el('td', { text: String(year) }),
          el('td', { class: 'op-cell' }, [
            el('a', {
              href: `/api/archive/download?type=${encodeURIComponent(type)}&year=${year}`,
              class: 'btn btn-sm'
            }, ['下载']),
            el('button', {
              type: 'button', class: 'btn btn-sm btn-danger',
              onclick: () => deleteArchive(type, year, null)
            }, ['删除'])
          ])
        ]);
        tb.appendChild(tr);
      }
    });
  }

  async function deleteArchive(type, year, month) {
    const label = month
      ? `${type} ${year}-${String(month).padStart(2, '0')}`
      : `${type} ${year}（全年）`;
    if (!confirm(`确定删除归档「${label}」吗？\n该操作仅删除归档副本，不影响原始数据。`)) return;
    const payload = { type, year };
    if (month) payload.month = month;
    const r = await API('POST', '/api/archive/delete', payload);
    toast(r.msg, r.ok);
    if (r.ok) refreshList();
  }

  QM.register('archive', initArchive);
})();
