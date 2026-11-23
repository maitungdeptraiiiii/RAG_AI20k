"""K3: chấm 3 engine theo gold, bảng chọn gói, nhận diện loại có đệm (kế hoạch 2026-11-23-khanh-ingest-bench-eval, Task 3)."""
import json
from functools import lru_cache

from rag.contracts.llm_json import ContractAIError
from rag.rules.bench.cases import load_cases
from rag.rules.bench.evalrun import ENGINES, cached_classifier, pack_choice, render_summary, score


@lru_cache(maxsize=None)
def _cases():
    return tuple(load_cases()[0])


def test_new_engines_match_all_gold():
    for eng in ("reference", "network"):
        s = score(list(_cases()), eng)
        assert s.misses == [], [(m.case_id, m.rule, m.want, m.got) for m in s.misses[:5]]


def test_legacy_counts_cross_object_rules_as_missing_not_crash():
    s = score([c for c in _cases() if c.suite == "b1"], "legacy")
    assert any(m.got == "MISSING" for m in s.misses) and all(m.explain_md is None for m in s.misses)


def test_confusion_totals_equal_number_of_labels():
    s = score(list(_cases()), "reference")
    assert sum(s.confusion.values()) == sum(len(c.expected) for c in _cases())
    assert sum(sum(c.values()) for c in s.by_pack.values()) == sum(len(c.expected) for c in _cases())


def test_miss_carries_path_and_explain(monkeypatch):
    import rag.rules.bench.evalrun as E
    c = next(c for c in _cases() if c.suite == "loan")
    real = E.run_case
    monkeypatch.setattr(E, "run_case", lambda case, eng: {k: _flip(r) for k, r in real(case, eng).items()})
    m = score([c], "network").misses[0]
    assert m.path == "tests/fixtures/rete/loan" and m.explain_md


def _flip(r):
    import dataclasses
    return dataclasses.replace(r, status="FAIL" if r.status != "FAIL" else "PASS")


def test_pack_choice_flags_wrong_domain():
    c = next(c for c in _cases() if c.suite == "lease")
    row = pack_choice([c], classify=lambda _c: "labor_contract")[0]
    assert row.wrong_domain is True and row.packs_run == ("labor",)
    assert pack_choice([c], classify=lambda _c: "lease_contract")[0].wrong_domain is False
    assert pack_choice([c])[0].wrong_domain is None


def test_pack_choice_one_row_per_document():
    rows = pack_choice([c for c in _cases() if c.suite == "a1"])
    assert len(rows) == 1


def test_summary_lists_missing_gold_and_every_engine():
    md = render_summary([score([], e) for e in ENGINES], [], ["x_dir"], classified=False)
    assert "x_dir" in md and all(e in md for e in ENGINES) and "classify: chưa chạy" in md


class CountingLLM:
    def __init__(self, reply):
        self.reply, self.calls = reply, 0

    def complete(self, system, user):
        self.calls += 1
        if isinstance(self.reply, Exception):
            raise self.reply
        payload = json.loads(user)
        u = payload["units"][0]
        return json.dumps({"kind": self.reply, "confidence": 0.9, "unit": u["uid"], "quote": u["text"][:20]},
                          ensure_ascii=False)


def test_classifier_calls_llm_once_per_document_and_caches(tmp_path):
    a1 = [c for c in _cases() if c.suite == "a1"]
    assert len(a1) > 1
    llm = CountingLLM("labor_contract")
    cls = cached_classifier(llm, tmp_path / "cache.json", "m1")
    assert {cls(c) for c in a1} == {"labor_contract"} and llm.calls == 1
    again = CountingLLM("labor_contract")
    assert cached_classifier(again, tmp_path / "cache.json", "m1")(a1[0]) == "labor_contract" and again.calls == 0


def test_classifier_llm_error_gives_unknown_and_wrong_domain(tmp_path):
    c = next(c for c in _cases() if c.suite == "lease")
    cls = cached_classifier(CountingLLM(ContractAIError("x")), tmp_path / "cache.json", "m1")
    assert cls(c) == "unknown" and pack_choice([c], classify=cls)[0].wrong_domain is True
