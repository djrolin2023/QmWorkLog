// 工作台账页面模块
(function () {
  'use strict';
  const { $, $$, el, API, toast, state, openModal, closeModal, zoom } = window.QM;
  const QM = window.QM;

  function qsType() { return new URLSearchParams(location.search).get('type'); }

  async function latestMonthOf(type) {
    try {
      const r = await API('GET', `/api/months?type=${encodeURIComponent(type)}`);
      const ms = (r.months || []).filter(x => x.count > 0);
      if (ms.length) {
        const last = ms[ms.length - 1];
        return { year: last.year, month: last.month };
      }
    } catch (e) {}
    const n = new Date();
    return { year: n.getFullYear(), month: n.getMonth() + 1 };
  }

  // 进入/退出编辑态时：日历作为常驻悬浮面板始终可见，不再隐藏
  function setEditMode(on) {
    // 悬浮日历始终保留，无需隐藏
  }

  async function initLedger() {
    // 确保类型已加载，避免 state.types 为空导致日历/部门异常
    if (!state.types || !state.types.length) { await QM.loadTypes(); }

    const cfg = await API('GET', '/api/config');
    const c = cfg.config || {};
    window.__COMPANY_FULL__ = (c.company_short_name || '') + (c.customer_name ? '（' + c.customer_name + '）' : '');
    const t = qsType();
    state.type = t || (state.types[0] && state.types[0].name) || '安保';
    const lm = await latestMonthOf(state.type);
    state.year = lm.year; state.month = lm.month;
    state.editLoaded = ''; // 已加载/保存的内容快照，用于判断未保存改动
    state.editActive = false;
    state.isNew = false; // 当前是否为"未创建台账"状态
    state.selected = new Set(); // 批量删除已选日期集合
    state.view = 'cal'; // 'cal'=日历(当月天数) | 'month'=月历(年份12月)
    state.selectedMonths = new Set(); // 月历视图已选月份集合，元素形如 'YYYY-MM'
    state.stats = { hasAny: false, yearHas: false }; // 类型是否有台账 / 当前年份是否有台账
    state.monthHas = false; // 当前月份是否有台账

    const typeSel = $('#typeSelect');
    typeSel.value = state.type;

    typeSel.addEventListener('change', async () => {
      // 切换类型时日历保持当前显示的年月（悬浮/保留），仅刷新当月的台账标记
      state.type = typeSel.value;
      state.selected.clear(); state.selectedMonths.clear();
      await refreshStats();
      if (state.view === 'month') renderMonthView(); else { renderCalendar(); }
    });
    $('#prevMonth').addEventListener('click', () => navMonth(-1));
    $('#nextMonth').addEventListener('click', () => navMonth(1));
    $('#todayBtn').addEventListener('click', () => {
      const n = new Date(); state.year = n.getFullYear(); state.month = n.getMonth() + 1;
      if (state.view === 'month') renderMonthView(); else renderCalendar();
      refreshStats();
    });
    $('#btnCreateNew').addEventListener('click', () => openEdit('', true));
    $('#btnEdit').addEventListener('click', () => openEdit(state.content || '', false, (function(){ const s=$('#tdSign'); return s?s.textContent:''; })()));
    $('#btnCancelEdit').addEventListener('click', () => {
      $('#editPanel').style.display = 'none';
      if (state.isNew) { showNewPlaceholder(); }
      else { $('#recordPanel').style.display = 'block'; setEditMode(false); state.editActive = false; }
    });
    $('#btnSaveEdit').addEventListener('click', saveEdit);
    $('#btnOpen').addEventListener('click', () => {
      // 打开本地对应的 .docx 文档（web 端触发下载，文件名保持原 docx 名）
      location.href = `/api/record/download?type=${encodeURIComponent(state.type)}&date=${encodeURIComponent(state.date)}`;
    });
    $('#btnDelete').addEventListener('click', deleteRecord);
    $('#btnBatchDelete').addEventListener('click', batchDelete);
    $('#btnDeleteMonth').addEventListener('click', deleteMonth);
    $('#btnDeleteType').addEventListener('click', deleteType);
    $('#viewCal').addEventListener('click', () => switchView('cal'));
    $('#viewMonth').addEventListener('click', () => switchView('month'));
    $('#btnDeleteMonths').addEventListener('click', deleteMonths);
    $('#btnDeleteYearAll').addEventListener('click', deleteYearAll);
    // 返回按钮：未保存则弹提醒，否则直接回日历
    $('#btnBackEdit').addEventListener('click', onBackEdit);

    // 未保存提醒三按钮
    $('#btnUnsavedConfirm').addEventListener('click', async () => {
      closeModal('unsavedModal');
      await saveEdit();
      exitEdit();
    });
    $('#btnUnsavedCancel').addEventListener('click', () => closeModal('unsavedModal'));
    $('#btnUnsavedExit').addEventListener('click', () => {
      closeModal('unsavedModal');
      exitEdit();
    });

    setEditMode(false);
    renderCalendar();
    refreshStats();
  }

  function navMonth(delta) {
    if (state.view === 'month') {
      // 月历视图：上一个/下一个年份
      state.year += delta;
      renderMonthView();
      refreshStats();
    } else {
      let y = state.year, m = state.month + delta;
      if (m < 1) { m = 12; y--; }
      else if (m > 12) { m = 1; y++; }
      state.year = y; state.month = m;
      renderCalendar();
      refreshStats();
    }
  }

  let calGen = 0;
  async function renderCalendar() {
    const cal = $('#calendar');
    if (!cal) return;
    const myGen = ++calGen;
    const y = state.year, m = state.month;
    const label = $('#calLabel');
    if (label) label.textContent = `${y}年${String(m).padStart(2, '0')}月`;
    const WK = ['日', '一', '二', '三', '四', '五', '六'];
    const first = new Date(y, m - 1, 1).getDay();
    const days = new Date(y, m, 0).getDate();
    const res = await API('GET', `/api/records?type=${state.type}&year=${y}&month=${m}`);
    if (myGen !== calGen) return;
    const have = new Set((res.days || []).map(d => d.day));
    state.monthHas = have.size > 0;
    cal.innerHTML = '';
    WK.forEach(w => cal.appendChild(el('div', { class: 'cal-h' }, [w])));
    for (let i = 0; i < first; i++) cal.appendChild(el('div', { class: 'cal-empty' }));
    for (let d = 1; d <= days; d++) {
      const has = have.has(d);
      const dateStr = `${y}-${String(m).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
      const cell = el('div', { class: 'cal-day' + (has ? ' has' : '') + (state.selected.has(dateStr) ? ' sel' : ''), 'data-day': d, 'data-date': dateStr }, [String(d)]);
      cell.addEventListener('click', (e) => selectDay(d, e, has));
      cal.appendChild(cell);
    }
    syncBatchBtn();
    syncButtons();
  }

  function syncBatchBtn() {
    const n = state.selected.size;
    const cnt = $('#selCount');
    if (cnt) cnt.textContent = n;
    const btn = $('#btnBatchDelete');
    if (btn) {
      btn.style.display = n === 0 ? 'none' : '';
      btn.disabled = n === 0;
    }
  }

  function switchView(v) {
    state.view = v;
    const isMonth = v === 'month';
    $('#calendar').style.display = isMonth ? 'none' : '';
    $('#monthView').style.display = isMonth ? '' : 'none';
    $('#calTip').style.display = isMonth ? 'none' : '';
    $('#monthActions').style.display = isMonth ? '' : 'none';
    $('#viewCal').classList.toggle('active', !isMonth);
    $('#viewMonth').classList.toggle('active', isMonth);
    $('#btnBatchDelete').style.display = 'none';
    if (isMonth) renderMonthView();
    else renderCalendar();
    syncButtons();
  }

  async function renderMonthView() {
    const box = $('#monthView');
    if (!box) return;
    const y = state.year;
    const label = $('#calLabel');
    if (label) label.textContent = `${y}年（月历：可多选月份）`;
    // 拉取该年各月台账数量
    const res = await API('GET', `/api/months?type=${encodeURIComponent(state.type)}&year=${y}`);
    const monthCounts = {};
    (res.months || []).forEach(mv => { monthCounts[`${mv.year}-${String(mv.month).padStart(2, '0')}`] = mv.count; });
    box.innerHTML = '';
    const grid = el('div', { class: 'month-grid' });
    for (let m = 1; m <= 12; m++) {
      const key = `${y}-${String(m).padStart(2, '0')}`;
      const cnt = monthCounts[key] || 0;
      const has = cnt > 0;
      const cell = el('div', { class: 'month-cell' + (has ? ' has' : '') + (state.selectedMonths.has(key) ? ' sel' : ''), 'data-month': key }, [
        el('div', { class: 'mc-name' }, [`${m}月`]),
        el('div', { class: 'mc-count' }, [has ? `${cnt} 条` : '无'])
      ]);
      cell.addEventListener('click', (e) => selectMonth(key, e, has, cell));
      grid.appendChild(cell);
    }
    box.appendChild(grid);
    syncMonthBtn();
  }

  function selectMonth(key, ev, has, cell) {
    if (!(ev && ev.ctrlKey)) {
      // 普通点击：进入该月日历视图便于查看
      const [, mm] = key.split('-');
      state.month = Number(mm);
      switchView('cal');
      return;
    }
    if (!has) { toast('该月无台账，无法选择', false); return; }
    const on = !state.selectedMonths.has(key);
    if (on) state.selectedMonths.add(key); else state.selectedMonths.delete(key);
    cell.classList.toggle('sel', on);
    syncMonthBtn();
  }

  function syncMonthBtn() {
    const n = state.selectedMonths.size;
    const cnt = $('#selMonthCount');
    if (cnt) cnt.textContent = n;
    const btn = $('#btnDeleteMonths');
    if (btn) btn.style.display = n === 0 ? 'none' : '';
  }

  // 拉取类型台账统计，用于决定哪些删除按钮可见
  async function refreshStats() {
    try {
      const res = await API('GET', `/api/months?type=${encodeURIComponent(state.type)}`);
      let hasAny = false, yearHas = false;
      (res.months || []).forEach(mv => {
        if (mv.count > 0) {
          hasAny = true;
          if (Number(mv.year) === state.year) yearHas = true;
        }
      });
      state.stats.hasAny = hasAny;
      state.stats.yearHas = yearHas;
    } catch (e) { state.stats = { hasAny: false, yearHas: false }; }
    syncButtons();
  }

  function syncButtons() {
    // 删除当月：仅日历视图且当前月有台账时显示
    const dm = $('#btnDeleteMonth');
    if (dm) dm.style.display = (state.view === 'cal' && state.monthHas) ? '' : 'none';
    // 删除整类型：仅当该类型存在任意年份台账时显示
    const dt = $('#btnDeleteType');
    if (dt) dt.style.display = state.stats.hasAny ? '' : 'none';
    // 删除整年（月历视图内）：仅当年份有台账时显示
    const dya = $('#btnDeleteYearAll');
    if (dya) dya.style.display = (state.view === 'month' && state.stats.yearHas) ? '' : 'none';
  }

  async function deleteMonths() {
    const months = Array.from(state.selectedMonths);
    if (months.length === 0) return;
    QM.confirm(`确定删除选中的 ${months.length} 个月份台账（${months.join('、')}）？此操作不可恢复。`, async () => {
      const res = await API('POST', '/api/records/delete-all', { type: state.type, mode: 'months', months });
      toast(res.msg, res.ok);
      if (res.ok) { state.selectedMonths.clear(); syncMonthBtn(); await renderMonthView(); await refreshStats(); }
    }, '批量删除月份');
  }

  async function deleteYearAll() {
    QM.confirm(`确定删除「${state.type}」${state.year}年 全部12个月台账？此操作不可恢复。`, async () => {
      const months = [];
      for (let m = 1; m <= 12; m++) months.push(`${state.year}-${String(m).padStart(2, '0')}`);
      const res = await API('POST', '/api/records/delete-all', { type: state.type, mode: 'months', months });
      toast(res.msg, res.ok);
      if (res.ok) { state.selectedMonths.clear(); syncMonthBtn(); await renderMonthView(); await refreshStats(); }
    }, '删除整年');
  }

  function toggleSelect(dateStr, on) {
    if (on) state.selected.add(dateStr);
    else state.selected.delete(dateStr);
    syncBatchBtn();
  }

  async function batchDelete() {
    const dates = Array.from(state.selected);
    if (dates.length === 0) return;
    QM.confirm(`确定批量删除选中的 ${dates.length} 条台账？此操作不可恢复。`, () => doBatchDelete(dates), '批量删除');
  }

  async function doBatchDelete(dates) {
    const res = await API('POST', '/api/records/delete', { type: state.type, dates });
    toast(res.msg, res.ok);
    if (res.ok) {
      state.selected.clear();
      const cnt = $('#selCount');
      if (cnt) cnt.textContent = '0';
      $('#btnBatchDelete').disabled = true;
      renderCalendar();
      await refreshStats();
    }
  }

  async function deleteMonth() {
    const m = `${state.year}-${String(state.month).padStart(2, '0')}`;
    QM.confirm(`确定删除「${state.type}」${m} 当月全部台账？此操作不可恢复。`, async () => {
      const res = await API('POST', '/api/records/delete-all', { type: state.type, mode: 'month', month: m });
      toast(res.msg, res.ok);
      if (res.ok) { state.selected.clear(); syncBatchBtn(); renderCalendar(); await refreshStats(); }
    }, '删除当月');
  }

  async function deleteType() {
    QM.confirm(`确定删除「${state.type}」全部年份台账？此操作不可恢复。`, async () => {
      const res = await API('POST', '/api/records/delete-all', { type: state.type, mode: 'all' });
      toast(res.msg, res.ok);
      if (res.ok) { state.selected.clear(); syncBatchBtn(); renderCalendar(); await refreshStats(); }
    }, '删除整类型');
  }

  function togglePlaceholder() {
    const ph = $('#detailPlaceholder');
    const np = $('#newPlaceholder');
    const showing = ($('#recordPanel').style.display !== 'none') || ($('#editPanel').style.display !== 'none');
    if (ph) ph.style.display = showing ? 'none' : 'flex';
    if (np) np.style.display = showing ? 'none' : 'flex';
  }

  // 显示"未创建台账"新建引导，隐藏其他面板
  function showNewPlaceholder() {
    document.body.classList.remove('edit-fullscreen');
    $('#recordPanel').style.display = 'none';
    $('#editPanel').style.display = 'none';
    $('#detailPlaceholder').style.display = 'none';
    $('#newPlaceholder').style.display = 'flex';
    setEditMode(false);
    state.editActive = false;
  }

  function selectDay(d, ev, has) {
    // 按住 Ctrl 键点击：批量选择（仅对有台账的日期生效）
    if (ev && ev.ctrlKey) {
      if (!has) { toast('该日期无台账，无法选择', false); return; }
      const dateStr = `${state.year}-${String(state.month).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
      const cell = ev.currentTarget;
      const on = !state.selected.has(dateStr);
      toggleSelect(dateStr, on);
      cell.classList.toggle('sel', on);
      return;
    }
    // 普通点击：查看/编辑当日台账
    state.day = d;
    state.date = `${state.year}-${String(state.month).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
    document.querySelectorAll('#calendar .cal-day').forEach(c => {
      c.classList.toggle('active', Number(c.getAttribute('data-day')) === d);
    });
    loadRecord();
  }

  // 渲染工作图片列表到指定容器（查看态/编辑态共用）
  function renderImages(boxId) {
    const box = $('#' + boxId);
    if (!box) return;
    const q = `type=${encodeURIComponent(state.type)}&date=${encodeURIComponent(state.date)}`;
    // 先探测图片数量
    API('GET', `/api/record?type=${state.type}&date=${encodeURIComponent(state.date)}`).then(res => {
      const n = (res.ok && res.record) ? (res.record.images || 0) : 0;
      box.innerHTML = '';
      if (n > 0) {
        for (let i = 0; i < n; i++) {
          const img = el('img', { src: `/api/record/image?${q}&i=${i}`, onclick: function () { QM.zoom(this.src); } });
          box.appendChild(img);
        }
      } else {
        box.innerHTML = '<span class="td-empty">（暂无图片）</span>';
      }
    });
  }

  // 模板照片框占位文字（与 demo.docx 一致）
  const FRAME_LABELS = ['第一张工作图', '第二张工作图', '第三张工作图', '第四张工作图'];

  // 编辑态：渲染 4 个照片框，每框独立上传按钮（与模板 2×2 布局一致）
  async function renderEditFrames() {
    const box = $('#editFrames');
    if (!box) return;
    const res = await API('GET', `/api/record?type=${state.type}&date=${encodeURIComponent(state.date)}`);
    const n = (res.ok && res.record) ? (res.record.images || 0) : 0;
    const total = Math.max(4, n);
    box.innerHTML = '';
    const q = `type=${encodeURIComponent(state.type)}&date=${encodeURIComponent(state.date)}`;
    for (let i = 0; i < total; i++) {
      const frame = el('div', { class: 'td-frame' });
      if (i < n) {
        frame.appendChild(el('img', { src: `/api/record/image?${q}&i=${i}`, onclick: function () { QM.zoom(this.src); } }));
      } else {
        frame.appendChild(el('div', { class: 'td-frame-placeholder' }, [FRAME_LABELS[i] || ('第' + (i + 1) + '张工作图')]));
      }
      const up = el('button', { class: 'td-frame-upload', type: 'button' }, [i < n ? '重新上传' : '上传图片']);
      up.addEventListener('click', () => uploadOneEdit(i));
      frame.appendChild(up);
      box.appendChild(frame);
    }
  }

  // 编辑态：向指定序号照片框单独上传一张图片
  async function uploadOneEdit(index) {
    const chk = await API('GET', `/api/record?type=${state.type}&date=${encodeURIComponent(state.date)}`);
    if (!chk.ok) {
      const ok = await saveEdit();
      if (!ok) { toast('请先保存台账后再上传图片', false); return; }
    }
    const inp = el('input', { type: 'file', accept: 'image/*' });
    inp.addEventListener('change', async () => {
      if (!inp.files.length) return;
      const fd = new FormData();
      fd.append('type', state.type);
      fd.append('date', state.date);
      fd.append('index', String(index));
      fd.append('images', inp.files[0]);
      const res = await API('POST', '/api/record/upload_images', fd, true);
      toast(res.msg, res.ok);
      if (res.ok) renderEditFrames();
    });
    inp.click();
  }

  async function loadRecord() {
    const res = await API('GET', `/api/record?type=${state.type}&date=${state.date}`);
    if (res.ok) {
      const r = res.record;
      state.content = r.content || '';
      state.editLoaded = r.content || '';
      $('#tdCompany').textContent = (window.__COMPANY_FULL__) || '';
      $('#tdDept').textContent = r.dept || '';
      $('#tdDate').textContent = r.date || state.date;
      $('#tdContent').textContent = r.content || '（暂无内容）';
      renderImages('tdImages');
      $('#tdSign').textContent = r.sign || '';
      $('#recordPanel').style.display = 'block';
      $('#editPanel').style.display = 'none';
      setEditMode(false);
      togglePlaceholder();
    } else {
      showNewPlaceholder();
    }
  }

  function editSnapshot() {
    return $('#editContent').value + '\u0000' + ($('#editSign').value || '');
  }

  function openEdit(content, isNew, sign) {
    // 确保日期有效：优先用已选日期，否则默认今天
    if (!state.date) {
      const t = new Date();
      state.day = t.getDate();
      state.date = `${t.getFullYear()}-${String(t.getMonth()+1).padStart(2,'0')}-${String(t.getDate()).padStart(2,'0')}`;
    }
    state.isNew = !!isNew;
    $('#editTitle').textContent = isNew ? '新建台账' : '编辑台账';
    $('#editCompany').textContent = (window.__COMPANY_FULL__) || '';
    $('#editDept').value = deptName(state.type);
    $('#editDate').value = state.date;
    $('#editContent').value = content || '';
    $('#editSign').value = sign || '';
    $('#recordPanel').style.display = 'none';
    $('#editPanel').style.display = 'block';
    $('#detailPlaceholder').style.display = 'none';
    $('#newPlaceholder').style.display = 'none';
    document.body.classList.add('edit-fullscreen');
    setEditMode(true);
    state.editActive = true;
    state.editLoaded = (isNew ? '' : (content || '')) + '\u0000' + (sign || '');
    renderEditFrames();
    togglePlaceholder();
  }

  function deptName(t) {
    if (t === '安保') return '安保部';
    if (t === '消控') return '安保部（消控）';
    return t + '部';
  }

  // 返回按钮：有未保存改动则弹提醒，否则直接退出
  function onBackEdit() {
    if (state.editActive && editSnapshot() !== state.editLoaded) {
      openModal('unsavedModal');
    } else {
      exitEdit();
    }
  }

  // 退出编辑，回到日历
  function exitEdit() {
    document.body.classList.remove('edit-fullscreen');
    $('#editPanel').style.display = 'none';
    $('#recordPanel').style.display = 'none';
    state.editActive = false;
    if (state.isNew) { showNewPlaceholder(); renderCalendar(); return; }
    setEditMode(false);
    renderCalendar();
    togglePlaceholder();
  }

  async function saveEdit() {
    const content = $('#editContent').value;
    const sign = $('#editSign').value;
    const res = await API('POST', '/api/record/save', { type: state.type, date: state.date, content, sign });
    if (res.ok) {
      toast(res.msg, true);
      state.content = content;
      state.editLoaded = content + '\u0000' + (sign || '');
      state.isNew = false;
      loadRecord();
    } else toast(res.msg, false);
    return res.ok;
  }

  async function deleteRecord() {
    if (!state.date) return;
    QM.confirm('确定删除 ' + state.date + ' 的台账？此操作不可恢复。', async () => {
      const res = await API('POST', '/api/record/delete', { type: state.type, date: state.date });
      toast(res.msg, res.ok);
      if (res.ok) { showNewPlaceholder(); renderCalendar(); }
    }, '删除台账');
  }

  QM.register('ledger', initLedger);
})();
