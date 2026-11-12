"""Dựng đồ thị luật thuần Python từ một snapshot kho luật: nút / cạnh với build_id tất định, kèm báo cáo.

Không ghi gì vào kho. Cùng snapshot + cùng GRAPH_VERSION -> cùng đồ thị.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from rag.legal.graph.appendix import split_appendices
from rag.legal.graph.refs import DocIndex, find_refs, ref_kind, resolve
from rag.legal.graph.relations import doc_relations
from rag.legal.keys import parse_provision_id, provision_id, unit_sort_key
from rag.legal.models import Address, LegalDocument, ProvisionVersion
from rag.legal.store import LegalStore
from rag.legal.structure import parse_structure

GRAPH_VERSION = "1"
SCHEMA = json.loads(Path(__file__).with_name("schema.json").read_text(encoding="utf-8"))
_STRUCTURAL = ("article", "clause", "point")
_DOC_RELATIONS = {"SUA_DOI_BO_SUNG": "AMENDS", "THAY_THE": "REPLACES", "BAI_BO": "REPEALS", "HOP_NHAT": "CONSOLIDATES"}
_SCOPE_TITLE = re.compile(r"phạm\s+vi\s+điều\s+chỉnh", re.IGNORECASE)
_AMENDING_TITLE = re.compile(r"sửa\s+đổi", re.IGNORECASE)
_FIRST_CLAUSE = re.compile(r"^\d+[a-zđ]?\.\s", re.MULTILINE)
_FIRST_POINT = re.compile(r"^[a-zđ]\d*\)\s", re.MULTILINE)


@dataclass(frozen=True)
class Node:
    node_id: str
    label: str
    props: dict


@dataclass(frozen=True)
class Edge:
    type: str
    src: str
    dst: str
    props: dict


@dataclass(frozen=True)
class LegalGraphBuild:
    build_id: str
    snapshot_id: str
    nodes: tuple[Node, ...]
    edges: tuple[Edge, ...]
    report: dict


def graph_build_id(snapshot_id: str) -> str:
    return hashlib.sha1(f"{snapshot_id}|{GRAPH_VERSION}".encode("utf-8")).hexdigest()[:16]


def _label(a: Address) -> str:
    parts = []
    if a.point:
        parts.append(f"điểm {a.point}")
    if a.clause:
        parts.append(f"khoản {a.clause}")
    parts.append(f"Điều {a.article}")
    return " ".join(parts)


def _parent(key: str, a: Address) -> str | None:
    if a.point:
        return provision_id(key, Address(a.article, a.clause), "clause")
    if a.clause:
        return provision_id(key, Address(a.article), "article")
    return None


def _order_key(a: Address) -> tuple:
    return (unit_sort_key(a.article), unit_sort_key(a.clause) if a.clause else (-1,),
            unit_sort_key(a.point) if a.point else (-1,))


def _at(history: list[ProvisionVersion], day) -> str | None:
    """Lời văn của phiên bản trong `history` hiệu lực tại `day` (tên Điều / đoạn mở đầu khoản)."""
    for v in history:
        if v.valid_from <= day and (v.valid_to is None or v.valid_to > day):
            return v.text
    return None


def _own_text(kind: str, text: str) -> str:
    """Phần lời văn của riêng đơn vị (không gồm khoản / điểm con), là tiền tố của `text` nên offset giữ nguyên."""
    body_at = text.find("\n") + 1
    if kind == "article":
        m = _FIRST_CLAUSE.search(text, body_at) if body_at else None
    elif kind == "clause":
        m = _FIRST_POINT.search(text, body_at) if body_at else None
    else:
        m = None
    return text[:m.start()] if m else text


def _iso(day) -> str | None:
    return day.isoformat() if day else None


def build_legal_graph(store: LegalStore, snapshot_id: str, *,
                      text_of: Callable[[LegalDocument], str] | None = None) -> LegalGraphBuild:
    read = text_of or (lambda d: Path(d.raw_text_path).read_text(encoding="utf-8"))
    build_id = graph_build_id(snapshot_id)
    docs = sorted(store.documents(), key=lambda d: d.document_key)
    keys = {d.document_key for d in docs}
    index = DocIndex(docs)
    nodes: dict[str, Node] = {}
    edges: dict[tuple, Edge] = {}
    problems: list[str] = []

    def node(node_id: str, label: str, props: dict) -> None:
        if node_id in nodes:
            problems.append(f"duplicate_node:{node_id}")
            return
        nodes[node_id] = Node(node_id, label, {k: v for k, v in props.items() if v is not None} | {"build_id": build_id})

    def edge(typ: str, src: str, dst: str, props: dict | None = None, *, key: tuple = ()) -> None:
        edges.setdefault((typ, src, dst, *key), Edge(typ, src, dst, props or {}))

    versions_of: dict[str, list[ProvisionVersion]] = {}      # document_key -> phiên bản đơn vị cấu trúc
    extras: dict[str, list[ProvisionVersion]] = {}           # pid tên Điều / đoạn mở đầu -> lịch sử
    texts: dict[str, str] = {}
    guides: dict[str, list[str]] = {}
    appendix_ids: dict[str, dict[str, str]] = {}
    scope_articles: dict[str, set[str]] = {}

    for d in docs:
        key = d.document_key
        texts[key] = read(d)
        all_versions = [] if d.is_consolidated else store.versions(key)
        structural = [v for v in all_versions if v.kind in _STRUCTURAL]
        for v in all_versions:
            if v.kind not in _STRUCTURAL:
                extras.setdefault(v.provision_id, []).append(v)
        versions_of[key] = structural
        starts = [v.valid_from for v in structural]
        ends = [v.valid_to for v in structural]
        closed = max(ends) if structural and all(e is not None for e in ends) else None   # type: ignore[type-var]
        body_end, parts = split_appendices(texts[key])
        node(key, "LawDoc", {
            "doc_type": d.doc_type, "doc_number": d.doc_number, "title": d.title, "issuer": d.issuer,
            "issued_on": _iso(d.issued_on), "effective_from": _iso(d.vbpl_effective_from or (min(starts) if starts else None)),
            "effective_to": _iso(d.vbpl_effective_to or closed), "eff_status": d.eff_status,
            "is_consolidated": d.is_consolidated, "body_end_offset": body_end})
        appendix_ids[key] = {}
        for n, part in enumerate(parts, 1):
            aid = f"{key}#pl{n}"
            node(aid, "Appendix", {"document_key": key, "number": part.number, "title": part.title, "kind": part.kind,
                                   "text": part.text, "span_start": part.span[0], "span_end": part.span[1]})
            edge("HAS_APPENDIX", key, aid)
            appendix_ids[key].setdefault(part.number.upper(), aid)

    for d in docs:                                           # điều khoản và phiên bản
        key = d.document_key
        structural = versions_of[key]
        if not structural:
            continue
        headings = {p.provision_id: list(p.heading_path) for p in parse_structure(texts[key], key)}
        addresses = {v.provision_id: parse_provision_id(v.provision_id)[1] for v in structural}
        kinds = {v.provision_id: v.kind for v in structural}
        ordered = sorted(addresses, key=lambda pid: _order_key(addresses[pid]))
        for order, pid in enumerate(ordered):
            a = addresses[pid]
            node(pid, "Provision", {"document_key": key, "kind": kinds[pid], "article": a.article, "clause": a.clause,
                                    "point": a.point, "label": _label(a), "order": order,
                                    "heading_path": headings.get(pid) or headings.get(provision_id(key, Address(a.article), "article"), [])})
            parent = _parent(key, a)
            if parent is None:
                edge("HAS_PROVISION", key, pid)
            elif parent in addresses:
                edge("CHILD_OF", pid, parent)
            else:
                problems.append(f"orphan_provision:{pid}")
        scope_articles[key] = {a.article for pid, a in addresses.items() if kinds[pid] == "article" and any(
            _SCOPE_TITLE.search(t.text) for t in extras.get(provision_id(key, Address(a.article, part="title"), "article_title"), []))}

    provision_ids = frozenset(n for n, x in nodes.items() if x.label == "Provision")

    for d in docs:                                           # quan hệ giữa văn bản
        key = d.document_key
        for r in store.relations(key):
            typ = _DOC_RELATIONS.get(r.relation)
            if typ and r.source_key == key and r.status == "confirmed" and r.target_key in keys:
                edge(typ, key, r.target_key, {"evidence": r.evidence})
        for typ, target, evidence in doc_relations(d, texts[key], index):
            edge(typ, key, target, {"evidence": evidence})
            if typ == "GUIDES":
                guides.setdefault(key, []).append(target)

    # văn bản sửa đổi: "Sửa đổi khoản 1 Điều 176 như sau:" nhắc điều khoản của luật ĐÍCH, không phải của chính nó;
    # quan hệ đó đã có ở CHANGED_BY, nên dẫn chiếu trống tên văn bản trong các văn bản này không được giải
    amending = {d.document_key for d in docs if _AMENDING_TITLE.search(d.title)} | {
        r.source_key for d in docs for r in store.relations(d.document_key) if r.relation == "SUA_DOI_BO_SUNG"}
    stats: Counter = Counter()
    missing_docs: Counter = Counter()
    for d in docs:                                           # phiên bản, CHANGED_BY, REFERS_TO
        key = d.document_key
        guided = guides.get(key, [])
        for v in versions_of[key]:
            pid = v.provision_id
            a = parse_provision_id(pid)[1]
            vid = f"{pid}@{v.valid_from.isoformat()}"
            in_scope = a.article in scope_articles.get(key, ())
            unresolved: list[str] = []
            own = _own_text(v.kind, v.text)
            for ref in find_refs(own):
                if key in amending and ref.doc_kind is None and ref.relative is None and ref.appendix is None:
                    stats["skipped_in_amending_document"] += 1
                    continue
                stats["refs"] += 1
                for res in resolve(ref, source_key=key, source_address=a, valid_from=v.valid_from, index=index,
                                   provision_ids=provision_ids, appendices=appendix_ids,
                                   guided_key=guided[0] if len(guided) == 1 else None, in_scope_article=in_scope):
                    if res.target is None:
                        stats[f"unresolved:{res.reason}"] += 1
                        doc_part = re.sub(r"\s+", " ", f"{ref.doc_kind or ''} {ref.doc_tail[:60]}").strip()
                        unresolved.append(f"{res.reason}: {ref.raw}" + (f" | {doc_part}" if doc_part else ""))
                        if res.reason == "doc_not_in_store":
                            missing_docs[doc_part[:70]] += 1
                        continue
                    if res.target == pid:
                        continue
                    stats["resolved"] += 1
                    stats["resolved_external"] += res.doc_key != key
                    kind = ref_kind(ref, res.doc_key, own, guided_keys=guided, in_scope_article=in_scope)
                    stats[f"kind:{kind}"] += 1
                    edge("REFERS_TO", vid, res.target, {"raw": ref.raw, "offset": ref.offset, "kind": kind}, key=(kind,))
            title = lead = None
            if v.kind == "article":
                title = _at(extras.get(provision_id(key, Address(a.article, part="title"), "article_title"), []), v.valid_from)
            elif v.kind == "clause":
                lead = _at(extras.get(provision_id(key, Address(a.article, a.clause, part="lead_in"), "clause_lead_in"), []),
                           v.valid_from)
            node(vid, "ProvisionVersion", {
                "provision_id": pid, "document_key": key, "text": v.text, "title": title, "lead_in": lead,
                "valid_from": _iso(v.valid_from), "valid_to": _iso(v.valid_to),
                "verification_status": v.verification_status, "status_reasons": list(v.status_reasons),
                "notes": list(v.notes), "unresolved_refs": unresolved})
            edge("HAS_VERSION", pid, vid)
            for op_id in v.source_operations:
                op = store.operation(op_id)
                if op is None or op.source_address is None:
                    stats["changed_by_skipped"] += 1
                    continue
                sa, src = op.source_address, op.source_document_key
                candidates = [provision_id(src, sa, "point")] if sa.point else []
                candidates += [provision_id(src, Address(sa.article, sa.clause), "clause")] if sa.clause else []
                candidates.append(provision_id(src, Address(sa.article), "article"))
                target = next((c for c in candidates if c in provision_ids), None)
                if target is None:
                    stats["changed_by_skipped"] += 1
                    continue
                edge("CHANGED_BY", vid, target, {"operation_id": op_id, "operation_type": op.operation_type}, key=(op_id,))

    node_list = tuple(sorted(nodes.values(), key=lambda n: n.node_id))
    edge_list = tuple(sorted(edges.values(), key=lambda e: (e.type, e.src, e.dst, json.dumps(e.props, sort_keys=True, ensure_ascii=False))))
    report = {
        "build_id": build_id, "snapshot_id": snapshot_id, "graph_version": GRAPH_VERSION,
        "nodes": dict(sorted(Counter(n.label for n in node_list).items())),
        "edges": dict(sorted(Counter(e.type for e in edge_list).items())),
        "refs": dict(sorted(stats.items())),
        "missing_documents": missing_docs.most_common(25),
        "problems": problems,
    }
    return LegalGraphBuild(build_id, snapshot_id, node_list, edge_list, report)


def validate(build: LegalGraphBuild, store: LegalStore) -> list[str]:
    """Lỗi chặn công bố. Rỗng = hợp lệ."""
    errors = list(build.report.get("problems", []))
    labels, types = set(SCHEMA["nodes"]), set(SCHEMA["relations"])
    by_id = {}
    for n in build.nodes:
        if n.label not in labels:
            errors.append(f"unknown_label:{n.label}")
        if n.node_id in by_id:
            errors.append(f"duplicate_node:{n.node_id}")
        by_id[n.node_id] = n
    for e in build.edges:
        if e.type not in types:
            errors.append(f"unknown_relation:{e.type}")
        if e.src not in by_id or e.dst not in by_id:
            errors.append(f"dangling_edge:{e.type}:{e.src}->{e.dst}")
        elif e.type == "REFERS_TO":
            text = by_id[e.src].props.get("text", "")
            if text[e.props["offset"]:e.props["offset"] + len(e.props["raw"])] != e.props["raw"]:
                errors.append(f"ref_raw_mismatch:{e.src}@{e.props['offset']}")
    spans: dict[str, list[tuple[str, str | None]]] = {}
    per_doc: Counter = Counter()
    for n in build.nodes:
        if n.label == "ProvisionVersion":
            spans.setdefault(n.props["provision_id"], []).append((n.props["valid_from"], n.props.get("valid_to")))
            per_doc[n.props["document_key"]] += 1
    for pid, items in spans.items():
        items.sort()
        for (_, end), (start, _) in zip(items, items[1:]):
            if end is None or end > start:
                errors.append(f"overlapping_versions:{pid}")
                break
    for d in store.documents():
        expected = 0 if d.is_consolidated else sum(1 for v in store.versions(d.document_key) if v.kind in _STRUCTURAL)
        if per_doc.get(d.document_key, 0) != expected:
            errors.append(f"version_count_mismatch:{d.document_key}:{per_doc.get(d.document_key, 0)}!={expected}")
    return errors


__all__ = ["GRAPH_VERSION", "SCHEMA", "Edge", "LegalGraphBuild", "Node", "build_legal_graph", "graph_build_id", "validate"]
