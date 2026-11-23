"""E3: chạy hồ sơ / kịch bản thành dòng sự kiện (kế hoạch 2026-11-23-w04-remaining, Task 4)."""
import json
from pathlib import Path

import pytest
import yaml

from rag.rules.scenario import DOSSIER_ROOT, list_dossiers, run_scenario

SCENARIO_IDS = sorted(p.parent.name for p in Path(DOSSIER_ROOT).glob("*/scenario.yaml"))


def _types(events):
    return [e["type"] for e in events]


def test_a1_scenario_events_in_order_and_match_expectations():
    events = list(run_scenario("a1"))
    sc = yaml.safe_load((Path(DOSSIER_ROOT) / "a1" / "scenario.yaml").read_text(encoding="utf-8"))
    assert _types(events)[:3] == ["step", "evaluation", "expect"]
    steps = [e for e in events if e["type"] == "step"]
    assert [s["index"] for s in steps] == list(range(len(sc["steps"]))) and steps[0]["do"] == "load"
    expects = [e for e in events if e["type"] == "expect"]
    assert len(expects) == len(sc["steps"]) and all(r["ok"] for e in expects for r in e["results"])
    diffs = [e for e in events if e["type"] == "evaluation_diff"]
    assert diffs and all(d["stats"] and "nodes_recomputed" in d["stats"] for d in diffs)       # network
    # bước đổi ngày 2024-07-15: lương tối thiểu vùng đổi PASS -> FAIL, kèm cây giải thích của rule đó
    step1 = [e for e in events if e.get("step") == 1]
    change = next(c for e in step1 if e["type"] == "evaluation_diff" for c in e["changes"]
                  if c["concept_id"] == "wage.minimum_regional" and c["rule_id"] == "r1")
    assert (change["before"]["status"], change["after"]["status"]) == ("PASS", "FAIL")
    tree = next(e for e in step1 if e["type"] == "explain" and e["concept_id"] == "wage.minimum_regional")["tree"]
    assert tree["kind"] == "rule" and tree["status"] == "FAIL" and tree["children"]


def test_explain_tree_reaches_the_contract_quote():
    events = list(run_scenario("a1"))
    trees = [e["tree"] for e in events if e["type"] == "explain"]

    def quotes(n):
        return ([n["detail"]["quote"]] if n["detail"].get("quote") else []) + [q for c in n["children"] for q in quotes(c)]
    assert any(quotes(t) for t in trees)


def test_reference_and_network_emit_same_results():
    def core(evaluator):
        return [(e["type"], e.get("step"), json.dumps(e.get("results") or e.get("changes"), sort_keys=True))
                for e in run_scenario("a1", evaluator=evaluator) if e["type"] in ("evaluation", "evaluation_diff", "expect")]
    assert core("reference") == core("network")
    assert all(e["stats"] is None for e in run_scenario("a1", evaluator="reference") if e["type"] == "evaluation_diff")


@pytest.mark.parametrize("did", SCENARIO_IDS)
def test_every_fixture_scenario_runs_and_meets_its_expectations(did):
    events = list(run_scenario(did))
    bad = [r for e in events if e["type"] == "expect" for r in e["results"] if not r["ok"]]
    assert not bad, bad
    assert "questions" in _types(events)


def test_questions_event_has_the_user_fact_and_affected_rules():
    qs = [e for e in run_scenario("b1") if e["type"] == "questions"]
    assert qs and all({"fact", "question", "guaranteed"} <= set(q) for e in qs for q in e["items"])


def test_answer_step_updates_facts_and_emits_diff():
    events = list(run_scenario("b1"))                       # b1 là kịch bản có bước `answer`
    assert any(e["type"] == "step" and e["do"] == "answer" for e in events)
    diff = next(e for e in events if e["type"] == "evaluation_diff" and e["cause"]["kind"] == "answer")
    assert diff["cause"]["facts"] and diff["changes"]


def test_unknown_dossier_and_bad_evaluator_are_errors():
    with pytest.raises(LookupError, match="không có"):                 # R.8: hồ sơ không có -> 404 ở route
        list(run_scenario("khong_co"))
    with pytest.raises(ValueError, match="evaluator"):
        list(run_scenario("a1", evaluator="x"))


def test_unknown_step_kind_is_error(tmp_path):
    d = tmp_path / "z1"
    d.mkdir()
    src = Path(DOSSIER_ROOT) / "a1"
    for f in ("dossier.yaml", "objects.yaml", "facts.yaml"):
        (d / f).write_text((src / f).read_text(encoding="utf-8"), encoding="utf-8")
    (d / "scenario.yaml").write_text(yaml.safe_dump({"dossier_id": "z1", "steps": [
        {"do": "load", "state": "z1", "review_date": "2023-06-01", "say": "x"}, {"do": "foo", "say": "y"}]}), encoding="utf-8")
    with pytest.raises(ValueError, match="foo"):
        list(run_scenario("z1", root=tmp_path))


def test_list_dossiers_marks_scenarios():
    rows = {r["dossier_id"]: r for r in list_dossiers()}
    assert rows["a1"]["has_scenario"] and rows["a1"]["packs"] == ["labor"] and rows["b2"]["has_scenario"] is False


def _copy_dossier(tmp_path, did="b1", scenario=None):
    import shutil
    shutil.copytree(Path(DOSSIER_ROOT) / did, tmp_path / did)
    if scenario is not None:
        (tmp_path / did / "scenario.yaml").write_text(yaml.safe_dump(scenario, allow_unicode=True), encoding="utf-8")
    return tmp_path


@pytest.mark.parametrize("steps,why", [
    ([{"do": "add", "state": "b1"}], "load"),                                       # add trước load
    ([{"do": "answer", "facts": {"x": 1}}], "load"),                                # answer trước load
    ([{"do": "load"}], "review_date"),                                              # load thiếu ngày soát
    ([{"do": "load", "review_date": "2025-01-01"}, {"do": "set_review_date"}], "value"),
    ([{"do": "load", "review_date": "2025-01-01"}, {"do": "answer"}], "facts"),
    ([{"do": "load", "review_date": "2025-01-01"}, {"do": "add"}], "state"),
    ({"steps": "không phải danh sách"}, "steps"),
])
def test_malformed_scenario_is_value_error_before_any_event(tmp_path, steps, why):
    """Hạn chế R.8: scenario.yaml hỏng -> ValueError (400) nêu khóa thiếu, không KeyError (404) / lỗi lạ (500)."""
    root = _copy_dossier(tmp_path, scenario=steps if isinstance(steps, dict) else {"steps": steps})
    with pytest.raises(ValueError) as e:
        list(run_scenario("b1", root=root))
    assert why in str(e.value)


def test_unknown_dossier_is_lookup_error():
    from rag.rules.scenario import UnknownDossier
    for did in ("khong_co", "../b1", "b1/../a1"):
        with pytest.raises(UnknownDossier):
            list(run_scenario(did))


def test_dossier_root_from_env(tmp_path, monkeypatch):
    """Hạn chế R.3: chạy ngoài môi trường dev đổi thư mục hồ sơ bằng RAG_DOSSIER_ROOT."""
    root = _copy_dossier(tmp_path)
    monkeypatch.setenv("RAG_DOSSIER_ROOT", str(root))
    assert [d["dossier_id"] for d in list_dossiers()] == ["b1"]
    assert next(iter(run_scenario("b1")))["type"] == "step"
