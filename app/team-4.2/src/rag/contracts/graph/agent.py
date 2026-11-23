"""Agent chỉ đọc trên đồ thị hợp đồng (spec 2026-11-16-contract-graph-agent §5.7).

Mỗi lượt LLM nhận câu hỏi (đã che PII), ngữ cảnh hợp đồng, mô tả công cụ và các bước đã đi; trả đúng một JSON:
gọi một công cụ, hoặc kết luận kèm đường đi. Không công cụ nào ghi; kết luận pháp lý phải đi qua `check_concept`.
Hậu kiểm: đường đi phải gồm nút đã thấy trong lượt này và nối nhau bằng cạnh thật, nếu không hạ `partial`."""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from datetime import date
from typing import Callable, Literal

from rag.bridge.catalog import Catalog
from rag.contracts.graph.tools import Tool, call_tool
from rag.contracts.graph.view import ContractGraphView
from rag.contracts.llm_json import ContractAIError, _parse
from rag.quality.pii import MaskState, mask_text

_AGENT_PROMPT_TEMPLATE = """Bạn là trợ lý trả lời câu hỏi về MỘT <<DOCUMENT>> bằng cách đi trên đồ thị của hợp đồng.
Đồ thị: Contract -HAS_PART-> Part -HAS_UNIT-> Unit (Điều, khoản); Unit -REFERS_TO-> Unit (dẫn chiếu);
Unit -AMENDS-> Unit (phụ lục sửa điều khoản, có valid_from); Unit -HAS_VALUE-> Value; ConceptInstance -ABOUT-> Unit;
Contract -HAS_FACT-> ContractFact -EVIDENCE-> Unit. Luật đọc qua công cụ law_* với pid trong neo của khái niệm.

Mỗi lượt trả về ĐÚNG MỘT đối tượng JSON, một trong hai dạng:
  {"thought": "<vì sao>", "tool": "<tên công cụ>", "args": {...}}
  {"final": {"answer": "<câu trả lời tiếng Việt>", "path": ["<node_id>", ...], "law": ["<pid>", ...],
             "confidence": "answer" | "partial" | "cannot"}}
Quy tắc:
- Bắt đầu từ khái niệm (find_concept) hoặc điều khoản (find_units) liên quan tới câu hỏi, rồi đi theo cạnh.
- Đi theo dẫn chiếu (REFERS_TO) khi điều khoản viết "quy định tại Điều N"; xem AMENDS để biết phụ lục sửa gì, từ ngày nào.
- Nói một điều là đúng luật / trái luật / vi phạm thì PHẢI gọi check_concept trước và dựa vào kết quả của nó.
- "path": dãy node_id liền nhau trên đồ thị (mỗi cặp liền kề có cạnh), chỉ dùng node_id đã thấy trong kết quả công cụ.
- Không đủ dữ kiện thì nói rõ thiếu gì, confidence "partial" hoặc "cannot". Không bịa số liệu.
- cypher_query (chỉ có khi đồ thị nằm trên Neo4j): dùng cho câu đếm / liệt kê / tổng hợp; câu hỏi về một điều khoản
  thì ưu tiên công cụ khác. Thuộc tính: Unit{uid,label,text,part_id,level}, Part{kind,title,number},
  Value{kind,raw}, ContractFact{name,value,unit,quote}, ConceptInstance{concept_id,quote,slot_<tên>},
  AMENDS{kind,valid_from,raw}, REFERS_TO{raw}. Muốn đưa nút vào "path" thì RETURN cả x.node_id.
  Bị từ chối hoặc lỗi thì đọc lý do, sửa câu và thử lại.
- "history" (nếu có): các lượt hỏi đáp trước, dùng để hiểu câu hỏi nối tiếp.
- Ký hiệu dạng [HD_...] là thông tin cá nhân đã ẩn: giữ nguyên, không đoán.
- Khi payload có "force_final": true, phải trả "final" ngay từ những gì đã biết."""


