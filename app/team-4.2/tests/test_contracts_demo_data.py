"""Dữ liệu demo phần 4: nạp nhóm luật bất động sản vào kho có phiên bản + hợp đồng thuê nhà mẫu."""

import importlib.util
from pathlib import Path

from rag.ingest.loaders import load_source
from rag.legal.snapshots import SnapshotManager

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = Path(__file__).parent / "fixtures" / "legal" / "realestate"
DEMO = ROOT / "data" / "team-4.2" / "contracts_demo"


def _seed_module():
    spec = importlib.util.spec_from_file_location("seed_legal_demo", ROOT / "scripts" / "team-4.2" / "seed_legal_demo.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_seed_publishes_real_estate_laws_and_is_idempotent(tmp_path):
    seed = _seed_module().seed
    first = seed(tmp_path, FIXTURES)
    mgr = SnapshotManager(tmp_path)
    keys = {d.document_key for d in mgr.store().documents()}
    assert {"luat:65/2014/QH13", "luat:27/2023/QH15"} <= keys
    assert mgr.current().snapshot_id == first
    assert mgr.store().latest_build("luat:65/2014/QH13") is not None
    n = len(mgr.list())
    assert seed(tmp_path, FIXTURES) == first          # lần 2: không có gì mới -> không tạo snapshot
    assert len(mgr.list()) == n


def test_demo_contract_files_are_readable():
    for name in ("hop_dong_thue_nha_2023.txt", "hop_dong_thue_nha_2023.docx"):
        pages = load_source(DEMO / name)
        text = "\n".join(p.text for p in pages)
        assert "HỢP ĐỒNG THUÊ NHÀ" in text and "Điều 12" in text
        assert "15 tháng 3 năm 2023" in text
