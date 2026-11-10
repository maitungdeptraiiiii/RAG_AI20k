"""Mô hình dữ liệu kho luật có phiên bản.

AmendmentOperation là nguồn sự thật (bất biến về nội dung); ProvisionVersion là dữ liệu dẫn xuất,
dựng lại được hoàn toàn từ văn bản gốc + các thao tác. Khoảng hiệu lực nửa mở [valid_from, valid_to).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Literal

OperationType = Literal[
    "REPLACE_ARTICLE", "REPLACE_ARTICLE_TITLE", "REPLACE_CLAUSE", "REPLACE_CLAUSE_LEAD_IN", "REPLACE_POINT",
    "INSERT_ARTICLE", "INSERT_CLAUSE", "INSERT_POINT",
    "DELETE_ARTICLE", "DELETE_CLAUSE", "DELETE_POINT",
    "REPLACE_TEXT", "AMEND_TEXT", "REPEAL_DOCUMENT", "UNSUPPORTED",
]
ParseStatus = Literal["exact", "partial", "unsupported", "failed"]
ReviewStatus = Literal["auto_accepted", "pending", "approved", "rejected"]
VerificationStatus = Literal["verified", "needs_review", "conflicted"]
ProvisionKind = Literal["article", "article_title", "clause", "clause_lead_in", "point"]
AddressPart = Literal["whole", "title", "lead_in"]


@dataclass(frozen=True)
class Address:
    """Địa chỉ một đơn vị trong một văn bản: Điều / khoản / điểm, hoặc tên Điều / đoạn mở đầu khoản."""

    article: str
    clause: str | None = None
    point: str | None = None
    part: AddressPart = "whole"


@dataclass(frozen=True)
class LegalDocument:
    document_key: str
    vbpl_id: str
    title: str
    doc_type: str
    doc_number: str
    issuer: str | None
    issued_on: date | None
    vbpl_effective_from: date | None
    vbpl_effective_to: date | None
    eff_status: str | None
    is_consolidated: bool
    raw_text_path: str
    raw_checksum: str
    fetched_at: datetime
    discovered_via: str | None = None


@dataclass(frozen=True)
class DocumentRelation:
    source_key: str
    target_key: str
    relation: str                 # mã vbpl: SUA_DOI_BO_SUNG, THAY_THE, HOP_NHAT, BAI_BO ...
    evidence: str
    status: Literal["detected", "confirmed", "rejected"]


@dataclass(frozen=True)
class Provision:
    provision_id: str
    document_key: str
    kind: ProvisionKind
    address: Address
    parent_id: str | None
    order: int
    heading_path: tuple[str, ...]
    text: str
    span: tuple[int, int]


@dataclass(frozen=True)
class AmendmentOperation:
    operation_id: str
    source_document_key: str
    source_issued_on: date | None
    source_locator: str
    source_address: Address | None
    source_span: tuple[int, int]
    sequence: int
    target_document_key: str | None
    target_law_name: str | None
    operation_type: OperationType
    target: Address | None
    anchor: Address | None
    new_text: str | None
    old_phrase: str | None
    effective_from: date | None
    parse_status: ParseStatus
    review_status: ReviewStatus
    status_reasons: tuple[str, ...] = ()
    old_text: str | None = None
    reviewer: str | None = None
    reviewed_at: datetime | None = None
    review_note: str | None = None
    supersedes_operation_id: str | None = None


@dataclass(frozen=True)
class ProvisionVersion:
    provision_id: str
    document_key: str
    kind: ProvisionKind
    text: str
    valid_from: date
    valid_to: date | None
    verification_status: VerificationStatus
    status_reasons: tuple[str, ...]
    notes: tuple[str, ...]
    source_operations: tuple[str, ...]
    build_id: str


@dataclass(frozen=True)
class BuildRun:
    build_id: str
    document_key: str
    operation_ids: tuple[str, ...]
    inputs_checksum: str
    built_at: datetime
    code_version: str


@dataclass(frozen=True)
class ReviewItem:
    review_id: str
    kind: Literal["operation", "vbhn_mismatch", "discovery"]
    document_key: str
    operation_id: str | None
    provision_id: str | None
    reasons: tuple[str, ...]
    status: Literal["open", "resolved"]
    created_at: datetime
    payload: dict[str, Any] = field(default_factory=dict, compare=False, hash=False)


@dataclass(frozen=True)
class ReviewDecision:
    review_id: str
    action: Literal["approve", "reject", "correct"]
    reviewer: str
    note: str
    corrected_fields: dict[str, Any]
    decided_at: datetime
