/* AhantaPulse article editor — Quill 2 + AI assistant + image upload.
   Initialized by article_form.html (which loads Quill from a CDN). */

(function () {
  if (typeof window.Quill !== 'function') {
    console.warn('Quill not loaded; editor will not initialize.');
    return;
  }

  function getCsrf() {
    var m = document.querySelector('meta[name=csrf-token]');
    return m ? m.getAttribute('content') : '';
  }

  function jsonFetch(url, body) {
    return fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'X-CSRFToken': getCsrf(),
      },
      credentials: 'same-origin',
      body: JSON.stringify(body || {}),
    }).then(function (r) {
      return r.json().then(function (j) { return { ok: r.ok && j.ok !== false, status: r.status, body: j }; });
    });
  }

  // ───────── Init Quill ─────────
  var holder = document.getElementById('editor');
  var bodyInput = document.getElementById('body-input');
  if (!holder || !bodyInput) return;

  var initialHTML = bodyInput.value || '';

  // Traditional WYSIWYG toolbar — headings, formatting, lists, indents,
  // alignment, link + image + video, and our AI helper.
  var toolbarOptions = [
    [{ header: [2, 3, 4, false] }],
    ['bold', 'italic', 'underline', 'strike'],
    [{ color: [] }, { background: [] }],
    [{ list: 'ordered' }, { list: 'bullet' }],
    [{ indent: '-1' }, { indent: '+1' }],
    [{ align: [] }],
    ['blockquote', 'code-block'],
    ['link', 'image', 'video'],
    ['clean'],
    ['ai'],     // custom button rendered by article_form.html (label "AI ✨")
  ];

  var quill = new Quill('#editor', {
    theme: 'snow',
    placeholder: 'Tell the story…',
    modules: { toolbar: { container: toolbarOptions } },
  });

  if (initialHTML) {
    quill.clipboard.dangerouslyPasteHTML(0, initialHTML);
  }

  // ───────── Drag-to-resize for images and embedded videos ─────────
  // Click an image or iframe inside the editor → an overlay frame appears
  // with 4 corner handles and an alignment toolbar. Drag any handle to
  // resize (aspect ratio preserved). Click outside or press Esc to deselect.
  (function attachResize() {
    var ICON_LEFT   = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="13" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/></svg>';
    var ICON_CENTER = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><line x1="3" y1="6" x2="21" y2="6"/><line x1="6" y1="12" x2="18" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/></svg>';
    var ICON_RIGHT  = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><line x1="3" y1="6" x2="21" y2="6"/><line x1="11" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/></svg>';
    var ICON_FULL   = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="6" width="18" height="12" rx="1"/></svg>';
    var ICON_DEL    = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2"/></svg>';

    var overlay = document.createElement('div');
    overlay.className = 'ql-resize';
    overlay.style.display = 'none';
    overlay.innerHTML =
      '<div class="ql-resize-frame">' +
        '<span class="ql-resize-handle" data-h="tl"></span>' +
        '<span class="ql-resize-handle" data-h="tr"></span>' +
        '<span class="ql-resize-handle" data-h="bl"></span>' +
        '<span class="ql-resize-handle" data-h="br"></span>' +
        '<span class="ql-resize-size" data-size></span>' +
      '</div>' +
      '<div class="ql-resize-bar">' +
        '<button type="button" data-act="left"   title="Float left">'   + ICON_LEFT   + '</button>' +
        '<button type="button" data-act="center" title="Center">'      + ICON_CENTER + '</button>' +
        '<button type="button" data-act="right"  title="Float right">' + ICON_RIGHT  + '</button>' +
        '<button type="button" data-act="full"   title="Full width">'  + ICON_FULL   + '</button>' +
        '<button type="button" data-act="delete" title="Remove">'      + ICON_DEL    + '</button>' +
      '</div>';
    document.body.appendChild(overlay);

    var target = null;
    var sizeEl = overlay.querySelector('[data-size]');

    function place() {
      if (!target) return;
      var r = target.getBoundingClientRect();
      overlay.style.position = 'fixed';
      overlay.style.top    = r.top + 'px';
      overlay.style.left   = r.left + 'px';
      overlay.style.width  = r.width + 'px';
      overlay.style.height = r.height + 'px';
      sizeEl.textContent = Math.round(r.width) + ' × ' + Math.round(r.height);
    }
    function show(el) {
      target = el;
      overlay.style.display = 'block';
      place();
      syncBody();
    }
    function hide() {
      target = null;
      overlay.style.display = 'none';
    }

    // Click to select (images and iframes)
    quill.root.addEventListener('click', function (e) {
      var t = e.target;
      if (t && (t.tagName === 'IMG' || t.tagName === 'IFRAME')) {
        e.preventDefault();
        e.stopPropagation();
        // Place the cursor right after the element so other actions still work.
        var blot = Quill.find(t);
        if (blot) {
          var idx = quill.getIndex(blot);
          quill.setSelection(idx + 1, 0, 'silent');
        }
        show(t);
      } else if (target && !overlay.contains(t)) {
        hide();
      }
    }, true);

    // Click anywhere else dismisses
    document.addEventListener('mousedown', function (e) {
      if (!target) return;
      if (overlay.contains(e.target)) return;
      if (e.target === target) return;
      hide();
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && target) hide();
    });

    // Keep the frame attached when the page scrolls or resizes
    window.addEventListener('scroll',  place, true);
    window.addEventListener('resize',  place);

    // Hide while the user types text edits
    quill.on('text-change', function (delta, _old, source) {
      // Don't hide for our own resize-driven width/height changes
      if (source === 'silent') return;
      hide();
    });

    // ── Drag-to-resize from each corner ──
    Array.prototype.forEach.call(overlay.querySelectorAll('[data-h]'), function (handle) {
      handle.addEventListener('mousedown', function (e) {
        if (!target) return;
        e.preventDefault();
        e.stopPropagation();

        var which = handle.getAttribute('data-h');
        var startX = e.clientX;
        var startRect = target.getBoundingClientRect();
        var startW = startRect.width;
        var startH = startRect.height;
        var ratio  = startW / Math.max(1, startH);
        var growsRight = (which === 'br' || which === 'tr');

        function onMove(ev) {
          var dx = ev.clientX - startX;
          var newW = growsRight ? (startW + dx) : (startW - dx);
          newW = Math.max(64, newW);
          // Constrain to the editor's content width so users can't push it past the page.
          var editorWidth = quill.root.clientWidth;
          if (newW > editorWidth) newW = editorWidth;
          var newH = Math.round(newW / ratio);
          target.setAttribute('width',  Math.round(newW));
          target.setAttribute('height', newH);
          target.style.width  = Math.round(newW) + 'px';
          target.style.height = newH + 'px';
          place();
        }
        function onUp() {
          document.removeEventListener('mousemove', onMove);
          document.removeEventListener('mouseup', onUp);
          syncBody();
        }
        document.addEventListener('mousemove', onMove);
        document.addEventListener('mouseup',  onUp);
      });
    });

    // ── Alignment / delete buttons ──
    overlay.querySelectorAll('[data-act]').forEach(function (btn) {
      btn.addEventListener('click', function (e) {
        if (!target) return;
        e.preventDefault();
        var act = btn.getAttribute('data-act');
        if (act === 'delete') {
          var blot = Quill.find(target);
          if (blot) {
            var idx = quill.getIndex(blot);
            quill.deleteText(idx, 1, 'user');
          }
          hide();
          syncBody();
          return;
        }
        // Reset all alignment-related styles before applying the new one
        target.style.float = '';
        target.style.display = '';
        target.style.marginLeft = '';
        target.style.marginRight = '';

        if (act === 'left') {
          target.style.float = 'left';
          target.style.marginRight = '1rem';
          target.style.marginBottom = '0.5rem';
        } else if (act === 'right') {
          target.style.float = 'right';
          target.style.marginLeft = '1rem';
          target.style.marginBottom = '0.5rem';
        } else if (act === 'center') {
          target.style.display = 'block';
          target.style.marginLeft = 'auto';
          target.style.marginRight = 'auto';
        } else if (act === 'full') {
          target.style.display = 'block';
          target.style.width = '100%';
          target.style.height = 'auto';
          target.style.marginLeft = '0';
          target.style.marginRight = '0';
          target.removeAttribute('width');
          target.removeAttribute('height');
        }
        place();
        syncBody();
      });
    });
  })();

  // Sync editor → hidden textarea on every change and on submit.
  function syncBody() {
    bodyInput.value = quill.root.innerHTML;
  }
  quill.on('text-change', syncBody);
  var form = document.getElementById('article-form');
  if (form) form.addEventListener('submit', syncBody);

  // ───────── Custom image handler (upload to server, not base64) ─────────
  var uploadUrl = holder.getAttribute('data-upload-url');
  if (uploadUrl) {
    quill.getModule('toolbar').addHandler('image', function () {
      var input = document.createElement('input');
      input.type = 'file';
      input.accept = 'image/*';
      input.onchange = function () {
        var file = input.files && input.files[0];
        if (!file) return;
        var fd = new FormData();
        fd.append('file', file);
        var range = quill.getSelection(true);
        // Insert a temporary placeholder so the user sees something happen.
        quill.insertText(range.index, 'Uploading…', { italic: true });
        fetch(uploadUrl, { method: 'POST', body: fd, headers: { 'X-CSRFToken': getCsrf() }, credentials: 'same-origin' })
          .then(function (r) { return r.json(); })
          .then(function (j) {
            quill.deleteText(range.index, 'Uploading…'.length);
            if (j && j.ok && j.url) {
              quill.insertEmbed(range.index, 'image', j.url);
              quill.setSelection(range.index + 1);
            } else {
              alert('Upload failed: ' + ((j && j.error) || 'unknown error'));
            }
          })
          .catch(function (err) {
            quill.deleteText(range.index, 'Uploading…'.length);
            alert('Upload failed: ' + err.message);
          });
      };
      input.click();
    });
  }

  // ───────── AI modal ─────────
  var modal = document.getElementById('ai-modal');
  function openModal()  { if (modal) modal.classList.remove('hidden'); }
  function closeModal() { if (modal) modal.classList.add('hidden'); }
  if (modal) {
    modal.querySelectorAll('[data-ai-close]').forEach(function (b) { b.addEventListener('click', closeModal); });
  }
  // Hook the custom toolbar AI button.
  quill.getModule('toolbar').addHandler('ai', openModal);

  // Tab switching inside the modal.
  document.querySelectorAll('[data-ai-tab]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var target = btn.getAttribute('data-ai-tab');
      document.querySelectorAll('[data-ai-tab]').forEach(function (b) {
        b.classList.toggle('active-tab', b.getAttribute('data-ai-tab') === target);
      });
      document.querySelectorAll('[data-ai-panel]').forEach(function (p) {
        p.classList.toggle('hidden', p.getAttribute('data-ai-panel') !== target);
      });
    });
  });

  // Run buttons
  function setStatus(html) {
    var s = document.getElementById('ai-status');
    if (s) s.innerHTML = html || '';
  }
  function ensureNotBlank() {
    var v = (bodyInput.value || '').replace(/<[^>]*>/g, '').trim();
    if (!v) {
      setStatus('<span style="color:var(--danger-text)">Write or paste something first.</span>');
      return false;
    }
    return true;
  }

  var btnDraft   = document.getElementById('ai-run-draft');
  var btnImprove = document.getElementById('ai-run-improve');
  var btnSEO     = document.getElementById('ai-run-seo');

  if (btnDraft) btnDraft.addEventListener('click', function () {
    var brief = (document.getElementById('ai-brief').value || '').trim();
    if (!brief) { setStatus('<span style="color:var(--danger-text)">Write a short brief first.</span>'); return; }
    setStatus('<span class="spinner"></span> Drafting…');
    btnDraft.disabled = true;
    jsonFetch('/dashboard/api/ai/draft', { brief: brief }).then(function (res) {
      btnDraft.disabled = false;
      if (!res.ok) { setStatus('<span style="color:var(--danger-text)">' + (res.body.error || 'AI request failed.') + '</span>'); return; }
      // Replace editor content with the draft.
      quill.setContents([]);
      quill.clipboard.dangerouslyPasteHTML(0, res.body.html || '');
      syncBody();
      setStatus('<span style="color:var(--success-text)">Draft inserted. Edit before publishing.</span>');
      setTimeout(closeModal, 600);
    }).catch(function (err) {
      btnDraft.disabled = false;
      setStatus('<span style="color:var(--danger-text)">' + err.message + '</span>');
    });
  });

  if (btnImprove) btnImprove.addEventListener('click', function () {
    if (!ensureNotBlank()) return;
    var focus = (document.getElementById('ai-focus-keyword').value || '').trim();
    setStatus('<span class="spinner"></span> Polishing & adding SEO touches…');
    btnImprove.disabled = true;
    jsonFetch('/dashboard/api/ai/improve', { body: bodyInput.value, focus_keyword: focus }).then(function (res) {
      btnImprove.disabled = false;
      if (!res.ok) { setStatus('<span style="color:var(--danger-text)">' + (res.body.error || 'AI request failed.') + '</span>'); return; }
      quill.setContents([]);
      quill.clipboard.dangerouslyPasteHTML(0, res.body.html || '');
      syncBody();
      setStatus('<span style="color:var(--success-text)">Article rewritten. Review carefully.</span>');
      setTimeout(closeModal, 600);
    }).catch(function (err) {
      btnImprove.disabled = false;
      setStatus('<span style="color:var(--danger-text)">' + err.message + '</span>');
    });
  });

  if (btnSEO) btnSEO.addEventListener('click', function () {
    if (!ensureNotBlank()) return;
    setStatus('<span class="spinner"></span> Generating headline ideas, summary and tags…');
    btnSEO.disabled = true;
    jsonFetch('/dashboard/api/ai/seo', { body: bodyInput.value }).then(function (res) {
      btnSEO.disabled = false;
      if (!res.ok) { setStatus('<span style="color:var(--danger-text)">' + (res.body.error || 'AI request failed.') + '</span>'); return; }
      var out = document.getElementById('ai-seo-output');
      var data = res.body || {};
      var html = '';
      if (data.title_suggestions && data.title_suggestions.length) {
        html += '<p class="mt-2 text-xs uppercase tracking-[0.16em] text-muted">Headline ideas</p><div class="mt-1 space-y-1">';
        data.title_suggestions.forEach(function (t) {
          html += '<button type="button" class="block w-full text-left rounded-md border border-app bg-page px-3 py-2 text-sm hover:border-accent" data-apply-title="' + escapeHTML(t) + '">' + escapeHTML(t) + '</button>';
        });
        html += '</div>';
      }
      if (data.summary) {
        html += '<p class="mt-3 text-xs uppercase tracking-[0.16em] text-muted">Meta description</p>';
        html += '<p class="mt-1 rounded-md border border-app bg-page p-3 text-sm">' + escapeHTML(data.summary) + '</p>';
        html += '<button type="button" id="ai-apply-summary" class="btn-secondary mt-2 text-xs">Use as summary</button>';
      }
      if (data.focus_keyword) {
        html += '<p class="mt-3 text-xs uppercase tracking-[0.16em] text-muted">Focus keyword</p>';
        html += '<p class="mt-1 chip chip-accent">' + escapeHTML(data.focus_keyword) + '</p>';
      }
      if (data.tags && data.tags.length) {
        html += '<p class="mt-3 text-xs uppercase tracking-[0.16em] text-muted">Suggested tags</p>';
        html += '<div class="mt-1 flex flex-wrap gap-1.5">';
        data.tags.forEach(function (t) {
          html += '<span class="chip">' + escapeHTML(t) + '</span>';
        });
        html += '</div>';
        html += '<button type="button" id="ai-apply-tags" class="btn-secondary mt-2 text-xs">Add these to my tags</button>';
      }
      out.innerHTML = html;
      // Wire up apply buttons.
      out.querySelectorAll('[data-apply-title]').forEach(function (b) {
        b.addEventListener('click', function () {
          var titleInput = document.querySelector('input[name=title]');
          if (titleInput) titleInput.value = b.getAttribute('data-apply-title');
        });
      });
      var sumBtn = document.getElementById('ai-apply-summary');
      if (sumBtn) sumBtn.addEventListener('click', function () {
        var sum = document.querySelector('[name=summary]');
        if (sum) sum.value = data.summary;
      });
      var tagBtn = document.getElementById('ai-apply-tags');
      if (tagBtn) tagBtn.addEventListener('click', function () {
        var t = document.querySelector('input[name=tags]');
        if (t) {
          var existing = (t.value || '').split(',').map(function (s) { return s.trim(); }).filter(Boolean);
          (data.tags || []).forEach(function (x) { if (existing.indexOf(x) === -1) existing.push(x); });
          t.value = existing.join(', ');
        }
      });
      setStatus('<span style="color:var(--success-text)">Suggestions ready — click to apply.</span>');
    }).catch(function (err) {
      btnSEO.disabled = false;
      setStatus('<span style="color:var(--danger-text)">' + err.message + '</span>');
    });
  });

  function escapeHTML(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
})();
