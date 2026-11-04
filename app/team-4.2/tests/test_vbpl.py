"""Crawler vbpl — dùng session giả, không gọi mạng."""

import json
from datetime import datetime, timezone

from rag.ingest.chunker import chunk_document
from rag.ingest.loaders import load_text
from rag.ingest.vbpl import (
    VbplClient,
    default_stem,
    html_to_text,
    load_manifest,
    metadata_from_detail,
    pick_detail,
    save_document,
    slugify,
    write_manifest,
)

HTML = """
<div><p>QUỐC HỘI</p><p>Bộ luật số: <b>45/2019/QH14</b></p>
<script>var x = 1;</script>
<p>Chương I</p><p>NHỮNG QUY ĐỊNH CHUNG</p>
<p>Điều 1. Phạm vi điều chỉnh</p><p>Bộ luật   này quy định\n tiêu chuẩn lao động.</p>
<p>Điều 2. Đối tượng áp dụng</p><table><tr><td>1. Người lao động.</td></tr></table></div>
"""

DETAIL = {
    "id": "139264",
    "title": "Bộ Luật lao động số 45/2019/QH14",
    "docNum": "45/2019/QH14",
    "docType": {"id": "x", "name": "Bộ luật", "code": "BL"},
    "agencyName": "Quốc hội",
    "issueDate": "2019-11-20T00:00:00",
    "effFrom": "2021-01-01T00:00:00",
    "effTo": None,
    "effStatus": {"name": "Hết hiệu lực một phần", "code": "HHL1P"},
    "documentFields": [{"name": "Lao động"}],
    "documentContent": {"content": HTML},
}

FIXED_NOW = lambda: datetime(2026, 11, 3, tzinfo=timezone.utc)  # noqa: E731


class FakeResponse:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        pass

    def json(self):
        return {"success": True, "data": self._data}


class FakeSession:
    def __init__(self, pages=None, details=None, fail_first=0):
        self.pages = pages or []
        self.details = details or {}
        self.fail_first = fail_first
        self.posts = []
        self.gets = []

    def post(self, url, json, timeout):
        self.posts.append(json)
        if self.fail_first:
            self.fail_first -= 1
            raise ConnectionError("tạm lỗi")
        return FakeResponse(self.pages[json["pageNumber"] - 1])

    def get(self, url, timeout):
        doc_id = url.rsplit("/", 1)[-1]
        self.gets.append(doc_id)
        return FakeResponse(self.details[doc_id])


def client(session):
    return VbplClient(session=session, delay=0, sleep=lambda s: None)


# --- parse -----------------------------------------------------------------------------


def test_html_to_text_one_line_per_element_and_drops_scripts():
    text = html_to_text(HTML)
    assert "var x" not in text
    assert text.splitlines()[:3] == ["QUỐC HỘI", "Bộ luật số:", "45/2019/QH14"]
    assert "Bộ luật này quy định" in text and "1. Người lao động." in text


def test_html_text_chunks_by_article():
    """Text crawl về phải đi qua được chunker hiện có, tách đúng theo Điều."""
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "bl.txt"
        path.write_text(html_to_text(HTML), encoding="utf-8")
        chunks = chunk_document(load_text(path))
    sections = {c.section for c in chunks}
    assert any(s and "Điều 1" in s for s in sections) and any(s and "Điều 2" in s for s in sections)


def test_metadata_from_detail():
    meta = metadata_from_detail(DETAIL)
    assert meta["doc_number"] == "45/2019/QH14"
    assert meta["doc_type"] == "Bộ luật"
    assert meta["issue_date"] == "2019-11-20" and meta["effective_to"] is None
    assert meta["effective_status"] == "Hết hiệu lực một phần"
    assert meta["fields"] == ["Lao động"]
    assert meta["source_url"].endswith("/139264")


def test_slug_and_default_stem():
    assert slugify("Bộ Luật lao động Đất đai") == "bo_luat_lao_dong_dat_dai"
    assert default_stem(metadata_from_detail(DETAIL)) == "bo_luat_lao_dong_45_2019_qh14"


# --- client ----------------------------------------------------------------------------


def test_search_by_number_filters_fuzzy_matches():
    page = {"total": 3, "items": [
        {"id": "1", "docNum": "36/2005/QH11"},
        {"id": "2", "docNum": "75/2025/QH15"},
        {"id": "3", "docNum": "36/2005/qh11 "},
    ]}
    s = FakeSession(pages=[page])
    found = client(s).search_by_number("36/2005/QH11")
    assert [i["id"] for i in found] == ["1", "3"]
    assert s.posts[0]["keyword"] == "36/2005/QH11"


def test_pick_detail_skips_records_without_content():
    s = FakeSession(details={"old": {"id": "old", "documentContent": None}, "139264": DETAIL})
    detail = pick_detail(client(s), [{"id": "old"}, {"id": "139264"}])
    assert detail["id"] == "139264" and s.gets == ["old", "139264"]


def test_iter_list_paginates_until_total():
    pages = [{"total": 3, "items": [{"id": "a"}, {"id": "b"}]}, {"total": 3, "items": [{"id": "c"}]}]
    s = FakeSession(pages=pages)
    assert [i["id"] for i in client(s).iter_list(page_size=2)] == ["a", "b", "c"]
    assert len(s.posts) == 2


def test_retry_then_success():
    s = FakeSession(pages=[{"total": 0, "items": []}], fail_first=2)
    assert client(s).list_page(1) == {"total": 0, "items": []}
    assert len(s.posts) == 3


# --- lưu + manifest --------------------------------------------------------------------


def test_save_new_unchanged_updated(tmp_path):
    manifest = {}
    r = save_document(DETAIL, tmp_path, manifest, now=FIXED_NOW)
    assert r.status == "new" and r.text_file.name == "bo_luat_lao_dong_45_2019_qh14.txt"
    meta = json.loads((tmp_path / "bo_luat_lao_dong_45_2019_qh14.meta.json").read_text(encoding="utf-8"))
    assert meta["doc_number"] == "45/2019/QH14" and len(meta["sha256"]) == 64
    assert meta["crawled_at"] == "2026-11-03T00:00:00Z"
    # metadata không lẫn vào text để embed
    assert "sha256" not in r.text_file.read_text(encoding="utf-8")

    write_manifest(tmp_path, manifest)
    manifest = load_manifest(tmp_path)
    assert save_document(DETAIL, tmp_path, manifest, now=FIXED_NOW).status == "unchanged"

    changed = {**DETAIL, "documentContent": {"content": HTML.replace("tiêu chuẩn", "chuẩn mực")}}
    r = save_document(changed, tmp_path, manifest, now=FIXED_NOW)
    assert r.status == "updated"
    assert "chuẩn mực" in r.text_file.read_text(encoding="utf-8")
    assert manifest["139264"]["previous_sha256"] == meta["sha256"]


def test_save_empty_content_writes_nothing(tmp_path):
    r = save_document({**DETAIL, "documentContent": {"content": "<p> </p>"}}, tmp_path, {})
    assert r.status == "empty" and not list(tmp_path.iterdir())


def test_save_custom_stem(tmp_path):
    r = save_document(DETAIL, tmp_path, {}, stem="bo_luat_lao_dong_2019")
    assert r.text_file == tmp_path / "bo_luat_lao_dong_2019.txt"
