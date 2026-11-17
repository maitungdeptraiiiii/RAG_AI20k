"""Bảng xác minh dữ kiện (spec 2026-11-13 §3, §5, §6, §7).

Bảng được dựng lại mỗi lần từ hai nguồn: ứng viên máy đọc (`facts["candidates"]`) và câu trả lời của người dùng trong
nhật ký thao tác (`SET_FIELD` của người, đích `party` / `sign_date` / `type` / `fact:<key>` / `q:<qid>`).
"""
from __future__ import annotations

import hashlib
import json
import unicodedata
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from rag.contracts.graph.oplog import human_op

NEUTRAL = "neutral"
NEUTRAL_LABEL = "Trung lập / tư vấn"
VERIFIED = ("confirmed", "corrected", "unknown")
GATED_OPS = ("review", "partial", "law_changes", "redline")
_DIRECT = ("party", "sign_date", "type")       # đích SET_FIELD sẵn có (đồ thị đọc `type`, `sign_date`)


class NeedsVerification(ValueError):
    """Còn dữ kiện bắt buộc chưa xác minh: chưa được soát."""

    def __init__(self, pending: list[dict]):
        self.pending = pending
        names = ", ".join(f["label"] for f in pending)
        super().__init__(f"Hãy xác minh thông tin trước khi soát: {names}")


@lru_cache(maxsize=1)
def catalog() -> dict:
    return json.loads(Path(__file__).with_name("fact_catalog.json").read_text(encoding="utf-8"))


def _norm(v: Any) -> str:
    return " ".join(unicodedata.normalize("NFC", str(v or "")).split()).casefold()


def catalog_type(kind: str | None) -> str:
    k = _norm(kind)
    if "lao động" in k:
        return "labor"
    if "thuê" in k:
        return "lease"
    return "common"


def _resolve(spec: dict) -> dict:
    opts = spec.get("options")
    return spec | {"options": catalog()[opts]} if isinstance(opts, str) else dict(spec)


def all_specs() -> list[dict]:
    """Mọi dữ kiện của mọi loại (để LLM trích một lần, trước khi biết loại)."""
    out, seen = [], set()
    for specs in catalog()["types"].values():
        for s in specs:
            if s["key"] not in seen:
                seen.add(s["key"])
                out.append(_resolve(s))
    return out


def party_options(contract) -> list[dict]:
    roles = [p["role"] for p in contract.facts.get("parties") or [] if p.get("role")]
    return [{"value": r, "label": f"Tôi là {r}"} for r in roles] + [{"value": NEUTRAL, "label": NEUTRAL_LABEL}]


def _options(spec: dict, contract) -> list[str] | None:
    if spec["key"] == "party":
        return [o["value"] for o in party_options(contract)]
    return spec.get("options")


def normalize_value(spec: dict, value: Any, contract) -> str | None:
    """Giá trị hợp lệ theo kiểu của dữ kiện, None nếu không hợp lệ. Enum: khớp không phân biệt hoa thường; HĐLĐ
    "xác định thời hạn" không được nuốt "không xác định thời hạn"."""
    if value is None or str(value).strip() == "":
        return None
    text = " ".join(str(value).split())
    if spec["kind"] == "date":
        try:
            return date.fromisoformat(text[:10]).isoformat()
        except ValueError:
            return None
    options = _options(spec, contract)
    if spec["kind"] == "enum" and options:
        exact = next((o for o in options if _norm(o) == _norm(text)), None)
        if exact is not None:
            return exact
        hits = [o for o in options if _norm(o) in _norm(text) or _norm(text) in _norm(o)]
        hits = [o for o in hits if not any(o != p and _norm(o) in _norm(p) and _norm(p) in _norm(text) for p in hits)]
        return hits[0] if len(hits) == 1 else None
    return text


def specs_for(contract) -> list[dict]:
    kind = catalog_type(current_type(contract))
    specs = [_resolve(s) for s in catalog()["types"]["common"]]
    if kind != "common":
        specs += [_resolve(s) for s in catalog()["types"][kind]]
    return specs


