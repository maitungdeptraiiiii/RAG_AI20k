import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from rag.config import Settings
from rag.retrieve.hybrid import RetrievalResult
from rag.schema import Chunk, GoldRef, Hit, Question


def runner_module():
    path = Path(__file__).resolve().parents[3] / "evals/team-4.2/runners/run_decomposition_benchmark.py"
    spec = importlib.util.spec_from_file_location("decomposition_benchmark", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_saved_baseline_is_read_only_and_requires_exact_question_ids(tmp_path):
    runner = runner_module()
    questions = [Question("q1", "question", "paraphrase", "test", (GoldRef("law", section="A"),))]
    path = tmp_path / "baseline.csv"
    path.write_text("id,type,config,recall@5,hit@5,mrr@5,recall@20\n"
                    "q1,paraphrase,old,1,1,1,1\n", encoding="utf-8")
    before = path.read_bytes()
    rows = runner.load_saved_baseline(str(path), "old", questions)
    assert rows[0]["config"] == "saved:old" and path.read_bytes() == before
    assert rows[0]["recall@5"] == 1.0
    assert "saved:old" in runner.summary_markdown(rows)
    assert runner.load_saved_baseline(None, "old", questions) == []
    with pytest.raises(ValueError):
        runner.load_saved_baseline(str(path), "missing", questions)
    path.write_text(path.read_text(encoding="utf-8") + "q1,paraphrase,old,1,1,1,1\n", encoding="utf-8")
    with pytest.raises(ValueError):
        runner.load_saved_baseline(str(path), "old", questions)


def test_benchmark_only_executes_new_configuration(tmp_path, monkeypatch):
    runner = runner_module()
    settings = Settings(data_dir=tmp_path, advanced="hyde", rerank_backend="jev")
    settings.index_config_path.parent.mkdir()
    settings.index_config_path.write_text("{}", encoding="utf-8")
    question_path = tmp_path / "questions.jsonl"
    question_path.write_text("synthetic test fixture", encoding="utf-8")
    questions = [Question(f"q{i}", f"question {i}", "paraphrase", "test",
                          (GoldRef("law", section="A"),)) for i in range(64)]
    chunk = Chunk("d:0000", "d", "law", 1, 1, "A", "text")
    hit = Hit(chunk.chunk_id, .9, 1, "rerank")
    decomposer = SimpleNamespace(max_subqueries=3, include_original=True, per_query_k=10,
                                pool_size=30, max_new_articles=10)
    calls = []

    def retrieve(query, k, **kwargs):
        assert retriever.decomposer is decomposer
        calls.append((query, kwargs))
        return RetrievalResult(query, "dense", candidates=[hit], ranked=[hit], hits=[hit], queries=[query])

    retriever = SimpleNamespace(decomposer=decomposer, arms={"dense": SimpleNamespace(fallback=True)},
                                retrieve=retrieve, chunks={chunk.chunk_id: chunk})
    pipeline = SimpleNamespace(retriever=retriever, store=SimpleNamespace(all=lambda: [chunk]))
    monkeypatch.setattr(runner.Settings, "load", lambda: settings)
    monkeypatch.setattr(runner, "load_questions", lambda path: questions)
    monkeypatch.setattr(runner.RAGPipeline, "from_settings", lambda s: pipeline)
    out = tmp_path / "out"
    baseline = tmp_path / "saved.csv"
    baseline.write_text("id,type,config,recall@5,hit@5,mrr@5,recall@20\n" + "".join(
        f"q{i},paraphrase,old,1,1,1,1\n" for i in range(64)), encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["benchmark", "--questions", str(question_path), "--out", str(out),
                                     "--baseline-csv", str(baseline), "--baseline-config", "old"])
    runner.main()
    assert len(calls) == 64 and all(kwargs == {"mode": "dense"} for _, kwargs in calls)
    metadata = json.loads((out / "config.json").read_text(encoding="utf-8"))
    assert metadata["baseline_execution"] is False
    assert "saved:old" in (out / "summary.md").read_text(encoding="utf-8")
    assert len((out / "retrieval_per_question.csv").read_text(encoding="utf-8").splitlines()) == 65
    with pytest.raises(ValueError, match="already contains"):
        runner.main()
    assert len(calls) == 64
