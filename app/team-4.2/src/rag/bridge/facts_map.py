"""Bảng dữ kiện phẳng cho rule engine (spec 2026-11-14-contract-concept-check §7): dữ kiện cấp hợp đồng từ `facts.py`
và slot của các thao tác ASSERT khái niệm. Hai nguồn khác giá trị -> CONFLICT, không chọn."""
from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Sequence

from rag.bridge.catalog import Slot
from rag.bridge.engine import CONFLICT, Fact, Facts, _Conflict
from rag.contracts.amendments import AMEND_RE as _AMEND
from rag.contracts.graph.oplog import GraphOperation, machine_op
from rag.contracts import quantity as q
from rag.contracts.values import extract_values

_ACTIVE = ("auto_accepted", "approved")
_DURATION_UNITS = {"ngày": "day", "tuần": "week", "tháng": "month", "năm": "year", "giờ": "hour"}
_TRUE = {"true", "có", "yes", "1"}
_FALSE = {"false", "không", "no", "0"}


def _durations(text: str) -> list[tuple[float, str] | None]:
    """Mọi thời hạn bộ đọc regex thấy: (số, đơn vị); "ngày làm việc" -> workday; năm -> 12 tháng."""
    out = []
    for v in extract_values(text):
        if v.kind != "duration":
            continue
        n, unit = v.norm["n"], _DURATION_UNITS.get(v.norm["unit"])
        if unit == "day" and text[v.end:].lstrip().casefold().startswith("làm việc"):
            unit = "workday"
        out.append((n * 12, "month") if unit == "year" else (n, unit) if unit else None)
    return out


def _one(values: list):
    """Bộ đọc regex chỉ được tin khi chuỗi có đúng MỘT giá trị cùng loại (sau chuẩn hóa). Nhiều giá trị ("2 năm 6
    tháng", lương + phụ cấp) -> không đọc: trước đây lấy giá trị đầu là sai im lặng. Đọc đúng chuỗi nhiều giá trị là
    việc của dạng có kiểu do LLM trả (`norm`)."""
    distinct = list(dict.fromkeys(values))
    return distinct[0] if len(distinct) == 1 else None


def _duration(text: str) -> tuple[float, str] | None:
    return _one(_durations(text))


def _only(text: str, kind: str):
    """Giá trị duy nhất loại `kind` trong chuỗi (lần xuất hiện đầu của nó); nhiều giá trị khác nhau -> None."""
    vals = [v for v in extract_values(text) if v.kind == kind]
    one = _one([tuple(sorted(v.norm.items())) for v in vals])
    return next(v for v in vals if tuple(sorted(v.norm.items())) == one) if one is not None else None


def _percent(slot: Slot, text: str, ctx) -> Fact | None:
    """Tỉ lệ: số trước "%". Slot có đơn vị khác `percent` (vd. percent_per_year) thì cách viết của kỳ ngay sau "%"
    phải khớp một `unit_forms` của gói và quy đổi được về đơn vị slot; không ghi kỳ thì không đoán (trả None)."""
    v = _only(text, "percent")
    if v is None:
        return None
    if slot.unit in (None, "percent") or ctx is None:
        return Fact(v.norm["percent"], "percent", "concept")
    rest = " ".join(text[v.end:].casefold().split())
    best = None
    for unit, forms in ctx.unit_forms.items():
        for form in forms:
            f = " ".join(form.casefold().split())
            if rest.startswith(f) and ctx.units.convert(1, unit, slot.unit) is not None:
                if best is None or len(f) > best[1]:
                    best = (unit, len(f))
    return Fact(v.norm["percent"], best[0], "concept") if best else None


def _legacy(kind: str, text: str, unit: str | None, ctx) -> tuple[Any, str] | None:
    if kind == "duration":
        return _duration(text)
    if kind == "money":
        return _salary(text)
    f = _percent(Slot("_", "percent", unit), text, ctx)
    return (f.value, f.unit) if f is not None else None


