"""Luồng upload 3 bước: bản nháp, kiểm trùng, xem trước, áp vào snapshot (spec §4.0–4.2, §4.4 bước 1)."""

import functools
import html
from dataclasses import replace
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from rag.ingest.loaders import load_source
from rag.ingest.vbpl import VbplError
from rag.legal.keys import document_key
from rag.legal.models import LegalDocument
from rag.legal.rawfiles import write_text
from rag.legal.service import LegalService
from rag.legal.snapshots import SnapshotManager
from rag.legal.store import LegalStore
from rag.legal.upload import normalize_legal_text
from rag.legal.upload.drafts import Draft, DraftStore
from rag.legal.upload.flow import REASONS_VI, StaleDraftError, StepError, UploadService

FIXTURES = Path(__file__).parent / "fixtures" / "legal" / "realestate"
NOW = datetime(2026, 11, 10, 9, 0, tzinfo=timezone.utc)
LAND, HOUSING, AMEND = "luat:31/2024/QH15", "luat:27/2023/QH15", "luat:43/2024/QH15"
TXT_43 = FIXTURES / "luat_43_2024_QH15.txt"
KEY_UPLOADED = document_key("Luật", "99/2024/QH15")

UPLOADED_V1 = """QUỐC HỘI
Số: 99/2024/QH15
Hà Nội, ngày 10 tháng 1 năm 2024
LUẬT
THỬ NGHIỆM
Điều 1. Phạm vi
Luật này quy định về thử nghiệm.
Điều 2. Đối tượng
Luật này áp dụng cho mọi tổ chức.
Điều 3. Hiệu lực thi hành
Luật này có hiệu lực thi hành từ ngày 01 tháng 8 năm 2024.
"""
UPLOADED_V2 = UPLOADED_V1.replace("mọi tổ chức.", "mọi tổ chức, cá nhân.")

DETAIL_43 = {"id": 171234, "docNum": "43/2024/QH15", "docType": {"name": "Luật"}, "agencyName": "Quốc hội",
             "title": "Luật sửa đổi, bổ sung một số điều của Luật Đất đai số 31/2024/QH15, Luật Nhà ở số "
                      "27/2023/QH15, Luật Kinh doanh bất động sản số 29/2023/QH15 và Luật Các tổ chức tín dụng "
                      "số 32/2024/QH15",
             "issueDate": "2024-06-29T00:00:00", "effFrom": "2024-08-01T00:00:00",
             "effStatus": {"name": "Còn hiệu lực"},
             "documentContent": {"content": "".join(f"<p>{html.escape(l)}</p>" for l in
                                                    TXT_43.read_text(encoding="utf-8").splitlines())}}


class FakeVbplClient:
    def __init__(self, details: dict[str, dict], *, offline: bool = False) -> None:
        self.details, self.offline = details, offline

    def search_by_number(self, number):
        if self.offline:
            raise VbplError("down")
        return [{"id": d["id"], "docNum": d["docNum"], "docType": d["docType"]}
                for d in self.details.values() if d["docNum"] == number]

    def detail(self, doc_id):
        if self.offline or str(doc_id) not in self.details:
            raise VbplError(f"không có {doc_id}")
        return self.details[str(doc_id)]


@functools.lru_cache(maxsize=None)
def _fixture_text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")       # nguyên văn fixture, header "Luật số: N"


@functools.lru_cache(maxsize=None)
def _normalized(path: str) -> str:
    return normalize_legal_text([p.text for p in load_source(Path(path))])


def _doc(key, number, title, issued, path, checksum, **kw):
    return LegalDocument(key, "1", title, "Luật", number, "Quốc hội", issued, None, None, None, False, str(path),
                         checksum, NOW, **kw)


