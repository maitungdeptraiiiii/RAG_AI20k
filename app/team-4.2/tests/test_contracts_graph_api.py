"""Phần 4 + đồ thị hợp đồng: tách mới, nhật ký thao tác, bản dựng, bố cục, hợp đồng định dạng cũ."""
import json
import sys
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from rag.contracts.graph.neo4j_store import GraphUnavailable
from rag.contracts.graph.service import ContractGraphService
from rag.contracts.store import ContractStore

UI = Path(__file__).resolve().parents[1] / "ui"
if str(UI) not in sys.path:
    sys.path.insert(0, str(UI))
import contracts_api  # noqa: E402

LIMIT_MSG = "Hợp đồng dài hơn 150 trang — chưa hỗ trợ"


class FakeStore:
    def __init__(self, fail=False):
        self.published, self.fail = [], fail

    def publish(self, build):
        if self.fail:
            raise GraphUnavailable("Không kết nối được Neo4j")
        self.published.append(build)


class SimpleLLM:
    """facts: loại + ngày ký; find: không có phát hiện. Ghi số đơn vị mỗi lượt nhận (SEEN)."""

    SEEN: dict[str, int] = {}

    def complete(self, system, user):
        stage = system.split("\n", 1)[0].removeprefix("BƯỚC:").strip() if system.startswith("BƯỚC:") else "facts"
        SimpleLLM.SEEN[stage] = len(json.loads(user).get("units") or [])
        if stage == "summary":
            return json.dumps({"sections": [{"title": "Giá", "items": [{"text": "Giá", "unit": "p0.d2"}]}]})
        if stage == "answer":
            return json.dumps({"answer": "Theo Điều 1.", "legal_conclusion": False, "law_ids": [], "units": []})
        if stage == "facts":
            return json.dumps({"type": "Hợp đồng dịch vụ", "parties": [],
                               "sign_date": {"value": "2023-03-15", "unit": "p0.d1",
                                             "quote": "ngày 15 tháng 3 năm 2023"}}, ensure_ascii=False)
        if stage == "find":
            return json.dumps({"findings": []})
        raise AssertionError(stage)


def contract_text(n: int) -> str:
    arts = [f"Điều {i}. Nội dung số {i}\nCác bên thực hiện nghĩa vụ thứ {i} theo hợp đồng này."
            for i in range(1, n + 1)]
    arts[0] = "Điều 1. Ký kết\nHợp đồng được ký ngày 15 tháng 3 năm 2023 tại Hà Nội."
    return "\n".join(arts) + "\n"


@pytest.fixture
def svc():
    return ContractGraphService(FakeStore())


@pytest.fixture
def client(tmp_path, svc):
    @contextmanager
    def lease():
        yield None

    contracts_api.CONFIG.root = tmp_path / "contracts"
    contracts_api.CONFIG.llm_factory = SimpleLLM
    contracts_api.CONFIG.lease = lease
    contracts_api.CONFIG.legacy_search = lambda q, k: []
    contracts_api.CONFIG.ocr_factory = lambda: None
    contracts_api.CONFIG.today = lambda: date(2026, 11, 12)
    contracts_api.CONFIG.document_source = None
    contracts_api.CONFIG.agent_baseline = None
    contracts_api.CONFIG.agent_config = None
    contracts_api.CONFIG.graph = lambda: svc
    contracts_api.reset()
    yield TestClient(Starlette(routes=contracts_api.routes))
    contracts_api.CONFIG.graph = None
    contracts_api.reset()


def upload(client, text, persist=False):
    return client.post("/api/contracts", files={"file": ("hd.txt", text.encode("utf-8"))},
                       data={"persist": "1" if persist else "0"})


def test_create_long_contract_not_cut(client):
    r = upload(client, contract_text(60))
    assert r.status_code == 200, r.text
    card = r.json()
    assert len(card["units"]) == 60 and card["coverage"] == {"reviewed": 30, "total": 60}
    assert card["graph"]["published"] is True and card["graph"]["enabled"] is True
    assert [p["part_id"] for p in card["parts"]] == ["p0"]
    assert set(card["parse_report"]) == {"counts", "gaps", "warnings"}


