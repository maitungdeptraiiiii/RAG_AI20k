"""Warehouse migration preserves sources and both modes share catalog evidence."""
import asyncio
from dataclasses import asdict
from datetime import date
import json
from pathlib import Path
import sqlite3

import httpx
import pytest

from rag.agent import AgentPipeline
from rag.agent.temporal import TemporalScopeFactory
from rag.config import Settings
from rag.legal.library import library_content, library_documents
from rag.legal.migrate import migrate
from rag.legal.service import LegalService
from rag.legal.store import LegalStore
from rag.schema import Chunk
from rag.temporal.index import VersionedIndex
from rag.temporal.qa import TemporalQA
from tests.test_agent import build_agent
from tests.test_dated_agent_e2e import DatedModel
from tests.test_temporal_qa import FakeLLM, FIRM
from tests.test_think_routing import server
from tests.test_temporal_qa import corpus


def source_store(tmp):
    (tmp / "processed").mkdir()
    (tmp / "raw").mkdir()
    rows = [Chunk("civil:0000", "civil", "civil.txt", 1, 1, "Điều 1", "Điều 1. Điều kiện\nChủ thể phải đáp ứng điều kiện dân sự."),
            Chunk("notes:0000", "notes", "notes.md", 1, 1, "Notes", "Tài liệu phụ trợ được giữ nguyên.")]
    (tmp / "processed/chunks.jsonl").write_text("\n".join(json.dumps(asdict(c), ensure_ascii=False) for c in rows), encoding="utf-8")
    for row in rows:
        (tmp / "raw" / row.source).write_text(row.text, encoding="utf-8")
    mapping = tmp / "map.yaml"
    mapping.write_text('laws:\n  - {source: civil.txt, type: "Bộ luật", number: "91/2015/QH13", issuer: "Quốc hội"}\n', encoding="utf-8")
    return mapping


def test_atomic_idempotent_migration_backup_and_unknown_applicability(tmp_path):
    mapping = source_store(tmp_path)
    before = (tmp_path / "processed/chunks.jsonl").read_bytes()
    store = LegalStore(tmp_path / "legal/catalog.sqlite")
    dry = migrate(tmp_path, mapping)
    assert dry["documents"] == 2 and store.documents() == []
    applied = migrate(tmp_path, mapping, apply=True)
    assert applied["changed_documents"] == 2
    assert Path(applied["backup_dir"], "catalog.sqlite").exists()
    with sqlite3.connect(Path(applied["backup_dir"], "catalog.sqlite")) as old:
        assert old.execute("SELECT count(*) FROM documents").fetchone()[0] == 0
    assert (tmp_path / "processed/chunks.jsonl").read_bytes() == before
    assert all(d.vbpl_effective_from is None and d.eff_status == "unverified_import" for d in store.documents())
    assert migrate(tmp_path, mapping, apply=True)["changed_documents"] == 0
    assert len(store.documents()) == 2
    assert all(row["applicability"] == "unverified" for row in store.reference_snapshots().values())
    with pytest.raises(ValueError, match="reviewed applicability"):
        LegalService(store).build_law("bo-luat:91/2015/QH13")


def test_reference_source_is_shared_and_can_never_be_promoted_to_firm(tmp_path):
    mapping = source_store(tmp_path)
    migrate(tmp_path, mapping, apply=True)
    service = LegalService(LegalStore(tmp_path / "legal/catalog.sqlite"))
    index = VersionedIndex(service.store)
    index.build()
    assert len(index.chunks) == 2
    assert all(c.valid_from is None and c.verification_status == "needs_review" for c in index.chunks.values())
    model = DatedModel()
    base, _ = build_agent(model)
    qa = TemporalQA(service, index, model)
    agent = AgentPipeline(base.baseline, scope_factory=TemporalScopeFactory(base.baseline, qa, None, base.config))
    trace = agent.ask_debug("Điều kiện dân sự của chủ thể?")
    assert trace.status == "partial", trace.retrieval.errors
    assert trace.temporal["certainty"] == "qualified"
    assert trace.context.blocks and trace.agent["verified"]
    assert trace.to_response("q")["sources"][0]["store"] == "reference"
    normal = TemporalQA(service, index, FakeLLM(FIRM)).ask("Điều kiện dân sự của chủ thể?")
    assert normal.answer.certainty != "firm"
    assert {i.document_key for i in normal.items} >= {trace.to_response("q")["sources"][0]["source"]}
    assert all(i.store == "reference" and i.valid_from is None for i in normal.items)