def _make_env(tmp_path, *, housing=True, offline=False):
    files = tmp_path / "files"
    files.mkdir()
    land_file = files / "31.txt"
    land_file.write_text(_fixture_text("luat_31_2024_QH15.txt"), encoding="utf-8")
    legal = tmp_path / "legal"
    raw = legal / "raw"
    store = LegalStore(legal / "catalog.sqlite")
    path, checksum = write_text(raw, LAND, _normalized(str(land_file)))
    store.upsert_document(_doc(LAND, "31/2024/QH15", "Luật Đất đai số 31/2024/QH15", date(2024, 1, 18), path,
                               checksum))
    if housing:
        path, checksum = write_text(raw, HOUSING, _fixture_text("luat_27_2023_QH15.txt"))
        store.upsert_document(_doc(HOUSING, "27/2023/QH15", "Luật Nhà ở số 27/2023/QH15", date(2023, 11, 27),
                                   path, checksum))
    path, checksum = write_text(raw, KEY_UPLOADED, UPLOADED_V1)
    store.upsert_document(_doc(KEY_UPLOADED, "99/2024/QH15", "Luật Thử nghiệm", date(2024, 1, 10), path, checksum,
                               text_source="file", content_verified={"by": "Bình", "at": NOW.isoformat()},
                               source_verified=False))
    snapshots = SnapshotManager(legal, now=lambda: NOW)
    drafts_root = legal / "uploads"
    client = FakeVbplClient({"171234": DETAIL_43}, offline=offline)
    upload = UploadService(snapshots, DraftStore(drafts_root), client_factory=lambda: client, now=lambda: NOW)
    return SimpleNamespace(snapshots=snapshots, upload=upload, drafts_root=drafts_root, files=files,
                           land_file=land_file, client=client)


@pytest.fixture
def svc_env(tmp_path):
    return _make_env(tmp_path)


@pytest.fixture
def svc_env_offline(tmp_path):
    return _make_env(tmp_path, offline=True)


@pytest.fixture
def svc_env_without_housing_law(tmp_path):
    return _make_env(tmp_path, housing=False)


def _file(env, name, text):
    path = env.files / name
    path.write_text(text, encoding="utf-8")
    return path


def walk_to_step2(env, path, replace=False):
    d = env.upload.create_from_file(path, Path(path).name)
    return env.upload.choose_replace(d.upload_id, "An") if replace else env.upload.confirm_text(d.upload_id, "An")


def walk_to_step3(env, path, replace=False):
    d = walk_to_step2(env, path, replace)
    return env.upload.confirm_understanding(d.upload_id, "An")


def replace_text_in_store(svc, key, text):
    old = svc.store.document(key)
    path, checksum = write_text(svc.store.path.parents[2] / "raw", key, UPLOADED_V1.replace("thử nghiệm.", f"{text}."))
    svc.store.upsert_document(replace(old, raw_text_path=str(path), raw_checksum=checksum))


# --- bước ① ---------------------------------------------------------------------------------------


def test_url_flow_creates_step1_with_vbpl_fields(svc_env):
    d = svc_env.upload.create_from_url("https://vbpl.vn/van-ban/chi-tiet/171234")
    assert d.state == "step1" and d.fields["doc_number"]["source"] == "vbpl" and d.source_verified
    assert d.origin == "url" and d.pages == [] and d.structure["n_articles"] == 5
    assert d.base_snapshot_id == svc_env.snapshots.current().snapshot_id


def test_bad_url_raises_step_error(svc_env):
    with pytest.raises(StepError, match="vbpl"):
        svc_env.upload.create_from_url("https://vbpl.vn/van-ban/khac/1")


def test_unknown_vbpl_id_raises_step_error(svc_env):
    with pytest.raises(StepError, match="vbpl"):
        svc_env.upload.create_from_url("https://vbpl.vn/van-ban/chi-tiet/999")


def test_steps_cannot_be_skipped(svc_env):
    d = svc_env.upload.create_from_file(TXT_43, "43.txt")
    with pytest.raises(StepError):
        svc_env.upload.confirm_understanding(d.upload_id, "An")
    with pytest.raises(StepError):
        svc_env.upload.submit(d.upload_id, "An")
    with pytest.raises(StepError):
        svc_env.upload.preview(d.upload_id)
    with pytest.raises(StepError):
        svc_env.upload.choose_replace(d.upload_id, "An")       # không trùng: không có gì để thay