def test_over_150_pages_rejected(client, monkeypatch, tmp_path):
    import rag.ingest.loaders as loaders

    pages = [SimpleNamespace(text=f"Điều {i}. Nội dung", page=i) for i in range(1, 152)]
    monkeypatch.setattr(loaders, "load_source", lambda *a, **k: pages)
    r = upload(client, "x", persist=True)
    assert r.status_code == 400 and r.json()["error"] == LIMIT_MSG
    root = tmp_path / "contracts"
    assert not root.exists() or not any(root.iterdir())
    assert contracts_api.store()._mem == {}


def test_full_review_caps_llm_scope_honestly(client):
    cid = upload(client, contract_text(40)).json()["contract_id"]
    rep = client.post(f"/api/contracts/{cid}/run", json={"op": "review"}).json()
    assert rep["coverage"] == {"reviewed": 30, "total": 40}
    assert rep["warnings"] == []


def test_sign_date_by_user_is_superseding_op(client):
    cid = upload(client, contract_text(4)).json()["contract_id"]
    r = client.post(f"/api/contracts/{cid}/sign-date", json={"date": "2023-04-01", "by": "Lan"})
    assert r.status_code == 200, r.text
    c = contracts_api.get(cid)
    assert c.oplog.field("sign_date") == "2023-04-01"
    llm = [o for o in c.oplog.all() if o.target == "sign_date" and o.origin == "llm"]
    assert len(llm) == 1 and llm[0].status == "rejected"
    human = [o for o in c.oplog.all() if o.target == "sign_date" and o.origin == "human"]
    assert human[0].reviewer == "Lan" and human[0].supersedes == llm[0].op_id
    assert len(c.builds) == 2


def test_layout_endpoint_reparses(client):
    text = contract_text(4)
    cid = upload(client, text).json()["contract_id"]
    r = client.post(f"/api/contracts/{cid}/layout",
                    json={"parts": [{"start": text.index("Điều 3"), "kind": "appendix", "title": "Phụ lục"}],
                          "by": "Lan"})
    assert r.status_code == 200, r.text
    card = r.json()
    assert [p["part_id"] for p in card["parts"]] == ["p0", "p1"]
    assert card["units"][2]["label"].startswith("Phụ lục 1 — ")
    c = contracts_api.get(cid)
    layouts = [o for o in c.oplog.all() if o.op_type == "SET_LAYOUT"]
    assert [o.status for o in layouts] == ["rejected", "approved"]
    bad = client.post(f"/api/contracts/{cid}/layout", json={"parts": [{"start": 0, "kind": "appendix"}]})
    assert bad.status_code == 400 and bad.json()["error"] == "Vị trí phần không hợp lệ"


def test_busy_returns_409(client, svc):
    text = contract_text(4)
    cid = upload(client, text).json()["contract_id"]
    with svc.writing(cid):
        r = client.post(f"/api/contracts/{cid}/layout",
                        json={"parts": [{"start": text.index("Điều 3"), "kind": "appendix", "title": ""}]})
    assert r.status_code == 409 and r.json()["error"]


def test_graph_down_contract_still_created(client):
    contracts_api.CONFIG.graph = lambda: ContractGraphService(FakeStore(fail=True))
    r = upload(client, contract_text(4))
    assert r.status_code == 200, r.text
    g = r.json()["graph"]
    assert g["error"] and g["published"] is False


PART4_TEXT = ("HỢP ĐỒNG DỊCH VỤ\nĐiều 1. Ký kết\nHợp đồng ký ngày 15 tháng 3 năm 2023.\n"
              "Điều 2. Giá\nGiá dịch vụ là 30 triệu đồng.\n")


