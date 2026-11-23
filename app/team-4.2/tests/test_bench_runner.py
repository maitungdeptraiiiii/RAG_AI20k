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


def test_empty_output_on_both_sides_is_an_error_not_a_pass():
    import rag.rules.bench.runner as R
    with pytest.raises(R.DegenerateScenario):
        R._check({"reference": ["[]"], "network": ["[]"]}, 5, "x", 0, "")
    with pytest.raises(R.DegenerateScenario):
        R._check({"reference": ["[]", "[]"], "network": ["[]", "[]"]}, 3, "x", 0, "")
    assert R._check({"reference": ["[]", "[1]"], "network": ["[]", "[1]"]}, 3, "x", 0, "")


def test_scenario5_asks_questions_on_synthetic_and_real_packs(tmp_path, monkeypatch):
    import rag.rules.bench.runner as R
    seen = []
    real = R.next_questions
    monkeypatch.setattr(R, "next_questions", lambda cat, s: seen.append(len(real(cat, s))) or real(cat, s))
    run_axis1(RuleSpec(30, 0.5, 3, 50, 0), seed=0, repeats=1, root=tmp_path)
    run_axis1(["labor"], seed=0, repeats=1, root=tmp_path)
    assert seen and min(seen) > 0


def test_load_note_times_only_the_loader(tmp_path, monkeypatch):
    import rag.rules.bench.runner as R
    import time
    slow = R._real_inputs
    monkeypatch.setattr(R, "_real_inputs", lambda *a: (time.sleep(1.5), slow(*a))[1])
    note = next(r.note for r in run_axis1(["labor"], seed=0, repeats=1, root=tmp_path) if r.scenario == 1)
    assert float(note.split("nạp YAML ")[1].split(" s")[0]) < 1.5


def test_rows_survive_an_error_mid_config(tmp_path, monkeypatch):
    import rag.rules.bench.runner as R
    monkeypatch.setattr(R, "next_questions", lambda *a: 1 / 0)
    sink = []
    with pytest.raises(ZeroDivisionError):
        run_axis1(RuleSpec(10, 0.5, 0, 50, 0), seed=0, repeats=1, root=tmp_path, sink=sink)
    assert {r.scenario for r in sink} == {1, 2, 3, 4}


def test_mismatch_raises(monkeypatch, tmp_path):
    import rag.rules.bench.runner as R
    monkeypatch.setattr(R, "_canon", lambda results, kind="x": kind)   # ép hai bên khác nhau
    with pytest.raises(R.EvaluatorMismatch) as e:
        run_axis1(RuleSpec(10, 0.5, 0, 50, 0), seed=7, repeats=1, root=tmp_path)
    assert "seed 7" in str(e.value)


# ───────────────────────────── script (Task 7) ─────────────────────────────
import importlib.util  # noqa: E402
import json  # noqa: E402
from pathlib import Path  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def _script():
    spec = importlib.util.spec_from_file_location("bench_rule_engine", ROOT / "scripts" / "bench_rule_engine.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _strip(out: Path):
    data = json.loads(next(out.glob("*.json")).read_text(encoding="utf-8"))
    return [{k: v for k, v in r.items() if k not in ("median_ms", "p95_ms", "peak_kb", "note")} for r in data["rows"]]


def test_quick_run_twice_same_table_except_timing(tmp_path):
    main = _script().main
    assert main(["--quick", "--seed", "0", "--out", str(tmp_path / "a")]) == 0
    assert main(["--quick", "--seed", "0", "--out", str(tmp_path / "b")]) == 0
    assert _strip(tmp_path / "a") == _strip(tmp_path / "b")


def test_summary_has_machine_six_scenarios_two_axes_and_charts(tmp_path):
    _script().main(["--quick", "--seed", "0", "--out", str(tmp_path)])
    md = (tmp_path / "summary.md").read_text(encoding="utf-8")
    assert "Python" in md and "CPU" in md and "RAM" in md
    assert all(f"Kịch bản {i}" in md for i in range(1, 7)) and "Trục 1" in md and "Trục 2" in md
    assert (tmp_path / "axis1.png").exists() and (tmp_path / "axis2.png").exists()


def test_unexpected_error_still_writes_partial_output(tmp_path, monkeypatch):
    mod = _script()
    calls = []

    def boom(spec, **kw):
        if calls:
            raise KeyError("x")
        calls.append(1)
        return run_axis2(ObjSpec(1, 5, 0), seed=0, repeats=1, root=kw["root"], sink=kw["sink"])
    monkeypatch.setattr(mod, "run_axis1", boom)
    assert mod.main(["--quick", "--seed", "0", "--out", str(tmp_path)]) == 2
    data = json.loads(next(tmp_path.glob("*.json")).read_text(encoding="utf-8"))
    assert "KeyError" in data["error"] and data["rows"]
