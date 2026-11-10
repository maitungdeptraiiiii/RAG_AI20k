from datetime import date
from pathlib import Path

from rag.legal.models import ProvisionVersion
from rag.legal.vbhn import compare_with_vbhn, normalize_for_compare, parse_consolidation_header

FIXTURES = Path(__file__).parent / "fixtures" / "legal"
KEY = "luat:59/2020/QH14"
VBHN = (FIXTURES / "vbhn_sample.txt").read_text(encoding="utf-8")


def art(n, text):
    return ProvisionVersion(f"{KEY}#d{n}", KEY, "article", text, date(2022, 3, 1), None, "verified", (), (), (), "b")


BUILT = [
    art("49", "Điều 49. Quyền của thành viên công ty\n1. Thành viên công ty có các quyền sau đây:\na) Tham dự họp Hội đồng thành viên."),
    art("50", "Điều 50. Nghĩa vụ của thành viên công ty\n1. Góp đủ, đúng hạn số vốn đã cam kết."),
]


def test_header_cutoff():
    info = parse_consolidation_header(VBHN)
    assert info.target_number == "59/2020/QH14"
    assert info.target_name == "Luật Doanh nghiệp"
    assert info.included == (("03/2022/QH15", date(2022, 3, 1)),)
    assert info.cutoff == date(2022, 3, 1)


def test_normalize_strips_footnotes_and_quotes():
    assert normalize_for_compare("Điều 49. Quyền[1]\n“A”  b") == normalize_for_compare('điều 49. quyền\n"a" b')


def test_footnotes_ignored_equal():
    assert compare_with_vbhn(BUILT, VBHN) == []


def test_text_differs_reported():
    built = [BUILT[0], art("50", BUILT[1].text.replace("đúng hạn", "đúng thời hạn"))]
    (m,) = compare_with_vbhn(built, VBHN)
    assert (m.article, m.reason) == ("50", "vbhn.text_differs")
    assert "thời hạn" in m.built_excerpt and len(m.built_excerpt) <= 200


def test_missing_article():
    (m,) = compare_with_vbhn(BUILT[:1], VBHN)
    assert (m.article, m.reason) == ("50", "vbhn.missing_in_build")
    extra = BUILT + [art("51", "Điều 51. Khác\nNội dung.")]
    (m2,) = compare_with_vbhn(extra, VBHN)
    assert (m2.article, m2.reason) == ("51", "vbhn.missing_in_vbhn")


def test_header_without_dates():
    info = parse_consolidation_header("Luật Nhà ở số 27/2023/QH15 được sửa đổi bởi Luật số 43/2024/QH15.\nĐiều 1. X")
    assert info.cutoff is None and info.included == (("43/2024/QH15", None),)
