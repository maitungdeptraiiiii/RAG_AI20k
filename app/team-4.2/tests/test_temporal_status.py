from datetime import date, datetime, timezone
from pathlib import Path

from rag.legal.keys import document_key
from rag.legal.models import BuildRun, LegalDocument, ProvisionVersion
from rag.legal.store import LegalStore
from rag.legal.structure import parse_structure
from rag.temporal.status import (LegacyLaw, is_amendment_only, legacy_duplicates, legacy_status, load_legacy_map,
                                 versioned_status)

ROOT = Path(__file__).resolve().parents[3]
FIX = Path(__file__).parent / "fixtures" / "legal"
NOW = datetime(2026, 11, 9, tzinfo=timezone.utc)


def doc(doc_type, number, title, consolidated=False):
    return LegalDocument(document_key(doc_type, number), "1", title, doc_type, number, "Quốc hội", date(2015, 11, 24),
                         None, None, None, consolidated, "x.txt", "0" * 64, NOW)


def ver(key, pid, start, end, status="verified", reasons=()):
    return ProvisionVersion(f"{key}#{pid}", key, "article", "t", start, end, status, reasons, (), (), "b")


def test_legacy_map_loads_six_codes():
    m = load_legacy_map(ROOT / "data" / "team-4.2" / "legal" / "legacy_map.yaml")
    assert len(m) == 6
    assert m["bo_luat_dan_su_2015.txt"] == LegacyLaw("bo_luat_dan_su_2015.txt", "Bộ luật", "91/2015/QH13", "Quốc hội")
    assert m["bo_luat_lao_dong_2019.txt"].doc_number == "45/2019/QH14"


def test_duplicate_by_number_type_issuer(tmp_path):
    store = LegalStore(tmp_path / "c.sqlite")
    store.upsert_document(doc("Nghị quyết", "91/2015/QH13", "Nghị quyết số 91/2015/QH13"))
    legacy = {"bo_luat_dan_su_2015.txt": LegacyLaw("bo_luat_dan_su_2015.txt", "Bộ luật", "91/2015/QH13", "Quốc hội")}
    assert legacy_duplicates(store, legacy) == set()
    store.upsert_document(doc("Bộ luật", "91/2015/QH13", "Bộ luật Dân sự số 91/2015/QH13"))
    assert legacy_duplicates(store, legacy) == {"bo_luat_dan_su_2015.txt"}


def test_versioned_status_levels():
    k = "luat:1/2020/QH14"
    assert versioned_status([]) == "outdated"
    assert versioned_status([ver(k, "d1", date(2021, 1, 1), None)]) == "verified"
    assert versioned_status([ver(k, "d1", date(2021, 1, 1), None), ver(k, "d2", date(2021, 1, 1), None, "needs_review")]) \
        == "partially_verified"
    assert versioned_status([ver(k, "d1", date(1900, 1, 1), None, "needs_review", ("effectivity.unresolved",))]) == "unknown"


def test_is_amendment_only_real():
    for name, key, expected in [("realestate/luat_43_2024_QH15.txt", "luat:43/2024/QH15", True),
                                ("luat_59_2020_QH14.txt", "luat:59/2020/QH14", False),
                                ("luat_03_2022_QH15.txt", "luat:03/2022/QH15", True)]:
        assert is_amendment_only(parse_structure((FIX / name).read_text(encoding="utf-8"), key)) is expected, name


def test_legacy_status(tmp_path):
    store = LegalStore(tmp_path / "c.sqlite")
    code = doc("Bộ luật", "91/2015/QH13", "Bộ luật Dân sự số 91/2015/QH13")
    store.upsert_document(code)
    store.save_build(BuildRun("b", code.document_key, (), "c", NOW, "v"),
                     [ver(code.document_key, "d1", date(2017, 1, 1), None)])
    blds = LegacyLaw("bo_luat_dan_su_2015.txt", "Bộ luật", "91/2015/QH13", "Quốc hội")
    labour = LegacyLaw("bo_luat_lao_dong_2019.txt", "Bộ luật", "45/2019/QH14", "Quốc hội")
    assert legacy_status(store, blds, start=date(2010, 1, 1), end=date(2010, 12, 31)) == "outdated"
    assert legacy_status(store, labour, start=date(2022, 1, 1), end=date(2022, 1, 1)) == "unversioned"
    assert legacy_status(store, None, start=date(2022, 1, 1), end=date(2022, 1, 1)) == "unknown"
