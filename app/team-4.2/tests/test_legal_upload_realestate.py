"""Upload văn bản pháp luật trên văn bản thật nhóm bất động sản (spec phần 3 §6): upload = crawler, PDF có text = vbpl,
luật sửa đổi trước luật gốc, cùng file hai lần, thay bản upload khi tra vbpl lỗi, thay VBHN, nhiều mốc hiệu lực,
dựng lỗi ở luật thứ N mà chat không đổi.

Fixture `fixtures/legal/realestate`: text đúng dạng crawler (`html_to_legal_text`) + một dòng trống cuối file;
manifest giữ metadata vbpl (id, ngày, eff_status) dùng làm chi tiết vbpl giả.
"""

import html
import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from rag.legal.crawl import save_detail
from rag.legal.effectivity import parse_effectivity
from rag.legal.keys import unit_sort_key
from rag.legal.models import LegalDocument
from rag.legal.rawfiles import write_text
from rag.legal.service import LegalService
from rag.legal.snapshots import SnapshotManager
from rag.legal.store import LegalStore, decode
from rag.legal.text import html_to_legal_text
from rag.legal.upload.drafts import DraftStore
from rag.legal.upload.flow import UploadService
from rag.temporal.index import VersionedIndex
from rag.temporal.qa import TemporalQA
from tests.test_extraction_check import ARIAL, _pdf
from tests.test_legal_upload_flow import FakeVbplClient
from tests.test_legal_upload_normalize import wrap_like_pdf
from tests.test_temporal_qa import FIRM, FakeLLM

UI = Path(__file__).resolve().parents[1] / "ui"
if str(UI) not in sys.path:
    sys.path.insert(0, str(UI))
from legal_runtime import LegalRuntime, RuntimeHolder, WriteWorker  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures" / "legal" / "realestate"
NOW = datetime(2026, 11, 10, 9, 0, tzinfo=timezone.utc)
LAND, HOUSING, BIZ = "luat:31/2024/QH15", "luat:27/2023/QH15", "luat:29/2023/QH15"
AMEND = "luat:43/2024/QH15"
VBHN = "vbhn:01/VBHN-VPQH"
MANIFEST = {r["document_key"]: r for r in json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))}


def fixture_text(key: str) -> str:
    """Text như crawler lưu (`html_to_legal_text`): bỏ dòng trống cuối file fixture."""
    return (FIXTURES / MANIFEST[key]["raw_text_path"]).read_text(encoding="utf-8").rstrip("\n")


def as_html(text: str) -> str:
    return "".join(f"<p>{html.escape(line)}</p>" for line in text.splitlines())


def detail_for(key: str, text: str | None = None) -> dict:
    """Chi tiết vbpl giả từ manifest (ruling R4: mỗi dòng fixture bọc trong <p>)."""
    row = MANIFEST[key]
    day = lambda v: f"{v}T00:00:00" if v else None  # noqa: E731
    return {"id": int(row["vbpl_id"]), "docNum": row["doc_number"], "docType": {"name": row["doc_type"]},
            "agencyName": row["issuer"], "title": row["title"], "issueDate": day(row["issued_on"]),
            "effFrom": day(row["vbpl_effective_from"]), "effTo": day(row["vbpl_effective_to"]),
            "effStatus": {"name": row["eff_status"]},
            "documentContent": {"content": as_html(text if text is not None else fixture_text(key))}}


def url_of(key: str) -> str:
    return f"https://vbpl.vn/van-ban/chi-tiet/{MANIFEST[key]['vbpl_id']}"


def make_env(tmp_path, *, exclude=(), build=False, offline=False):
    """Kho (legacy catalog -> snapshot bootstrap) gồm manifest trừ `exclude`, text ghi theo nội dung như crawler."""
    legal = tmp_path / "legal"
    store = LegalStore(legal / "catalog.sqlite")
    for key, row in MANIFEST.items():
        if key in exclude:
            continue
        path, checksum = write_text(legal / "raw", key, fixture_text(key))
        assert checksum == row["raw_checksum"]             # cùng text crawler đã lưu
        store.upsert_document(decode(LegalDocument, {**row, "raw_text_path": str(path)}))
    if build:
        LegalService(store, now=lambda: NOW).build_all()
    snapshots = SnapshotManager(legal, now=lambda: NOW)
    client = FakeVbplClient({MANIFEST[k]["vbpl_id"]: detail_for(k) for k in MANIFEST}, offline=offline)
    upload = UploadService(snapshots, DraftStore(legal / "uploads"), client_factory=lambda: client, now=lambda: NOW)
    files = tmp_path / "files"
    files.mkdir()
    return SimpleNamespace(legal=legal, snapshots=snapshots, upload=upload, client=client, files=files)