def agent_prompt(ctx=None) -> str:
    """Prompt cho loại văn bản của gói đang dùng (`ctx.document_label`); None -> hợp đồng lao động."""
    return _AGENT_PROMPT_TEMPLATE.replace("<<DOCUMENT>>", getattr(ctx, "document_label", None) or "hợp đồng lao động")


AGENT_PROMPT = agent_prompt()          # bản cho gói labor (tên công khai cũ, giữ tương thích)

_LEGAL_CLAIM = re.compile(r"đúng luật|trái luật|trái pháp luật|vi phạm|hợp pháp|đúng quy định", re.IGNORECASE)
Confidence = Literal["answer", "partial", "cannot"]
_RANK = {"answer": 2, "partial": 1, "cannot": 0}


@dataclass
class GraphAnswer:
    answer: str
    path: list[dict]
    law: list[str]
    confidence: Confidence
    warnings: list[str] = field(default_factory=list)
    trace: list[dict] = field(default_factory=list)
    stats: dict = field(default_factory=dict)
    seen_unused: list[dict] = field(default_factory=list)   # nút agent đã thấy nhưng không đưa vào đường đi


def agent_context(view: ContractGraphView, catalog: Catalog, *, sign_date: date | None) -> dict:
    """Ngữ cảnh đầu lượt: các phần, điều khoản cấp cao nhất, khái niệm đã gán (kèm điều khoản)."""
    parts = [{"node_id": p["node_id"], "kind": p.get("kind"), "title": p.get("title", "")} for p in view.find("Part")]
    articles = [{"node_id": u["node_id"], "label": u.get("label")} for u in view.find("Unit")
                if not view.neighbors(u["node_id"], rel_types=["CHILD_OF"], direction="out")]
    concepts = []
    for ci in view.find("ConceptInstance"):
        about = view.neighbors(ci["node_id"], rel_types=["ABOUT"], direction="out")
        concept = catalog.concepts.get(ci["concept_id"])
        concepts.append({"concept_id": ci["concept_id"], "label": concept.label if concept else None,
                         "node_id": ci["node_id"], "about": about[0]["node"]["node_id"] if about else None})
    return {"contract_id": view.contract_id, "document_label": catalog.context.document_label,
            "sign_date": sign_date.isoformat() if sign_date else None,
            "parts": parts, "articles": articles, "concepts": concepts,
            "catalog": [{"concept_id": c.id, "label": c.label} for c in catalog.concepts.values()]}


def _node_ids(value, out: set[str], prefix: str | None = None) -> None:
    """Mã nút xuất hiện trong kết quả công cụ: khóa node_id/about/src/dst, và (kết quả Cypher) mọi chuỗi mang tiền tố
    mã nút của hợp đồng này `<contract_id>:`."""
    if isinstance(value, dict):
        for k, v in value.items():
            if k in ("node_id", "about", "src", "dst") and isinstance(v, str):
                out.add(v)
            _node_ids(v, out, prefix)
    elif isinstance(value, list):
        for v in value:
            _node_ids(v, out, prefix)
    elif prefix and isinstance(value, str) and (value.startswith(prefix) or value == prefix[:-1]):
        out.add(value)                     # prefix[:-1] = contract_id = mã nút Contract


def _summary(result: dict) -> str:
    text = json.dumps(result, ensure_ascii=False, default=str)
    return text if len(text) <= 300 else text[:300] + "…"


