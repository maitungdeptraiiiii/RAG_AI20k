"""Dựng ProvisionVersion cho một luật từ cây gốc + các thao tác áp dụng được, theo thời gian.

Trạng thái là cây lá (Điều: tiêu đề, phần dẫn, các khoản; khoản: đoạn mở đầu/toàn văn, các điểm). Text của
Điều/khoản luôn render lại từ lá, nên đổi một điểm thì khoản và Điều chứa nó cũng mở phiên bản mới.
Kết quả tất định: cùng đầu vào (bất kể thứ tự thao tác) cho cùng kết quả.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date

from rag.legal.effectivity import EffectivityInfo, effective_date_for, parse_effectivity
from rag.legal.keys import parse_provision_id, provision_id, unit_sort_key
from rag.legal.models import Address, AmendmentOperation, LegalDocument, Provision, ProvisionVersion
from rag.legal.structure import ARTICLE_RE, parse_structure

FALLBACK_START = date(1900, 1, 1)
# cờ Điều hiệu lực khiến ngày bắt đầu của luật gốc không chắc chắn -> mọi phiên bản cần xem lại
_UNKNOWN_DATE_FLAGS = ("effectivity.unit_exception_unresolved", "effectivity.relative_date", "effectivity.invalid_date")


def applicable(op: AmendmentOperation) -> bool:
    return op.review_status in ("auto_accepted", "approved") and op.effective_from is not None


class _ApplyError(Exception):
    pass


@dataclass
class _Clause:
    lead: str
    points: dict[str, str] = field(default_factory=dict)


@dataclass
class _Article:
    heading: str
    title: str
    intro: list[str]
    clauses: dict[str, _Clause] = field(default_factory=dict)


def _tree(provisions: Sequence[Provision]) -> dict[str, _Article]:
    tree: dict[str, _Article] = {}
    titles = {p.address.article: p.text for p in provisions if p.kind == "article_title"}
    by_parent: dict[str | None, list[Provision]] = {}
    for p in provisions:
        by_parent.setdefault(p.parent_id, []).append(p)
    for art in (p for p in provisions if p.kind == "article"):
        lines = art.text.split("\n")
        clauses = [p for p in by_parent.get(art.provision_id, []) if p.kind == "clause"]
        first = lines.index(clauses[0].text.split("\n")[0], 1) if clauses else len(lines)
        node = _Article(lines[0], titles.get(art.address.article, ""), lines[1:first])
        for cl in clauses:
            kids = by_parent.get(cl.provision_id, [])
            lead = next((k.text for k in kids if k.kind == "clause_lead_in"), None)
            points = {k.address.point: k.text for k in kids if k.kind == "point"}
            node.clauses[cl.address.clause] = _Clause(lead if lead is not None else cl.text, points)
        tree[art.address.article] = node
    return tree


def _article_from_text(key: str, label: str, text: str) -> _Article:
    tree = _tree(parse_structure(text, key))
    if label not in tree:
        raise _ApplyError("article label mismatch")
    return tree[label]


def _clause_from_text(key: str, article: str, label: str, text: str) -> _Clause:
    tree = _tree(parse_structure(f"Điều {article}. _\n{text}", key))
    node = tree.get(article)
    if node is None or label not in node.clauses:
        raise _ApplyError("clause label mismatch")
    return node.clauses[label]


def _sorted(d: Mapping[str, object]) -> list[str]:
    return sorted(d, key=unit_sort_key)


def _render(key: str, tree: Mapping[str, _Article]) -> dict[str, tuple[str, str]]:
    out: dict[str, tuple[str, str]] = {}
    for a in _sorted(tree):
        art = tree[a]
        clause_texts = []
        for c in _sorted(art.clauses):
            cl = art.clauses[c]
            pts = [cl.points[p] for p in _sorted(cl.points)]
            text = "\n".join([cl.lead, *pts])
            clause_texts.append(text)
            out[provision_id(key, Address(a, c), "clause")] = ("clause", text)
            if pts:
                out[provision_id(key, Address(a, c, part="lead_in"), "clause_lead_in")] = ("clause_lead_in", cl.lead)
            for p in _sorted(cl.points):
                out[provision_id(key, Address(a, c, p), "point")] = ("point", cl.points[p])
        out[provision_id(key, Address(a), "article")] = ("article", "\n".join([art.heading, *art.intro, *clause_texts]))
        if art.title:
            out[provision_id(key, Address(a, part="title"), "article_title")] = ("article_title", art.title)
    return out


def _replace_phrase(values: list[str], old: str, new: str) -> list[str]:
    for i, v in enumerate(values):
        if old in v:
            values[i] = v.replace(old, new, 1)
            return values
    raise _ApplyError("phrase not found")


def _apply(tree: dict[str, _Article], key: str, o: AmendmentOperation) -> None:
    t, ot = o.target, o.operation_type
    if ot == "REPEAL_DOCUMENT":
        return                                   # xử lý ở status.apply_repeals
    if ot == "UNSUPPORTED" or t is None:
        # được duyệt nhưng không có cách áp dụng: không được im lặng coi là đã áp dụng
        raise _ApplyError(f"{ot} không áp dụng được")
    art = tree.get(t.article)
    if ot in ("REPLACE_ARTICLE", "INSERT_ARTICLE"):
        tree[t.article] = _article_from_text(key, t.article, o.new_text or "")
        return
    if art is None:
        raise _ApplyError("article missing")
    if ot == "DELETE_ARTICLE":
        del tree[t.article]
    elif ot == "REPLACE_ARTICLE_TITLE":
        art.title = (o.new_text or "").strip()
        m = ARTICLE_RE.match(art.heading.strip())
        art.heading = f"Điều {t.article}. {art.title}" if m else art.heading
    elif ot in ("REPLACE_CLAUSE", "INSERT_CLAUSE"):
        art.clauses[t.clause] = _clause_from_text(key, t.article, t.clause, o.new_text or "")
    elif ot == "DELETE_CLAUSE":
        art.clauses.pop(t.clause)
    elif ot == "REPLACE_CLAUSE_LEAD_IN":
        cl = art.clauses[t.clause]
        new = (o.new_text or "").strip()
        # có điểm: đoạn mở đầu = phần trước các điểm; không có điểm: "khổ đầu" = đoạn văn đầu tiên của khoản
        cl.lead = new if cl.points else "\n".join([new, *cl.lead.split("\n")[1:]])
    elif ot in ("REPLACE_POINT", "INSERT_POINT"):
        art.clauses[t.clause].points[t.point] = (o.new_text or "").strip()
    elif ot == "DELETE_POINT":
        art.clauses[t.clause].points.pop(t.point)
    elif ot in ("REPLACE_TEXT", "AMEND_TEXT"):
        old, new = o.old_phrase or "", o.new_text or ""
        if not old:
            raise _ApplyError("no phrase")
        if t.point:
            cl = art.clauses[t.clause]
            cl.points[t.point] = _replace_phrase([cl.points[t.point]], old, new)[0]
        elif t.clause:
            cl = art.clauses[t.clause]
            keys = _sorted(cl.points)
            vals = _replace_phrase([cl.lead, *(cl.points[p] for p in keys)], old, new)
            cl.lead, cl.points = vals[0], dict(zip(keys, vals[1:]))
        else:
            vals = _replace_phrase([art.title, *art.intro], old, new) if any(old in v for v in [art.title, *art.intro]) \
                else None
            if vals is None:
                for c in _sorted(art.clauses):
                    cl = art.clauses[c]
                    keys = _sorted(cl.points)
                    if any(old in v for v in [cl.lead, *cl.points.values()]):
                        v2 = _replace_phrase([cl.lead, *(cl.points[p] for p in keys)], old, new)
                        cl.lead, cl.points = v2[0], dict(zip(keys, v2[1:]))
                        return
                raise _ApplyError("phrase not found")
            art.title, art.intro = vals[0], vals[1:]
    else:
        raise _ApplyError(f"unsupported {ot}")
    # KeyError -> _ApplyError handled by caller


def op_base(o: AmendmentOperation) -> str | None:
    """pid gốc của đơn vị đích (không có hậu tố title/lead) — dùng để xét "chạm"."""
    if o.target is None or o.target_document_key is None:
        return None
    t = Address(o.target.article, o.target.clause, o.target.point)
    kind = "point" if t.point else "clause" if t.clause else "article"
    return provision_id(o.target_document_key, t, kind)  # type: ignore[arg-type]


def touches(base: str, pid: str) -> bool:
    """pid là đơn vị đích, con cháu hoặc tổ tiên của đơn vị đích `base`."""
    key, _, path = base.partition("#")
    k2, _, p2 = pid.partition("#")
    if key != k2:
        return False
    a, b = path.split("."), [x for x in p2.split(".") if x not in ("title", "lead")]
    n = min(len(a), len(b))
    return a[:n] == b[:n]


def _sort_key(o: AmendmentOperation):
    return (o.effective_from, o.source_issued_on or date.min, o.source_document_key, o.sequence)


@dataclass
class _Open:
    kind: str
    text: str
    start: date
    ops: tuple[str, ...]
    reasons: tuple[str, ...]


def _build(document: LegalDocument, provisions: Sequence[Provision], effectivity: EffectivityInfo,
           ops: Sequence[AmendmentOperation], build_id: str):
    key = document.document_key
    tree = _tree(provisions)
    initial = _render(key, tree)
    starts: dict[str, tuple[date, tuple[str, ...]]] = {}
    for pid in initial:
        _, addr, _ = parse_provision_id(pid)
        day = effective_date_for(effectivity, addr)
        conditional = any(c.article == addr.article and (c.clause is None or c.clause == addr.clause)
                          and (c.point is None or c.point == addr.point) for c in effectivity.conditional_units)
        extra = ("effectivity.conditional_unit",) if conditional else ()
        extra += tuple(f.split(":")[0] for f in effectivity.flags if f.startswith(_UNKNOWN_DATE_FLAGS))
        if day is None:
            starts[pid] = (document.vbpl_effective_from or FALLBACK_START, ("effectivity.unresolved", *extra))
        else:
            starts[pid] = (day, extra)
    events: dict[date, list[AmendmentOperation]] = {}
    for o in sorted((o for o in ops if applicable(o) and o.target_document_key == key), key=_sort_key):
        events.setdefault(o.effective_from, []).append(o)  # type: ignore[arg-type]
    failed: list[AmendmentOperation] = []
    applied: list[AmendmentOperation] = []
    opened: dict[str, _Open] = {}
    out: list[ProvisionVersion] = []

    def close(pid: str, day: date) -> None:
        v = opened.pop(pid)
        out.append(ProvisionVersion(pid, key, v.kind, v.text, v.start, day, "verified", v.reasons, (), v.ops, build_id))  # type: ignore[arg-type]

    for day in sorted({s for s, _ in starts.values()} | set(events)):
        ev = []
        for o in events.get(day, []):
            backup = copy.deepcopy(tree)
            try:
                _apply(tree, key, o)
            except (_ApplyError, KeyError):
                tree = backup
                failed.append(o)
                continue
            ev.append(o)
            applied.append(o)
        cur = _render(key, tree)
        for pid, (kind, text) in cur.items():
            touching = tuple(o.operation_id for o in ev if (b := op_base(o)) and touches(b, pid))
            if pid in opened:
                if opened[pid].text != text:
                    reasons = opened[pid].reasons
                    close(pid, day)
                    opened[pid] = _Open(kind, text, day, touching, reasons)
            elif pid in starts:
                start, reasons = starts[pid]
                if start == day or (start < day and touching):
                    opened[pid] = _Open(kind, text, day, touching, reasons)
            else:
                opened[pid] = _Open(kind, text, day, touching, ())
        for pid in [p for p in opened if p not in cur]:
            close(pid, day)
    for pid in list(opened):
        v = opened.pop(pid)
        out.append(ProvisionVersion(pid, key, v.kind, v.text, v.start, None, "verified", v.reasons, (), v.ops, build_id))  # type: ignore[arg-type]
    return out, tree, applied, failed


def build_versions(document: LegalDocument, provisions: Sequence[Provision], effectivity: EffectivityInfo,
                   operations: Sequence[AmendmentOperation], *, build_id: str,
                   default_dates: Mapping[str, date] | None = None) -> list[ProvisionVersion]:
    key = document.document_key
    versions, tree, applied, failed = _build(document, provisions, effectivity, operations, build_id)
    amended = bool(effectivity.article) and any(
        o.target is not None and o.target.article == effectivity.article for o in applied)
    unstable = False
    if amended:
        current = effectivity
        for attempt in range(2):
            art_text = _render(key, tree).get(provision_id(key, Address(current.article), "article"), ("", ""))[1]
            new = parse_effectivity(parse_structure(art_text, key))
            if (new.default_from, new.exceptions) == (current.default_from, current.exceptions) or new.default_from is None:
                break
            current = replace(current, default_from=new.default_from, exceptions=new.exceptions)
            versions, tree, applied, failed = _build(document, provisions, current, operations, build_id)
        else:
            art_text = _render(key, tree).get(provision_id(key, Address(current.article), "article"), ("", ""))[1]
            new = parse_effectivity(parse_structure(art_text, key))
            unstable = (new.default_from, new.exceptions) != (current.default_from, current.exceptions)
    failed_ids = {o.operation_id for o in failed}
    pending_failed = [replace(o, review_status="pending",
                              status_reasons=o.status_reasons + (f"operation.apply_failed:{o.operation_id}",))
                      for o in operations if o.operation_id in failed_ids]
    others = [o for o in operations if o.operation_id not in failed_ids]
    from rag.legal.status import apply_statuses  # vòng phụ thuộc: status dùng touches/op_base của builder

    versions = apply_statuses(versions, [*others, *pending_failed], default_dates=default_dates or {},
                              document=document, effectivity_amended=amended)
    if unstable:
        versions = [replace(v, verification_status="needs_review" if v.verification_status == "verified" else v.verification_status,
                            status_reasons=v.status_reasons + ("effectivity.unstable",)) for v in versions]
    return sorted(versions, key=lambda v: (v.provision_id, v.valid_from))


__all__ = ["FALLBACK_START", "applicable", "build_versions", "op_base", "touches"]
