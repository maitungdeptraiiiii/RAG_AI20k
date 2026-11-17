"""Thông tin nền của hợp đồng, trích theo lô trên toàn bộ hợp đồng (spec 2026-11-13 §4).

Mỗi giá trị phải kèm trích dẫn có thật trong **chính đơn vị** mà LLM ghi là nguồn; trích dẫn không khớp -> bỏ giá trị
(không đoán). Mọi ứng viên của mọi lô được giữ ở `facts["candidates"]`; bảng xác minh (verify.py) dựng từ đó.
"""

from __future__ import annotations

import unicodedata
from datetime import date
from typing import Any

from rag.contracts.batches import Batch, make_batches, run_batches
from rag.contracts.llm_json import ContractAIError, ask_json, quote_ok
from rag.contracts.models import Contract
from rag.contracts.verify import all_specs, normalize_value

FACTS_PROMPT = """Bạn đọc MỘT PHẦN của một hợp đồng tiếng Việt (các đơn vị có uid trong "units") và trích thông tin nền.
"context" và "references" là đoạn khác của cùng hợp đồng, chỉ để tham khảo (hiểu định nghĩa, các bên, dẫn chiếu).
Trả JSON:
{"type": "loại hợp đồng hoặc 'chưa rõ'",
 "parties": [{"name": "...", "role": "vai trò trong hợp đồng, vd. Bên cho thuê", "unit": "uid", "quote": "trích nguyên văn"}],
 "sign_date": {"value": "YYYY-MM-DD", "unit": "uid", "quote": "trích nguyên văn"} hoặc null,
 "effective_date": {...} hoặc null, "value": {"value": "...", "unit": "uid", "quote": "..."} hoặc null,
 "term": {...} hoặc null,
 "other_dates": [{"label": "...", "value": "YYYY-MM-DD", "unit": "uid", "quote": "..."}],
 "fields": {"<key trong fields_wanted>": {"value": "...", "unit": "uid", "quote": "trích nguyên văn"}}}
Quy tắc: "quote" phải là đoạn chép NGUYÊN VĂN từ đơn vị "unit"; "unit" là uid trong "units", "context" hoặc "references".
Không tìm thấy thì để null / bỏ khóa, không suy đoán. Ngày dạng YYYY-MM-DD. Trường có "options": "value" phải là
đúng một lựa chọn trong đó."""

_SCALARS = ("sign_date", "effective_date", "value", "term")


def _norm(v: Any) -> str:
    return " ".join(unicodedata.normalize("NFC", str(v or "")).split()).casefold()


def _unit_text(contract: Contract, uid: Any) -> str:
    u = contract.unit(str(uid or ""))
    return u.text if u is not None else ""


def _checked(contract: Contract, item: Any) -> dict | None:
    """Ứng viên hợp lệ: trích dẫn có nguyên văn trong hợp đồng. `unit` được sửa thành đơn vị thực sự chứa trích dẫn
    (mô hình hay ghi nhầm uid hoặc ghi nhãn "Điều 5"); không đơn vị nào chứa -> bỏ."""
    if not isinstance(item, dict):
        return None
    quote = str(item.get("quote") or "")
    if not quote_ok(_unit_text(contract, item.get("unit")), quote):
        home = next((u for u in contract.units if quote_ok(u.text, quote)), None)
        if home is None:
            return None
        item = item | {"unit": home.uid}
    return {k: item.get(k) for k in ("value", "label", "name", "role", "unit", "quote") if item.get(k) is not None}


def _iso(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _wanted() -> list[dict]:
    return [{"key": s["key"], "label": s["label"], "hint": s.get("hint", ""),
             **({"options": s["options"]} if isinstance(s.get("options"), list) else {})}
            for s in all_specs() if s["key"] not in ("party", "sign_date", "type", *_SCALARS)]


def _payload(batch: Batch) -> dict:
    return {"units": batch.payload_units(), "context": list(batch.context), "references": list(batch.references),
            "fields_wanted": _wanted()}


def _add(cands: dict[str, list[dict]], key: str, item: dict | None) -> None:
    if item is None or item.get("value") in (None, ""):
        return
    bucket = cands.setdefault(key, [])
    if not any(_norm(c["value"]) == _norm(item["value"]) for c in bucket):
        bucket.append({k: item[k] for k in ("value", "unit", "quote") if k in item})


def extract_facts(llm, contract: Contract) -> dict:
    specs = {s["key"]: s for s in all_specs()}
    run = run_batches(make_batches(contract), lambda b: ask_json(llm, FACTS_PROMPT, _payload(b), contract.mask_state))
    if not run.results:
        raise ContractAIError()
    types: list[str] = []
    parties: list[dict] = []
    other: list[dict] = []
    cands: dict[str, list[dict]] = {}
    for _, data in run.results:
        kind = str(data.get("type") or "").strip()
        if kind and kind.casefold() != "chưa rõ":
            types.append(kind)
        for p in (_checked(contract, x) for x in data.get("parties") or []):
            if p and p.get("role") and not any(_norm(q["role"]) == _norm(p["role"]) for q in parties):
                parties.append(p)
        for key in _SCALARS:
            item = _checked(contract, data.get(key))
            if item and key in ("sign_date", "effective_date"):
                item = item | {"value": _iso(item.get("value")).isoformat()} if _iso(item.get("value")) else None
            _add(cands, key, item)
        other += [d for d in (_checked(contract, x) for x in data.get("other_dates") or []) if d]
        fields = data.get("fields") if isinstance(data.get("fields"), dict) else {}
        for key, raw in fields.items():
            item = _checked(contract, raw) if key in specs else None
            if item is not None:
                value = normalize_value(specs[key], item.get("value"), contract)
                _add(cands, key, item | {"value": value} if value is not None else None)

    facts: dict[str, Any] = {"type": types[0] if types else "chưa rõ", "parties": parties, "other_dates": other}
    for key in _SCALARS:                                   # dạng cũ: giá trị duy nhất, nhiều giá trị -> ứng viên đầu
        facts[key] = (cands.get(key) or [None])[0]
    if types:
        # mỗi lô tự đoán loại từ đoạn nó đọc: lấy loại của lô đầu tiên (có phần mở đầu), không coi là mâu thuẫn
        cands["type"] = [{"value": types[0]}]
    facts["candidates"] = cands
    facts["questions"] = list(contract.facts.get("questions") or [])
    facts["coverage"] = {"read": len(run.read_uids), "total": len(contract.units)}
    facts["warnings"] = run.warnings()
    signed = cands.get("sign_date") or []
    if len(signed) == 1 and contract.sign_date_source != "user":
        contract.sign_date, contract.sign_date_source = _iso(signed[0]["value"]), "text"
    elif not signed:
        facts["sign_date"] = None
    contract.facts = facts
    return facts


__all__ = ["FACTS_PROMPT", "extract_facts"]