def test_file_draft_keeps_original_and_page_report(svc_env):
    d = svc_env.upload.create_from_file(TXT_43, "43.txt")
    assert (svc_env.drafts_root / d.upload_id / "original.txt").read_bytes() == TXT_43.read_bytes()
    assert d.pages and d.pages[0]["chars"] > 0
    assert d.fields["doc_number"]["value"] == "43/2024/QH15" and d.source_verified   # tra vbpl theo số hiệu
    assert d.fields["vbpl_id"]["value"] == "171234"


def test_file_without_vbpl_match_is_unverified(svc_env_offline):
    d = svc_env_offline.upload.create_from_file(TXT_43, "43.txt")
    assert d.source_verified is False
    assert d.fields["doc_number"]["source"] == "text"


def test_text_is_not_pii_masked(svc_env):
    text = UPLOADED_V1.replace("99/2024", "77/2024").replace(
        "mọi tổ chức.", "ông Nguyễn Văn An, số điện thoại 0912345678.")
    d = svc_env.upload.create_from_file(_file(svc_env, "x.txt", text), "x.txt")
    assert "0912345678" in d.text and "Nguyễn Văn An" in d.text


def test_identical_duplicate_stops(svc_env):
    d = svc_env.upload.create_from_file(svc_env.land_file, "31.txt")
    assert d.state == "duplicate" and d.duplicate["diff"] is None
    assert d.duplicate["document_key"] == LAND
    with pytest.raises(StepError):
        svc_env.upload.confirm_text(d.upload_id, "An")


def test_file_cannot_replace_vbpl_text(svc_env):
    edited = _fixture_text("luat_31_2024_QH15.txt").replace("Luật này quy định về chế độ sở hữu đất đai",
                                                           "Luật này quy định chi tiết về chế độ sở hữu đất đai", 1)
    d = svc_env.upload.create_from_file(_file(svc_env, "31b.txt", edited), "31.txt")
    assert d.state == "step1"
    assert d.duplicate["replace_allowed"] is False and d.duplicate["diff"]["changed"]
    assert [c["article"] for c in d.duplicate["diff"]["changed"]] == ["1"]
    with pytest.raises(StepError):
        svc_env.upload.choose_replace(d.upload_id, "An")
    with pytest.raises(StepError):
        svc_env.upload.confirm_text(d.upload_id, "An")


def test_file_can_replace_file_text_and_inherits(svc_env):
    d = svc_env.upload.create_from_file(_file(svc_env, "99.txt", UPLOADED_V2), "99.txt")
    assert d.duplicate["replace_allowed"] is True and d.duplicate["text_source"] == "file"
    d = svc_env.upload.choose_replace(d.upload_id, "An")
    assert d.state == "step2" and d.replace and d.confirmations["step1"]["by"] == "An"
    assert d.fields["vbpl_id"]["source"] == "inherited"


def test_confirm_text_moves_to_step2(svc_env):
    d = walk_to_step2(svc_env, TXT_43)
    assert d.state == "step2" and d.confirmations["step1"]["by"] == "An"
    with pytest.raises(StepError):
        svc_env.upload.confirm_text(d.upload_id, "An")


# --- bước ② ---------------------------------------------------------------------------------------


def test_update_fields_marks_user_source_and_rechecks_duplicate(svc_env):
    text = UPLOADED_V2.replace("Số: 99/2024/QH15\n", "")
    d = walk_to_step2(svc_env, _file(svc_env, "noname.txt", text))
    assert "doc_number" not in d.fields and d.duplicate is None
    d = svc_env.upload.update_fields(d.upload_id, {"doc_number": "99/2024/QH15"}, "An")
    assert d.fields["doc_number"] == {"value": "99/2024/QH15", "source": "user", "at": NOW.isoformat(), "detail": "An"}
    assert d.duplicate and d.duplicate["document_key"] == KEY_UPLOADED and d.state == "step1"   # quay về so sánh


