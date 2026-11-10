import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from rag.index.embedder import HashEmbedder
from rag.legal.models import LegalDocument
from rag.legal.service import LegalService
from rag.legal.store import LegalStore, decode
from rag.temporal.index import VersionedIndex

FIX = Path(__file__).parent / "fixtures" / "legal" / "realestate"
NOW = datetime(2026, 11, 9, tzinfo=timezone.utc)
QUERY = "điều kiện làm chủ đầu tư dự án xây dựng nhà ở thương mại"


def realestate_service(tmp) -> LegalService:
    store = LegalStore(tmp / "catalog.sqlite")
    for row in json.loads((FIX / "manifest.json").read_text(encoding="utf-8")):
        row["raw_text_path"] = str(FIX / row["raw_text_path"])
        store.upsert_document(decode(LegalDocument, row))
    svc = LegalService(store, now=lambda: NOW)
    svc.build_all()
    return svc


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    svc = realestate_service(tmp_path_factory.mktemp("tindex"))
    index = VersionedIndex(svc.store, HashEmbedder(dim=64))
    index.build()
    return svc, index


def docs(results):
    return {c.document_key for c, _ in results}


def test_filter_before_rank_returns_version_valid_at_date(built):
    _, index = built
    early = index.search(QUERY, date(2023, 6, 15), date(2023, 6, 15), k=30)
    late = index.search(QUERY, date(2025, 6, 15), date(2025, 6, 15), k=30)
    assert "luat:65/2014/QH13" in docs(early) and "luat:27/2023/QH15" not in docs(early)
    assert "luat:27/2023/QH15" in docs(late) and "luat:65/2014/QH13" not in docs(late)
    for c, _ in early:
        assert c.valid_from <= date(2023, 6, 15) and (c.valid_to is None or c.valid_to > date(2023, 6, 15))


def test_year_range_returns_both_versions(built):
    _, index = built
    year = index.search(QUERY, date(2024, 1, 1), date(2024, 12, 31), k=60)
    assert {"luat:65/2014/QH13", "luat:27/2023/QH15"} <= docs(year)


def test_amendment_only_docs_not_indexed(built):
    _, index = built
    assert all(c.document_key not in ("luat:43/2024/QH15", "luat:03/2022/QH15") for c in index.chunks.values())


def test_versions_of_article(built):
    _, index = built
    chunk = next(c for c in index.chunks.values() if c.article_id == "luat:65/2014/QH13#d23")
    vs = index.versions_of(chunk.article_id, date(2015, 1, 1), date(2024, 12, 31))
    assert len({v.valid_from for v in vs}) >= 2           # khoản 1 Điều 23 đổi ngày 01/3/2022


def test_stale_after_new_build(built):
    svc, index = built
    assert not index.stale()
    svc.build_law("luat:65/2014/QH13")                   # cùng đầu vào: cùng build_id -> không cũ
    assert not index.stale()
    svc.store.set_review(svc.store.operations(target_key="luat:65/2014/QH13")[0].operation_id, "rejected", "T", "x", NOW)
    svc.build_law("luat:65/2014/QH13")
    assert index.stale()


def test_deterministic(built):
    _, index = built
    assert index.search(QUERY, date(2023, 6, 15), date(2023, 6, 15), k=10) == \
        index.search(QUERY, date(2023, 6, 15), date(2023, 6, 15), k=10)


def test_rebuild_keeps_old_state_visible_until_swap(built, monkeypatch):
    # review I3: trong lúc build lại, search đồng thời vẫn thấy chỉ mục cũ đầy đủ (đổi nguyên khối)
    import rag.temporal.index as mod
    _, index = built
    before = len(index.chunks)
    seen = []
    real = mod.export_chunks

    def spy(store, key):
        seen.append(len(index.chunks))
        return real(store, key)

    monkeypatch.setattr(mod, "export_chunks", spy)
    index.build()
    assert seen and all(n == before for n in seen)
