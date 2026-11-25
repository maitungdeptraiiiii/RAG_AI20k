"""Chạy pipeline hợp đồng thật (đường của ui/server.py) trên một file, ghi dữ liệu từng bước ra JSON.

Chạy từ app/team-4.2:  python scripts/trace_contract_pipeline.py <file hợp đồng> <file json ra> [câu hỏi hỏi đáp]
Dùng môi trường có đủ extra `jev` và `graph` (xem README). Neo4j tắt thì đồ thị chỉ được dựng, không công bố.
"""
from __future__ import annotations

import json
import sys
import time
from dataclasses import asdict
from pathlib import Path

APP = Path.cwd()
sys.path[:0] = [str(APP), str(APP / "ui"), str(APP / "src")]

import server  # noqa: E402  — cấu hình contracts_api.CONFIG như khi chạy app
import contracts_api as api  # noqa: E402
from rag.contracts import answer as ca  # noqa: E402
from rag.contracts import verify  # noqa: E402
from rag.contracts.batches import make_batches  # noqa: E402
from rag.contracts.graph.build import build_graph  # noqa: E402

src, out_path = Path(sys.argv[1]), Path(sys.argv[2])
scratch = out_path.parent / "contracts_store"
api.CONFIG.root = lambda: scratch

trace: dict = {"file": src.name, "llm_calls": [], "law_searches": [], "steps": {}}
stage = {"name": "?"}


class RecLLM:
    def __init__(self, llm):
        self.llm = llm

    def complete(self, system, user):
        t0 = time.time()
        raw = self.llm.complete(system, user)
        trace["llm_calls"].append({"stage": stage["name"], "prompt_head": system.split("\n", 1)[0][:120],
                                   "system_chars": len(system), "payload": json.loads(user),
                                   "raw": raw, "seconds": round(time.time() - t0, 1)})
        return raw


base_llm = server.get_pipeline()[0].llm
api.CONFIG.llm_factory = lambda: RecLLM(base_llm)

_find = ca.find_evidence


def rec_find(runtime, legacy, query, anchor, k=4):
    res = _find(runtime, legacy, query, anchor, k)
    trace["law_searches"].append({"stage": stage["name"], "query": query, "anchor": anchor.isoformat(), "k": k,
                                  "runtime": runtime is not None,
                                  "results": [{"eid": e.eid, "store": e.store, "source_title": e.source_title,
                                               "section": e.section, "valid_from": str(e.valid_from),
                                               "valid_to": str(e.valid_to), "status": e.status,
                                               "text": e.text[:300]} for e in res]})
    return res


ca.find_evidence = rec_find

data = src.read_bytes()

# --- Giai đoạn 1 ---
stage["name"] = "create"
t0 = time.time()
card = api.create(data, src.name, False)
cid = card["contract_id"]
c = api.get(cid)
trace["steps"]["create_seconds"] = round(time.time() - t0, 1)
trace["steps"]["pages"] = [asdict(p) | {"text": p.text[:400]} for p in c.page_texts]
trace["steps"]["page_meta"] = c.pages
trace["steps"]["text_chars"] = len(c.text)
trace["steps"]["parts"] = [asdict(p) for p in c.doc.parts]
trace["steps"]["units_all"] = [{"uid": u.uid, "level": u.level, "label": u.label, "parent": u.parent_uid,
                                "page": u.page_start, "chars": len(u.text), "text": u.text[:160]} for u in c.doc.units]
trace["steps"]["top_units"] = [{"uid": u.uid, "label": u.label, "chars": len(u.text)} for u in c.units]
trace["steps"]["values"] = [asdict(v) for v in c.doc.values]
trace["steps"]["xrefs"] = [asdict(x) for x in c.doc.xrefs]
trace["steps"]["parse_report"] = asdict(c.doc.report)
trace["steps"]["batches"] = [{"index": b.index, "uids": b.uids, "labels": [u.label for u in b.units],
                              "chars": sum(len(u.text) for u in b.units),
                              "context": [{"uid": x["uid"], "label": x["label"], "chars": len(x["text"])} for x in b.context],
                              "references": [{"uid": x["uid"], "label": x["label"], "chars": len(x["text"])}
                                             for x in b.references]}
                             for b in make_batches(c)]
