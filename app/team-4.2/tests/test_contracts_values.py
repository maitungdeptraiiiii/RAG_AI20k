from rag.contracts.values import extract_values


def kinds(text):
    return [(v.kind, v.norm) for v in extract_values(text)]


def test_money_forms():
    assert kinds("Tiền thuê 30.000.000 đồng/tháng") == [("money", {"amount": 30000000, "currency": "VND"})]
    assert kinds("đặt cọc 90 triệu đồng") == [("money", {"amount": 90000000, "currency": "VND"})]
    assert kinds("giá 1,5 tỷ VNĐ") == [("money", {"amount": 1500000000, "currency": "VND"})]
    assert kinds("phí 2.000 USD") == [("money", {"amount": 2000, "currency": "USD"})]


def test_percent_and_dates():
    assert kinds("phạt 20% giá trị") == [("percent", {"percent": 20.0})]
    assert kinds("ký ngày 15 tháng 3 năm 2023") == [("date", {"iso": "2023-03-15"})]
    assert kinds("từ 01/08/2024") == [("date", {"iso": "2024-08-01"})]


def test_duration_not_taken_from_inside_a_date():
    vals = kinds("ngày 15 tháng 3 năm 2023, báo trước 30 ngày, thời hạn 3 năm")
    assert vals == [("date", {"iso": "2023-03-15"}), ("duration", {"n": 30, "unit": "ngày"}),
                    ("duration", {"n": 3, "unit": "năm"})]


def test_spans_point_at_raw_text():
    text = "đặt cọc 90 triệu đồng"
    v = extract_values(text)[0]
    assert text[v.start:v.end] == v.raw == "90 triệu đồng"


def test_invalid_date_reserves_its_span():
    assert kinds("ngày 31 tháng 2 năm 2023") == []
    assert kinds("ngày 15 tháng 3, năm 2023") == [("date", {"iso": "2023-03-15"})]


def test_duration_not_taken_from_decimal_or_grouped_number():
    assert kinds("thời hạn 1,5 năm") == []
    assert kinds("trong 2.000 ngày") == []


def test_money_does_not_absorb_preceding_integer():
    assert kinds("Điều 5 200.000 đồng") == [("money", {"amount": 200000, "currency": "VND"})]
    assert kinds("Điều 5\n200.000 đồng") == [("money", {"amount": 200000, "currency": "VND"})]
    assert kinds("cọc 5 100 000 đồng") == [("money", {"amount": 5100000, "currency": "VND"})]


def test_values_do_not_cross_newlines_or_take_id_numbers():
    # số CCCD / điện thoại không thành thời hạn / tiền; không nối qua dòng
    assert kinds("CCCD số: 001203004567 Ngày cấp: 12/03/2021") == [("date", {"iso": "2021-03-12"})]
    assert kinds("Điện thoại: 0912345678\nNgày sinh: 01/02/1990") == [("date", {"iso": "1990-02-01"})]
    assert kinds("mã 1234567 ngày") == []
    assert kinds("số 0912345678 đồng") == []
    assert kinds("5\nngày") == [] and kinds("30\nđồng") == [] and kinds("20\n%") == []
    assert kinds("trong vòng 05 ngày làm việc") == [("duration", {"n": 5, "unit": "ngày"})]
