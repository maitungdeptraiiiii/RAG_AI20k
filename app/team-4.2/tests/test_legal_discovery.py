from datetime import datetime, timezone
from pathlib import Path

import pytest

from rag.legal.crawl import fetch_document
from rag.legal.discovery import Seed, discover, load_seeds
from rag.legal.store import LegalStore

FIXTURES = Path(__file__).parent / "fixtures" / "legal"
NOW = lambda: datetime(2026, 11, 9, tzinfo=timezone.utc)  # noqa: E731


def html(text: str) -> str:
    return "".join(f"<p>{line}</p>" for line in text.split("\n"))


class FakeClient:
    def __init__(self, docs):
        self.docs = {d["id"]: d for d in docs}

    def _item(self, d):
        return {k: d[k] for k in ("id", "title", "docNum", "issueDate", "effFrom")} | {"docType": d["docType"]["name"],
                                                                                      "effStatus": d["effStatus"]["name"]}

    def iter_list(self, *, keyword=None, **_):
        for d in self.docs.values():
            yield self._item(d)

    def list_page(self, page, size=50, **kw):
        items = list(self.iter_list(**kw))
        return {"items": items[(page - 1) * size: page * size], "total": len(items)}

    def search_by_number(self, number):
        return [self._item(d) for d in self.docs.values() if d["docNum"] == number]

    def detail(self, doc_id):
        return self.docs[doc_id]


def vb(doc_id, doc_type, number, title, issued, text, status="Còn hiệu lực"):
    return {"id": doc_id, "docType": {"name": doc_type}, "docNum": number, "title": title,
            "issueDate": f"{issued}T00:00:00", "effFrom": f"{issued}T00:00:00", "effTo": None,
            "effStatus": {"name": status}, "agencyName": "Quốc hội", "isConsolidatedDocument": "VBHN" in number,
            "documentContent": {"content": html(text)}}


ENTERPRISE = vb("1", "Luật", "59/2020/QH14", "Luật Doanh nghiệp số 59/2020/QH14", "2020-06-17",
                (FIXTURES / "luat_59_2020_QH14.txt").read_text(encoding="utf-8"), "Hết hiệu lực một phần")
AMEND = vb("2", "Luật", "03/2022/QH15", "Luật sửa đổi, bổ sung một số điều của Luật Đầu tư công, ..., Luật Doanh nghiệp "
           "số 03/2022/QH15", "2022-01-11", (FIXTURES / "luat_03_2022_QH15.txt").read_text(encoding="utf-8"))
FAKE_AMEND = vb("3", "Luật", "99/2023/QH15", "Luật sửa đổi, bổ sung Luật Doanh nghiệp và Luật Khác số 99/2023/QH15",
                "2023-05-01", "Điều 1. Sửa đổi, bổ sung một số điều của Luật Khác\n1. Sửa đổi khoản 1 Điều 2 như sau:\n"
                '"1. X.”.\nĐiều 2. Hiệu lực thi hành\nLuật này có hiệu lực thi hành từ ngày 01 tháng 7 năm 2023.')


def test_number_collision_filtered_by_type(tmp_path):
    resolution = vb("10", "Nghị quyết", "91/2015/QH13", "Nghị quyết số 91/2015/QH13", "2015-06-18", "Điều 1. X\nNội dung.")
    code = vb("11", "Bộ luật", "91/2015/QH13", "Bộ luật Dân sự số 91/2015/QH13", "2015-11-24", "Điều 1. Phạm vi\nNội dung.")
    doc, text = fetch_document(FakeClient([resolution, code]), "Bộ luật", "91/2015/QH13", tmp_path, now=NOW)
    assert doc.document_key == "bo-luat:91/2015/QH13" and "Phạm vi" in text
    assert Path(doc.raw_text_path).read_text(encoding="utf-8").startswith("Điều 1. Phạm vi")
    assert fetch_document(FakeClient([resolution]), "Bộ luật", "91/2015/QH13", tmp_path, now=NOW) is None


def test_saved_text_matches_checksum_and_is_never_overwritten(tmp_path):
    import hashlib

    from rag.legal.crawl import save_detail
    from rag.legal.snapshots import SnapshotManager

    old, _ = save_detail(ENTERPRISE, tmp_path / "raw", now=NOW)
    new, _ = save_detail({**ENTERPRISE, "documentContent": {"content": html("Điều 1. Khác\nNội dung.")}},
                         tmp_path / "raw", now=NOW)
    for doc in (old, new):
        assert hashlib.sha256(Path(doc.raw_text_path).read_bytes()).hexdigest() == doc.raw_checksum
    assert old.raw_text_path != new.raw_text_path                    # bản cũ (snapshot cũ) vẫn nguyên
    snaps = SnapshotManager(tmp_path / "legal")
    res = snaps.write("cli:crawl", "t", lambda svc: svc.store.upsert_document(
        save_detail(ENTERPRISE, snaps.legal_dir / "raw", now=NOW)[0]))   # validate: checksum file khớp
    assert res.snapshot.status == "published"