def test_ui_reads_catalog_without_initializing_warehouse_one(server, monkeypatch, tmp_path):
    mapping = source_store(tmp_path)
    migrate(tmp_path, mapping, apply=True)
    service = LegalService(LegalStore(tmp_path / "legal/catalog.sqlite"))
    monkeypatch.setattr(server, "get_legal_service", lambda: service)
    monkeypatch.setattr(server.Settings, "load", lambda: Settings(data_dir=tmp_path))
    monkeypatch.setattr(server, "get_pipeline", lambda: pytest.fail("Catalog UI must not open warehouse 1"))

    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url="http://test") as client:
            info = await client.get("/api/info")
            assert info.status_code == 200
            data = info.json()
            assert data["warehouse"] == "catalog" and len(data["docs"]) == 2
            assert data["total_chunks"] == 2
            doc = data["docs"][0]
            content = await client.get("/api/doc_content/" + doc["source"])
            assert content.status_code == 200 and content.json()["store"] == "catalog"
            assert content.json()["content"]
            assert (await client.get("/doc/" + doc["source"])).status_code == 200
            assert (await client.get("/api/doc_content/not-in-catalog.txt")).status_code == 404
    asyncio.run(run())


def test_migration_with_missing_original_preserves_chunks_as_explicit_reconstruction(tmp_path):
    mapping = source_store(tmp_path)
    (tmp_path / "raw/notes.md").unlink()
    migrate(tmp_path, mapping, apply=True)
    service = LegalService(LegalStore(tmp_path / "legal/catalog.sqlite"))
    row = service.store.reference_snapshots()["reference:notes"]
    assert row["source_reconstructed"]
    assert "giữ nguyên" in library_content(service, "notes.md")["content"]


def test_temporal_review_repairs_format_once_without_weakening_source_certainty(tmp_path):
    from rag.agent.temporal import TEMPORAL_REVIEW
    class Model(DatedModel):
        review_calls = 0
        def complete(self, system, user):
            if system == TEMPORAL_REVIEW:
                self.review_calls += 1
                if self.review_calls == 1:
                    return '{"issues":[],"transition_assessments":[],"follow_up_questions":[]}'
            return super().complete(system, user)
    mapping = source_store(tmp_path)
    migrate(tmp_path, mapping, apply=True)
    service = LegalService(LegalStore(tmp_path / "legal/catalog.sqlite"))
    index = VersionedIndex(service.store)
    index.build()
    model = Model()
    base, _ = build_agent(model)
    qa = TemporalQA(service, index, model)
    trace = AgentPipeline(base.baseline, scope_factory=TemporalScopeFactory(base.baseline, qa, None, base.config)).ask_debug(
        "Điều kiện dân sự của chủ thể?")
    assert model.review_calls == 2
    assert trace.status == "partial" and trace.temporal["certainty"] == "qualified"
    assert trace.retrieval.errors["temporal_review_schema_repaired"] == "recovered"


def test_library_counts_match_searchable_catalog_not_amendment_source_fragments(corpus):
    service, index = corpus
    docs = library_documents(service)
    assert sum(d["n_chunks"] for d in docs) == len(index.chunks)
    assert any(not d["searchable"] for d in docs)


def test_binary_original_is_archived_while_catalog_serves_readable_extracted_text(tmp_path):
    source_store(tmp_path)
    original = b"%PDF-1.7\x00\xffbinary"
    (tmp_path / "raw/binary.pdf").write_bytes(original)
    records = [asdict(Chunk("pdf:0000", "pdf", "binary.pdf", 1, 1, "Điều 1", "Nội dung đã trích xuất."))]
    migrate(tmp_path, tmp_path / "missing.yaml", apply=True, records=records)
    service = LegalService(LegalStore(tmp_path / "legal/catalog.sqlite"))
    snapshot = service.store.reference_snapshots()["reference:pdf"]
    assert Path(snapshot["original_archive"]).read_bytes() == original
    assert library_content(service, "reference:pdf")["content"] == "Nội dung đã trích xuất."


def test_both_modes_fail_closed_if_catalog_is_unavailable(server, monkeypatch):
    from tests.test_think_routing import request_for
    monkeypatch.setattr(server, "get_temporal_qa", lambda: None)
    monkeypatch.setattr(server, "get_pipeline", lambda: (object(), Settings()))
    monkeypatch.setattr(server, "_sync_ask", lambda *a: pytest.fail("No warehouse-1 fallback"))
    async def run():
        normal = await server.handle_chat(request_for({"query": "Câu hỏi"}))
        think = await server.handle_chat(request_for({"query": "Câu hỏi", "think": True}))
        assert normal.status_code == think.status_code == 503
    asyncio.run(run())
