"""Biểu mẫu dữ kiện người dùng của gói đang dùng (câu hỏi gợi ý, spec rule engine §8).

Tên dữ kiện, câu hỏi, giá trị và nhãn đều lấy từ gói; UI chỉ vẽ theo `kind`. Dữ kiện nằm trong `user_facts` mà gói không khai
câu hỏi vẫn được nhập: có đơn vị thì là số, không thì là chữ."""
from __future__ import annotations

from rag.bridge.view import format_value
from rag.rules.model import Catalog
from rag.rules.questions import Question


def _kind(question, unit) -> str:
    if question is None:
        return "number" if unit else "text"
    values = question.values
    if all(isinstance(v, bool) for v in values):
        return "bool"
    if all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in values):
        return "number"
    return "choice"


def user_fact_fields(catalog: Catalog) -> list[dict]:
    """Mỗi dữ kiện người dùng của gói: {key, label, kind: bool|number|choice|text, question, unit, options?}.
    Dữ kiện có câu hỏi đứng trước, theo thứ tự gói khai; phần còn lại xếp theo nhãn."""
    ctx = catalog.context
    names = [n for n in ctx.input_units if n not in ctx.document_facts]
    asked = [n for n in ctx.questions if n in names]
    rest = sorted((n for n in names if n not in ctx.questions), key=lambda n: (catalog.fact_label(n), n))
    out = []
    for name in [*asked, *rest]:
        q = ctx.questions.get(name)
        unit = q.unit if q is not None and q.unit else ctx.input_units.get(name)
        field = {"key": name, "label": catalog.fact_label(name), "kind": _kind(q, unit),
                 "question": q.question if q is not None else None, "unit": unit}
        if field["kind"] == "choice":
            labels = dict(q.labels)
            field["options"] = [{"value": v, "label": labels.get(v, str(v))} for v in q.values]
        out.append(field)
    return out


def _option_label(value, unit, labels: dict) -> str:
    if value in labels:
        return labels[value]
    if isinstance(value, bool):
        return "Có" if value else "Không"
    return format_value(value, unit) if isinstance(value, (int, float)) else str(value)


def question_payload(catalog: Catalog, q: Question) -> dict:
    """Câu hỏi gợi ý (`next_questions`) dạng gửi cho UI: mỗi lựa chọn có nhãn và số kết quả UNKNOWN nó giải quyết (`resolves`)."""
    spec = catalog.context.questions[q.fact]
    labels = dict(spec.labels)
    return {"fact": q.fact, "question": q.question, "unit": q.unit, "guaranteed": q.guaranteed, "possible": q.possible,
            "options": [{"value": v, "label": _option_label(v, q.unit, labels), "resolves": n} for v, n in q.outcomes]}


__all__ = ["question_payload", "user_fact_fields"]
