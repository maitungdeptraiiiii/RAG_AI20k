"""Nhận diện loại hợp đồng (H2; spec bản 3: quyết định gói nào được chạy).

LLM đọc phần đầu hợp đồng và chọn MỘT loại trong `document_kinds` của các gói (nhãn từ `document_labels`), kèm câu trích
nguyên văn làm bằng chứng. Không danh sách từ khóa: thêm gói mới là thêm loại. Không chắc, câu trích không có trong văn
bản, loại không có gói, hay lỗi gọi model -> `unknown` (người gọi không chạy gói nào, không rơi về gói lao động).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from rag.contracts.llm_json import ContractAIError, ask_json, quote_ok
from rag.contracts.models import Contract
from rag.rules.loader import PACKS_ROOT, load_pack

UNKNOWN = "unknown"
AUTO_KIND = "auto"          # check_contract / ask_contract_graph: document_kind="auto" -> nhận diện rồi chọn gói
MIN_CONFIDENCE = 0.6
HEAD_UNITS = 8            # phần đầu: tên văn bản, các bên, điều đầu tiên — đủ để biết loại
HEAD_CHARS = 800          # cắt mỗi đơn vị (chỉ để nhận diện loại)

CLASSIFY_PROMPT = """Bạn đọc PHẦN ĐẦU của một văn bản tiếng Việt (các đơn vị có uid trong "units") và cho biết văn bản
thuộc loại nào trong "kinds" (mỗi loại có "id" và "label").
Trả JSON: {"kind": <id trong kinds, hoặc "unknown">, "confidence": <số 0..1>, "unit": <uid>, "quote": <câu chép
NGUYÊN VĂN từ đơn vị đó cho thấy loại văn bản, vd. tên văn bản hoặc câu nói đối tượng của hợp đồng>}.
- Chọn loại hẹp nhất đúng với văn bản. Không có loại nào đúng, hoặc không chắc: "kind": "unknown".
- Không suy đoán từ tên người, tên công ty hay địa chỉ."""


def document_kinds(root: Path = PACKS_ROOT) -> dict[str, str]:
    """{document_kind: nhãn} của mọi gói có khái niệm (concepts.yaml), theo tên thư mục."""
    out: dict[str, str] = {}
    for d in sorted(p for p in Path(root).iterdir() if (p / "concepts.yaml").is_file()):
        spec = load_pack(d.name, root=root)
        for k in spec.document_kinds:
            out.setdefault(k, spec.document_labels.get(k, k))
    return out


def _unknown(reason: str, confidence: float = 0.0) -> dict:
    return {"kind": UNKNOWN, "confidence": confidence, "evidence": [], "reason": reason}


def _confidence(v: Any) -> float | None:
    if isinstance(v, bool):
        return None
    try:
        c = float(v)
    except (TypeError, ValueError):
        return None
    return c if 0.0 <= c <= 1.0 else None


def classify_contract(llm, contract: Contract, *, kinds: Mapping[str, str] | None = None,
                      min_confidence: float = MIN_CONFIDENCE) -> dict:
    """{"kind": document_kind | "unknown", "confidence", "evidence": [{"uid", "quote"}], "reason"?}."""
    kinds = dict(kinds) if kinds is not None else document_kinds()
    head = contract.units[:HEAD_UNITS]
    payload = {"units": [{"uid": u.uid, "text": u.text[:HEAD_CHARS]} for u in head],
               "kinds": [{"id": k, "label": v} for k, v in kinds.items()]}
    try:
        data = ask_json(llm, CLASSIFY_PROMPT, payload, contract.mask_state)
    except ContractAIError:
        return _unknown("llm_error")
    kind, quote, uid = str(data.get("kind") or ""), str(data.get("quote") or ""), str(data.get("unit") or "")
    conf = _confidence(data.get("confidence"))
    if kind == UNKNOWN:
        return _unknown("model_unknown", conf or 0.0)
    text = {u.uid: u.text for u in head}
    if not quote or not quote_ok(text.get(uid, ""), quote):
        uid = next((u for u, t in text.items() if quote and quote_ok(t, quote)), "")
        if not uid:
            return _unknown("quote_not_found", conf or 0.0)
    if kind not in kinds:
        return _unknown("unknown_kind", conf or 0.0)
    if conf is None or conf < min_confidence:
        return _unknown("low_confidence", conf or 0.0)
    return {"kind": kind, "confidence": conf, "evidence": [{"uid": uid, "quote": quote}]}


__all__ = ["AUTO_KIND", "CLASSIFY_PROMPT", "MIN_CONFIDENCE", "UNKNOWN", "classify_contract", "document_kinds"]
