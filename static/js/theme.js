// 乾明工作台账系统 - 主题切换（浅色/深色），深色模式持久化到 localStorage
(function () {
  'use strict';

  function getTheme() {
    try {
      var t = localStorage.getItem('theme');
      return (t === 'dark' || t === 'light') ? t : 'light';
    } catch (e) { return 'light'; }
  }

  function applyTheme(t) {
    document.documentElement.setAttribute('data-theme', t);
    // 更新所有切换按钮的文字（表示"点击后切换到的模式"）
    var btns = document.querySelectorAll('[data-theme-toggle]');
    btns.forEach(function (btn) {
      var label = btn.querySelector('.theme-label');
      if (label) label.textContent = (t === 'dark') ? '浅色模式' : '深色模式';
    });
  }

  window.Theme = {
    init: function () { applyTheme(getTheme()); },
    toggle: function () {
      var next = getTheme() === 'dark' ? 'light' : 'dark';
      try { localStorage.setItem('theme', next); } catch (e) {}
      applyTheme(next);
    }
  };

  // 供 head 内联脚本提前调用，避免页面闪烁
  window.__themeApply = applyTheme;
  window.__themeGet = getTheme;

  // 自动同步切换按钮文字（兼容 head 内加载与 body 末尾加载两种情况）
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () { window.Theme.init(); });
  } else {
    window.Theme.init();
  }
})();