def _typed(kind: str, norm: Any, unit: str | None, ctx, evidence: str) -> tuple[Any, str] | None:
    """Dạng có kiểu LLM trả -> (giá trị, đơn vị): kiểm hợp lệ, kiểm căn cứ từng số, code cộng / quy đổi."""
    units = (ctx if ctx is not None else _labor_ctx()).units
    if kind == "duration":
        parts = q.duration_parts(norm)
        if parts is None or not all(q.grounded(n, evidence) for n, _ in parts):
            return None
        return q.sum_duration(parts, unit, units)
    if kind == "money":
        mv = q.money_value(norm)
        if mv is None or mv[1] != "VND" or not q.grounded(mv[0], evidence):
            return None
        return q.plain(mv[0]), "vnd"
    pv = q.percent_value(norm)
    if pv is None or not q.grounded(pv[0], evidence):
        return None
    value, per = q.plain(pv[0]), pv[1]
    if unit in (None, "percent"):
        return value, "percent"
    per_unit = f"percent_per_{per}" if per else None
    if per_unit is None or per_unit not in units.names or units.convert(1, per_unit, unit) is None:
        return None                                                    # không ghi kỳ / kỳ gói không có: không đoán
    return value, per_unit


def _same(a: tuple[Any, str], b: tuple[Any, str], ctx) -> bool:
    if a[1] == b[1]:
        return abs(float(a[0]) - float(b[0])) < 1e-9
    v = (ctx if ctx is not None else _labor_ctx()).units.convert(float(a[0]), a[1], b[1])
    return v is not None and abs(v - float(b[0])) < 1e-9


def read_quantity(kind: str, text: str, norm: Any, *, unit: str | None, ctx=None,
                  evidence: str = "") -> tuple[Any, str] | None:
    """Giá trị số (thời hạn / tiền / tỉ lệ) -> (giá trị, đơn vị), None nếu không đọc được chắc chắn.
    Có `norm` (dạng có kiểu LLM trả): dùng nó khi mọi số có căn cứ trong `evidence` + `text`, và bộ đọc regex (nếu đọc
    được một giá trị duy nhất) không mâu thuẫn. Không có `norm` (dữ liệu cũ): bộ đọc regex, chỉ khi một giá trị."""
    legacy = _legacy(kind, text, unit, ctx)
    if norm is None:
        return legacy
    typed = _typed(kind, norm, unit, ctx, f"{evidence}\n{text}")
    if typed is None or (legacy is not None and not _same(legacy, typed, ctx)):
        return None
    return typed


def _labor_ctx():
    from rag.bridge.catalog import labor_context
    return labor_context()


def _split_raw(raw: Any) -> tuple[str, Any]:
    """Giá trị slot: chuỗi (dạng cũ) hoặc {"text": cụm nguyên văn, "norm": dạng có kiểu}."""
    if isinstance(raw, dict):
        return str(raw.get("text") or ""), raw.get("norm")
    return str(raw or ""), None


def normalize_slot(slot: Slot, raw: Any, ctx=None, *, quote: str | None = None) -> Fact | None:
    """Giá trị LLM trả cho một slot -> Fact (nguồn "concept"), None nếu không chuẩn hóa được.
    `ctx`: Context của gói (đơn vị, `unit_forms`); None -> gói labor. `quote`: câu trích chứa giá trị (căn cứ)."""
    if slot.kind in ("duration", "percent", "money"):
        text, norm = _split_raw(raw)
        got = read_quantity(slot.kind, text, norm, unit=slot.unit, ctx=ctx, evidence=quote or "")
        return Fact(got[0], got[1], "concept") if got else None
    if slot.kind == "bool":
        if isinstance(raw, bool):
            return Fact(raw, None, "concept")
        s = str(raw).strip().casefold()
        return Fact(True, None, "concept") if s in _TRUE else Fact(False, None, "concept") if s in _FALSE else None
    if slot.kind == "enum":
        return Fact(raw, None, "concept") if raw in slot.options else None
    return None


_NEW_VALUE = re.compile(r"\s(?:lên|thành)\s", re.IGNORECASE)
_PART = re.compile(r"^p(\d+)\.")


def _salary(text: str) -> tuple[int, str] | None:
    m = list(_NEW_VALUE.finditer(text)) if _AMEND.search(text) else []
    if m:                                     # "điều chỉnh từ X lên Y": giá trị mới là Y
        text = text[m[-1].end():]
    v = _only(text, "money")
    return (v.norm["amount"], "vnd") if v and v.norm["currency"] == "VND" else None


