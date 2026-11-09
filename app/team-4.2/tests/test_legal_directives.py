from pathlib import Path

import pytest

from rag.legal.directives import parse_directives, strip_quotes
from rag.legal.models import Address
from rag.legal.structure import parse_structure

FIXTURES = Path(__file__).parent / "fixtures" / "legal"
AMEND = "luat:03/2022/QH15"


@pytest.fixture(scope="module")
def directives():
    text = (FIXTURES / "luat_03_2022_QH15.txt").read_text(encoding="utf-8")
    return parse_directives(parse_structure(text, AMEND))


def ops(ds):
    return [(d.operation_type, d.target, d.anchor) for d in ds]


def law(ds, name):
    return [d for d in ds if d.target_law_name == name]


def test_real_enterprise_law_article_7(directives):
    ds = law(directives, "Luật Doanh nghiệp")
    assert ops(ds) == [
        ("REPLACE_ARTICLE_TITLE", Address("49", part="title"), None),
        ("REPLACE_CLAUSE_LEAD_IN", Address("49", "1", part="lead_in"), None),
        ("REPLACE_ARTICLE_TITLE", Address("50", part="title"), None),
        ("REPLACE_POINT", Address("60", "2", "e"), None),
        ("REPLACE_CLAUSE", Address("60", "3"), None),
        ("REPLACE_POINT", Address("109", "1", "d"), None),
        ("REPLACE_CLAUSE", Address("148", "1"), None),
        ("REPLACE_CLAUSE", Address("148", "2"), None),
        ("REPLACE_CLAUSE", Address("158", "2"), None),
        ("REPLACE_CLAUSE", Address("217", "5"), None),
    ]
    assert all(d.parse_status == "exact" for d in ds)
    assert ds[4].source_locator == "Điều 7 > 3 > b"
    assert ds[4].new_text.startswith("3. Trường hợp chủ tọa, người ghi biên bản từ chối ký")
    assert ds[4].new_text.endswith("pháp luật có liên quan.")
    assert ds[0].new_text == "Quyền của thành viên công ty"
    assert ds[1].new_text == "1. Thành viên công ty có các quyền sau đây:"
    assert ds[2].new_text == "Nghĩa vụ của thành viên công ty"
    assert [d.sequence for d in directives] == sorted(d.sequence for d in directives)


def test_real_public_investment_nested(directives):
    ds = [d for d in law(directives, "Luật Đầu tư công") if d.source_address.clause == "1"]
    assert ops(ds) == [
        ("REPLACE_POINT", Address("17", "4", "b"), None),
        ("REPLACE_POINT", Address("17", "4", "c"), None),
        ("DELETE_POINT", Address("17", "4", "d"), None),
        ("INSERT_CLAUSE", Address("17", "5a"), Address("17", "5")),
    ]
    assert ds[0].new_text.startswith("b) Chương trình, dự án đầu tư nhóm A")
    assert ds[1].new_text.startswith("c) Chương trình") and ds[1].new_text.endswith("khu vực;")
    assert ds[2].new_text is None


def test_real_insert_point_after(directives):
    ds = [d for d in law(directives, "Luật Đầu tư") if d.source_address.clause == "1"]
    assert ops(ds) == [
        ("REPLACE_POINT", Address("31", "1", "g"), None),
        ("INSERT_POINT", Address("31", "1", "g1"), Address("31", "1", "g")),
    ]
    assert ds[1].new_text.startswith("g1) ")


def test_real_unsupported_appendix(directives):
    investment = [d for d in law(directives, "Luật Đầu tư") if d.source_address.clause == "5"]
    tax = law(directives, "Luật Thuế tiêu thụ đặc biệt")
    for d in investment + tax:
        assert d.operation_type == "UNSUPPORTED" and d.parse_status == "unsupported"
    assert len(investment) == 1 and len(tax) == 1


def test_title_is_directive(directives):
    (d,) = law(directives, "Luật Nhà ở")
    assert (d.operation_type, d.target) == ("REPLACE_CLAUSE", Address("23", "1"))
    assert d.new_text.startswith("1. Có quyền sử dụng đất hợp pháp")


