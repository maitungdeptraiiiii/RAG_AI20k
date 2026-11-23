"""user_fact_fields(): biểu mẫu dữ kiện người dùng sinh từ gói, không có danh sách viết cứng."""
import pytest

from rag.bridge.catalog import load_catalog
from rag.bridge.user_form import user_fact_fields
from rag.rules.loader import load_packs
from rules_synth import concept, rule, write_pack


@pytest.fixture(scope="module")
def synth(tmp_path_factory):
    root = tmp_path_factory.mktemp("uf")
    write_pack(root, {
        "user_facts": ["flag", "days", "region", "note", "plain_n", "unasked"],
        "user_fact_units": {"plain_n": "day"},
        "user_fact_questions": {
            "region": {"question": "Vùng nào?", "values": ["I", "II"], "labels": {"I": "Vùng I"}},
            "flag": {"question": "Có không?", "values": [True, False]},
            "days": {"question": "Bao nhiêu ngày?", "values": [5, 50], "unit": "day"}},
        "labels": {"facts": {"flag": "Cờ", "region": "Vùng", "note": "Ghi chú", "days": "Số ngày"}}},
        [concept("c.a", [rule("r1")])], pack_id="uf")
    return load_packs(["uf"], root=root)


def by_key(fields):
    return {f["key"]: f for f in fields}


def test_kind_follows_question_values_then_unit(synth):
    f = by_key(user_fact_fields(synth))
    assert f["flag"]["kind"] == "bool" and f["flag"]["question"] == "Có không?"
    assert f["days"]["kind"] == "number" and f["days"]["unit"] == "day"
    assert f["region"]["kind"] == "choice"
    assert f["plain_n"]["kind"] == "number"                       # không câu hỏi nhưng có đơn vị
    assert f["note"]["kind"] == "text" and f["note"]["question"] is None


def test_choice_options_use_pack_labels_and_fall_back_to_value(synth):
    region = by_key(user_fact_fields(synth))["region"]
    assert region["options"] == [{"value": "I", "label": "Vùng I"}, {"value": "II", "label": "II"}]
    assert "options" not in by_key(user_fact_fields(synth))["flag"]


def test_order_asked_facts_first_then_by_label(synth):
    keys = [f["key"] for f in user_fact_fields(synth)]
    assert keys[:3] == list(synth.context.questions)               # theo thứ tự gói khai câu hỏi
    assert keys[3:] == sorted(keys[3:], key=lambda k: by_key(user_fact_fields(synth))[k]["label"])


def test_label_comes_from_pack_and_falls_back_to_name(synth):
    f = by_key(user_fact_fields(synth))
    assert f["flag"]["label"] == "Cờ" and f["unasked"]["label"] == "unasked"


def test_pack_without_user_facts_has_empty_form(tmp_path):
    write_pack(tmp_path, {}, [concept("c.a", [rule("r1")])], pack_id="none")
    assert user_fact_fields(load_packs(["none"], root=tmp_path)) == []


def test_labor_form_comes_from_pack_not_a_fixed_list():
    f = by_key(user_fact_fields(load_catalog()))
    assert f["fixed_term_contract_count"]["kind"] == "number"
    assert f["wage_region"]["kind"] == "choice" and [o["value"] for o in f["wage_region"]["options"]] == ["I", "II", "III", "IV"]
    assert f["work_condition"]["options"][0] == {"value": "binh_thuong", "label": "Bình thường"}
    assert f["pregnant"]["kind"] == "bool"
    assert "sign_date" not in f and "term_months" not in f         # dữ kiện của hợp đồng, không hỏi người dùng
    assert len(f) == 15