def test_amendment_confirmed_by_content(tmp_path):
    store = LegalStore(tmp_path / "c.sqlite")
    report = discover(FakeClient([ENTERPRISE, AMEND, FAKE_AMEND]), store, [Seed("Luật", "59/2020/QH14")],
                      tmp_path / "raw", now=NOW)
    assert ("luat:03/2022/QH15", "SUA_DOI_BO_SUNG") in [(k, r) for k, r, _ in report.added]
    assert any(t.startswith("Luật sửa đổi, bổ sung Luật Doanh nghiệp và Luật Khác") and r == "discovery.not_confirmed_by_content"
               for t, r in report.rejected)
    assert store.document("luat:99/2023/QH15") is None
    rel = store.relations("luat:59/2020/QH14")[0]
    assert (rel.source_key, rel.target_key, rel.status) == ("luat:03/2022/QH15", "luat:59/2020/QH14", "confirmed")
    assert "luat:59/2020/QH14" in store.document("luat:03/2022/QH15").discovered_via
    assert report.suspicious == []


def test_replacement_found_from_repeal_clause(tmp_path):
    new = vb("20", "Luật", "27/2023/QH15", "Luật Nhà ở số 27/2023/QH15", "2023-11-27",
             "Điều 1. Phạm vi\nNội dung.\nĐiều 198. Hiệu lực thi hành\n1. Luật này có hiệu lực thi hành từ ngày 01 tháng 01 năm 2025.\n"
             "2. Luật Nhà ở số 65/2014/QH13 hết hiệu lực kể từ ngày Luật này có hiệu lực thi hành.")
    old = vb("21", "Luật", "65/2014/QH13", "Luật Nhà ở số 65/2014/QH13", "2014-11-25", "Điều 1. Phạm vi\nCũ.",
             "Hết hiệu lực toàn bộ")
    store = LegalStore(tmp_path / "c.sqlite")
    report = discover(FakeClient([new, old]), store, [Seed("Luật", "27/2023/QH15")], tmp_path / "raw", now=NOW)
    assert ("luat:65/2014/QH13", "THAY_THE") in [(k, r) for k, r, _ in report.added]
    rel = [r for r in store.relations("luat:65/2014/QH13") if r.relation == "THAY_THE"][0]
    assert (rel.source_key, rel.target_key) == ("luat:27/2023/QH15", "luat:65/2014/QH13")


def _chain(n):
    """A <- B <- C <- D: B sửa Luật Mẫu (theo tên); C, D sửa văn bản liền trước theo số hiệu (như văn bản thật)."""
    docs = [vb("100", "Luật", "1/2020/QH14", "Luật Mẫu số 1/2020/QH14", "2020-01-01", "Điều 1. A\n1. Khoản một.")]
    prev_ref, prev_num = "Luật Mẫu", "1/2020/QH14"
    for i in range(1, n):
        num = f"{i + 1}/202{i}/QH15"
        text = (f"Điều 1. Sửa đổi, bổ sung một số điều của {prev_ref}\n1. Sửa đổi, bổ sung khoản 1 Điều 1 như sau:\n"
                f'"1. Bản {i}.”.\nĐiều 2. Hiệu lực thi hành\nLuật này có hiệu lực thi hành từ ngày 01 tháng 01 năm 202{i + 1}.')
        docs.append(vb(str(100 + i), "Luật", num, f"Luật sửa đổi, bổ sung một số điều của {prev_ref} số {num}",
                       f"202{i}-06-01", text))
        prev_ref, prev_num = f"Luật số {num}", num
    return docs


def test_depth_limit(tmp_path):
    store = LegalStore(tmp_path / "c.sqlite")
    report = discover(FakeClient(_chain(4)), store, [Seed("Luật", "1/2020/QH14")], tmp_path / "raw", max_depth=2, now=NOW)
    keys = [k for k, _, _ in report.added]
    assert "luat:2/2021/QH15" in keys and "luat:3/2022/QH15" in keys
    assert "luat:4/2023/QH15" not in keys


def test_suspicious_partial_status(tmp_path):
    store = LegalStore(tmp_path / "c.sqlite")
    report = discover(FakeClient([ENTERPRISE]), store, [Seed("Luật", "59/2020/QH14")], tmp_path / "raw", now=NOW)
    assert report.suspicious == ["luat:59/2020/QH14"]


