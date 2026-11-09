"""ui/server.py — xem tài liệu: tên file tiếng Việt (header Latin-1) và chặn path traversal."""

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import quote

import pytest
from starlette.testclient import TestClient

UI = Path(__file__).resolve().parents[1] / "ui" / "server.py"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("team42_server", UI)
    server = importlib.util.module_from_spec(spec)
    sys.modules["team42_server"] = server
    spec.loader.exec_module(server)

    data = tmp_path / "data"
    (data / "raw").mkdir(parents=True)
    (data / "cache" / "ocr").mkdir(parents=True)
    (data / "raw" / "Luật tiếp cận thông tin_0001.pdf").write_bytes(b"%PDF-1.4 fake")
    (data / "raw" / "luat.txt").write_text("Điều 1. Nội dung", encoding="utf-8")
    (data / "cache" / "ocr" / "abc.txt").write_text("text OCR gốc chưa mask: 0912345678", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("OPENROUTER_API_KEY=sk-secret", encoding="utf-8")

    import fitz

    pdf = fitz.open()
    pdf.new_page().insert_text((72, 72), "scan")
    pdf.save(data / "raw" / "scan.pdf")
    (data / "extracted").mkdir()
    (data / "extracted" / "d1.json").write_text(json.dumps({"doc_id": "d1", "source": "scan.pdf", "pages": [
        {"index": 0, "page": 1, "kind": "ocr", "text": "Điều 1. <b>Phạm vi</b> [PHONE_1]"}]}), encoding="utf-8")
    (data / "ingest_reports").mkdir()
    (data / "ingest_reports" / "d1.json").write_text(json.dumps({"doc_id": "d1", "source": "scan.pdf", "pages_detail": [
        {"index": 0, "kind": "ocr", "confidence": 43.4, "confidence_status": "low", "ocr_reason": "empty",
         "issues": [{"code": "ocr.low_confidence", "detail": "Độ tin cậy OCR thấp"}]}]}), encoding="utf-8")
    old_chunks = [SimpleNamespace(source="cu.txt", page_start=None, text="Điều 9. Đoạn cũ")]

    settings = SimpleNamespace(data_dir=data)
    pipeline = SimpleNamespace(store=SimpleNamespace(
        all=lambda: [], by_doc=lambda doc_id: old_chunks if doc_id == "old" else []))
    monkeypatch.setattr(server, "get_pipeline", lambda: (pipeline, settings))
    monkeypatch.chdir(tmp_path)                     # Path("data/team-4.2") không tồn tại trong tmp
    return TestClient(server.app)


def test_pdf_with_vietnamese_name_is_served(client):
    r = client.get("/doc/" + quote("Luật tiếp cận thông tin_0001.pdf"))
    assert r.status_code == 200 and r.content == b"%PDF-1.4 fake"
    cd = r.headers["content-disposition"]
    assert cd.startswith('inline; filename="Luat tiep can thong tin_0001.pdf"')
    assert "filename*=UTF-8''Lu%E1%BA%ADt%20ti%E1%BA%BFp" in cd


@pytest.mark.parametrize("name", [
    "../secret.txt", "..%2Fsecret.txt", "..%5Csecret.txt", "raw/../../secret.txt", "*.txt", "abc.txt",
])
def test_traversal_glob_and_private_dirs_are_blocked(client, name):
    for route in ("/doc/", "/api/doc_content/"):
        r = client.get(route + name)
        assert "sk-secret" not in r.text and "0912345678" not in r.text, (route, name)


def test_normal_text_doc_still_works(client):
    r = client.get("/api/doc_content/luat.txt")
    assert r.status_code == 200 and r.json()["content"] == "Điều 1. Nội dung"


def test_extracted_view_shows_full_text_with_page_image_and_review_badges(client):
    r = client.get("/extracted/d1")
    assert r.status_code == 200
    assert "Điều 1. &lt;b&gt;Phạm vi&lt;/b&gt; [PHONE_1]" in r.text          # escape HTML, giữ placeholder PII
    assert "Tin cậy 43.4" in r.text and "Độ tin cậy OCR thấp" in r.text and 'class="card review"' in r.text
    assert "/api/page_image/d1/1" in r.text
    img = client.get("/api/page_image/d1/1")
    assert img.status_code == 200 and img.headers["content-type"] == "image/png" and img.content[1:4] == b"PNG"
    assert client.get("/api/page_image/d1/9").status_code == 404


def test_extracted_view_falls_back_to_chunks_for_old_documents(client):
    r = client.get("/extracted/old")
    assert r.status_code == 200 and "Điều 9. Đoạn cũ" in r.text and "dựng lại từ" in r.text
    assert client.get("/extracted/khong-co").status_code == 404
