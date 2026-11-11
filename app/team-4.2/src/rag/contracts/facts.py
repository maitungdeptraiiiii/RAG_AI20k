"""Thông tin nền của hợp đồng: loại, các bên, ngày ký, ngày hiệu lực, giá trị, thời hạn.

Mỗi giá trị phải kèm trích dẫn có thật trong hợp đồng; trích dẫn không khớp -> bỏ giá trị (không đoán).
"""

from __future__ import annotations

from datetime import date
from typing import Any

from rag.contracts.llm_json import ask_json, quote_ok
from rag.contracts.models import Contract

FACTS_PROMPT = """Bạn đọc một hợp đồng tiếng Việt (đã tách thành các đơn vị có uid) và trích thông tin nền.
Trả JSON:
{"type": "loại hợp đồng hoặc 'chưa rõ'",
 "parties": [{"name": "...", "role": "vai trò trong hợp đồng, vd. Bên cho thuê", "unit": "uid", "quote": "trích nguyên văn"}],
 "sign_date": {"value": "YYYY-MM-DD", "unit": "uid", "quote": "trích nguyên văn"} hoặc null,
 "effective_date": {...} hoặc null, "value": {"value": "...", "unit": "uid", "quote": "..."} hoặc null,
 "term": {...} hoặc null,
 "other_dates": [{"label": "...", "value": "YYYY-MM-DD", "unit": "uid", "quote": "..."}]}
Quy tắc: "quote" phải là đoạn chép NGUYÊN VĂN từ hợp đồng; không tìm thấy thì để null, không suy đoán."""


def _payload(contract: Contract) -> dict:
    return {"units": [{"uid": u.uid, "label": u.label, "text": u.text} for u in contract.units]}


def _checked(item: Any, text: str) -> dict | None:
    if not isinstance(item, dict) or not quote_ok(text, str(item.get("quote") or "")):
        return None
    return {k: item.get(k) for k in ("value", "label", "name", "role", "unit", "quote") if item.get(k) is not None}


def _iso(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def extract_facts(llm, contract: Contract) -> dict:
    data = ask_json(llm, FACTS_PROMPT, _payload(contract), contract.mask_state)
    text = contract.text
    facts: dict[str, Any] = {"type": str(data.get("type") or "chưa rõ")}
    facts["parties"] = [p for p in (_checked(x, text) for x in data.get("parties") or []) if p and p.get("role")]
    for key in ("sign_date", "effective_date", "value", "term"):
        facts[key] = _checked(data.get(key), text)
    facts["other_dates"] = [d for d in (_checked(x, text) for x in data.get("other_dates") or []) if d]
    signed = _iso((facts["sign_date"] or {}).get("value"))
    if signed is None:
        facts["sign_date"] = None
    elif contract.sign_date_source != "user":
        contract.sign_date, contract.sign_date_source = signed, "text"
    contract.facts = facts
    return facts
