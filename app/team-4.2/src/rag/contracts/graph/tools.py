"""Bộ công cụ chỉ đọc cho agent (spec 2026-11-16-contract-graph-agent §5.6).

Mỗi công cụ có tên, mô tả một dòng, lược đồ tham số và hàm chạy. `call_tool` kiểm tham số trước khi chạy; mọi lỗi
(tham số sai, loại cạnh lạ, đồ thị luật vắng) trả `{"error": ...}` cho agent thay vì ném. Kết quả cắt còn khoảng
3.000 ký tự (danh sách dài nhất bị cắt, thêm `more`). Không công cụ nào ghi đồ thị hay oplog."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date
from typing import Any, Callable

from rag.bridge.basis import AnchorLawBasis
from rag.bridge.catalog import Catalog
from rag.bridge.engine import CONFLICT, Facts
from rag.bridge.graph_facts import factset_from_graph
from rag.contracts.graph.view import UNIT_TEXT_LIMIT, ContractGraphView, run_cypher
from rag.rules.evaluator import default_kind, evaluator_for

OUTPUT_LIMIT = 3000
LEGAL_DOWN = {"error": "legal_graph_unavailable"}
_TYPES = {"str": str, "int": int, "list[str]": list, "date": str}


@dataclass(frozen=True)
class Tool:
    name: str
    doc: str
    params: dict[str, dict]
    run: Callable[[dict], dict]

    def spec(self) -> dict:
        return {"name": self.name, "doc": self.doc, "params": self.params}


def _check_args(tool: Tool, args: Any) -> str | None:
    if not isinstance(args, dict):
        return "args phải là object"
    extra = set(args) - set(tool.params)
    if extra:
        return f"tham số lạ: {sorted(extra)}"
    for name, p in tool.params.items():
        if name not in args:
            if p.get("required"):
                return f"thiếu tham số {name}"
            continue
        v = args[name]
        if not isinstance(v, _TYPES[p["type"]]) or isinstance(v, bool):
            return f"{name} phải là {p['type']}"
        if p["type"] == "list[str]" and not all(isinstance(x, str) for x in v):
            return f"{name} phải là list[str]"
        if "enum" in p and v not in p["enum"]:
            return f"{name} phải là một trong {p['enum']}"
        if p["type"] == "date":
            try:
                date.fromisoformat(v)
            except ValueError:
                return f"{name} phải là ngày ISO YYYY-MM-DD"
    return None


def _cap(out: dict) -> dict:
    """Cắt danh sách dài nhất (kể cả lồng một cấp) cho tới khi JSON ≤ OUTPUT_LIMIT ký tự."""
    def size(x):
        return len(json.dumps(x, ensure_ascii=False, default=str))
    more = 0
    while size(out) > OUTPUT_LIMIT:
        lists = [(k, None) for k, v in out.items() if isinstance(v, list) and v]
        lists += [(k, k2) for k, v in out.items() if isinstance(v, dict)
                  for k2, v2 in v.items() if isinstance(v2, list) and v2]
        if not lists:
            break
        k, k2 = max(lists, key=lambda kk: size(out[kk[0]] if kk[1] is None else out[kk[0]][kk[1]]))
        target = out[k] if k2 is None else out[k][k2]
        target.pop()
        more += 1
    if more:
        out["more"] = more
    return out


def call_tool(tools: dict[str, Tool], name: str, args: dict) -> dict:
    tool = tools.get(name)
    if tool is None:
        return {"error": f"không có công cụ {name!r}; có: {sorted(tools)}"}
    problem = _check_args(tool, args)
    if problem:
        return {"error": problem}
    try:
        return _cap(tool.run(args))
    except ValueError as exc:
        return {"error": str(exc)}


def _fact_out(name: str, f) -> dict:
    if f is CONFLICT:
        return {"name": name, "conflict": True}
    return {"name": name, "value": f.value.isoformat() if isinstance(f.value, date) else f.value, "unit": f.unit,
            "uid": f.uid, "quote": f.quote, "amended_from": list(f.amended_from),
            "later_amendments": list(f.later_amendments)}


CONTEXT_TEXT = 300


def unit_context(view: ContractGraphView, unit_id: str) -> dict:
    """Ngữ cảnh một bước, tất định, kèm theo mỗi điều khoản trả về: điều khoản nó dẫn chiếu tới (kèm lời văn), phụ lục
    sửa nó (kèm ngày hiệu lực), con số trong nó. Agent không phải tự nhớ đi theo dẫn chiếu / sửa đổi."""
    refs, amended, values = [], [], []
    for h in view.neighbors(unit_id, rel_types=["REFERS_TO", "AMENDS", "HAS_VALUE"]):
        n = h["node"]
        if h["rel"] == "REFERS_TO" and h["dir"] == "out":
            refs.append({"node_id": n["node_id"], "label": n.get("label"), "raw": h["props"].get("raw"),
                         "text": str(n.get("text") or "")[:CONTEXT_TEXT]})
        elif h["rel"] == "AMENDS" and h["dir"] == "in":
            amended.append({"node_id": n["node_id"], "label": n.get("label"), "kind": h["props"].get("kind"),
                            "valid_from": h["props"].get("valid_from"), "raw": h["props"].get("raw")})
        elif h["rel"] == "HAS_VALUE":
            values.append(n.get("raw"))
    return {"refers_to": refs, "amended_by": amended, "values": values}


def make_tools(view: ContractGraphView, *, catalog: Catalog, day: date, sign_date: date | None,
               legal=None, user_facts: Facts | None = None, expand_context: bool = True,
               text2cypher: bool = True) -> dict[str, Tool]:
    """`day`: ngày soát (mặc định cho công cụ luật và dữ kiện); `legal`: LegalGraph hoặc None.
    `expand_context` / `text2cypher`: tắt để đo đối chứng (scripts/bench_contract_agent.py)."""
    basis = AnchorLawBasis(catalog, legal)
    evaluator = evaluator_for(catalog, default_kind())          # biên dịch một lần cho cả bộ công cụ

    def facts_at():
        return factset_from_graph(view, day=day, sign_date=sign_date)

    def law(fn):
        def run(a):
            if legal is None:
                return LEGAL_DOWN
            try:
                return fn(a, date.fromisoformat(a["day"]) if "day" in a else day)
            except Exception:  # noqa: BLE001 — đồ thị luật chưa công bố / Neo4j tắt
                return LEGAL_DOWN
        return run

    def find_units(a):
        if "text" in a:
            units = view.search_units(a["text"])
        elif "label" in a:
            want = " ".join(a["label"].casefold().split())
            units = [u for u in view.find("Unit", UNIT_TEXT_LIMIT) if " ".join(str(u.get("label", "")).casefold().split())
                     == want or str(u.get("label", "")).casefold().startswith(want + ":")
                     or str(u.get("label", "")).casefold().startswith(want + ".")]
        else:
            raise ValueError("cần text hoặc label")
        if not expand_context:
            return {"units": units}
        return {"units": [{**u, "context": unit_context(view, u["node_id"])} for u in units]}

    def find_concept(a):
        concept = catalog.concepts.get(a["concept_id"])
        if concept is None:
            raise ValueError(f"không có khái niệm {a['concept_id']!r} trong danh mục")
        inst = []
        for ci in view.find("ConceptInstance", concept_id=a["concept_id"]):
            about = view.neighbors(ci["node_id"], rel_types=["ABOUT"], direction="out")
            unit = about[0]["node"]["node_id"] if about else None
            inst.append({"node_id": ci["node_id"], "about": unit, "quote": ci.get("quote"),
                         **({"context": unit_context(view, unit) if unit else None} if expand_context else {}),
                         "slots": {k[5:]: ci[k] for k in ci if k.startswith("slot_") and not k.endswith("_unit")}})
        return {"concept_id": concept.id, "label": concept.label, "instances": inst}

    def expand(a):
        return {"hops": view.neighbors(a["node_id"], rel_types=a.get("rel_types"),
                                       direction=a.get("direction", "both"))}

    def find_path(a):
        p = view.path(a["src"], a["dst"], rel_types=a.get("rel_types"), max_hops=a.get("max_hops", 4))
        return {"path": p} if p is not None else {"path": None, "note": "không có đường trong giới hạn"}

    def subgraph(a):
        return view.subgraph(a["node_id"], hops=a.get("hops", 1), rel_types=a.get("rel_types"))

    def contract_facts(a):
        fs, warnings = facts_at()
        names = [a["name"]] if "name" in a else sorted(fs.facts)
        return {"day": day.isoformat(), "facts": [_fact_out(n, fs.facts[n]) for n in names if n in fs.facts],
                "warnings": warnings}

    def concept_basis(a):
        return basis.concept_basis(a["concept_id"], date.fromisoformat(a["day"]) if "day" in a else day)

    def check_concept(a):
        concept = catalog.concepts.get(a["concept_id"])
        if concept is None:
            raise ValueError(f"không có khái niệm {a['concept_id']!r} trong danh mục")
        fs, _ = facts_at()
        session = evaluator.session(day=day, facts={**fs.facts, **(user_facts or {})},
                                    present={concept.id} if concept.id in fs.present else set(),
                                    evidence={concept.id: list(fs.evidence.get(concept.id, ()))})
        results = [r for r in session.results() if r.concept_id == concept.id]
        keep = ("rule_id", "finding", "status", "law_values", "facts_used", "missing_facts", "evidence")
        return {"concept_id": concept.id, "label": concept.label, "day": day.isoformat(),
                "results": [{k: v for k, v in asdict(r).items() if k in keep} for r in results]}

    S, I, L, D = ({"type": t} for t in ("str", "int", "list[str]", "date"))
    req = lambda p: {**p, "required": True}  # noqa: E731
    direction = {"type": "str", "enum": ["out", "in", "both"]}
    specs = [
        ("find_units", "Tìm điều khoản theo chữ trong văn bản (text) hoặc nhãn như 'Điều 6' (label)",
         {"text": S, "label": S}, find_units),
        ("find_concept", "Các chỗ trong hợp đồng mang một khái niệm của danh mục, kèm điều khoản (about)",
         {"concept_id": req(S)}, find_concept),
        ("expand", "Các nút kề của một nút; lọc loại cạnh và chiều", {"node_id": req(S), "rel_types": L,
                                                                     "direction": direction}, expand),
        ("find_path", "Đường ngắn nhất giữa hai nút (tối đa max_hops ≤ 6 bước)",
         {"src": req(S), "dst": req(S), "rel_types": L, "max_hops": I}, find_path),
        ("subgraph", "Đồ thị con quanh một nút (hops ≤ 2)", {"node_id": req(S), "hops": I, "rel_types": L}, subgraph),
        ("contract_facts", "Dữ kiện hợp đồng tại ngày soát, kèm giá trị bị sửa và sửa đổi sau ngày soát",
         {"name": S}, contract_facts),
        ("law_text_at", "Lời văn điều luật (pid) hiệu lực tại ngày (mặc định ngày soát)", {"pid": req(S), "day": D},
         law(lambda a, d: legal.text_at(a["pid"], d))),
        ("law_changes", "Các phiên bản của điều luật từ ngày soát tới ngày to", {"pid": req(S), "to": req(D)},
         law(lambda a, d: {"versions": legal.changes(a["pid"], day, date.fromisoformat(a["to"]))})),
        ("law_guidance", "Văn bản hướng dẫn điều luật tại ngày", {"pid": req(S), "day": D},
         law(lambda a, d: {"guidance": legal.guidance(a["pid"], d)})),
        ("law_references", "Dẫn chiếu một bước của điều luật (direction out / in)",
         {"pid": req(S), "day": D, "direction": {"type": "str", "enum": ["out", "in"]}},
         law(lambda a, d: {"references": legal.references(a["pid"], d, a.get("direction", "out"))})),
        ("concept_basis", "Căn cứ luật (neo) của một khái niệm tại ngày", {"concept_id": req(S), "day": D},
         concept_basis),
        ("check_concept", "Chạy bộ kiểm luật cho một khái niệm trên dữ kiện của đồ thị (kết luận pháp lý)",
         {"concept_id": req(S)}, check_concept),
    ]
    if text2cypher and view.backend == "neo4j":       # Text2Cypher chỉ khi đồ thị nằm trên Neo4j (spec §5.8)
        specs.append(("cypher_query",
                      "Cypher CHỈ ĐỌC trên đồ thị hợp đồng cho câu đếm / liệt kê / tổng hợp mà công cụ khác không làm "
                      "được. Mỗi MATCH phải neo {contract_id: $cid} trong mẫu; chỉ nhãn/cạnh của đồ thị hợp đồng; "
                      "tối đa 50 dòng. ContractFact chứa MỌI giá trị kể cả giá trị đã bị phụ lục sửa: hỏi giá trị tại "
                      "một ngày thì dùng contract_facts", {"query": req(S)},
                      lambda a: run_cypher(view, a["query"])))
    return {name: Tool(name, doc, params, run) for name, doc, params, run in specs}


__all__ = ["LEGAL_DOWN", "OUTPUT_LIMIT", "Tool", "call_tool", "make_tools", "unit_context"]
