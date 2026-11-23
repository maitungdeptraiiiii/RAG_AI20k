"""Soát một HĐLĐ theo danh mục khái niệm, đầu tới cuối (spec 2026-11-14-contract-concept-check §4):
dữ kiện -> bên ký -> gán khái niệm -> engine -> kiểm lại khái niệm im lặng -> engine -> căn cứ luật -> báo cáo.

Engine đọc dữ kiện từ đồ thị hợp đồng (spec 2026-11-16-contract-graph-agent §5.5): mọi kết quả máy ghi vào oplog,
đồ thị dựng lại từ oplog, rồi đọc qua `ContractGraphView` (Neo4j nếu công bố được, không thì bản bộ nhớ)."""
from __future__ import annotations

import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from datetime import date, datetime

from rag.bridge.basis import AnchorLawBasis, LawBasis
from rag.bridge.catalog import CONTRACT_FACTS, USER_FACT_UNITS, USER_FACTS, Catalog, load_catalog, resolve_catalog
from rag.bridge.engine import Fact, Facts, RuleResult
from rag.bridge.facts_map import fact_ops, party_ops
from rag.bridge.graph_facts import factset_from_graph
from rag.bridge.recheck import needs_recheck, recheck
from rag.bridge.tagger import tag_contract
from rag.contracts.facts import extract_facts
from rag.contracts.doc import ContractDoc
from rag.contracts.graph.build import build_graph
from rag.contracts.graph.view import ContractGraphView, open_view
from rag.contracts.models import Contract
from rag.rules.events import diff_event
from rag.rules.evaluator import default_kind, evaluator_for
from rag.contracts.classify import AUTO_KIND, classify_contract
from rag.rules.loader import packs_for_kind

_ORDER = ("violation", "missing_content", "hidden_right", "conflict", "possible_right", "needs_facts")
_TITLES = {
    "violation": "Vi phạm",
    "missing_content": "Thiếu nội dung bắt buộc",
    "hidden_right": "Quyền mà hợp đồng không nhắc",
    "conflict": "Mâu thuẫn trong hợp đồng",
    "possible_right": "Có thể có quyền (cần thêm thông tin về bạn)",
    "needs_facts": "Cần thêm dữ kiện",
}


@dataclass
class CheckReport:
    contract_id: str
    day: date
    catalog_version: str
    results: list[RuleResult]
    basis: dict[str, dict]
    tag_rejected: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    stats: dict = field(default_factory=dict)


class _CountingLLM:
    def __init__(self, llm):
        self.llm, self.calls = llm, 0
        self._lock = threading.Lock()

    def complete(self, system: str, user: str) -> str:
        with self._lock:                 # các lô gọi song song
            self.calls += 1
        return self.llm.complete(system, user)


def user_fact_set(user_facts: dict | None, ctx=None) -> Facts:
    """Dữ kiện người dùng trả lời: {tên: giá trị} hoặc {tên: [giá trị, đơn vị]}. Tên phải là dữ kiện người dùng hoặc
    dữ kiện cấp hợp đồng của gói đang dùng (`ctx`, mặc định gói labor). Ghi đè giá trị trích từ hợp đồng."""
    if ctx is None or not ctx.input_units:
        allowed = {**{n: None for n in USER_FACTS}, **USER_FACT_UNITS, **CONTRACT_FACTS}
    else:
        allowed = dict(ctx.input_units)
    out: Facts = {}
    for name, v in (user_facts or {}).items():
        if name not in allowed:
            raise ValueError(f"Dữ kiện người dùng không có trong danh mục: {name}")
        value, unit = (v[0], v[1]) if isinstance(v, (list, tuple)) else (v, allowed[name])
        out[name] = Fact(value, unit, "user")
    return out


def _add_ops(contract: Contract, ops) -> int:
    return sum(1 for op in ops if contract.oplog.add(op))