class GraphAgent:
    def __init__(self, llm, tools: dict[str, Tool], view: ContractGraphView, *, mask: MaskState, context: dict,
                 max_steps: int = 8):
        self.llm, self.tools, self.view, self.mask = llm, tools, view, mask
        self.context, self.max_steps = context, max_steps
        self.check_references = True       # tắt để đo đối chứng

    def _ask_llm(self, payload: dict) -> str:
        prompt = _AGENT_PROMPT_TEMPLATE.replace("<<DOCUMENT>>", self.context.get("document_label") or "hợp đồng lao động")
        return self.llm.complete(prompt, json.dumps(payload, ensure_ascii=False, default=str))

    def _history(self, history) -> list[dict]:
        """3 lượt cuối, mỗi chuỗi ≤500 ký tự, đã che PII; phần tử không phải dict bị bỏ."""
        def m(v) -> str:
            return mask_text(str(v or "")[:500], state=self.mask).masked_text
        turns = [h for h in history or [] if isinstance(h, dict)] if isinstance(history, list) else []
        return [{"query": m(h.get("query")), "answer": m(h.get("answer"))} for h in turns[-3:]]

    def ask(self, question: str, history: list[dict] | None = None,
            on_step: Callable[[dict], None] | None = None) -> GraphAnswer:
        """history: lượt hỏi đáp trước [{query, answer}]; on_step nhận {type: step, n, tool, thought, args, result}."""
        t0 = time.monotonic()
        q = mask_text(question, state=self.mask).masked_text
        hist = self._history(history)
        specs = [t.spec() for t in self.tools.values()]
        steps: list[dict] = []
        trace: list[dict] = []
        warnings: list[str] = []
        seen: set[str] = set()
        found_at: dict[str, tuple[int, str]] = {}   # nút -> (bước đầu tiên thấy nó, công cụ)
        calls = parse_errors = 0
        final = None
        force = nudged = False
        while final is None:
            payload = {"question": q, "context": self.context, "tools": specs, "steps": steps}
            if hist:
                payload["history"] = hist
            if force:
                payload["force_final"] = True
            calls += 1
            try:
                data = _parse(self._ask_llm(payload))
                if "final" not in data and not isinstance(data.get("tool"), str):
                    raise ContractAIError("thiếu 'tool' hoặc 'final'")
            except ContractAIError as exc:
                parse_errors += 1
                if parse_errors >= 2 or force:
                    final = {"answer": "Không trả lời được: AI trả kết quả không hợp lệ.", "path": [], "law": [],
                             "confidence": "cannot"}
                    warnings.append("AI trả JSON không hợp lệ")
                    break
                steps.append({"error": f"JSON không hợp lệ ({exc}); trả lại đúng một đối tượng JSON"})
                continue
            except Exception:  # noqa: BLE001 — lỗi mạng / API
                final = {"answer": "Không gọi được AI lúc này, hãy thử lại.", "path": [], "law": [],
                         "confidence": "cannot"}
                warnings.append("Không gọi được AI")
                break
            if "final" in data:
                final = data["final"] if isinstance(data["final"], dict) else {}
                unread = [] if nudged or force or not self.check_references else self._unread_references(final, seen)
                if unread:                 # chặn kết luận một lần: còn điều khoản được dẫn chiếu chưa đọc
                    nudged = True
                    steps.append({"error": "Kết luận dựa trên điều khoản có dẫn chiếu chưa đọc; đọc chúng (expand / "
                                           "find_units) rồi kết luận lại", "unread_references": unread})
                    final = None
                    continue
                break
            if force:                      # đã ép kết luận mà vẫn gọi công cụ
                final = {"answer": "Không đi tới kết luận trong giới hạn bước.", "path": [], "law": [],
                         "confidence": "cannot"}
                break
            name, args = data["tool"], data.get("args") or {}
            t1 = time.monotonic()
            result = call_tool(self.tools, name, args)
            got: set[str] = set()
            _node_ids(result, got, f"{self.view.contract_id}:")
            if "error" not in result:      # nút agent đã nêu và công cụ đã giải được
                got.update(v for k, v in args.items() if k in ("node_id", "src", "dst") and isinstance(v, str))
            seen |= got
            for nid in got:
                found_at.setdefault(nid, (len(trace) + 1, name))
            steps.append({"thought": data.get("thought", ""), "tool": name, "args": args, "result": result})
            trace.append({"thought": data.get("thought", ""), "tool": name, "args": args,
                          "result": _summary(result), "ms": round((time.monotonic() - t1) * 1000),
                          "error": str(result["error"]) if "error" in result else None,
                          "nodes": sorted(got)[:50], "n_nodes": len(got)})
            if on_step is not None:
                t = trace[-1]
                on_step({"type": "step", "n": len(trace), **t})
            if len(trace) >= self.max_steps:
                force = True
                warnings.append(f"Đạt giới hạn {self.max_steps} bước: kết luận từ những gì đã đi")
        return self._finish(final, force, steps, trace, warnings, seen, calls, t0, found_at)

    def _unread_references(self, final: dict, seen: set[str]) -> list[str]:
        """Điều khoản (Điều / khoản / điểm) mà các Unit trên đường đi dẫn chiếu tới nhưng chưa xuất hiện trong lượt này.
        Dẫn chiếu tới cả một phụ lục ("Phụ lục 01") không tính: đó là văn bản đính kèm, không phải chỗ đặt giá trị."""
        out: list[str] = []
        for nid in final.get("path") or []:
            if not isinstance(nid, str) or nid not in seen:
                continue
            for h in self.view.neighbors(nid, rel_types=["REFERS_TO"], direction="out"):
                target = h["node"]["node_id"]
                if (target not in seen and target not in out
                        and not str(h["props"].get("raw") or "").casefold().startswith("phụ lục")):
                    out.append(target)
        return out

    def _finish(self, final, forced, steps, trace, warnings, seen, calls, t0, found_at=None) -> GraphAnswer:
        conf = final.get("confidence") if final.get("confidence") in _RANK else "partial"
        answer = str(final.get("answer") or "")
        path_ids = [p for p in final.get("path") or [] if isinstance(p, str)]
        law = [p for p in final.get("law") or [] if isinstance(p, str)]

        def lower(to: Confidence, why: str):
            nonlocal conf
            if _RANK[conf] > _RANK[to]:
                conf = to
            warnings.append(why)

        if forced and conf == "answer":
            conf = "partial"
        bad = [p for p in path_ids if p not in seen or self.view.node(p) is None]
        bad_edges = [(a, b) for a, b in zip(path_ids, path_ids[1:])
                     if a != b and not self.view.path(a, b, max_hops=1)]
        if bad or bad_edges:
            lower("partial", "đường đi có nút/cạnh không có trong đồ thị hoặc chưa thấy trong lượt này")
        unread = self._unread_references(final, seen) if self.check_references else []
        if unread:
            lower("partial", "kết luận chưa đọc điều khoản được dẫn chiếu: " + ", ".join(unread))
        used_check = any(s.get("tool") == "check_concept" and "error" not in s.get("result", {}) for s in steps)
        if conf != "cannot" and _LEGAL_CLAIM.search(answer) and not used_check:
            lower("partial", "kết luận pháp lý chưa qua bộ kiểm luật (check_concept)")
        found_at = found_at or {}
        path = []
        for i, p in enumerate(path_ids):
            item = self._node_view(p)
            if p in found_at:
                item["found_at"] = {"step": found_at[p][0], "tool": found_at[p][1]}
            if i and p != path_ids[i - 1]:
                item["edge"] = self._edge(path_ids[i - 1], p)
            path.append(item)
        on_path = set(path_ids)
        unused = [{**self._node_view(n, text=False), **({"found_at": {"step": found_at[n][0], "tool": found_at[n][1]}}
                                                        if n in found_at else {})}
                  for n in sorted(seen - on_path, key=lambda n: (found_at.get(n, (99, ""))[0], n))[:40]]
        return GraphAnswer(self.mask.unmask(answer), path, law, conf, warnings, trace,
                           {"steps": len(trace), "llm_calls": calls, "backend": self.view.backend,
                            "seconds": round(time.monotonic() - t0, 1), "seen": len(seen)},
                           [u for u in unused if u.get("node_type")])

    def _node_view(self, node_id: str, *, text: bool = True) -> dict:
        """Nút để vẽ: loại, nhãn, lời văn đầy đủ (đã bỏ che PII); ConceptInstance kèm concept_id."""
        n = self.view.node(node_id) or {}
        out = {"node_id": node_id, "node_type": n.get("node_type"),
               "label": self.mask.unmask(str(n.get("label") or n.get("title") or n.get("concept_id") or n.get("name")
                                             or n.get("raw") or ""))}
        if n.get("concept_id"):
            out["concept_id"] = n["concept_id"]
        if text:
            full = self.mask.unmask(str(n.get("text") or n.get("quote") or ""))
            out["text"], out["text_full"] = full[:160], full
        return out

    def _edge(self, a: str, b: str) -> dict:
        """Cạnh thật nối hai nút liền kề trên đường đi (một bước); `dir` "out": a -> b, "in": b -> a.
        verified=False khi đồ thị không có cạnh nào nối trực tiếp (agent tự nối)."""
        hops = self.view.path(a, b, max_hops=1) if self.view.node(a) and self.view.node(b) else None
        if not hops:
            return {"verified": False}
        h = hops[0]
        props = {k: h["props"][k] for k in ("valid_from", "kind", "raw") if h["props"].get(k) is not None}
        if "raw" in props:
            props["raw"] = self.mask.unmask(str(props["raw"]))
        return {"verified": True, "rel": h["rel"], "dir": h["dir"], "props": props}


