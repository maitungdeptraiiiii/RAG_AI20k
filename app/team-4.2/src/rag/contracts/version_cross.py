"""Quy tắc liên văn bản giữa hai phiên bản hợp đồng (spec 2026-11-26-contract-versions-design §6). Không gọi LLM.

Mỗi hợp đồng của phiên bản = một văn bản chính của hồ sơ trong bộ nhớ, mỗi phần phụ lục = một văn bản `amendment`;
dữ kiện lấy từ `contract.facts` đã lưu. Kết quả "sau" là cập nhật mạng từ kết quả "trước"."""
from __future__ import annotations

import dataclasses
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from rag.contracts.doc import assemble
from rag.contracts.dossier import AMENDMENT, Dossier, DossierDoc, Party, dossier_objects
from rag.contracts.models import Contract
from rag.contracts.versions import compare_results
from rag.rules.evaluator import default_kind, evaluator_for
from rag.rules.loader import load_pack, load_packs, packs_for_kind
from rag.rules.scenario import object_changes
from rag.rules.semantics import Fact

PARTY = "party1"        # mọi tham chiếu bên của các văn bản trỏ về một bên người dùng đã xác nhận là chung
UNSUPPORTED = "Không có quy tắc liên văn bản cho loại hợp đồng này"


def _object_types(packs: Sequence[str]) -> dict:
    out: dict = {}
    seen: set[str] = set()

    def visit(pid: str) -> None:
        if pid in seen:
            return
        seen.add(pid)
        spec = load_pack(pid)
        for parent in spec.extends:
            visit(parent)
        out.update(spec.object_types)
    for p in packs:
        visit(p)
    return out


def _part_texts(c: Contract) -> list[str]:
    """Chữ của từng phần theo bố cục hiện tại (p0 trước)."""
    text = assemble(c.page_texts).text
    parts = c.doc.parts if c.doc is not None else []
    if len(parts) < 2:
        return [text]
    ends = [*(p.start for p in parts[1:]), len(text)]
    return [text[p.start:end].strip() for p, end in zip(parts, ends)]


def _documents(c: Contract) -> tuple[list[DossierDoc], dict]:
    main_text, *appendices = _part_texts(c)
    kind = str((c.facts or {}).get("document_kind") or "")
    docs = [DossierDoc(c.contract_id, c.filename, kind, {}, main_text)]
    cands = {k: list(v) for k, v in ((c.facts or {}).get("candidates") or {}).items()}
    dates = (c.facts or {}).get("appendix_dates") or {}
    for i, text in enumerate(appendices, start=1):
        if not text.startswith("PHỤ LỤC"):       # bộ tách của hồ sơ nhận phần theo tiêu đề
            text = f"PHỤ LỤC {i}\n{text}"
        docs.append(DossierDoc(f"{c.contract_id}-p{i}", c.filename, AMENDMENT, {"contract": c.contract_id}, text))
        eff = (dates.get(f"p{i}") or {}).get("effective_date")
        if eff:
            cands.setdefault("effective_date", []).append({"value": eff, "unit": f"p{i}.pre"})
    return docs, {**(c.facts or {}), "candidates": cands}


def version_dossier(contracts: Sequence[Contract], *, day: date, continuous_employment: bool | None,
                    user_facts: dict) -> tuple[Dossier, dict[str, dict]]:
    kinds = [str((c.facts or {}).get("document_kind") or "") for c in contracts]
    packs = tuple(dict.fromkeys(p for k in kinds for p in packs_for_kind(k)))
    types = _object_types(packs)
    docs: list[DossierDoc] = []
    facts: dict[str, dict] = {}
    names: list[str] = []
    for c in contracts:
        mine, f = _documents(c)
        main = mine[0]
        refs = {r: PARTY for t in types.values() if main.kind in t.documents for r in t.refs if r != t.amends}
        names += [r for r in refs if r not in names]
        docs += [dataclasses.replace(main, refs=refs), *mine[1:]]
        facts[c.contract_id] = f
    roles = list(load_packs(list(packs)).roles) if packs else []
    role = "NLD" if "NLD" in roles else (roles[0] if roles else names[0] if names else "party")
    party = Party(PARTY, role, "", continuous_employment)
    return Dossier("version", day, packs, (party,), tuple(docs), dict(user_facts), Path(".")), facts


def cross_check(before: Sequence[Contract], after: Sequence[Contract], *, day: date,
                continuous_employment: bool | None, user_facts: dict) -> dict:
    """{"day", "supported", "results", "compare", "recomputed", "total", "note"}; chỉ kết quả của rule xuyên đối tượng."""
    kw = dict(day=day, continuous_employment=continuous_employment, user_facts=user_facts)
    old, old_facts = version_dossier(before, **kw)
    new, new_facts = version_dossier(after, **kw)
    types = _object_types(new.packs)
    kinds = {x.kind for x in new.documents if x.kind != AMENDMENT}
    empty = {"day": day.isoformat(), "supported": False, "results": [], "compare": compare_results([], []),
             "recomputed": 0, "total": 0, "note": UNSUPPORTED}
    if not new.packs or not any(set(t.documents) & kinds for t in types.values()):
        return empty
    cat = load_packs(list(new.packs))
    old_objects = dossier_objects(old, old_facts) if old.packs else []
    session = evaluator_for(cat, default_kind()).session(
        day=day, facts={k: Fact(v, None, "user") for k, v in user_facts.items()}, present=set(), evidence={},
        objects=old_objects)
    first = session.results()
    session.update({}, objects=object_changes(old_objects, dossier_objects(new, new_facts)))
    second = session.results()
    stats = getattr(session, "stats", None) or {}

    def cross(results):
        return [dataclasses.asdict(r) for r in results if r.object is not None]

    results = cross(second)
    return {"day": day.isoformat(), "supported": True, "results": results,
            "compare": compare_results(cross(first), results),
            "recomputed": stats.get("rules_recomputed", len(second)), "total": len(second), "note": None}


__all__ = ["PARTY", "UNSUPPORTED", "cross_check", "version_dossier"]
