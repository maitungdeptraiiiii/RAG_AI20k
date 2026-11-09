"""Shared document/content data models; independent of OCR and index backends."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from rag.models.common import nonempty, require
from rag.models.content import Block, SafeBlock
from rag.models.document import ProcessingRecord
from rag.models.quality import QualityIssue


@dataclass(frozen=True, kw_only=True)
class ParseResult:
    processing: ProcessingRecord
    blocks: tuple[Block, ...]
    findings: tuple[QualityIssue, ...] = ()

    def __post_init__(self) -> None:
        require(len({b.block_id for b in self.blocks}) == len(self.blocks), "Duplicate block IDs")
        require(len({b.order for b in self.blocks}) == len(self.blocks), "Duplicate block order")
        require(all(b.processing_id == self.processing.processing_id and b.version_id == self.processing.version_id
                    and b.locator.source_id == self.processing.source_id for b in self.blocks),
                "Blocks do not belong to parse processing/source/version")


@dataclass(frozen=True, kw_only=True)
class MaskResult:
    blocks: tuple[SafeBlock, ...]
    findings: tuple[QualityIssue, ...]
    masking_config_id: str

    def __post_init__(self) -> None:
        nonempty(self.masking_config_id)
        require(all(isinstance(b, SafeBlock) and b.masking_config_id == self.masking_config_id for b in self.blocks),
                "Mask result requires consistent SafeBlocks")


@dataclass(frozen=True, kw_only=True)
class ResolvedScope:
    generation_id: str
    catalog_revision: int
    resolved_date: date | None
    eligible_chunk_ids: frozenset[str]
    ambiguous_unit_ids: tuple[str, ...] = ()
    findings: tuple[QualityIssue, ...] = ()


__all__ = [
    'ParseResult',
    'MaskResult',
    'ResolvedScope',
]
