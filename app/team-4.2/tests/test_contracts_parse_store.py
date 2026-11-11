from datetime import datetime, timezone
from pathlib import Path

import pytest

from rag.contracts.models import Contract
from rag.contracts.parse import limit_units, split_units
from rag.contracts.store import ContractStore

DEMO = Path(__file__).resolve().parents[3] / "data" / "team-4.2" / "contracts_demo" / "hop_dong_thue_nha_2023.txt"


def test_demo_contract_splits_into_preamble_and_12_articles():
    units = split_units(DEMO.read_text(encoding="utf-8"))
    assert units[0].label == "Phần mở đầu" and "BÊN CHO THUÊ" in units[0].text
    articles = [u for u in units if u.label.startswith("Điều ")]
    assert [u.label for u in articles] == [f"Điều {i}" for i in range(1, 13)]
    assert articles[8].text.startswith("Điều 9. Đơn phương chấm dứt") and "khoản 1 Điều này" in articles[8].text
    assert len({u.uid for u in units}) == len(units)


def test_unnumbered_contract_splits_by_paragraph():
    units = split_units("Bên A bán cho Bên B một xe máy.\n\nGiá bán là 20 triệu đồng.\n\nHai bên cam kết thực hiện.")
    assert [u.label for u in units] == ["Đoạn 1", "Đoạn 2", "Đoạn 3"]


def test_numbered_sections_without_dieu():
    units = split_units("HỢP ĐỒNG\n1. Đối tượng\nBên A giao hàng.\n2. Giá\nMột triệu đồng.")
    assert [u.label for u in units] == ["Phần mở đầu", "Mục 1", "Mục 2"]


def test_limit_units_keeps_demo_maximum():
    units = split_units("\n".join(f"Điều {i}. Nội dung {i}" for i in range(1, 41)))
    kept, total = limit_units(units, 30)
    assert len(kept) == 30 and total == 40


def _contract(cid="c1", persist=False):
    return Contract(cid, "hd.txt", persist, datetime(2026, 11, 11, tzinfo=timezone.utc), "Điều 1. A", split_units("Điều 1. A"), 1)


def test_session_contract_is_memory_only(tmp_path):
    store = ContractStore(tmp_path)
    store.add(_contract(), original=b"Dieu 1", suffix=".txt")
    assert store.get("c1").filename == "hd.txt"
    assert not any(tmp_path.iterdir())


def test_saved_contract_survives_new_store_and_delete_removes_it(tmp_path):
    store = ContractStore(tmp_path)
    c = _contract()
    c.party = "Bên thuê"
    store.add(c, original=b"Dieu 1", suffix=".txt")
    store.save("c1")
    again = ContractStore(tmp_path).get("c1")
    assert again.persist and again.party == "Bên thuê" and again.units[0].label == "Điều 1"
    assert (tmp_path / "c1" / "original.txt").read_bytes() == b"Dieu 1"
    store.delete("c1")
    assert not (tmp_path / "c1").exists()
    with pytest.raises(KeyError):
        ContractStore(tmp_path).get("c1")


@pytest.mark.parametrize("bad", ["../x", "C:foo", "", "a/b"])
def test_invalid_ids_are_rejected(tmp_path, bad):
    with pytest.raises(KeyError):
        ContractStore(tmp_path).get(bad)
