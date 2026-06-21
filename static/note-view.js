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

  function notifyUser(message) {
    if (typeof window.toast === 'function') window.toast(message);
    else alert(message);
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

  let mermaidLoadPromise = null;

  function loadMermaid() {
    if (window.mermaid) return Promise.resolve(window.mermaid);
    if (mermaidLoadPromise) return mermaidLoadPromise;
    mermaidLoadPromise = new Promise(function (resolve, reject) {
      const script = document.createElement('script');
      script.src = 'https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js';
      script.onload = function () {
        window.mermaid.initialize({
          startOnLoad: false,
          theme: 'neutral',
          securityLevel: 'loose',
        });
        resolve(window.mermaid);
      };
      script.onerror = function () {
        reject(new Error('Mermaid 加载失败'));
      };
      document.head.appendChild(script);
    });
    return mermaidLoadPromise;
  }

  function normalizeMermaidSource(source) {
    return source
      .replace(/\[\\"/g, '["')
      .replace(/\\"\]/g, '"]')
      .replace(/\["([^"\]]+)\\?\]$/gm, '["$1"]');
  }

  function showMermaidFallback(div, source) {
    const pre = document.createElement('pre');
    const codeEl = document.createElement('code');
    codeEl.className = 'language-mermaid';
    codeEl.textContent = source;
    pre.appendChild(codeEl);
    const hint = document.createElement('p');
    hint.className = 'mermaid-fallback-hint';
    hint.textContent = '流程图语法有误，已显示源码。';
    div.replaceWith(pre);
    pre.after(hint);
  }

  async function renderMermaidInContainer(container) {
    if (!container) return;
    const codes = container.querySelectorAll(
      'pre > code.language-mermaid, pre > code.mermaid'
    );
    if (!codes.length) return;

    try {
      await loadMermaid();
    } catch (_) {
      return;
    }

    const nodes = [];
    codes.forEach(function (code) {
      const pre = code.parentElement;
      if (!pre || pre.dataset.mermaidSource === '1') return;
      pre.dataset.mermaidSource = '1';
      const source = normalizeMermaidSource(code.textContent);
      const div = document.createElement('div');
      div.className = 'mermaid';
      div.textContent = source;
      div.dataset.mermaidSourceText = source;
      pre.replaceWith(div);
      nodes.push(div);
    });

    for (const div of nodes) {
      try {
        await window.mermaid.run({ nodes: [div] });
      } catch (err) {
        console.error('Mermaid render error:', err);
        showMermaidFallback(div, div.dataset.mermaidSourceText || div.textContent || '');
      }
    }
  }

  async function ensureDeepReadMermaid(panel) {
    if (!panel || panel.dataset.mermaidRendered === '1') return;
    const content = panel.querySelector('.content');
    if (!content) return;
    await renderMermaidInContainer(content);
    panel.dataset.mermaidRendered = '1';
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

  function updateDeepReadRegenBtn(root) {
    const regenBtn = root.querySelector('#deep_read_regen_btn');
    if (!regenBtn) return;
    const note = getNoteData(root);
    const loading = root.dataset.deepLoading === '1';
    regenBtn.hidden = !note.has_deep_read || loading;
  }

  function setupDeepReadPanel(root, note) {
    const panel = root.querySelector('#deep_read_panel');
    if (!panel) return;
    panel.classList.remove('open');
    panel.innerHTML = '';
    panel.dataset.mermaidRendered = '0';
    if (note.has_deep_read && note.deep_read_html) {
      panel.dataset.loaded = '1';
      panel.innerHTML = '<div class="content">' + note.deep_read_html + '</div>';
    } else {
      panel.dataset.loaded = '0';
    }
    updateDeepReadRegenBtn(root);
  }

  async function fetchDeepRead(root, regenerate) {
    const panel = root.querySelector('#deep_read_panel');
    const btn = root.querySelector('#deep_read_btn');
    const regenBtn = root.querySelector('#deep_read_regen_btn');
    if (!panel) return;

    const note = getNoteData(root);
    const previousHtml = note.deep_read_html || '';
    root.dataset.deepLoading = '1';
    if (btn) btn.disabled = true;
    if (regenBtn) regenBtn.disabled = true;
    updateDeepReadRegenBtn(root);
    panel.classList.add('open');
    panel.innerHTML =
      '<div class="deep-read-loading"><span class="tomato">🍅</span><div>努力读书中</div></div>';

    try {
      const res = await fetch(apiUrl(root, '/api/notes/' + encodeURIComponent(note.id) + '/deep-read'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ regenerate: !!regenerate }),
      });
      const data = await res.json();
      if (!root.isConnected) return;
      if (!res.ok) throw new Error(data.error || '生成失败');
      if (regenerate && data.cached) {
        throw new Error('服务端未执行重新生成，请退出并重启简报 App 后重试');
      }
      if (!(data.html || '').trim()) {
        throw new Error('深度解读结果为空，请稍后重试');
      }
      panel.dataset.mermaidRendered = '0';
      panel.innerHTML = '<div class="content">' + (data.html || '') + '</div>';
      panel.dataset.loaded = '1';
      setNoteData(root, { has_deep_read: true, deep_read_html: data.html || '' });
      await ensureDeepReadMermaid(panel);
    } catch (err) {
      if (!root.isConnected) return;
      const message = err.message || '生成失败';
      notifyUser(message);
      if (regenerate && previousHtml) {
        panel.innerHTML = '<div class="content">' + previousHtml + '</div>';
        panel.dataset.loaded = '1';
      } else {
        panel.innerHTML = '<div class="deep-read-loading">' + esc(message) + '</div>';
        panel.dataset.loaded = '0';
      }
    } finally {
      if (!root.isConnected) return;
      root.dataset.deepLoading = '0';
      if (btn) btn.disabled = false;
      if (regenBtn) regenBtn.disabled = false;
      updateDeepReadRegenBtn(root);
    }
  }

  async function toggleDeepRead(root) {
    const panel = root.querySelector('#deep_read_panel');
    if (!panel) return;

    if (panel.classList.contains('open') && panel.dataset.loaded === '1') {
      panel.classList.remove('open');
      return;
    }
    if (panel.dataset.loaded === '1') {
      panel.classList.add('open');
      await ensureDeepReadMermaid(panel);
      return;
    }
    if (root.dataset.deepLoading === '1') return;
    await fetchDeepRead(root, false);
  }

  async function regenerateDeepRead(root) {
    if (root.dataset.deepLoading === '1') return;
    await fetchDeepRead(root, true);
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
      '<div class="deep-read-head">' +
      '<button type="button" class="btn-deep-read" id="deep_read_btn">全文深度解读</button>' +
      '<button type="button" class="btn-deep-read-regen" id="deep_read_regen_btn" title="重新生成" aria-label="重新生成" hidden>↻</button>' +
      '</div>' +
      '<div class="deep-read-panel" id="deep_read_panel"></div>';
    placeDeepReadAfterWhyRead(contentEl, wrap);
    root.querySelector('#deep_read_btn').addEventListener('click', function () {
      toggleDeepRead(root);
    });
    root.querySelector('#deep_read_regen_btn').addEventListener('click', function () {
      regenerateDeepRead(root);
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

  function bindPushZoteroButton(root) {
    const btn = root.querySelector('[data-action="push-zotero"]');
    if (!btn) return;
    btn.addEventListener('click', async function () {
      const note = getNoteData(root);
      if (!note.id) return;
      if (root.dataset.pushLoading === '1') return;

      root.dataset.pushLoading = '1';
      btn.disabled = true;
      const prevText = btn.textContent;
      btn.textContent = '回推中…';

      try {
        const statusRes = await fetch(
          apiUrl(root, '/api/notes/' + encodeURIComponent(note.id) + '/push-zotero/status')
        );
        const status = await statusRes.json();
        if (!statusRes.ok) throw new Error(status.error || '状态查询失败');

        if (!status.configured) {
          alert('未配置 Zotero API Key。\n请打开控制台 → 设置 → Zotero 回推 填写并保存凭证。');
          return;
        }

        let mode = 'create';
        let noteKey = null;
        const existing = status.existing || [];
        if (existing.length > 0) {
          const updateLatest = confirm(
            '检测到已有 ' + existing.length + ' 条回推笔记。\n\n' +
            '确定 = 更新最新一条\n取消 = 选择其他操作'
          );
          if (updateLatest) {
            mode = 'update';
            noteKey = existing[0].key;
          } else {
            const createNew = confirm('是否新建一条子笔记？');
            if (!createNew) return;
            mode = 'create';
          }
        }

        const body = { mode: mode };
        if (noteKey) body.note_key = noteKey;

        const pushRes = await fetch(
          apiUrl(root, '/api/notes/' + encodeURIComponent(note.id) + '/push-zotero'),
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
          }
        );
        const result = await pushRes.json();
        if (!pushRes.ok) throw new Error(result.error || '回推失败');
        alert(result.message || '已回推，Zotero 同步后可在条目下查看');
      } catch (err) {
        alert(err.message || '回推失败');
      } finally {
        root.dataset.pushLoading = '0';
        btn.disabled = false;
        btn.textContent = prevText;
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

  function bindDigestAppLink(root) {
    if ((root.dataset.viewer || '') !== 'hub') return;
    const el = root.querySelector('[data-role="digest-app"]');
    if (!el || el.dataset.digestBound === '1') return;
    el.dataset.digestBound = '1';
    el.addEventListener('click', function (e) {
      e.preventDefault();
      const url = el.getAttribute('href');
      if (!url) return;
      const note = getNoteData(root);
      const apiBase = root.dataset.apiBase || '';
      // file:// hub 冷启动：直接走深链接，不等待会失败的 API
      if (location.protocol === 'file:' || !apiBase) {
        window.location.href = url;
        return;
      }
      fetch(apiUrl(root, '/api/open-digest-app'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ note_id: note.id }),
      })
        .then(function (res) {
          if (res.ok) return;
          window.location.href = url;
        })
        .catch(function () {
          window.location.href = url;
        });
    });
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
    bindPushZoteroButton(root);
    bindExternalLinks(root);
    bindDigestAppLink(root);
    refreshExternalLinks(root);
  }

  window.initNoteView = initNoteView;

  document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('.note-view-root[data-autoinit="1"]').forEach(initNoteView);
  });
})();
