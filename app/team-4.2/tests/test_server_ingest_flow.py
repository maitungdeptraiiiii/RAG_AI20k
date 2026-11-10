"""ui/server.py — upload chỉ trích xuất/OCR; embedding, tải bản OCR, bỏ là các lựa chọn riêng."""

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from starlette.testclient import TestClient

UI = Path(__file__).resolve().parents[1] / "ui" / "server.py"
LAW = "Điều 1. Phạm vi điều chỉnh\nLuật này quy định về tiếp cận thông tin. Liên hệ 0912 345 678.\n" \
      "Điều 2. Đối tượng áp dụng\nCơ quan nhà nước và công dân."


class _NoLLM:
    model_id = "none"

    def complete(self, system, user):
        raise AssertionError("upload / embedding không gọi LLM")


@pytest.fixture()
def env(tmp_path, monkeypatch):
    from rag.index.bm25_index import BM25Index
    from rag.index.embedder import HashEmbedder
    from rag.index.store import ChunkStore
    from rag.index.vector_index import VectorIndex
    from rag.pipeline import RAGPipeline
    from rag.retrieve.hybrid import HybridRetriever

    spec = importlib.util.spec_from_file_location("team42_server_flow", UI)
    server = importlib.util.module_from_spec(spec)
    sys.modules["team42_server_flow"] = server
    spec.loader.exec_module(server)

    data = tmp_path / "data"
    pipeline = RAGPipeline(ChunkStore(), HybridRetriever(BM25Index(), VectorIndex(HashEmbedder(dim=64))), _NoLLM(),
                           extracted_dir=data / "extracted")
    settings = SimpleNamespace(data_dir=data)
    monkeypatch.setattr(server, "get_pipeline", lambda: (pipeline, settings))
    monkeypatch.chdir(tmp_path)
    return SimpleNamespace(client=TestClient(server.app), pipeline=pipeline, data=data, server=server)


def _upload(env, name="luat.txt", text=LAW, mode="prepare"):
    form = {"mode": mode} if mode else {}
    r = env.client.post("/api/ingest", data=form, files={"files": (name, text.encode("utf-8"), "text/plain")})
    assert r.status_code == 200
    (row,) = r.json()["results"]
    assert "error" not in row, row
    return row


def test_upload_only_extracts_then_embedding_on_demand(env):
    row = _upload(env)
    assert row["indexed"] is False and len(env.pipeline.store) == 0          # chưa embedding / chưa vào kho
    assert (env.data / "extracted" / f"{row['doc_id']}.json").is_file()
    (listed,) = env.client.get("/api/ingest_reports").json()["reports"]
    assert listed["indexed"] is False

    md = env.client.get(f"/api/extracted/{row['doc_id']}/download?format=md")
    assert md.status_code == 200 and md.headers["content-disposition"].startswith('attachment; filename="luat_ocr.md"')
    assert "## Nội dung" in md.text and "Điều 1. Phạm vi điều chỉnh" in md.text
    assert "0912 345 678" not in md.text and "[PHONE_1]" in md.text           # bản tải về đã che PII
    assert env.client.get(f"/api/extracted/{row['doc_id']}/download?format=txt").text.startswith("luat.txt")

    done = env.client.post(f"/api/index/{row['doc_id']}").json()
    assert done["indexed"] is True and done["n_chunks"] >= 1 and done["indexed_at"]
    assert len(env.pipeline.store.by_doc(row["doc_id"])) == done["n_chunks"]
    assert env.client.get(f"/api/ingest_reports/{row['doc_id']}").json()["indexed"] is True
    again = env.client.post(f"/api/index/{row['doc_id']}").json()             # bấm lại: không index 2 lần
    assert again["indexed"] is True and len(env.pipeline.store) == done["n_chunks"]


def test_embedding_after_server_restart_reprepares_from_uploaded_file(env):
    row = _upload(env)
    env.server._PREPARED.clear()                                                # mất bản trong RAM
    done = env.client.post(f"/api/index/{row['doc_id']}")
    assert done.status_code == 200 and done.json()["indexed"] is True and len(env.pipeline.store) >= 1


def test_discard_removes_upload_report_and_extracted_without_touching_index(env):
    kept = _upload(env, mode=None)                                              # trang chat: nạp thẳng như cũ
    assert kept["indexed"] is True
    n = len(env.pipeline.store)
    row = _upload(env, name="nhap.txt", text=LAW.replace("Điều 2", "Điều 3"))
    r = env.client.post(f"/api/discard/{row['doc_id']}")
    assert r.status_code == 200
    assert not (env.data / "raw" / "nhap.txt").exists()
    assert not (env.data / "extracted" / f"{row['doc_id']}.json").exists()
    assert env.client.get(f"/api/ingest_reports/{row['doc_id']}").status_code == 404
    assert len(env.pipeline.store) == n
    assert env.client.post(f"/api/discard/{kept['doc_id']}").status_code == 409  # đã vào kho: không bỏ ở đây
    assert (env.data / "raw" / "luat.txt").exists()
