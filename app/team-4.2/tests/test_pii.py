"""W02-02f — mask PII: mẫu dương theo loại, mẫu âm của văn bản luật."""

import pytest

from rag.quality.pii import MaskState, column_pii_type, count_by_type, mask_cells, mask_text


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Email: a.b@example.test", "Email: [EMAIL_1]"),
        ("Gửi về a.b@example.test.", "Gửi về [EMAIL_1]."),           # dấu chấm cuối câu
        ("Gửi a.b@example.test, rồi gọi", "Gửi [EMAIL_1], rồi gọi"),
        ("ĐT: 0912 345 678", "ĐT: [PHONE_1]"),
        ("ĐT 0912.345.678", "ĐT [PHONE_1]"),
        ("gọi 0912345678", "gọi [PHONE_1]"),
        ("+84 912 345 678", "[PHONE_1]"),
        ("84912345678", "[PHONE_1]"),
        ("Cố định 024 3974 1234", "Cố định [PHONE_1]"),
        ("CCCD: 001203004567", "CCCD: [CCCD_1]"),
        ("số 001203004567", "số [CCCD_1]"),
        ("CMND số 123456789", "CMND số [CMND_1]"),
        ("MST 0101234567", "MST [MST_1]"),
        ("Mã số thuế: 0101234567-001", "Mã số thuế: [MST_1]"),
        ("STK 0123456789012", "STK [BANK_1]"),
        ("số tài khoản 1903 1234 5678", "số tài khoản [BANK_1]"),
        ("Họ và tên: Nguyễn Minh An, sinh năm 1990", "Họ và tên: [NAME_1], sinh năm 1990"),
    ],
)
def test_masks_each_pii_type(text, expected):
    assert mask_text(text).masked_text == expected


@pytest.mark.parametrize(
    "text, expected",
    [
        ("ĐT: 0912 345678", "ĐT: [PHONE_1]"),
        ("ĐT: 0912.345678", "ĐT: [PHONE_1]"),
        ("ĐT: 0912-345678.", "ĐT: [PHONE_1]."),
        ("Mức 0912 3456789 đồng", "Mức 0912 3456789 đồng"),      # 4-7: sai độ dài, không phải SĐT
        ("Mã 0123 456789", "Mã 0123 456789"),                    # đầu số 01 không phải di động
        ("Số 0912 345678.5", "Số 0912 345678.5"),                # dính phần thập phân phía sau
    ],
)
def test_phone_four_six_grouping(text, expected):
    assert mask_text(text).masked_text == expected


@pytest.mark.parametrize(
    "text, expected",
    [
        # tên dừng ở từ viết thường đầu tiên, không nuốt chữ phía sau
        ("Họ và tên: Nguyễn Minh An sinh năm 1990", "Họ và tên: [NAME_1] sinh năm 1990"),
        ("Họ tên: Lê Văn C có hộ khẩu tại Hà Nội", "Họ tên: [NAME_1] có hộ khẩu tại Hà Nội"),
        ("Họ tên người nộp: Trần Thị Bình nộp hồ sơ", "Họ tên người nộp: [NAME_1] nộp hồ sơ"),
        ("Họ và tên: Đặng Thị Ánh Tuyết", "Họ và tên: [NAME_1]"),
        # không đủ 2 từ viết hoa -> không coi là tên
        ("Họ và tên: chưa khai báo", "Họ và tên: chưa khai báo"),
        ("Họ và tên: An sinh năm 1990", "Họ và tên: An sinh năm 1990"),
    ],
)
def test_name_stops_at_first_lowercase_word(text, expected):
    assert mask_text(text).masked_text == expected


@pytest.mark.parametrize(
    "text",
    [
        "Phạt tiền 84.000.000.000 đồng",          # số tiền bắt đầu bằng 84 (lỗi cũ: bị coi là SĐT)
        "Phạt 84.500.000.000 đồng",
        "mức 840.000.000 đồng",
        "Mức phạt từ 5.000.000 - 10.000.000 đồng",
        "Luật số 45/2019/QH14 ngày 20/11/2019",
        "Quyết định 0912/QĐ-UBND",
        "Điều 123 khoản 2 điểm a",
        "Có hiệu lực từ ngày 01.07.2026",
        "năm 2026 có 1.500.000 người",
        "Mã hồ sơ 123456789",                      # 9 số không có từ khoá CMND
        "Mã thủ tục 0101234567",                   # 10 số không có từ khoá MST, không phải đầu số di động
    ],
)
def test_does_not_mask_legal_numbers(text):
    result = mask_text(text)
    assert result.masked_text == text and result.safe_findings == ()


def test_same_value_gets_same_placeholder_and_findings_have_no_raw_value():
    result = mask_text("Gọi 0912345678, nếu không được gọi lại 0912345678 hoặc 0987654321.")
    assert result.masked_text == "Gọi [PHONE_1], nếu không được gọi lại [PHONE_1] hoặc [PHONE_2]."
    assert count_by_type(result.safe_findings) == {"phone": 3}
    assert "0912345678" not in repr(result.safe_findings)


def test_column_header_masks_whole_cell():
    assert column_pii_type("Số điện thoại liên hệ") == "phone"
    assert column_pii_type("Họ và tên") == "name"
    assert column_pii_type("Mức phạt") is None
    rows = (("Lê Văn C", "0100000003"),)
    masked, findings = mask_cells(rows, column_types={0: "name", 1: "mst"})
    assert masked == (("[NAME_1]", "[MST_1]"),)
    assert [f.entity_type for f in findings] == ["name", "mst"]
    assert all(f.location and "Lê" not in f.location for f in findings)


def test_known_values_are_masked_elsewhere_in_document():
    state = MaskState()
    mask_cells((("0100000003",),), column_types={0: "mst"}, state=state)
    text, n = state.mask_known("Mã số doanh nghiệp 0100000003 | 01000000031")
    assert text == "Mã số doanh nghiệp [MST_1] | 01000000031" and n == 1


# --- kiểm tra rò rỉ end-to-end ----------------------------------------------------