def test_part4_contract_json_still_opens(client, tmp_path):
    folder = tmp_path / "contracts" / "old1"
    folder.mkdir(parents=True)
    (folder / "original.txt").write_bytes(PART4_TEXT.encode("utf-8"))
    report = {"rid": "r1", "op": "review", "created_at": "2026-11-01T00:00:00+00:00", "party": "neutral",
              "anchor": "2023-04-01", "coverage": {"reviewed": 1, "total": 1}, "scope": ["Điều 1"],
              "topics": [], "findings": []}
    (folder / "contract.json").write_text(json.dumps({
        "contract_id": "old1", "filename": "hd.txt", "persist": True, "created_at": "2026-11-01T00:00:00+00:00",
        "text": PART4_TEXT, "units": [{"uid": "u1", "label": "Điều 1", "text": PART4_TEXT, "page": None}],
        "total_units": 1, "pages": [], "facts": {"type": "Hợp đồng dịch vụ", "parties": []}, "party": None,
        "sign_date": "2023-04-01", "sign_date_source": "user", "reports": {"r1": report}}, ensure_ascii=False),
        encoding="utf-8")
    r = client.get("/api/contracts/old1")
    assert r.status_code == 200, r.text
    assert all(u["uid"].startswith("p0.") for u in r.json()["units"])
    c = contracts_api.get("old1")
    assert c.reports["r1"]["pre_graph"] is True
    assert c.oplog.field("sign_date") == "2023-04-01"
    assert [o.reviewer for o in c.oplog.all() if o.origin == "human"] == ["chuyển đổi"]
    saved = json.loads((folder / "contract.json").read_text(encoding="utf-8"))
    assert saved["format"] == 2 and saved["reports"]["r1"]["pre_graph"] is True
    dl = client.get("/api/contracts/old1/reports/r1.docx")
    assert dl.status_code == 200 and dl.content[:2] == b"PK"


def test_part4_contract_without_original_still_opens(client, tmp_path):
    folder = tmp_path / "contracts" / "old2"
    folder.mkdir(parents=True)
    (folder / "contract.json").write_text(json.dumps({
        "contract_id": "old2", "filename": "hd.txt", "persist": True, "created_at": "2026-11-01T00:00:00+00:00",
        "text": PART4_TEXT, "units": [{"uid": "u1", "label": "Điều 1", "text": PART4_TEXT, "page": None}],
        "total_units": 1, "facts": {}, "reports": {}}, ensure_ascii=False), encoding="utf-8")
    r = client.get("/api/contracts/old2")
    assert r.status_code == 200, r.text
    assert [u["uid"] for u in r.json()["units"]] == ["u1"] and r.json()["parts"] == []


def test_saved_contract_roundtrip_keeps_ops(client, tmp_path):
    cid = upload(client, contract_text(5), persist=True).json()["contract_id"]
    client.post(f"/api/contracts/{cid}/sign-date", json={"date": "2023-04-01"})
    before = contracts_api.get(cid)
    again = ContractStore(tmp_path / "contracts").get(cid)
    assert again.oplog.all() == before.oplog.all()
    assert [u.uid for u in again.doc.units] == [u.uid for u in before.doc.units]
    assert [u.uid for u in again.units] == [u.uid for u in before.units]
    assert again.builds == before.builds and again.graph == before.graph


def test_failed_rebuild_leaves_contract_unchanged(client, svc, monkeypatch):
    cid = upload(client, contract_text(4), persist=True).json()["contract_id"]
    c = contracts_api.get(cid)
    ops, day, builds = c.oplog.to_json(), c.sign_date, list(c.builds)

    def boom(*a, **k):
        raise RuntimeError("boom")
    monkeypatch.setattr(svc, "rebuild", boom)
    r = client.post(f"/api/contracts/{cid}/sign-date", json={"date": "2023-04-01"})
    assert r.status_code == 500 and r.json()["error"]
    c = contracts_api.get(cid)
    assert c.oplog.to_json() == ops and c.sign_date == day and c.sign_date_source == "text" and c.builds == builds
    monkeypatch.undo()
    assert client.post(f"/api/contracts/{cid}/sign-date", json={"date": "2023-04-01"}).status_code == 200
    assert c.oplog.field("sign_date") == "2023-04-01" and len(c.builds) == 2


def _write_part4(root, cid):
    folder = root / cid
    folder.mkdir(parents=True)
    (folder / "original.txt").write_bytes(PART4_TEXT.encode("utf-8"))
    report = {"rid": "r1", "op": "review", "created_at": "2026-11-01T00:00:00+00:00", "party": "neutral",
              "anchor": "2023-04-01", "coverage": {"reviewed": 1, "total": 1}, "findings": []}
    (folder / "contract.json").write_text(json.dumps({
        "contract_id": cid, "filename": "hd.txt", "persist": True, "created_at": "2026-11-01T00:00:00+00:00",
        "text": PART4_TEXT, "units": [{"uid": "u1", "label": "Điều 1", "text": PART4_TEXT, "page": None}],
        "total_units": 1, "facts": {}, "sign_date": "2023-04-01", "sign_date_source": "user",
        "reports": {"r1": report}}, ensure_ascii=False), encoding="utf-8")
    return folder