def _answer(contract, target: str):
    """Thao tác của người đang hiệu lực mới nhất trên `target`, None nếu chưa có."""
    return next((o for o in reversed(contract.oplog.active())
                 if o.op_type == "SET_FIELD" and o.target == target and o.origin == "human"), None)


def _target(key: str) -> str:
    return key if key in _DIRECT else f"fact:{key}"


def current_type(contract) -> str | None:
    op = _answer(contract, "type")
    if op is not None and op.content.get("action") != "unknown":
        return op.content.get("value")
    return contract.facts.get("type")


def _candidates(contract, key: str) -> list[dict]:
    facts = contract.facts or {}
    cands = facts.get("candidates")
    if cands is None:                                  # hợp đồng lưu trước bản này: dựng từ dữ kiện cũ
        legacy = facts.get(key) if key in ("sign_date", "effective_date", "value", "term") else None
        if key == "type" and facts.get("type") and facts["type"] != "chưa rõ":
            legacy = {"value": facts["type"]}
        return [legacy] if isinstance(legacy, dict) and legacy.get("value") else []
    return list(cands.get(key) or [])


def fields(contract) -> list[dict]:
    """Bảng xác minh theo loại hợp đồng hiện tại."""
    out = []
    for spec in specs_for(contract):
        key = spec["key"]
        cands = _candidates(contract, key)
        row = {"key": key, "label": spec["label"], "kind": spec["kind"], "required": bool(spec.get("required")),
               "options": _options(spec, contract), "candidates": cands, "value": None, "unit": None, "quote": None}
        if key == "party":
            row["option_labels"] = {o["value"]: o["label"] for o in party_options(contract)}
        if len(cands) == 1:
            row.update(value=cands[0]["value"], unit=cands[0].get("unit"), quote=cands[0].get("quote"), status="found")
        else:
            row["status"] = "conflict" if cands else "missing"
        op = _answer(contract, _target(key))
        if op is not None:
            action = op.content.get("action")
            if action == "unknown":
                row.update(status="unknown", value=None)
            else:
                value = op.content.get("value")
                same = len(cands) >= 1 and any(_norm(c["value"]) == _norm(value) for c in cands)
                # chọn đúng một giá trị máy đã đọc (kể cả khi chọn giữa các ứng viên mâu thuẫn) = xác nhận
                row.update(value=value, status="confirmed" if same else "corrected")
                if not same:
                    row.update(unit=None, quote=None)
                else:
                    hit = next(c for c in cands if _norm(c["value"]) == _norm(value))
                    row.update(unit=hit.get("unit"), quote=hit.get("quote"))
            row["by"] = op.reviewer
        out.append(row)
    return out


def questions(contract) -> list[dict]:
    out = []
    for q in contract.facts.get("questions") or []:
        op = _answer(contract, f"q:{q['qid']}")
        answer = None if op is None or op.content.get("action") == "unknown" else op.content.get("value")
        out.append(q | {"status": "open" if op is None else "answered", "answer": answer,
                        "unknown": op is not None and op.content.get("action") == "unknown"})
    return out


def pending_required(contract) -> list[dict]:
    return [{"key": f["key"], "label": f["label"], "status": f["status"]}
            for f in fields(contract) if f["required"] and f["status"] not in VERIFIED]


def summary(contract) -> dict:
    rows = fields(contract)
    pending = [f for f in rows if f["required"] and f["status"] not in VERIFIED]
    return {"fields": rows, "pending": [{"key": f["key"], "label": f["label"]} for f in pending],
            "complete": not pending, "catalog_type": catalog_type(current_type(contract)),
            "questions": questions(contract), "coverage": contract.facts.get("coverage"),
            "warnings": list(contract.facts.get("warnings") or [])}


def check_gate(contract, op: str) -> None:
    if op in GATED_OPS:
        pending = pending_required(contract)
        if pending:
            raise NeedsVerification(pending)


