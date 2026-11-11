"""Đồng bộ sang kho luật có phiên bản (spec 2026-11-11-new-store-sync-design.md)."""

from pathlib import Path

import yaml

LEGAL = Path(__file__).resolve().parents[3] / "data" / "team-4.2" / "legal"


def test_seeds_cover_legacy_map():
    seeds = {(x["type"], x["number"]) for x in yaml.safe_load((LEGAL / "seeds.yaml").read_text(encoding="utf-8"))["laws"]}
    legacy = yaml.safe_load((LEGAL / "legacy_map.yaml").read_text(encoding="utf-8"))["laws"]
    assert len(legacy) == 6
    assert all((x["type"], x["number"]) in seeds for x in legacy)


# --- Task 2: kho cũ chỉ còn tài liệu thường ------------------------------------------------------

from types import SimpleNamespace  # noqa: E402

from rag.schema import Chunk, Hit  # noqa: E402
from rag.temporal.status import DOCUMENT_LABEL, document_search, legacy_documents, load_legacy_map  # noqa: E402

LEGACY_MAP = load_legacy_map(LEGAL / "legacy_map.yaml")
CODE = Chunk("blds:1", "blds", "bo_luat_dan_su_2015.txt", 1, 1, "Điều 1", "Điều 1. Phạm vi điều chỉnh")
NOTE = Chunk("doc:1", "doc", "quy_trinh_noi_bo.pdf", 1, 1, "Mục 1", "Quy trình duyệt hợp đồng nội bộ")


def retriever(chunks):
    return SimpleNamespace(chunks={c.chunk_id: c for c in chunks},
                           retrieve=lambda q, k: SimpleNamespace(hits=[Hit(c.chunk_id, 1.0, i, "bm25")
                                                                      for i, c in enumerate(chunks, 1)][:k]))


def test_document_search_drops_the_six_codes():
    search = document_search(retriever([CODE, NOTE]), LEGACY_MAP)
    assert [c.chunk_id for c in search("hợp đồng", 4)] == ["doc:1"]


def test_document_search_on_codes_only_store_is_empty():
    assert document_search(retriever([CODE]), LEGACY_MAP)("x", 4) == []


def test_legacy_documents_lists_only_ordinary_documents():
    docs = [SimpleNamespace(source="bo_luat_hinh_su_2015.txt"), SimpleNamespace(source="quy_trinh_noi_bo.pdf")]
    assert [d.source for d in legacy_documents(docs, LEGACY_MAP)] == ["quy_trinh_noi_bo.pdf"]
    assert DOCUMENT_LABEL == "Tài liệu (không phải văn bản pháp luật)"


def test_contract_think_uses_document_source_not_raw_old_store(tmp_path, monkeypatch):
    import sys
    ui = Path(__file__).resolve().parents[1] / "ui"
    if str(ui) not in sys.path:
        sys.path.insert(0, str(ui))
    import contracts_api
    import rag.contracts.agent_view as av
    from datetime import datetime, timezone
    from rag.contracts.models import Contract
    from rag.contracts.parse import split_units

    c = Contract("c1", "hd.txt", False, datetime(2026, 11, 11, tzinfo=timezone.utc), "Điều 1. A", split_units("Điều 1. A"), 1)
    contracts_api.reset()
    contracts_api.CONFIG.root = tmp_path
    contracts_api.store().add(c, original=b"x", suffix=".txt")
    seen = {}
    monkeypatch.setattr(av, "run_contract_agent", lambda cc, b, cfg, rt, chunks, search, q, h, stream=False:
                        seen.update(chunks=chunks) or {"answer": "ok"})
    monkeypatch.setattr(contracts_api.CONFIG, "agent_baseline", lambda: SimpleNamespace(retriever=None))
    monkeypatch.setattr(contracts_api.CONFIG, "agent_config", None)
    monkeypatch.setattr(contracts_api.CONFIG, "document_source", lambda: ({"doc:1": NOTE}, lambda q, k: []))
    contracts_api.chat_think("c1", "Hỏi?", [])
    assert list(seen["chunks"]) == ["doc:1"]


