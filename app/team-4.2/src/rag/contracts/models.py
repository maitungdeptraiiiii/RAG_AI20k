"""Mô hình dữ liệu của hợp đồng đính kèm trong chat (phần 4)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from rag.contracts.doc import ContractDoc, PageText
from rag.contracts.graph.oplog import OperationLog
from rag.quality.pii import MaskState

CONTRACT_PII_PREFIX = "HD_"
"""Placeholder PII của hợp đồng: [HD_PHONE_1] — khác [USER_...] của câu hỏi và [PHONE_1] của kho tài liệu."""


def new_mask_state() -> MaskState:
    return MaskState(prefix=CONTRACT_PII_PREFIX)


@dataclass(frozen=True)
class ContractUnit:
    uid: str            # u1, u2, ... ổn định theo thứ tự trong hợp đồng
    label: str          # "Điều 5" | "Mục 2" | "Đoạn 3" | "Phần mở đầu"
    text: str
    page: int | None = None


@dataclass
class Contract:
    contract_id: str
    filename: str
    persist: bool
    created_at: datetime
    text: str
    units: list[ContractUnit]
    total_units: int                      # tổng số đơn vị cấp cao nhất
    pages: list[dict[str, Any]] = field(default_factory=list)
    facts: dict[str, Any] = field(default_factory=dict)
    party: str | None = None              # "neutral" hoặc vai trò một bên (vd. "Bên thuê")
    sign_date: date | None = None
    sign_date_source: str | None = None   # "text" | "user"
    reports: dict[str, dict[str, Any]] = field(default_factory=dict)
    mask_state: MaskState = field(default_factory=new_mask_state, repr=False)
    page_texts: list[PageText] = field(default_factory=list)
    file_checksum: str | None = None
    oplog: OperationLog | None = None     # None -> nhật ký rỗng theo contract_id
    doc: ContractDoc | None = field(default=None, repr=False)   # dẫn xuất, không lưu
    graph: dict[str, Any] = field(default_factory=dict)          # trạng thái bản dựng gần nhất
    builds: list[dict[str, Any]] = field(default_factory=list)   # bản ghi các bản dựng, mới nhất cuối

    def __post_init__(self) -> None:
        if self.oplog is None:
            self.oplog = OperationLog(self.contract_id)

    def unit(self, uid: str) -> ContractUnit | None:
        return next((u for u in self.units if u.uid == uid), None)
