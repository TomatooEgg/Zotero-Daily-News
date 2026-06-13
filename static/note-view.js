(function () {
  function esc(text) {
    return String(text)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/"/g, '&quot;');
  }

  function apiUrl(root, path) {
    const base = root.dataset.apiBase || '';
    return base + path;
  }

  function getNoteData(root) {
    try {
      return JSON.parse(root.dataset.note || '{}');
    } catch {
      return {};
    }
  }

  function setNoteData(root, patch) {
    const data = { ...getNoteData(root), ...patch };
    root.dataset.note = JSON.stringify(data);
    return data;
  }

  function collectAbstractOriginal(bodyWrap) {
    return bodyWrap ? bodyWrap.textContent.trim() : '';
  }

  function setAbstractPanelOriginal(panel, original) {
    panel.innerHTML = '';
    const label = document.createElement('div');
    label.className = 'abstract-zh-label';
    label.textContent = '英文原文';
    const text = document.createElement('div');
    text.textContent = original;
    panel.appendChild(label);
    panel.appendChild(text);
  }

  function applyAbstractSwap(root, zh, en) {
    const body = root.querySelector('#abstract_body');
    const panel = root.querySelector('#abstract_zh_panel');
    const btn = root.querySelector('#abstract_zh_btn');
    if (!body || !panel) return;
    const original = en || body.dataset.original || collectAbstractOriginal(body);
    body.dataset.original = original;
    body.textContent = zh;
    setAbstractPanelOriginal(panel, original);
    panel.dataset.loaded = '1';
    if (btn) btn.textContent = '查看原文';
  }

  function setupAbstractZhPanel(root, note) {
    const panel = root.querySelector('#abstract_zh_panel');
    if (!panel) return;
    panel.classList.remove('open');
    panel.innerHTML = '';
    if (note.has_abstract_zh && note.abstract_zh) {
      applyAbstractSwap(root, note.abstract_zh, note.abstract_original);
    } else {
      panel.dataset.loaded = '0';
    }
  }

  async function toggleAbstractZh(root) {
    const panel = root.querySelector('#abstract_zh_panel');
    const btn = root.querySelector('#abstract_zh_btn');
    if (!panel || !btn) return;

    if (panel.dataset.loaded === '1') {
      panel.classList.toggle('open');
      return;
    }
    if (root.dataset.abstractLoading === '1') return;

    const note = getNoteData(root);
    root.dataset.abstractLoading = '1';
    btn.disabled = true;
    panel.classList.add('open');
    panel.innerHTML = '<div class="abstract-zh-loading">翻译中…</div>';

    try {
      const res = await fetch(apiUrl(root, '/api/notes/' + encodeURIComponent(note.id) + '/abstract-zh'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || '翻译失败');
      applyAbstractSwap(root, data.text || '', data.original || '');
      panel.classList.add('open');
      setNoteData(root, {
        has_abstract_zh: true,
        abstract_zh: data.text || '',
        abstract_original: data.original || '',
      });
    } catch (err) {
      panel.innerHTML = '<div class="abstract-zh-loading">' + esc(err.message || '翻译失败') + '</div>';
      panel.dataset.loaded = '0';
      panel.classList.add('open');
    } finally {
      root.dataset.abstractLoading = '0';
      btn.disabled = false;
    }
  }

  function placeDeepReadAfterWhyRead(contentEl, wrapEl) {
    if (!contentEl || !wrapEl) return;
    const h3s = contentEl.querySelectorAll('h3');
    let anchor = null;
    for (const h3 of h3s) {
      if (h3.textContent.includes('为何值得读')) {
        anchor = h3;
        break;
      }
    }
    if (anchor) {
      let node = anchor;
      while (node.nextElementSibling && !/^H[23]$/.test(node.nextElementSibling.tagName)) {
        node = node.nextElementSibling;
      }
      node.after(wrapEl);
      return;
    }
    const h2s = contentEl.querySelectorAll('h2');
    for (const h2 of h2s) {
      if (h2.textContent.includes('关键术语')) {
        contentEl.insertBefore(wrapEl, h2);
        return;
      }
    }
    contentEl.appendChild(wrapEl);
  }

  function setupDeepReadPanel(root, note) {
    const panel = root.querySelector('#deep_read_panel');
    if (!panel) return;
    panel.classList.remove('open');
    panel.innerHTML = '';
    if (note.has_deep_read && note.deep_read_html) {
      panel.dataset.loaded = '1';
      panel.innerHTML = '<div class="content">' + note.deep_read_html + '</div>';
    } else {
      panel.dataset.loaded = '0';
    }
  }

  async function toggleDeepRead(root) {
    const panel = root.querySelector('#deep_read_panel');
    const btn = root.querySelector('#deep_read_btn');
    if (!panel || !btn) return;

    if (panel.classList.contains('open') && panel.dataset.loaded === '1') {
      panel.classList.remove('open');
      return;
    }
    if (panel.dataset.loaded === '1') {
      panel.classList.add('open');
      return;
    }
    if (root.dataset.deepLoading === '1') return;

    const note = getNoteData(root);
    root.dataset.deepLoading = '1';
    btn.disabled = true;
    panel.classList.add('open');
    panel.innerHTML =
      '<div class="deep-read-loading"><span class="tomato">🍅</span><div>努力读书中</div></div>';

    try {
      const res = await fetch(apiUrl(root, '/api/notes/' + encodeURIComponent(note.id) + '/deep-read'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || '生成失败');
      panel.innerHTML = '<div class="content">' + (data.html || '') + '</div>';
      panel.dataset.loaded = '1';
      panel.classList.add('open');
      setNoteData(root, { has_deep_read: true, deep_read_html: data.html || '' });
    } catch (err) {
      panel.innerHTML = '<div class="deep-read-loading">' + esc(err.message || '生成失败') + '</div>';
      panel.dataset.loaded = '0';
    } finally {
      root.dataset.deepLoading = '0';
      btn.disabled = false;
    }
  }

  function mountAbstractZhControls(root, note) {
    if (!note.has_abstract) return;
    const contentEl = root.querySelector('.content');
    if (!contentEl) return;

    const h2s = contentEl.querySelectorAll('h2');
    let abstractH2 = null;
    for (const h2 of h2s) {
      if (h2.textContent.trim() === '摘要') {
        abstractH2 = h2;
        break;
      }
    }
    if (!abstractH2) return;

    const head = document.createElement('div');
    head.className = 'abstract-head';
    abstractH2.replaceWith(head);
    head.appendChild(abstractH2);

    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'btn-abstract-zh';
    btn.id = 'abstract_zh_btn';
    btn.textContent = '中文翻译';
    btn.addEventListener('click', function () {
      toggleAbstractZh(root);
    });
    head.appendChild(btn);

    const panel = document.createElement('div');
    panel.className = 'abstract-zh-panel';
    panel.id = 'abstract_zh_panel';

    const bodyWrap = document.createElement('div');
    bodyWrap.id = 'abstract_body';
    bodyWrap.className = 'abstract-body';
    let node = head.nextElementSibling;
    while (node && node.tagName !== 'H2' && node.tagName !== 'H3') {
      const next = node.nextElementSibling;
      bodyWrap.appendChild(node);
      node = next;
    }
    head.after(bodyWrap);
    bodyWrap.after(panel);
    bodyWrap.dataset.original = note.abstract_original || collectAbstractOriginal(bodyWrap);
    setupAbstractZhPanel(root, note);
  }

  function mountDeepReadControls(root, note) {
    const contentEl = root.querySelector('.content');
    if (!contentEl) return;
    const wrap = document.createElement('div');
    wrap.className = 'deep-read-wrap';
    wrap.innerHTML =
      '<button type="button" class="btn-deep-read" id="deep_read_btn">全文深度解读</button>' +
      '<div class="deep-read-panel" id="deep_read_panel"></div>';
    placeDeepReadAfterWhyRead(contentEl, wrap);
    root.querySelector('#deep_read_btn').addEventListener('click', function () {
      toggleDeepRead(root);
    });
    setupDeepReadPanel(root, note);
  }

  function bindRevealButton(root) {
    const btn = root.querySelector('[data-action="reveal"]');
    if (!btn) return;
    btn.addEventListener('click', async function () {
      const note = getNoteData(root);
      try {
        const res = await fetch(apiUrl(root, '/api/notes/' + encodeURIComponent(note.id) + '/reveal'), {
          method: 'POST',
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || '打开失败');
      } catch (err) {
        alert(err.message || '打开失败');
      }
    });
  }

  function shouldUseApiForExternalLinks(root) {
    if (location.protocol === 'file:') return false;
    const viewer = root.dataset.viewer || '';
    return viewer === 'app' || viewer === 'standalone';
  }

  async function openExternalUrl(root, url) {
    try {
      const res = await fetch(apiUrl(root, '/api/open-url'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url }),
      });
      const data = await res.json().catch(function () {
        return {};
      });
      if (!res.ok) throw new Error(data.error || '打开失败');
    } catch (err) {
      if ((root.dataset.viewer || '') === 'app') {
        alert(err.message || '无法打开链接，请确认 Zotero 已安装并在运行');
        return;
      }
      window.location.href = url;
    }
  }

  function bindExternalLinks(root) {
    if (!shouldUseApiForExternalLinks(root)) return;
    root.querySelectorAll('[data-external-link]').forEach(function (el) {
      if (el.dataset.externalBound === '1') return;
      el.dataset.externalBound = '1';
      el.addEventListener('click', function (e) {
        e.preventDefault();
        const url = el.getAttribute('href');
        if (url) openExternalUrl(root, url);
      });
    });
    root.querySelectorAll('.content a[href^="zotero://"]').forEach(function (el) {
      if (el.dataset.externalBound === '1') return;
      el.dataset.externalBound = '1';
      el.addEventListener('click', function (e) {
        e.preventDefault();
        openExternalUrl(root, el.getAttribute('href'));
      });
    });
  }

  function upsertMetaLink(meta, role, href, label) {
    if (!href) {
      const existing = meta.querySelector('a[data-role="' + role + '"]');
      if (existing) existing.remove();
      return;
    }
    let link = meta.querySelector('a[data-role="' + role + '"]');
    if (!link) {
      link = document.createElement('a');
      link.className = 'btn-secondary';
      link.dataset.externalLink = '';
      link.dataset.role = role;
      const reveal = meta.querySelector('[data-action="reveal"]');
      meta.insertBefore(link, reveal || null);
    }
    link.href = href;
    link.textContent = label;
  }

  async function refreshExternalLinks(root) {
    const note = getNoteData(root);
    if (!note.id) return;
    try {
      const res = await fetch(apiUrl(root, '/api/notes/' + encodeURIComponent(note.id)));
      const data = await res.json();
      if (!res.ok) return;
      setNoteData(root, { pdf_url: data.pdf_url, zotero_url: data.zotero_url });
      const meta = root.querySelector('.meta');
      if (!meta) return;
      upsertMetaLink(meta, 'zotero', data.zotero_url, 'Zotero 条目');
      upsertMetaLink(meta, 'pdf', data.pdf_url, 'PDF');
      bindExternalLinks(root);
    } catch (_) {
      /* 忽略网络错误，保留服务端渲染的按钮 */
    }
  }

  function initNoteView(root) {
    if (!root || root.dataset.initialized === '1') return;
    root.dataset.initialized = '1';
    const note = getNoteData(root);
    mountAbstractZhControls(root, note);
    mountDeepReadControls(root, note);
    bindRevealButton(root);
    bindExternalLinks(root);
    refreshExternalLinks(root);
  }

  window.initNoteView = initNoteView;

  document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('.note-view-root[data-autoinit="1"]').forEach(initNoteView);
  });
})();