def test_update_fields_rejects_bad_values(svc_env):
    d = walk_to_step2(svc_env, TXT_43)
    with pytest.raises(StepError):
        svc_env.upload.update_fields(d.upload_id, {"issued_on": "không phải ngày"}, "An")
    with pytest.raises(StepError):
        svc_env.upload.update_fields(d.upload_id, {"bogus": "x"}, "An")
    d = svc_env.upload.update_fields(d.upload_id, {"issued_on": "29/06/2024"}, "An")
    assert d.fields["issued_on"]["value"] == "2024-06-29"


def test_relookup_vbpl(svc_env_offline):
    env = svc_env_offline
    d = env.upload.create_from_file(TXT_43, "43.txt")
    assert not d.source_verified
    env.client.offline = False                  # mạng trở lại
    d = env.upload.relookup_vbpl(d.upload_id)
    assert d.source_verified and d.fields["vbpl_id"]["value"] == "171234"


def test_preview_warns_missing_base_law(svc_env_without_housing_law):
    d = walk_to_step2(svc_env_without_housing_law, TXT_43)
    d = svc_env_without_housing_law.upload.preview(d.upload_id)
    warn = [t["warning"] for t in d.preview["targets"] if not t["in_store"]]
    assert "Văn bản này sửa Luật Nhà ở 27/2023/QH15, nhưng kho chưa có luật này. Hãy upload luật gốc." in warn
    assert {t["document_key"] for t in d.preview["targets"] if t["in_store"]} == {LAND}


def test_preview_shows_per_operation_dates(svc_env):
    d = svc_env.upload.preview(walk_to_step2(svc_env, TXT_43).upload_id)
    assert all("effective_from" in o for o in d.preview["operations"])
    assert d.preview["kind"] == "amending"
    lead = next(o for o in d.preview["operations"] if o["source_locator"] == "Điều 1 > 4")
    assert lead["description"] == "Sửa đoạn đầu khoản 4 Điều 260 của Luật Đất đai"
    assert lead["effective_from"] == "2024-08-01" and lead["review_status"] == "auto_accepted"
    assert lead["excerpt"]
    credit = next(o for o in d.preview["operations"] if o["source_locator"] == "Điều 4")
    assert credit["review_status"] == "pending"
    assert REASONS_VI["operation.target_law_not_found"] in credit["reasons_vi"]
    assert d.preview["effectivity"]["default_from"] == "2024-08-01"
    assert "có hiệu lực thi hành từ ngày 01 tháng 8 năm 2024" in d.preview["effectivity"]["evidence"]
    # xem trước không ghi gì vào kho
    assert svc_env.snapshots.store().document(AMEND) is None


def test_preview_effectivity_of_base_law(svc_env):
    text = _fixture_text("luat_31_2024_QH15.txt").replace("31/2024/QH15", "31/2099/QH15")
    d = svc_env.upload.preview(walk_to_step2(svc_env, _file(svc_env, "land.txt", text)).upload_id)
    eff = d.preview["effectivity"]
    assert d.preview["kind"] == "base"
    assert eff["default_from"] == "2025-01-01"
    assert {"units": ["Điều 190", "Điều 248"], "date": "2024-04-01"} == {k: eff["exceptions"][0][k]
                                                                        for k in ("units", "date")}
    assert "01 tháng 4 năm 2024" in eff["exceptions"][0]["evidence"]
    assert [c["unit"] for c in eff["conditional_units"]] == ["khoản 9 Điều 60"]
    assert eff["flags_vi"]
    repealed = {r["number"]: r for r in d.preview["repeals"]}
    assert "45/2013/QH13" in repealed and repealed["45/2013/QH13"]["in_store"] is False
    assert "hết hiệu lực" in repealed["45/2013/QH13"]["evidence"]