def test_replace_whole_article(directives):
    d = next(d for d in law(directives, "Luật Thi hành án dân sự") if d.source_address.clause == "1")
    assert (d.operation_type, d.target) == ("REPLACE_ARTICLE", Address("55"))
    assert d.new_text.startswith("Điều 55.")


def test_multiline_quoted_clause_with_points(directives):
    d = next(d for d in law(directives, "Luật Doanh nghiệp") if d.target == Address("148", "1"))
    assert "b) Thay đổi ngành, nghề và lĩnh vực kinh doanh;" in d.new_text
    assert "c) Thay đổi cơ cấu tổ chức quản lý công ty;" in d.new_text
    assert not d.new_text.lstrip().startswith("2.")


def test_insert_article_and_insert_clause_with_replace(directives):
    bidding = law(directives, "Luật Đấu thầu")
    assert ops(bidding)[0] == ("INSERT_ARTICLE", Address("33a"), Address("33"))
    electricity = law(directives, "Luật Điện lực")
    assert ops(electricity) == [
        ("REPLACE_CLAUSE", Address("4", "2"), None),
        ("INSERT_CLAUSE", Address("4", "2a"), Address("4", "2")),
        ("INSERT_POINT", Address("40", "1", "d1"), Address("40", "1", "d")),
        ("INSERT_POINT", Address("40", "2", "h1"), Address("40", "2", "h")),
    ]
    assert electricity[1].new_text.startswith("2a. Nhà nước độc quyền")


def _synthetic(quote_open: str, quote_close: str) -> str:
    return ("Điều 1. Sửa đổi, bổ sung một số điều của Luật Doanh nghiệp\n"
            "1. Sửa đổi, bổ sung khoản 2 Điều 10 như sau:\n"
            f"{quote_open}2. Nội dung mới dòng một;\na) Điểm a;\nb) Điểm b.{quote_close}.\n"
            "Điều 2. Hiệu lực thi hành\nLuật này có hiệu lực thi hành từ ngày 01 tháng 7 năm 2026.")


def test_curly_and_straight_quotes_equal():
    straight = parse_directives(parse_structure(_synthetic('"', '"'), "luat:9/2026/QH16"))
    curly = parse_directives(parse_structure(_synthetic("“", "”"), "luat:9/2026/QH16"))
    assert straight[0].new_text == curly[0].new_text == "2. Nội dung mới dòng một;\na) Điểm a;\nb) Điểm b."


def test_bulk_replace_text_is_partial():
    text = ("Điều 1. Sửa đổi, bổ sung một số điều của Luật Doanh nghiệp\n"
            "1. Thay cụm từ “Bộ Kế hoạch và Đầu tư” bằng cụm từ “Bộ Tài chính” tại một số điều của Luật Doanh nghiệp.")
    (d,) = parse_directives(parse_structure(text, "luat:9/2026/QH16"))
    assert d.operation_type == "REPLACE_TEXT" and d.parse_status == "partial"
    assert d.old_phrase == "Bộ Kế hoạch và Đầu tư" and d.new_text == "Bộ Tài chính"
    assert any(r.startswith("operation.bulk_text_scope") for r in d.reasons)


def test_scoped_replace_text_is_exact():
    text = ("Điều 1. Sửa đổi, bổ sung một số điều của Luật Doanh nghiệp\n"
            "1. Thay cụm từ “X” bằng cụm từ “Y” tại khoản 2 Điều 10.")
    (d,) = parse_directives(parse_structure(text, "luat:9/2026/QH16"))
    assert (d.operation_type, d.parse_status, d.target) == ("REPLACE_TEXT", "exact", Address("10", "2"))


