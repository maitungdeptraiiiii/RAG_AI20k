"""Nhật ký thao tác của đồ thị hợp đồng: nguồn sự thật cho mọi quyết định."""
from __future__ import annotations

import dataclasses
import hashlib
import json
import secrets
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

OpType = Literal["SET_LAYOUT", "SET_FIELD", "ASSERT", "AMEND_UNIT"]
Origin = Literal["rule", "llm", "human"]
ReviewStatus = Literal["auto_accepted", "pending", "approved", "rejected"]

_ACTIVE = ("auto_accepted", "approved")


@dataclass(frozen=True)
class GraphOperation:
    """Một thao tác bất biến trong nhật ký."""

    op_id: str
    contract_id: str
    op_type: OpType
    target: str | None
    content: dict
    origin: Origin
    status: ReviewStatus
    created_at: datetime
    source_uid: str | None = None
    quote: tuple[str, ...] = ()
    status_reasons: tuple[str, ...] = ()
    reviewer: str | None = None
    reviewed_at: datetime | None = None
    note: str | None = None
    supersedes: str | None = None
    model: str | None = None
    prompt_version: str | None = None


def machine_op(contract_id, op_type, target, content, origin, status, *,
               source_uid=None, quote=(), at) -> GraphOperation:
    """Thao tác do máy sinh; mã là băm nội dung."""
    raw = (f"{contract_id}|{op_type}|{target or ''}|{source_uid or ''}|"
           f"{json.dumps(content, sort_keys=True, ensure_ascii=False)}")
    op_id = "o" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
    return GraphOperation(op_id, contract_id, op_type, target, content, origin,
                          status, at, source_uid=source_uid, quote=tuple(quote))


def human_op(contract_id, op_type, target, content, reviewer, *, note="",
             source_uid=None, quote=(), at) -> GraphOperation:
    """Thao tác do người nhập; mặc định đã duyệt."""
    return GraphOperation("h" + secrets.token_hex(6), contract_id, op_type, target,
                          content, "human", "approved", at, source_uid=source_uid,
                          quote=tuple(quote), reviewer=reviewer, reviewed_at=at,
                          note=note)


def _dt(v):
    return v.isoformat() if v is not None else None


def _undt(v):
    return datetime.fromisoformat(v) if v is not None else None


class OperationLog:
    """Nhật ký chỉ thêm; không xóa thao tác."""

    def __init__(self, contract_id: str, ops=()):
        self.contract_id = contract_id
        self._ops: list[GraphOperation] = []
        self._index: dict[str, int] = {}
        for op in ops:
            self.add(op)

    def add(self, op: GraphOperation) -> bool:
        """Thêm thao tác; trùng mã thì không đổi gì và trả False."""
        if op.op_id in self._index:
            return False
        self._index[op.op_id] = len(self._ops)
        self._ops.append(op)
        return True

    def set_review(self, op_id, status, reviewer, note, at) -> None:
        """Đặt trạng thái duyệt cho một thao tác."""
        i = self._index[op_id]
        self._ops[i] = dataclasses.replace(
            self._ops[i], status=status, reviewer=reviewer, reviewed_at=at, note=note)

    def supersede(self, old_id, new_op, reviewer, note, at) -> None:
        """Từ chối thao tác cũ và thêm thao tác mới thay thế."""
        if old_id not in self._index:
            raise KeyError(old_id)
        self.set_review(old_id, "rejected", reviewer, note, at)
        self.add(dataclasses.replace(new_op, supersedes=old_id))

    def active(self) -> list[GraphOperation]:
        return [o for o in self._ops if o.status in _ACTIVE]

    def _last(self, op_type, target=None, match_target=False):
        found = None
        for o in self.active():
            if o.op_type == op_type and (not match_target or o.target == target):
                found = o
        return found

    def field(self, name: str) -> Any:
        o = self._last("SET_FIELD", name, True)
        return o.content.get("value") if o else None

    def layout(self) -> list[dict] | None:
        o = self._last("SET_LAYOUT")
        return o.content.get("parts") if o else None

    def all(self) -> list[GraphOperation]:
        return list(self._ops)

    def to_json(self) -> list[dict]:
        out = []
        for o in self._ops:
            d = dataclasses.asdict(o)
            d["created_at"] = _dt(o.created_at)
            d["reviewed_at"] = _dt(o.reviewed_at)
            d["quote"] = list(o.quote)
            d["status_reasons"] = list(o.status_reasons)
            out.append(d)
        return out

    @classmethod
    def from_json(cls, contract_id: str, data) -> "OperationLog":
        ops = []
        for d in data:
            d = dict(d)
            d["created_at"] = _undt(d["created_at"])
            d["reviewed_at"] = _undt(d.get("reviewed_at"))
            d["quote"] = tuple(d.get("quote", ()))
            d["status_reasons"] = tuple(d.get("status_reasons", ()))
            ops.append(GraphOperation(**d))
        return cls(contract_id, ops)
