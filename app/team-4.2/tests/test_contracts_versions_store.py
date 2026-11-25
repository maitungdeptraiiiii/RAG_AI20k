"""Lineage phiên bản được lưu và liệt kê theo họ."""
from datetime import datetime, timezone

from rag.contracts.models import Contract, family_id, version_of
from rag.contracts.store import ContractStore


def _contract(cid, persist=True, lineage=None):
    return Contract(cid, "x.txt", persist, datetime.now(timezone.utc), "t", [], 0, lineage=lineage or {})


def test_lineage_round_trip_and_family(tmp_path):
    root_id, v2_id, draft_id, member_id = "a" * 24, "b" * 24, "c" * 24, "d" * 24
    s = ContractStore(tmp_path)
    root = _contract(root_id)
    v2 = _contract(v2_id, lineage={"family_id": root_id, "version": 2, "parent_id": root_id, "status": "ready"})
    draft = _contract(draft_id, False, {"family_id": root_id, "version": 3, "status": "draft"})
    member = _contract(member_id, lineage={"family_id": root_id, "status": "member"})
    for c in (v2, root, draft, member):
        s.add(c, original=b"x", suffix=".txt")
    (tmp_path / ("e" * 24)).mkdir()
    (tmp_path / ("e" * 24) / "contract.json").write_text("{hỏng", encoding="utf-8")
    fresh = ContractStore(tmp_path)
    assert [c.contract_id for c in fresh.family(root_id)] == [root_id, v2_id]
    assert fresh.get(v2_id).lineage == v2.lineage
    assert version_of(fresh.get(root_id)) == 1 and family_id(fresh.get(root_id)) == root_id


def test_family_includes_unsaved_ready_versions(tmp_path):
    s = ContractStore(tmp_path)
    s.add(_contract("a" * 24, False), original=b"x", suffix=".txt")
    s.add(_contract("b" * 24, False, {"family_id": "a" * 24, "version": 2, "status": "ready"}), original=b"x", suffix=".txt")
    assert [version_of(c) for c in s.family("a" * 24)] == [1, 2]
