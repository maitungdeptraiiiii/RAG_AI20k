"""Interface Evaluator công bố cho benchmark (checklist A3): chữ ký ổn định, dữ liệu stub đúng kiểu."""
from datetime import date

import pytest

from rag.bridge.engine import RuleResult
from rag.rules.evaluator import Diff, make_evaluator


def test_make_evaluator_returns_session_with_typed_results():
    s = make_evaluator(["labor"]).session(day=date(2025, 3, 1), facts={}, present=set(), evidence={})
    r = s.results()
    assert r and all(isinstance(x, RuleResult) for x in r)
    assert isinstance(s.update({}, present=set()), Diff)
    assert s.fork() is not s


def test_network_kind_not_available_yet():
    with pytest.raises(NotImplementedError):
        make_evaluator(["labor"], "network")
