"""Tách `effectivity_reasons_for_text` khỏi `unsupported_effectivity_reasons` không được đổi hành vi luồng cũ:
`source_text` vốn đã NFC + casefold, nên chữ hoa ("Riêng Điều", "Hiệu lực") cho cùng kết quả qua cả hai đường."""

from datetime import date
from types import SimpleNamespace

from rag.versioning.effectivity_guard import effectivity_reasons_for_text, unsupported_effectivity_reasons

TEXTS = [
    "Luật này có hiệu lực thi hành từ ngày 01 tháng 7 năm 2026. Riêng Điều 3 có hiệu lực từ ngày 01 tháng 01 năm 2027.",
    "Hiệu lực thi hành: Luật này có hiệu lực sau 45 ngày kể từ ngày ký.",
    "Hồ sơ nộp trước ngày Luật này có hiệu lực thì tiếp tục áp dụng quy định cũ.",
]


def test_wrapper_and_text_function_agree_on_capitalised_input():
    for text in TEXTS:
        parsed = SimpleNamespace(blocks=[SimpleNamespace(text=text, order=0, table=None)])
        for eff in (None, date(2026, 7, 1)):
            assert unsupported_effectivity_reasons(parsed, effective_from=eff) == \
                effectivity_reasons_for_text(text, effective_from=eff)


def test_capitalised_unit_exception_is_flagged():
    reasons = effectivity_reasons_for_text(TEXTS[0], effective_from=None)
    assert any(r.startswith("effectivity.unit_exception") for r in reasons)
