"""Kiểm lại khái niệm "im lặng" trước khi báo thiếu nội dung hoặc quyền ẩn (spec 2026-11-14-contract-concept-check §6.2).
Báo nhầm quyền ẩn khi hợp đồng có ghi là lỗi nặng nhất, nên mỗi khái niệm sắp bị báo được tìm lại riêng."""
from __future__ import annotations

from datetime import datetime

from rag.bridge.catalog import Catalog
from rag.bridge.engine import RuleResult
from rag.bridge.facts_map import FactSet
from rag.bridge.tagger import assert_op, catalog_payload, check_item
from rag.contracts.graph.oplog import GraphOperation, machine_op
from rag.contracts.llm_json import ContractAIError, ask_json
from rag.contracts.models import Contract
from rag.index.bm25_index import BM25Index, syllable_tokenize
from rag.schema import Chunk

RECHECK_PROMPT_VERSION = "concept-recheck-1"

RECHECK_PROMPT = """Bạn kiểm tra lại MỘT khái niệm trong hợp đồng lao động tiếng Việt. "concepts" có đúng một khái niệm;
"units" là vài đoạn của hợp đồng có thể liên quan.

Có đoạn nào NÓI TỚI khái niệm đó không (dựa vào "describe" và "phrasing")? Có thì trả
{"items": [{"concept": <id>, "uid": <uid>, "quote": <câu chép NGUYÊN VĂN>, "slots": {<tên slot>: <giá trị>}}]};
không có thì trả {"items": []}.
- "quote" chép đúng từng chữ. Slot kiểu duration / percent / money chép nguyên cụm chứa con số trong quote; bool là
  true / false; enum là một giá trị trong "options". Chỉ điền slot khi đoạn văn nói rõ.
- Không đoán. Không đánh giá đúng sai luật."""

_SILENT = ("missing_content", "hidden_right")


def needs_recheck(results: list[RuleResult], factset: FactSet) -> list[str]:
    out: list[str] = []
    for r in results:
        if (r.finding in _SILENT and r.concept_id not in factset.present
                and r.concept_id not in factset.absent_checked and r.concept_id not in out):
            out.append(r.concept_id)
    return out


def _search(contract: Contract, query: str, k: int) -> list[str]:
    index = BM25Index(tokenizer=syllable_tokenize, tokenizer_name="syllable")
    index.build([Chunk(chunk_id=u.uid, doc_id=contract.contract_id, source="contract", page_start=None,
                       page_end=None, section=u.label, text=u.text) for u in contract.units if u.text.strip()])
    return [h.chunk_id for h in index.search(query, k)]


def recheck(llm, contract: Contract, catalog: Catalog, concept_ids: list[str], *, at: datetime, k: int = 5,
            model: str | None = None, on_event=None) -> list[GraphOperation]:
    ops: list[GraphOperation] = []
    for cid in concept_ids:
        concept = catalog.concepts[cid]
        uids = _search(contract, concept.label + " " + " ".join(concept.phrasing), k)
        if on_event:
            on_event({"type": "recheck", "status": "start", "concept_id": cid,
                      "label": concept.label, "uids": uids})
        found: list[GraphOperation] = []
        if uids:
            payload = {"units": [{"uid": u, "label": contract.unit(u).label, "text": contract.unit(u).text}
                                 for u in uids],
                       "concepts": catalog_payload(catalog, [cid])}
            try:
                data = ask_json(llm, RECHECK_PROMPT, payload, contract.mask_state)
            except ContractAIError:
                if on_event:
                    on_event({"type": "recheck", "status": "error", "concept_id": cid, "uids": uids})
                continue                       # không kiểm được: không ghi "vắng mặt"
            for it in data.get("items") if isinstance(data.get("items"), list) else []:
                checked, _ = check_item(contract, uids, it, catalog)
                if checked is not None and checked["concept_id"] == cid:
                    op = assert_op(contract, checked, catalog, at=at, found_by="recheck", model=model,
                                   prompt_version=RECHECK_PROMPT_VERSION)
                    if all(op.op_id != o.op_id for o in found):
                        found.append(op)
        if found:
            ops += found
        else:
            ops.append(machine_op(contract.contract_id, "ASSERT", cid,
                                  {"kind": "concept_absent", "concept_id": cid, "searched_uids": uids,
                                   "catalog_version": catalog.version}, "llm", "auto_accepted", at=at))
        if on_event:
            on_event({"type": "recheck", "status": "done", "concept_id": cid, "label": concept.label,
                      "uids": uids, "found": bool(found)})
    return ops


__all__ = ["RECHECK_PROMPT", "RECHECK_PROMPT_VERSION", "needs_recheck", "recheck"]
