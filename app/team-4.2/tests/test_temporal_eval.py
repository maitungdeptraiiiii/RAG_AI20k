import importlib.util
import json
from pathlib import Path

import pytest

from rag.temporal.index import VersionedIndex
from tests.test_temporal_index import realestate_service

REPO = Path(__file__).resolve().parents[3]
RUNNER = REPO / "evals" / "team-4.2" / "runners" / "run_temporal_eval.py"
DATASET = REPO / "evals" / "team-4.2" / "datasets" / "temporal_qa_realestate.jsonl"


def load_runner():
    spec = importlib.util.spec_from_file_location("run_temporal_eval", RUNNER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def report(tmp_path_factory):
    runner = load_runner()
    svc = realestate_service(tmp_path_factory.mktemp("teval"))
    index = VersionedIndex(svc.store)
    index.build()
    return runner.evaluate(runner.load_dataset(DATASET), index, k=10)


def test_dataset_has_enough_questions():
    rows = [json.loads(line) for line in DATASET.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(rows) >= 15
    for r in rows:
        assert {"id", "question", "asked_at", "expected_anchors", "expected_documents", "forbidden_documents"} <= set(r)


def test_version_accuracy_is_perfect_on_fixture(report):
    failed = [r["id"] for r in report["rows"] if not r["version_ok"]]
    assert report["version_accuracy"] == 1.0, failed


def test_anchor_accuracy_at_least_90(report):
    failed = [r["id"] for r in report["rows"] if not r["anchor_ok"]]
    assert report["anchor_accuracy"] >= 0.9, failed


def test_forbidden_document_is_a_failure():
    runner = load_runner()
    assert runner.version_check({"signing": ["a"]}, {"signing": ["b"]}, {"signing": {"a", "b"}}) is False
    assert runner.version_check({"signing": ["a"]}, {}, {"signing": {"a"}}) is True
    assert runner.version_check({"signing": ["a"]}, {}, {}) is False      # thiếu mốc có vai trò đó


def test_firm_on_unverified_counts_only_cited_sources():
    runner = load_runner()
    from types import SimpleNamespace as NS
    items = [NS(n=1, document_status="verified"), NS(n=2, document_status="unversioned")]
    firm_ok = NS(certainty="firm", issues=[{"citations": [1]}])
    firm_bad = NS(certainty="firm", issues=[{"citations": [1, 2]}])
    assert runner.firm_on_unverified(firm_ok, items) is False      # nguồn chưa xác minh có trong ngữ cảnh nhưng không được dẫn
    assert runner.firm_on_unverified(firm_bad, items) is True
    assert runner.firm_on_unverified(NS(certainty="qualified", issues=[{"citations": [2]}]), items) is False