def contract_view(contract: Contract, graph, at: datetime, catalog=None) -> tuple[ContractGraphView, str, list[str], ContractDoc]:
    """Dựng lại đồ thị từ oplog hiện tại và mở view: (view, build_id, cảnh báo, ContractDoc của bản dựng). `graph`: ContractGraphService
    hoặc None (chỉ bản bộ nhớ). Đồ thị lỗi lược đồ / đang bị khóa / Neo4j tắt -> vẫn đọc bản bộ nhớ."""
    from rag.contracts.graph.service import GraphBusy
    warnings: list[str] = []
    if not contract.page_texts:
        warnings.append("Hợp đồng không có văn bản theo trang: đồ thị rỗng, chỉ có dữ kiện người dùng")
    kw = dict(file_checksum=contract.file_checksum or "", catalog=catalog)
    status: dict = {"published": False}
    build = None
    if graph is not None:
        try:
            with graph.writing(contract.contract_id):
                build, doc, status = graph.build_and_publish(contract.contract_id, contract.page_texts, contract.oplog,
                                                           now=at, **kw)
        except GraphBusy:
            warnings.append("Đồ thị đang được thay đổi: đọc bản dựng trong bộ nhớ")
    if build is None:
        build, doc = build_graph(contract.contract_id, contract.page_texts, contract.oplog, built_at=at, **kw)
    if build.problems:
        warnings.append("Đồ thị có lỗi lược đồ: " + "; ".join(build.problems[:3]))
    return open_view(build, status, getattr(graph, "store", None)), build.build_id, warnings, doc


def in_force_warnings(results: Sequence[RuleResult], day: date) -> list[str]:
    """Cảnh báo cho rule không soát vì hợp đồng ký trước ngày luật có hiệu lực (lý do `law_not_in_force:<ngày>`); rule
    có `earlier_law_governs` là điều khoản khác luật mới: phải soát theo luật cũ, engine chưa có."""
    skipped = [r for r in results if any(x.startswith("law_not_in_force:") for x in r.reasons)]
    if not skipped:
        return []
    old = sorted({r.concept_id for r in skipped if "earlier_law_governs" in r.reasons})
    msg = (f"Hợp đồng ký ngày {day.isoformat()}, trước ngày luật có hiệu lực: {len(skipped)} rule không soát theo luật "
           "hiện hành")
    return [msg + (f"; điều khoản khác luật mới, cần soát theo luật cũ: {', '.join(old)}" if old else "")]


