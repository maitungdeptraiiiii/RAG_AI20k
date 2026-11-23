"""D34: nhãn hiển thị khai trong pack.yaml (kế hoạch 2026-11-23-w04-remaining, Task 3)."""
import json
from pathlib import Path

import pytest
import yaml

from rag.bridge.catalog import load_catalog
from rag.bridge.view import result_views
from rag.rules.loader import CatalogError, load_pack, load_packs

FROZEN = json.loads((Path(__file__).parent / "fixtures" / "labels_labor_before_d34.json").read_text(encoding="utf-8"))
PACKS = ["civil_loan", "civil_lease", "consumer", "commercial", "civil_general"]


def test_labor_labels_unchanged():
    cat = load_catalog()
    assert {k: cat.verdict_label(k) for k in FROZEN["verdicts"]} == FROZEN["verdicts"]
    assert {k: cat.fact_label(k) for k in FROZEN["facts"]} == FROZEN["facts"]


def test_unlabeled_names_fall_back_to_neutral():
    cat = load_packs(["civil_lease"])
    assert cat.fact_label("khong_co_nhan") == "khong_co_nhan"
    assert cat.verdict_label("khong_co_nhan") == "khong_co_nhan"
    assert cat.verdict_label("violation") == FROZEN["verdicts"]["violation"]       # finding lõi dùng chung


@pytest.mark.parametrize("pack", PACKS)
def test_pack_labels_have_no_employee_wording(pack):
    cat = load_packs([pack])
    texts = [cat.verdict_label(f) for f in ("ok", "violation", "needs_facts", "conflict", "missing_content")]
    texts += [cat.fact_label(n) for n in (*cat.context.document_facts, *cat.context.input_units)]
    assert not [t for t in texts if "lao động" in t.lower()], pack


def test_lease_view_has_no_employee_wording():
    cat = load_packs(["civil_lease"])
    concept = next(iter(cat.concepts.values()))
    results = [{"concept_id": concept.id, "finding": f, "missing_facts": ["rent_vnd", "lease_term_months"],
                "law_values": {}, "evidence": []} for f in ("ok", "violation", "needs_facts", "missing_content", "conflict")]
    contract = type("C", (), {"units": []})()
    views = result_views(results, cat, contract, {})
    blob = json.dumps(views, ensure_ascii=False).lower()
    assert "lao động" not in blob


def test_every_labor_only_finding_label_comes_from_the_pack():
    assert load_packs(["labor"]).verdict_label("hidden_right") == FROZEN["verdicts"]["hidden_right"]
    assert "hidden_right" not in load_packs(["civil_lease"]).context.finding_labels


def _pack_dir(tmp_path, name, labels):
    src = Path(__file__).resolve().parents[1] / "src" / "rag" / "rules" / "packs" / "civil_general"
    d = tmp_path / name
    d.mkdir()
    for f in src.iterdir():
        if f.is_file():
            (d / f.name).write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
    data = yaml.safe_load((d / "pack.yaml").read_text(encoding="utf-8"))
    data["id"] = name
    data["labels"] = labels
    (d / "pack.yaml").write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return d


def test_conflicting_labels_across_packs_fail_load(tmp_path):
    base_a = _pack_dir(tmp_path, "pa", {"facts": {"x": "Nhãn A"}})
    _pack_dir(tmp_path, "pb", {"facts": {"x": "Nhãn B"}})
    assert base_a.exists()
    with pytest.raises(CatalogError, match="labels"):
        load_packs(["pa", "pb"], root=tmp_path)


def test_label_for_unknown_finding_is_a_load_error(tmp_path):
    _pack_dir(tmp_path, "pc", {"findings": {"khong_ton_tai": "x"}})
    with pytest.raises(CatalogError, match="khong_ton_tai"):
        load_pack("pc", root=tmp_path)


def test_view_uses_the_catalog_labels():
    cat = load_packs(["civil_lease"])
    concept = next(iter(cat.concepts.values()))
    results = [{"concept_id": concept.id, "finding": "needs_facts", "missing_facts": ["rent_vnd"], "law_values": {}, "evidence": []}]
    v = result_views(results, cat, type("C", (), {"units": []})(), {})[0]["view"]
    assert v["missing"] == ["Giá thuê"] and v["verdict"] == cat.verdict_label("needs_facts")


def test_view_no_longer_hardcodes_labor_wording():
    import rag.bridge.view as view
    assert not hasattr(view, "FACT_LABELS") and not hasattr(view, "VERDICTS")
