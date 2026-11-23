"""LLM gán khái niệm cho điều khoản (spec 2026-11-14-contract-concept-check §6.1). LLM chỉ nhận diện: khái niệm nào,
ở đơn vị nào, câu nguyên văn, giá trị thô. Không gửi ngưỡng luật, rule hay neo. Kết quả là thao tác ASSERT; người gọi
ghi vào nhật ký."""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from rag.bridge.catalog import Catalog
from rag.bridge.facts_map import normalize_slot
from rag.contracts.batches import BUDGET, Batch, make_batches, run_batches
from rag.contracts.graph.oplog import GraphOperation, machine_op
from rag.contracts.llm_json import _norm, ask_json, quote_ok
from rag.contracts.models import Contract

TAG_PROMPT_VERSION = "concept-tag-5"
BATCH_BUDGET = BUDGET
_TEXT_SLOTS = ("duration", "percent", "money")

_TAG_PROMPT_TEMPLATE = """Bạn đọc MỘT PHẦN của một <<DOCUMENT>> tiếng Việt (các đơn vị có uid trong "units"). "context" và
"references" chỉ để hiểu, không gán khái niệm cho chúng.

"concepts" là danh sách khái niệm cố định. Với MỖI đơn vị trong "units", tìm những khái niệm mà đơn vị đó NÓI TỚI
(dựa vào "describe" và "phrasing"). Một đơn vị có thể nói tới nhiều khái niệm; một khái niệm có thể ở nhiều đơn vị.
"kind" là loại khái niệm dùng chung cho mọi loại hợp đồng: các khái niệm cùng "kind" đọc slot theo cùng cách.
  rate_cap = tỉ lệ có trần; time_limit = khoảng thời gian có giới hạn; notice = báo trước / thông báo;
  required_content = nội dung hợp đồng phải ghi; payment = khoản tiền hoặc tỉ lệ tiền phải trả; penalty = phạt vi phạm;
  leave_entitlement = số ngày nghỉ; count_limit = giới hạn số lần;
  prohibited_practice, void_term, termination = điều khoản có thể trái luật, slot bool là true khi hợp đồng CÓ điều
  khoản đúng như slot mô tả, false khi hợp đồng nói ngược lại (vd. loại trừ trách nhiệm, bên bán được đổi giá, bên
  cho thuê được vào nhà không báo trước).
"not_about" của một khái niệm liệt kê những nội dung KHÔNG thuộc khái niệm đó (kèm khái niệm đúng sau "→"):
đơn vị chỉ nói tới nội dung như vậy thì không gán khái niệm đó.

Trả về {"items": [{"concept": <id>, "uid": <uid của đơn vị>, "quote": <câu chép NGUYÊN VĂN từ đơn vị>,
"slots": {<tên slot>: <giá trị>}}]}.
- "quote": chép đúng từng chữ, không sửa, không tóm tắt; đủ dài để thấy nội dung khái niệm.
- slot kiểu duration / percent / money: {"text": <cụm chứa con số, chép NGUYÊN VĂN trong quote>, "norm": <giá trị đọc
  ra>}. "norm" ghi đúng từng con số như điều khoản viết (bằng chữ số hay bằng chữ đều đọc ra số), KHÔNG cộng, KHÔNG
  đổi đơn vị:
  duration: {"parts": [{"n": <số>, "unit": "hour|day|workday|week|month|year"}, ...]} ("2 năm 6 tháng" -> hai phần;
    "ngày làm việc" -> workday); money: {"amount": <số đồng>, "currency": "VND|USD"};
  percent: {"value": <số>, "per": "day|month|year" hoặc null nếu không ghi kỳ}.
- slot kiểu bool: true hoặc false theo đúng điều khoản nói. slot kiểu enum: một giá trị trong "options".
- Chỉ điền slot khi điều khoản nói rõ; không có thì bỏ.
- Không đánh giá điều khoản đúng hay sai luật.
- Không có khái niệm nào thì trả {"items": []}."""


def tag_prompt(ctx=None) -> str:
    """Prompt cho loại văn bản của gói đang dùng (`ctx.document_label`); None -> hợp đồng lao động."""
    return _TAG_PROMPT_TEMPLATE.replace("<<DOCUMENT>>", getattr(ctx, "document_label", None) or "hợp đồng lao động")


TAG_PROMPT = tag_prompt()          # bản cho gói labor (tên công khai cũ, giữ tương thích)


@dataclass
class TagRun:
    ops: list[GraphOperation] = field(default_factory=list)
    rejected: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def catalog_payload(catalog: Catalog, ids: list[str] | None = None) -> list[dict]:
    out = []
    for cid, c in catalog.concepts.items():
        if ids is not None and cid not in ids:
            continue
        d: dict[str, Any] = {"id": cid, "label": c.label, "describe": c.describe, "phrasing": list(c.phrasing)}
        if c.kind:
            d["kind"] = c.kind                  # loại khái niệm chung các miền (kinds.yaml): khái niệm cùng loại có slot cùng kiểu
        if c.not_about:
            d["not_about"] = [f"{x['text']} → {x['see']}" for x in c.not_about]
        if c.slots:
            d["slots"] = {n: {"kind": s.kind, "unit": s.unit, **({"options": list(s.options)} if s.options else {})}
                          for n, s in c.slots.items()}
        out.append(d)
    return out


def _unit_text(contract: Contract, uid: str) -> str:
    u = contract.unit(uid)
    return u.text if u is not None else ""