def test_preview_counts_operations_waiting_for_base_law(svc_env_without_housing_law):
    env = svc_env_without_housing_law
    d = env.upload.submit(walk_to_step3(env, TXT_43).upload_id, "An")
    env.snapshots.write(f"upload:{d.upload_id}", "An", lambda s: env.upload.apply_to(s, d.upload_id))
    housing = _file(env, "27.txt", _fixture_text("luat_27_2023_QH15.txt"))
    d = env.upload.preview(walk_to_step2(env, housing).upload_id)
    assert d.preview["waiting_for_this"] == 1                   # Điều 2 của 43/2024 đang chờ Luật Nhà ở
    assert env.snapshots.store().document(HOUSING) is None


def test_reject_unsupported_type(svc_env):
    decree = UPLOADED_V1.replace("Số: 99/2024/QH15", "Số: 10/2024/NĐ-CP").replace("LUẬT\n", "NGHỊ ĐỊNH\n")
    d = walk_to_step2(svc_env, _file(svc_env, "nd.txt", decree))
    d = svc_env.upload.update_fields(d.upload_id, {"doc_type": "Nghị định", "title": "Nghị định thử"}, "An")
    with pytest.raises(StepError, match="Kho luật chỉ nhận"):
        svc_env.upload.confirm_understanding(d.upload_id, "An")


def test_missing_required_fields_block_step2(svc_env):
    d = walk_to_step2(svc_env, _file(svc_env, "noname.txt", UPLOADED_V2.replace("Số: 99/2024/QH15\n", "")))
    with pytest.raises(StepError, match="Số hiệu"):
        svc_env.upload.confirm_understanding(d.upload_id, "An")


def test_consolidated_needs_target_law(svc_env):
    text = UPLOADED_V1.replace("Số: 99/2024/QH15", "Số: 01/VBHN-VPQH").replace("LUẬT\n", "VĂN BẢN HỢP NHẤT\n")
    d = walk_to_step2(svc_env, _file(svc_env, "vbhn.txt", text))
    with pytest.raises(StepError, match="hợp nhất"):
        svc_env.upload.confirm_understanding(d.upload_id, "An")


# --- bước ③ và áp vào kho -------------------------------------------------------------------------


def test_submit_queues_without_writing(svc_env):
    d = walk_to_step3(svc_env, TXT_43)
    assert d.state == "step3" and d.preview is not None
    with pytest.raises(StepError):
        svc_env.upload.submit(d.upload_id, "  ")
    d = svc_env.upload.submit(d.upload_id, "An", "ghi chú")
    assert d.state == "queued" and d.confirmations["step3"]["note"] == "ghi chú"
    assert svc_env.snapshots.store().document(AMEND) is None


def test_apply_writes_document_and_relations(svc_env):
    d = svc_env.upload.submit(walk_to_step3(svc_env, TXT_43).upload_id, "An")
    res = svc_env.snapshots.write(f"upload:{d.upload_id}", "An", lambda s: svc_env.upload.apply_to(s, d.upload_id))
    store = svc_env.snapshots.store(res.snapshot.snapshot_id)
    doc = store.document(AMEND)
    assert doc.discovered_via == f"upload:{d.upload_id}" and doc.text_source == "file"
    assert doc.content_verified == {"by": "An", "at": NOW.isoformat()} and doc.source_verified
    assert doc.field_sources["doc_number"]["source"] == "vbpl" and doc.raw_checksum == d.checksum
    assert Path(doc.raw_text_path).read_text(encoding="utf-8") == d.text
    rels = {(r.target_key, r.relation, r.status) for r in store.relations(AMEND) if r.source_key == AMEND}
    assert rels == {(LAND, "SUA_DOI_BO_SUNG", "confirmed"), (HOUSING, "SUA_DOI_BO_SUNG", "confirmed")}