def test_seeds_file_valid():
    seeds = load_seeds(Path(__file__).parents[3] / "data" / "team-4.2" / "legal" / "seeds.yaml")
    assert seeds == [Seed("Luật", "31/2024/QH15"), Seed("Luật", "27/2023/QH15"), Seed("Luật", "29/2023/QH15"),
                     Seed("Bộ luật", "91/2015/QH13"), Seed("Bộ luật", "95/2015/QH13"),
                     Seed("Bộ luật", "100/2015/QH13"), Seed("Bộ luật", "45/2019/QH14"),
                     Seed("Bộ luật", "92/2015/QH13"), Seed("Bộ luật", "101/2015/QH13"),
                     # hợp đồng lao động: tầng 1 (nguồn rule, gồm bản cũ để áp theo ngày ký) + tầng 2 (tra cứu)
                     Seed("Nghị định", "145/2020/NĐ-CP"), Seed("Thông tư", "10/2020/TT-BLĐTBXH"),
                     Seed("Nghị định", "293/2025/NĐ-CP"), Seed("Nghị định", "74/2024/NĐ-CP"),
                     Seed("Nghị định", "38/2022/NĐ-CP"), Seed("Luật", "41/2024/QH15"), Seed("Luật", "58/2014/QH13"),
                     Seed("Nghị định", "158/2025/NĐ-CP"), Seed("Nghị định", "115/2015/NĐ-CP"),
                     Seed("Nghị định", "12/2022/NĐ-CP"), Seed("Nghị định", "283/2026/NĐ-CP"),
                     Seed("Luật", "74/2025/QH15"), Seed("Luật", "25/2008/QH12"),
                     Seed("Luật", "51/2024/QH15"), Seed("Luật", "84/2015/QH13"),
                     Seed("Nghị định", "337/2025/NĐ-CP"), Seed("Thông tư", "08/2026/TT-BNV")]


def test_subordinate_documents_cannot_amend_a_law(tmp_path):
    decree = vb("30", "Nghị định", "10/2023/NĐ-CP", "Nghị định sửa đổi, bổ sung một số điều liên quan Luật Doanh nghiệp "
                "số 10/2023/NĐ-CP", "2023-04-03", (FIXTURES / "luat_03_2022_QH15.txt").read_text(encoding="utf-8"))
    ministry_vbhn = vb("31", "Văn bản hợp nhất", "21/VBHN-BXD", "Văn bản hợp nhất Quy định chi tiết Luật Doanh nghiệp",
                       "2024-01-01", "Nghị định số 59/2020/QH14\nĐiều 1. X")
    store = LegalStore(tmp_path / "c.sqlite")
    report = discover(FakeClient([ENTERPRISE, decree, ministry_vbhn]), store, [Seed("Luật", "59/2020/QH14")],
                      tmp_path / "raw", now=NOW)
    assert report.added == []
    assert store.document("nghi-dinh:10/2023/NĐ-CP") is None and store.document("vbhn:21/VBHN-BXD") is None
    reasons = {t: r for t, r in report.rejected}
    assert reasons[decree["title"]] == "discovery.subordinate_document"


NEW_HOUSING = vb("40", "Luật", "27/2023/QH15", "Luật Nhà ở số 27/2023/QH15", "2023-11-27",
                 "Điều 1. Phạm vi\nNội dung.\nĐiều 198. Hiệu lực thi hành\n"
                 "1. Luật này có hiệu lực thi hành từ ngày 01 tháng 8 năm 2024.\n"
                 "2. Luật Nhà ở số 65/2014/QH13 đã được sửa đổi, bổ sung một số điều theo Luật số 61/2020/QH14 và "
                 "Luật số 62/2020/QH14 hết hiệu lực kể từ ngày Luật này có hiệu lực thi hành.")
OLD_HOUSING = vb("41", "Luật", "65/2014/QH13", "Luật Nhà ở số 65/2014/QH13", "2014-11-25",
                 "Điều 23. Điều kiện\n1. Khoản một.", "Hết hiệu lực toàn bộ")
# Luật Đầu tư 2020: sửa Luật Nhà ở ở một Điều cuối, tiêu đề cả văn bản không nhắc Luật Nhà ở
INVESTMENT = vb("42", "Luật", "61/2020/QH14", "Luật Đầu tư số 61/2020/QH14", "2020-06-17",
                "Điều 1. Phạm vi\nNội dung.\nĐiều 75. Sửa đổi, bổ sung một số điều của Luật Nhà ở\n"
                "1. Sửa đổi, bổ sung khoản 1 Điều 23 như sau:\n\"1. Khoản một mới.\".\n"
                "Điều 77. Hiệu lực thi hành\nLuật này có hiệu lực thi hành từ ngày 01 tháng 01 năm 2021.")
