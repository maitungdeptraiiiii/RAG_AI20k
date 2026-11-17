/* /upload — chế độ "Văn bản pháp luật": 3 bước ① Text đúng chưa? → ② Hệ thống hiểu đúng chưa? → ③ Đưa vào kho.
 * Dùng chung với upload.html (script cổ điển, cùng phạm vi toàn cục): $, esc, fmtTime, fmtPct, ICON, KIND, TONE_LABEL,
 * pageTone, pageLabel, pageTipHtml, confCell, showTip, hideTip. Mọi chuỗi từ server đều qua esc(). */
(() => {
  'use strict';

  const store = {
    get(k) { try { return localStorage.getItem(k) || ''; } catch (e) { return ''; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch (e) {} },
  };

  // ------------------------------------------------------------------ hằng số hiển thị
  const STATE = {
    step1: ['Bước ① chờ xác nhận text', 'warning'], step2: ['Bước ② chờ xác nhận', 'warning'],
    step3: ['Bước ③ chờ đưa vào kho', 'warning'], queued: ['Chờ lượt ghi', 'warning'], building: ['Đang dựng kho', 'warning'],
    published: ['Đã vào kho', 'good'], failed: ['Lỗi', 'critical'], stale: ['Kho đã thay đổi', 'critical'],
    duplicate: ['Đã có trong kho', 'good'], cancelled: ['Đã huỷ', 'neutral'],
  };
  const DRAFT_STEP = { step1: 1, duplicate: 1, step2: 2, step3: 3, queued: 3, building: 3, published: 3, failed: 3, stale: 3, cancelled: 1 };
  const EDITABLE = ['step1', 'step2', 'step3', 'duplicate', 'failed', 'stale', 'queued'];
  const FIELD_LABEL = {
    doc_type: 'Loại văn bản', doc_number: 'Số hiệu', title: 'Tên văn bản', issuer: 'Cơ quan ban hành', issued_on: 'Ngày ban hành',
    vbpl_id: 'Mã vbpl', vbpl_effective_from: 'Hiệu lực từ (vbpl)', vbpl_effective_to: 'Hiệu lực đến (vbpl)', eff_status: 'Tình trạng (vbpl)',
  };
  const DATE_FIELDS = ['issued_on', 'vbpl_effective_from', 'vbpl_effective_to'];
  const SOURCE_LABEL = { vbpl: 'vbpl', text: 'từ văn bản', user: 'bạn nhập', inherited: 'kế thừa' };
  const KIND_VI = { base: 'Luật gốc', amending: 'Luật sửa đổi', consolidated: 'Văn bản hợp nhất' };
  const REVIEW_VI = { auto_accepted: ['Tự xác minh', 'good'], pending: ['Cần duyệt', 'warning'], approved: ['Đã duyệt', 'good'], rejected: ['Từ chối', 'critical'] };
  const JOB_STAGES = [
    ['queued', 'Chờ lượt'], ['building', 'Dựng kho'], ['validating', 'Kiểm tra & công bố'], ['indexing', 'Dựng chỉ mục'], ['done', 'Chat đã chuyển sang dữ liệu mới'],
  ];
  const TONE_ICON = (t) => (window.ICON && ICON[t]) || '';

  // ------------------------------------------------------------------ trạng thái trang
  const L = { cur: null, view: 1, dirty: false, openPage: null, openOp: null, timer: null, jobId: null, busy: false, note: '' };

  const byName = () => $('legal-by');
  const who = () => (byName() ? byName().value.trim() : store.get('legal_by'));
  const fieldVal = (d, n) => (d.fields[n] || {}).value;
  const fmtDate = (s) => { if (!s) return '—'; const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(s); return m ? `${m[3]}/${m[2]}/${m[1]}` : s; };
  const fd = (s) => esc(fmtDate(s));      // dùng khi chèn vào HTML

  async function api(method, path, body, form) {
    const opt = { method };
    if (form) opt.body = form;
    else if (body !== undefined) { opt.headers = { 'Content-Type': 'application/json' }; opt.body = JSON.stringify(body); }
    const res = await fetch(path, opt);
    let data = null;
    try { data = await res.json(); } catch (e) { /* không phải JSON */ }
    if (!res.ok) throw new Error((data && data.error) || `Lỗi server (${res.status})`);
    return data;
  }

  const banner = (tone, html) => `<div class="banner ${tone}" role="${tone === 'critical' ? 'alert' : 'status'}">${TONE_ICON(tone === 'info' ? 'good' : tone)}<div class="min-w-0 break-words">${html}</div></div>`;
  const stateChip = (st, extra) => {
    const [label, tone] = STATE[st] || [st, 'neutral'];
    const color = tone === 'neutral' ? 'var(--ink-3)' : `var(--${tone}-text)`;
    return `<span class="text-[11.5px] font-medium" style="color:${color}">${esc(extra || label)}</span>`;
  };
  function setStatus(html, tone) {
    const el = $('legal-status');
    el.className = 'text-[12.5px] block';
    el.style.color = tone ? `var(--${tone}-text)` : 'var(--ink-2)';
    el.innerHTML = html;
  }
  function flash(html, tone) {           // thông báo ngắn ở đầu phần chi tiết
    const el = $('legal-flash');
    if (el) el.innerHTML = html ? banner(tone, html) : '';
  }

  // ------------------------------------------------------------------ trái: tải lên, lịch sử, chỉ dẫn chờ
  let picked = null;
  function renderPicked() {
    $('legal-picked').innerHTML = picked
      ? `<span class="inline-flex items-center gap-2 bg-neutral-50 rounded-md px-2 py-1 max-w-full"><span class="truncate">${esc(picked.name)} <span class="text-neutral-400">· ${(picked.size / 1024).toFixed(0)} KB</span></span><button id="legal-unpick" class="text-neutral-400 hover:text-black" aria-label="Bỏ file">✕</button></span>` : '';
    const b = $('legal-unpick');
    if (b) b.onclick = (e) => { e.preventDefault(); picked = null; renderPicked(); };
  }

  async function doUpload() {
    const url = $('legal-url').value.trim();
    if (!picked && !url) { setStatus('Chọn một file hoặc dán link vbpl.', 'critical'); return; }
    const btn = $('legal-upload');
    btn.disabled = true; btn.textContent = 'Đang đọc văn bản…';
    setStatus('File scan cần OCR từng trang nên có thể mất vài phút.');
    const fd = new FormData();
    if (picked) fd.append('file', picked); else fd.append('url', url);
    try {
      const d = await api('POST', '/api/legal/uploads', undefined, fd);
      setStatus('Đã tạo bản nháp. Hãy kiểm tra text ở bước ①.', 'good');
      picked = null; renderPicked(); $('legal-url').value = '';
      await loadHistory();
      showDraft(d);
    } catch (e) {
      setStatus(`Lỗi: ${esc(e.message)}`, 'critical');
    } finally {
      btn.disabled = false; btn.textContent = 'Tải lên';
    }
  }

  async function loadHistory() {
    try {
      const { uploads = [], legacy_warning: legacy = null } = await api('GET', '/api/legal/uploads');
      $('legal-count').textContent = `${uploads.length} bản`;
      // kho luật cũ được ghi sau khi kho có phiên bản khởi tạo: không tự nhập, báo người dùng việc cần làm
      const warn = legacy ? `<li class="px-1 pb-2">${banner('warning', `<b>Kho luật cũ chưa được nhập.</b><div class="text-[12px] mt-1 break-words">${esc(legacy)}</div>`)}</li>` : '';
      $('legal-history').innerHTML = warn + (uploads.length ? uploads.map((u) => {
        const idx = u.state === 'published' && u.index_failed ? 'Đã vào kho, chỉ mục lỗi' : null;
        const num = fieldVal(u, 'doc_number'), title = fieldVal(u, 'title');
        return `<li><button class="legal-item report-item w-full text-left px-2.5 py-2 rounded-lg hover:bg-neutral-100 ${L.cur && L.cur.upload_id === u.upload_id ? 'active' : ''}" data-id="${esc(u.upload_id)}">
          <div class="truncate text-[13px] font-medium">${esc(title || num || u.source_name)}</div>
          <div class="mt-0.5 text-[11.5px] text-neutral-500 flex flex-wrap gap-x-2"><span>${stateChip(u.state, idx)}</span><span>${esc(num || '')}</span><span>${esc(fmtTime(u.created_at))}</span></div>
        </button></li>`;
      }).join('') : '<li class="px-2.5 py-3 text-[12.5px] text-neutral-500">Chưa có bản nháp nào.</li>');
      document.querySelectorAll('#legal-history .legal-item').forEach((b) => { b.onclick = () => openDraft(b.dataset.id); });
    } catch (e) { $('legal-history').innerHTML = `<li class="px-2.5 py-3 text-[12.5px]" style="color:var(--critical-text)">${esc(e.message)}</li>`; }
  }

  async function loadPending() {
    try {
      const { laws = [] } = await api('GET', '/api/legal/pending-base-laws');
      $('legal-pending').innerHTML = laws.length ? laws.map((g) => `
        <li class="border border-neutral-200 rounded-lg px-2.5 py-1.5">
          <div class="font-medium break-words">${esc(g.target_law_name || 'Luật chưa rõ tên')} ${esc(g.target_law_number || '')}</div>
          <div class="text-[11.5px] text-neutral-500">${g.count} chỉ dẫn chờ · từ ${esc([...new Set(g.operations.map((o) => o.source_document_key))].join(', '))}</div>
        </li>`).join('') : '<li class="text-neutral-500">Không có chỉ dẫn nào đang chờ.</li>';
    } catch (e) { $('legal-pending').innerHTML = `<li style="color:var(--critical-text)">${esc(e.message)}</li>`; }
  }

  // ------------------------------------------------------------------ mở / vẽ bản nháp
  async function openDraft(id) {
    stopPoll();
    try { showDraft(await api('GET', '/api/legal/uploads/' + encodeURIComponent(id))); }
    catch (e) { setStatus(`Lỗi: ${esc(e.message)}`, 'critical'); }
  }

  function showDraft(d, view) {
    stopPoll();
    const prev = L.cur && L.cur.upload_id === d.upload_id ? L.cur : null;
    L.cur = d;
    L.view = view || DRAFT_STEP[d.state] || 1;
    if (!prev || prev.state !== d.state) { L.dirty = false; L.openOp = null; }
    document.querySelectorAll('#legal-history .legal-item').forEach((b) => b.classList.toggle('active', b.dataset.id === d.upload_id));
    render();
    if (!prev && window.innerWidth < 1024) $('legal-detail').scrollIntoView({ block: 'start' });   // điện thoại: đưa bước lên đầu
  }

  function renderSteps() {
    const d = L.cur, max = d ? DRAFT_STEP[d.state] || 1 : 0;
    document.querySelectorAll('#legal-steps .step-btn').forEach((b) => {
      const n = +b.dataset.step;
      b.disabled = !d || n > max;
      b.setAttribute('aria-disabled', String(b.disabled));
      if (n === L.view && d) b.setAttribute('aria-current', 'step'); else b.removeAttribute('aria-current');
      b.title = b.disabled ? 'Cần xác nhận bước trước' : '';
    });
  }

  function render() {
    const d = L.cur;
    renderSteps();
    $('legal-empty').classList.toggle('hidden', !!d);
    const body = $('legal-body');
    body.classList.toggle('hidden', !d);
    if (!d) return;
    const stepName = ['', 'Text đúng chưa?', 'Hệ thống hiểu đúng chưa?', 'Đưa vào kho'][L.view];
    body.innerHTML = `
      <div class="card p-4">
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div class="min-w-0">
            <div class="text-[12px] text-neutral-500">${d.origin === 'url' ? 'Link vbpl' : 'File tải lên'} · ${esc(fmtTime(d.created_at))} · ${stateChip(d.state, d.state === 'published' && d.index_failed ? 'Đã vào kho, chỉ mục lỗi' : '')}</div>
            <h2 class="mt-0.5 text-[16px] font-semibold break-words">${esc(fieldVal(d, 'title') || d.source_name)}</h2>
            <div class="text-[12px] text-neutral-500 break-all">${esc(d.source_name)}</div>
          </div>
          <label class="block w-full sm:w-[230px]"><span class="text-[11.5px] text-neutral-500">Người thực hiện (bắt buộc để xác nhận)</span>
            <input id="legal-by" class="lf-input mt-0.5" autocomplete="name" placeholder="Họ tên" value="${esc(store.get('legal_by'))}"></label>
        </div>
      </div>
      <div id="legal-flash"></div>
      <div id="legal-step" aria-label="${esc(stepName)}"></div>`;
    byName().oninput = () => store.set('legal_by', byName().value.trim());
    ({ 1: renderStep1, 2: renderStep2, 3: renderStep3 })[L.view]();
  }

  function stepFooter(buttons) {
    return `<div class="flex flex-wrap items-center gap-2 pt-1">${buttons}</div>`;
  }
  const cancelBtn = () => (EDITABLE.includes(L.cur.state) ? '<button id="b-cancel" class="btn-ghost" style="color:var(--critical-text)">Hủy bản nháp</button>' : '');

  async function act(fn, pending) {
    if (L.busy) return;
    L.busy = true;
    document.querySelectorAll('#legal-step button').forEach((b) => { b.disabled = true; });
    if (pending) flash(esc(pending), 'info');
    try { await fn(); }
    catch (e) { L.busy = false; render(); flash(esc(e.message), 'critical'); return; }
    L.busy = false;
  }
  function needBy() {
    if (!who()) { flash('Hãy nhập tên người thực hiện.', 'critical'); byName().focus(); return false; }
    store.set('legal_by', who());
    return true;
  }
  function bindCancel() {
    const b = $('b-cancel');
    if (!b) return;
    b.onclick = () => {
      if (!confirm('Hủy bản nháp này?')) return;
      act(async () => { const d = await api('POST', `/api/legal/uploads/${L.cur.upload_id}/cancel`, {}); await loadHistory(); showDraft(d); });
    };
  }

  // ------------------------------------------------------------------ ① Text đúng chưa?
  function structureBox(s) {
    const gaps = s.gaps || [];
    const problems = [];
    if (!s.n_articles) problems.push('Không đọc được Điều nào — text có thể sai định dạng hoặc OCR hỏng.');
    gaps.forEach(([a, b]) => problems.push(`Điều nhảy số: có Điều ${esc(a)} rồi tới Điều ${esc(b)} — có thể thiếu nội dung.`));
    if (!s.has_effectivity_article) problems.push('Không tìm thấy điều hiệu lực thi hành.');
    return `
      <div class="card p-4 space-y-2">
        <h3 class="text-[14px] font-semibold">Kiểm tra cấu trúc</h3>
        <div class="flex flex-wrap gap-x-5 gap-y-1 text-[13px]">
          <span><b class="tabular">${s.n_articles}</b> Điều đọc được</span>
          <span>${gaps.length ? `<b class="tabular">${gaps.length}</b> chỗ nhảy số` : 'Không nhảy số'}</span>
          <span>${s.has_effectivity_article ? 'Có điều hiệu lực thi hành' : 'Chưa có điều hiệu lực'}</span>
        </div>
        ${problems.length ? banner('warning', `<b>Cần xem kỹ text trước khi đi tiếp.</b><ul class="list-disc pl-5 mt-1">${problems.map((p) => `<li>${p.startsWith('Điều nhảy') ? p : esc(p)}</li>`).join('')}</ul>Vẫn đi tiếp được nếu bạn xác nhận text đúng.`) : banner('good', 'Cấu trúc đọc được liền mạch.')}
      </div>`;
  }

  function pagesBlock(d) {
    const pages = d.pages || [];
    if (!pages.length) return '';
    let tableNo = 0;
    pages.forEach((p) => { if (p.kind === 'table') p._tableNo = ++tableNo; });
    const tones = { good: 0, warning: 0, critical: 0 };
    pages.forEach((p) => { tones[pageTone(p)]++; });
    const total = pages.length;
    return `
      <div class="card p-4 space-y-3">
        <div class="flex flex-wrap items-baseline justify-between gap-2"><h3 class="text-[14px] font-semibold">Bản đồ trang</h3>
          <span class="text-[12px] text-neutral-500">Bấm một ô để xem ảnh trang gốc cạnh text</span></div>
        <div class="seg" role="img" aria-label="${['good', 'warning', 'critical'].map((t) => `${TONE_LABEL[t]} ${tones[t]} trang`).join(', ')}">
          ${['good', 'warning', 'critical'].filter((t) => tones[t]).map((t) => `<div style="width:${100 * tones[t] / total}%;background:var(--${t})"></div>`).join('')}
        </div>
        <div class="flex flex-wrap gap-x-4 gap-y-1 text-[12px] text-neutral-700">
          ${['good', 'warning', 'critical'].map((t) => `<span class="inline-flex items-center gap-1.5">${ICON[t]}${TONE_LABEL[t]} <span class="text-neutral-500 tabular">${tones[t]}</span></span>`).join('')}
        </div>
        <div id="lg-map" class="flex flex-wrap gap-[3px] pt-1">
          ${pages.map((p) => `<button class="page-cell ${L.openPage === p.index ? 'active' : ''}" data-i="${p.index}" aria-label="${esc(pageLabel(p))}: ${TONE_LABEL[pageTone(p)]}" style="background:var(--${pageTone(p)})"></button>`).join('')}
        </div>
      </div>
      <div class="card overflow-hidden">
        <div class="p-4 border-b border-neutral-100"><h3 class="text-[14px] font-semibold">Chi tiết từng trang</h3></div>
        <div class="overflow-x-auto"><table class="w-full text-[13px]">
          <thead class="text-left text-[11.5px] text-neutral-500 bg-neutral-50"><tr>
            <th class="px-4 py-2 font-medium whitespace-nowrap">Trang</th><th class="px-3 py-2 font-medium whitespace-nowrap">Nguồn text</th>
            <th class="px-3 py-2 font-medium whitespace-nowrap">Độ tin cậy OCR</th><th class="px-3 py-2 font-medium whitespace-nowrap text-right">Số từ</th>
            <th class="px-3 py-2 font-medium whitespace-nowrap">Trạng thái</th></tr></thead>
          <tbody>${pages.map((p) => {
            const tone = pageTone(p), open = L.openPage === p.index;
            const no = p.page != null ? p.page : p.index + 1;
            const img = d.origin === 'file' ? `<img loading="lazy" alt="Ảnh trang ${esc(no)} gốc" class="w-full rounded-lg border border-neutral-200" src="/api/legal/uploads/${encodeURIComponent(d.upload_id)}/page_image/${encodeURIComponent(no)}" onerror="this.replaceWith(Object.assign(document.createElement('div'),{className:'text-[12px] text-neutral-400',textContent:'Không có ảnh trang (file không phải PDF/ảnh).'}))">` : '';
            return `<tr class="lg-row border-t border-neutral-100 hover:bg-neutral-50 cursor-pointer align-top" data-i="${p.index}">
              <td class="px-4 py-2.5 font-medium whitespace-nowrap">${esc(pageLabel(p))}</td><td class="px-3 py-2.5 whitespace-nowrap">${esc(KIND[p.kind] || p.kind)}</td>
              <td class="px-3 py-2.5 whitespace-nowrap">${confCell(p)}</td><td class="px-3 py-2.5 text-right tabular">${p.words.toLocaleString('vi-VN')}</td>
              <td class="px-3 py-2.5 whitespace-nowrap"><span class="inline-flex items-center gap-1.5" style="color:var(--${tone}-text)">${ICON[tone]}${TONE_LABEL[tone]}</span></td></tr>
              <tr class="${open ? '' : 'hidden'}" data-for="${p.index}"><td colspan="5" class="px-4 pb-3"><div class="grid grid-cols-1 md:grid-cols-2 gap-3 bg-neutral-50 border border-neutral-200 rounded-lg p-3">
                <div class="min-w-0">${open ? img : ''}</div>
                <div class="min-w-0"><div class="text-[11px] text-neutral-500 mb-1">Text trích từ trang này (đầu trang)${p.ocr_model ? ` · ${esc(p.ocr_model)}` : ''}</div>
                  <div class="legal-text text-neutral-700">${p.preview ? esc(p.preview) + (p.chars > p.preview.length ? '…' : '') : '<i class="text-neutral-400">Không có chữ</i>'}</div>
                  ${(p.issues || []).map((i) => `<div class="mt-1 text-[12px]" style="color:var(--warning-text)">• ${esc(i.detail)}</div>`).join('')}</div>
              </div></td></tr>`;
          }).join('')}</tbody></table></div>
      </div>`;
  }

  function diffBlock(d) {
    const dup = d.duplicate;
    if (!dup) return '';
    if (d.state === 'duplicate' || !dup.diff) {
      return banner('good', `<b>Văn bản này đã có trong kho</b> (đưa vào ngày ${esc(fmtTime(dup.fetched_at))}, nguồn ${esc(dup.text_source || '—')}), không có gì thay đổi. Bản nháp dừng ở đây, không tạo bản mới.`);
    }
    const df = dup.diff;
    const words = (ops, side) => ops.filter(([t]) => t === 'equal' || t === side).map(([t, w]) => (t === 'equal' ? esc(w) : `<span class="w-${t}">${esc(w)}</span>`)).join(' ');
    return `
      <div class="card p-4 space-y-3">
        ${banner('warning', `<b>Số hiệu này đã có trong kho với nội dung khác.</b> Xem từng Điều bên dưới rồi chọn "Thay bản trong kho" hoặc "Hủy". Bản trong kho: nguồn ${esc(dup.text_source || '—')}, ${esc(fmtTime(dup.fetched_at))}.`)}
        <div class="grid grid-cols-2 sm:grid-cols-4 gap-2 text-center">
          ${[['Giống', df.same], ['Sửa', df.changed.length], ['Thêm', df.added.length], ['Bỏ', df.removed.length]].map(([k, n]) => `<div class="border border-neutral-200 rounded-lg py-2"><div class="text-[20px] font-semibold tabular">${n}</div><div class="text-[12px] text-neutral-500">Điều ${k.toLowerCase()}</div></div>`).join('')}
        </div>
        ${df.added.length ? `<div class="text-[13px]"><b>Điều thêm:</b> ${df.added.map((a) => `<span class="chip">Điều ${esc(a)}</span>`).join(' ')}</div>` : ''}
        ${df.removed.length ? `<div class="text-[13px]"><b>Điều bỏ:</b> ${df.removed.map((a) => `<span class="chip">Điều ${esc(a)}</span>`).join(' ')}</div>` : ''}
        ${df.changed.length ? `<div class="space-y-2"><h4 class="text-[13px] font-semibold">Điều bị sửa</h4>
          ${df.changed.map((c) => `<details class="border border-neutral-200 rounded-lg"><summary class="cursor-pointer px-3 py-2 text-[13px] font-medium">Điều ${esc(c.article)}</summary>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-3 p-3 pt-0">
              <div class="min-w-0"><div class="text-[11.5px] text-neutral-500 mb-1">Trong kho</div><div class="legal-text border border-neutral-200 rounded-lg p-2.5 max-h-[300px] overflow-y-auto">${words(c.ops, 'delete')}</div></div>
              <div class="min-w-0"><div class="text-[11.5px] text-neutral-500 mb-1">Bản mới</div><div class="legal-text border border-neutral-200 rounded-lg p-2.5 max-h-[300px] overflow-y-auto">${words(c.ops, 'insert')}</div></div>
            </div></details>`).join('')}</div>` : ''}
        ${dup.replace_allowed ? '' : banner('info', '<b>Không thay được bản trong kho:</b> bản vbpl là text gốc, nên file tải lên không được thay thế nó. Bảng so sánh chỉ để tham khảo; bạn chỉ có thể hủy.')}
      </div>`;
  }

  function renderStep1() {
    const d = L.cur, dup = d.duplicate;
    const atStep1 = d.state === 'step1';
    const textBox = `<details class="card p-4"${d.origin === 'url' ? ' open' : ''}><summary class="cursor-pointer text-[14px] font-semibold">Toàn văn đã chuẩn hoá (${d.text.length.toLocaleString('vi-VN')} ký tự)</summary>
      ${d.origin === 'url' ? `<div class="mt-2 text-[12.5px]">Text lấy từ vbpl: <a class="underline break-all" href="${esc(d.source_name)}" target="_blank" rel="noopener noreferrer">${esc(d.source_name)}</a> — không có ảnh trang.</div>` : ''}
      <div class="legal-text mt-2 border border-neutral-200 rounded-lg p-3 max-h-[420px] overflow-y-auto">${esc(d.text)}</div></details>`;
    let buttons = '';
    if (atStep1 && !dup) buttons = '<button id="b-confirm1" class="btn-primary">Text đúng, sang bước ②</button>';
    if (atStep1 && dup && dup.diff && dup.replace_allowed) buttons = '<button id="b-replace" class="btn-primary">Thay bản trong kho</button>';
    $('legal-step').innerHTML = `<div class="space-y-4">
      ${!atStep1 && d.state !== 'duplicate' && d.state !== 'cancelled' ? banner('info', 'Bạn đã xác nhận bước này' + (d.confirmations.step1 ? ` (${esc(d.confirmations.step1.by)}, ${esc(fmtTime(d.confirmations.step1.at))})` : '') + '. Đang xem lại, không sửa được.') : ''}
      ${d.state === 'cancelled' ? banner('info', 'Bản nháp đã huỷ.') : ''}
      ${diffBlock(d)}${structureBox(d.structure)}${pagesBlock(d)}${textBox}
      ${stepFooter(buttons + cancelBtn())}</div>`;
    bindCancel();
    document.querySelectorAll('#lg-map .page-cell').forEach((c) => {
      const p = d.pages[+c.dataset.i], html = pageTipHtml(p);
      c.onmouseenter = (e) => showTip(e, html); c.onmousemove = (e) => showTip(e, html); c.onmouseleave = hideTip;
      c.onclick = () => { hideTip(); L.openPage = L.openPage === p.index ? null : p.index; renderStep1(); };
    });
    document.querySelectorAll('.lg-row').forEach((tr) => { tr.onclick = () => { L.openPage = L.openPage === +tr.dataset.i ? null : +tr.dataset.i; renderStep1(); }; });
    const c = $('b-confirm1');
    if (c) c.onclick = () => { if (needBy()) act(async () => { showDraft(await api('POST', `/api/legal/uploads/${d.upload_id}/confirm-text`, { by: who() })); loadHistory(); }); };
    const r = $('b-replace');
    if (r) r.onclick = () => { if (needBy()) act(async () => { showDraft(await api('POST', `/api/legal/uploads/${d.upload_id}/replace`, { by: who() })); loadHistory(); }); };
  }

  // ------------------------------------------------------------------ ② Hệ thống hiểu đúng chưa?
  function chip(f) {
    if (!f || !f.source) return '';
    const tip = [`Nguồn: ${SOURCE_LABEL[f.source] || f.source}`, f.at ? `Lúc: ${fmtTime(f.at)}` : '', f.detail ? `Bằng chứng: ${f.detail}` : ''].filter(Boolean).join('\n');
    return `<span class="src-chip ${esc(f.source)}" tabindex="0" title="${esc(tip)}" aria-label="${esc(tip.replace(/\n/g, '. '))}">${esc(SOURCE_LABEL[f.source] || f.source)}</span>`;
  }

  function fieldsForm(d) {
    const pv = d.preview, eff = pv && pv.effectivity;
    const textDate = eff && eff.default_from;
    return `<div class="card p-4 space-y-3"><h3 class="text-[14px] font-semibold">Thông tin văn bản</h3>
      ${d.source_verified ? '' : banner('warning', '<b>Chưa đối chiếu được với vbpl trong lần upload này.</b> Mọi phiên bản sinh ra từ văn bản này sẽ ở trạng thái "cần duyệt" (không có thông tin vbpl đối chiếu). Bấm "Tra lại vbpl" nếu đã có số hiệu.')}
      <div class="grid grid-cols-1 md:grid-cols-2 gap-x-4 gap-y-3">
        ${Object.keys(FIELD_LABEL).map((n) => {
          const f = d.fields[n] || {}, v = f.value == null ? '' : f.value;
          const mismatch = n === 'vbpl_effective_from' && textDate && v && textDate !== v;
          const warn = mismatch || f.source === 'inherited';
          const note = mismatch ? `Lệch: câu chữ văn bản ghi hiệu lực từ ${fmtDate(textDate)}, vbpl ghi ${fmtDate(v)}.`
            : f.source === 'inherited' ? 'Giá trị kế thừa từ bản trước trong kho — hãy đối chiếu với text mới (không tính là đối chiếu vbpl lần này).' : '';
          return `<div class="min-w-0"><div class="flex items-center justify-between gap-2 mb-1"><label for="f-${n}" class="text-[12px] text-neutral-600">${esc(FIELD_LABEL[n])}</label>${chip(f)}</div>
            <input id="f-${n}" data-f="${n}" data-orig="${esc(v)}" class="lf-input ${warn ? 'warn' : ''}" ${DATE_FIELDS.includes(n) ? 'type="date"' : ''} value="${esc(v)}">
            ${note ? `<div class="mt-1 text-[11.5px]" style="color:var(--warning-text)">${esc(note)}</div>` : ''}
            ${f.detail && f.source !== 'inherited' ? `<div class="mt-0.5 text-[11px] text-neutral-400 truncate" title="${esc(f.detail)}">${esc(f.detail)}</div>` : ''}</div>`;
        }).join('')}
      </div>
      <div class="flex flex-wrap items-center gap-2"><button id="b-save" class="btn-ghost" disabled>Lưu thông tin</button><span id="save-hint" class="text-[12px] text-neutral-500"></span></div>
    </div>`;
  }

  function effectivityBlock(eff) {
    const ex = eff.exceptions || [], cu = eff.conditional_units || [], flags = eff.flags_vi || [];
    return `<div class="card p-4 space-y-3"><h3 class="text-[14px] font-semibold">Hiệu lực</h3>
      <div class="text-[13px]"><span class="text-neutral-500">Ngày hiệu lực chung:</span> <b>${eff.default_from ? fd(eff.default_from) : 'chưa đọc được'}</b>
        ${eff.evidence ? `<div class="legal-text mt-1 border-l-2 border-neutral-300 pl-2 text-neutral-600">“${esc(eff.evidence)}”</div>` : ''}</div>
      ${ex.length ? `<div><div class="text-[12px] text-neutral-500 mb-1">Ngoại lệ theo đơn vị</div><ul class="space-y-1.5 text-[13px]">${ex.map((e) => `<li><b>${esc(e.units.join(', '))}</b> hiệu lực từ <b>${fd(e.date)}</b>${e.evidence ? `<div class="legal-text border-l-2 border-neutral-300 pl-2 text-neutral-600">“${esc(e.evidence)}”</div>` : ''}</li>`).join('')}</ul></div>` : ''}
      ${cu.length ? `<div><div class="text-[12px] text-neutral-500 mb-1">Hiệu lực theo sự kiện (không theo ngày)</div><ul class="space-y-1.5 text-[13px]">${cu.map((c) => `<li><b>${esc(c.unit)}</b>${c.evidence ? `<div class="legal-text border-l-2 border-neutral-300 pl-2 text-neutral-600">“${esc(c.evidence)}”</div>` : ''}</li>`).join('')}</ul></div>` : ''}
      ${flags.map((f) => banner('warning', esc(f))).join('')}
    </div>`;
  }

  function targetsBlock(pv) {
    const t = pv.targets || [], rp = pv.repeals || [];
    return `<div class="card p-4 space-y-3"><h3 class="text-[14px] font-semibold">Văn bản này là: ${esc(KIND_VI[pv.kind] || pv.kind)}</h3>
      ${t.length ? `<div><div class="text-[12px] text-neutral-500 mb-1">${pv.kind === 'consolidated' ? 'Luật được hợp nhất' : 'Luật bị sửa'}</div><ul class="space-y-1.5">
        ${t.map((x) => `<li>${x.in_store ? `<div class="text-[13px] flex items-start gap-1.5">${ICON.good}<span class="break-words"><b>${esc(x.name || '')} ${esc(x.number || '')}</b> — có trong kho (${esc(x.document_key)})</span></div>` : banner('warning', esc(x.warning || 'Kho chưa có luật này.'))}</li>`).join('')}</ul></div>`
        : (pv.kind === 'base' ? '<div class="text-[13px] text-neutral-600">Không sửa luật nào khác.</div>' : '')}
      ${rp.length ? `<div><div class="text-[12px] text-neutral-500 mb-1">Làm hết hiệu lực</div><ul class="space-y-1.5 text-[13px]">${rp.map((r) => `<li><b>${esc(r.name || '')} ${esc(r.number || '')}</b>${r.units && r.units.length ? ' — ' + esc(r.units.join(', ')) : ''} ${r.effective_from ? 'từ ' + fd(r.effective_from) : ''} ${r.in_store ? '' : '<span class="text-neutral-500">(chưa có trong kho)</span>'}${r.evidence ? `<div class="legal-text border-l-2 border-neutral-300 pl-2 text-neutral-600">“${esc(r.evidence)}”</div>` : ''}</li>`).join('')}</ul></div>` : ''}
      ${pv.waiting_for_this ? banner('good', `Có <b>${pv.waiting_for_this}</b> chỉ dẫn từ các văn bản đã có trong kho đang chờ luật này; sẽ được áp dụng khi luật vào kho.`) : ''}
      ${pv.replace_note ? banner('info', esc(pv.replace_note)) : ''}
    </div>`;
  }

  function opsBlock(pv) {
    const ops = pv.operations || [];
    if (!ops.length) return `<div class="card p-4"><h3 class="text-[14px] font-semibold">Chỉ dẫn sửa đổi</h3><div class="mt-1 text-[13px] text-neutral-600">Văn bản này không có chỉ dẫn sửa đổi luật khác.</div></div>`;
    return `<div class="card overflow-hidden"><div class="p-4 border-b border-neutral-100"><h3 class="text-[14px] font-semibold">Chỉ dẫn sửa đổi <span class="text-neutral-500 font-normal">· ${ops.length}</span></h3>
      <div class="text-[12px] text-neutral-500">Bấm một dòng để xem câu chữ gốc của chỉ dẫn.</div></div>
      <div class="overflow-x-auto"><table class="w-full text-[13px]"><thead class="text-left text-[11.5px] text-neutral-500 bg-neutral-50"><tr>
        <th class="px-4 py-2 font-medium whitespace-nowrap">Vị trí</th><th class="px-3 py-2 font-medium">Thao tác</th><th class="px-3 py-2 font-medium whitespace-nowrap">Hiệu lực từ</th>
        <th class="px-3 py-2 font-medium whitespace-nowrap">Trạng thái</th><th class="px-3 py-2 font-medium min-w-[180px]">Lý do</th></tr></thead><tbody>
      ${ops.map((o, i) => {
        const [lab, tone] = REVIEW_VI[o.review_status] || [o.review_status, 'warning'];
        return `<tr class="op-row border-t border-neutral-100 hover:bg-neutral-50 cursor-pointer align-top" data-i="${i}" tabindex="0">
          <td class="px-4 py-2.5 whitespace-nowrap">${esc(o.source_locator)}</td><td class="px-3 py-2.5 min-w-[200px]">${esc(o.description)}</td>
          <td class="px-3 py-2.5 whitespace-nowrap tabular">${o.effective_from ? fd(o.effective_from) : '<span style="color:var(--warning-text)">chưa rõ</span>'}</td>
          <td class="px-3 py-2.5 whitespace-nowrap"><span class="inline-flex items-center gap-1.5" style="color:var(--${tone}-text)">${ICON[tone] || ''}${esc(lab)}</span></td>
          <td class="px-3 py-2.5 text-neutral-600">${(o.reasons_vi || []).map(esc).join('; ') || '<span class="text-neutral-400">—</span>'}</td></tr>
          <tr class="${L.openOp === i ? '' : 'hidden'}" data-for="${i}"><td colspan="5" class="px-4 pb-3"><div class="legal-text bg-neutral-50 border border-neutral-200 rounded-lg p-3 max-h-[260px] overflow-y-auto">${esc(o.excerpt || '')}</div></td></tr>`;
      }).join('')}</tbody></table></div></div>`;
  }

  async function ensurePreview() {
    const d = L.cur;
    if (d.state !== 'step2' || d.preview) return;
    $('legal-step').innerHTML = '<div class="card p-6 text-center text-[13px] text-neutral-500">Đang phân tích văn bản…</div>';
    try {
      const nd = await api('POST', `/api/legal/uploads/${d.upload_id}/fields`, { values: {}, by: who() || 'hệ thống' });
      showDraft(nd, 2);
    } catch (e) { L.cur.preview = null; renderStep2(true); flash(esc(e.message), 'critical'); }
  }

  function renderStep2(skipEnsure) {
    const d = L.cur, pv = d.preview, atStep2 = d.state === 'step2';
    if (atStep2 && !pv && !skipEnsure) { ensurePreview(); return; }
    const buttons = atStep2
      ? '<button id="b-relookup" class="btn-ghost">Tra lại vbpl</button><button id="b-back" class="btn-ghost">← Quay lại bước ①</button><button id="b-confirm2" class="btn-primary">Hiểu đúng, sang bước ③</button>'
      : '<button id="b-back" class="btn-ghost">← Quay lại bước ①</button>';
    $('legal-step').innerHTML = `<div class="space-y-4">
      ${atStep2 ? '' : banner('info', 'Bạn đã xác nhận bước này. Đang xem lại, không sửa được.')}
      ${fieldsForm(d)}${pv ? targetsBlock(pv) + effectivityBlock(pv.effectivity) + opsBlock(pv) : ''}
      ${stepFooter(buttons + (atStep2 ? cancelBtn() : ''))}</div>`;
    bindCancel();
    const inputs = [...document.querySelectorAll('#legal-step input[data-f]')];
    const dirtyValues = () => Object.fromEntries(inputs.filter((i) => i.value !== i.dataset.orig).map((i) => [i.dataset.f, i.value]));
    const refresh = () => {
      const n = Object.keys(dirtyValues()).length;
      L.dirty = n > 0;
      $('b-save').disabled = !atStep2 || !n;
      $('save-hint').textContent = n ? `${n} trường đã sửa, chưa lưu` : '';
    };
    inputs.forEach((i) => { i.disabled = !atStep2; i.oninput = refresh; });
    $('b-save').onclick = () => { if (needBy()) saveFields(); };
    document.querySelectorAll('.op-row').forEach((tr) => {
      const toggle = () => { L.openOp = L.openOp === +tr.dataset.i ? null : +tr.dataset.i; const row = document.querySelector(`#legal-step tr[data-for="${tr.dataset.i}"]`); document.querySelectorAll('#legal-step tr[data-for]').forEach((r) => { if (r !== row) r.classList.add('hidden'); }); row.classList.toggle('hidden', L.openOp !== +tr.dataset.i); };
      tr.onclick = toggle; tr.onkeydown = (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggle(); } };
    });
    $('b-back').onclick = () => { L.view = 1; render(); };
    const rl = $('b-relookup');
    if (rl) rl.onclick = () => act(async () => { const nd = await api('POST', `/api/legal/uploads/${d.upload_id}/relookup`, {}); showDraft(nd); flash(nd.source_verified ? 'Đã đối chiếu với vbpl.' : 'Không tra được vbpl (không tìm thấy hoặc mạng lỗi).', nd.source_verified ? 'good' : 'warning'); loadHistory(); }, 'Đang tra vbpl…');
    const c2 = $('b-confirm2');
    if (c2) c2.onclick = () => {
      if (L.dirty) { flash('Bạn đã sửa thông tin nhưng chưa lưu — hãy bấm "Lưu thông tin" trước.', 'critical'); return; }
      if (needBy()) act(async () => { showDraft(await api('POST', `/api/legal/uploads/${d.upload_id}/confirm-understanding`, { by: who() })); loadHistory(); });
    };
  }

  function saveFields() {
    const d = L.cur;
    const values = Object.fromEntries([...document.querySelectorAll('#legal-step input[data-f]')].filter((i) => i.value !== i.dataset.orig).map((i) => [i.dataset.f, i.value]));
    act(async () => {
      const before = d.state;
      const nd = await api('POST', `/api/legal/uploads/${d.upload_id}/fields`, { values, by: who() });
      L.dirty = false;
      showDraft(nd);
      if (nd.state !== before || L.view === 1) flash('Số hiệu / loại văn bản đã đổi, kho có văn bản cùng số hiệu — hãy xem lại so sánh ở bước ①.', 'warning');
      else flash('Đã lưu và phân tích lại văn bản.', 'good');
      loadHistory();
    }, 'Đang lưu và phân tích lại…');
  }

  // ------------------------------------------------------------------ ③ Đưa vào kho
  function stopPoll() { if (L.timer) { clearTimeout(L.timer); L.timer = null; } L.jobId = null; }

  function stageIndex(job) {
    // "Kiểm tra & công bố" là một giai đoạn; "finalizing" (việc xong, đang cập nhật bản nháp) vẫn đang chạy: giai đoạn chỉ mục
    const state = job.state === 'publishing' ? 'validating' : job.state === 'finalizing' ? 'indexing' : job.state;
    const i = JOB_STAGES.findIndex(([k]) => k === state);
    return i < 0 ? 0 : i;
  }
  function stagesHtml(job) {
    const cur = stageIndex(job), p = job.progress;
    const failed = job.state === 'failed' || job.state === 'index_failed';
    return `<ol class="space-y-1.5" aria-live="polite">${JOB_STAGES.map(([k, label], i) => {
      let text = label;
      if (k === 'building' && p && p.stage === 'build' && p.total) text += ` (${p.done}/${p.total})`;
      let icon, color = 'var(--ink-3)';
      if (failed && i === cur) { icon = ICON.critical; color = 'var(--critical-text)'; }
      else if (i < cur || job.state === 'done') { icon = ICON.good; color = 'var(--good-text)'; }
      else if (i === cur) { icon = '<span class="inline-block w-3.5 h-3.5 rounded-full border-2 border-neutral-400 border-t-neutral-900 animate-spin"></span>'; color = 'var(--ink)'; }
      else icon = '<span class="inline-block w-3.5 h-3.5 rounded-full border border-neutral-300"></span>';
      return `<li class="flex items-center gap-2 text-[13px]" style="color:${color}">${icon}${esc(text)}</li>`;
    }).join('')}</ol>`;
  }

  function resultHtml(d) {
    const laws = (d.result && d.result.laws) || [];
    return `<div class="card p-4 space-y-2"><h3 class="text-[14px] font-semibold">Kết quả theo luật</h3>
      ${laws.length ? `<div class="overflow-x-auto"><table class="w-full text-[13px]"><thead class="text-left text-[11.5px] text-neutral-500 bg-neutral-50"><tr><th class="px-3 py-2 font-medium">Luật</th><th class="px-3 py-2 font-medium text-right whitespace-nowrap">Điều có phiên bản mới</th><th class="px-3 py-2 font-medium text-right whitespace-nowrap">Mục duyệt mới</th><th class="px-3 py-2"></th></tr></thead><tbody>
        ${laws.map((l) => `<tr class="border-t border-neutral-100"><td class="px-3 py-2 min-w-[180px]"><div class="font-medium break-words">${esc(l.title)}</div><div class="text-[11.5px] text-neutral-500 break-all">${esc(l.document_key)}</div></td>
          <td class="px-3 py-2 text-right tabular">${l.changed_provisions}</td><td class="px-3 py-2 text-right tabular">${l.new_review_items}</td>
          <td class="px-3 py-2 whitespace-nowrap"><a class="underline" href="${esc(l.review_url)}">Mở ở /review →</a></td></tr>`).join('')}</tbody></table></div>`
        : '<div class="text-[13px] text-neutral-600">Không có luật nào thay đổi phiên bản.</div>'}</div>`;
  }

  function renderStep3() {
    const d = L.cur, st = d.state;
    const pv = d.preview, c3 = d.confirmations.step3;
    if (st === 'step3') {
      $('legal-step').innerHTML = `<div class="space-y-4"><div class="card p-4 space-y-3"><h3 class="text-[14px] font-semibold">Sẵn sàng đưa vào kho</h3>
        <ul class="list-disc pl-5 text-[13px] space-y-1">
          <li>${d.replace ? '<b>Thay thế</b> bản đang có trong kho' : '<b>Văn bản mới</b> của kho'}: ${esc(fieldVal(d, 'title') || '')} ${esc(fieldVal(d, 'doc_number') || '')}.</li>
          ${pv ? `<li>${esc(KIND_VI[pv.kind] || '')}; ${(pv.operations || []).length} chỉ dẫn sửa đổi${pv.waiting_for_this ? `, ${pv.waiting_for_this} chỉ dẫn từ văn bản khác sẽ được áp dụng` : ''}.</li>` : ''}
          <li>Toàn kho sẽ được dựng lại ở vùng tạm, kiểm tra rồi mới công bố.</li>
          <li>Chat chỉ chuyển sang dữ liệu mới khi mọi thứ xong; nếu lỗi, chat vẫn dùng dữ liệu cũ.</li></ul>
        <label class="block"><span class="text-[12px] text-neutral-600">Ghi chú (không bắt buộc)</span><textarea id="l-note" rows="2" class="lf-input mt-0.5"></textarea></label>
        <div class="flex flex-wrap items-center gap-2"><button id="b-submit" class="btn-primary">Đưa vào kho luật</button><button id="b-back2" class="btn-ghost">← Quay lại bước ②</button>${cancelBtn()}</div>
        <div class="text-[12px] text-neutral-500">Người thực hiện: nhập ở ô phía trên.</div></div></div>`;
      bindCancel();
      $('l-note').value = L.note;
      $('l-note').oninput = () => { L.note = $('l-note').value; };
      $('b-back2').onclick = () => { L.view = 2; render(); };
      $('b-submit').onclick = () => { if (needBy()) act(async () => {
        const { job_id } = await api('POST', `/api/legal/uploads/${d.upload_id}/submit`, { by: who(), note: L.note });
        L.note = '';
        showDraft(await api('GET', `/api/legal/uploads/${d.upload_id}`));
        loadHistory();
      }, 'Đang gửi vào hàng đợi…'); };
      return;
    }
    if (st === 'cancelled') { $('legal-step').innerHTML = banner('info', 'Bản nháp đã huỷ.'); return; }

    // queued / building / published / failed / stale
    const job = d.job || (st === 'published' ? { state: d.index_failed ? 'index_failed' : 'done' } : { state: 'queued' });
    let html = '';
    if (st === 'queued' || st === 'building') {
      html = `<div class="card p-4 space-y-3"><h3 class="text-[14px] font-semibold">Đang đưa vào kho${c3 ? ` · ${esc(c3.by)}` : ''}</h3>${stagesHtml(job)}</div>`;
    } else if (st === 'published') {
      html = `${d.index_failed
        ? banner('warning', `<b>Kho đã cập nhật nhưng chỉ mục hỏi đáp lỗi, chat đang dùng dữ liệu trước đó.</b>${d.index_error ? `<div class="text-[12px] mt-1">${esc(d.index_error)}</div>` : ''}<div class="mt-2"><button id="b-reindex" class="btn-primary">Dựng lại chỉ mục</button></div>`)
        : banner('good', '<b>Đã vào kho.</b> Chat đã chuyển sang dữ liệu mới.')}
        <div class="card p-4"><h3 class="text-[14px] font-semibold mb-2">Các giai đoạn</h3>${stagesHtml(job.state === 'index_failed' || d.index_failed ? { state: 'index_failed', progress: null } : { state: 'done' })}</div>${resultHtml(d)}`;
    } else if (st === 'failed') {
      html = `${banner('critical', `<b>Không đưa vào kho được.</b> Chat vẫn dùng dữ liệu cũ.<div class="mt-1 break-words">${esc(d.error || 'Lỗi không rõ')}</div>`)}
        <div class="flex flex-wrap gap-2"><button id="b-retry" class="btn-primary">Thử lại</button><button id="b-cancel" class="btn-ghost" style="color:var(--critical-text)">Huỷ</button></div>`;
    } else if (st === 'stale') {
      html = `${banner('critical', `<b>${esc(d.error || 'Kho đã thay đổi từ lúc bạn so sánh — hãy xem lại bước ①')}</b><div class="mt-1">Hãy huỷ bản nháp này và tải văn bản lên lại để so sánh với kho mới.</div>`)}
        <div class="flex flex-wrap gap-2"><button id="b-view1" class="btn-ghost">Xem lại bước ①</button><button id="b-cancel" class="btn-ghost" style="color:var(--critical-text)">Huỷ bản nháp</button></div>`;
    }
    $('legal-step').innerHTML = `<div class="space-y-4">${html}</div>`;
    bindCancel();
    const v1 = $('b-view1'); if (v1) v1.onclick = () => { L.view = 1; render(); };
    const ri = $('b-reindex');
    if (ri) ri.onclick = () => act(async () => { const { job_id } = await api('POST', '/api/legal/reindex', {}); startPoll(job_id, 'reindex'); }, 'Đang đưa việc dựng chỉ mục vào hàng đợi…');
    const rt = $('b-retry');
    if (rt) rt.onclick = () => { if (needBy()) act(async () => { await api('POST', `/api/legal/uploads/${d.upload_id}/retry`, { by: who() }); showDraft(await api('GET', `/api/legal/uploads/${d.upload_id}`)); loadHistory(); }, 'Đang thử lại…'); };
    if (st === 'queued' || st === 'building') startPoll(d.job && d.job.job_id, 'upload');
  }

  // polling /api/legal/jobs/{id} mỗi 1,5 giây
  function startPoll(jobId, kind) {
    stopPoll();
    const d = L.cur, uid = d.upload_id;
    L.jobId = jobId || null;
    const tick = async () => {
      if (!L.cur || L.cur.upload_id !== uid || L.view !== 3) return stopPoll();
      try {
        let job = null;
        if (jobId) {
          try { job = await api('GET', '/api/legal/jobs/' + encodeURIComponent(jobId)); } catch (e) { job = null; }
        }
        const terminal = job && ['done', 'failed', 'index_failed'].includes(job.state);
        if (!job || terminal) {            // việc đã kết thúc (hoặc server khởi động lại): đọc lại bản nháp
          const nd = await api('GET', `/api/legal/uploads/${uid}`);
          if (!job && (nd.state === 'queued' || nd.state === 'building')) {
            L.cur = nd; renderStep3(); return;      // renderStep3 -> startPoll: luôn đúng một timer
          }
          showDraft(nd); loadHistory(); loadPending();
          if (kind === 'reindex') flash(job && job.state === 'done' ? 'Đã dựng lại chỉ mục, chat đã chuyển sang dữ liệu mới.' : esc((job && job.error) || 'Dựng lại chỉ mục lỗi.'), job && job.state === 'done' ? 'good' : 'critical');
          return;
        }
        const box = document.querySelector('#legal-step .card ol');
        if (box) box.outerHTML = stagesHtml(job);
        else { L.cur.job = job; renderStep3(); return; }
      } catch (e) { flash(esc(e.message), 'critical'); }
      L.timer = setTimeout(tick, 1500);
    };
    L.timer = setTimeout(tick, 1500);
  }

  // ------------------------------------------------------------------ khởi tạo
  window.legalInit = () => {
    $('legal-upload').onclick = doUpload;
    const fi = $('legal-file'), dz = $('legal-dropzone');
    fi.onchange = () => { picked = fi.files[0] || null; fi.value = ''; renderPicked(); };
    ['dragenter', 'dragover'].forEach((t) => dz.addEventListener(t, (e) => { e.preventDefault(); dz.classList.add('drag'); }));
    ['dragleave', 'drop'].forEach((t) => dz.addEventListener(t, (e) => { e.preventDefault(); dz.classList.remove('drag'); }));
    dz.addEventListener('drop', (e) => { picked = e.dataTransfer.files[0] || null; renderPicked(); });
    document.querySelectorAll('#legal-steps .step-btn').forEach((b) => {
      b.onclick = () => { if (b.disabled || !L.cur) return; stopPoll(); L.view = +b.dataset.step; render(); };
    });
    loadHistory(); loadPending();
  };
})();