def test_apply_replace_keeps_relations(svc_env):
    from rag.legal.models import DocumentRelation
    svc_env.snapshots.write("seed", "B", lambda s: s.store.add_relation(
        DocumentRelation(KEY_UPLOADED, LAND, "SUA_DOI_BO_SUNG", "x", "confirmed")))
    d = walk_to_step3(svc_env, _file(svc_env, "99.txt", UPLOADED_V2), replace=True)
    d = svc_env.upload.submit(d.upload_id, "An")
    res = svc_env.snapshots.write(f"upload:{d.upload_id}", "An", lambda s: svc_env.upload.apply_to(s, d.upload_id))
    store = svc_env.snapshots.store(res.snapshot.snapshot_id)
    assert store.document(KEY_UPLOADED).raw_checksum == d.checksum
    assert [r.target_key for r in store.relations(KEY_UPLOADED)] == [LAND]


def test_apply_is_stale_when_store_changed(svc_env):
    d = walk_to_step3(svc_env, _file(svc_env, "99.txt", UPLOADED_V2), replace=True)
    d = svc_env.upload.submit(d.upload_id, "An")
    svc_env.snapshots.write("upload:other", "B", lambda s: replace_text_in_store(s, KEY_UPLOADED, "v3"))
    before = svc_env.snapshots.current().snapshot_id
    with pytest.raises(StaleDraftError):
        svc_env.snapshots.write(f"upload:{d.upload_id}", "An", lambda s: svc_env.upload.apply_to(s, d.upload_id))
    assert svc_env.snapshots.current().snapshot_id == before


def test_apply_is_stale_when_same_number_appeared(svc_env):
    d = svc_env.upload.submit(walk_to_step3(svc_env, TXT_43).upload_id, "An")
    svc_env.snapshots.write("crawler", "B", lambda s: s.store.upsert_document(
        _doc(AMEND, "43/2024/QH15", "Luật 43", date(2024, 6, 29), *write_text(
            s.store.path.parents[2] / "raw", AMEND, "Điều 1. X\nLuật này có hiệu lực thi hành từ ngày 01 tháng 8 năm 2024."))))
    with pytest.raises(StaleDraftError, match="Kho đã thay đổi"):
        svc_env.snapshots.write(f"upload:{d.upload_id}", "An", lambda s: svc_env.upload.apply_to(s, d.upload_id))


def test_apply_replace_keeps_rejected_relation(svc_env):
    from rag.legal.models import DocumentRelation

    def seed(s):
        text = TXT_43.read_text(encoding="utf-8").replace("Luật này có hiệu lực", "Luật này có hiệu  lực")
        path, checksum = write_text(s.store.path.parents[2] / "raw", AMEND, text)
        s.store.upsert_document(_doc(AMEND, "43/2024/QH15", "Luật sửa đổi 43", date(2024, 6, 29), path, checksum,
                                     text_source="file"))
        s.store.add_relation(DocumentRelation(AMEND, LAND, "SUA_DOI_BO_SUNG", "người duyệt: sai", "rejected"))
    svc_env.snapshots.write("seed", "B", seed)
    d = walk_to_step3(svc_env, TXT_43, replace=True)
    d = svc_env.upload.submit(d.upload_id, "An")
    res = svc_env.snapshots.write(f"upload:{d.upload_id}", "An", lambda s: svc_env.upload.apply_to(s, d.upload_id))
    rels = {(r.target_key, r.relation): r for r in svc_env.snapshots.store(res.snapshot.snapshot_id).relations(AMEND)}
    assert (rels[(LAND, "SUA_DOI_BO_SUNG")].status, rels[(LAND, "SUA_DOI_BO_SUNG")].evidence) == \
        ("rejected", "người duyệt: sai")
    assert rels[(HOUSING, "SUA_DOI_BO_SUNG")].status == "confirmed"          # quan hệ mới vẫn được thêm


def test_apply_rechecks_source_rule(svc_env):
    d = walk_to_step3(svc_env, _file(svc_env, "99.txt", UPLOADED_V2), replace=True)
    d = svc_env.upload.submit(d.upload_id, "An")
    # crawler nạp lại cùng text (cùng checksum) nhưng giờ là nguồn vbpl: file không được thay text vbpl
    svc_env.snapshots.write("crawler", "B", lambda s: s.store.upsert_document(
        replace(s.store.document(KEY_UPLOADED), text_source="vbpl")))
    with pytest.raises(StepError, match="vbpl") as exc:
        svc_env.snapshots.write(f"upload:{d.upload_id}", "An", lambda s: svc_env.upload.apply_to(s, d.upload_id))
    assert not isinstance(exc.value, StaleDraftError)


