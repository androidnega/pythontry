// Portrait gallery + lightbox.
// Activated for any element with [data-gallery]. Reads JSON from a sibling
// <script type="application/json" data-gallery-views> with shape:
//   [{ src: "/static/...", label: "Main view" }, ...]
(function () {
  "use strict";

  function $(sel, root) { return (root || document).querySelector(sel); }
  function $$(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }

  function clamp(n, min, max) { return Math.min(max, Math.max(min, n)); }

  function createLightbox(views, startIndex, opts) {
    var idx = startIndex || 0;
    var scale = 1, tx = 0, ty = 0;
    var dragging = false, dragStartX = 0, dragStartY = 0, txStart = 0, tyStart = 0;
    var pinchStartDist = 0, pinchStartScale = 1;

    var backdrop = document.createElement("div");
    backdrop.className = "lightbox-backdrop no-save-zone";
    backdrop.setAttribute("role", "dialog");
    backdrop.setAttribute("aria-modal", "true");
    backdrop.innerHTML = [
      '<div class="lightbox-toolbar">',
      '  <span class="lb-title" data-lb-title></span>',
      '  <span class="lb-counter" data-lb-counter></span>',
      '  <button type="button" class="lightbox-btn" data-action="zoom-out" title="Zoom out (–)">',
      '    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><line x1="5" y1="12" x2="19" y2="12"/></svg>',
      '  </button>',
      '  <button type="button" class="lightbox-btn" data-action="zoom-reset" title="Reset (0)"><span data-lb-scale>100%</span></button>',
      '  <button type="button" class="lightbox-btn" data-action="zoom-in" title="Zoom in (+)">',
      '    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>',
      '  </button>',
      '  <button type="button" class="lightbox-btn" data-action="close" title="Close (Esc)" aria-label="Close">',
      '    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>',
      '  </button>',
      '</div>',
      '<div class="lightbox-stage" data-lb-stage>',
      '  <div class="lightbox-image-wrap" data-lb-wrap>',
      '    <img alt="" data-lb-img class="no-save" draggable="false" />',
      '  </div>',
      '  <button type="button" class="lightbox-side-btn lightbox-prev" data-action="prev" aria-label="Previous">',
      '    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 18 9 12 15 6"/></svg>',
      '  </button>',
      '  <button type="button" class="lightbox-side-btn lightbox-next" data-action="next" aria-label="Next">',
      '    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"/></svg>',
      '  </button>',
      '</div>',
      '<div class="lightbox-footer" data-lb-foot></div>'
    ].join("");

    document.body.appendChild(backdrop);
    document.body.classList.add("lightbox-open");
    requestAnimationFrame(function () { backdrop.classList.add("is-open"); });

    var img = $("[data-lb-img]", backdrop);
    var wrap = $("[data-lb-wrap]", backdrop);
    var stage = $("[data-lb-stage]", backdrop);
    var titleEl = $("[data-lb-title]", backdrop);
    var counterEl = $("[data-lb-counter]", backdrop);
    var scaleEl = $("[data-lb-scale]", backdrop);
    var footer = $("[data-lb-foot]", backdrop);
    var prevBtn = $('[data-action="prev"]', backdrop);
    var nextBtn = $('[data-action="next"]', backdrop);

    // Build footer strip
    views.forEach(function (v, i) {
      var t = document.createElement("button");
      t.type = "button";
      t.className = "lightbox-foot-thumb no-save-zone";
      t.dataset.idx = String(i);
      t.innerHTML = '<img alt="" class="no-save" draggable="false" src="' + v.src + '">';
      t.addEventListener("click", function () { go(i); });
      footer.appendChild(t);
    });

    // Apply best-effort save protection to dynamic content
    if (typeof window.protectMedia === "function") {
      window.protectMedia(backdrop);
    }

    function applyTransform() {
      wrap.style.transform = "translate(" + tx + "px, " + ty + "px)";
      img.style.transform = "scale(" + scale + ")";
      if (scaleEl) scaleEl.textContent = Math.round(scale * 100) + "%";
      wrap.classList.toggle("is-grabbable", scale > 1);
    }

    function resetTransform() {
      scale = 1; tx = 0; ty = 0;
      applyTransform();
    }

    function setView(i) {
      idx = ((i % views.length) + views.length) % views.length;
      var v = views[idx];
      img.src = v.src;
      img.alt = v.label || "";
      if (titleEl) titleEl.textContent = v.label || "";
      if (counterEl) counterEl.textContent = (idx + 1) + " / " + views.length;
      $$(".lightbox-foot-thumb", footer).forEach(function (t, ti) {
        t.classList.toggle("is-active", ti === idx);
      });
      var only = views.length <= 1;
      prevBtn.disabled = only;
      nextBtn.disabled = only;
      resetTransform();
    }

    function go(i) { setView(i); }
    function next() { setView(idx + 1); }
    function prev() { setView(idx - 1); }

    function zoom(factor, originX, originY) {
      var newScale = clamp(scale * factor, 1, 6);
      if (newScale === scale) return;
      // Keep zoom origin near the cursor: convert origin (relative to stage center) into translation adjustment.
      if (originX != null && originY != null) {
        var rect = stage.getBoundingClientRect();
        var cx = rect.left + rect.width / 2;
        var cy = rect.top + rect.height / 2;
        var dx = originX - cx;
        var dy = originY - cy;
        var ratio = newScale / scale - 1;
        tx -= dx * ratio;
        ty -= dy * ratio;
      }
      scale = newScale;
      if (scale === 1) { tx = 0; ty = 0; }
      applyTransform();
    }

    function close() {
      backdrop.classList.remove("is-open");
      setTimeout(function () {
        backdrop.remove();
        document.body.classList.remove("lightbox-open");
        document.removeEventListener("keydown", onKey);
        if (opts && typeof opts.onClose === "function") opts.onClose();
      }, 180);
    }

    function onKey(e) {
      if (e.key === "Escape") { e.preventDefault(); close(); }
      else if (e.key === "ArrowRight") { e.preventDefault(); next(); }
      else if (e.key === "ArrowLeft") { e.preventDefault(); prev(); }
      else if (e.key === "+" || e.key === "=") { e.preventDefault(); zoom(1.25); }
      else if (e.key === "-" || e.key === "_") { e.preventDefault(); zoom(1 / 1.25); }
      else if (e.key === "0") { e.preventDefault(); resetTransform(); }
    }
    document.addEventListener("keydown", onKey);

    backdrop.addEventListener("click", function (e) {
      var action = e.target.closest("[data-action]");
      if (action) {
        var a = action.dataset.action;
        if (a === "close") close();
        else if (a === "next") next();
        else if (a === "prev") prev();
        else if (a === "zoom-in") zoom(1.25);
        else if (a === "zoom-out") zoom(1 / 1.25);
        else if (a === "zoom-reset") resetTransform();
        return;
      }
      // Click on empty area closes
      if (e.target === backdrop || e.target === stage) close();
    });

    // Wheel to zoom
    stage.addEventListener("wheel", function (e) {
      e.preventDefault();
      var factor = e.deltaY < 0 ? 1.12 : 1 / 1.12;
      zoom(factor, e.clientX, e.clientY);
    }, { passive: false });

    // Double-click toggles 1x ↔ 2.5x
    img.addEventListener("dblclick", function (e) {
      e.preventDefault();
      if (scale > 1) resetTransform();
      else zoom(2.5, e.clientX, e.clientY);
    });

    // Mouse drag to pan when zoomed
    img.addEventListener("mousedown", function (e) {
      if (scale <= 1) return;
      e.preventDefault();
      dragging = true;
      dragStartX = e.clientX; dragStartY = e.clientY;
      txStart = tx; tyStart = ty;
      wrap.classList.add("is-dragging");
    });
    window.addEventListener("mousemove", function (e) {
      if (!dragging) return;
      tx = txStart + (e.clientX - dragStartX);
      ty = tyStart + (e.clientY - dragStartY);
      applyTransform();
    });
    window.addEventListener("mouseup", function () {
      if (!dragging) return;
      dragging = false;
      wrap.classList.remove("is-dragging");
    });

    // Touch: 1-finger pan (only when zoomed), 2-finger pinch
    var touchStartX = 0, touchStartY = 0, touchTxStart = 0, touchTyStart = 0;
    var lastTap = 0;

    function distance(t1, t2) {
      var dx = t1.clientX - t2.clientX;
      var dy = t1.clientY - t2.clientY;
      return Math.sqrt(dx * dx + dy * dy);
    }

    stage.addEventListener("touchstart", function (e) {
      if (e.touches.length === 1) {
        // Double-tap detection
        var now = Date.now();
        if (now - lastTap < 320) {
          if (scale > 1) resetTransform();
          else zoom(2.5, e.touches[0].clientX, e.touches[0].clientY);
          lastTap = 0;
          return;
        }
        lastTap = now;
        if (scale > 1) {
          touchStartX = e.touches[0].clientX;
          touchStartY = e.touches[0].clientY;
          touchTxStart = tx; touchTyStart = ty;
        }
      } else if (e.touches.length === 2) {
        pinchStartDist = distance(e.touches[0], e.touches[1]);
        pinchStartScale = scale;
      }
    }, { passive: true });

    stage.addEventListener("touchmove", function (e) {
      if (e.touches.length === 1 && scale > 1) {
        e.preventDefault();
        tx = touchTxStart + (e.touches[0].clientX - touchStartX);
        ty = touchTyStart + (e.touches[0].clientY - touchStartY);
        applyTransform();
      } else if (e.touches.length === 2 && pinchStartDist > 0) {
        e.preventDefault();
        var d = distance(e.touches[0], e.touches[1]);
        var newScale = clamp(pinchStartScale * (d / pinchStartDist), 1, 6);
        var midX = (e.touches[0].clientX + e.touches[1].clientX) / 2;
        var midY = (e.touches[0].clientY + e.touches[1].clientY) / 2;
        var rect = stage.getBoundingClientRect();
        var cx = rect.left + rect.width / 2;
        var cy = rect.top + rect.height / 2;
        var dx = midX - cx;
        var dy = midY - cy;
        var ratio = newScale / scale - 1;
        tx -= dx * ratio;
        ty -= dy * ratio;
        scale = newScale;
        if (scale === 1) { tx = 0; ty = 0; }
        applyTransform();
      }
    }, { passive: false });

    // Swipe horizontally between views when not zoomed
    var swipeStartX = 0, swipeStartY = 0, swipeTracking = false;
    stage.addEventListener("touchstart", function (e) {
      if (scale === 1 && e.touches.length === 1) {
        swipeTracking = true;
        swipeStartX = e.touches[0].clientX;
        swipeStartY = e.touches[0].clientY;
      } else {
        swipeTracking = false;
      }
    }, { passive: true });
    stage.addEventListener("touchend", function (e) {
      if (!swipeTracking) return;
      swipeTracking = false;
      var t = e.changedTouches[0];
      var dx = t.clientX - swipeStartX;
      var dy = t.clientY - swipeStartY;
      if (Math.abs(dx) > 60 && Math.abs(dx) > Math.abs(dy) * 1.4) {
        if (dx < 0) next(); else prev();
      }
    });

    setView(idx);
    return { close: close };
  }

  function initGallery(root) {
    var dataEl = root.querySelector('script[type="application/json"][data-gallery-views]');
    if (!dataEl) return;
    var views;
    try { views = JSON.parse(dataEl.textContent || "[]"); } catch (_e) { return; }
    if (!Array.isArray(views) || !views.length) return;

    var main = root.querySelector("[data-gallery-main]");
    var mainImg = main && main.querySelector("img");
    var label = root.querySelector("[data-gallery-label]");
    var thumbs = $$("[data-gallery-thumb]", root);
    var prev = root.querySelector("[data-gallery-prev]");
    var next = root.querySelector("[data-gallery-next]");
    var current = 0;

    function setMain(i) {
      current = ((i % views.length) + views.length) % views.length;
      if (mainImg) {
        mainImg.src = views[current].src;
        mainImg.alt = views[current].label || "";
      }
      if (label) label.textContent = views[current].label || "";
      thumbs.forEach(function (t, ti) { t.classList.toggle("is-active", ti === current); });
      if (prev) prev.disabled = views.length <= 1;
      if (next) next.disabled = views.length <= 1;
    }

    thumbs.forEach(function (t, ti) {
      t.addEventListener("click", function () { setMain(ti); });
    });
    if (prev) prev.addEventListener("click", function () { setMain(current - 1); });
    if (next) next.addEventListener("click", function () { setMain(current + 1); });

    if (main) {
      main.addEventListener("click", function (e) {
        // Don't open lightbox when clicking the in-image nav buttons
        if (e.target.closest("[data-gallery-prev], [data-gallery-next]")) return;
        createLightbox(views, current);
      });

      // Hover-zoom: tracks cursor position and applies a transform on the
      // image. Only on devices with a real hover pointer.
      var hoverable = window.matchMedia("(hover: hover) and (pointer: fine)").matches;
      if (hoverable) {
        var zoomTimer = null;
        function setCursorTarget(e) {
          var rect = main.getBoundingClientRect();
          var x = ((e.clientX - rect.left) / rect.width) * 100;
          var y = ((e.clientY - rect.top) / rect.height) * 100;
          x = Math.max(0, Math.min(100, x));
          y = Math.max(0, Math.min(100, y));
          main.style.setProperty("--hz-x", x + "%");
          main.style.setProperty("--hz-y", y + "%");
        }
        main.addEventListener("mouseenter", function (e) {
          setCursorTarget(e);
          // Small delay so a quick mouse-over doesn't snap the zoom on.
          zoomTimer = setTimeout(function () {
            main.classList.add("is-hover-zoom");
          }, 120);
        });
        main.addEventListener("mousemove", setCursorTarget);
        main.addEventListener("mouseleave", function () {
          clearTimeout(zoomTimer);
          main.classList.remove("is-hover-zoom");
        });
      }
    }

    setMain(0);
  }

  document.addEventListener("DOMContentLoaded", function () {
    $$("[data-gallery]").forEach(initGallery);
  });
})();
