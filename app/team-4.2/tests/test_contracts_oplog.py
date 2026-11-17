from datetime import datetime, timezone
from rag.contracts.graph.oplog import OperationLog, human_op, machine_op

T = datetime(2026, 11, 12, tzinfo=timezone.utc)

def test_machine_ids_are_content_hashes_and_dedupe():
    a = machine_op("c1", "SET_FIELD", "type", {"value": "thuê nhà"}, "llm", "auto_accepted", at=T)
    b = machine_op("c1", "SET_FIELD", "type", {"value": "thuê nhà"}, "llm", "auto_accepted", at=T)
    log = OperationLog("c1")
    assert a.op_id == b.op_id and a.op_id.startswith("o") and log.add(a) and not log.add(b)

def test_human_supersede_wins_and_keeps_history():
    log = OperationLog("c1")
    m = machine_op("c1", "SET_FIELD", "sign_date", {"value": "2023-03-15"}, "llm", "auto_accepted", at=T)
    log.add(m)
    h = human_op("c1", "SET_FIELD", "sign_date", {"value": "2023-03-16"}, "Tùng", at=T)
    log.supersede(m.op_id, h, "Tùng", "sai ngày", T)
    assert log.field("sign_date") == "2023-03-16"
    old = next(o for o in log.all() if o.op_id == m.op_id)
    assert old.status == "rejected" and old.reviewer == "Tùng"
    assert next(o for o in log.all() if o.op_id == h.op_id).supersedes == m.op_id

def test_rejected_and_pending_not_active_and_json_roundtrip():
    log = OperationLog("c1")
    p = machine_op("c1", "SET_FIELD", "type", {"value": "x"}, "llm", "pending", at=T)
    log.add(p)
    assert log.active() == [] and log.field("type") is None
    again = OperationLog.from_json("c1", log.to_json())
    assert again.all() == log.all()

def test_supersede_is_all_or_nothing():
    import pytest
    log = OperationLog("c1")
    m = machine_op("c1", "SET_FIELD", "type", {"value": "a"}, "llm", "auto_accepted", at=T)
    h = human_op("c1", "SET_FIELD", "type", {"value": "b"}, "Tùng", at=T)
    log.add(m)
    log.add(h)
    before = log.all()
    with pytest.raises(ValueError):
        log.supersede(m.op_id, h, "Tùng", "x", T)
    with pytest.raises(ValueError):
        log.supersede(h.op_id, h, "Tùng", "x", T)
    with pytest.raises(KeyError):
        log.supersede("nope", human_op("c1", "SET_FIELD", "type", {"value": "c"}, "Tùng", at=T), "Tùng", "x", T)
    assert log.all() == before and log.field("type") == "b"
