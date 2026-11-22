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
from rag.contracts.values import extract_values
from rag.contracts.verify import catalog as fact_catalog

_ACTIVE = ("auto_accepted", "approved")
_DURATION_UNITS = {"ngày": "day", "tuần": "week", "tháng": "month", "năm": "year", "giờ": "hour"}
_JOB_LEVEL_CODES = ("quan_ly_doanh_nghiep", "cao_dang_tro_len", "trung_cap_ky_thuat", "cong_viec_khac")
_TRUE = {"true", "có", "yes", "1"}
_FALSE = {"false", "không", "no", "0"}


def _duration(text: str) -> tuple[float, str] | None:
    """Thời hạn đầu tiên trong chuỗi: (số, đơn vị); "ngày làm việc" -> workday; năm -> 12 tháng."""
    for v in extract_values(text):
        if v.kind != "duration":
            continue
        n, unit = v.norm["n"], _DURATION_UNITS.get(v.norm["unit"])
        if unit == "day" and text[v.end:].lstrip().casefold().startswith("làm việc"):
            unit = "workday"
        if unit == "year":
            return n * 12, "month"
        return (n, unit) if unit else None
    return None


def _first(text: str, kind: str):
    return next((v for v in extract_values(text) if v.kind == kind), None)


def _percent(slot: Slot, text: str, ctx) -> Fact | None:
    """Tỉ lệ: số trước "%". Slot có đơn vị khác `percent` (vd. percent_per_year) thì cách viết của kỳ ngay sau "%"
    phải khớp một `unit_forms` của gói và quy đổi được về đơn vị slot; không ghi kỳ thì không đoán (trả None)."""
    v = _first(text, "percent")
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


def normalize_slot(slot: Slot, raw: Any, ctx=None) -> Fact | None:
    """Giá trị thô LLM trả cho một slot -> Fact (nguồn "concept"), None nếu không chuẩn hóa được.
    `ctx`: Context của gói (đơn vị, `unit_forms`); None -> như cũ (gói labor)."""
    if slot.kind == "bool":
        if isinstance(raw, bool):
            return Fact(raw, None, "concept")
        s = str(raw).strip().casefold()
        return Fact(True, None, "concept") if s in _TRUE else Fact(False, None, "concept") if s in _FALSE else None
    if slot.kind == "enum":
        return Fact(raw, None, "concept") if raw in slot.options else None
    text = str(raw or "")
    if slot.kind == "duration":
        d = _duration(text)
        return Fact(d[0], d[1], "concept") if d else None
    if slot.kind == "percent":
        return _percent(slot, text, ctx)
    if slot.kind == "money":
        v = _first(text, "money")
        return Fact(v.norm["amount"], "vnd", "concept") if v and v.norm["currency"] == "VND" else None
    return None


def _labor_kind(text: str) -> str | None:
    t = text.casefold()
    if "không xác định" in t:
        return "khong_xac_dinh_thoi_han"
    return "xac_dinh_thoi_han" if "xác định" in t else None


def _term_months(text: str) -> tuple[float, str] | None:
    d = _duration(text)
    if d is None:
        return None
    n, unit = d
    if unit == "month":
        return n, "month"
    if unit == "day":
        return n / 30, "month"
    return None


_NEW_VALUE = re.compile(r"\s(?:lên|thành)\s", re.IGNORECASE)
_PART = re.compile(r"^p(\d+)\.")


def _salary(text: str) -> tuple[int, str] | None:
    m = list(_NEW_VALUE.finditer(text)) if _AMEND.search(text) else []
    if m:                                     # "điều chỉnh từ X lên Y": giá trị mới là Y
        text = text[m[-1].end():]
    v = _first(text, "money")
    return (v.norm["amount"], "vnd") if v and v.norm["currency"] == "VND" else None


def _pct(text: str) -> tuple[float, str] | None:
    v = _first(text, "percent")
    return (v.norm["percent"], "percent") if v else None


def _job_level(text: str) -> tuple[str, None] | None:
    levels = [str(x) for x in fact_catalog().get("job_levels") or []]
    for code, label in zip(_JOB_LEVEL_CODES, levels):
        if text.strip().casefold() == label.casefold():
            return code, None
    return None


_CONTRACT_MAP = {
    "contract_kind": ("labor_kind", lambda t: (k, None) if (k := _labor_kind(t)) else None),
    "term_months": ("term", _term_months),
    "base_salary_vnd": ("salary", _salary),
    "has_probation": ("probation_period", lambda t: (True, None)),
    "probation_length": ("probation_period", _duration),
    "probation_pay_pct": ("probation_salary", _pct),
    "job_level": ("job_level", _job_level),
}


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


def contract_facts(facts: dict, *, sign_date: date | None) -> Facts:
    """Dữ kiện cấp hợp đồng từ `contract.facts` (đầu ra của extract_facts: candidates[key] = [{value, unit, quote}])."""
    cands = facts.get("candidates") or {}
    out: Facts = {}
    for name, (key, norm) in _CONTRACT_MAP.items():
        seen: list[Fact] = []
        for c in cands.get(key) or []:
            got = norm(str(c.get("value") or ""))
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


def fact_ops(facts: dict, contract_id: str, *, at: datetime) -> list[GraphOperation]:
    """Một ASSERT `fact` cho mỗi (tên dữ kiện, ứng viên) chuẩn hóa được; ứng viên thiếu đơn vị chứa câu trích bị bỏ.
    Đồ thị dựng nút `ContractFact` từ các thao tác này (spec 2026-11-16-contract-graph-agent §5.2)."""
    cands = facts.get("candidates") or {}
    ops: list[GraphOperation] = []
    for name, (key, norm) in _CONTRACT_MAP.items():
        for c in cands.get(key) or []:
            uid = c.get("unit")
            got = norm(str(c.get("value") or "")) if uid else None
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


_PARTY_LABEL = {"NLD": "Người lao động", "NSDLD": "Người sử dụng lao động"}


def party_role(role_text: str) -> str | None:
    t = " ".join(str(role_text or "").casefold().split())
    if "sử dụng lao động" in t or "công ty" in t or "người sử dụng" in t:
        return "NSDLD"
    return "NLD" if "người lao động" in t else None


def party_ops(facts: dict, contract_id: str, *, at: datetime) -> list[GraphOperation]:
    """Một thao tác ASSERT `party` cho mỗi vai trò NLĐ / NSDLĐ tìm thấy trong `facts["parties"]`. Không ghi tên."""
    roles = list(dict.fromkeys(r for p in facts.get("parties") or [] if (r := party_role(p.get("role")))))
    return [machine_op(contract_id, "ASSERT", f"party:{r}", {"kind": "party", "role": r, "label": _PARTY_LABEL[r]},
                       "rule", "auto_accepted", at=at) for r in roles]


__all__ = ["FactSet", "build_factset", "contract_facts", "fact_ops", "normalize_slot", "party_ops", "party_role"]
