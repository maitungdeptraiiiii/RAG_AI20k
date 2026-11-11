"""Gọi LLM nhận JSON: che PII mọi chuỗi gửi đi, mở che mọi chuỗi nhận về; kiểm trích dẫn nguyên văn."""

from __future__ import annotations

import json
import re
import unicodedata
from typing import Any

from rag.quality.pii import MaskState, mask_text

JSON_RULES = ("\nChỉ trả về MỘT đối tượng JSON hợp lệ, không thêm chữ nào khác. "
              "Các ký hiệu dạng [HD_...] là thông tin cá nhân đã được ẩn: giữ nguyên đúng ký hiệu, không đoán giá trị.")


class ContractAIError(RuntimeError):
    """LLM trả kết quả không dùng được — báo người dùng thử lại, không coi là "không có vấn đề"."""

    def __init__(self, message: str = "AI trả kết quả không hợp lệ, hãy thử lại") -> None:
        super().__init__(message)


def _walk(value: Any, fn) -> Any:
    if isinstance(value, str):
        return fn(value)
    if isinstance(value, list):
        return [_walk(v, fn) for v in value]
    if isinstance(value, dict):
        return {k: _walk(v, fn) for k, v in value.items()}
    return value


def mask_payload(payload: Any, state: MaskState) -> Any:
    return _walk(payload, lambda s: mask_text(s, state=state).masked_text)


def unmask_payload(payload: Any, state: MaskState) -> Any:
    return _walk(payload, state.unmask)


def _parse(raw: str) -> dict:
    text = (raw or "").strip()
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.S)
    if fenced:
        text = fenced.group(1)
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        start, end = text.find("{"), text.rfind("}")
        try:
            data = json.loads(text[start:end + 1]) if 0 <= start < end else None
        except ValueError:
            data = None
    if not isinstance(data, dict):
        raise ContractAIError()
    return data


def ask_json(llm, system: str, payload: dict, state: MaskState) -> dict:
    user = json.dumps(mask_payload(payload, state), ensure_ascii=False)
    try:
        raw = llm.complete(system + JSON_RULES, user)
    except ContractAIError:
        raise
    except Exception as exc:  # noqa: BLE001 — lỗi mạng / API: báo thử lại, không lộ chi tiết SDK
        raise ContractAIError("Không gọi được AI lúc này, hãy thử lại") from exc
    return unmask_payload(_parse(raw), state)


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFC", text or "")
    text = text.replace("“", '"').replace("”", '"').replace("’", "'")
    return " ".join(text.split()).casefold()


def quote_ok(source: str, quote: str) -> bool:
    q = _norm(quote)
    return bool(q) and q in _norm(source)