def through_steps(env, d, *, replace_existing=False):
    up = env.upload
    d = up.choose_replace(d.upload_id, "An") if replace_existing else up.confirm_text(d.upload_id, "An")
    d = up.confirm_understanding(d.upload_id, "An")
    return up.submit(d.upload_id, "An")


def write(env, d):
    return env.snapshots.write(f"upload:{d.upload_id}", "An", lambda s: env.upload.apply_to(s, d.upload_id))


def upload_url(env, key, **kw):
    d = env.upload.create_from_url(url_of(key))
    assert d.state == "step1"
    return write(env, through_steps(env, d, **kw))


def versions_signature(store: LegalStore, key: str):
    return sorted((v.provision_id, v.valid_from, v.valid_to, v.text, v.verification_status)
                  for v in store.versions(key))


def reasons_signature(store: LegalStore, key: str):
    return sorted((v.provision_id, v.valid_from, tuple(sorted(v.status_reasons))) for v in store.versions(key))


@pytest.fixture(scope="module")
def crawler_store(tmp_path_factory):
    """A: manifest đầy đủ -> build_all (như test_legal_realestate)."""
    store = LegalStore(tmp_path_factory.mktemp("crawler") / "catalog.sqlite")
    for row in MANIFEST.values():
        store.upsert_document(decode(LegalDocument, {**row, "raw_text_path": str(FIXTURES / row["raw_text_path"])}))
    LegalService(store, now=lambda: NOW).build_all()
    return store


def test_fake_vbpl_html_round_trips_fixture_text():
    # R4: html_to_legal_text(<p>dòng</p>...) == fixture, chỉ khác dòng trống cuối file
    for key in MANIFEST:
        raw = (FIXTURES / MANIFEST[key]["raw_text_path"]).read_text(encoding="utf-8")
        assert html_to_legal_text(as_html(raw)) == raw.rstrip("\n") == fixture_text(key)


def test_upload_equals_crawler(tmp_path, crawler_store):
    env = make_env(tmp_path, exclude=(AMEND,))
    res = upload_url(env, AMEND)
    uploaded = env.snapshots.store(res.snapshot.snapshot_id)
    assert uploaded.document(AMEND).raw_checksum == MANIFEST[AMEND]["raw_checksum"]
    for key in (LAND, HOUSING, BIZ, AMEND):
        assert versions_signature(crawler_store, key) == versions_signature(uploaded, key), key
        assert reasons_signature(crawler_store, key) == reasons_signature(uploaded, key), key

    # cùng văn bản qua crawler thật (save_detail) trong một lần ghi snapshot cho cùng kết quả
    env2 = make_env(tmp_path / "c", exclude=(AMEND,))

    def crawl(svc):
        doc, _ = save_detail(detail_for(AMEND), env2.legal / "raw", now=lambda: NOW)
        svc.store.upsert_document(doc)
    crawled = env2.snapshots.store(env2.snapshots.write("cli:crawl", "t", crawl).snapshot.snapshot_id)
    for key in (LAND, HOUSING, BIZ, AMEND):
        assert versions_signature(crawled, key) == versions_signature(uploaded, key), key


def _ops(preview):
    return [(o["source_locator"], o["description"], o["effective_from"]) for o in preview["operations"]]


@pytest.mark.skipif(not os.path.exists(ARIAL), reason="cần font Arial để vẽ tiếng Việt")
def test_pdf_like_file_gives_same_operations_as_vbpl(tmp_path):
    env = make_env(tmp_path, exclude=(AMEND,))
    pages = wrap_like_pdf(fixture_text(AMEND), width=70)
    pdf = _pdf(tmp_path / "43.pdf", pages)
    f = env.upload.create_from_file(pdf, "43.pdf")
    assert f.fields["doc_number"]["value"] == "43/2024/QH15" and f.source_verified       # tra vbpl theo số hiệu
    f = env.upload.preview(env.upload.confirm_text(f.upload_id, "An").upload_id)
    u = env.upload.create_from_url(url_of(AMEND))
    u = env.upload.preview(env.upload.confirm_text(u.upload_id, "An").upload_id)
    assert f.structure["n_articles"] == u.structure["n_articles"] and not f.structure["gaps"]
    assert _ops(f.preview) and _ops(f.preview) == _ops(u.preview)
    assert [o["review_status"] for o in f.preview["operations"]] == [o["review_status"] for o in u.preview["operations"]]