def known_facts(contract) -> dict:
    """Dữ kiện đã xác minh và câu hỏi đã trả lời, gửi kèm payload soát để LLM không hỏi lại."""
    facts = {f["label"]: ("không biết" if f["status"] == "unknown" else f["value"])
             for f in fields(contract) if f["status"] in VERIFIED}
    answered = [{"question": q["question"], "answer": "không biết" if q["unknown"] else q["answer"]}
                for q in questions(contract) if q["status"] == "answered"]
    return {"facts": facts, "answered_questions": answered}


def apply_answers(contract, answers: dict, by: str, now: datetime) -> list:
    """Kiểm và ghi câu trả lời thành thao tác của người (thay thế câu trả lời trước cùng đích). Trả các thao tác mới.
    Đồng bộ `contract.party`, `contract.sign_date` như các API cũ. Lỗi kiểu -> ValueError, không ghi gì."""
    if not isinstance(answers, dict) or not answers:
        raise ValueError("Không có câu trả lời nào")
    rows = {f["key"]: f for f in fields(contract)}
    specs = {s["key"]: s for s in all_specs()}
    qs = {q["qid"]: q for q in questions(contract)}
    planned: list[tuple[str, dict]] = []
    for key, ans in answers.items():
        if not isinstance(ans, dict) or ans.get("action") not in ("confirm", "set", "unknown"):
            raise ValueError(f"Câu trả lời không hợp lệ cho {key}")
        action = ans["action"]
        if key.startswith("q:"):
            q = qs.get(key[2:])
            if q is None:
                raise ValueError(f"Không có câu hỏi {key}")
            if action == "confirm":
                raise ValueError("Câu hỏi chỉ trả lời bằng 'set' hoặc 'unknown'")
            value = None if action == "unknown" else " ".join(str(ans.get("value") or "").split())
            if action == "set" and not value:
                raise ValueError(f"Thiếu câu trả lời cho: {q['question']}")
            planned.append((key, {"action": action, "value": value}))
            continue
        if key not in rows:
            raise ValueError(f"Dữ kiện không có trong bảng xác minh: {key}")
        row = rows[key]
        if action == "unknown":
            if key in ("party", "sign_date"):
                raise ValueError(f"{row['label']}: cần một giá trị, không chọn 'không biết' được")
            planned.append((_target(key), {"action": "unknown", "value": None}))
            continue
        raw = row["value"] if action == "confirm" else ans.get("value")
        if action == "confirm" and (row["status"] == "conflict" or raw in (None, "")):
            raise ValueError(f"{row['label']}: chưa có một giá trị để xác nhận, hãy chọn hoặc nhập giá trị")
        value = normalize_value(specs[key], raw, contract)
        if value is None:
            raise ValueError(f"{row['label']}: giá trị không hợp lệ")
        planned.append((_target(key), {"action": action, "value": value}))
    new_ops = []
    for target, content in planned:
        op = human_op(contract.contract_id, "SET_FIELD", target, content, by, at=now)
        old = _answer(contract, target) or next((o for o in reversed(contract.oplog.active())
                                                  if o.op_type == "SET_FIELD" and o.target == target), None)
        if old is None:
            contract.oplog.add(op)
        else:
            contract.oplog.supersede(old.op_id, op, by, "", now)
        new_ops.append(op)
        if target == "party":
            contract.party = content["value"]
        elif target == "sign_date":
            contract.sign_date, contract.sign_date_source = date.fromisoformat(content["value"]), "user"
    return new_ops


def question_id(question: str) -> str:
    return hashlib.sha1(_norm(question).encode("utf-8")).hexdigest()[:10]


__all__ = ["GATED_OPS", "NEUTRAL", "NeedsVerification", "all_specs", "apply_answers", "catalog", "catalog_type",
           "check_gate", "current_type", "fields", "known_facts", "normalize_value", "party_options",
           "pending_required", "question_id", "questions", "specs_for", "summary"]
