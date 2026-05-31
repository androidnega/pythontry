/* AhantaPulse front-end glue:
   - theme toggle (light/dark) with localStorage persistence
   - mobile drawer
   - footer newsletter signup
   - simple carousel (scroll-snap + dots + arrows)
*/
(function () {
  // ---------- Theme ----------
  function applyTheme(t) {
    document.documentElement.setAttribute('data-theme', t);
    document.querySelectorAll('[data-theme-icon]').forEach(function (el) {
      el.innerHTML = t === 'dark'
        ? '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2"/><path d="M12 20v2"/><path d="m4.93 4.93 1.41 1.41"/><path d="m17.66 17.66 1.41 1.41"/><path d="M2 12h2"/><path d="M20 12h2"/><path d="m4.93 19.07 1.41-1.41"/><path d="m17.66 6.34 1.41-1.41"/></svg>'
        : '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>';
    });
  }
  function readPref() {
    try { return localStorage.getItem('theme'); } catch (e) { return null; }
  }
  function savePref(v) {
    try { localStorage.setItem('theme', v); } catch (e) { /* private mode */ }
  }
  // Initial paint sync (also done inline in <head>, this is a safety net)
  applyTheme(document.documentElement.getAttribute('data-theme') || 'light');

  document.addEventListener('click', function (e) {
    var btn = e.target.closest && e.target.closest('[data-theme-toggle]');
    if (!btn) return;
    var cur = document.documentElement.getAttribute('data-theme') || 'light';
    var next = cur === 'dark' ? 'light' : 'dark';
    applyTheme(next);
    savePref(next);
  });

  // ---------- Mobile drawer ----------
  var navBtn = document.getElementById('mobile-nav-btn');
  var nav = document.getElementById('mobile-nav');
  if (navBtn && nav) {
    navBtn.addEventListener('click', function () {
      nav.classList.toggle('hidden');
      var open = !nav.classList.contains('hidden');
      navBtn.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
  }

  // ---------- Footer newsletter ----------
  var form = document.getElementById('footer-notify');
  if (form) {
    var msg = document.getElementById('footer-notify-msg');
    var endpoint = form.getAttribute('data-endpoint');
    form.addEventListener('submit', function (e) {
      e.preventDefault();
      var email = document.getElementById('footer-notify-email').value.trim();
      fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify({ email: email })
      }).then(function (r) {
        return r.json().then(function (j) { return { ok: r.ok, body: j }; });
      }).then(function (res) {
        if (!msg) return;
        msg.classList.remove('hidden');
        msg.style.color = '';
        if (res.ok && res.body.ok) {
          msg.textContent = res.body.message || "You're on the list.";
          msg.style.color = 'var(--success-text)';
          form.reset();
        } else {
          msg.textContent = (res.body && res.body.error) || 'Something went wrong.';
          msg.style.color = 'var(--danger-text)';
        }
      }).catch(function () {
        if (!msg) return;
        msg.classList.remove('hidden');
        msg.textContent = 'Network error. Try again.';
        msg.style.color = 'var(--danger-text)';
      });
    });
  }

  // ---------- Carousel ----------
  function initCarousel(root) {
    var track = root.querySelector('.carousel');
    var dotsBox = root.querySelector('[data-carousel-dots]');
    var prev = root.querySelector('[data-carousel-prev]');
    var next = root.querySelector('[data-carousel-next]');
    if (!track) return;
    var items = track.querySelectorAll('.carousel-item');
    if (items.length <= 1) {
      if (prev) prev.style.display = 'none';
      if (next) next.style.display = 'none';
      if (dotsBox) dotsBox.style.display = 'none';
      return;
    }

    // Build dots
    if (dotsBox) {
      dotsBox.innerHTML = '';
      items.forEach(function (_, i) {
        var d = document.createElement('button');
        d.type = 'button';
        d.className = 'carousel-dot';
        d.setAttribute('aria-label', 'Go to slide ' + (i + 1));
        d.addEventListener('click', function () {
          items[i].scrollIntoView({ behavior: 'smooth', inline: 'start', block: 'nearest' });
        });
        dotsBox.appendChild(d);
      });
    }

    function update() {
      var rect = track.getBoundingClientRect();
      var midX = rect.left + rect.width / 2;
      var bestIdx = 0; var bestDist = Infinity;
      items.forEach(function (it, i) {
        var r = it.getBoundingClientRect();
        var c = r.left + r.width / 2;
        var dist = Math.abs(c - midX);
        if (dist < bestDist) { bestDist = dist; bestIdx = i; }
      });
      if (dotsBox) {
        dotsBox.querySelectorAll('.carousel-dot').forEach(function (d, i) {
          d.classList.toggle('active', i === bestIdx);
        });
      }
    }

    track.addEventListener('scroll', function () {
      window.requestAnimationFrame(update);
    }, { passive: true });
    window.addEventListener('resize', update);
    update();

    function step(dir) {
      var w = items[0].getBoundingClientRect().width + 16; // gap
      track.scrollBy({ left: dir * w, behavior: 'smooth' });
    }
    if (prev) prev.addEventListener('click', function () { step(-1); });
    if (next) next.addEventListener('click', function () { step(1); });
  }
  document.querySelectorAll('[data-carousel]').forEach(initCarousel);
})();
