/* AhantaPulse article editor — TinyMCE 7 + AI assistant + image upload.
   Initialised by templates/admin/article_form.html.

   If the TinyMCE script failed to load (CDN blocked, network down, etc.)
   the page falls back to the plain textarea that's already in the DOM.
   The AI modal still works against that textarea's .value. */

(function () {
  var holder = document.getElementById('body-input');
  if (!holder) return;

  var CFG = window.AHANTA_EDITOR || {};
  var UPLOAD_URL = CFG.uploadUrl || '/dashboard/api/upload-image';
  var AI = (CFG.aiUrls || {});
  var URL_DRAFT   = AI.draft   || '/dashboard/api/ai/draft';
  var URL_IMPROVE = AI.improve || '/dashboard/api/ai/improve';
  var URL_SEO     = AI.seo     || '/dashboard/api/ai/seo';

  function getCsrf() {
    var m = document.querySelector('meta[name=csrf-token]');
    return m ? m.getAttribute('content') : '';
  }

  function showEditorWarning(text) {
    if (document.getElementById('editor-warn-banner')) return;
    var banner = document.createElement('div');
    banner.id = 'editor-warn-banner';
    banner.style.cssText =
      'margin: .5rem 0 .75rem; padding: .75rem 1rem; border-radius: 10px;' +
      'background: var(--warn-bg, #fef3c7); color: var(--warn-text, #92400e);' +
      'border: 1px solid rgba(0,0,0,0.06); font-size: .85rem; line-height: 1.5;';
    banner.innerHTML = '<strong>Heads up:</strong> ' + text;
    var anchor = holder.parentNode;
    if (anchor) anchor.insertBefore(banner, holder);
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

  // ──────────────── Content access helpers ────────────────
  // Always go through these so the AI modal works the same whether
  // TinyMCE mounted or not.
  function getBody() {
    if (window.tinymce && tinymce.activeEditor) {
      return tinymce.activeEditor.getContent() || '';
    }
    return holder.value || '';
  }
  function setBody(html) {
    if (window.tinymce && tinymce.activeEditor) {
      tinymce.activeEditor.setContent(html || '');
      tinymce.activeEditor.save(); // sync to textarea
    } else {
      holder.value = html || '';
    }
  }
  function bodyIsBlank() {
    var v = (getBody() || '').replace(/<[^>]*>/g, '').replace(/&nbsp;/g, '').trim();
    return v.length === 0;
  }

  // ──────────────── TinyMCE init ────────────────
  if (typeof window.tinymce === 'undefined') {
    console.warn('TinyMCE not loaded; falling back to plain textarea.');
    showEditorWarning(
      "The rich-text editor couldn't load (CDN blocked or the TinyMCE API key " +
      "is missing). Set it at Dashboard → Settings → WYSIWYG editor. You can " +
      "still write below in plain text / HTML."
    );
  } else {
    var isDark = document.documentElement.getAttribute('data-theme') === 'dark';

    tinymce.init({
      selector: '#body-input',
      license_key: 'gpl',
      menubar: 'edit view insert format tools table help',
      branding: false,
      promotion: false,
      relative_urls: false,
      convert_urls: false,
      browser_spellcheck: true,
      contextmenu: false,
      object_resizing: 'img,table,iframe',
      paste_data_images: true,
      image_caption: true,
      image_title: true,
      image_advtab: true,
      image_class_list: [
        { title: 'Default', value: '' },
        { title: 'Full width', value: 'w-full' },
        { title: 'Left float', value: 'float-left' },
        { title: 'Right float', value: 'float-right' },
        { title: 'Rounded corners', value: 'rounded-lg' },
      ],
      media_alt_source: false,
      media_poster: false,
      media_dimensions: true,
      automatic_uploads: true,

      // Grow with the content; sticky toolbar so it's always reachable.
      min_height: 540,
      autoresize_bottom_margin: 60,
      autoresize_overflow_padding: 24,
      toolbar_sticky: true,
      toolbar_sticky_offset: 120, /* admin header + writer top bar */
      toolbar_mode: 'sliding',
      toolbar_location: 'top',
      statusbar: true,
      elementpath: false,
      resize: false,

      // Editor visual: light or dark skin to match the dashboard theme.
      skin: isDark ? 'oxide-dark' : 'oxide',
      content_css: isDark ? 'dark' : 'default',
      content_style:
        "@import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700&family=Source+Serif+4:wght@500;700&display=swap');" +
        "body { font-family: 'Manrope', -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif;" +
        "       font-size: 17px; line-height: 1.75; padding: 1.5rem 2rem; max-width: 780px; margin: 0 auto; color: #0f172a; }" +
        "body.dark-mce { color: #e2e8f0; }" +
        "h1, h2, h3, h4 { font-family: 'Source Serif 4', Georgia, serif; line-height: 1.3; }" +
        "h2 { font-size: 1.65rem; font-weight: 700; margin: 1.5rem 0 .5rem; }" +
        "h3 { font-size: 1.3rem; font-weight: 700; margin: 1.3rem 0 .4rem; }" +
        "h4 { font-size: 1.1rem; font-weight: 700; margin: 1.1rem 0 .3rem; }" +
        "p { margin: .75rem 0; }" +
        "img, iframe, video { max-width: 100%; height: auto; border-radius: 8px; }" +
        "iframe { background: #000; }" +
        "blockquote { border-left: 4px solid #0ea5e9; padding: .6rem 1.1rem; margin: 1.2rem 0;" +
        "             font-style: italic; background: rgba(14,165,233,0.06); border-radius: 0 10px 10px 0; }" +
        "pre, code { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }" +
        "pre { background: #f1f5f9; padding: .75rem 1rem; border-radius: 8px; overflow:auto; }" +
        "code { background: #f1f5f9; padding: 1px 6px; border-radius: 4px; font-size: .92em; }" +
        "table { border-collapse: collapse; width: 100%; margin: 1rem 0; }" +
        "table th, table td { border: 1px solid #e2e8f0; padding: .55rem .75rem; }" +
        "table th { background: #f8fafc; font-weight: 600; text-align: left; }" +
        "hr { border: 0; border-top: 1px solid #e2e8f0; margin: 1.4rem 0; }" +
        "a { color: #0284c7; text-decoration: underline; text-underline-offset: 3px; }",

      plugins: [
        'advlist', 'autolink', 'autoresize', 'autosave', 'lists', 'link',
        'image', 'media', 'charmap', 'preview', 'anchor', 'searchreplace',
        'visualblocks', 'visualchars', 'code', 'fullscreen', 'insertdatetime',
        'table', 'wordcount', 'emoticons', 'codesample', 'quickbars',
        'pagebreak', 'nonbreaking', 'directionality', 'help', 'accordion',
      ].join(' '),

      // 3-row sliding toolbar. The "Insert" group is grouped under a dropdown
      // (toolbar_groups) for less visual noise.
      toolbar: [
        'undo redo | blocks | bold italic underline strikethrough | forecolor backcolor',
        'alignleft aligncenter alignright alignjustify | bullist numlist outdent indent',
        'link image media table | blockquote codesample hr | removeformat | aibtn | searchreplace fullscreen preview code help',
      ].join(' | '),

      block_formats:
        'Paragraph=p;' +
        'Heading 2=h2;' +
        'Heading 3=h3;' +
        'Heading 4=h4;' +
        'Pull-quote=blockquote;' +
        'Pre-formatted=pre',

      // Word-count goal in the statusbar.
      statusbar_elements: 'wordcount',

      // Better autosave — TinyMCE's built-in autosave handles restore prompts.
      autosave_ask_before_unload: true,
      autosave_interval: '20s',
      autosave_prefix: window.AHANTA_EDITOR && window.AHANTA_EDITOR.autosaveKey
        ? window.AHANTA_EDITOR.autosaveKey + '-'
        : 'ahanta-tinymce-',
      autosave_restore_when_empty: false,
      autosave_retention: '60m',

      // Quick floating toolbars (image + selection).
      quickbars_selection_toolbar: 'bold italic underline | h2 h3 | blockquote | link forecolor',
      quickbars_image_toolbar: 'alignleft aligncenter alignright | imageoptions | rotateleft rotateright | flipv fliph',
      quickbars_insert_toolbar: 'quickimage quicktable hr',

      // Upload images to our Flask endpoint instead of inlining base64.
      images_upload_handler: function (blobInfo) {
        return new Promise(function (resolve, reject) {
          var fd = new FormData();
          fd.append('file', blobInfo.blob(), blobInfo.filename());
          fetch(UPLOAD_URL, {
            method: 'POST',
            body: fd,
            headers: { 'X-CSRFToken': getCsrf() },
            credentials: 'same-origin',
          })
            .then(function (r) { return r.json(); })
            .then(function (j) {
              if (j && j.ok && j.url) {
                resolve(j.url);
              } else {
                reject({ message: (j && j.error) || 'Upload failed', remove: true });
              }
            })
            .catch(function (err) {
              reject({ message: err.message || 'Network error', remove: true });
            });
        });
      },

      // Custom AI button that opens our existing modal.
      setup: function (editor) {
        editor.ui.registry.addButton('aibtn', {
          text: 'AI ✨',
          tooltip: 'AI writing assistant',
          onAction: function () {
            var m = document.getElementById('ai-modal');
            if (m) m.classList.remove('hidden');
          },
        });

        // Show "Saved … ago" status in the writer top bar.
        var statusEl = document.getElementById('autosave-status');
        var lastSaved = null;
        function updateStatus() {
          if (!statusEl) return;
          if (!lastSaved) { statusEl.textContent = ''; statusEl.classList.add('hidden'); return; }
          var s = Math.max(1, Math.round((Date.now() - lastSaved) / 1000));
          var label = s < 60 ? s + 's ago' : (Math.floor(s / 60) + 'm ago');
          statusEl.textContent = '✓ Draft saved ' + label;
          statusEl.classList.remove('hidden');
        }
        setInterval(updateStatus, 15000);

        // Push to the hidden textarea on every change so a manual submit
        // always grabs the latest content.
        editor.on('change keyup undo redo', function () { editor.save(); });
        // Mark "saved" each time TinyMCE's autosave plugin writes to storage.
        editor.on('StoreDraft', function () { lastSaved = Date.now(); updateStatus(); });

        // If TinyMCE locks the editor (invalid origin / wrong key) we
        // destroy the broken instance and reveal the textarea fallback so
        // the author can ALWAYS see and edit their article content. A
        // banner explains exactly what's wrong.
        editor.on('init', function () {
          setTimeout(function () {
            try {
              var locked = editor.mode && editor.mode.get && editor.mode.get() === 'readonly';
              if (!locked) return;
              // 1. show the warning above the editor
              showEditorWarning(
                "TinyMCE refused to start (invalid origin or key). Falling back to " +
                "a plain HTML editor so you can still see and edit your article. " +
                "Fix: log in at tiny.cloud → API keys, add this site's domain " +
                "(e.g. ahantapulse.online) to the Approved Domains list, then reload."
              );
              // 2. nuke the broken editor and show the raw textarea
              editor.remove();
              holder.style.display = 'block';
              holder.classList.remove('hidden');
            } catch (e) { /* noop */ }
          }, 700);
        });
      },
    });
  }

  // ──────────────── AI modal wiring ────────────────
  var modal = document.getElementById('ai-modal');
  function closeModal() { if (modal) modal.classList.add('hidden'); }
  if (modal) {
    modal.querySelectorAll('[data-ai-close]').forEach(function (b) {
      b.addEventListener('click', closeModal);
    });
  }

  // Tab switching.
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

  function setStatus(html) {
    var s = document.getElementById('ai-status');
    if (s) s.innerHTML = html || '';
  }
  function ensureNotBlank() {
    if (bodyIsBlank()) {
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
    jsonFetch(URL_DRAFT, { brief: brief }).then(function (res) {
      btnDraft.disabled = false;
      if (!res.ok) { setStatus('<span style="color:var(--danger-text)">' + (res.body.error || 'AI request failed.') + '</span>'); return; }
      setBody(res.body.html || '');
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
    jsonFetch(URL_IMPROVE, { body: getBody(), focus_keyword: focus }).then(function (res) {
      btnImprove.disabled = false;
      if (!res.ok) { setStatus('<span style="color:var(--danger-text)">' + (res.body.error || 'AI request failed.') + '</span>'); return; }
      setBody(res.body.html || '');
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
    jsonFetch(URL_SEO, { body: getBody() }).then(function (res) {
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
        data.tags.forEach(function (t) { html += '<span class="chip">' + escapeHTML(t) + '</span>'; });
        html += '</div>';
        html += '<button type="button" id="ai-apply-tags" class="btn-secondary mt-2 text-xs">Add these to my tags</button>';
      }
      out.innerHTML = html;
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