# --- Task 3: danh sách văn bản pháp luật -------------------------------------------------------

import importlib.util  # noqa: E402
from datetime import date  # noqa: E402

import pytest  # noqa: E402

from rag.legal.snapshots import SnapshotManager  # noqa: E402
from rag.temporal.status import legal_overview  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def seeded_store(tmp_path_factory):
    spec = importlib.util.spec_from_file_location("seed", ROOT / "scripts" / "team-4.2" / "seed_legal_demo.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    d = tmp_path_factory.mktemp("legal")
    mod.seed(d, Path(__file__).parent / "fixtures" / "legal" / "realestate")
    return SnapshotManager(d).store()


def test_legal_overview_reports_status_today(seeded_store):
    rows = {r["document_key"]: r for r in legal_overview(seeded_store, date(2026, 11, 11))}
    old, new = rows["luat:65/2014/QH13"], rows["luat:27/2023/QH15"]
    assert new["status_today"] == "in_force" and new["title"].startswith("Luật Nhà ở")
    assert old["status_today"] == "repealed" and old["replaced_by"]["document_key"] == "luat:27/2023/QH15"
    assert rows["luat:43/2024/QH15"]["status_today"] in ("in_force", "amending")
    assert all(r["doc_type"] for r in rows.values())


def test_legal_overview_before_new_law_is_not_yet(seeded_store):
    rows = {r["document_key"]: r for r in legal_overview(seeded_store, date(2023, 1, 1))}
    assert rows["luat:27/2023/QH15"]["status_today"] == "not_yet"


def test_documents_panel_has_two_groups():
    page = (Path(__file__).resolve().parents[1] / "ui" / "index.html").read_text(encoding="utf-8")
    assert "Văn bản pháp luật" in page and "Tài liệu thường" in page and "legal_docs" in page


def test_api_info_returns_legal_docs_and_only_ordinary_documents(seeded_store, monkeypatch):
    import asyncio
    import json as _json
    import sys
    ui = Path(__file__).resolve().parents[1] / "ui"
    if str(ui) not in sys.path:
        sys.path.insert(0, str(ui))
    import legal_api
    saved = [(ns, dict(vars(ns))) for ns in (legal_api.CONFIG,)]
    spec = importlib.util.spec_from_file_location("sync_info_server", ui / "server.py")
    server = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(server)
    finally:
        for ns, values in saved:
            vars(ns).clear()
            vars(ns).update(values)
    docs = [SimpleNamespace(doc_id="a", source="bo_luat_dan_su_2015.txt", n_chunks=700),
            SimpleNamespace(doc_id="b", source="quy_trinh_noi_bo.pdf", n_chunks=5)]
    pipeline = SimpleNamespace(store=SimpleNamespace(docs=lambda: docs, __len__=lambda: 705))
    settings = SimpleNamespace(decomp_enabled=False, listwise_enabled=False, advanced="", llm_model="m", embed_model="e",
                               embed_dim=1, rerank_backend="none", listwise_model="m", condense_model="m",
                               context_min_p=0.5, top_k=5, ocr_engine="none", ocr_model="")
    monkeypatch.setattr(server, "get_pipeline", lambda: (pipeline, settings))
    monkeypatch.setattr(server, "_legal_store", lambda: seeded_store)
    resp = asyncio.run(server.handle_info(None))
    data = _json.loads(resp.body)
    assert [d["source"] for d in data["docs"]] == ["quy_trinh_noi_bo.pdf"]
    assert data["legal_total"] == len(data["legal_docs"]) > 0
    assert any(d["document_key"] == "luat:27/2023/QH15" and d["status_today"] == "in_force" for d in data["legal_docs"])