def test_unsplittable_content_is_partial():
    text = ("Điều 1. Sửa đổi, bổ sung một số điều của Luật Doanh nghiệp\n"
            "1. Sửa đổi, bổ sung khoản 1 và khoản 2 Điều 10 như sau:\n"
            '"Nội dung không có nhãn khoản.”.')
    ds = parse_directives(parse_structure(text, "luat:9/2026/QH16"))
    assert len(ds) == 2 and all(d.parse_status == "partial" for d in ds)
    assert all("operation.cannot_split_content" in d.reasons for d in ds)


def test_strip_quotes():
    assert strip_quotes('"3. Nội dung.".') == "3. Nội dung."
    assert strip_quotes("“a) X;\nb) Y;”;") == "a) X;\nb) Y;"


def test_no_directive_text_returns_empty():
    text = (FIXTURES / "luat_59_2020_QH14.txt").read_text(encoding="utf-8")
    assert parse_directives(parse_structure(text, "luat:59/2020/QH14")) == []


def test_target_law_by_number_only():
    text = ("Điều 1. Sửa đổi, bổ sung một số điều của Luật số 03/2022/QH15\n"
            "1. Sửa đổi, bổ sung khoản 1 Điều 11 như sau:\n\"1. Nội dung mới.”.")
    (d,) = parse_directives(parse_structure(text, "luat:9/2023/QH15"))
    assert (d.target_law_name, d.target_law_number) == (None, "03/2022/QH15")


def test_kho_dau_is_lead_in():
    # Luật 43/2024/QH15: "Sửa đổi, bổ sung khổ đầu khoản 4 Điều 260"
    text = ("Điều 1. Sửa đổi, bổ sung một số điều của Luật Đất đai số 31/2024/QH15\n"
            "4. Sửa đổi, bổ sung khổ đầu khoản 4 Điều 260 như sau:\n\"4. Phương án sử dụng đất đã được phê duyệt:\".")
    (d,) = parse_directives(parse_structure(text, "luat:43/2024/QH15"))
    assert (d.operation_type, d.target) == ("REPLACE_CLAUSE_LEAD_IN", Address("260", "4", part="lead_in"))
    assert d.target_law_number == "31/2024/QH15" and d.parse_status == "exact"


def _ds(body: str):
    text = "Điều 1. Sửa đổi, bổ sung một số điều của Luật Doanh nghiệp\n" + body
    return parse_directives(parse_structure(text, "luat:9/2026/QH16"))


@pytest.mark.parametrize("line,expected", [
    ("1. Bãi bỏ khoản 2 Điều 10 và khoản 3 Điều 11.",
     [("DELETE_CLAUSE", Address("10", "2"), None), ("DELETE_CLAUSE", Address("11", "3"), None)]),
    ("1. Bãi bỏ Điều 10 và khoản 2 Điều 11.",
     [("DELETE_ARTICLE", Address("10"), None), ("DELETE_CLAUSE", Address("11", "2"), None)]),
    ("1. Bãi bỏ điểm a khoản 1 Điều 10, khoản 3 Điều 11 và Điều 12.",
     [("DELETE_POINT", Address("10", "1", "a"), None), ("DELETE_CLAUSE", Address("11", "3"), None),
      ("DELETE_ARTICLE", Address("12"), None)]),
])
def test_multi_article_target_list(line, expected):
    # Luật Đất đai 31/2024: "Bãi bỏ khoản 3 Điều 36 và khoản 2 Điều 86 của Luật Quản lý, sử dụng tài sản công"
    ds = _ds(line)
    assert ops(ds) == expected and all(d.parse_status == "exact" for d in ds)


def test_multi_article_replace_splits_content():
    ds = _ds('1. Sửa đổi, bổ sung khoản 2 Điều 10 và khoản 3 Điều 11 như sau:\n"2. Nội dung A.\n3. Nội dung B.".')
    assert ops(ds) == [("REPLACE_CLAUSE", Address("10", "2"), None), ("REPLACE_CLAUSE", Address("11", "3"), None)]
    assert [d.new_text for d in ds] == ["2. Nội dung A.", "3. Nội dung B."]