def test_amending_before_base_applies_later(tmp_path, crawler_store):
    env = make_env(tmp_path, exclude=(AMEND, HOUSING))
    res = upload_url(env, AMEND)
    store = env.snapshots.store(res.snapshot.snapshot_id)
    waiting = [o for o in store.operations(source_key=AMEND)
               if o.target_law_name and "Nhà ở" in o.target_law_name]
    assert waiting and all(o.target_document_key is None and o.review_status == "pending"
                           and "operation.target_law_not_found" in o.status_reasons for o in waiting)

    res = upload_url(env, HOUSING)
    svc = env.snapshots.service(res.snapshot.snapshot_id)
    applied = [o for o in svc.store.operations(source_key=AMEND) if o.target_document_key == HOUSING]
    assert applied and all(o.review_status == "auto_accepted" for o in applied)
    article = parse_effectivity(svc.provisions_for(HOUSING)).article
    history = svc.store.provision_history(f"{HOUSING}#d{article}")
    assert date(2024, 8, 1) in {v.valid_from for v in history}
    assert versions_signature(svc.store, HOUSING) == versions_signature(crawler_store, HOUSING)


def test_same_file_twice_no_new_snapshot(tmp_path):
    env = make_env(tmp_path, exclude=(AMEND,))
    path = env.files / "43.txt"
    path.write_text(fixture_text(AMEND), encoding="utf-8")
    write(env, through_steps(env, env.upload.create_from_file(path, "43.txt")))
    n = len(env.snapshots.list())
    current = env.snapshots.current().snapshot_id
    d = env.upload.create_from_file(path, "43.txt")
    assert d.state == "duplicate" and d.duplicate["diff"] is None
    with pytest.raises(ValueError):
        env.upload.confirm_text(d.upload_id, "An")
    assert len(env.snapshots.list()) == n and env.snapshots.current().snapshot_id == current


def test_unverified_replace_does_not_inherit_verification(tmp_path):
    env = make_env(tmp_path, exclude=(AMEND,))
    path = env.files / "43.txt"
    path.write_text(fixture_text(AMEND), encoding="utf-8")
    res = write(env, through_steps(env, env.upload.create_from_file(path, "43.txt")))
    first = env.snapshots.store(res.snapshot.snapshot_id).document(AMEND)
    assert first.text_source == "file" and first.source_verified

    env.client.offline = True                                   # tra vbpl lỗi lần này
    edited = env.files / "43b.txt"
    edited.write_text(fixture_text(AMEND).replace("Luật này có hiệu lực thi hành",
                                                  "Luật này có hiệu lực thi  hành", 1)
                      .replace("Quốc hội ban hành", "Quốc hội nước ban hành", 1), encoding="utf-8")
    d = env.upload.create_from_file(edited, "43b.txt")
    assert d.duplicate and d.duplicate["replace_allowed"] and not d.source_verified
    d = through_steps(env, d, replace_existing=True)
    assert d.fields["vbpl_id"]["source"] == "inherited"
    store = env.snapshots.store(write(env, d).snapshot.snapshot_id)
    doc = store.document(AMEND)
    assert doc.source_verified is False and doc.field_sources["vbpl_id"]["source"] == "inherited"
    assert doc.vbpl_id == MANIFEST[AMEND]["vbpl_id"]
    versions = store.versions(AMEND)
    assert versions and all(v.verification_status == "needs_review" and "source.no_vbpl_metadata" in v.status_reasons
                            for v in versions)


def _vbhn_text(articles: list[str]) -> str:
    head = ("VĂN PHÒNG QUỐC HỘI\nSố: 01/VBHN-VPQH\nHà Nội, ngày 10 tháng 9 năm 2024\nVĂN BẢN HỢP NHẤT\nLUẬT\nNHÀ Ở\n"
            "Luật Nhà ở số 27/2023/QH15 ngày 27 tháng 11 năm 2023 của Quốc hội, có hiệu lực kể từ ngày 01 tháng 01 "
            "năm 2025, được sửa đổi, bổ sung bởi:\nLuật số 43/2024/QH15 ngày 29 tháng 6 năm 2024 của Quốc hội sửa "
            "đổi, bổ sung một số điều của Luật Đất đai, Luật Nhà ở, có hiệu lực kể từ ngày 01 tháng 8 năm 2024.")
    return head + "\n" + "\n".join(articles)


def _vbhn_detail(text: str) -> dict:
    return {"id": 900001, "docNum": "01/VBHN-VPQH", "docType": {"name": "Văn bản hợp nhất"},
            "agencyName": "Văn phòng Quốc hội", "title": "Luật Nhà ở", "issueDate": "2024-09-10T00:00:00",
            "isConsolidatedDocument": True, "effStatus": {"name": "Còn hiệu lực"},
            "documentContent": {"content": as_html(text)}}


def _mismatch_articles(store):
    return {v.provision_id.partition("#d")[2] for v in store.versions(HOUSING)
            if "vbhn.text_differs" in v.status_reasons and v.kind == "article"}


