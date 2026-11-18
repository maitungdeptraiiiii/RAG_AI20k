"""Test đỏ cho các mục P0 của bản rà 2026-11-15-contract-pipeline-generalization-audit.md (phía hợp đồng).
Mỗi test là xfail(strict=True): khi sửa xong code, test XPASS -> strict làm suite đỏ, nhắc gỡ dấu xfail."""
import pytest

from rag.bridge.facts_map import _duration
from rag.contracts.doc import PageText
from rag.contracts.parts import detect_parts
from rag.contracts.structure import parse_contract
from rag.contracts.values import extract_values
from rag.quality.pii import mask_text

red = pytest.mark.xfail(strict=True, reason="P0 chưa sửa (audit 2026-11-15)")


def _money(text):
    return [v.norm["amount"] for v in extract_values(text) if v.kind == "money"]


@red
@pytest.mark.parametrize("text", [
    "Mức lương 15.000.000đ/tháng", "Mức lương 15.000.000 đ/tháng", "Mức lương 15,000,000 VND/tháng",
    "Mức lương 15tr/tháng"])
def test_money_written_in_common_ways(text):          # 3.1
    assert _money(text) == [15_000_000]


@red
def test_duration_with_number_in_words_and_parentheses():   # 3.1
    assert _duration("thời hạn 12 (mười hai) tháng") == (12, "month")


@red
def test_duration_year_and_month_adds_up():            # 3.2
    assert _duration("thời hạn 1 năm 6 tháng") == (18, "month")


@red
@pytest.mark.parametrize("fmt", ["Điều {n} {t}", "Điều thứ {w}: {t}", "Điều {n}) {t}"])
def test_article_heading_without_dot_still_splits(fmt):    # 2.1
    words = ["nhất", "hai", "ba"]
    text = "\n".join(fmt.format(n=i + 1, w=words[i], t=f"Mục {i + 1}") + f"\nNội dung {i + 1}." for i in range(3))
    assert parse_contract([PageText(None, text)]).report.counts["article"] == 3


@red
@pytest.mark.parametrize("heading", ["BIÊN BẢN THỎA THUẬN SỬA ĐỔI", "BẢN SỬA ĐỔI, BỔ SUNG HỢP ĐỒNG", "Phụ lục A"])
def test_amendment_documents_are_own_part(heading):         # 2.2
    text = f"HỢP ĐỒNG LAO ĐỘNG\nĐiều 1. Lương\nLương 10.000.000 đồng.\n\n{heading}\nLương mới 12.000.000 đồng.\n"
    assert len(detect_parts(text)) == 2


@red
@pytest.mark.parametrize("text,name", [
    ("Ông Nguyễn Văn Tùng sinh năm 1990.", "Nguyễn Văn Tùng"),
    ("Người lao động: Trần Thị Bích Ngọc", "Trần Thị Bích Ngọc"),
    ("Đại diện: Bà Lê Thu Hà, chức vụ Giám đốc", "Lê Thu Hà")])
def test_pii_masks_names_outside_ho_va_ten(text, name):    # 7.1
    assert name not in mask_text(text).masked_text
