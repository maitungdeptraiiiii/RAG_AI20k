import importlib.util
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from rag.contracts.evidence import find_evidence, law_changes
from rag.legal.snapshots import SnapshotManager
from rag.schema import Chunk
from rag.temporal.index import VersionedIndex

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = Path(__file__).parent / "fixtures" / "legal" / "realestate"
SIGNED, TODAY = date(2023, 3, 15), date(2026, 11, 11)


@pytest.fixture(scope="module")
def runtime(tmp_path_factory):
    spec = importlib.util.spec_from_file_location("seed", ROOT / "scripts" / "team-4.2" / "seed_legal_demo.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    legal_dir = tmp_path_factory.mktemp("legal")
    sid = mod.seed(legal_dir, FIXTURES)
    service = SnapshotManager(legal_dir).service(sid)
    index = VersionedIndex(service.store, snapshot_id=sid)
    index.build()
    return SimpleNamespace(snapshot_id=sid, service=service, index=index)


LEGACY = Chunk("bo_luat_dan_su:1", "blds", "bo_luat_dan_su_2015.txt", 1, 1, "Điều 418. Thỏa thuận phạt vi phạm",
               "Điều 418. Thỏa thuận phạt vi phạm\nPhạt vi phạm là sự thỏa thuận giữa các bên trong hợp đồng.")


def legacy_search(query, k):
    return [LEGACY]


def test_versioned_evidence_is_valid_at_signing_date(runtime):
    ev = find_evidence(runtime, legacy_search, "đơn phương chấm dứt hợp đồng thuê nhà ở", SIGNED, k=4)
    versioned = [e for e in ev if e.store == "versioned"]
    assert versioned and all(e.valid_from <= SIGNED and (e.valid_to is None or e.valid_to > SIGNED) for e in versioned)
    assert any(e.document_key == "luat:65/2014/QH13" for e in versioned)
    assert all("Luật" in e.source_title for e in versioned)
    legacy = [e for e in ev if e.store == "legacy"]
    assert legacy and legacy[0].valid_from is None and legacy[0].status == "unversioned"
    assert len({e.eid for e in ev}) == len(ev)


def test_no_runtime_returns_only_legacy():
    ev = find_evidence(None, legacy_search, "phạt vi phạm", SIGNED)
    assert [e.store for e in ev] == ["legacy"]


def test_law_changes_reports_repeal_and_replacement(runtime):
    ev = [e for e in find_evidence(runtime, lambda q, k: [], "đơn phương chấm dứt hợp đồng thuê nhà ở", SIGNED, k=4)
          if e.document_key == "luat:65/2014/QH13"]
    changes = law_changes(runtime, ev, TODAY)
    row = changes[0]
    assert row["status"] == "repealed"
    assert row["replaced_by"]["document_key"] == "luat:27/2023/QH15"
    assert row["replaced_from"] == "2024-08-01"
    assert row["transition_articles"]                  # Luật Nhà ở 2023 có Điều chuyển tiếp


def test_law_changes_marks_legacy_untracked():
    ev = find_evidence(None, legacy_search, "phạt vi phạm", SIGNED)
    assert law_changes(None, ev, TODAY)[0]["status"] == "untracked"


def test_evidence_section_is_the_article_and_duplicates_merge(runtime):
    ev = find_evidence(runtime, legacy_search, "đơn phương chấm dứt hợp đồng thuê nhà ở", SIGNED, k=6)
    versioned = [e for e in ev if e.store == "versioned"]
    assert versioned and all(e.section.startswith("Điều ") for e in versioned)
    keys = [(e.document_key, e.section) for e in versioned]
    assert len(keys) == len(set(keys))


def test_law_change_rows_are_unique_per_article(runtime):
    ev = find_evidence(runtime, lambda q, k: [], "đơn phương chấm dứt hợp đồng thuê nhà ở", SIGNED, k=6)
    rows = law_changes(runtime, ev + ev, TODAY)
    assert len(rows) == len({(r["source_title"], r["section"]) for r in rows})
