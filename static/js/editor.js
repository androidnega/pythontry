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
  } else {
    var isDark = document.documentElement.getAttribute('data-theme') === 'dark';

    tinymce.init({
      selector: '#body-input',
      license_key: 'gpl',
      height: 620,
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
      ],
      media_alt_source: false,
      media_poster: false,
      media_dimensions: true,
      automatic_uploads: true,

      // Editor visual: light or dark skin to match the dashboard theme.
      skin: isDark ? 'oxide-dark' : 'oxide',
      content_css: isDark ? 'dark' : 'default',
      content_style:
        "body { font-family: 'Manrope', -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif;" +
        "       font-size: 16.5px; line-height: 1.7; padding: 1rem 1.4rem; }" +
        "img, iframe { max-width: 100%; height: auto; }" +
        "blockquote { border-left: 3px solid #0ea5e9; padding: .4rem 1rem; margin: 1rem 0;" +
        "             font-style: italic; background: rgba(14,165,233,0.06); border-radius: 0 8px 8px 0; }" +
        "h2 { font-size: 1.6rem; font-weight: 700; margin: 1.2rem 0 .5rem; }" +
        "h3 { font-size: 1.25rem; font-weight: 700; margin: 1.1rem 0 .4rem; }",

      plugins: [
        'advlist', 'autolink', 'lists', 'link', 'image', 'media', 'charmap',
        'preview', 'anchor', 'searchreplace', 'visualblocks', 'code',
        'fullscreen', 'insertdatetime', 'table', 'wordcount', 'emoticons',
        'codesample', 'quickbars',
      ].join(' '),

      toolbar: [
        'undo redo | blocks | bold italic underline strikethrough',
        'forecolor backcolor removeformat | alignleft aligncenter alignright alignjustify',
        'bullist numlist outdent indent | link image media table',
        'blockquote codesample emoticons | aibtn | fullscreen preview code',
      ].join(' | '),

      block_formats: 'Paragraph=p; Heading 2=h2; Heading 3=h3; Heading 4=h4; Blockquote=blockquote; Code=pre',

      // Quick floating toolbars (image + selection).
      quickbars_selection_toolbar: 'bold italic link blockquote forecolor',
      quickbars_image_toolbar: 'alignleft aligncenter alignright | imageoptions',
      quickbars_insert_toolbar: false,

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
        // Make sure submit-time content is always saved to the textarea.
        editor.on('change keyup undo redo', function () { editor.save(); });
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
