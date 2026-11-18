// Trang /contracts — soát hợp đồng từng bước: ① Nạp → ② Dữ kiện → ③ Soát.
// Độc lập với plugin hợp đồng trong chat (contracts.js); chỉ dùng chung API /api/contracts.
(function () {
  'use strict';
  const API = '/api/contracts';
  const LS_SAVED = 'ctpage.saved';

  const STEPS = [[1, 'Nạp hợp đồng'], [2, 'Xác minh dữ kiện'], [3, 'Soát']];
  const FACT = { found: ['Máy đọc được — chờ bạn xác nhận', '#475467'], conflict: ['Hợp đồng ghi nhiều giá trị khác nhau — hãy chọn', '#b42318'],
    missing: ['Không tìm thấy trong hợp đồng', '#8a5a00'], confirmed: ['Đã xác nhận', '#006300'],
    corrected: ['Bạn đã sửa', '#006300'], unknown: ['Bạn không biết', '#475467'] };
  const USER_FACTS = [
    ['employee_is_female', 'Người lao động là nữ', 'bool'], ['pregnant', 'Đang mang thai', 'bool'],
    ['pregnancy_month', 'Tháng thai kỳ', 'number'], ['child_under_12_months', 'Nuôi con dưới 12 tháng', 'bool'],
    ['employee_consent', 'Người lao động đồng ý', 'bool'], ['medical_certificate', 'Có giấy xác nhận y tế', 'bool'],
    ['wage_region', 'Vùng lương tối thiểu', 'region'], ['work_condition', 'Điều kiện làm việc', 'text'],
  ];
  const FINDING = { violation: 'Vi phạm', missing_content: 'Thiếu nội dung bắt buộc', hidden_right: 'Quyền mà hợp đồng không nhắc',
    conflict: 'Mâu thuẫn trong hợp đồng', possible_right: 'Có thể có quyền (cần thêm thông tin về bạn)', needs_facts: 'Cần thêm dữ kiện' };
  const FINDING_ORDER = ['violation', 'missing_content', 'hidden_right', 'conflict', 'possible_right', 'needs_facts'];
  const GROUP = { illegal: 'Trái luật', missing_required: 'Thiếu nội dung bắt buộc', unfavorable: 'Bất lợi', ambiguous: 'Mơ hồ / dễ tranh chấp' };
  const SEV = { critical: ['Nghiêm trọng', '#b42318', '#fef3f2'], major: ['Cần sửa', '#8a5a00', '#fffaf0'], minor: ['Lưu ý', '#475467', '#f2f4f7'] };

  const state = { card: null, step: 1, userFacts: {}, running: false, result: null, review: null, error: '',
    progress: null, partial: null, filter: '', open: new Set(), savedAt: null, stale: false };
  const $ = id => document.getElementById(id);
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const day = iso => iso ? iso.slice(0, 10).split('-').reverse().join('/') : '—';
  const when = iso => { try { return new Date(iso).toLocaleString('vi-VN', { dateStyle: 'short', timeStyle: 'short' }); } catch (e) { return day(iso); } };

  function savedIds() { try { return JSON.parse(localStorage.getItem(LS_SAVED) || '[]'); } catch (e) { return []; } }
  function setSavedIds(ids) { try { localStorage.setItem(LS_SAVED, JSON.stringify([...new Set(ids)].slice(0, 50))); } catch (e) { /* bỏ qua */ } }

  async function api(path, opts = {}) {
    const res = await fetch(API + path, opts);
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const err = new Error(data.error || `Lỗi server (${res.status})`);
      err.status = res.status; err.pending = data.pending || null;
      throw err;
    }
    return data;
  }
  const post = (path, body) => api(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) });

  function notice(msg) {
    const el = $('notice');
    el.textContent = msg || '';
    el.classList.toggle('hidden', !msg);
  }

  // ------------------------------------------------------------------ stepper
  function unlocked(n) {
    if (n === 1) return true;
    if (!state.card) return false;
    return n === 2 || (state.card.verification && state.card.verification.complete);
  }

  function goStep(n) {
    if (!unlocked(n)) return;
    state.step = n;
    render();
  }

  function renderStepper() {
    $('stepper').innerHTML = STEPS.map(([n, label], i) => {
      const done = n < state.step || (n === 1 && state.card) || (n === 2 && unlocked(3));
      const cls = ['step', 'flex items-center gap-2 text-[13px]', n === state.step ? 'on' : '', done && n !== state.step ? 'done' : '',
        unlocked(n) ? 'cursor-pointer' : 'locked'].join(' ');
      return `<button type="button" data-step="${n}" class="${cls}"><span class="step-dot">${done && n !== state.step ? '✓' : n}</span>
        <span class="${n === state.step ? 'font-semibold' : ''}">${esc(label)}</span></button>${i < STEPS.length - 1 ? '<span class="text-neutral-300">—</span>' : ''}`;
    }).join('');
  }

  function render() {
    renderStepper();
    [1, 2, 3].forEach(n => $('step-' + n).classList.toggle('hidden', n !== state.step));
    if (state.step === 1) renderStep1();
    else if (state.step === 2) renderStep2();
    else renderStep3();
  }

  function setCard(card) {
    state.card = card;
    state.result = null; state.review = null; state.progress = null; state.partial = null; state.open.clear();
    state.savedAt = null; state.stale = false;
  }

  // ------------------------------------------------------------------ ① Nạp
  function cardSummary(c) {
    const g = c.graph || {};
    const graphNote = g.enabled && !g.published
      ? `<div class="text-[12.5px]" style="color:#8a5a00">Đồ thị chưa cập nhật: ${esc(g.error || (g.problems || [])[0] || '')}</div>` : '';
    return `<div class="border border-neutral-200 rounded-xl p-3 space-y-1">
      <div class="text-[13.5px] font-semibold">${esc(c.filename)}</div>
      <div class="text-[12.5px] text-neutral-500">${(c.units || []).length} điều khoản · tạo ${day(c.created_at)}${c.sign_date ? ' · ký ' + day(c.sign_date) : ''}</div>
      ${graphNote}
      ${c.last_check ? `<button type="button" data-view-last="${esc(c.contract_id)}" class="btn-ghost mt-1">Xem kết quả kiểm tra concept (${esc(when(c.last_check.checked_at))})</button>` : ''}</div>`;
  }

  async function renderStep1() {
    const el = $('step-1');
    el.innerHTML = `<div class="text-[14px] font-semibold mb-2">① Nạp hợp đồng</div>
      <div class="text-[12.5px] text-neutral-500 mb-3">PDF, DOCX, TXT hoặc ảnh scan, tối đa 50 MB. Hợp đồng không đi vào kho tra cứu luật.</div>
      <div id="drop" class="border-2 border-dashed border-neutral-300 rounded-xl p-6 text-center text-[13px] text-neutral-500">
        <input type="file" id="file" accept=".pdf,.docx,.txt,.md,.png,.jpg,.jpeg,.tif,.tiff,.webp" class="block mx-auto mb-2">
        <label class="flex items-center justify-center gap-1.5 text-[12.5px]"><input type="checkbox" id="persist"> Lưu để mở lại sau</label>
      </div>
      <div class="flex items-center gap-3 mt-3"><button type="button" id="go" class="btn">Đọc hợp đồng</button><span id="status" class="text-[12.5px] text-neutral-500"></span></div>
      <div id="current" class="mt-4">${state.card ? cardSummary(state.card) : ''}</div>
      ${state.card ? '<button type="button" id="next" class="btn mt-3">Tiếp tục: xác minh dữ kiện →</button>' : ''}
      <div id="saved" class="mt-5"></div>`;
    const ids = savedIds();
    if (!ids.length) return;
    try {
      const list = (await api('?ids=' + encodeURIComponent(ids.join(',')))).contracts || [];
      setSavedIds(list.map(c => c.contract_id));      // bỏ hợp đồng đã xóa / hết phiên
      if (!list.length || state.step !== 1) return;
      $('saved').innerHTML = `<div class="text-[12.5px] font-semibold mb-1.5">Hợp đồng đã lưu</div><div class="space-y-1.5">${list.map(c => `
        <div class="flex items-center justify-between border border-neutral-200 rounded-lg px-3 py-1.5">
          <span class="text-[13px] truncate">${esc(c.filename)} <span class="text-neutral-400">· ${day(c.created_at)}</span></span>
          <span class="flex gap-1.5 flex-shrink-0">${c.last_check ? `<button type="button" data-view-last="${esc(c.contract_id)}" class="btn-ghost">Xem kết quả</button>` : ''}
            <button type="button" data-open="${esc(c.contract_id)}" class="btn-ghost">Mở</button></span></div>`).join('')}</div>`;
    } catch (e) { /* danh sách đã lưu chỉ là tiện ích */ }
  }

  async function upload() {
    const file = $('file').files[0];
    const status = $('status');
    if (!file) { status.textContent = 'Hãy chọn file hợp đồng.'; return; }
    const fd = new FormData();
    fd.append('file', file);
    fd.append('persist', $('persist').checked ? '1' : '0');
    status.textContent = 'Đang đọc hợp đồng và trích thông tin…';
    $('go').disabled = true;
    try {
      const res = await fetch(API, { method: 'POST', body: fd });
      const card = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(card.error || `Lỗi server (${res.status})`);
      if (card.persist) setSavedIds([card.contract_id, ...savedIds()]);
      notice('');
      setCard(card);
      state.step = 2;
      render();
    } catch (e) {
      status.textContent = e.message;
      $('go').disabled = false;
    }
  }

  async function openSaved(cid, toReview = false) {
    try {
      setCard(await api('/' + encodeURIComponent(cid)));
      notice('');
      state.step = toReview && unlocked(3) ? 3 : 2;
      render();
    } catch (e) {
      if (e.status === 404) setSavedIds(savedIds().filter(i => i !== cid));
      notice(e.status === 404 ? 'Hợp đồng này đã hết phiên — hãy nạp lại.' : e.message);
      state.card = null;
      state.step = 1;
      render();
    }
  }

  // Xem lại kết quả Kiểm tra concept đã lưu (không gọi LLM, không chạy lại).
  async function viewLast(cid) {
    if (state.running) return;
    try {
      if (!state.card || state.card.contract_id !== cid) setCard(await api('/' + encodeURIComponent(cid)));
      const saved = await api(`/${encodeURIComponent(cid)}/concept-check/last`);
      state.result = saved; state.progress = null; state.partial = null; state.filter = '';
      state.savedAt = saved.checked_at; state.stale = !!saved.stale; state.error = '';
      notice('');
      state.step = 3;
      render();
    } catch (e) { notice(e.message); }
  }

  // ------------------------------------------------------------------ ② Dữ kiện
  function unitLabel(c, uid) { return ((c.units || []).find(u => u.uid === uid) || {}).label || ''; }

  function factInput(f) {
    const cls = 'max-w-full';
    const dis = f.status === 'unknown' ? 'disabled' : '';
    const choices = (f.options && f.options.length) ? f.options
      : (f.candidates || []).length > 1 ? f.candidates.map(x => x.value) : null;
    if (choices) {
      const label = v => (f.option_labels && f.option_labels[v]) || v;
      return `<select data-fact="${esc(f.key)}" class="${cls}" ${dis}><option value="">— chọn —</option>
        ${choices.map(v => `<option value="${esc(v)}" ${v === f.value ? 'selected' : ''}>${esc(label(v))}</option>`).join('')}</select>`;
    }
    return `<input type="${f.kind === 'date' ? 'date' : 'text'}" data-fact="${esc(f.key)}" value="${esc(f.value || '')}" class="${cls} w-56" ${dis}>`;
  }

  function factRow(c, f) {
    const st = FACT[f.status] || ['', '#475467'];
    const cands = (f.candidates || []).length > 1
      ? `<div class="text-[11.5px] text-neutral-500">${f.candidates.map(x => `“${esc(x.quote || x.value)}” (${esc(unitLabel(c, x.unit))})`).join(' · ')}</div>`
      : (f.quote ? `<div class="text-[11.5px] text-neutral-500 italic">“${esc(f.quote)}”${f.unit ? ` <span class="not-italic">(${esc(unitLabel(c, f.unit))})</span>` : ''}</div>` : '');
    const canUnknown = !['party', 'sign_date'].includes(f.key);
    return `<tr class="align-top border-b border-neutral-100">
      <td class="py-1.5 pr-3 text-[12.5px] whitespace-nowrap">${esc(f.label)}${f.required ? ' <span style="color:#b42318">*</span>' : ''}</td>
      <td class="py-1.5 pr-3">${factInput(f)}${cands}</td>
      <td class="py-1.5 text-[11.5px]"><div style="color:${st[1]}">${esc(st[0])}</div>
        ${canUnknown ? `<label class="flex gap-1 text-neutral-500"><input type="checkbox" data-unknown="${esc(f.key)}" ${f.status === 'unknown' ? 'checked' : ''}> không biết</label>` : ''}</td></tr>`;
  }

  function userFactInput([key, , kind]) {
    const v = state.userFacts[key];
    if (kind === 'bool') {
      return `<select data-user="${key}"><option value="">— bỏ trống —</option><option value="true" ${v === true ? 'selected' : ''}>Có</option><option value="false" ${v === false ? 'selected' : ''}>Không</option></select>`;
    }
    if (kind === 'region') {
      return `<select data-user="${key}"><option value="">— bỏ trống —</option>${['I', 'II', 'III', 'IV'].map(r => `<option ${v === r ? 'selected' : ''}>${r}</option>`).join('')}</select>`;
    }
    return `<input type="${kind === 'number' ? 'number' : 'text'}" data-user="${key}" value="${esc(v ?? '')}" class="w-40">`;
  }

  function renderStep2() {
    const c = state.card, v = c.verification;
    const el = $('step-2');
    if (!v) { el.innerHTML = '<div class="text-[13px]">Hợp đồng chưa có dữ kiện để xác minh.</div>'; return; }
    const cov = v.coverage && v.coverage.read < v.coverage.total
      ? `<div class="text-[12px]" style="color:#8a5a00">⚠ AI mới đọc ${v.coverage.read}/${v.coverage.total} điều khoản khi trích thông tin.</div>` : '';
    const warn = (v.warnings || []).map(w => `<div class="text-[12px]" style="color:#8a5a00">⚠ ${esc(w)}</div>`).join('');
    const required = v.fields.filter(f => f.required), other = v.fields.filter(f => !f.required);
    el.innerHTML = `<div class="text-[14px] font-semibold mb-1">② Xác minh dữ kiện</div>
      <div class="text-[12.5px] text-neutral-500 mb-3">AI đã đọc hợp đồng <b>${esc(c.filename)}</b> và điền sẵn. Kiểm tra từng dòng, sửa chỗ sai, chọn “không biết” nếu không rõ.
        Mục có <span style="color:#b42318">*</span> là bắt buộc trước khi Soát luật.</div>
      ${cov}${warn}
      <div class="overflow-x-auto"><table class="w-full"><tbody>${required.map(f => factRow(c, f)).join('')}</tbody></table></div>
      ${other.length ? `<details class="mt-2" ${v.complete ? '' : 'open'}><summary class="text-[12.5px] text-neutral-600 cursor-pointer">Thông tin nên xác nhận (${other.length})</summary>
        <div class="overflow-x-auto"><table class="w-full"><tbody>${other.map(f => factRow(c, f)).join('')}</tbody></table></div></details>` : ''}
      <div class="mt-4 border-t border-neutral-100 pt-3">
        <div class="text-[13px] font-semibold">Thông tin về người lao động <span class="font-normal text-neutral-500">(tùy chọn — dùng cho Kiểm tra concept)</span></div>
        <div class="grid sm:grid-cols-2 gap-x-6 gap-y-1.5 mt-2">${USER_FACTS.map(u => `<label class="flex items-center justify-between gap-2 text-[12.5px]"><span>${esc(u[1])}</span>${userFactInput(u)}</label>`).join('')}</div>
      </div>
      <div class="flex items-center gap-3 mt-4">
        <button type="button" id="confirm" class="btn">Xác nhận thông tin</button>
        <span id="status2" class="text-[12.5px]" style="color:#8a5a00">${v.pending.length ? 'Còn thiếu: ' + esc(v.pending.map(p => p.label).join(', ')) : ''}</span>
        ${unlocked(3) ? '<button type="button" id="to3" class="btn-ghost">Sang bước Soát →</button>' : ''}
        ${c.last_check ? `<button type="button" data-view-last="${esc(c.contract_id)}" class="btn-ghost">Xem lại kết quả kiểm tra (${esc(when(c.last_check.checked_at))})</button>` : ''}</div>`;
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

  function collectUserFacts(el) {
    const out = {};
    for (const [key, , kind] of USER_FACTS) {
      const input = el.querySelector(`[data-user="${key}"]`);
      const raw = input ? input.value.trim() : '';
      if (!raw) continue;
      out[key] = kind === 'bool' ? raw === 'true' : kind === 'number' ? Number(raw) : raw;
    }
    return out;
  }

  async function confirmFacts() {
    const el = $('step-2');
    state.userFacts = collectUserFacts(el);
    const answers = collectFacts(el, state.card);
    const status = $('status2');
    $('confirm').disabled = true;
    try {
      if (Object.keys(answers).length) setCard(await post(`/${state.card.contract_id}/facts`, { answers }));
      render();
      if (unlocked(3)) { state.step = 3; render(); }
    } catch (e) {
      status.textContent = e.message;
      $('confirm').disabled = false;
    }
  }

  // ------------------------------------------------------------------ ③ Soát
  function download(name, text, type) {
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([text], { type }));
    a.download = name;
    a.click();
    URL.revokeObjectURL(a.href);
  }

  const PIPE = [['facts', 'Đọc hợp đồng'], ['tag', 'Gán khái niệm'], ['evaluate', 'Đánh giá'], ['recheck', 'Kiểm lại'], ['basis', 'Căn cứ luật']];

  function progressHtml() {
    const p = state.progress;
    if (!p) return '';
    const finished = !!state.result;
    return `<div class="flex flex-wrap items-center gap-x-3 gap-y-1.5 text-[12.5px]">${PIPE.map(([key, label]) => {
      const st = p[key];
      let icon = '<span class="text-neutral-300">○</span>', cls = 'text-neutral-400', text = label;
      if (st === 'done') { icon = '<span style="color:var(--good-text)">✔</span>'; cls = 'text-neutral-700'; }
      else if (st === 'start') { icon = '<span class="spin">⟳</span>'; cls = 'font-medium'; }
      else if (finished) { icon = '<span class="text-neutral-300">–</span>'; text += ' (không cần)'; }
      const n = key === 'tag' && p.tagTotal ? ` (${p.tagDone}/${p.tagTotal} lô)` : '';
      return `<span class="flex items-center gap-1 ${cls}">${icon} ${esc(text)}${n}</span>`;
    }).join('<span class="text-neutral-300">›</span>')}</div>`;
  }

  function itemKey(r) { return `${r.concept_id}/${r.rule_id}`; }

  function detailHtml(r) {
    const v = r.view;
    const contract = v.contract.length
      ? v.contract.map(c => `<blockquote class="italic border-l-2 border-neutral-300 pl-2 text-neutral-700">“${esc(c.quote)}” <span class="not-italic text-neutral-400">— ${esc(c.label)}</span></blockquote>`).join('')
      : '<div class="text-neutral-500">Không có điều khoản nào trong hợp đồng nhắc đến nội dung này.</div>';
    const values = v.law_values.length
      ? `<div><span class="text-neutral-500">Mức luật quy định:</span> ${v.law_values.map(x => `<b>${esc(x.text)}</b> <span class="text-[11px] text-neutral-400">${esc(x.key)}</span>`).join(' · ')}</div>` : '';
    const law = v.law.map(a => a.citation
      ? `<div class="rounded-lg p-2" style="background:#f7f7f8"><div class="font-medium">${esc(a.citation)}</div>${ContractQA.lawMeta(a)}
          ${a.text ? `<div class="text-[12.5px] text-neutral-700 whitespace-pre-wrap mt-1">${esc(a.text)}</div>` : ''}</div>`
      : `<div class="text-[12px] text-neutral-500">Căn cứ: ${esc(a.pid)} <span class="text-neutral-400">(chưa có lời văn — đồ thị luật chưa bật)</span></div>`).join('');
    const missing = v.missing.length
      ? `<div class="rounded-lg p-2" style="background:#fffaf0"><div style="color:var(--warning-text)">Cần thêm thông tin: ${esc(v.missing.join(', '))}</div>
          <button type="button" data-a="to-facts" class="text-[12.5px] underline mt-1">Bổ sung ở bước ②</button></div>` : '';
    return `<div class="space-y-3 text-[13px] pt-2 pl-5">
      <section><div class="field-label mb-0.5">Ý nghĩa với ${esc(v.holder || 'người lao động')}</div>
        <div class="font-medium">${esc(v.verdict)}</div>${v.meaning ? `<div class="text-neutral-600">${esc(v.meaning)}</div>` : ''}</section>
      <section><div class="field-label mb-0.5">Trong hợp đồng</div>${contract}</section>
      ${law || values ? `<section><div class="field-label mb-0.5">Luật</div><div class="space-y-1.5">${values}${law}</div></section>` : ''}
      ${missing}
      <div class="text-[11px] text-neutral-400">${esc(itemKey(r))}</div></div>`;
  }

  function itemHtml(r) {
    const key = itemKey(r);
    return `<details class="border border-neutral-200 rounded-xl px-3 py-2 bg-white" data-key="${esc(key)}" ${state.open.has(key) ? 'open' : ''}>
      <summary class="cursor-pointer list-none flex items-start gap-2"><span class="chev text-neutral-400">▸</span>
        <span><span class="text-[13.5px] font-medium">${esc(r.view.title)}</span>
        <span class="block text-[12.5px] text-neutral-500">${esc(r.view.verdict)}</span></span></summary>
      ${detailHtml(r)}</details>`;
  }

  function conceptReport() {
    const views = state.result ? state.result.views : state.partial;
    if (!views) return '';
    const count = {};
    views.forEach(r => { count[r.finding] = (count[r.finding] || 0) + 1; });
    const order = [...FINDING_ORDER, 'ok'];
    const title = k => k === 'ok' ? 'Không có vấn đề' : FINDING[k];
    const chips = order.filter(k => count[k]).map(k => `<button type="button" data-filter="${k}" class="chip ${state.filter === k ? 'chip-on' : ''}">${esc(title(k))}: ${count[k]}</button>`).join(' ');
    const groups = order.filter(k => count[k] && (!state.filter || state.filter === k)).map(k => {
      const rows = views.filter(r => r.finding === k);
      const body = `<div class="space-y-1.5 mt-1.5">${rows.map(itemHtml).join('')}</div>`;
      return k === 'ok' && state.filter !== 'ok'
        ? `<details data-key="group:ok" ${state.open.has('group:ok') ? 'open' : ''}><summary class="text-[13.5px] font-semibold cursor-pointer">${esc(title(k))} (${rows.length}) — bấm để xem</summary>${body}</details>`
        : `<div><div class="text-[13.5px] font-semibold">${esc(title(k))} (${rows.length})</div>${body}</div>`;
    }).join('');
    const report = state.result && state.result.report;
    return `<div class="space-y-3">
      <div class="flex flex-wrap items-center gap-2"><div class="text-[13.5px] font-semibold">Kết quả Kiểm tra concept${report ? ' · ngày áp luật ' + day(report.day) : ''}</div>
        ${state.result ? '' : '<span class="chip" style="color:var(--warning-text)">Sơ bộ — đang kiểm lại…</span>'}
        ${state.savedAt ? `<span class="chip">Kết quả đã lưu lúc ${esc(when(state.savedAt))}</span>` : ''}</div>
      ${state.savedAt && state.stale ? '<div class="text-[12.5px]" style="color:var(--warning-text)">⚠ Dữ kiện hợp đồng đã đổi sau lần kiểm tra này — bấm “Kiểm tra concept” để chạy lại với dữ kiện mới.</div>' : ''}
      <div class="flex flex-wrap gap-1.5">${chips}${state.filter ? ' <button type="button" data-filter="" class="text-[12px] underline text-neutral-500">Bỏ lọc</button>' : ''}</div>
      ${report ? (report.warnings || []).map(w => `<div class="text-[12.5px]" style="color:var(--warning-text)">⚠ ${esc(w)}</div>`).join('') : ''}
      ${groups || '<div class="text-[13.5px]">Không phát hiện vấn đề.</div>'}
      ${state.result ? `<div class="flex flex-wrap gap-2"><a class="btn" href="/contracts/ask?cid=${encodeURIComponent(state.card.contract_id)}">Hỏi về hợp đồng này →</a><button type="button" data-dl="md" class="btn-ghost">Tải report.md</button><button type="button" data-dl="json" class="btn-ghost">Tải report.json</button></div>` : ''}</div>`;
  }

  async function refreshCard() {      // sau khi kiểm tra xong: thẻ mang last_check mới
    try { const keep = state.result; state.card = await api('/' + encodeURIComponent(state.card.contract_id)); state.result = keep; } catch (e) { /* không chặn kết quả */ }
  }

  async function runConceptStream() {
    state.progress = {}; state.partial = null; state.result = null; state.filter = ''; state.savedAt = null; state.stale = false;
    renderStep3();
    const res = await fetch(`${API}/${state.card.contract_id}/concept-check/stream`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ user_facts: state.userFacts }) });
    const last = await ContractQA.readSse(res, onStreamEvent);
    if (last.type === 'error') { const err = new Error(last.error); err.status = last.status; throw err; }
  }

  function onStreamEvent(e) {
    const p = state.progress;
    if (e.type === 'stage') p[e.stage] = e.status;
    else if (e.type === 'progress') { p.tagDone = e.done; p.tagTotal = e.total; }
    else if (e.type === 'partial') state.partial = e.views;
    else if (e.type === 'done') { state.result = e; state.savedAt = null; state.stale = false; refreshCard(); }
    else return;
    renderStep3();
  }

  function findingHtml(f, i) {
    const sev = SEV[f.severity] || SEV.minor;
    return `<div class="border border-neutral-200 rounded-xl p-3 space-y-1.5 text-[13px]">
      <div class="flex flex-wrap items-center gap-2 text-[12.5px]"><span class="font-semibold">${i}. ${esc(f.unit_label)}</span>
        <span class="rounded-full px-2 py-0.5" style="color:${sev[1]};background:${sev[2]}">${sev[0]}</span>
        <span class="text-neutral-600">${esc(f.group_label || GROUP[f.group] || f.group)}</span>
        ${f.disadvantaged ? `<span class="text-neutral-500">· bất lợi cho ${esc(f.disadvantaged)}</span>` : ''}</div>
      ${f.quote ? `<blockquote class="italic border-l-2 border-neutral-300 pl-2 text-neutral-700">“${esc(f.quote)}”</blockquote>` : ''}
      <div class="text-[13.5px]">${esc(f.explanation)}</div>
      ${(f.evidence || []).map(e => `<div class="text-[12px] border-l-2 border-neutral-300 pl-2"><span class="font-medium">${esc(e.source_title)}</span> — ${esc(e.section)}</div>`).join('')}
      ${f.suggestion ? `<div><span class="text-neutral-500">Gợi ý sửa:</span> ${esc(f.suggestion)}</div>` : ''}</div>`;
  }

  function reviewReport() {
    const r = state.review, f = r.findings || [];
    const cov = r.coverage || {};
    const links = (r.rid ? ['docx', 'pdf'] : []).map(fmt => `<a class="btn-ghost" href="${API}/${state.card.contract_id}/reports/${esc(r.rid)}.${fmt}">Tải .${fmt}</a>`).join(' ');
    return `<div class="space-y-3"><div class="text-[13.5px] font-semibold">Báo cáo Soát luật${cov.reviewed ? ` · đã soát ${cov.reviewed}/${cov.requested || cov.total} điều khoản` : ''}</div>
      ${(r.warnings || []).map(w => `<div class="text-[12.5px]" style="color:#8a5a00">⚠ ${esc(w)}</div>`).join('')}
      ${f.length ? f.map((x, i) => findingHtml(x, i + 1)).join('') : '<div class="text-[13.5px]">Không phát hiện vấn đề trong phạm vi đã soát.</div>'}
      ${links ? `<div class="flex gap-2">${links}</div>` : ''}</div>`;
  }

  function renderStep3() {
    const c = state.card;
    $('step-3').innerHTML = `<div class="text-[14px] font-semibold mb-1">③ Soát</div>
      <div class="text-[12.5px] text-neutral-500 mb-3">${esc(c.filename)} · ${(c.units || []).length} điều khoản</div>
      <div class="flex flex-wrap items-center gap-2">
        <button type="button" id="run-concept" class="btn" ${state.running ? 'disabled' : ''}>Kiểm tra concept</button>
        <button type="button" id="run-review" class="btn-ghost" ${state.running ? 'disabled' : ''}>Soát luật</button>
        ${c.last_check && !state.savedAt ? `<button type="button" data-view-last="${esc(c.contract_id)}" class="btn-ghost" ${state.running ? 'disabled' : ''}>Xem lại kết quả kiểm tra (${esc(when(c.last_check.checked_at))})</button>` : ''}
        <span id="run-status" class="text-[12.5px] text-neutral-500">${state.running && !state.progress ? 'Đang chạy…' : ''}</span></div>
      <div class="mt-3">${progressHtml()}</div>
      <div id="run-error" class="text-[12.5px] mt-2" style="color:#b42318">${esc(state.error)}</div>
      <div class="mt-4 space-y-6">${conceptReport()}${state.review ? reviewReport() : ''}</div>`;
  }

  async function runOp(kind) {
    if (state.running) return;
    state.running = true; state.error = '';
    renderStep3();
    try {
      if (kind === 'concept') {
        await runConceptStream();
      } else {
        const rep = await post(`/${state.card.contract_id}/run`, { op: 'review' });
        state.review = rep;
        state.card = await api('/' + encodeURIComponent(state.card.contract_id));
      }
    } catch (e) {
      if (e.status === 409 && e.pending) {
        state.running = false;
        notice('Còn dữ kiện bắt buộc chưa xác minh: ' + e.pending.map(p => p.label).join(', '));
        try { setCard(await api('/' + encodeURIComponent(state.card.contract_id))); } catch (_) { /* giữ thẻ cũ */ }
        state.step = 2;
        render();
        return;
      }
      if (e.status === 404) {
        state.running = false; state.card = null; state.step = 1;
        notice('Hợp đồng này đã hết phiên — hãy nạp lại.');
        render();
        return;
      }
      state.error = e.message;
    }
    state.running = false;
    notice('');
    renderStep3();
  }

  // ------------------------------------------------------------------ sự kiện
  document.addEventListener('click', e => {
    const t = e.target.closest('button');
    if (!t) return;
    if (t.dataset.viewLast) viewLast(t.dataset.viewLast);
    else if (t.dataset.step) goStep(Number(t.dataset.step));
    else if (t.id === 'go') upload();
    else if (t.id === 'next') goStep(2);
    else if (t.dataset.open) openSaved(t.dataset.open);
    else if (t.id === 'confirm') confirmFacts();
    else if (t.id === 'to3') goStep(3);
    else if (t.id === 'run-concept') runOp('concept');
    else if (t.id === 'run-review') runOp('review');
    else if (t.dataset.filter !== undefined) { state.filter = t.dataset.filter; renderStep3(); }
    else if (t.dataset.a === 'to-facts') goStep(2);
    else if (t.dataset.dl === 'md') download('report.md', state.result.markdown, 'text/markdown');
    else if (t.dataset.dl === 'json') download('report.json', JSON.stringify(state.result.report, null, 2), 'application/json');
  });

  document.addEventListener('toggle', e => {
    const d = e.target;
    if (!(d instanceof HTMLDetailsElement) || !d.dataset.key) return;
    if (d.open) state.open.add(d.dataset.key); else state.open.delete(d.dataset.key);
  }, true);

  const startCid = new URLSearchParams(location.search).get('cid');
  if (startCid) openSaved(startCid, true); else render();
})();
