// Phần dùng chung cho hỏi đáp hợp đồng trên đồ thị (spec 2026-11-17-contract-ask-page-design):
// đọc luồng SSE, gọi /api/contracts/{cid}/ask/stream, vẽ câu trả lời và các bước agent.
(function () {
  'use strict';
  const API = '/api/contracts';
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const CONF = { answer: ['Trả lời được', 'var(--good-text)'], partial: ['Trả lời một phần', 'var(--warning-text)'],
    cannot: ['Không trả lời được', 'var(--critical-text)'] };

  // Đọc luồng SSE `data: {json}`; gọi onEvent từng sự kiện; trả sự kiện cuối (done / error) hoặc ném lỗi khi đứt.
  async function readSse(res, onEvent) {
    if (!res.ok || !res.body) {
      const data = await res.json().catch(() => ({}));
      const err = new Error(data.error || `Lỗi server (${res.status})`); err.status = res.status; throw err;
    }
    const reader = res.body.getReader(), dec = new TextDecoder();
    let buf = '', last = null;
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true }).replace(/\r\n/g, '\n');
      let i;
      while ((i = buf.indexOf('\n\n')) >= 0) {
        const chunk = buf.slice(0, i); buf = buf.slice(i + 2);
        const line = chunk.split('\n').find(l => l.startsWith('data: '));
        if (!line) continue;
        last = JSON.parse(line.slice(6));
        onEvent(last);
      }
    }
    if (!last || (last.type !== 'done' && last.type !== 'error')) throw new Error('Mất kết nối giữa chừng — hãy hỏi lại.');
    return last;
  }

  // Hỏi agent đồ thị; onEvent nhận step / done / error; trả sự kiện cuối.
  async function ask(cid, { question, history, userFacts }, onEvent) {
    const res = await fetch(`${API}/${encodeURIComponent(cid)}/ask/stream`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question, history: history || [], user_facts: userFacts || {} }) });
    return readSse(res, onEvent);
  }

  // Hiệu lực, khoảng hiệu lực và nguồn gốc của một căn cứ luật (xem law_entry trong rag/bridge/view.py).
  function lawMeta(a) {
    const bits = [];
    if (a.note) bits.push(`<span style="color:var(--critical-text)">${esc(a.note)}</span>`);
    if (a.valid_from) bits.push(`Hiệu lực từ ${esc(a.valid_from)}${a.valid_to ? ' đến ' + esc(a.valid_to) : ''}`);
    if (a.source_url && /^https?:\/\//.test(a.source_url)) bits.push(`<a href="${esc(a.source_url)}" target="_blank" rel="noopener" class="underline">Xem văn bản gốc</a>`);
    return bits.length ? `<div class="text-[11.5px] text-neutral-500 mt-0.5">${bits.join(' · ')}</div>` : '';
  }

  // ---------------------------------------------------------------- đường đi trên đồ thị
  const TYPE_VI = { Contract: 'Hợp đồng', Part: 'Phần', Unit: 'Điều khoản', Value: 'Giá trị', Party: 'Bên',
    ConceptInstance: 'Khái niệm', ContractFact: 'Dữ kiện' };
  const REL_VI = { ABOUT: 'khái niệm nói về điều khoản', AMENDS: 'sửa đổi', REFERS_TO: 'dẫn chiếu tới',
    HAS_VALUE: 'có giá trị', CHILD_OF: 'là phần con của', HAS_UNIT: 'chứa điều khoản', HAS_PART: 'có phần',
    HAS_FACT: 'có dữ kiện', EVIDENCE: 'bằng chứng nằm ở', HOLDER: 'quyền thuộc về', HAS_PARTY: 'có bên' };
  const shortId = id => String(id || '').split(':').slice(-1)[0] || '?';
  const TOOL_VI = {
    find_units: a => a.text ? `Tìm điều khoản chứa “${a.text}”` : `Tìm điều khoản ${a.label ? '“' + a.label + '”' : ''}`,
    find_concept: a => `Tìm vị trí khái niệm ${a.concept_id || ''}`,
    expand: a => `Mở các nút kề ${a.node_id ? 'của ' + shortId(a.node_id) : ''}${a.rel_types ? ' qua ' + a.rel_types.join(', ') : ''}${a.direction && a.direction !== 'both' ? ` (chiều ${a.direction === 'out' ? 'ra' : 'vào'})` : ''}`,
    find_path: a => `Tìm đường ${a.src ? 'từ ' + shortId(a.src) + ' tới ' + shortId(a.dst) : 'giữa hai nút'}`,
    subgraph: a => `Lấy đồ thị con ${a.node_id ? 'quanh ' + shortId(a.node_id) : ''}`,
    contract_facts: a => a.name ? `Đọc dữ kiện “${a.name}” tại ngày soát` : 'Đọc dữ kiện hợp đồng tại ngày soát',
    law_text_at: a => `Đọc lời văn điều luật ${a.pid || ''}${a.day ? ' ngày ' + a.day : ''}`,
    law_changes: a => `Xem các phiên bản điều luật ${a.pid || ''}${a.to ? ' tới ' + a.to : ''}`,
    law_guidance: a => `Tìm văn bản hướng dẫn ${a.pid || ''}`,
    law_references: a => `Xem dẫn chiếu ${a.direction === 'in' ? 'tới' : 'từ'} ${a.pid || ''}`,
    concept_basis: a => `Lấy căn cứ luật (neo) của khái niệm ${a.concept_id || ''}`,
    check_concept: a => `Chạy bộ kiểm luật cho khái niệm ${a.concept_id || ''}`,
    cypher_query: () => 'Truy vấn Cypher chỉ đọc trên đồ thị hợp đồng',
  };
  const isAppendix = p => /^phụ lục/i.test(p.label || '');
  const typeVi = p => p.node_type === 'Unit' && isAppendix(p) ? 'Phụ lục' : (TYPE_VI[p.node_type] || p.node_type || 'Nút');
  const nodeName = p => p.concept_label || p.label || shortId(p.node_id);
  const toolName = t => (TOOL_VI[t] ? TOOL_VI[t]({}).trim() : t);

  function edgeHtml(e) {
    if (!e) return '';
    if (!e.verified) return `<div class="pl-3 py-0.5 text-[12px]" style="color:var(--critical-text)">│ ✗ không có cạnh nối trực tiếp trong đồ thị — agent tự nối</div>`;
    const pr = e.props || {};
    const extra = [pr.valid_from ? 'hiệu lực từ ' + esc(pr.valid_from) : '', pr.raw ? '“' + esc(pr.raw) + '”' : ''].filter(Boolean).join(' · ');
    const back = e.dir === 'in' ? ' <span class="text-neutral-400">(chiều ngược: nút dưới → nút trên)</span>' : '';
    return `<div class="pl-3 py-0.5 text-[12px] text-neutral-600">│ <b>${esc(e.rel)}</b> — ${esc(REL_VI[e.rel] || '')}${back}
      <span style="color:var(--good-text)">✓</span>${extra ? ` <span class="text-neutral-500">· ${extra}</span>` : ''}</div>`;
  }

  function textHtml(p) {
    const full = p.text_full || p.text || '';
    if (!full) return '';
    if (full.length <= 160) return `<div class="text-[12px] text-neutral-600 whitespace-pre-wrap">${esc(full)}</div>`;
    return `<details class="text-[12px] text-neutral-600"><summary class="cursor-pointer list-none">${esc(full.slice(0, 160))}… <span class="underline">xem toàn văn</span></summary>
      <div class="whitespace-pre-wrap mt-1">${esc(full)}</div></details>`;
  }

  function lawLinksHtml(p) {
    if (!(p.law_links || []).length) return '';
    const read = p.law_links.some(l => l.read_by_agent);
    return `<div class="pl-3 py-0.5 text-[12px] text-neutral-600">│ <b>neo luật</b> — căn cứ của khái niệm theo danh mục ·
        ${read ? '<span style="color:var(--good-text)">agent đã đọc ✓</span>' : '<span class="text-neutral-400">agent không đọc trong lượt này</span>'}</div>
      <div class="space-y-1">${p.law_links.map(l => `<div class="rounded-lg px-2 py-1.5" style="background:#f7f7f8">
        <div class="flex flex-wrap items-baseline gap-x-2"><span class="chip">Luật</span><b>${esc(l.citation || l.pid)}</b></div>${lawMeta(l)}
        ${l.text ? textHtml({ text_full: l.text }) : ''}</div>`).join('')}</div>`;
  }

  function nodeHtml(p) {
    const found = p.found_at ? `<span class="text-[11.5px] text-neutral-400">bước ${p.found_at.step} · ${esc(toolName(p.found_at.tool))}</span>` : '';
    return `<div class="rounded-lg border border-neutral-200 px-2 py-1.5">
      <div class="flex flex-wrap items-baseline gap-x-2"><span class="chip">${esc(typeVi(p))}</span><b>${esc(nodeName(p))}</b>${found}</div>
      ${textHtml(p)}</div>`;
  }

  function pathHtml(d) {
    const path = d.path || [];
    if (!path.length) return '';
    const edges = path.slice(1).map(p => p.edge).filter(Boolean);
    const ok = edges.every(e => e.verified);
    return `<section><div class="flex flex-wrap items-baseline gap-2 mb-1"><div class="field-label">Đường đi trên đồ thị</div>
        ${edges.length ? `<span class="text-[11.5px]" style="color:${ok ? 'var(--good-text)' : 'var(--critical-text)'}">${ok ? '✓ mọi cạnh có thật trong đồ thị' : '⚠ có cạnh không có trong đồ thị'}</span>` : ''}</div>
      <div class="space-y-0.5">${path.map(p => edgeHtml(p.edge) + nodeHtml(p) + lawLinksHtml(p)).join('')}</div></section>`;
  }

  function unusedHtml(d) {
    const u = d.seen_unused || [];
    if (!u.length) return '';
    return `<details class="text-[12.5px]"><summary class="cursor-pointer text-neutral-500 list-none"><span class="chev">▸</span> Đã xem nhưng không dùng (${u.length})</summary>
      <div class="flex flex-wrap gap-1.5 mt-1.5">${u.map(p => `<span class="chip" title="${esc(p.node_id)}">${esc(typeVi(p))}: ${esc(nodeName(p))}${p.found_at ? ` · bước ${p.found_at.step}` : ''}</span>`).join('')}</div></details>`;
  }

  // Sơ đồ nhỏ của đường đi (trang /contracts/ask): nút = hộp, cạnh = mũi tên theo đúng chiều, nhãn = loại cạnh.
  function diagramHtml(d) {
    const path = d.path || [];
    if (path.length < 2) return '';
    const W = 150, H = 50, G = 86, P = 8;
    const law = path.findIndex(p => (p.law_links || []).length);
    const rows = law >= 0 ? 2 : 1;
    const width = P * 2 + path.length * W + (path.length - 1) * G, height = P * 2 + rows * H + (rows - 1) * 40;
    const cut = (s, n) => { s = String(s || ''); return s.length > n ? s.slice(0, n - 1) + '…' : s; };
    const box = (x, y, kind, name, dashed) => `<rect x="${x}" y="${y}" width="${W}" height="${H}" rx="8" fill="none" stroke="currentColor" stroke-opacity=".35"${dashed ? ' stroke-dasharray="4 3"' : ''}/>
      <text x="${x + 8}" y="${y + 18}" font-size="10.5" fill="currentColor" fill-opacity=".55">${esc(kind)}</text>
      <text x="${x + 8}" y="${y + 36}" font-size="12" font-weight="600" fill="currentColor">${esc(cut(name, 21))}</text>`;
    let svg = '';
    path.forEach((p, i) => {
      const x = P + i * (W + G);
      svg += box(x, P, typeVi(p), nodeName(p), false);
      if (!i || !p.edge) return;
      const x0 = x - G, x1 = x, y = P + H / 2, e = p.edge;
      const color = e.verified ? 'var(--good-text, #067647)' : 'var(--critical-text, #b42318)';
      const [a, b] = e.dir === 'in' ? [x1 - 2, x0 + 2] : [x0 + 2, x1 - 2];
      const tip = e.dir === 'in' ? 6 : -6;
      svg += `<line x1="${a}" y1="${y}" x2="${b}" y2="${y}" stroke="${color}" stroke-width="1.5"${e.verified ? '' : ' stroke-dasharray="4 3"'}/>
        <path d="M${b} ${y} l${tip} -4 l0 8 z" fill="${color}"/>
        <text x="${(x0 + x1) / 2}" y="${y - 7}" font-size="10" text-anchor="middle" fill="${color}">${esc(e.verified ? e.rel : '?')}</text>`;
    });
    if (law >= 0) {
      const x = P + law * (W + G), y0 = P + H, y1 = P + H + 40;
      const n = path[law].law_links.length;
      svg += `<line x1="${x + W / 2}" y1="${y0 + 2}" x2="${x + W / 2}" y2="${y1 - 2}" stroke="currentColor" stroke-opacity=".5" stroke-dasharray="3 3"/>
        <text x="${x + W / 2 + 6}" y="${y0 + 24}" font-size="10" fill="currentColor" fill-opacity=".6">neo luật</text>
        ${box(x, y1, 'Graph luật', `${n} điều luật`, true)}`;
    }
    return `<section><div class="field-label mb-1">Sơ đồ đường đi</div><div class="overflow-x-auto"><svg width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" role="img" aria-label="Sơ đồ đường đi của agent trên đồ thị">${svg}</svg></div></section>`;
  }

  function answerHtml(d, opts = {}) {
    const [label, color] = CONF[d.confidence] || CONF.partial;
    const stats = d.stats || {};
    const linked = new Set((d.path || []).flatMap(p => (p.law_links || []).map(l => l.pid)));
    const rest = (d.law || []).filter(a => !linked.has(a.pid));         // căn cứ chưa nằm trên đường đi
    const law = rest.length ? `<section><div class="field-label mb-0.5">Căn cứ luật khác agent nêu</div><div class="space-y-1.5">${rest.map(a => a.citation
      ? `<div class="rounded-lg p-2" style="background:#f7f7f8"><div class="font-medium">${esc(a.citation)}</div>${lawMeta(a)}${a.text ? textHtml({ text_full: a.text }) : ''}</div>`
      : `<div class="text-[12px] text-neutral-500">${esc(a.pid)}</div>`).join('')}</div></section>` : '';
    const warn = (d.warnings || []).map(w => `<div class="text-[12px]" style="color:var(--warning-text)">⚠ ${esc(w)}</div>`).join('');
    return `<div class="space-y-3 text-[13px]">
      <div class="whitespace-pre-wrap text-[14.5px] leading-relaxed">${esc(d.answer)}</div>
      <div><span class="chip" style="color:${color}">${label}</span> <span class="text-[11.5px] text-neutral-400">${stats.steps ?? 0} bước${stats.seen != null ? ` · đã xem ${stats.seen} nút` : ''} · ${stats.seconds ?? '?'} s · ${esc(stats.backend || '')}</span></div>
      ${opts.diagram ? diagramHtml(d) : ''}${pathHtml(d)}${law}${unusedHtml(d)}${warn}</div>`;
  }

  function stepsHtml(steps, open) {
    if (!steps || !steps.length) return '';
    const rows = steps.map((s, i) => {
      const n = s.n || i + 1;
      const what = TOOL_VI[s.tool] ? TOOL_VI[s.tool](s.args || {}) : s.tool;
      const res = s.error ? `<span style="color:var(--critical-text)">✗ ${esc(s.error)}</span>`
        : s.n_nodes != null ? `<span class="text-neutral-500">→ ${s.n_nodes} nút</span>` : '';
      const mark = s.error ? '<span style="color:var(--critical-text)">✗</span>' : '<span style="color:var(--good-text)">✓</span>';
      return `<div class="border-l-2 border-neutral-200 pl-2">
        <div>${mark} <b>${n}. ${esc(what)}</b> ${res}${s.ms != null ? ` <span class="text-neutral-400">· ${s.ms} ms</span>` : ''}</div>
        ${s.thought ? `<div class="text-neutral-500"><span class="text-neutral-400">Lý do agent nêu:</span> ${esc(s.thought)}</div>` : ''}
        <details><summary class="cursor-pointer list-none text-[11.5px] text-neutral-400">JSON thô ▸</summary>
          <pre class="text-[11.5px] whitespace-pre-wrap text-neutral-600">${esc(JSON.stringify({ tool: s.tool, args: s.args }, null, 1))}</pre>
          <div class="text-[11.5px] text-neutral-400 break-all">${esc(s.result)}</div></details></div>`;
    }).join('');
    return open ? `<div class="space-y-1.5 text-[12.5px]">${rows}</div>`
      : `<details class="text-[12.5px]"><summary class="cursor-pointer text-neutral-500 list-none"><span class="chev">▸</span> Các bước agent đã đi (${steps.length})</summary><div class="space-y-1.5 mt-1.5">${rows}</div></details>`;
  }

  window.ContractQA = { esc, readSse, ask, answerHtml, stepsHtml, lawMeta };
})();
