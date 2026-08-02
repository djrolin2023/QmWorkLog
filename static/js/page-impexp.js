// 导入导出页面模块（逻辑与原单文件版本保持一致）
(function () {
  'use strict';
  const { $, el, API, toast } = window.QM;
  const QM = window.QM;

  async function initImpexp() {
    await window.QM.loadTypes();
    await fillTypes('#expType');
    await fillTypes('#impType');
    $('#btnExportZip').addEventListener('click', () => {
      location.href = `/api/export?type=${$('#expType').value}&year=${$('#expYear').value}&kind=zip`;
    });
    $('#btnExportYear').addEventListener('click', () => {
      location.href = `/api/export?type=${$('#expType').value}&year=${$('#expYear').value}&kind=year`;
    });
    $('#btnBackup').addEventListener('click', () => { location.href = '/api/backup/download'; });
    $('#btnOpenImport').addEventListener('click', openImportModal);
    $('#btnCloseImport').addEventListener('click', closeImportModal);
    $('#btnCancelImport').addEventListener('click', closeImportModal);
    $('#impFile').addEventListener('change', onFilePick);
    $('#btnStartImport').addEventListener('click', startImport);
    $('#btnAddType').addEventListener('click', async () => {
      const add = await API('POST', '/api/types', { name: '安保' });
      if (add && add.ok) {
        await fillTypes('#impType');
        $('#impType').value = '安保';
        $('#impTypeHint').hidden = true;
        toast('已新增台账类型「安保」', true);
      } else {
        toast('新增失败：' + (add && add.msg ? add.msg : '未知错误'), false);
      }
    });
  }

  function openImportModal() {
    fillTypes('#impType');
    $('#impFile').value = '';
    renderFileList([]);
    $('#impResult').hidden = true;
    $('#impResult').innerHTML = '';
    $('#impProgressWrap').hidden = true;
    $('#impProgressFill').style.width = '0%';
    $('#impProgressText').textContent = '0%';
    $('#btnStartImport').disabled = true;
    QM.openModal('importModal');
  }

  function closeImportModal() {
    QM.closeModal('importModal');
  }

  function renderFileList(files) {
    const box = $('#impFileList');
    box.innerHTML = '';
    files.forEach((f, i) => {
      const row = el('div', { class: 'imp-file-row' }, [
        el('span', { class: 'imp-file-name' }, [f.name]),
        el('span', { class: 'imp-file-status', id: 'fstat-' + i }, ['待上传'])
      ]);
      box.appendChild(row);
    });
    $('#btnStartImport').disabled = files.length === 0;
  }

  function onFilePick() {
    renderFileList(Array.from($('#impFile').files));
  }

  async function startImport() {
    const files = Array.from($('#impFile').files);
    if (!files.length) { toast('请先选择文件', false); return; }
    let dtype = $('#impType').value || '';
    // 若未选类型，尝试从首个文件名自动识别部门（安保/消控）并新建类型
    if (!dtype) {
      const first = files[0] ? files[0].name : '';
      const m = /(安保|消控)/.exec(first);
      if (m) {
        dtype = m[1];
        const add = await API('POST', '/api/types', { name: dtype });
        if (add && add.ok) {
          await fillTypes('#impType');
          $('#impType').value = dtype;
          $('#impTypeHint').hidden = true;
        } else {
          toast('自动新建类型失败：' + (add && add.msg ? add.msg : '未知错误'), false);
          return;
        }
      } else {
        toast('无法从文件名识别类型，请手动选择目标类型', false);
        return;
      }
    }
    $('#btnStartImport').disabled = true;
    $('#impFile').disabled = true;
    $('#impType').disabled = true;
    $('#impProgressWrap').hidden = false;
    $('#impResult').hidden = false;
    $('#impResult').innerHTML = '';

    let done = 0, okN = 0, dupN = 0, failN = 0;
    const total = files.length;
    for (let i = 0; i < total; i++) {
      const f = files[i];
      const statEl = $('#fstat-' + i);
      statEl.textContent = '上传中…';
      statEl.className = 'imp-file-status uploading';
      const fd = new FormData();
      fd.append('file', f);
      fd.append('type', dtype);
      let res;
      try {
        res = await API('POST', '/api/import', fd, true);
      } catch (e) {
        res = { ok: false, results: [{ file: f.name, ok: false, msg: '网络错误', dup: false }] };
      }
      const item = (res.results && res.results[0]) || { file: f.name, ok: false, msg: '无返回', dup: false };
      done++;
      if (item.ok) {
        if (item.dup) { dupN++; statEl.textContent = '覆盖'; }
        else { okN++; statEl.textContent = '成功'; }
        statEl.className = 'imp-file-status ' + (item.dup ? 'dup' : 'ok');
      } else {
        failN++;
        statEl.textContent = '失败';
        statEl.className = 'imp-file-status fail';
      }
      const pct = Math.round(done / total * 100);
      $('#impProgressFill').style.width = pct + '%';
      $('#impProgressText').textContent = pct + '%';
      appendResultLine(item);
    }
    appendSummary(total, okN, dupN, failN);
    $('#impFile').disabled = false;
    $('#impType').disabled = false;
  }

  function appendResultLine(item) {
    const box = $('#impResult');
    const icon = item.ok ? (item.dup ? '↻' : '✔') : '✘';
    const div = el('div', { class: 'imp-result-line ' + (item.ok ? (item.dup ? 'dup' : 'ok') : 'fail') },
      [`${icon} ${item.file}：${item.msg}`]);
    box.appendChild(div);
  }

  function appendSummary(total, okN, dupN, failN) {
    const box = $('#impResult');
    const div = el('div', { class: 'imp-result-summary' }, [
      `导入完成：共 ${total} 个文件，新增成功 ${okN} 条，重复覆盖 ${dupN} 条，失败 ${failN} 条`
    ]);
    box.appendChild(div);
    toast(`导入完成 成功${okN}/覆盖${dupN}/失败${failN}`, failN === 0);
  }

  async function fillTypes(selId) {
    const sel = $(selId);
    if (!sel) return;
    const r = await API('GET', '/api/types');
    sel.innerHTML = '';
    (r.types || []).forEach(t => {
      const o = el('option', { value: t.name }, [t.name]);
      sel.appendChild(o);
    });
    if (selId === '#expType') {
      const all = el('option', { value: '全部' }, ['全部']);
      sel.insertBefore(all, sel.firstChild);
    }
    // 导入类型为空时显示引导提示
    if (selId === '#impType') {
      const hint = $('#impTypeHint');
      if (hint) hint.hidden = (r.types || []).length > 0;
    }
  }

  QM.register('impexp', initImpexp);
})();
