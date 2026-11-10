from dataclasses import replace
from datetime import date, datetime, timezone

import pytest

from rag.temporal.models import LegalTimeline, TimeAnchor
from rag.temporal.transitions import collect_transition_rules
from tests.test_temporal_index import realestate_service

NOW = datetime(2026, 11, 9, tzinfo=timezone.utc)


def anchor(role, d):
    return TimeAnchor(role, d, d, "day", "question", "x", None, 0.9)


def timeline(*anchors):
    return LegalTimeline(tuple(anchors), anchors[0], (), NOW)


@pytest.fixture(scope="module")
def svc(tmp_path_factory):
    return realestate_service(tmp_path_factory.mktemp("trans"))


def chunk_of(svc, key, day):
    from rag.legal.chunks import export_chunks
    return next(c for c in export_chunks(svc.store, key)
                if c.valid_from <= day and (c.valid_to is None or c.valid_to > day))


def test_family_change_across_anchors_adds_transition_article(svc):
    used = [chunk_of(svc, "luat:65/2014/QH13", date(2023, 6, 15)), chunk_of(svc, "luat:27/2023/QH15", date(2025, 6, 15))]
    rules = collect_transition_rules(svc, used, timeline(anchor("signing", date(2023, 6, 15)),
                                                         anchor("evaluation", date(2025, 6, 15))))
    housing = [r for r in rules if r.new_law_key == "luat:27/2023/QH15"]
    assert housing and housing[0].source_article == "Điều 198" and housing[0].old_law_key == "luat:65/2014/QH13"
    assert housing[0].text.startswith("Điều 198.") and housing[0].new_law_effective_from == date(2024, 8, 1)
    assert set(housing[0].related_roles) == {"signing", "evaluation"}


def test_land_law_has_several_transition_articles(svc):
    used = [chunk_of(svc, "luat:45/2013/QH13", date(2023, 6, 15)), chunk_of(svc, "luat:31/2024/QH15", date(2025, 6, 15))]
    rules = collect_transition_rules(svc, used, timeline(anchor("signing", date(2023, 6, 15)),
                                                         anchor("dispute", date(2025, 6, 15))))
    land = [r.source_article for r in rules if r.new_law_key == "luat:31/2024/QH15"]
    assert "Điều 253" in land and len(land) >= 2


def test_no_rule_when_single_law_applies(svc):
    used = [chunk_of(svc, "luat:27/2023/QH15", date(2025, 6, 15))]
    assert collect_transition_rules(svc, used, timeline(anchor("evaluation", date(2025, 6, 15)))) == []


def test_note_based_rule(svc):
    c = replace(chunk_of(svc, "luat:27/2023/QH15", date(2025, 6, 15)), notes=("note:transition:luat:43/2024/QH15#d5",))
    rules = collect_transition_rules(svc, [c], timeline(anchor("evaluation", date(2025, 6, 15))))
    (r,) = rules
    assert (r.rule_id, r.source_document_key, r.source_article) == ("luat:43/2024/QH15#d5", "luat:43/2024/QH15", "Điều 5")
    assert r.text.startswith("Điều 5.")


def test_rules_unique(svc):
    used = [chunk_of(svc, "luat:65/2014/QH13", date(2023, 6, 15))] * 2 + [chunk_of(svc, "luat:27/2023/QH15", date(2025, 6, 15))]
    rules = collect_transition_rules(svc, used, timeline(anchor("signing", date(2023, 6, 15)),
                                                         anchor("evaluation", date(2025, 6, 15))))
    assert len({r.rule_id for r in rules}) == len(rules)


def test_year_anchor_straddling_change_adds_transition(svc):
    # review I5: mốc cả năm 2024 trùm ngày đổi luật 01/8/2024 -> phải có điều chuyển tiếp của luật mới
    used = [chunk_of(svc, "luat:65/2014/QH13", date(2024, 1, 1)), chunk_of(svc, "luat:27/2023/QH15", date(2024, 9, 1))]
    year = TimeAnchor("signing", date(2024, 1, 1), date(2024, 12, 31), "year", "question", "x", None, 0.9)
    rules = collect_transition_rules(svc, used, timeline(year))
    assert any(r.new_law_key == "luat:27/2023/QH15" and r.old_law_key == "luat:65/2014/QH13" for r in rules)
