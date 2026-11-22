"""Danh mục khái niệm HĐLĐ: lớp tương thích trên `rag.rules` (spec 2026-11-22-rete-rule-engine-design §3, §5.5).

Nạp và kiểm nằm ở `rag.rules.loader`; file này giữ các tên công khai cũ, gắn với gói `labor`."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from rag.rules.loader import PACKS_ROOT, load_concepts, load_pack
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
UNITS = labor_pack().units.names


def load_catalog(path: Path = DEFAULT_PATH) -> Catalog:
    return load_concepts(path, labor_pack())


__all__ = ["CONTRACT_FACTS", "DEFAULT_PATH", "OPS", "UNITS", "USER_FACTS", "Catalog", "CatalogError", "Concept",
           "Rule", "Slot", "labor_context", "labor_pack", "load_catalog"]