def ask_contract_graph(llm, contract, question: str, *, at, catalog: Catalog | None = None, graph=None, legal=None,
                       agent_llm=None, tag_llm=None, model: str | None = None, max_steps: int = 8,
                       user_facts: dict | None = None, packs=None, document_kind: str | None = None):
    """Soát hợp đồng (ghi oplog, dựng/công bố đồ thị) rồi để agent trả lời trên đồ thị vừa dựng.
    Trả (GraphAnswer, CheckReport). agent_llm None -> dùng `llm`."""
    from rag.bridge.basis import AnchorLawBasis
    from rag.bridge.catalog import resolve_catalog
    from rag.bridge.check import check_contract, contract_view, user_fact_set
    from rag.contracts.graph.build import graph_mask_state
    from rag.contracts.graph.tools import make_tools
    if document_kind is not None and catalog is None and packs is None:
        from rag.contracts.classify import AUTO_KIND, classify_contract
        from rag.rules.loader import packs_for_kind
        if document_kind == AUTO_KIND:          # E5: nhận diện loại; unknown -> không có gói -> từ chối như loại lạ
            document_kind = classify_contract(llm, contract)["kind"]
        packs = packs_for_kind(document_kind) or None
        if packs is None:
            raise ValueError(f"Loại hợp đồng {document_kind!r} không có gói luật")
    catalog = resolve_catalog(catalog, packs)
    report = check_contract(llm, contract, catalog=catalog, basis=AnchorLawBasis(catalog, legal), at=at, model=model,
                            tag_llm=tag_llm, user_facts=user_facts, graph=graph)
    view, _, warnings, doc = contract_view(contract, graph, at, catalog)
    tools = make_tools(view, catalog=catalog, day=report.day, sign_date=contract.sign_date, legal=legal,
                       user_facts=user_fact_set(user_facts, catalog.context))
    agent = GraphAgent(agent_llm or llm, tools, view, mask=graph_mask_state(doc),
                       context=agent_context(view, catalog, sign_date=contract.sign_date), max_steps=max_steps)
    answer = agent.ask(question)
    answer.warnings[:0] = warnings
    return answer, report


__all__ = ["AGENT_PROMPT", "GraphAgent", "GraphAnswer", "agent_context", "ask_contract_graph"]