def test_delete_phrase_is_text_operation_not_clause_delete():
    (d,) = _ds("1. Bãi bỏ cụm từ “doanh nghiệp xã hội” tại khoản 2 Điều 10.")
    assert (d.operation_type, d.target, d.old_phrase, d.new_text, d.parse_status) == (
        "REPLACE_TEXT", Address("10", "2"), "doanh nghiệp xã hội", "", "exact")


def test_thay_the_cum_tu():
    (d,) = _ds("1. Thay thế cụm từ “A” bằng cụm từ “B” tại khoản 4 Điều 10.")
    assert (d.operation_type, d.target, d.old_phrase, d.new_text) == ("REPLACE_TEXT", Address("10", "4"), "A", "B")


def test_unknown_phrase_wording_is_partial():
    ds = _ds("1. Sửa đổi cụm từ “X” tại Điều 10 cho phù hợp.")
    assert ds and all(d.parse_status != "exact" for d in ds)


def _doc(text: str):
    return parse_directives(parse_structure(text, "luat:61/2020/QH14"))


def test_clause_level_target_law_in_omnibus_article():
    # Luật Đầu tư 61/2020/QH14, Điều 75: luật đích nằm ở từng khoản, kèm đuôi "đã được sửa đổi ... theo Luật số ..."
    ds = _doc("Điều 75. Sửa đổi, bổ sung một số điều của các luật có liên quan đến đầu tư kinh doanh\n"
              "1. Sửa đổi, bổ sung một số điều của Luật Nhà ở số 65/2014/QH13 đã được sửa đổi, bổ sung một số điều "
              "theo Luật số 40/2019/QH14 như sau:\n"
              "a) Sửa đổi, bổ sung khoản 2 Điều 21 như sau:\n\"2. Có vốn ký quỹ.\";\n"
              "b) Bãi bỏ khoản 3 Điều 22 và Điều 171.\n"
              "2. Sửa đổi, bổ sung một số điều của Luật Kinh doanh bất động sản số 66/2014/QH13 như sau:\n"
              "a) Sửa đổi, bổ sung khoản 1 Điều 10 như sau:\n\"1. Tổ chức kinh doanh.\".\n"
              "Điều 76. Điều khoản thi hành\nLuật này có hiệu lực thi hành từ ngày 01 tháng 01 năm 2021.")
    housing = [d for d in ds if d.target_law_number == "65/2014/QH13"]
    assert [d.target_law_name for d in housing] == ["Luật Nhà ở"] * 3
    assert ops(housing) == [("REPLACE_CLAUSE", Address("21", "2"), None), ("DELETE_CLAUSE", Address("22", "3"), None),
                            ("DELETE_ARTICLE", Address("171"), None)]
    biz = [d for d in ds if d.target_law_number == "66/2014/QH13"]
    assert ops(biz) == [("REPLACE_CLAUSE", Address("10", "1"), None)] and biz[0].target_law_name == "Luật Kinh doanh bất động sản"


def test_article_title_law_with_amended_by_suffix():
    # Luật 62/2020/QH14 Điều 2
    (d,) = _doc("Điều 2. Sửa đổi, bổ sung Điều 17 của Luật Nhà ở số 65/2014/QH13 đã được sửa đổi, bổ sung một số điều "
                "theo Luật số 40/2019/QH14\nSửa đổi, bổ sung Điều 17 như sau:\n"
                "\"Điều 17. Hình thức phát triển nhà ở\n1. Hình thức gồm:\na) Theo dự án.\".")
    assert (d.target_law_name, d.target_law_number) == ("Luật Nhà ở", "65/2014/QH13")
    assert (d.operation_type, d.target, d.parse_status) == ("REPLACE_ARTICLE", Address("17"), "exact")