def _text(c: dict) -> str:
    return str(c.get("value") or "")


def _q(kind: str, c: dict, spec, ctx):
    return read_quantity(kind, _text(c), c.get("norm"), unit=spec.unit, ctx=ctx, evidence=str(c.get("quote") or ""))


def _p_duration_to_unit(c: dict, spec, ctx) -> tuple[float, str] | None:
    """Thời hạn quy về đơn vị khai của dữ kiện (vd. "2 năm" -> 24 tháng, "365 ngày" -> 12,17 tháng)."""
    d = _q("duration", c, spec, ctx)
    if d is None:
        return None
    if d[1] == spec.unit:
        return d
    v = ctx.units.convert(d[0], d[1], spec.unit)
    return (v, spec.unit) if v is not None else None


def _p_enum(c: dict, spec, ctx):
    t = _text(c).strip().casefold()
    return next(((code, None) for label, code in spec.values if label.casefold() == t), None)


def _p_contains(c: dict, spec, ctx):
    t = _text(c).casefold()
    return next(((code, None) for piece, code in spec.values if piece.casefold() in t), None)


# Bộ đọc theo tên (`parse` trong pack.yaml document_facts); danh sách tên ở rag.rules.model.DOCUMENT_PARSERS.
# Mỗi bộ đọc nhận một ứng viên của facts.py: {value: chữ nguyên văn, quote, norm?: dạng có kiểu}.
_PARSERS = {
    "duration": lambda c, spec, ctx: _q("duration", c, spec, ctx),
    "duration_to_unit": _p_duration_to_unit,
    "money": lambda c, spec, ctx: _q("money", c, spec, ctx),
    "percent": lambda c, spec, ctx: _q("percent", c, spec, ctx),
    "flag": lambda c, spec, ctx: (True, None),
    "enum": _p_enum,
    "contains": _p_contains,
    "text": lambda c, spec, ctx: (" ".join(_text(c).split()).casefold() or None, None) if _text(c).strip() else None,
}


def _specs(ctx):
    if ctx is None:
        from rag.bridge.catalog import labor_context
        ctx = labor_context()
    return ctx, ctx.document_specs


def _part(uid: str | None) -> int:
    m = _PART.match(uid or "")
    return int(m.group(1)) if m else 0


def _resolve(seen: list[Fact]) -> Fact | _Conflict:
    """Nhiều giá trị khác nhau: giá trị ở phần sau cùng (phụ lục) thay thế các giá trị ở phần trước khi nó là phần duy
    nhất mang giá trị đó và câu trích có từ sửa đổi ("điều chỉnh", "sửa đổi"...). Còn lại: CONFLICT, không chọn."""
    last = max(_part(f.uid) for f in seen)
    newest = [f for f in seen if _part(f.uid) == last]
    older = [f for f in seen if _part(f.uid) < last]
    if len(newest) != 1 or not older or not _AMEND.search(newest[0].quote or ""):
        return CONFLICT
    return dataclasses.replace(newest[0], amended_from=tuple({"value": f.value, "unit": f.unit, "uid": f.uid}
                                                             for f in older))


def contract_facts(facts: dict, *, sign_date: date | None, ctx=None) -> Facts:
    """Dữ kiện cấp hợp đồng từ `contract.facts` (đầu ra của extract_facts: candidates[key] = [{value, unit, quote}]),
    theo khai báo `document_facts` của gói (`ctx`; None -> gói labor)."""
    cands = facts.get("candidates") or {}
    out: Facts = {}
    ctx, specs = _specs(ctx)
    for name, spec in specs.items():
        seen: list[Fact] = []
        for c in cands.get(spec.field) or []:
            got = _PARSERS[spec.parse](c, spec, ctx)
            if got is None:
                continue
            f = Fact(got[0], got[1], "contract", c.get("unit"), c.get("quote"))
            if not any((s.value, s.unit) == (f.value, f.unit) for s in seen):
                seen.append(f)
        if len(seen) == 1:
            out[name] = seen[0]
        elif len(seen) > 1:
            out[name] = _resolve(seen)
    if sign_date is not None:
        out["sign_date"] = Fact(sign_date, None, "contract")
    return out


