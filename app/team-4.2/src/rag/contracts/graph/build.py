"""Dựng đồ thị hợp đồng thuần: trang + nhật ký thao tác -> nút/cạnh với build_id tất định."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from rag.contracts.amendments import find_amendments
from rag.contracts.doc import ContractDoc, PageText, PartSpec
from rag.contracts.graph.oplog import OperationLog
from rag.contracts.structure import PARSER_VERSION, parse_contract
from rag.quality.pii import MaskState, mask_text

_INT64 = (-(2 ** 63), 2 ** 63 - 1)
SCHEMA = json.loads(Path(__file__).with_name("schema.json").read_text(encoding="utf-8"))


@dataclass(frozen=True)
class GraphNode:
    node_id: str
    label: str
    props: dict


@dataclass(frozen=True)
class GraphEdge:
    type: str
    src: str
    dst: str
    props: dict


@dataclass(frozen=True)
class GraphBuild:
    build_id: str
    contract_id: str
    built_at: datetime
    inputs: dict
    nodes: tuple
    edges: tuple
    problems: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()           # vấn đề mềm, không chặn công bố

    def record(self) -> dict:
        """Bản ghi bản dựng (không gồm nút/cạnh)."""
        return {"build_id": self.build_id, "contract_id": self.contract_id,
                "built_at": self.built_at.isoformat(), "inputs": self.inputs,
                "problems": list(self.problems), "notes": list(self.notes), "n_nodes": len(self.nodes),
                "n_edges": len(self.edges)}


def _unresolved(doc: ContractDoc) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for x in doc.xrefs:
        if x.kind in ("missing", "external_law") or (x.kind == "appendix" and x.to_uid is None):
            out.setdefault(x.from_uid, []).append(x.raw)
    return out


def _mask_doc(doc: ContractDoc) -> tuple[MaskState, dict[str, str], dict[str, str]]:
    """Che PII tiêu đề phần rồi văn bản đơn vị, đúng thứ tự: placeholder ổn định giữa các lần dựng."""
    state = MaskState(prefix="HD_")
    titles = {p.part_id: mask_text(p.title, state=state).masked_text for p in doc.parts}
    texts = {u.uid: mask_text(u.text, state=state).masked_text for u in doc.units}
    return state, titles, texts


def graph_mask_state(doc: ContractDoc) -> MaskState:
    """Bảng che PII mà đồ thị dùng cho `doc`: để mở che câu trả lời của agent (spec 2026-11-16 §5.7)."""
    return _mask_doc(doc)[0]


def build_graph(contract_id: str, pages: list[PageText], oplog: OperationLog, *,
                file_checksum: str, built_at: datetime) -> tuple[GraphBuild, ContractDoc]:
    """Dựng đồ thị thuần: cùng đầu vào cho cùng nút, cạnh và build_id."""
    layout = oplog.layout()
    doc = parse_contract(pages, [PartSpec(**d) for d in layout] if layout else None)
    inputs = {"file_checksum": file_checksum, "parser_version": PARSER_VERSION,
              "schema_version": SCHEMA["version"], "op_ids": [o.op_id for o in oplog.active()]}
    build_id = "b" + hashlib.sha256(json.dumps(inputs, sort_keys=True).encode("utf-8")).hexdigest()[:12]
    cid = contract_id
    common = {"contract_id": cid, "build_id": build_id}
    sign_date = oplog.field("sign_date")
    state, titles, texts = _mask_doc(doc)
    unresolved = _unresolved(doc)

    nodes = [GraphNode(cid, "Contract", {**common, "type": oplog.field("type"), "sign_date": sign_date})]
    for p in doc.parts:
        nodes.append(GraphNode(f"{cid}:{p.part_id}", "Part", {
            **common, "kind": p.kind, "title": titles[p.part_id], "number": p.number}))
    nid = {u.uid: f"{cid}:{u.uid}@{u.version}" for u in doc.units}
    for u in doc.units:
        nodes.append(GraphNode(nid[u.uid], "Unit", {
            **common, "uid": u.uid, "part_id": u.part_id, "level": u.level, "label": u.label,
            "text": texts[u.uid], "page_start": u.page_start, "page_end": u.page_end,
            "version": u.version, "valid_from": sign_date, "valid_to": None,
            "unresolved_refs": unresolved.get(u.uid, [])}))
    for v in doc.values:
        props = {**common, "kind": v.kind, "raw": v.raw}
        for k, val in v.norm.items():
            if isinstance(val, int) and not _INT64[0] <= val <= _INT64[1]:
                val = str(val)  # Neo4j chỉ nhận số nguyên 64 bit
            props[f"norm_{k}" if k in ("kind", "raw") else k] = val
        nodes.append(GraphNode(f"{cid}:{v.vid}", "Value", props))

    edges = [GraphEdge("HAS_PART", cid, f"{cid}:{p.part_id}", {}) for p in doc.parts]
    edges += [GraphEdge("HAS_UNIT", f"{cid}:{u.part_id}", nid[u.uid], {}) for u in doc.units]
    edges += [GraphEdge("CHILD_OF", nid[u.uid], nid[u.parent_uid], {})
              for u in doc.units if u.parent_uid in nid]
    edges += [GraphEdge("REFERS_TO", nid[x.from_uid], nid[x.to_uid], {"raw": x.raw})
              for x in doc.xrefs if x.to_uid in nid and x.from_uid in nid]
    edges += [GraphEdge("HAS_VALUE", nid[v.uid], f"{cid}:{v.vid}", {}) for v in doc.values if v.uid in nid]
    notes: list[str] = []
    for a in find_amendments(doc):
        if a.src_uid in nid and a.dst_uid in nid:
            edges.append(GraphEdge("AMENDS", nid[a.src_uid], nid[a.dst_uid], {
                "kind": a.kind, "valid_from": a.valid_from.isoformat() if a.valid_from else None,
                "raw": mask_text(a.raw, state=state).masked_text}))
            if a.valid_from is None:
                notes.append(f"sửa đổi {a.src_uid} -> {a.dst_uid}: không rõ ngày hiệu lực")
    _concept_layer(cid, common, oplog, nid, state, nodes, edges)

    build = GraphBuild(build_id, cid, built_at, inputs, tuple(nodes), tuple(edges))
    return GraphBuild(build_id, cid, built_at, inputs, build.nodes, build.edges,
                      tuple(validate(build)), tuple(notes)), doc


def _concept_layer(cid: str, common: dict, oplog: OperationLog, nid: dict[str, str], state: MaskState,
                   nodes: list, edges: list) -> None:
    """Nút Party / ConceptInstance từ các ASSERT đang hiệu lực (spec 2026-11-14-contract-concept-check §10)."""
    asserts = [o for o in oplog.active() if o.op_type == "ASSERT"]
    if not asserts:
        return
    absent = sorted({o.content["concept_id"] for o in asserts if o.content.get("kind") == "concept_absent"})
    if absent:
        nodes[0].props["absent_checked"] = absent
    for o in asserts:
        if o.content.get("kind") != "fact":
            continue
        fid = f"{cid}:fact:{o.op_id}"
        nodes.append(GraphNode(fid, "ContractFact", {
            **common, "name": o.content["name"], "value": o.content.get("value"), "unit": o.content.get("unit"),
            "quote": mask_text(o.quote[0], state=state).masked_text if o.quote else "", "op_id": o.op_id,
            "source": "contract"}))
        edges.append(GraphEdge("HAS_FACT", cid, fid, {}))
        if o.source_uid in nid:
            edges.append(GraphEdge("EVIDENCE", fid, nid[o.source_uid], {}))
    parties: dict[str, str] = {}
    for o in asserts:
        if o.content.get("kind") == "party" and o.content.get("role") not in parties:
            pid = f"{cid}:party:{o.content['role']}"
            parties[o.content["role"]] = pid
            nodes.append(GraphNode(pid, "Party", {**common, "role": o.content["role"],
                                                  "label": o.content.get("label", "")}))
            edges.append(GraphEdge("HAS_PARTY", cid, pid, {}))
    concepts = None
    for o in asserts:
        if o.content.get("kind") != "concept":
            continue
        if concepts is None:
            from rag.bridge.catalog import load_catalog
            concepts = load_catalog().concepts
        node_id = f"{cid}:ci:{o.op_id}"
        props = {**common, "concept_id": o.content["concept_id"], "op_id": o.op_id,
                 "found_by": o.content.get("found_by", ""),
                 "quote": mask_text(o.quote[0], state=state).masked_text if o.quote else ""}
        for name, v in (o.content.get("slots") or {}).items():
            props[f"slot_{name}"] = v.get("value")
            props[f"slot_{name}_unit"] = v.get("unit")
        nodes.append(GraphNode(node_id, "ConceptInstance", props))
        if o.source_uid in nid:
            edges.append(GraphEdge("ABOUT", node_id, nid[o.source_uid], {}))
        concept = concepts.get(o.content["concept_id"])
        if concept is not None and concept.holder in parties:
            edges.append(GraphEdge("HOLDER", node_id, parties[concept.holder], {}))


def _day(s, default: date) -> date:
    return date.fromisoformat(s) if s else default


def validate(build: GraphBuild) -> list[str]:
    """Kiểm bản dựng; mỗi vi phạm một chuỗi mô tả."""
    problems: list[str] = []
    labels = {n.node_id: n.label for n in build.nodes}
    cid = build.contract_id
    for e in build.edges:
        rel = SCHEMA["relations"].get(e.type)
        if rel is None:
            problems.append(f"cạnh {e.type} ({e.src} -> {e.dst}): loại cạnh không có trong lược đồ")
            continue
        for end in (e.src, e.dst):
            if end not in labels:
                problems.append(f"cạnh {e.type}: đầu {end} không tồn tại")
        if e.src in labels and e.dst in labels and not (
                labels[e.src] in rel[0] and labels[e.dst] in rel[1]):
            problems.append(f"cạnh {e.type} ({e.src} -> {e.dst}): nhãn {labels[e.src]} -> "
                            f"{labels[e.dst]} sai miền/đích")
    for n in build.nodes:
        ok = n.node_id == cid if n.label == "Contract" else n.node_id.startswith(cid + ":")
        if not ok or n.props.get("contract_id") != cid:
            problems.append(f"nút {n.node_id}: không thuộc hợp đồng {cid}")
    state = MaskState(prefix="HD_")
    owners = [(f"nút {n.node_id}", n.props) for n in build.nodes]
    owners += [(f"cạnh {e.type} ({e.src} -> {e.dst})", e.props) for e in build.edges]
    for who, props in owners:
        for key, val in props.items():
            strings = [val] if isinstance(val, str) else (
                [x for x in val if isinstance(x, str)] if isinstance(val, (list, tuple)) else [])
            if any(mask_text(x, state=state).safe_findings for x in strings):
                problems.append(f"{who}: thuộc tính {key} còn PII")
            if isinstance(val, int) and not isinstance(val, bool) and not _INT64[0] <= val <= _INT64[1]:
                problems.append(f"{who}: thuộc tính {key} vượt số nguyên 64 bit")
    by_uid: dict[str, list[GraphNode]] = {}
    for n in build.nodes:
        if n.label == "Unit":
            by_uid.setdefault(n.props.get("uid"), []).append(n)
    for uid, group in by_uid.items():
        spans = []
        for n in group:
            try:
                spans.append((_day(n.props.get("valid_from"), date.min),
                              _day(n.props.get("valid_to"), date.max), n.node_id))
            except ValueError:
                problems.append(f"nút {n.node_id}: valid_from/valid_to không phải ngày ISO")
        spans.sort()
        for i, a in enumerate(spans):
            for b in spans[i + 1:]:
                if b[0] < a[1]:
                    problems.append(f"đơn vị {uid}: khoảng hiệu lực của {a[2]} và {b[2]} chồng nhau")
    return problems
