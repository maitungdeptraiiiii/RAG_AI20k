"""Hồ sơ nhiều văn bản -> đối tượng cho rule engine (H1; định dạng `tests/fixtures/rete/README.md`).

- `load_dossier`: đọc dossier.yaml (các bên theo vai trò của gói, văn bản, dữ kiện người dùng).
- `bundle`: một hợp đồng chính + các phụ lục của nó, phân tích như một tài liệu (mỗi văn bản một phần p0, p1, ...).
- `extract_dossier_facts`: bước trích (LLM, `facts.py`) cho từng bộ — luồng thật.
- `dossier_objects`: kết quả trích + văn bản -> `WorkingObject`. Kiểu, thuộc tính và cách dựng lấy từ `object_types` của
  gói (không viết cứng lao động). Không đoán: thiếu căn cứ -> thuộc tính vắng (engine coi là UNKNOWN).
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

from rag.bridge.facts_map import contract_facts
from rag.contracts.amendments import find_amendments
from rag.contracts.doc import ContractDoc, PageText
from rag.contracts.llm_json import quote_ok
from rag.contracts.models import Contract
from rag.contracts.structure import parse_contract, to_contract_units
from rag.rules.loader import load_pack, load_packs
from rag.rules.model import ObjectType
from rag.rules.objects import WorkingObject
from rag.rules.semantics import Fact

AMENDMENT = "amendment"


@dataclass(frozen=True)
class Party:
    id: str
    role: str
    name: str = ""
    continuous_employment: bool | None = None   # người dùng khai: làm việc liên tục suốt hồ sơ (văn bản không ghi)


@dataclass(frozen=True)
class DossierDoc:
    doc_id: str
    file: str
    kind: str                                    # document_kind của gói, hoặc "amendment"
    refs: Mapping[str, str] = field(default_factory=dict)
    text: str | None = None                      # văn bản đã đọc sẵn (hồ sơ tải lên); None -> đọc `root / file`


@dataclass(frozen=True)
class Dossier:
    dossier_id: str
    review_date: date | None
    packs: tuple[str, ...]
    parties: tuple[Party, ...]
    documents: tuple[DossierDoc, ...]
    user_facts: Mapping[str, Any]
    root: Path

    def doc(self, doc_id: str) -> DossierDoc:
        return next(x for x in self.documents if x.doc_id == doc_id)

    def party(self, pid: str | None) -> Party | None:
        return next((p for p in self.parties if p.id == pid), None)

    def parts(self, main_id: str) -> list[DossierDoc]:
        """Hợp đồng chính rồi các phụ lục của nó, theo thứ tự trong dossier.yaml (= p0, p1, ...)."""
        return [self.doc(main_id), *(x for x in self.documents
                                     if x.kind == AMENDMENT and x.refs.get("contract") == main_id)]


def _date(v: Any) -> date | None:
    if v is None or isinstance(v, date):
        return v
    return date.fromisoformat(str(v))


def load_dossier(path: Path) -> Dossier:
    path = Path(path)
    d = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    docs = tuple(DossierDoc(x["doc_id"], x["file"], x["kind"], dict(x.get("refs") or {})) for x in d.get("documents") or [])
    ids = {x.doc_id for x in docs}
    for x in docs:
        if x.kind == AMENDMENT and x.refs.get("contract") not in ids:
            raise ValueError(f"{path}: phụ lục {x.doc_id!r} trỏ tới hợp đồng không có trong hồ sơ")
    parties = tuple(Party(p["id"], p["role"], p.get("name", ""), p.get("continuous_employment"))
                    for p in d.get("parties") or [])
    return Dossier(str(d.get("dossier_id")), _date(d.get("review_date")), tuple(d.get("packs") or ()), parties, docs,
                   dict(d.get("user_facts") or {}), path.parent)


def doc_text(d: Dossier, x: DossierDoc) -> str:
    return x.text if x.text is not None else (d.root / x.file).read_text(encoding="utf-8")


def bundle(d: Dossier, main_id: str) -> ContractDoc:
    pages = [PageText(i + 1, doc_text(d, x)) for i, x in enumerate(d.parts(main_id))]
    return parse_contract(pages)


def extract_dossier_facts(llm, d: Dossier, *, extra_fields: Sequence[dict] = ()) -> dict[str, dict]:
    """Luồng thật: chạy `extract_facts` (LLM, kiểm câu trích) cho từng bộ hợp đồng chính + phụ lục."""
    from rag.contracts.facts import extract_facts
    out = {}
    for main in (x for x in d.documents if x.kind != AMENDMENT):
        doc = bundle(d, main.doc_id)
        units = to_contract_units(doc)
        text = "\n".join(doc_text(d, x) for x in d.parts(main.doc_id))
        c = Contract(main.doc_id, main.file, False, datetime.now(timezone.utc), text, units, len(units), doc=doc)
        out[main.doc_id] = extract_facts(llm, c, extra_fields=extra_fields)
    return out


# ── dựng đối tượng ──
def _object_types(packs: Sequence[str]) -> dict[str, ObjectType]:
    out: dict[str, ObjectType] = {}
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


def _part_of(uid: str | None) -> int | None:
    if not uid or not uid.startswith("p"):
        return None
    head = uid.split(".", 1)[0][1:]
    return int(head) if head.isdigit() else None


def _only_part(facts: dict, part: int) -> dict:
    cands = {k: [c for c in v if _part_of(c.get("unit")) == part] for k, v in (facts.get("candidates") or {}).items()}
    return {"candidates": {k: v for k, v in cands.items() if v}}


def _one_date(facts: dict, *keys: str) -> tuple[date | None, dict | None]:
    """Ngày duy nhất của trường đầu tiên có giá trị; nhiều ngày khác nhau -> không chọn (None)."""
    for key in keys:
        vals = {str(c.get("value"))[:10]: c for c in (facts.get("candidates") or {}).get(key) or []}
        if len(vals) == 1:
            v, c = next(iter(vals.items()))
            try:
                return date.fromisoformat(v), c
            except ValueError:
                return None, None
        if vals:
            return None, None
    return None, None


def _add_months(d: date, n: int) -> date:
    y, m = divmod(d.month - 1 + n, 12)
    y, m = d.year + y, m + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def _end_from_term(start: date | None, term: Fact | None) -> date | None:
    """Không có ngày kết thúc ghi rõ: ngày bắt đầu + thời hạn - 1 ngày (thời hạn tháng hoặc ngày, số nguyên)."""
    if start is None or not isinstance(term, Fact) or not float(term.value).is_integer():
        return None
    if term.unit == "month":
        return _add_months(start, int(term.value)) - timedelta(days=1)
    if term.unit == "day":
        return start + timedelta(days=int(term.value) - 1)
    return None


def _contract(d: Dossier, doc: DossierDoc, ot: ObjectType, facts: dict, ctx) -> WorkingObject:
    mine = _only_part(facts, 0)
    flat = contract_facts(mine, sign_date=None, ctx=ctx)
    start, _ = _one_date(mine, "start_date", "effective_date", "sign_date")
    end, _ = _one_date(mine, "end_date")
    if end is None:
        end = _end_from_term(start, flat.get("term_months"))
    attrs = {a: flat[f] for a, f in ot.from_facts.items() if isinstance(flat.get(f), Fact)}
    refs = {k: v for k, v in doc.refs.items() if k in ot.refs}
    return WorkingObject(doc.doc_id, ot.name, attrs, start, end, refs)


def _covers(doc: ContractDoc, dst: str, uid: str, quote: str) -> bool:
    """Điều khoản bị sửa (`dst`) chứa trường trích (đơn vị `uid`, câu `quote`)."""
    if uid == dst or uid.startswith(dst + "."):
        return True
    if dst.startswith(uid + "."):                      # trường nằm ở đơn vị lớn hơn: câu trích phải ở trong phần bị sửa
        u = doc.unit(dst)
        return u is not None and quote_ok(u.text, quote)
    return False


def _amendment(doc: DossierDoc, part: int, ot: ObjectType, parsed: ContractDoc, found: list, facts: dict) -> WorkingObject:
    mine = [a for a in found if _part_of(a.src_uid) == part]
    attrs: dict[str, Fact] = {}
    valid_from = next((a.valid_from for a in mine if a.valid_from), None)
    eff, eff_c = _one_date(_only_part(facts, part), "effective_date")
    valid_from = valid_from or eff
    if ot.states_valid_from and valid_from is not None:
        quote = eff_c.get("quote") if eff_c else None
        attrs[ot.states_valid_from] = Fact(True, None, "contract", eff_c.get("unit") if eff_c else None, quote)
    if mine and ot.states_target:
        attrs[ot.states_target] = Fact(True, None, "contract", mine[0].src_uid, mine[0].raw)
    for attr, field_name in ot.modifies.items():
        targets = [c for c in (facts.get("candidates") or {}).get(field_name) or [] if _part_of(c.get("unit")) == 0]
        if not mine or not targets:
            continue                                     # không biết điều khoản bị sửa / điều khoản chứa trường: vắng
        hit = next((a for a in mine for c in targets if _covers(parsed, a.dst_uid, c["unit"], c.get("quote") or "")), None)
        a = hit or mine[0]
        attrs[attr] = Fact(hit is not None, None, "contract", a.src_uid, a.raw)
    refs = {ot.amends: doc.refs.get("contract")} if ot.amends else {}
    return WorkingObject(doc.doc_id, ot.name, attrs, valid_from, None, refs)


def _gaps(d: Dossier, objs: list[WorkingObject], types: dict[str, ObjectType]) -> list[WorkingObject]:
    """`gap_after_end`: số ngày từ hết hạn tới văn bản kế tiếp cùng ref. Nối liền -> 0 (chắc chắn); có khoảng trống ->
    chỉ tính khi bên được ref khai `continuous_employment: true`; không có văn bản kế tiếp -> vắng."""
    out = []
    for o in objs:
        ot = types[o.type]
        if ot.gap_after_end is None or o.valid_to is None:
            out.append(o)
            continue
        attr, ref = ot.gap_after_end
        later = sorted((x for x in objs if x.type == o.type and x.id != o.id and x.refs.get(ref) == o.refs.get(ref)
                        and x.valid_from is not None and x.valid_from > o.valid_to), key=lambda x: x.valid_from)
        if not later:
            out.append(o)
            continue
        gap = max((later[0].valid_from - o.valid_to).days - 1, 0)
        party = d.party(o.refs.get(ref))
        if gap == 0 or (party is not None and party.continuous_employment is True):
            o = WorkingObject(o.id, o.type, {**o.attrs, attr: Fact(gap, "day", "derived")}, o.valid_from, o.valid_to,
                              o.refs)
        out.append(o)
    return out


def dossier_objects(d: Dossier, facts_by_contract: Mapping[str, dict]) -> list[WorkingObject]:
    """Đối tượng của hồ sơ theo `object_types` của các gói (`documents` chọn kiểu theo loại văn bản). `facts_by_contract`:
    {hợp đồng chính: contract.facts của bộ hợp đồng + phụ lục} (đầu ra `extract_dossier_facts`)."""
    types = _object_types(d.packs)
    by_kind = {k: ot for ot in types.values() for k in ot.documents}
    ctx = load_packs(list(d.packs)).context
    objs: list[WorkingObject] = []
    for main in (x for x in d.documents if x.kind != AMENDMENT):
        facts = facts_by_contract.get(main.doc_id) or {}
        ot = by_kind.get(main.kind)
        if ot is not None:
            objs.append(_contract(d, main, ot, facts, ctx))
        parts = d.parts(main.doc_id)
        amend_ot = by_kind.get(AMENDMENT)
        if amend_ot is None or len(parts) == 1:
            continue
        parsed = bundle(d, main.doc_id)
        found = find_amendments(parsed)
        for i, x in enumerate(parts[1:], start=1):
            objs.append(_amendment(x, i, amend_ot, parsed, found, facts))
    return _gaps(d, objs, types)


__all__ = ["AMENDMENT", "Dossier", "DossierDoc", "Party", "bundle", "doc_text", "dossier_objects", "extract_dossier_facts", "load_dossier"]
