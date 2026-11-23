"""Danh mục khái niệm HĐLĐ: lớp tương thích trên `rag.rules` (spec 2026-11-22-rete-rule-engine-design §3, §5.5).

Nạp và kiểm nằm ở `rag.rules.loader`; file này giữ các tên công khai cũ, gắn với gói `labor`."""
from __future__ import annotations

from functools import lru_cache
import dataclasses
from pathlib import Path

from typing import Sequence

from rag.rules.loader import PACKS_ROOT, load_concepts, load_pack, load_packs
from rag.rules.model import OPS, Catalog, CatalogError, Concept, Context, PackSpec, Rule, Slot
from rag.rules.model import leaves as _leaves  # noqa: F401  (engine cũ và test còn import tên này)

DEFAULT_PATH = PACKS_ROOT / "labor" / "concepts.yaml"


@lru_cache(maxsize=1)
def labor_pack() -> PackSpec:
    return load_pack("labor")


def labor_context() -> Context:
    return labor_pack().context()


# Hằng tương thích, đọc ra từ packs/labor/pack.yaml.
CONTRACT_FACTS: dict[str, str | None] = dict(labor_pack().document_facts)
USER_FACTS = labor_pack().user_facts
USER_FACT_UNITS: dict[str, str | None] = dict(labor_pack().user_fact_units)
UNITS = labor_pack().units.names


def load_catalog(path: Path = DEFAULT_PATH) -> Catalog:
    pack = labor_pack()
    cat = load_concepts(path, pack)
    return dataclasses.replace(cat, version=f"{pack.id}@{pack.version}/{cat.version}")   # cùng dạng load_packs (1.5)


def resolve_catalog(catalog: Catalog | None, packs: Sequence[str] | None) -> Catalog:
    """Catalog cho check_contract / ask_contract_graph: truyền sẵn `catalog`, hoặc danh sách `packs` (mặc định labor)."""
    if packs is not None and not packs:
        raise ValueError("packs rỗng: bỏ trống (mặc định labor) hoặc liệt kê ít nhất một gói")
    if catalog is not None and packs:
        raise ValueError("chỉ truyền catalog hoặc packs, không truyền cả hai")
    if catalog is not None:
        return catalog
    return load_packs(packs) if packs else load_catalog()


__all__ = ["CONTRACT_FACTS", "DEFAULT_PATH", "OPS", "UNITS", "USER_FACTS", "USER_FACT_UNITS", "Catalog", "CatalogError", "Concept",
           "Rule", "Slot", "labor_context", "labor_pack", "load_catalog"]
