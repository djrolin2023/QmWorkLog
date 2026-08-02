(function () {
  function initManual() {
    var nav = document.querySelector('.about-nav');
    if (!nav) return;
    var links = Array.prototype.slice.call(nav.querySelectorAll('.settings-nav-item'));
    var sections = links.map(function (a) {
      return document.getElementById(a.getAttribute('href').slice(1));
    });
    function viewportH() { return window.innerHeight; }
    function setActive(id) {
      links.forEach(function (a) {
        a.classList.toggle('active', a.getAttribute('href') === '#' + id);
      });
    }
    links.forEach(function (a) {
      a.addEventListener('click', function (e) {
        var id = a.getAttribute('href').slice(1);
        var el = document.getElementById(id);
        if (!el) return;
        e.preventDefault();
        el.scrollIntoView({ behavior: 'smooth', block: 'start' });
        setActive(id);
        if (history.replaceState) history.replaceState(null, '', '#' + id);
      });
    });
    function onScroll() {
      var mid = viewportH() * 0.35;
      var current = sections[0];
      for (var i = 0; i < sections.length; i++) {
        var s = sections[i];
        if (!s) continue;
        var relTop = s.getBoundingClientRect().top;
        if (relTop <= mid) current = s;
      }
      if (current) setActive(current.id);
    }
    window.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('resize', onScroll);
    onScroll();
  }

  if (window.QM && QM.register) {
    QM.register('manual', initManual);
  } else {
    window.addEventListener('DOMContentLoaded', initManual);
  }
})();