def check_item(contract: Contract, batch_uids: list[str], item: Any, catalog: Catalog) -> tuple[dict | None, str | None]:
    """Kiểm một item LLM trả. Hợp lệ -> (item đã chuẩn hóa, None); hỏng -> (None, lý do).
    Item chuẩn hóa: {concept_id, uid, quote, slots_raw, slots: {name: {value, unit}}, bad_slots: [name],
    dropped_slots: {name: raw}} (slot không có trong khái niệm bị bỏ, khái niệm vẫn giữ)."""
    if not isinstance(item, dict):
        return None, "not_an_object"
    concept = catalog.concepts.get(str(item.get("concept") or ""))
    if concept is None:
        return None, "unknown_concept"
    quote, uid = str(item.get("quote") or ""), str(item.get("uid") or "")
    if uid not in batch_uids or not quote_ok(_unit_text(contract, uid), quote):
        home = next((u for u in batch_uids if quote_ok(_unit_text(contract, u), quote)), None)
        if home is None:
            return None, "quote_not_found" if uid in batch_uids else "unknown_uid"
        uid = home
    given = item.get("slots") if isinstance(item.get("slots"), dict) else {}
    raw_slots = {n: v for n, v in given.items() if n in concept.slots}
    dropped = {n: v for n, v in given.items() if n not in concept.slots}   # slot LLM tự đặt: bỏ slot, giữ khái niệm
    slots, bad = {}, []
    for name, raw in raw_slots.items():
        slot = concept.slots[name]
        text = str(raw.get("text") or "") if isinstance(raw, dict) else str(raw)
        if slot.kind in _TEXT_SLOTS and (not _norm(text) or _norm(text) not in _norm(quote)):
            return None, "slot_not_in_quote"
        f = normalize_slot(slot, raw, catalog.context, quote=quote)
        if f is None:
            bad.append(name)
        else:
            slots[name] = {"value": f.value, "unit": f.unit}
    return {"concept_id": concept.id, "uid": uid, "quote": quote, "slots_raw": raw_slots, "slots": slots,
            "bad_slots": bad, "dropped_slots": dropped}, None


def assert_op(contract: Contract, checked: dict, catalog: Catalog, *, at: datetime, found_by: str,
              model: str | None, prompt_version: str) -> GraphOperation:
    content = {"kind": "concept", "concept_id": checked["concept_id"], "slots_raw": checked["slots_raw"],
               "slots": checked["slots"], "catalog_version": catalog.version, "found_by": found_by,
               "holder": catalog.concepts[checked["concept_id"]].holder}     # đồ thị nối HOLDER không cần nạp lại gói
    if checked.get("dropped_slots"):
        content["dropped_slots"] = checked["dropped_slots"]
    bad = checked["bad_slots"]
    op = machine_op(contract.contract_id, "ASSERT", checked["concept_id"], content, "llm",
                    "pending" if bad else "auto_accepted", source_uid=checked["uid"], quote=(checked["quote"],), at=at)
    return dataclasses.replace(op, model=model, prompt_version=prompt_version,
                               status_reasons=tuple(f"slot_unparsable:{n}" for n in bad))


def tag_contract(llm, contract: Contract, catalog: Catalog, *, at: datetime, model: str | None = None,
                 on_progress=None, on_event=None) -> TagRun:
    """on_progress(xong, tổng): gọi sau mỗi lô."""
    concepts = catalog_payload(catalog)
    run = TagRun()
    seen: set[str] = set()

    def read(batch: Batch) -> dict:
        payload = {"units": batch.payload_units(), "context": list(batch.context),
                   "references": list(batch.references), "concepts": concepts}
        if on_event:
            on_event({"type": "tag_batch", "status": "start", "batch": batch.index, "uids": batch.uids})
        data = ask_json(llm, tag_prompt(catalog.context), payload, contract.mask_state)
        if on_event:
            for item in data.get("items", []) if isinstance(data.get("items"), list) else []:
                checked, reason = check_item(contract, batch.uids, item, catalog)
                if checked is not None:
                    op = assert_op(contract, checked, catalog, at=at, found_by="tagger", model=model,
                                   prompt_version=TAG_PROMPT_VERSION)
                    on_event({"type": "concept", "concept_id": checked["concept_id"],
                              "label": catalog.concepts[checked["concept_id"]].label,
                              "uid": checked["uid"], "quote": checked["quote"], "op": dataclasses.asdict(op)})
            on_event({"type": "tag_batch", "status": "done", "batch": batch.index, "uids": batch.uids})
        return data

    batches = run_batches(make_batches(contract, budget=BATCH_BUDGET), read, on_done=on_progress)
    run.warnings += batches.warnings()
    for batch, data in batches.results:
        items = data.get("items") if isinstance(data.get("items"), list) else []
        for it in items:
            checked, reason = check_item(contract, batch.uids, it, catalog)
            if checked is None:
                run.rejected.append({"item": it, "reason": reason})
                continue
            if checked["dropped_slots"]:
                run.rejected.append({"item": it, "reason": "unknown_slot_dropped",
                                     "slots": list(checked["dropped_slots"])})
            op = assert_op(contract, checked, catalog, at=at, found_by="tagger", model=model,
                           prompt_version=TAG_PROMPT_VERSION)
            if op.op_id not in seen:
                seen.add(op.op_id)
                run.ops.append(op)
    return run


__all__ = ["BATCH_BUDGET", "TAG_PROMPT", "TAG_PROMPT_VERSION", "TagRun", "assert_op", "catalog_payload",
           "check_item", "tag_contract"]