def test_failed_part4_conversion_is_retried(client, svc, monkeypatch, tmp_path):
    folder = _write_part4(tmp_path / "contracts", "old3")
    raw = (folder / "contract.json").read_text(encoding="utf-8")

    def boom(*a, **k):
        raise RuntimeError("boom")
    monkeypatch.setattr(svc, "rebuild", boom)
    r = client.get("/api/contracts/old3")
    assert r.status_code == 200 and [u["uid"] for u in r.json()["units"]] == ["u1"]
    c = contracts_api.get("old3")
    assert c.page_texts == [] and c.oplog.all() == [] and "pre_graph" not in c.reports["r1"]
    assert (folder / "contract.json").read_text(encoding="utf-8") == raw
    monkeypatch.undo()
    r = client.get("/api/contracts/old3")
    assert r.status_code == 200 and r.json()["units"][0]["uid"].startswith("p0.")
    assert contracts_api.get("old3").reports["r1"]["pre_graph"] is True


def test_list_does_not_convert_and_skips_broken(client, tmp_path):
    root = tmp_path / "contracts"
    folder = _write_part4(root, "old4")
    (root / "bad1").mkdir()
    (root / "bad1" / "contract.json").write_text("{không phải json", encoding="utf-8")
    r = client.get("/api/contracts?ids=old4,bad1,khongco")
    assert r.status_code == 200
    listed = r.json()["contracts"]
    assert [c["contract_id"] for c in listed] == ["old4"] and listed[0]["units"][0]["uid"] == "u1"
    assert "page_texts" not in json.loads((folder / "contract.json").read_text(encoding="utf-8"))
    assert contracts_api.store().get("old4").page_texts == []


def test_llm_payloads_capped_at_30_units(client):
    SimpleLLM.SEEN.clear()
    cid = upload(client, contract_text(40)).json()["contract_id"]
    assert SimpleLLM.SEEN["facts"] == 30
    assert client.post(f"/api/contracts/{cid}/run", json={"op": "summary"}).status_code == 200
    contracts_api.chat_answer(cid, "Ký ngày nào?", [])
    assert SimpleLLM.SEEN["summary"] == 30 and SimpleLLM.SEEN["answer"] == 30


APPENDIX_TEXT = ("Điều 1. A\nXem Phụ lục 1 và Phụ lục 2.\nĐiều 2. B\n\nPHỤ LỤC 01\nDanh mục tài sản kèm theo hợp đồng\n"
                 "Điều 1. X\n\nPHỤ LỤC 02\nBiên bản bàn giao nhà và trang thiết bị\nĐiều 1. Y\n")


def test_resubmitting_detected_layout_keeps_xrefs(client):
    cid = upload(client, APPENDIX_TEXT).json()["contract_id"]
    c = contracts_api.get(cid)
    before = [(x.from_uid, x.to_uid, x.raw, x.kind) for x in c.doc.xrefs]
    assert ("p0.d1", "p1.pre", "Phụ lục 1", "appendix") in before
    parts = [{"start": p.start, "kind": "appendix", "title": p.title} for p in c.doc.parts[1:]]
    r = client.post(f"/api/contracts/{cid}/layout", json={"parts": parts})
    assert r.status_code == 200, r.text
    c = contracts_api.get(cid)
    assert [(x.from_uid, x.to_uid, x.raw, x.kind) for x in c.doc.xrefs] == before
    assert [p.number for p in c.doc.parts] == [None, 1, 2]


def test_layout_without_number_in_title_uses_position():
    specs = contracts_api._layout_parts("x" * 50, [{"start": 30, "title": "Bản vẽ"}, {"start": 10, "title": "PHỤ LỤC 05"}])
    assert [(p.part_id, p.number) for p in specs] == [("p0", None), ("p1", 5), ("p2", 2)]