def test_relookup_rechecks_duplicate_when_key_changes(svc_env):
    d = svc_env.upload.create_from_url("https://vbpl.vn/van-ban/chi-tiet/171234")
    d = svc_env.upload.confirm_text(d.upload_id, "An")
    svc_env.client.details["171234"] = {**DETAIL_43, "docNum": "99/2024/QH15"}
    d = svc_env.upload.relookup_vbpl(d.upload_id)
    assert d.duplicate and d.duplicate["document_key"] == KEY_UPLOADED
    assert d.state == "step1" and d.confirmations == {} and d.duplicate["replace_allowed"] is True


def test_apply_requires_queued(svc_env):
    d = walk_to_step3(svc_env, TXT_43)
    with pytest.raises(StepError):
        svc_env.snapshots.write("x", "An", lambda s: svc_env.upload.apply_to(s, d.upload_id))


# --- bản nháp ---------------------------------------------------------------------------------------


def test_drafts_survive_restart(tmp_path, svc_env):
    d = svc_env.upload.create_from_file(TXT_43, "43.txt")
    loaded = DraftStore(svc_env.drafts_root).load(d.upload_id)
    assert loaded.text == d.text and loaded == d


U1, U2, U3 = "u20261110090000-aaaaa1", "u20261110090000-aaaaa2", "u20261110090000-aaaaa3"


def test_draft_store_list_and_mark_interrupted(tmp_path):
    store = DraftStore(tmp_path)
    base = Draft(U1, NOW, "queued", "file", "a.txt", "t", "c", [], {}, {}, False, "s1", None)
    store.save(base)
    store.save(replace(base, upload_id=U2, created_at=NOW.replace(hour=10), state="building"))
    store.save(replace(base, upload_id=U3, created_at=NOW.replace(hour=8), state="step1"))
    assert [d.upload_id for d in store.list()] == [U2, U1, U3]
    assert sorted(store.mark_interrupted()) == [U1, U2]
    assert store.load(U1).state == "failed" and store.load(U1).error == "server khởi động lại giữa chừng"
    assert store.load(U3).state == "step1"
    with pytest.raises(KeyError):
        store.load("u20261110090000-bbbbbb")


@pytest.mark.parametrize("bad", ["C:foo", "..\\x", "../x", "..", "", "u1", "u20261110090000-AAAAAA",
                                 "u20261110090000-aaaaaa/../x", "C:\\Windows", "u20261110090000-aaaaaa\n"])
def test_draft_store_rejects_ids_outside_format(tmp_path, bad):
    store = DraftStore(tmp_path / "uploads")
    with pytest.raises(KeyError):
        store.load(bad)
    with pytest.raises(KeyError):
        store.save(Draft(bad, NOW, "step1", "file", "a.txt", "t", "c", [], {}, {}, False, "s1", None))
    with pytest.raises(KeyError):
        store.save_original(bad, TXT_43, ".txt")
    assert list(tmp_path.iterdir()) == [tmp_path / "uploads"]


def test_generated_ids_match_store_format(svc_env):
    d = svc_env.upload.create_from_file(TXT_43, "43.txt")
    assert DraftStore(svc_env.drafts_root).folder(d.upload_id).parent == svc_env.drafts_root


def test_cancel(svc_env):
    d = svc_env.upload.create_from_file(TXT_43, "43.txt")
    assert svc_env.upload.cancel(d.upload_id).state == "cancelled"
    with pytest.raises(StepError):
        svc_env.upload.cancel(d.upload_id)
    with pytest.raises(StepError):
        svc_env.upload.confirm_text(d.upload_id, "An")
