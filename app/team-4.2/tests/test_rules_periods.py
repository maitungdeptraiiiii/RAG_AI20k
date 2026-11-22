"""Giá trị luật theo kỳ không cần dữ kiện chọn (`by`): mỗi kỳ một `value`, chọn theo ngày soát.

Dùng cho mức luật đổi theo thời gian mà không theo vùng / loại (vd. trần lãi vay: BLDS 2005 150% lãi suất cơ bản trước
01/01/2017, BLDS 2015 20%/năm từ 01/01/2017)."""
from datetime import date

import pytest

from rag.rules.evaluator import evaluator_for
from rag.rules.explain import explain
from rag.rules.loader import load_packs
from rag.rules.model import CatalogError
from rag.rules.semantics import Fact
from rules_synth import concept, rule, write_pack

PACK = {"units": ["percent_per_year"], "conversions": {"percent_per_year": {"base": "percent_per_year", "factor": 1}},
        "user_facts": ["rate"]}
LAW = {"cap": {"unit": "percent_per_year", "periods": [
    {"valid_from": "2010-12-01", "value": 13.5, "source": "bo-luat:33/2005/QH11#d476.k1"},
    {"valid_from": "2017-01-01", "value": 20, "source": "bo-luat:91/2015/QH13#d468.k1"}]}}


def _cat(tmp_path, law=LAW):
    r = rule("r1", mode="threshold", law=law, check={"fact": "rate", "op": "lte", "law": "cap"})
    write_pack(tmp_path, PACK, [concept("c.cap", [r])], pack_id="per")
    return load_packs(["per"], root=tmp_path)


@pytest.mark.parametrize("kind", ["reference", "network"])
@pytest.mark.parametrize("day,rate,status,cap", [
    (date(2016, 6, 1), 15, "FAIL", 13.5), (date(2016, 6, 1), 12, "PASS", 13.5),
    (date(2018, 1, 1), 15, "PASS", 20), (date(2018, 1, 1), 24, "FAIL", 20)])
def test_period_value_chosen_by_review_day(tmp_path, kind, day, rate, status, cap):
    cat = _cat(tmp_path)
    s = evaluator_for(cat, kind).session(day=day, facts={"rate": Fact(rate, "percent_per_year")},
                                         present={"c.cap"}, evidence={})
    r = s.results()[0]
    assert (r.status, r.law_values["cap"]["value"]) == (status, cap)


def test_day_before_first_period_is_unknown_not_violation(tmp_path):
    cat = _cat(tmp_path)
    s = evaluator_for(cat, "network").session(day=date(2009, 1, 1), facts={"rate": Fact(30, "percent_per_year")},
                                              present={"c.cap"}, evidence={})
    r = s.results()[0]
    assert r.status == "UNKNOWN" and "law_period_not_covered" in r.reasons


def test_explain_shows_period_source(tmp_path):
    cat = _cat(tmp_path)
    s = evaluator_for(cat, "reference").session(day=date(2016, 6, 1), facts={"rate": Fact(15, "percent_per_year")},
                                                present={"c.cap"}, evidence={})
    law = next(n for n in explain(cat, s, "c.cap", "r1").children if n.kind == "law")
    assert (law.detail["value"], law.detail["source"], law.detail["valid_from"]) == (
        13.5, "bo-luat:33/2005/QH11#d476.k1", "2010-12-01")


@pytest.mark.parametrize("periods", [
    [{"valid_from": "2017-01-01"}],                                       # thiếu value
    [{"valid_from": "2017-01-01", "values": {"I": 1}}],                   # values mà không có by
    [{"value": 20}],                                                      # thiếu valid_from
])
def test_loader_rejects_malformed_unkeyed_periods(tmp_path, periods):
    with pytest.raises(CatalogError):
        _cat(tmp_path, {"cap": {"unit": "percent_per_year", "periods": periods}})
