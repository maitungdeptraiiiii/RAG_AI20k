// Phần 4 — đính kèm hợp đồng trong chat (spec 2026-11-11-contract-review-design.md).
// Dùng các biến / hàm toàn cục của index.html: chatSessions, currentSessionId, saveSessionsToStorage,
// renderRecentsList, setChatInputPosition, escapeHtml, scrollToBottom, toggleIngestModal.
(function () {
  const API = '/api/contracts';
  const LS_SAVED = 'justice_saved_contracts_v1';
  const GONE = 'Hợp đồng này đã hết phiên — hãy đính kèm lại';
  const OPS = [
    ['summary', 'Tóm tắt'], ['review', 'Soát toàn bộ'], ['partial', 'Soát một phần'],
    ['law_changes', 'Đối chiếu thay đổi của luật'], ['redline', 'Đề xuất sửa'], ['ask', 'Hỏi về hợp đồng này'],
  ];
  const TOPICS = ['Phạt vi phạm', 'Chấm dứt hợp đồng', 'Thanh toán', 'Bồi thường', 'Bảo hành / sửa chữa',
    'Giải quyết tranh chấp', 'Đặt cọc'];
  const GROUP = { illegal: 'Trái luật', missing_required: 'Thiếu nội dung bắt buộc', unfavorable: 'Bất lợi',
    ambiguous: 'Mơ hồ / dễ tranh chấp' };
  const SEV = { critical: ['Nghiêm trọng', '#b42318', '#fef3f2'], major: ['Cần sửa', '#8a5a00', '#fffaf0'],
    minor: ['Lưu ý', '#475467', '#f2f4f7'] };
  const STATUS = { concluded: ['Có căn cứ — kho luật có phiên bản', '#006300'], conditional: ['Có điều kiện — kho cũ', '#8a5a00'],
    cannot_conclude: ['Chưa thể kết luận', '#b42318'], blocked_no_date: ['Chưa có ngày ký', '#8a5a00'],
    not_legal: ['Nhận xét câu chữ / thương mại', '#475467'] };
  const CHANGE = { unchanged: 'Không đổi', changed: 'Đã sửa đổi', repealed: 'Hết hiệu lực', untracked: 'Không theo dõi được (kho cũ)' };

  const state = { cards: {}, active: null, mode: 'free' };
  const esc = s => escapeHtml(String(s ?? ''));
  const day = iso => iso ? iso.slice(0, 10).split('-').reverse().join('/') : '—';

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
    const parties = (c.facts && c.facts.parties) || [];
    const cov = c.coverage || {};
    const partyBtn = (val, label) => `<button type="button" data-a="party" data-v="${esc(val)}"
        class="text-[12.5px] border rounded-full px-3 py-1 ${c.party === val ? 'bg-neutral-900 text-white border-neutral-900' : 'border-neutral-300 hover:bg-neutral-100'}">${esc(label)}</button>`;
    return `
      <div class="border border-neutral-200 rounded-2xl p-4 space-y-3 bg-white">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <div class="min-w-0"><div class="text-[14.5px] font-semibold truncate">📎 ${esc(c.filename)}</div>
            <div class="text-[12px] text-neutral-500">${esc((c.facts && c.facts.type) || 'chưa rõ loại')} · ${cov.reviewed}/${cov.total} điều khoản${cov.reviewed < cov.total ? ' (bản demo chỉ soát ' + cov.reviewed + ' đầu)' : ''} · ${c.persist ? 'Đã lưu' : 'Chỉ trong phiên này'}</div></div>
          <div class="flex gap-2 text-[12.5px]">
            ${c.persist ? '' : '<button type="button" data-a="save" class="text-blue-600 hover:underline">Lưu hợp đồng này</button>'}
            <button type="button" data-a="remove" class="text-neutral-500 hover:text-red-700">Gỡ</button></div>
        </div>
        ${c.facts && c.facts.error ? `<div class="text-[12.5px]" style="color:#8a5a00">⚠ Chưa trích được thông tin nền: ${esc(c.facts.error)}</div>` : ''}
        <div><div class="text-[12px] text-neutral-500 mb-1">Bạn là bên nào?</div>
          <div class="flex flex-wrap gap-1.5">${parties.map(p => partyBtn(p.role, 'Tôi là ' + p.role)).join('')}${partyBtn('neutral', 'Trung lập / tư vấn')}</div>
          ${c.party ? '' : '<div class="text-[11.5px] mt-1" style="color:#8a5a00">Chưa chọn bên — AI soát ở chế độ Trung lập.</div>'}</div>
        <div class="flex flex-wrap items-center gap-2 text-[12.5px]">
          <span class="text-neutral-500">Ngày ký (mốc pháp lý):</span>
          <input type="date" data-f="sign" value="${esc(c.sign_date || '')}" class="border border-neutral-300 rounded-md px-1.5 py-0.5">
          <button type="button" data-a="sign" class="text-blue-600 hover:underline">Lưu ngày</button>
          <span class="text-neutral-400">${c.sign_date ? (c.sign_date_source === 'user' ? 'bạn nhập' : 'đọc từ hợp đồng') : '<span style="color:#b42318">chưa có — phần pháp lý sẽ bị chặn</span>'}</span>
        </div>
        <div class="flex flex-wrap gap-1.5">${OPS.map(([op, label]) => `<button type="button" data-a="op" data-op="${op}"
            class="text-[13px] border border-neutral-300 rounded-lg px-3 py-1.5 hover:bg-neutral-100">${label}</button>`).join('')}</div>
        <div data-f="partial" class="hidden border-t pt-3 space-y-2 text-[12.5px]">
          <div class="text-neutral-500">Chọn điều khoản hoặc chủ đề cần soát:</div>
          <div class="flex flex-wrap gap-x-3 gap-y-1 max-h-40 overflow-y-auto">${(c.units || []).map(u => `<label class="flex gap-1"><input type="checkbox" data-unit="${esc(u.uid)}"> ${esc(u.label)}</label>`).join('')}</div>
          <div class="flex flex-wrap gap-x-3 gap-y-1">${TOPICS.map(t => `<label class="flex gap-1"><input type="checkbox" data-topic="${esc(t)}"> ${esc(t)}</label>`).join('')}</div>
          <button type="button" data-a="run-partial" class="bg-neutral-900 text-white rounded-lg px-3 py-1.5">Soát phần đã chọn</button>
        </div>
        <div data-f="status" class="text-[12.5px] text-neutral-500" role="status" aria-live="polite"></div>
      </div>`;
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
      if (a === 'party') { state.cards[cid] = await post(`/${cid}/party`, { party: btn.dataset.v }); renderCardTurn(turn, state.cards[cid]); }
      else if (a === 'sign') {
        const v = el.querySelector('[data-f="sign"]').value;
        if (!v) { status.textContent = 'Hãy chọn ngày ký.'; return; }
        state.cards[cid] = await post(`/${cid}/sign-date`, { date: v }); renderCardTurn(turn, state.cards[cid]);
      }
      else if (a === 'save') { state.cards[cid] = await post(`/${cid}/save`); setSavedIds([...savedIds(), cid]); renderCardTurn(turn, state.cards[cid]); }
      else if (a === 'remove') {
        await fetch(`${API}/${cid}`, { method: 'DELETE' });
        setSavedIds(savedIds().filter(x => x !== cid));
        delete state.cards[cid];
        renderCardTurn(turn, null);
        if (state.active === cid) setActive(null, 'free');
      }
      else if (a === 'op') {
        const op = btn.dataset.op;
        if (op === 'partial') { el.querySelector('[data-f="partial"]').classList.toggle('hidden'); return; }
        if (op === 'ask') { setActive(cid, 'contract'); document.getElementById('main-query-input').focus(); return; }
        await runOp(el, cid, { op });
      }
      else if (a === 'run-partial') {
        const unit_ids = [...el.querySelectorAll('[data-unit]:checked')].map(x => x.dataset.unit);
        const topics = [...el.querySelectorAll('[data-topic]:checked')].map(x => x.dataset.topic);
        if (!unit_ids.length && !topics.length) { status.textContent = 'Hãy chọn ít nhất một điều khoản hoặc chủ đề.'; return; }
        await runOp(el, cid, { op: 'partial', unit_ids, topics });
      }
    } catch (err) {
      if (err.status === 404) { renderCardTurn(turn, null); return; }
      status.textContent = '⚠ ' + err.message;
    }
  }

  async function runOp(el, cid, body) {
    const status = el.querySelector('[data-f="status"]');
    const label = (OPS.find(o => o[0] === body.op) || [0, 'Thao tác'])[1];
    el.querySelectorAll('button').forEach(b => b.disabled = true);
    status.innerHTML = `<span class="animate-pulse">AI đang ${esc(label.toLowerCase())}…</span>`;
    try {
      const report = await post(`/${cid}/run`, body);
      status.textContent = '';
      const turn = { turnId: 'ctr-' + Date.now(), kind: 'contract_report', contract_id: cid, report, timestamp: Date.now() };
      pushTurn(turn);
      renderReportTurn(turn);
      scrollToBottom();
    } finally {
      el.querySelectorAll('button').forEach(b => b.disabled = false);
    }
  }

  // ------------------------------------------------------------------ báo cáo
  function evidenceHtml(e) {
    const when = e.store === 'versioned'
      ? `hiệu lực ${day(e.valid_from)} → ${e.valid_to ? day(e.valid_to) : 'nay'} · ${esc(e.status)}`
      : 'Kho cũ — chưa xác định phiên bản';
    return `<div class="text-[12px] border-l-2 border-neutral-300 pl-2"><span class="font-medium">${esc(e.source_title)}</span> — ${esc(e.section)}
      <span class="text-neutral-500">(${when})</span><div class="text-neutral-500 line-clamp-2">${esc((e.text || '').slice(0, 260))}</div></div>`;
  }

  function findingHtml(f, i) {
    const sev = SEV[f.severity] || SEV.minor;
    const st = STATUS[f.legal_status] || ['', '#475467'];
    const refusal = f.refusal ? `<div class="text-[12.5px]" style="color:#b42318">${esc(f.refusal).replace('/upload', '<a href="/upload" class="underline">/upload</a>')}</div>` : '';
    return `<div class="border border-neutral-200 rounded-xl p-3 space-y-1.5">
      <div class="flex flex-wrap items-center gap-2 text-[12.5px]"><span class="font-semibold">${i}. ${esc(f.unit_label)}</span>
        <span class="rounded-full px-2 py-0.5" style="color:${sev[1]};background:${sev[2]}">${sev[0]}</span>
        <span class="text-neutral-600">${esc(GROUP[f.group] || f.group)}</span>
        ${f.disadvantaged ? `<span class="text-neutral-500">· bất lợi cho ${esc(f.disadvantaged)}</span>` : ''}</div>
      ${f.quote ? `<blockquote class="text-[13px] italic border-l-2 border-neutral-300 pl-2 text-neutral-700">“${esc(f.quote)}”</blockquote>`
        : (f.needs_check ? '<div class="text-[12px]" style="color:#8a5a00">Trích dẫn không khớp hợp đồng — cần kiểm tra lại.</div>' : '')}
      <div class="text-[13.5px]">${esc(f.explanation)}</div>
      <div class="text-[12px] font-medium" style="color:${st[1]}">${esc(st[0])}</div>
      ${(f.evidence || []).map(evidenceHtml).join('')}${refusal}
      ${f.note ? `<div class="text-[12px] text-neutral-500">${esc(f.note)}</div>` : ''}
      ${f.suggestion ? `<div class="text-[13px]"><span class="text-neutral-500">Gợi ý sửa:</span> ${esc(f.suggestion)}</div>` : ''}
    </div>`;
  }

  function reportBody(r) {
    if (r.op === 'summary') {
      return (r.sections || []).map(s => `<div><div class="text-[13.5px] font-semibold mb-1">${esc(s.title)}</div><ul class="list-disc pl-5 text-[13.5px] space-y-0.5">
        ${s.items.map(it => `<li>${esc(it.text)}${it.unit_label ? ` <span class="text-neutral-400">(${esc(it.unit_label)})</span>` : ''}</li>`).join('')}</ul></div>`).join('');
    }
    if (r.op === 'review' || r.op === 'partial') {
      const f = r.findings || [];
      return (r.op === 'partial' ? `<div class="text-[12.5px] text-neutral-500">Phạm vi: ${esc((r.scope || []).join(', ') || '—')}</div>` : '')
        + (f.length ? f.map((x, i) => findingHtml(x, i + 1)).join('') : '<div class="text-[13.5px]">Không phát hiện vấn đề trong phạm vi đã soát.</div>');
    }
    if (r.op === 'law_changes') {
      const rows = r.changes || [];
      if (!rows.length) return '<div class="text-[13.5px]">Chưa có căn cứ luật nào để đối chiếu.</div>';
      return `<div class="overflow-x-auto"><table class="w-full text-[12.5px] border-collapse"><thead><tr class="text-left text-neutral-500">
        <th class="p-1.5 border-b">Căn cứ tại ngày ký</th><th class="p-1.5 border-b">Hiện nay</th><th class="p-1.5 border-b">Chi tiết</th><th class="p-1.5 border-b">Điều khoản bị ảnh hưởng</th></tr></thead><tbody>
        ${rows.map(x => `<tr class="align-top"><td class="p-1.5 border-b">${esc(x.source_title)} — ${esc(x.section)}</td>
          <td class="p-1.5 border-b font-medium" style="color:${x.status === 'repealed' ? '#b42318' : x.status === 'changed' ? '#8a5a00' : '#344054'}">${esc(CHANGE[x.status] || x.status)}</td>
          <td class="p-1.5 border-b">${x.replaced_by ? `Thay bởi ${esc(x.replaced_by.title)} từ ${day(x.replaced_from)}${(x.transition_articles || []).length ? '; Điều chuyển tiếp: ' + esc(x.transition_articles.map(t => t.article).join(', ')) : ''}` : x.status === 'changed' ? `Nội dung mới từ ${day(x.current_from)}` : ''}</td>
          <td class="p-1.5 border-b">${esc((x.affected_units || []).join(', '))}</td></tr>`).join('')}</tbody></table></div>`;
    }
    if (r.op === 'redline') {
      const rows = r.redlines || [];
      if (!rows.length) return '<div class="text-[13.5px]">Không có điều khoản cần sửa.</div>';
      return rows.map(x => `<div class="border border-neutral-200 rounded-xl p-3 space-y-1.5 text-[13px]">
        <div class="font-semibold">${esc(x.unit_label)}${x.legal_note ? ` <span class="text-[12px] font-normal" style="color:#8a5a00">· ${esc(x.legal_note)}</span>` : ''}</div>
        <div class="grid sm:grid-cols-2 gap-2">
          <div class="rounded-lg p-2" style="background:#fef3f2"><div class="text-[11.5px] text-neutral-500">Hiện tại${x.old_ok ? '' : ' (không khớp hợp đồng)'}</div><del>${esc(x.old)}</del></div>
          <div class="rounded-lg p-2" style="background:#ecfdf3"><div class="text-[11.5px] text-neutral-500">Đề xuất</div><ins class="no-underline">${esc(x.new)}</ins></div></div>
        <div class="text-neutral-600">${esc(x.reason)}</div></div>`).join('');
    }
    return '';
  }

  const TITLE = { summary: 'Tóm tắt hợp đồng', review: 'Báo cáo soát toàn bộ', partial: 'Báo cáo soát một phần',
    law_changes: 'Đối chiếu thay đổi của luật', redline: 'Đề xuất sửa' };

  function renderReportTurn(turn) {
    const r = turn.report, cid = turn.contract_id;
    const thread = document.getElementById('chat-thread-view');
    const el = document.createElement('div');
    el.id = turn.turnId;
    const cov = r.coverage || {};
    const party = r.party && r.party !== 'neutral' ? r.party : 'Trung lập';
    el.innerHTML = `<div class="border border-neutral-200 rounded-2xl p-4 space-y-3 bg-white">
      <div class="flex flex-wrap items-center justify-between gap-2">
        <div><div class="text-[14.5px] font-semibold">${esc(TITLE[r.op] || 'Báo cáo')}</div>
          <div class="text-[12px] text-neutral-500">${esc((state.cards[cid] || {}).filename || '')} · góc nhìn: ${esc(party)} · mốc: ${day(r.anchor)} · Đã soát ${cov.reviewed}/${cov.total} điều khoản</div></div>
        ${r.op === 'summary' ? '' : `<div class="flex gap-2 text-[12.5px]">
          <a href="${API}/${encodeURIComponent(cid)}/reports/${encodeURIComponent(r.rid)}.docx" class="border border-neutral-300 rounded-lg px-2.5 py-1 hover:bg-neutral-100">Tải Word</a>
          <a href="${API}/${encodeURIComponent(cid)}/reports/${encodeURIComponent(r.rid)}.pdf" class="border border-neutral-300 rounded-lg px-2.5 py-1 hover:bg-neutral-100">Tải PDF</a></div>`}
      </div>
      <div class="space-y-2">${reportBody(r)}</div>
      <div class="text-[11.5px] text-neutral-400">Báo cáo do AI tạo để tham khảo. Không thay thế tư vấn pháp lý.</div></div>`;
    thread.appendChild(el);
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
      renderReportTurn(turn);
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
