"""Phiên bản hợp đồng khi bổ sung phụ lục và đối chiếu kết quả (spec 2026-11-26-contract-versions-design §4–§7).

Mỗi phiên bản là một `Contract` riêng; bản cha không bao giờ bị sửa. Không gọi LLM."""
from __future__ import annotations

import copy
import dataclasses
import hashlib
from collections.abc import Sequence
from datetime import date, datetime

from rag.contracts.amendments import find_amendments
from rag.contracts.doc import PageText, PartSpec, assemble
from rag.contracts.graph.oplog import OperationLog, human_op
from rag.contracts.models import Contract, family_id, version_of
from rag.contracts.parts import detect_parts
from rag.contracts.structure import parse_contract, to_contract_units

_KEEP_ANSWERS = ("party", "sign_date", "type")      # câu trả lời của chính hợp đồng, phụ lục không đổi


def copy_for_version(parent: Contract, new_id: str, at: datetime) -> Contract:
    """Bản sao nháp của `parent` mang version kế tiếp; nhật ký giữ mã thao tác, đổi `contract_id`."""
    c = copy.deepcopy(parent)
    c.contract_id, c.persist, c.created_at, c.concept_check = new_id, False, at, None
    c.oplog = OperationLog(new_id, [dataclasses.replace(o, contract_id=new_id) for o in parent.oplog.all()])
    c.reports, c.graph, c.builds = {}, {}, []
    c.lineage = {"family_id": family_id(parent), "version": version_of(parent) + 1,
                 "parent_id": parent.contract_id, "status": "draft",
                 "linked": list(parent.lineage.get("linked") or [])}
    return c


def append_appendix(c: Contract, texts: Sequence[PageText], data: bytes, title: str, at: datetime) -> str:
    """Nối các trang của phụ lục thành MỘT phần mới ở cuối; bố cục và uid phần cũ giữ nguyên. Trả part_id."""
    old_text = assemble(c.page_texts).text
    layout = c.oplog.layout()
    parts = [PartSpec(**p) for p in layout] if layout else detect_parts(old_text)
    number = max(int(p.part_id[1:]) for p in parts) + 1
    new = PartSpec(f"p{number}", "appendix", title[:100], len(old_text) + 2, None)
    last = max((p.page or 0 for p in c.page_texts), default=0)
    c.page_texts = [*c.page_texts,
                    *(dataclasses.replace(t, page=last + i) for i, t in enumerate(texts, start=1))]
    content = {"parts": [dataclasses.asdict(p) for p in (*parts, new)]}
    op = human_op(c.contract_id, "SET_LAYOUT", None, content, "bổ sung văn bản", at=at)
    current = next((o for o in reversed(c.oplog.active()) if o.op_type == "SET_LAYOUT"), None)
    if current is None:
        c.oplog.add(op)
    else:
        c.oplog.supersede(current.op_id, op, "bổ sung văn bản", "", at)
    c.text = assemble(c.page_texts).text
    c.pages = [*c.pages, *({"page": last + i, "chars": len(t.text), "kind": t.kind}
                           for i, t in enumerate(texts, start=1))]
    c.file_checksum = hashlib.sha256((c.file_checksum or "").encode() + data).hexdigest()
    c.doc = parse_contract(c.page_texts, [*parts, new])
    c.units = to_contract_units(c.doc)
    c.total_units = len(c.units)
    return new.part_id


def effective_date(c: Contract, part_id: str) -> date | None:
    """Ngày hiệu lực của phần: từ câu sửa đổi, không có thì ngày hiệu lực bước trích ghi cho phần đó."""
    for a in find_amendments(c.doc) if c.doc is not None else []:
        if a.src_uid.startswith(f"{part_id}.") and a.valid_from is not None:
            return a.valid_from
    value = ((c.facts.get("appendix_dates") or {}).get(part_id) or {}).get("effective_date")
    return date.fromisoformat(value) if value else None


def reopen_changed_fields(c: Contract, keys: Sequence[str]) -> None:
    """Trường mà phần mới đưa giá trị khác: bỏ câu trả lời cũ của người dùng để phải xác minh lại."""
    targets = {t for k in keys if k not in _KEEP_ANSWERS for t in (k, f"fact:{k}")}
    c.oplog = OperationLog(c.contract_id, [
        o for o in c.oplog.all()
        if not (o.op_type == "SET_FIELD" and o.origin == "human" and o.target in targets)])


def _result_key(r: dict) -> str:
    return f"{r['concept_id']}/{r['rule_id']}@{r.get('object') or ''}"


def _meaning(r: dict) -> tuple:
    """Phần của kết quả tính là "đổi": trạng thái, kết luận, ngưỡng luật và giá trị dữ kiện (không tính trích đoạn)."""
    facts = {k: (v.get("value"), v.get("unit")) if isinstance(v, dict) else v
             for k, v in (r.get("facts_used") or {}).items()}
    return r.get("status"), r.get("finding"), r.get("law_values") or {}, facts


def compare_results(before: Sequence[dict], after: Sequence[dict]) -> dict:
    old = {_result_key(r): r for r in before}
    changed, added, unchanged = [], [], 0
    for r in after:
        key = _result_key(r)
        prev = old.pop(key, None)
        if prev is None:
            added.append(r)
        elif _meaning(prev) != _meaning(r):
            changed.append({"key": key, "before": prev, "after": r})
        else:
            unchanged += 1
    return {"changed": changed, "added": added, "removed": list(old.values()), "unchanged": unchanged}
