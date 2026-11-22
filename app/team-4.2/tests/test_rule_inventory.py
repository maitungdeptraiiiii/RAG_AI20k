"""Bản liệt kê rule (phần Tuấn, tuan.md §2): trích dẫn phải có NGUYÊN VĂN trong kho luật, đủ trường, đủ ví dụ."""
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "docs" / "rule_inventory"
from legal_corpus import ROOTS, law_text  # noqa: E402
FILES = ["labor_w04.yaml", "civil_general.yaml", "civil_loan.yaml", "civil_lease.yaml"]
TYPES = {"threshold", "required", "prohibited", "default", "derived", "exception"}
DEROGATIONS = {"mandatory", "floor", "ceiling", "default"}
SILENCE = {"missing_content", "hidden_right", "default_applies", "none"}
REQUIRED = {"id", "source", "type", "kind", "derogation", "applies_when", "facts_needed", "exceptions", "conclusion",
            "on_silence", "derived_from", "examples", "open_questions"}


def entries():
    for name in FILES:
        for e in yaml.safe_load((INVENTORY / name).read_text(encoding="utf-8")):
            yield name, e


def _norm(s: str) -> str:
    return " ".join(s.split())


@pytest.mark.skipif(not ROOTS, reason="không có kho luật cục bộ")
@pytest.mark.parametrize("name,entry", list(entries()), ids=lambda x: x if isinstance(x, str) else x.get("id"))
def test_every_quote_is_verbatim_in_the_corpus(name, entry):
    quotes = [(entry["source"]["pid"], entry["source"]["quote"])]
    quotes += [(x["pid"], x["quote"]) for x in entry["exceptions"]]
    quotes += [(x["pid"], x["quote"]) for x in entry.get("periods") or []]   # cùng quy định ở các bản luật trước/sau
    for pid, quote in quotes:
        text = law_text(pid)
        if text is None:
            assert entry["open_questions"], f"{entry['id']}: {pid} không có trong kho mà không ghi câu hỏi mở"
            continue
        assert _norm(quote) in _norm(text), f"{entry['id']}: trích dẫn không khớp nguyên văn {pid}: {quote[:60]}"


@pytest.mark.parametrize("name,entry", list(entries()), ids=lambda x: x if isinstance(x, str) else x.get("id"))
def test_entry_shape(name, entry):
    assert REQUIRED <= set(entry), REQUIRED - set(entry)
    assert entry["type"] in TYPES and entry["derogation"] in DEROGATIONS and entry["on_silence"] in SILENCE
    assert entry["id"].split(".")[0] in {"labor", "civil", "civil_loan", "civil_lease"}
    assert "#d" in entry["source"]["pid"] and entry["source"]["quote"].strip()
    for x in entry["exceptions"]:
        assert {"pid", "quote", "condition"} <= set(x)
    for f in entry["facts_needed"]:
        assert {"name", "kind", "from"} <= set(f) and f["from"] in {"contract", "user", "dossier", "derived"}
    if entry["type"] != "derived":
        expected = {ex["expected"] for ex in entry["examples"]}
        assert {"PASS", "FAIL", "UNKNOWN"} <= expected, (entry["id"], expected)
    for ex in entry["examples"]:
        if ex["expected"] == "UNKNOWN":
            assert ex.get("why"), entry["id"]


def test_ids_unique_and_derived_from_resolves():
    all_entries = [e for _, e in entries()]
    ids = [e["id"] for e in all_entries]
    assert len(ids) == len(set(ids))
    for e in all_entries:
        for d in e["derived_from"]:
            assert d in ids, (e["id"], d)


def test_periods_are_ordered_and_cover_the_source():
    """Quy định có nhiều bản luật: mỗi kỳ có ngày bắt đầu, tăng dần, và kỳ cuối là `source`."""
    for _, e in entries():
        periods = e.get("periods")
        if not periods:
            continue
        starts = [str(p["valid_from"]) for p in periods]
        assert starts == sorted(starts) and len(set(starts)) == len(starts), e["id"]
        assert periods[-1]["pid"] == e["source"]["pid"], e["id"]