def check_contract(llm, contract: Contract, *, catalog: Catalog | None = None, basis: LawBasis | None = None,
                   at: datetime, model: str | None = None, tag_llm=None, tag_model: str | None = None,
                   user_facts: dict | None = None, graph=None, evaluator: str | None = None,
                   packs: Sequence[str] | None = None, document_kind: str | None = None,
                   on_event: Callable[[dict], None] | None = None) -> CheckReport:
    """tag_llm / tag_model: model riêng cho bước gán khái niệm (so model); None -> dùng llm / model.
    evaluator: "reference" | "network"; None -> RAG_RULE_EVALUATOR (spec 2026-11-22-rete-rule-engine-design §7).
    graph: ContractGraphService để công bố và đọc từ Neo4j; None -> đọc bản dựng trong bộ nhớ.
    on_event: nhận sự kiện tiến trình {type: stage|progress|partial, ...} (spec 2026-11-17-concept-check-streaming-ui §2)."""
    emit = on_event or (lambda e: None)

    def stage(name: str, status: str) -> None:
        emit({"type": "stage", "stage": name, "status": status})
    t0 = time.monotonic()
    classification = None
    if document_kind is not None:
        if catalog is not None or packs is not None:
            raise ValueError("document_kind chọn gói: không truyền kèm catalog hoặc packs")
        if document_kind == AUTO_KIND:   # E5: LLM nhận diện loại trong document_kinds của các gói (classify_contract)
            classification = classify_contract(llm, contract)
            document_kind = classification["kind"]
            contract.facts = {**(contract.facts or {}), "document_kind": document_kind}
        packs = packs_for_kind(document_kind)
        if not packs:                    # loại không nhận diện được: không soát bằng gói nào, không gọi LLM nữa
            why = (f"Không nhận diện được loại hợp đồng ({classification.get('reason')})" if classification
                   else f"Loại hợp đồng {document_kind!r} không có gói luật")
            return CheckReport(contract.contract_id, contract.sign_date or at.date(), "none", [], {},
                               warnings=[f"{why}: không chạy rule nào"],
                               stats={"packs": [], **({"classification": classification} if classification else {})})
    catalog = resolve_catalog(catalog, packs)
    user = user_fact_set(user_facts, catalog.context)
    rule_evaluator = evaluator_for(catalog, evaluator or default_kind())      # tên lạ -> ValueError trước mọi lời gọi LLM
    basis = basis or AnchorLawBasis(catalog, None)
    llm = _CountingLLM(llm)
    tagger = _CountingLLM(tag_llm) if tag_llm is not None else llm
    tag_model = tag_model or model
    warnings: list[str] = []
    stage("facts", "start")
    if not {k: v for k, v in (contract.facts or {}).items() if k != "document_kind"}:   # loại đã nhận diện không phải dữ kiện đã trích
        extract_facts(llm, contract, extra_fields=catalog.context.extract_fields,
                      **({"on_event": emit} if on_event else {}))
    stage("facts", "done")
    warnings += list(contract.facts.get("warnings") or [])

    day = contract.sign_date
    if day is None:
        day = catalog.law_values_valid_from
        warnings.append(f"Không có ngày ký: tạm dùng giá trị luật từ {day.isoformat()}")

    _add_ops(contract, party_ops(contract.facts, contract.contract_id, at=at, roles=catalog.roles))
    _add_ops(contract, fact_ops(contract.facts, contract.contract_id, at=at, ctx=catalog.context))
    stage("tag", "start")
    tag = tag_contract(tagger, contract, catalog, at=at, model=tag_model,
                       on_progress=lambda done, total: emit({"type": "progress", "stage": "tag", "done": done,
                                                             "total": total}), **({"on_event": emit} if on_event else {}))
    stage("tag", "done")
    warnings += tag.warnings
    _add_ops(contract, tag.ops)

    session_state: dict = {}              # phiên đánh giá và dữ kiện đã đưa vào: lần đọc sau recheck chỉ update phần đổi

    def evaluate_now(facts: Facts, present: set[str], evidence: dict) -> list[RuleResult]:
        session = session_state.get("session")
        if session is None:
            session = session_state["session"] = rule_evaluator.session(day=day, facts=facts, present=present,
                                                                       evidence=evidence)
        else:
            old = session_state["facts"]
            diff = session.update({n: facts.get(n) for n in set(old) | set(facts) if old.get(n) != facts.get(n)},
                                  present=present, evidence=evidence)
            emit(diff_event(diff, getattr(session, "stats", None)))
        session_state["facts"] = dict(facts)
        return session.results()

    def read_graph():
        view, build_id, graph_warnings, _ = contract_view(contract, graph, at, catalog)
        factset, fact_warnings = factset_from_graph(view, day=day, sign_date=contract.sign_date)
        results = evaluate_now({**factset.facts, **user}, set(factset.present), factset.evidence)
        if on_event:
            nodes = [n for label in ("Contract", "Part", "Unit", "Value", "Party", "ContractFact", "ConceptInstance")
                     for n in view.find(label)]
            edges = {}
            for node in nodes:
                for hop in view.neighbors(node["node_id"], direction="out"):
                    key = (hop["rel"], node["node_id"], hop["node"]["node_id"])
                    edges[key] = {"type": key[0], "src": key[1], "dst": key[2], "props": hop["props"]}
            emit({"type": "graph", "build_id": build_id, "nodes": nodes, "edges": list(edges.values())})
            for result in results:
                emit({"type": "evaluation", "result": asdict(result)})
        return view, build_id, factset, results, graph_warnings + fact_warnings

    stage("evaluate", "start")
    view, build_id, factset, results, graph_warnings = read_graph()
    stage("evaluate", "done")
    emit({"type": "partial", "results": [asdict(x) for x in results]})
    todo = needs_recheck(results, factset)
    if todo:
        stage("recheck", "start")
        _add_ops(contract, recheck(llm, contract, catalog, todo, at=at, model=model, **({"on_event": emit} if on_event else {})))
        view, build_id, factset, results, graph_warnings = read_graph()
        stage("recheck", "done")
    warnings += graph_warnings
    warnings += in_force_warnings(results, day)

    reported =list(dict.fromkeys(r.concept_id for r in results if r.finding != "ok"))
    kinds: dict[str, int] = {}
    for op in contract.oplog.all():
        if op.op_type == "ASSERT":
            key = f"{op.content.get('kind')}:{op.status}"
            kinds[key] = kinds.get(key, 0) + 1
    stats = {"llm_calls": llm.calls + (tagger.calls if tagger is not llm else 0), "tag_model": tag_model, "recheck_concepts": len(todo), "tag_ops": len(tag.ops),
             "tag_rejected": len(tag.rejected), "assert_ops": kinds, "seconds": round(time.monotonic() - t0, 1),
             "graph_backend": view.backend, "build_id": build_id, "packs": list(packs) if packs else None,
             **({"classification": classification} if classification else {})}
    stage("basis", "start")
    law_basis = {cid: basis.concept_basis(cid, day) for cid in reported}
    stage("basis", "done")
    return CheckReport(contract.contract_id, day, catalog.version, results, law_basis, tag.rejected, warnings, stats)