trace["steps"]["facts"] = c.facts
trace["steps"]["sign_date_after_create"] = c.sign_date.isoformat() if c.sign_date else None
trace["steps"]["oplog_after_create"] = c.oplog.to_json()
trace["steps"]["graph_status"] = {k: v for k, v in c.graph.items() if k != "record"} | {"record": c.graph.get("record")}
build, _ = build_graph(cid, c.page_texts, c.oplog, file_checksum=c.file_checksum, built_at=api._now())
from collections import Counter  # noqa: E402
trace["steps"]["graph_nodes"] = dict(Counter(n.label for n in build.nodes))
trace["steps"]["graph_edges"] = dict(Counter(e.type for e in build.edges))
trace["steps"]["graph_sample_nodes"] = [{"id": n.node_id, "label": n.label,
                                         **{k: (str(v)[:120]) for k, v in n.props.items() if k not in ("contract_id",)}}
                                        for n in build.nodes[:6]]
trace["steps"]["card_verification"] = card["verification"]

# --- Giai đoạn 2: thử kiểm tra trước khi xác minh (phải bị chặn) ---
stage["name"] = "gate"
try:
    verify.check_gate(c, "review")
    trace["steps"]["gate"] = "KHÔNG bị chặn"
except Exception as e:  # noqa: BLE001
    trace["steps"]["gate"] = {"error": type(e).__name__, "message": str(e), "pending": getattr(e, "pending", None)}

# xác minh: chọn bên thuê, xác nhận các trường bắt buộc đang 'found'
rows = card["verification"]["fields"]
roles = [p["role"] for p in c.facts.get("parties") or []]
party = (next((r for r in roles if "người lao động" in r.lower()), None)
         or next((r for r in roles if "thuê" in r.lower() and "cho" not in r.lower()), None)
         or (roles[-1] if roles else "neutral"))
answers = {"party": {"action": "set", "value": party}}
for r in rows:
    if r["key"] == "party":
        continue
    if r["status"] == "found":
        answers[r["key"]] = {"action": "confirm"}
    elif r["required"]:
        answers[r["key"]] = ({"action": "set", "value": r["candidates"][0]["value"]} if r["candidates"]
                             else {"action": "unknown"})
trace["steps"]["verify_answers"] = answers
stage["name"] = "verify"
card2 = api.set_facts(cid, answers, "demo-user")
trace["steps"]["verification_after"] = card2["verification"]
trace["steps"]["oplog_after_verify"] = c.oplog.to_json()
trace["steps"]["build_after_verify"] = card2["graph"]

# --- Giai đoạn 3: kiểm tra concept (bộ máy luật) ---
stage["name"] = "concept_check"
t0 = time.time()
try:
    trace["steps"]["concept_check"] = api.concept_check(cid, {})
except Exception as e:  # noqa: BLE001
    trace["steps"]["concept_check"] = {"error": f"{type(e).__name__}: {e}"}
trace["steps"]["concept_check_seconds"] = round(time.time() - t0, 1)

stage["name"] = "chat_answer"
q = sys.argv[3] if len(sys.argv) > 3 else "Bên cho thuê có được tự ý tăng giá thuê khi thị trường thay đổi không?"
try:
    trace["steps"]["chat"] = {"question": q, **api.chat_answer(cid, q, [])}
except Exception as e:  # noqa: BLE001
    trace["steps"]["chat"] = {"question": q, "error": f"{type(e).__name__}: {e}"}

out_path.write_text(json.dumps(trace, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
print("OK", len(trace["llm_calls"]), "llm calls", len(trace["law_searches"]), "law searches")
