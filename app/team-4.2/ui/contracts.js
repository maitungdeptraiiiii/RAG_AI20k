// Phần 4 — đính kèm hợp đồng trong chat (spec 2026-11-11-contract-review-design.md).
// Dùng các biến / hàm toàn cục của index.html: chatSessions, currentSessionId, saveSessionsToStorage,
// renderRecentsList, setChatInputPosition, escapeHtml, scrollToBottom, toggleIngestModal.
(function () {
  const API = '/api/contracts';
  const LS_SAVED = 'justice_saved_contracts_v1';
  const GONE = 'Hợp đồng này đã hết phiên — hãy đính kèm lại';
  const FACT = { found: ['Máy đọc được — chờ bạn xác nhận', '#475467'], conflict: ['Hợp đồng ghi nhiều giá trị khác nhau — hãy chọn', '#b42318'],
    missing: ['Không tìm thấy trong hợp đồng', '#8a5a00'], confirmed: ['Đã xác nhận', '#006300'],
    corrected: ['Bạn đã sửa', '#006300'], unknown: ['Bạn không biết', '#475467'] };

  const state = { cards: {}, active: null, mode: 'free' };
  const esc = s => escapeHtml(String(s ?? ''));

  function savedIds() { try { return JSON.parse(localStorage.getItem(LS_SAVED) || '[]'); } catch (e) { return []; } }
  function setSavedIds(ids) { try { localStorage.setItem(LS_SAVED, JSON.stringify([...new Set(ids)].slice(0, 50))); } catch (e) { /* bỏ qua */ } }

  async function api(path, opts = {}) {
    const res = await fetch(API + path, opts);
    const data = await res.json().catch(() => ({}));
    if (!res.ok) { const err = new Error(data.error || `Lỗi server (${res.status})`); err.status = res.status; throw err; }
    return data;
  }
  const post = (path, body) => api(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) });

  // ------------------------------------------------------------------ phiên chat
  function currentSession() { return chatSessions.find(s => s.id === currentSessionId) || null; }

  function ensureSession(title) {
    if (!currentSessionId || !currentSession()) {
      currentSessionId = 'session_' + Date.now();
      chatSessions.unshift({ id: currentSessionId, title: title.slice(0, 36), createdAt: Date.now(), updatedAt: Date.now(), turns: [] });
      document.getElementById('conversation-title').textContent = title.slice(0, 36);
    }
    setChatInputPosition('bottom');
    document.getElementById('hero-view').classList.add('hidden');
    const wrapper = document.getElementById('main-content-wrapper');
    if (wrapper) { wrapper.classList.remove('justify-center'); wrapper.classList.add('justify-start'); }
    document.getElementById('chat-thread-view').classList.remove('hidden');
    return currentSession();
  }

  function pushTurn(turn) {
    const s = currentSession();
    if (!s) return;
    s.turns = s.turns || [];
    s.turns.push(turn);
    s.updatedAt = Date.now();
    saveSessionsToStorage();
    renderRecentsList();
  }

  function sessionContractIds(sess) {
    return [...new Set(((sess && sess.turns) || []).filter(t => t.kind === 'contract_card').map(t => t.contract_id))];
  }

  // ------------------------------------------------------------------ menu "+" và hộp đính kèm
  function closeMenu() { document.getElementById('ct-plus-menu')?.remove(); }

  function openPlusMenu(event) {
    event.stopPropagation();
    closeMenu();
    const r = event.currentTarget.getBoundingClientRect();
    const menu = document.createElement('div');
    menu.id = 'ct-plus-menu';
    menu.className = 'fixed z-50 bg-white border border-neutral-200 rounded-xl shadow-lg py-1 text-[13.5px] w-64';
    menu.style.left = Math.max(8, Math.min(r.left, innerWidth - 270)) + 'px';
    menu.style.top = Math.max(8, r.top - 104) + 'px';
    menu.innerHTML = `
      <button type="button" data-a="ingest" class="w-full text-left px-3 py-2 hover:bg-neutral-100">Nạp tài liệu vào kho
        <div class="text-[11.5px] text-neutral-500">Tài liệu được index để tra cứu chung</div></button>
      <button type="button" data-a="contract" class="w-full text-left px-3 py-2 hover:bg-neutral-100">Đính kèm hợp đồng để soát
        <div class="text-[11.5px] text-neutral-500">Không đưa vào kho tra cứu</div></button>`;
    menu.addEventListener('click', e => {
      const a = e.target.closest('button')?.dataset.a;
      closeMenu();
      if (a === 'ingest') toggleIngestModal(true);
      if (a === 'contract') openAttach();
    });
    document.body.appendChild(menu);
    setTimeout(() => document.addEventListener('click', closeMenu, { once: true }), 0);
  }

  function openAttach() {
    document.getElementById('ct-attach')?.remove();
    const box = document.createElement('div');
    box.id = 'ct-attach';
    box.className = 'fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4';
    box.innerHTML = `
      <div class="bg-white rounded-2xl w-full max-w-md p-5 space-y-4 max-h-[90vh] overflow-y-auto">
        <div class="flex items-center justify-between"><h3 class="text-[16px] font-semibold">Đính kèm hợp đồng để soát</h3>
          <button type="button" data-a="close" class="text-neutral-400 hover:text-black" aria-label="Đóng">✕</button></div>
        <input id="ct-file" type="file" accept=".pdf,.docx,.txt,.md,.png,.jpg,.jpeg,.tif,.tiff,.webp"
          class="w-full text-[13px] file:mr-3 file:py-1.5 file:px-3 file:rounded-lg file:border-0 file:bg-neutral-900 file:text-white">
        <fieldset class="space-y-1 text-[13.5px]"><legend class="font-medium mb-1">Lưu hợp đồng</legend>
          <label class="flex gap-2"><input type="radio" name="ct-persist" value="0" checked> Chỉ trong phiên này <span class="text-neutral-500">(mất khi tắt server)</span></label>
          <label class="flex gap-2"><input type="radio" name="ct-persist" value="1"> Lưu lại để mở sau</label></fieldset>
        <p class="text-[12px] text-neutral-500">Thông tin cá nhân (CCCD, số tài khoản, SĐT, email) được che trước khi gửi cho AI. Hợp đồng không được đưa vào kho tra cứu chung.</p>
        <div id="ct-attach-status" class="text-[13px]" role="status" aria-live="polite"></div>
        <button type="button" data-a="go" class="w-full bg-neutral-900 hover:bg-black text-white rounded-lg py-2 text-[14px]">Đính kèm & đọc hợp đồng</button>
        <div id="ct-saved" class="border-t pt-3"></div>
      </div>`;
    box.addEventListener('click', async e => {
      const a = e.target.closest('[data-a]')?.dataset.a;
      if (e.target === box || a === 'close') box.remove();
      if (a === 'go') await doAttach(box);
      if (a === 'open') { box.remove(); await openSaved(e.target.closest('[data-a]').dataset.id); }
    });
    document.body.appendChild(box);
    renderSavedList();
  }

  async function renderSavedList() {
    const el = document.getElementById('ct-saved');
    const ids = savedIds();
    if (!el || !ids.length) return;
    try {
      const { contracts } = await api('?ids=' + encodeURIComponent(ids.join(',')));
      setSavedIds(contracts.map(c => c.contract_id));
      el.innerHTML = contracts.length ? `<div class="text-[13px] font-medium mb-2">Hợp đồng đã lưu</div>` + contracts.map(c => `
        <div class="flex items-center justify-between gap-2 py-1 text-[13px]"><span class="truncate">${esc(c.filename)}</span>
          <button type="button" data-a="open" data-id="${esc(c.contract_id)}" class="text-blue-600 hover:underline flex-shrink-0">Mở</button></div>`).join('') : '';
    } catch (e) { el.innerHTML = ''; }
  }

  async function doAttach(box) {
    const file = box.querySelector('#ct-file').files[0];
    const status = box.querySelector('#ct-attach-status');
    if (!file) { status.textContent = 'Hãy chọn file hợp đồng.'; return; }
    const fd = new FormData();
    fd.append('file', file);
    fd.append('persist', box.querySelector('input[name="ct-persist"]:checked').value);
    status.textContent = 'Đang đọc hợp đồng và trích thông tin…';
    box.querySelector('[data-a="go"]').disabled = true;
    try {
      const res = await fetch(API, { method: 'POST', body: fd });
      const card = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(card.error || `Lỗi server (${res.status})`);
      box.remove();
      addCard(card);
    } catch (e) {
      status.textContent = e.message;
      box.querySelector('[data-a="go"]').disabled = false;
    }
  }

  async function openSaved(cid) {
    try { addCard(await api('/' + encodeURIComponent(cid))); } catch (e) { alert(e.message); }
  }

  function addCard(card) {
    state.cards[card.contract_id] = card;
    if (card.persist) setSavedIds([...savedIds(), card.contract_id]);
    ensureSession('Hợp đồng: ' + card.filename);
    const turn = { turnId: 'ct-' + Date.now(), kind: 'contract_card', contract_id: card.contract_id, filename: card.filename, timestamp: Date.now() };
    pushTurn(turn);
    renderCardTurn(turn, card);
    setActive(card.contract_id, 'contract');
    scrollToBottom();
  }

  // ------------------------------------------------------------------ thẻ hợp đồng
  function cardHtml(turnId, c) {
    const cov = c.coverage || {};
    const parts = c.parts || [];
    const warnings = (c.parse_report && c.parse_report.warnings) || [];
    const graph = c.graph || {};
    const graphNote = graph.enabled && !graph.published
      ? `<div class="text-[12.5px]" style="color:#8a5a00">Đồ thị chưa cập nhật: ${esc(graph.error || (graph.problems || [])[0] || '')}</div>` : '';
    return `
      <div class="border border-neutral-200 rounded-2xl p-4 space-y-3 bg-white">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <div class="min-w-0"><div class="text-[14.5px] font-semibold truncate">📎 ${esc(c.filename)}</div>
            <div class="text-[12px] text-neutral-500">${esc((c.facts && c.facts.type) || 'chưa rõ loại')} · ${cov.total} điều khoản · ${c.persist ? 'Đã lưu' : 'Chỉ trong phiên này'}${parts.length > 1 ? ' · ' + (parts.length - 1) + ' phụ lục' : ''}</div></div>
          <div class="flex gap-2 text-[12.5px]">
            ${c.persist ? '' : '<button type="button" data-a="save" class="text-blue-600 hover:underline">Lưu hợp đồng này</button>'}
            <button type="button" data-a="remove" class="text-neutral-500 hover:text-red-700">Gỡ</button></div>
        </div>
        ${c.facts && c.facts.error ? `<div class="text-[12.5px]" style="color:#8a5a00">⚠ Chưa trích được thông tin nền: ${esc(c.facts.error)}</div>` : ''}
        ${warnings.map(w => `<div class="text-[12.5px]" style="color:#8a5a00">⚠ ${esc(w)}</div>`).join('')}
        ${graphNote}
        ${verifyHtml(c)}
        <div class="flex flex-wrap gap-1.5">
          <button type="button" data-a="ask" class="text-[13px] border border-neutral-300 rounded-lg px-3 py-1.5 hover:bg-neutral-100">Hỏi về hợp đồng này</button></div>
        <div data-f="status" class="text-[12.5px] text-neutral-500" role="status" aria-live="polite"></div>
      </div>`;
  }

  // ------------------------------------------------------------------ xác minh thông tin
  function unitLabel(c, uid) { return ((c.units || []).find(u => u.uid === uid) || {}).label || ''; }

  function factInput(c, f) {
    const cls = 'border border-neutral-300 rounded-md px-1.5 py-0.5 text-[12.5px] max-w-full';
    const dis = f.status === 'unknown' ? 'disabled' : '';
    const choices = (f.options && f.options.length) ? f.options
      : (f.candidates || []).length > 1 ? f.candidates.map(x => x.value) : null;
    if (choices) {
      const label = v => (f.option_labels && f.option_labels[v]) || v;
      return `<select data-fact="${esc(f.key)}" class="${cls}" ${dis}><option value="">— chọn —</option>
        ${choices.map(v => `<option value="${esc(v)}" ${v === f.value ? 'selected' : ''}>${esc(label(v))}</option>`).join('')}</select>`;
    }
    const type = f.kind === 'date' ? 'date' : 'text';
    return `<input type="${type}" data-fact="${esc(f.key)}" value="${esc(f.value || '')}" class="${cls} w-56" ${dis}>`;
  }

  function factRow(c, f) {
    const st = FACT[f.status] || ['', '#475467'];
    const cands = (f.candidates || []).length > 1
      ? `<div class="text-[11.5px] text-neutral-500">${f.candidates.map(x => `“${esc(x.quote || x.value)}” (${esc(unitLabel(c, x.unit))})`).join(' · ')}</div>`
      : (f.quote ? `<div class="text-[11.5px] text-neutral-500 italic">“${esc(f.quote)}”${f.unit ? ` <span class="not-italic">(${esc(unitLabel(c, f.unit))})</span>` : ''}</div>` : '');
    const canUnknown = !['party', 'sign_date'].includes(f.key);
    return `<tr class="align-top border-b border-neutral-100">
      <td class="py-1.5 pr-2 text-[12.5px] whitespace-nowrap">${esc(f.label)}${f.required ? ' <span style="color:#b42318">*</span>' : ''}</td>
      <td class="py-1.5 pr-2">${factInput(c, f)}${cands}</td>
      <td class="py-1.5 text-[11.5px]"><div style="color:${st[1]}">${esc(st[0])}</div>
        ${canUnknown ? `<label class="flex gap-1 text-neutral-500"><input type="checkbox" data-unknown="${esc(f.key)}" ${f.status === 'unknown' ? 'checked' : ''}> không biết</label>` : ''}</td></tr>`;
  }

  function verifyHtml(c) {
    const v = c.verification;
    if (!v) return '';
    const open = !v.complete || state.editFacts === c.contract_id;
    const cov = v.coverage && v.coverage.read < v.coverage.total
      ? `<div class="text-[12px]" style="color:#8a5a00">⚠ AI mới đọc ${v.coverage.read}/${v.coverage.total} điều khoản khi trích thông tin.</div>` : '';
    const warn = (v.warnings || []).map(w => `<div class="text-[12px]" style="color:#8a5a00">⚠ ${esc(w)}</div>`).join('');
    if (!open) {
      const brief = v.fields.filter(f => f.required).map(f => `${esc(f.label)}: <span class="text-neutral-800">${esc(f.status === 'unknown' ? 'không biết' : ((f.option_labels || {})[f.value] || f.value || '—'))}</span>`).join(' · ');
      return `<div class="text-[12.5px] text-neutral-500"><span style="color:#006300">✓ Đã xác minh thông tin</span> · ${brief}
        <button type="button" data-a="edit-facts" class="text-blue-600 hover:underline ml-1">Xem / sửa</button></div>`;
    }
    const required = v.fields.filter(f => f.required), other = v.fields.filter(f => !f.required);
    return `<div class="border border-neutral-200 rounded-xl p-3 space-y-2" data-f="verify">
      <div class="text-[13px] font-semibold">Xác minh thông tin trước khi soát</div>
      <div class="text-[12px] text-neutral-500">AI đã đọc hợp đồng và điền sẵn. Hãy kiểm tra từng dòng, sửa chỗ sai, chọn “không biết” nếu không rõ.
        Mục có <span style="color:#b42318">*</span> là bắt buộc trước khi soát.</div>
      ${cov}${warn}
      <div class="overflow-x-auto"><table class="w-full"><tbody>${required.map(f => factRow(c, f)).join('')}</tbody></table></div>
      ${other.length ? `<details ${v.complete ? '' : 'open'}><summary class="text-[12.5px] text-neutral-600 cursor-pointer">Thông tin nên xác nhận (${other.length})</summary>
        <div class="overflow-x-auto"><table class="w-full"><tbody>${other.map(f => factRow(c, f)).join('')}</tbody></table></div></details>` : ''}
      <button type="button" data-a="facts" class="bg-neutral-900 text-white rounded-lg px-3 py-1.5 text-[13px]">Xác nhận thông tin</button>
      ${v.pending.length ? `<span class="text-[12px] ml-2" style="color:#8a5a00">Còn thiếu: ${esc(v.pending.map(p => p.label).join(', '))}</span>` : ''}
    </div>`;
  }

  function collectFacts(el, c) {
    const answers = {};
    for (const f of c.verification.fields) {
      const unknown = el.querySelector(`[data-unknown="${f.key}"]`);
      if (unknown && unknown.checked) { if (f.status !== 'unknown') answers[f.key] = { action: 'unknown' }; continue; }
      const input = el.querySelector(`[data-fact="${f.key}"]`);
      const value = input ? input.value.trim() : '';
      if (!value) continue;
      if (value === (f.value || '') && ['confirmed', 'corrected'].includes(f.status)) continue;
      answers[f.key] = value === (f.value || '') && f.status === 'found' ? { action: 'confirm' } : { action: 'set', value };
    }
    return answers;
  }

  function goneHtml(turn) {
    return `<div class="border border-neutral-200 rounded-2xl p-4 text-[13px] bg-neutral-50">
      📎 ${esc(turn.filename || 'Hợp đồng')} — <span style="color:#8a5a00">${GONE}.</span></div>`;
  }

  function renderCardTurn(turn, card) {
    const thread = document.getElementById('chat-thread-view');
    let el = document.getElementById(turn.turnId);
    if (!el) {
      el = document.createElement('div');
      el.id = turn.turnId;
      thread.appendChild(el);
    }
    if (!card) { el.innerHTML = goneHtml(turn); return; }
    el.innerHTML = cardHtml(turn.turnId, card);
    el.onclick = e => onCardClick(e, el, turn, card.contract_id);
  }

  async function refreshCard(el, turn, cid) {
    try {
      const card = await api('/' + encodeURIComponent(cid));
      state.cards[cid] = card;
      renderCardTurn(turn, card);
    } catch (e) {
      if (e.status === 404) { delete state.cards[cid]; renderCardTurn(turn, null); if (state.active === cid) setActive(null, 'free'); }
    }
  }

  async function onCardClick(e, el, turn, cid) {
    const btn = e.target.closest('[data-a]');
    if (!btn) return;
    const status = el.querySelector('[data-f="status"]');
    const a = btn.dataset.a;
    try {
      if (a === 'edit-facts') { state.editFacts = cid; renderCardTurn(turn, state.cards[cid]); }
      else if (a === 'facts') {
        const answers = collectFacts(el, state.cards[cid]);
        if (!Object.keys(answers).length) {
          if (state.cards[cid].verification.complete) { state.editFacts = null; renderCardTurn(turn, state.cards[cid]); }
          else status.textContent = 'Hãy điền hoặc xác nhận các mục bắt buộc.';
          return;
        }
        state.cards[cid] = await post(`/${cid}/facts`, { answers });
        if (state.cards[cid].verification.complete) state.editFacts = null;
        renderCardTurn(turn, state.cards[cid]);
      }
      else if (a === 'save') { state.cards[cid] = await post(`/${cid}/save`); setSavedIds([...savedIds(), cid]); renderCardTurn(turn, state.cards[cid]); }
      else if (a === 'remove') {
        await fetch(`${API}/${cid}`, { method: 'DELETE' });
        setSavedIds(savedIds().filter(x => x !== cid));
        delete state.cards[cid];
        renderCardTurn(turn, null);
        if (state.active === cid) setActive(null, 'free');
      }
      else if (a === 'ask') { setActive(cid, 'contract'); document.getElementById('main-query-input').focus(); }
    } catch (err) {
      if (err.status === 404) { renderCardTurn(turn, null); return; }
      if (err.status === 409) { await refreshCard(el, turn, cid); }
      const st = el.querySelector('[data-f="status"]');
      if (st) st.textContent = '⚠ ' + err.message;
    }
  }

  // Lượt báo cáo của luồng soát cũ (đã gỡ) còn trong phiên chat đã lưu: chỉ ghi chú, không dựng lại báo cáo.
  function renderLegacyReportTurn(turn) {
    const el = document.createElement('div');
    el.id = turn.turnId;
    el.innerHTML = `<div class="border border-neutral-200 rounded-2xl p-4 text-[13px] bg-neutral-50 text-neutral-500">
      Báo cáo của luồng soát cũ — không còn hiển thị. Hãy kiểm tra lại hợp đồng ở trang <a href="/contract-studio/" class="underline">Soát hợp đồng</a>.</div>`;
    document.getElementById('chat-thread-view').appendChild(el);
  }

  // ------------------------------------------------------------------ chế độ hỏi
  function setActive(cid, mode) {
    state.active = cid;
    state.mode = cid ? mode : 'free';
    renderModeBar();
  }

  function renderModeBar() {
    const bar = document.getElementById('contract-mode-bar');
    if (!bar) return;
    const ids = sessionContractIds(currentSession()).filter(id => state.cards[id]);
    if (!ids.length) { bar.classList.add('hidden'); bar.innerHTML = ''; state.mode = 'free'; return; }
    if (!state.active || !ids.includes(state.active)) state.active = ids[ids.length - 1];
    const chip = (on, label, attrs) => `<button type="button" ${attrs} class="rounded-full px-3 py-1 border text-[12.5px] ${on ? 'bg-neutral-900 text-white border-neutral-900' : 'border-neutral-300 hover:bg-neutral-100'}">${label}</button>`;
    const select = ids.length > 1 ? `<select data-a="pick" class="border border-neutral-300 rounded-md text-[12.5px] px-1 py-0.5 max-w-[11rem]">${ids.map(id => `<option value="${esc(id)}" ${id === state.active ? 'selected' : ''}>${esc(state.cards[id].filename)}</option>`).join('')}</select>` : '';
    bar.classList.remove('hidden');
    bar.innerHTML = chip(state.mode === 'free', 'Hỏi tự do', 'data-a="free"')
      + chip(state.mode === 'contract', 'Hỏi với hợp đồng: ' + esc(state.cards[state.active].filename), 'data-a="contract"') + select;
    bar.onclick = e => { const a = e.target.closest('[data-a]')?.dataset.a; if (a === 'free') setActive(state.active, 'free'); if (a === 'contract') setActive(state.active, 'contract'); };
    bar.onchange = e => { if (e.target.dataset.a === 'pick') setActive(e.target.value, 'contract'); };
  }

  async function onSessionLoaded(sess) {
    state.mode = 'free';
    for (const id of sessionContractIds(sess)) {
      if (state.cards[id]) continue;
      try { state.cards[id] = await api('/' + encodeURIComponent(id)); } catch (e) { /* hết phiên */ }
    }
    renderModeBar();
  }

  function renderTurn(turn) {
    if (turn.kind === 'contract_card') {
      const card = state.cards[turn.contract_id];
      renderCardTurn(turn, card || null);
      if (!card) {
        const el = document.getElementById(turn.turnId);
        refreshCard(el, turn, turn.contract_id);
      }
    } else if (turn.kind === 'contract_report') {
      renderLegacyReportTurn(turn);
    }
  }

  function forgetSession(sess) {
    for (const id of sessionContractIds(sess)) {
      const card = state.cards[id];
      if (card && !card.persist) fetch(`${API}/${encodeURIComponent(id)}`, { method: 'DELETE' }).catch(() => {});
      delete state.cards[id];
    }
  }

  function requestContract() {
    if (state.mode !== 'contract' || !state.active || !state.cards[state.active]) return null;
    return { id: state.active, label: state.cards[state.active].filename };
  }

  window.ContractUI = { openPlusMenu, openAttach, renderTurn, onSessionLoaded, forgetSession, requestContract, renderModeBar };
})();
