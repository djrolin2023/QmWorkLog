// 系统设置页面模块（逻辑与原单文件版本保持一致）
(function () {
  'use strict';
  const { $, $$, el, API, toast, openModal, closeModal } = window.QM;
  const QM = window.QM;

  async function initSettings() {
    $$('.settings-nav .nav-btn').forEach(b => b.addEventListener('click', () => {
      $$('.settings-nav .nav-btn').forEach(x => x.classList.remove('active'));
      $$('.settings-body .panel').forEach(p => p.classList.remove('active'));
      b.classList.add('active');
      const p = $('#' + b.dataset.panel); if (p) p.classList.add('active');
    }));

    const res = await API('GET', '/api/config');
    const c = res.config || {};
    if ($('#coTitle')) $('#coTitle').value = c.system_title || '';
    $('#coShort').value = c.company_short_name || '';
    $('#coCust').value = c.customer_name || '';
    window.__COMPANY_FULL__ = (c.company_short_name || '') + (c.customer_name ? '（' + c.customer_name + '）' : '');
    if (c.company_logo) $('#logoPreview').innerHTML = '<img src="' + c.company_logo + '">';

    $('#companyForm').addEventListener('submit', async e => {
      e.preventDefault();
      const fd = new FormData($('#companyForm'));
      const r = await API('POST', '/api/config', fd, true);
      $('#companyMsg').textContent = r.msg || '';
      if (r.ok) { toast('设置已保存', true); location.reload(); }
    });

    $('#pwdFormInline').addEventListener('submit', async e => {
      e.preventDefault();
      const f = new FormData($('#pwdFormInline'));
      if (f.get('new') !== f.get('confirm')) { $('#pwdMsgInline').textContent = '两次密码不一致'; return; }
      const r = await API('POST', '/api/account/password', { old: f.get('old'), new: f.get('new') });
      $('#pwdMsgInline').textContent = r.msg || '';
      if (r.ok) { toast('密码已修改', true); $('#pwdFormInline').reset(); }
    });

    initAiPanel();
  }

  // AI 配置面板：拉取模型、保存、中文模型介绍
  const MODEL_DESCS = {
    'Qwen/Qwen3-8B-Instruct': '阿里通义千问 Qwen3-8B：开源免费模型，中文能力优秀，适合日常台账总结，速度快、成本低。',
    'Qwen/Qwen2.5-7B-Instruct': '阿里通义千问 2.5-7B：稳定可靠的中文对话模型，适合通用总结。',
    'deepseek-ai/DeepSeek-V3': '深度求索 DeepSeek-V3：强推理大模型，适合复杂分析与长文本总结。',
    'deepseek-ai/DeepSeek-R1': '深度求索 DeepSeek-R1：推理增强模型，擅长分步思考与深度分析。',
    'THUDM/glm-4-9b-chat': '智谱 GLM-4-9B：中文表现均衡，适合总结与问答。',
    'meta-llama/Llama-3.3-70B-Instruct': 'Meta Llama-3.3-70B：英文强、中文良好，适合多语言场景。',
  };
  function modelDesc(id) {
    if (MODEL_DESCS[id]) return MODEL_DESCS[id];
    const s = (id || '').toLowerCase();
    if (s.includes('qwen')) return '通义千问系列模型，中文能力强，适合台账总结。';
    if (s.includes('deepseek')) return 'DeepSeek 系列模型，推理能力突出。';
    if (s.includes('glm')) return '智谱 GLM 系列，中文表现均衡。';
    return '该模型可用于生成总结，具体能力请参考平台说明。';
  }

  async function initAiPanel() {
    const r = await API('GET', '/api/ai/config');
    const ai = (r && r.ai) || {};
    if ($('#aiProvider')) $('#aiProvider').value = ai.provider || 'siliconflow';
    if ($('#aiBaseUrl')) $('#aiBaseUrl').value = ai.base_url || '';
    if ($('#aiKey')) $('#aiKey').value = ai.api_key || '';
    if (ai.model) { $('#aiModel').innerHTML = ''; addModelOpt(ai.model, true); $('#aiModel').value = ai.model; }
    showModelDesc($('#aiModel').value);

    const PROVIDER_URLS = {
      siliconflow: 'https://api.siliconflow.cn/v1',
      deepseek: 'https://api.deepseek.com/v1',
      openai: 'https://api.openai.com/v1',
    };
    $('#aiProvider').addEventListener('change', () => {
      const v = $('#aiProvider').value;
      if (PROVIDER_URLS[v]) $('#aiBaseUrl').value = PROVIDER_URLS[v];
    });
    $('#aiModel').addEventListener('change', () => showModelDesc($('#aiModel').value));

    $('#btnFetchModels').addEventListener('click', async () => {
      const btn = $('#btnFetchModels'); btn.disabled = true; btn.textContent = '拉取中…';
      const r2 = await API('GET', '/api/ai/models');
      btn.disabled = false; btn.textContent = '拉取模型';
      if (!r2 || !r2.ok) { toast((r2 && r2.msg) || '拉取失败', false); return; }
      const cur = $('#aiModel').value;
      $('#aiModel').innerHTML = '';
      (r2.models || []).forEach(m => addModelOpt(m.id, false));
      // 自动补全中文介绍
      r2.models.forEach(m => { MODEL_DESCS[m.id] = m.desc; });
      if (cur) $('#aiModel').value = cur;
      showModelDesc($('#aiModel').value);
      toast('已拉取 ' + (r2.models ? r2.models.length : 0) + ' 个可用模型', true);
    });

    $('#aiForm').addEventListener('submit', async e => {
      e.preventDefault();
      const body = {
        provider: $('#aiProvider').value,
        base_url: $('#aiBaseUrl').value.trim(),
        api_key: $('#aiKey').value.trim(),
        model: $('#aiModel').value,
      };
      const r3 = await API('POST', '/api/ai/config', body);
      $('#aiMsg').textContent = (r3 && r3.msg) || '';
      if (r3 && r3.ok) toast('AI 配置已保存', true);
      else toast((r3 && r3.msg) || '保存失败', false);
    });
  }

  function addModelOpt(id, selected) {
    if (!id) return;
    const o = document.createElement('option');
    o.value = id; o.textContent = id;
    if (selected) o.selected = true;
    $('#aiModel').appendChild(o);
  }
  function showModelDesc(id) {
    const box = $('#aiModelDesc');
    if (box) box.textContent = id ? modelDesc(id) : '';
  }

  QM.register('settings', initSettings);
})();
