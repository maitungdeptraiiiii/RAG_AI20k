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
