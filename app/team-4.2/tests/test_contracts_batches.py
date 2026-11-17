import random
import time

import pytest

from rag.contracts.batches import batch_workers, run_batches
from rag.contracts.llm_json import ContractAIError


def _sleepy(b):
    time.sleep(random.uniform(0, 0.05))
    return b * 10


def test_results_keep_batch_order():
    batches = list(range(6))
    run = run_batches(batches, _sleepy, workers=4)
    assert [b for b, _ in run.results] == batches
    assert [r for _, r in run.results] == [b * 10 for b in batches]


def test_failed_batch_recorded_others_kept():
    def fn(b):
        if b == 2:
            raise ContractAIError("hỏng")
        return b
    batches = list(range(6))
    run = run_batches(batches, fn, workers=4)
    assert run.failed == [2]
    assert [b for b, _ in run.results] == [0, 1, 3, 4, 5]


def test_on_done_counts_to_total():
    calls = []
    run_batches(list(range(6)), _sleepy, workers=3, on_done=lambda d, t: calls.append((d, t)))
    assert sorted(d for d, _ in calls) == [1, 2, 3, 4, 5, 6]
    assert all(t == 6 for _, t in calls)


def test_parallel_is_faster():
    t0 = time.monotonic()
    run_batches(list(range(4)), lambda b: time.sleep(0.2), workers=4)
    assert time.monotonic() - t0 < 0.5


@pytest.mark.parametrize("raw, expected", [("abc", 1), ("0", 1), ("-3", 1), ("2", 2), (None, 4)])
def test_batch_workers_env(monkeypatch, raw, expected):
    if raw is None:
        monkeypatch.delenv("CONTRACT_BATCH_WORKERS", raising=False)
    else:
        monkeypatch.setenv("CONTRACT_BATCH_WORKERS", raw)
    assert batch_workers() == expected
