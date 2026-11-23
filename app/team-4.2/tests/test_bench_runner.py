"""K2: bộ đo và 6 kịch bản benchmark, so hai evaluator mỗi lần chạy (kế hoạch 2026-11-23-khanh-ingest-bench-eval, Task 6–7)."""
import pytest

from rag.rules.bench.runner import measure, run_axis1, run_axis2
from rag.rules.bench.synth import ObjSpec, RuleSpec


def test_measure_drops_warmup_and_reports_p95():
    calls = []
    t = measure(lambda: calls.append(1), repeats=20, warmup=1)
    assert len(calls) == 21 and t.runs == 20 and t.p95_ms >= t.median_ms >= 0


def test_axis1_small_has_all_scenarios_both_evaluators(tmp_path):
    rows = run_axis1(RuleSpec(30, 0.5, 3, 50, 0), seed=0, repeats=3, root=tmp_path)
    assert {(r.scenario, r.evaluator) for r in rows} >= {(s, e) for s in (1, 2, 3, 4, 5) for e in ("reference", "network")}
    assert {r.size.split("/")[-1] for r in rows if r.scenario == 3} == {"u1", "u5", "u20"}
    assert any(r.recomputed is not None for r in rows if r.evaluator == "network" and r.scenario == 3)
    assert all(r.recomputed is None for r in rows if r.evaluator == "reference")
    assert all(r.peak_kb > 0 for r in rows)


def test_axis1_real_pack_uses_fixture_inputs(tmp_path):
    rows = run_axis1(["labor"], seed=0, repeats=2, root=tmp_path)
    assert {r.scenario for r in rows} == {1, 2, 3, 4, 5} and all(r.size.startswith("labor") for r in rows)


def test_axis2_has_scenario_2_and_6(tmp_path):
    rows = run_axis2(ObjSpec(5, 5, 0), seed=0, repeats=3, root=tmp_path)
    assert {r.scenario for r in rows} == {2, 6}
    assert {r.size.split("/")[-1] for r in rows if r.scenario == 6} == {"add", "remove", "modify"}


def test_digest_same_for_both_evaluators(tmp_path):
    rows = run_axis1(RuleSpec(30, 0.5, 0, 50, 0), seed=0, repeats=3, root=tmp_path)
    rows += run_axis2(ObjSpec(5, 5, 0), seed=0, repeats=3, root=tmp_path)
    by = {}
    for r in rows:
        by.setdefault((r.axis, r.scenario, r.size), set()).add(r.digest)
    assert all(len(v) == 1 for k, v in by.items() if k[1] != 1)


def test_mismatch_raises(monkeypatch, tmp_path):
    import rag.rules.bench.runner as R
    monkeypatch.setattr(R, "_canon", lambda results, kind="x": kind)   # ép hai bên khác nhau
    with pytest.raises(R.EvaluatorMismatch) as e:
        run_axis1(RuleSpec(10, 0.5, 0, 50, 0), seed=7, repeats=1, root=tmp_path)
    assert "seed 7" in str(e.value)