def test_replace_vbhn_keeps_links(tmp_path):
    env = make_env(tmp_path, build=True)
    built = env.snapshots.store()
    cutoff = date(2024, 8, 1)
    articles = sorted((v for v in built.provisions_as_of(HOUSING, cutoff) if v.kind == "article"),
                      key=lambda v: unit_sort_key(v.provision_id.partition("#d")[2]))
    texts = [v.text for v in articles]
    assert texts[0].startswith("Điều 1.") and texts[1].startswith("Điều 2.")
    v1 = _vbhn_text([texts[0].replace("Luật này", "Luật này (bản in lỗi)", 1), *texts[1:]])
    v2 = _vbhn_text([texts[0], texts[1].replace("Luật này", "Luật này (bản in lỗi)", 1), *texts[2:]])

    env.client.details["900001"] = _vbhn_detail(v1)
    d = env.upload.create_from_url("https://vbpl.vn/van-ban/chi-tiet/900001")
    store = env.snapshots.store(write(env, through_steps(env, d)).snapshot.snapshot_id)
    rels = [(r.source_key, r.relation, r.status) for r in store.relations(HOUSING) if r.relation == "HOP_NHAT"]
    assert rels == [(VBHN, "HOP_NHAT", "confirmed")]
    assert _mismatch_articles(store) == {"1"}

    env.client.details["900001"] = _vbhn_detail(v2)            # vbpl sửa bản hợp nhất
    d = env.upload.create_from_url("https://vbpl.vn/van-ban/chi-tiet/900001")
    assert d.duplicate and d.duplicate["replace_allowed"]
    store = env.snapshots.store(write(env, through_steps(env, d, replace_existing=True)).snapshot.snapshot_id)
    assert store.document(VBHN).raw_checksum == d.checksum
    rels = [(r.source_key, r.relation, r.status) for r in store.relations(HOUSING) if r.relation == "HOP_NHAT"]
    assert rels == [(VBHN, "HOP_NHAT", "confirmed")]
    assert _mismatch_articles(store) == {"2"}                   # đối chiếu dùng text mới
    item = store.review_item(f"vbhn:{VBHN}:2")
    assert item is not None and item.status == "open"


def test_multi_date_effectivity_preview(tmp_path):
    env = make_env(tmp_path, exclude=(LAND,), build=True)        # đã lập thao tác: 43/2024 chờ Luật Đất đai
    d = env.upload.create_from_url(url_of(LAND))
    d = env.upload.preview(env.upload.confirm_text(d.upload_id, "An").upload_id)
    eff = d.preview["effectivity"]
    assert d.preview["kind"] == "base" and eff["default_from"] == "2025-01-01"
    exc = {e["date"]: e for e in eff["exceptions"]}
    assert exc["2024-04-01"]["units"] == ["Điều 190", "Điều 248"] and "01 tháng 4 năm 2024" in exc["2024-04-01"]["evidence"]
    assert "khoản 9 Điều 60" in [c["unit"] for c in eff["conditional_units"]]
    assert eff["evidence"] and eff["flags_vi"]
    assert d.preview["waiting_for_this"] > 0                    # chỉ dẫn của 43/2024 đang chờ Luật Đất đai


def test_build_failure_at_nth_law_chat_unchanged(tmp_path, monkeypatch):
    env = make_env(tmp_path, exclude=(AMEND,), build=True)
    llm = FakeLLM(FIRM)

    def make_runtime(sid):
        svc = env.snapshots.service(sid)
        index = VersionedIndex(svc.store, snapshot_id=sid)
        index.build()
        return LegalRuntime(sid, svc, index, TemporalQA(svc, index, llm, now=lambda: NOW))

    holder = RuntimeHolder(env.snapshots, make_runtime)
    worker = WriteWorker(env.snapshots, holder, make_runtime=make_runtime)
    old = holder.get()
    question = "Ký hợp đồng mua nhà ngày 15/06/2025, điều kiện làm chủ đầu tư dự án nhà ở thương mại là gì?"
    before = old.qa.ask(question)
    assert before.items

    d = through_steps(env, env.upload.create_from_url(url_of(AMEND)))
    calls = []
    real_build_law = LegalService.build_law

    def flaky(self, key):
        calls.append(key)
        if len(calls) == 3:
            raise RuntimeError(f"dựng lỗi ở luật thứ 3 ({key})")
        return real_build_law(self, key)
    monkeypatch.setattr(LegalService, "build_law", flaky)

    job = worker.submit("upload", d.upload_id, "An", lambda s: env.upload.apply_to(s, d.upload_id))
    assert worker.wait_idle(120)
    j = worker.job(job.job_id)
    assert j.state == "failed" and "luật thứ 3" in j.error and len(calls) == 3
    assert env.snapshots.list()[0].status == "failed"
    assert env.snapshots.current().snapshot_id == old.snapshot_id
    assert holder.get() is old and holder.get().snapshot_id == old.snapshot_id
    after = holder.get().qa.ask(question)
    assert [i.chunk_id for i in after.items] == [i.chunk_id for i in before.items]
    assert env.snapshots.store().document(AMEND) is None