def report_json(r: CheckReport) -> dict:
    return {"contract_id": r.contract_id, "day": r.day.isoformat(), "catalog_version": r.catalog_version,
            "results": [asdict(x) for x in r.results], "basis": r.basis, "tag_rejected": r.tag_rejected,
            "warnings": r.warnings, "stats": r.stats}


def _law_text(values: dict) -> str:
    parts = []
    for name, v in values.items():
        val = v.get("value")
        val = ", ".join(map(str, val)) if isinstance(val, list) else val
        parts.append(f"{name} = {val}{' ' + v['unit'] if v.get('unit') else ''}")
    return "; ".join(parts)


def report_markdown(r: CheckReport, catalog: Catalog) -> str:
    lines = [f"# Soát hợp đồng {r.contract_id}", "",
             f"Ngày áp luật: {r.day.isoformat()} · danh mục {r.catalog_version}", ""]
    if r.warnings:
        lines += ["**Cảnh báo:**", *[f"- {w}" for w in r.warnings], ""]
    for finding in _ORDER:
        group = [x for x in r.results if x.finding == finding]
        if not group:
            continue
        lines += [f"## {_TITLES[finding]} ({len(group)})", ""]
        for x in group:
            concept = catalog.concepts[x.concept_id]
            lines.append(f"- **{concept.label}** (`{x.concept_id}/{x.rule_id}`)")
            for e in x.evidence:
                lines.append(f"  - Hợp đồng [{e.get('uid')}]: “{e.get('quote')}”")
            if x.law_values:
                lines.append(f"  - Luật: {_law_text(x.law_values)}")
            for name, v in x.facts_used.items():
                for old in v.get("amended_from") or []:
                    lines.append(f"  - {name} = {v['value']} {v.get('unit') or ''}: sửa đổi từ {old['value']} "
                                 f"{old.get('unit') or ''} [{old.get('uid')}]")
                for new in v.get("later_amendments") or []:
                    lines.append(f"  - {name} từ {new['valid_from']}: {new['value']} {new.get('unit') or ''} "
                                 f"[{new.get('uid')}]")
            if x.missing_facts and finding not in ("hidden_right", "missing_content"):   # HĐ im lặng: không có slot
                lines.append(f"  - Thiếu dữ kiện: {', '.join(x.missing_facts)}")
            pids = [a["pid"] for a in r.basis.get(x.concept_id, {}).get("anchors", [])]
            if pids:
                lines.append(f"  - Căn cứ: {', '.join(pids)}")
        lines.append("")
    ok = sum(1 for x in r.results if x.finding == "ok")
    lines += [f"Không có vấn đề: {ok} rule.", ""]
    return "\n".join(lines)


__all__ = ["CheckReport", "check_contract", "contract_view", "report_json", "report_markdown", "user_fact_set"]