def test_passive_voice_directive():
    # Luật 34/2009/QH12: "Điều 126 của Luật nhà ở được sửa đổi, bổ sung như sau:"
    ds = _doc("Điều 1. Điều 126 của Luật nhà ở được sửa đổi, bổ sung như sau:\n"
              "\"Điều 126. Quyền sở hữu nhà ở\n1. Người Việt Nam định cư ở nước ngoài.\".\n"
              "Điều 2. Điều 121 của Luật đất đai được sửa đổi, bổ sung như sau:\n"
              "\"Điều 121. Quyền sử dụng đất ở\n1. Nội dung.\".")
    assert [(d.target_law_name, d.operation_type, d.target) for d in ds] == [
        ("Luật nhà ở", "REPLACE_ARTICLE", Address("126")), ("Luật đất đai", "REPLACE_ARTICLE", Address("121"))]
    assert ds[0].new_text.startswith("Điều 126.") and ds[0].parse_status == "exact"


def test_point_level_target_law_in_phrase_scope():
    # Luật Kiến trúc 40/2019/QH14 Điều 39
    ds = _doc("Điều 39. Sửa đổi, bổ sung một số điều của các luật có liên quan đến hoạt động kiến trúc\n"
              "1. Sửa đổi, bổ sung một số điều như sau:\n"
              "b) Thay thế cụm từ “quy chế quản lý quy hoạch kiến trúc đô thị” bằng cụm từ “quy chế quản lý kiến trúc” "
              "tại khoản 2 Điều 20 của Luật Nhà ở số 65/2014/QH13.")
    (d,) = ds
    assert (d.target_law_name, d.target_law_number, d.operation_type, d.target) == (
        "Luật Nhà ở", "65/2014/QH13", "REPLACE_TEXT", Address("20", "2"))


def test_insert_lead_in_before_clause_is_not_a_clause_edit():
    # Luật 61/2020 Điều 75 khoản 2 điểm c: "Bổ sung đoạn mở đầu vào trước khoản 1 Điều 51"
    ds = _doc("Điều 75. Sửa đổi, bổ sung một số điều của Luật Kinh doanh bất động sản\n"
              "1. Bổ sung đoạn mở đầu vào trước khoản 1 Điều 51 như sau:\n\"Thủ tục chuyển nhượng dự án.\".")
    assert ds and all(d.parse_status != "exact" for d in ds)


def test_chapter_replacement_becomes_per_article_pending_ops():
    # Luật 35/2018/QH14 Điều 6 khoản 1: "Sửa đổi, bổ sung Chương IV như sau:" (Luật Đất đai 2013)
    ds = _doc("Điều 6. Sửa đổi, bổ sung một số điều của Luật Đất đai số 45/2013/QH13\n"
              "1. Sửa đổi, bổ sung Chương IV như sau:\n"
              "“CHƯƠNG IV\nQUY HOẠCH, KẾ HOẠCH SỬ DỤNG ĐẤT\n"
              "Điều 35. Nguyên tắc lập quy hoạch\n1. Nội dung.\n"
              "Điều 36. Hệ thống quy hoạch\nNội dung.”.\n"
              "2. Bãi bỏ khoản 3 Điều 50.")
    chapter = [d for d in ds if d.source_address.clause == "1"]
    assert ops(chapter) == [("REPLACE_ARTICLE", Address("35"), None), ("REPLACE_ARTICLE", Address("36"), None)]
    assert all(d.parse_status == "partial" and "operation.chapter_replacement" in d.reasons for d in chapter)
    assert chapter[0].new_text.startswith("Điều 35.") and "Điều 36" not in chapter[0].new_text
    assert ops([d for d in ds if d.source_address.clause == "2"]) == [("DELETE_CLAUSE", Address("50", "3"), None)]


def test_inner_closing_quote_does_not_end_block():
    ds = _ds('1. Sửa đổi, bổ sung Điều 10 như sau:\n'
             '"Điều 10. Doanh nghiệp xã hội\n'
             '1. Doanh nghiệp đáp ứng điều kiện sau được gọi là “doanh nghiệp xã hội”.\n'
             '2. Khoản hai.\n'
             '3. Khoản ba.".\n'
             '2. Bãi bỏ khoản 1 Điều 12.')
    assert ops(ds) == [("REPLACE_ARTICLE", Address("10"), None), ("DELETE_CLAUSE", Address("12", "1"), None)]
    assert "3. Khoản ba." in ds[0].new_text
