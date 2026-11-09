from datetime import date
from pathlib import Path

from rag.legal.effectivity import effective_date_for, parse_effectivity, parse_vn_date
from rag.legal.models import Address
from rag.legal.structure import parse_structure

FIXTURES = Path(__file__).parent / "fixtures" / "legal"


def _info(text: str, key: str = "luat:1/2026/QH16"):
    return parse_effectivity(parse_structure(text, key))


def test_parse_vn_date_forms():
    assert parse_vn_date("ngày 01 tháng 3 năm 2022") == date(2022, 3, 1)
    assert parse_vn_date("01/03/2022") == date(2022, 3, 1)
    assert parse_vn_date("2022-03-01") == date(2022, 3, 1)
    assert parse_vn_date("ngày 31 tháng 02 năm 2026") is None


def test_real_amending_law_single_date():
    text = (FIXTURES / "luat_03_2022_QH15.txt").read_text(encoding="utf-8")
    info = parse_effectivity(parse_structure(text, "luat:03/2022/QH15"))
    assert info.default_from == date(2022, 3, 1)
    assert info.article == "10"
    assert info.transition_article == "11"
    assert info.exceptions == ()
    assert info.flags == ()


def test_unit_exception():
    info = _info("Điều 1. Sửa đổi\n1. A.\n2. B.\n3. C.\nĐiều 3. Hiệu lực thi hành\n"
                 "1. Luật này có hiệu lực thi hành từ ngày 01 tháng 7 năm 2026.\n"
                 "2. Khoản 3 Điều 1 của Luật này có hiệu lực từ ngày 01 tháng 01 năm 2027.")
    assert info.default_from == date(2026, 7, 1)
    assert info.exceptions == ((Address("1", "3"), date(2027, 1, 1)),)
    assert effective_date_for(info, Address("1", "3", "a")) == date(2027, 1, 1)
    assert effective_date_for(info, Address("1", "2")) == date(2026, 7, 1)
    assert effective_date_for(info, None) == date(2026, 7, 1)


def test_repeal_statement():
    info = _info("Điều 198. Hiệu lực thi hành\n1. Luật này có hiệu lực thi hành từ ngày 01 tháng 8 năm 2024.\n"
                 "2. Luật Nhà ở số 65/2014/QH13 hết hiệu lực kể từ ngày Luật này có hiệu lực thi hành.")
    assert info.default_from == date(2024, 8, 1)
    (rep,) = info.repeals
    assert rep.target_number == "65/2014/QH13"
    assert rep.target_name == "Luật Nhà ở"
    assert rep.effective == date(2024, 8, 1)
    assert rep.has_exception is False


def test_repeal_with_exception():
    info = _info("Điều 9. Hiệu lực thi hành\n1. Luật này có hiệu lực thi hành từ ngày 01 tháng 8 năm 2024.\n"
                 "2. Luật Kinh doanh bất động sản số 66/2014/QH13 hết hiệu lực kể từ ngày Luật này có hiệu lực "
                 "thi hành, trừ trường hợp quy định tại Điều 10 của Luật này.")
    assert info.repeals[0].has_exception is True


def test_relative_date_flag():
    info = _info("Điều 2. Hiệu lực thi hành\nLuật này có hiệu lực sau 45 ngày kể từ ngày ký.")
    assert info.default_from is None
    assert any(f.startswith("effectivity.relative_date") for f in info.flags)


def test_invalid_date():
    info = _info("Điều 2. Hiệu lực thi hành\nLuật này có hiệu lực thi hành từ ngày 31 tháng 02 năm 2026.")
    assert info.default_from is None
    assert any(f.startswith("effectivity.invalid_date") for f in info.flags)


def test_no_effectivity_article():
    info = _info("Điều 1. Phạm vi\nNội dung.")
    assert info.article is None and info.default_from is None


def test_real_base_law_picks_effectivity_article_not_namesakes():
    text = (FIXTURES / "luat_59_2020_QH14.txt").read_text(encoding="utf-8")
    info = parse_effectivity(parse_structure(text, "luat:59/2020/QH14"))
    assert info.article == "217"            # không phải Điều 62 "Hiệu lực nghị quyết, quyết định của HĐTV"
    assert info.default_from == date(2021, 1, 1)
    assert info.transition_article == "218"


def test_repeal_ignores_amending_laws_listed_as_context():
    # câu thật trong Luật Nhà ở 27/2023/QH15 và Luật Đầu tư 143/2025/QH15
    info = _info("Điều 198. Hiệu lực thi hành\n1. Luật này có hiệu lực thi hành từ ngày 01 tháng 01 năm 2025.\n"
                 "2. Luật Nhà ở số 65/2014/QH13 đã được sửa đổi, bổ sung một số điều theo Luật số 40/2019/QH14, "
                 "Luật số 61/2020/QH14, Luật số 62/2020/QH14, Luật số 64/2020/QH14 và Luật số 03/2022/QH15 hết hiệu lực "
                 "kể từ ngày Luật này có hiệu lực thi hành, trừ trường hợp quy định tại điểm b khoản 2 Điều 197.\n"
                 "3. Luật Đầu tư số 61/2020/QH14 đã được sửa đổi, bổ sung một số điều theo Luật số 72/2020/QH14 và "
                 "Luật số 03/2022/QH15 (sau đây gọi là Luật Đầu tư năm 2020) hết hiệu lực kể từ ngày Luật này có hiệu lực thi hành.")
    assert [(r.target_name, r.target_number) for r in info.repeals] == [
        ("Luật Nhà ở", "65/2014/QH13"), ("Luật Đầu tư", "61/2020/QH14")]
    assert info.repeals[0].has_exception and not info.repeals[1].has_exception


