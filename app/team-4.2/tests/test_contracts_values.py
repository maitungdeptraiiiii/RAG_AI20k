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
