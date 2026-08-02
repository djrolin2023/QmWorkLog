// 数据大屏页面逻辑：索引同步已移至后端（打开大屏时自动执行），前端无需手动触发
window.Dashboard = (function () {
  function el(id) { return document.getElementById(id); }

  return { el: el };
})();