def test_partial_repeal_is_not_whole_document_repeal():
    info = _info("Điều 9. Hiệu lực thi hành\n1. Luật này có hiệu lực thi hành từ ngày 01 tháng 7 năm 2026.\n"
                 "2. Khoản 3 Điều 248 của Luật Đất đai số 31/2024/QH15 hết hiệu lực kể từ ngày Luật này có hiệu lực thi hành.")
    (rep,) = info.repeals                    # ghi nhận là bãi bỏ MỘT PHẦN (units), không phải cả văn bản
    assert rep.target_number == "31/2024/QH15" and rep.units == (Address("248", "3"),)
    assert rep.effective == date(2026, 7, 1)


def test_ap_dung_unit_exception():
    info = _info("Điều 3. Hiệu lực thi hành\n1. Luật này có hiệu lực thi hành từ ngày 01 tháng 01 năm 2025.\n"
                 "2. Quy định tại khoản 2 Điều 1 của Luật này được áp dụng từ ngày 01 tháng 7 năm 2025.")
    assert info.exceptions == ((Address("1", "2"), date(2025, 7, 1)),)


def test_unexplained_date_is_flagged():
    info = _info("Điều 3. Hiệu lực thi hành\n1. Luật này có hiệu lực thi hành từ ngày 01 tháng 01 năm 2025.\n"
                 "2. Các quy định về đấu giá tại Luật này có hiệu lực từ ngày 01/7/2025.")
    assert info.exceptions == ()
    assert any(f.startswith("effectivity.unit_exception_unresolved") for f in info.flags)


def test_repeal_with_leading_since_clause():
    info = _info("Điều 9. Hiệu lực thi hành\n1. Luật này có hiệu lực thi hành từ ngày 01 tháng 8 năm 2024.\n"
                 "2. Kể từ ngày Luật này có hiệu lực thi hành, Luật Nhà ở số 65/2014/QH13 hết hiệu lực.")
    (rep,) = info.repeals
    assert (rep.target_number, rep.effective, rep.units) == ("65/2014/QH13", date(2024, 8, 1), ())


def test_repeal_records_known_amenders():
    info = _info("Điều 198. Hiệu lực thi hành\n1. Luật này có hiệu lực thi hành từ ngày 01 tháng 8 năm 2024.\n"
                 "2. Luật Nhà ở số 65/2014/QH13 đã được sửa đổi, bổ sung một số điều theo Luật số 40/2019/QH14, "
                 "Luật số 61/2020/QH14 và Luật số 03/2022/QH15 hết hiệu lực kể từ ngày Luật này có hiệu lực thi hành.")
    (rep,) = info.repeals
    assert rep.amended_by == ("40/2019/QH14", "61/2020/QH14", "03/2022/QH15")


def test_exception_lists_several_articles():
    # Điều 252 Luật Đất đai 31/2024/QH15 (bản gốc)
    info = _info("Điều 252. Hiệu lực thi hành\n"
                 "1. Luật này có hiệu lực thi hành từ ngày 01 tháng 01 năm 2025, trừ trường hợp quy định tại khoản 2 và khoản 3 Điều này.\n"
                 "2. Điều 190 và Điều 248 của Luật này có hiệu lực thi hành từ ngày 01 tháng 4 năm 2024.\n"
                 "3. Việc lập quy hoạch được tiếp tục thực hiện theo Nghị quyết số 61/2022/QH15.\n"
                 "Khoản 9 Điều 60 của Luật này có hiệu lực thi hành từ ngày Nghị quyết số 61/2022/QH15 hết hiệu lực.")
    assert info.default_from == date(2025, 1, 1)
    assert info.exceptions == ((Address("190"), date(2024, 4, 1)), (Address("248"), date(2024, 4, 1)))
    assert info.repeals == ()
    assert any(f.startswith("effectivity.conditional") for f in info.flags)
    assert info.conditional_units == (Address("60", "9"),)


def test_exception_clauses_of_one_article():
    info = _info("Điều 3. Hiệu lực thi hành\n1. Luật này có hiệu lực thi hành từ ngày 01 tháng 7 năm 2026.\n"
                 "2. Khoản 1 và khoản 4 Điều 2 của Luật này có hiệu lực thi hành từ ngày 01 tháng 01 năm 2027.")
    assert info.exceptions == ((Address("2", "1"), date(2027, 1, 1)), (Address("2", "4"), date(2027, 1, 1)))
