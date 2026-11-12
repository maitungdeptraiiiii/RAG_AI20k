"""Tách hợp đồng thành đơn vị cấp cao nhất (Điều / Mục / đoạn) qua parse_contract."""

from __future__ import annotations

from rag.contracts.doc import PageText
from rag.contracts.models import ContractUnit
from rag.contracts.structure import parse_contract, to_contract_units

DEMO_MAX_UNITS = 30


def split_units(text: str) -> list[ContractUnit]:
    return to_contract_units(parse_contract([PageText(None, text)]))


def llm_units(units: list[ContractUnit]) -> list[ContractUnit]:
    """Đơn vị gửi LLM trong một lượt: bản demo chỉ DEMO_MAX_UNITS đầu (soát theo lô là kế hoạch 2)."""
    return list(units[:DEMO_MAX_UNITS])


def limit_units(units: list[ContractUnit], n: int = DEMO_MAX_UNITS) -> tuple[list[ContractUnit], int]:
    return units[:n], len(units)
