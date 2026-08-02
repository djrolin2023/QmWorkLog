// 智能总结页面模块（复选框多选 + 本地/免费AI/AI 三种生成）
(function () {
  'use strict';
  const { $, el, API, toast } = window.QM;
  let lastParams = { type: '全部', year: new Date().getFullYear(), period: 'year' };

  async function loadCheckTypes() {
    const r = await API('GET', '/api/types');
    const box = $('#sumTypes');
    box.innerHTML = '';
    (r.types || []).forEach(t => {
      const lab = el('label', { class: 'chk-item' }, []);
      const cb = document.createElement('input');
      cb.type = 'checkbox'; cb.value = t.name; cb.checked = true;
      lab.appendChild(cb);
      lab.appendChild(document.createTextNode(' ' + t.name));
      box.appendChild(lab);
    });
  }

  function selectedTypes() {
    const cbs = document.querySelectorAll('#sumTypes input[type=checkbox]');
    const arr = [];
    cbs.forEach(c => { if (c.checked) arr.push(c.value); });
    return arr;
  }

  function typeParam() {
    const ts = selectedTypes();
    if (ts.length === 0) return null;
    return ts.length === 1 ? ts[0] : ts.join(',');
  }

  function currentParams() {
    const year = Number($('#sumYear').value) || new Date().getFullYear();
    const period = $('#sumPeriod').value;
    const tp = typeParam();
    if (!tp) return null;
    const p = { type: tp, year, period };
    if (period === 'range') {
      p.start = $('#sumStart').value; p.end = $('#sumEnd').value;
      if (!p.start || !p.end) { toast('请选择开始和结束日期', false); return null; }
    }
    return p;
  }

  async function initSummary() {
    await loadCheckTypes();
    const y = new Date().getFullYear();
    const yearInput = $('#sumYear');
    if (yearInput && !yearInput.value) yearInput.value = y;

    $('#sumPeriod').addEventListener('change', function () {
      $('#sumRangeWrap').style.display = this.value === 'range' ? 'inline-flex' : 'none';
    });

    $('#btnSumGen').addEventListener('click', () => doGenerate('/api/summary', 'local'));
    $('#btnSumAI').addEventListener('click', () => doGenerate('/api/summary/ai', 'ai'));

    const exp = $('#btnSumExport');
    if (exp) exp.addEventListener('click', exportWord);

    // 首次进入自动生成一次
    doGenerate('/api/summary', 'local');
  }

  async function doGenerate(url, kind) {
    const p = currentParams();
    if (!p) return;
    lastParams = p;
    const card = $('#sumResultCard');
    const body = $('#sumBody');
    card.style.display = 'block';
    body.innerHTML = '<div class="loading">生成中…</div>';

    let r;
    if (kind === 'ai') {
      r = await API('POST', url, p);
    } else {
      r = await API('GET', url + '?' + new URLSearchParams(p).toString());
    }
    if (!r || !r.ok) {
      body.innerHTML = '<div class="err">' + ((r && r.msg) || '生成失败') + '</div>';
      return;
    }
    $('#sumTitle').textContent = (r.label || '智能总结') + (kind === 'ai' ? '（AI）' : kind === 'free' ? '（免费AI）' : '');
    const stats = $('#sumStats');
    stats.innerHTML = '';
    if (r.empty) {
      stats.innerHTML = '<span class="stat-empty">（暂无数据）</span>';
    } else {
      const items = [
        ['录入台账', r.record_count + ' 份'],
        ['覆盖天数', r.days + ' 天'],
        ['记录事项', r.item_count + ' 项'],
      ];
      if (r.keywords && r.keywords.length) items.push(['高频关键词', r.keywords.join('、')]);
      items.forEach(([k, v]) => {
        stats.appendChild(el('div', { class: 'stat-item' }, [
          el('span', { class: 'stat-k' }, [k]),
          el('span', { class: 'stat-v' }, [String(v)]),
        ]));
      });
    }
    body.innerHTML = '<p>' + (r.narrative || '（暂无内容）') + '</p>';
  }

  async function exportWord() {
    const qs = new URLSearchParams(lastParams).toString();
    try {
      const resp = await fetch('/api/summary/export?' + qs, { credentials: 'include' });
      if (!resp.ok) {
        let msg = '导出失败';
        try { const j = await resp.json(); msg = j.msg || msg; } catch (e) {}
        toast(msg, false);
        return;
      }
      const blob = await resp.blob();
      const cd = resp.headers.get('Content-Disposition') || '';
      const mstar = cd.match(/filename\*=(?:UTF-8'')?([^;]+)/i);
      const mascii = cd.match(/filename="?([^";]+)"?/i);
      let fname = '智能总结.docx';
      if (mstar) fname = decodeURIComponent(mstar[1].trim().replace(/^["]|["]$/g, ''));
      else if (mascii) fname = mascii[1].trim().replace(/^["]|["]$/g, '');
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = fname;
      document.body.appendChild(a); a.click();
      document.body.removeChild(a); URL.revokeObjectURL(url);
      toast('已导出 Word', true);
    } catch (e) {
      toast('导出失败：' + e.message, false);
    }
  }

  window.QM.register('summary', initSummary);
})();
