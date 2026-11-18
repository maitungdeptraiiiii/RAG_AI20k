// Trang /contracts/ask: chọn hợp đồng đã dựng đồ thị, hỏi agent trên đồ thị (spec 2026-11-17-contract-ask-page-design).
(function () {
  'use strict';
  const API = '/api/contracts';
  const KEYS = ['ctpage.saved', 'justice_saved_contracts_v1'];   // trang Hợp đồng + plugin chat
  const SAMPLES = ['Lúc thử việc tôi được trả bao nhiêu tiền mỗi tháng, có đúng luật không?',
    'Thời gian làm việc và làm thêm giờ trong hợp đồng quy định thế nào?',
    'Phụ lục sửa những điều khoản nào và có hiệu lực từ ngày nào?',
    'Tôi được nghỉ phép năm bao nhiêu ngày?'];
  const { esc, answerHtml, stepsHtml } = window.ContractQA;
  const $ = id => document.getElementById(id);
  const day = iso => iso ? iso.slice(0, 10).split('-').reverse().join('/') : '—';
  const state = { cards: [], active: null, convos: {}, draft: '' };

  function storedIds(key) { try { const v = JSON.parse(localStorage.getItem(key) || '[]'); return Array.isArray(v) ? v : []; } catch (e) { return []; } }
  function dropId(cid) {
    KEYS.forEach(k => { try { localStorage.setItem(k, JSON.stringify(storedIds(k).filter(i => i !== cid))); } catch (e) { /* bỏ qua */ } });
  }

  async function getJson(path) {
    const res = await fetch(API + path);
    const data = await res.json().catch(() => ({}));
    if (!res.ok) { const err = new Error(data.error || `Lỗi server (${res.status})`); err.status = res.status; throw err; }
    return data;
  }

  function notice(msg) { const el = $('notice'); el.textContent = msg || ''; el.classList.toggle('hidden', !msg); }
  const card = cid => state.cards.find(c => c.contract_id === cid);
  const busy = cid => (state.convos[cid] || []).some(t => !t.done && !t.error);

  // ------------------------------------------------------------------ danh sách
  function renderList() {
    if (!state.cards.length) {
      $('list').innerHTML = '<div class="text-[13px] text-neutral-500 px-1">Chưa có hợp đồng. <a class="underline" href="/contracts">Nạp ở trang Soát hợp đồng</a> (chọn “Lưu để mở lại sau”).</div>';
      return;
    }
    $('list').innerHTML = state.cards.map(c => {
      const ready = c.concepts > 0;
      return `<div class="${ready ? '' : 'opacity-60'}">
        <button type="button" class="item ${c.contract_id === state.active ? 'on' : ''}" data-cid="${esc(c.contract_id)}" ${ready ? '' : 'disabled'}>
          <div class="text-[13.5px] font-medium truncate">${esc(c.filename)}</div>
          <div class="text-[11.5px] text-neutral-500">ký ${day(c.sign_date)} · ${ready ? `${c.concepts} khái niệm` : 'chưa dựng đồ thị'}</div></button>
        ${ready ? '' : `<a class="block text-[11.5px] underline text-neutral-600 px-2.5 -mt-1 mb-1" href="/contracts?cid=${encodeURIComponent(c.contract_id)}">Kiểm tra concept →</a>`}</div>`;
    }).join('');
  }

  // ------------------------------------------------------------------ hội thoại
  function renderChat() {
    const c = card(state.active);
    const turns = c ? (state.convos[c.contract_id] || []) : [];
    $('chat-head').innerHTML = c ? `<div class="text-[14px] font-semibold truncate">${esc(c.filename)}</div>
        <div class="text-[12px] text-neutral-500">ngày ký ${day(c.sign_date)} · ${c.concepts} khái niệm đã gán · trả lời bằng agent đi trên đồ thị hợp đồng</div>` : '';
    if (!c) {
      $('turns').innerHTML = '<div class="h-full flex items-center justify-center text-[14px] text-neutral-500">Chọn một hợp đồng đã dựng đồ thị ở cột bên trái.</div>';
    } else if (!turns.length) {
      $('turns').innerHTML = `<div class="max-w-[720px] mx-auto pt-6"><div class="text-[20px] font-semibold mb-4">Bạn muốn biết gì về hợp đồng này?</div>
        <div class="grid sm:grid-cols-2 gap-2">${SAMPLES.map((s, i) => `<button type="button" class="sample" data-sample="${i}">${esc(s)}</button>`).join('')}</div></div>`;
    } else {
      $('turns').innerHTML = `<div class="max-w-[760px] mx-auto space-y-5">${turns.map(t => `
        <div class="flex justify-end"><div class="bg-[#f4f4f4] px-5 py-2.5 rounded-3xl max-w-[85%] text-[15px] leading-relaxed whitespace-pre-wrap">${esc(t.q)}</div></div>
        <div>${t.done ? answerHtml(t.done, { diagram: true }) + '<div class="mt-2">' + stepsHtml(t.steps.length ? t.steps : (t.done.trace || []), false) + '</div>'
          : t.error ? `<div class="text-[13px]" style="color:var(--critical-text)">${esc(t.error)}</div>`
          : `<div class="text-[13px] text-neutral-600 mb-1.5"><span class="spin">⟳</span> Agent đang đi trên đồ thị…</div>${stepsHtml(t.steps, true)}`}</div>`).join('')}</div>`;
      $('turns').scrollTop = $('turns').scrollHeight;
    }
    const input = $('q');
    const off = !c || busy(c.contract_id);
    input.disabled = off; $('send').disabled = off;
    if (input.value !== state.draft) input.value = state.draft;
  }

  function select(cid) {
    if (!card(cid) || card(cid).concepts <= 0) return;
    state.active = cid;
    const url = new URL(location.href); url.searchParams.set('cid', cid); history.replaceState(null, '', url);
    renderList(); renderChat();
    $('q').focus();
  }

  async function send(text) {
    const cid = state.active;
    const q = (text ?? state.draft).trim();
    if (!cid || !q || busy(cid)) return;
    const convo = state.convos[cid] = state.convos[cid] || [];
    const history = convo.filter(t => t.done).map(t => ({ query: t.q, answer: t.done.answer }));
    const turn = { q, steps: [], done: null, error: '' };
    convo.push(turn);
    if (text === undefined) state.draft = '';
    const redraw = () => { if (state.active === cid) renderChat(); };   // đổi hợp đồng giữa chừng: vẫn ghi vào lượt cũ
    redraw();
    try {
      const last = await window.ContractQA.ask(cid, { question: q, history }, e => {
        if (e.type === 'step') turn.steps.push(e);
        else if (e.type === 'done') turn.done = e;
        else return;
        redraw();
      });
      if (last.type === 'error') turn.error = last.error;
      if (last.status === 404) { dropId(cid); notice('Hợp đồng này đã hết phiên — hãy nạp lại ở trang Soát hợp đồng.'); }
    } catch (e) {
      turn.error = e.message;
    }
    redraw();
    if (state.active === cid) $('q').focus();
  }

  // ------------------------------------------------------------------ nạp danh sách
  async function load() {
    const want = new URLSearchParams(location.search).get('cid');
    const ids = [...new Set([...(want ? [want] : []), ...KEYS.flatMap(storedIds)])].slice(0, 50);
    try {
      state.cards = ids.length ? (await getJson('?ids=' + ids.map(encodeURIComponent).join(','))).contracts : [];
    } catch (e) {
      notice(e.message);
    }
    const got = new Set(state.cards.map(c => c.contract_id));
    ids.filter(i => !got.has(i) && i !== want).forEach(dropId);          // id đã hết phiên
    if (want && !got.has(want)) {                                        // hợp đồng nạp tạm: không có trong ?ids=
      try { state.cards.unshift(await getJson('/' + encodeURIComponent(want))); }
      catch (e) { notice(e.status === 404 ? 'Hợp đồng trên đường dẫn đã hết phiên — hãy nạp lại.' : e.message); }
    }
    const first = (want && card(want)) || state.cards.find(c => c.concepts > 0);
    if (want && card(want) && card(want).concepts <= 0) notice('Hợp đồng này chưa dựng đồ thị: hãy chạy Kiểm tra concept ở trang Soát hợp đồng.');
    renderList();
    if (first && first.concepts > 0) select(first.contract_id); else renderChat();
  }

  // ------------------------------------------------------------------ sự kiện
  document.addEventListener('click', e => {
    const t = e.target.closest('button');
    if (!t) return;
    if (t.dataset.cid) select(t.dataset.cid);
    else if (t.dataset.sample !== undefined) send(SAMPLES[Number(t.dataset.sample)]);
    else if (t.id === 'send') send();
  });
  $('q').addEventListener('input', e => {
    state.draft = e.target.value;
    e.target.style.height = 'auto'; e.target.style.height = Math.min(e.target.scrollHeight, 160) + 'px';
  });
  $('q').addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); send(); }
  });

  load();
})();