CONSTRUCTION = vb("43", "Luật", "62/2020/QH14", "Luật sửa đổi, bổ sung một số điều của Luật Xây dựng số 62/2020/QH14",
                  "2020-06-17", "Điều 1. Sửa đổi, bổ sung một số điều của Luật Xây dựng\n1. Sửa đổi khoản 1 Điều 3 như sau:\n"
                  "\"1. X.\".\nĐiều 3. Hiệu lực thi hành\nLuật này có hiệu lực thi hành từ ngày 01 tháng 01 năm 2021.")


def test_known_amenders_are_fetched_and_confirmed_by_content(tmp_path):
    store = LegalStore(tmp_path / "c.sqlite")
    report = discover(FakeClient([NEW_HOUSING, OLD_HOUSING, INVESTMENT, CONSTRUCTION]), store,
                      [Seed("Luật", "27/2023/QH15")], tmp_path / "raw", now=NOW)
    added = [(k, r) for k, r, _ in report.added]
    assert ("luat:61/2020/QH14", "SUA_DOI_BO_SUNG") in added       # sửa đổi nằm trong luật khác
    rel = next(r for r in store.relations("luat:65/2014/QH13") if r.source_key == "luat:61/2020/QH14")
    assert (rel.relation, rel.status) == ("SUA_DOI_BO_SUNG", "confirmed") and "Điều 75" in rel.evidence
    # 62/2020 được nêu là đã sửa Luật Nhà ở nhưng nội dung không có chỉ dẫn nào cho Luật Nhà ở
    assert store.document("luat:62/2020/QH14") is None
    assert any(r == "discovery.amender_without_directives" for _, r in report.rejected)


def test_amender_number_shared_by_law_and_resolution_tries_every_type(tmp_path):
    # "đã được sửa đổi ... theo Nghị quyết số 19/2008/QH12": Luật Sĩ quan cũng mang số 19/2008/QH12
    new = vb("60", "Luật", "27/2023/QH15", "Luật Nhà ở số 27/2023/QH15", "2023-11-27",
             "Điều 1. Phạm vi\nNội dung.\nĐiều 198. Hiệu lực thi hành\n1. Luật này có hiệu lực thi hành từ ngày 01 tháng 8 năm 2024.\n"
             "2. Luật Nhà ở số 65/2014/QH13 đã được sửa đổi, bổ sung một số điều theo Nghị quyết số 19/2008/QH12 "
             "hết hiệu lực kể từ ngày Luật này có hiệu lực thi hành.")
    officers = vb("61", "Luật", "19/2008/QH12", "Luật Sửa đổi, bổ sung một số điều của Luật Sĩ quan số 19/2008/QH12",
                  "2008-06-03", "Điều 1. Sửa đổi, bổ sung một số điều của Luật Sĩ quan\n1. Sửa đổi khoản 1 Điều 2 như sau:\n\"1. X.\".")
    resolution = vb("62", "Nghị quyết", "19/2008/QH12", "Nghị quyết số 19/2008/QH12 sửa đổi Luật Nhà ở", "2008-06-03",
                    "Điều 1. Sửa đổi, bổ sung một số điều của Luật Nhà ở\n1. Sửa đổi, bổ sung khoản 1 Điều 23 như sau:\n"
                    "\"1. Khoản thí điểm.\".\nĐiều 2. Hiệu lực thi hành\nNghị quyết này có hiệu lực thi hành từ ngày 01 tháng 01 năm 2009.")
    store = LegalStore(tmp_path / "c.sqlite")
    report = discover(FakeClient([new, OLD_HOUSING, officers, resolution]), store, [Seed("Luật", "27/2023/QH15")],
                      tmp_path / "raw", now=NOW)
    assert ("nghi-quyet:19/2008/QH12", "SUA_DOI_BO_SUNG") in [(k, r) for k, r, _ in report.added]
    assert store.document("luat:19/2008/QH12") is None


def test_partial_repeal_is_not_recorded_as_replacement(tmp_path):
    new = vb("50", "Luật", "9/2026/QH16", "Luật Khác số 9/2026/QH16", "2026-01-01",
             "Điều 1. A\nNội dung.\nĐiều 9. Hiệu lực thi hành\n1. Luật này có hiệu lực thi hành từ ngày 01 tháng 7 năm 2026.\n"
             "2. Khoản 1 Điều 23 của Luật Nhà ở số 65/2014/QH13 hết hiệu lực kể từ ngày Luật này có hiệu lực thi hành.")
    store = LegalStore(tmp_path / "c.sqlite")
    report = discover(FakeClient([new, OLD_HOUSING]), store, [Seed("Luật", "9/2026/QH16")], tmp_path / "raw", now=NOW)
    rels = [(r.source_key, r.target_key, r.relation) for r in store.relations("luat:65/2014/QH13")]
    assert rels == [("luat:9/2026/QH16", "luat:65/2014/QH13", "BAI_BO")]
    assert ("luat:65/2014/QH13", "THAY_THE") not in [(k, r) for k, r, _ in report.added]