def fact_ops(facts: dict, contract_id: str, *, at: datetime, ctx=None) -> list[GraphOperation]:
    """Một ASSERT `fact` cho mỗi (tên dữ kiện, ứng viên) chuẩn hóa được; ứng viên thiếu đơn vị chứa câu trích bị bỏ.
    Đồ thị dựng nút `ContractFact` từ các thao tác này (spec 2026-11-16-contract-graph-agent §5.2)."""
    cands = facts.get("candidates") or {}
    ops: list[GraphOperation] = []
    ctx, specs = _specs(ctx)
    for name, spec in specs.items():
        for c in cands.get(spec.field) or []:
            uid = c.get("unit")
            got = _PARSERS[spec.parse](c, spec, ctx) if uid else None
            if got is None:
                continue
            content = {"kind": "fact", "name": name, "value": got[0], "unit": got[1]}
            ops.append(machine_op(contract_id, "ASSERT", f"fact:{name}", content, "llm", "auto_accepted",
                                  source_uid=uid, quote=(c["quote"],) if c.get("quote") else (), at=at))
    return ops


@dataclass(frozen=True)
class FactSet:
    facts: Facts
    present: frozenset[str]
    evidence: dict[str, list[dict]]
    absent_checked: frozenset[str]


def _merge(out: Facts, name: str, f: Fact) -> None:
    old = out.get(name)
    if old is None:
        out[name] = f
    elif old is not CONFLICT and (old.value, old.unit) != (f.value, f.unit):
        out[name] = CONFLICT


def build_factset(contract_level: Facts, ops: Sequence[GraphOperation]) -> FactSet:
    out: Facts = dict(contract_level)
    present: set[str] = set()
    absent: set[str] = set()
    evidence: dict[str, list[dict]] = {}
    for op in ops:
        if op.op_type != "ASSERT" or op.status not in _ACTIVE:
            continue
        kind, cid = op.content.get("kind"), op.content.get("concept_id")
        if kind == "concept_absent":
            absent.add(cid)
        if kind != "concept":
            continue
        present.add(cid)
        quote = op.quote[0] if op.quote else None
        evidence.setdefault(cid, []).append({"uid": op.source_uid, "quote": quote, "op_id": op.op_id})
        for name, v in (op.content.get("slots") or {}).items():
            _merge(out, name, Fact(v.get("value"), v.get("unit"), "concept", op.source_uid, quote))
    return FactSet(out, frozenset(present), evidence, frozenset(absent - present))


def _roles(roles):
    if roles is None:
        from rag.bridge.catalog import load_catalog
        roles = load_catalog().roles
    return roles


def party_role(role_text: str, roles=None) -> str | None:
    """Vai trò (id trong `roles` của gói) mà chữ mô tả bên trong hợp đồng nói tới: nhãn hoặc `aliases` của vai trò dài
    nhất nằm trong chữ đó thắng. Vai trò con (`subtype_of`) không dùng để nhận diện bên. `roles` None -> gói labor."""
    t = " ".join(str(role_text or "").casefold().split())
    best = None
    for rid, r in _roles(roles).items():
        if r.get("subtype_of"):
            continue
        for name in [r.get("label") or "", *(r.get("aliases") or [])]:
            n = " ".join(str(name).casefold().split())
            if n and n in t and (best is None or len(n) > best[1]):
                best = (rid, len(n))
    return best[0] if best else None


def party_ops(facts: dict, contract_id: str, *, at: datetime, roles=None) -> list[GraphOperation]:
    """Một thao tác ASSERT `party` cho mỗi vai trò của gói tìm thấy trong `facts["parties"]`. Không ghi tên."""
    table = _roles(roles)
    found = list(dict.fromkeys(r for p in facts.get("parties") or [] if (r := party_role(p.get("role"), table))))
    return [machine_op(contract_id, "ASSERT", f"party:{r}",
                       {"kind": "party", "role": r, "label": table[r].get("label", r)},
                       "rule", "auto_accepted", at=at) for r in found]


__all__ = ["FactSet", "build_factset", "contract_facts", "fact_ops", "normalize_slot", "party_ops", "party_role"]
