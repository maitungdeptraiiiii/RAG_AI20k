"""Shared document/content data models; independent of OCR and index backends."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import Literal
from rag.models.common import BlockKind, Record, artifact_path, checksum_value, nonempty, require


@dataclass(frozen=True, kw_only=True)
class Locator:
    source_id: str
    page: int | None = None
    slide: int | None = None
    sheet: str | None = None
    table_id: str | None = None
    row_start: int | None = None
    row_end: int | None = None
    column_start: int | None = None
    column_end: int | None = None
    heading_path: tuple[str, ...] = ()
    bbox: tuple[float, float, float, float] | None = None

    def __post_init__(self) -> None:
        nonempty(self.source_id)
        for number in (self.page, self.slide):
            require(number is None or number >= 1, "Page/slide starts at 1")
        for start, end in ((self.row_start, self.row_end), (self.column_start, self.column_end)):
            require((start is None and end is None) or
                    (start is not None and end is not None and 0 <= start < end), "Invalid [start,end) range")
        if self.bbox is not None:
            require(len(self.bbox) == 4, "bbox requires four coordinates")
            x0, y0, x1, y1 = self.bbox
            require(0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1, "Invalid normalized bbox")


@dataclass(frozen=True, kw_only=True)
class CellSpan:
    region: Literal["headers", "rows"]
    row_start: int
    row_end: int
    column_start: int
    column_end: int

    def __post_init__(self) -> None:
        require(self.region in ("headers", "rows"), "Invalid table region")
        require(0 <= self.row_start < self.row_end and 0 <= self.column_start < self.column_end,
                "Invalid cell span")


@dataclass(frozen=True, kw_only=True)
class TableData:
    headers: tuple[tuple[str, ...], ...]
    rows: tuple[tuple[str, ...], ...]
    column_units: tuple[str | None, ...]
    caption: str | None = None
    notes: tuple[str, ...] = ()
    period: str | None = None
    merged_cells: tuple[CellSpan, ...] = ()

    def __post_init__(self) -> None:
        width = len(self.column_units)
        require(width > 0, "Table needs columns")
        require(all(len(row) == width for row in (*self.headers, *self.rows)), "Inconsistent column count")
        for span in self.merged_cells:
            region = self.headers if span.region == "headers" else self.rows
            require(span.row_end <= len(region) and span.column_end <= width, "Cell span exceeds table")


@dataclass(frozen=True, kw_only=True)
class BlockRelation:
    target_block_id: str
    relation: Literal["next", "contains", "branch"]
    condition: str | None = None

    def __post_init__(self) -> None:
        nonempty(self.target_block_id)
        require(self.relation in ("next", "contains", "branch"), "Invalid block relation")


@dataclass(frozen=True, kw_only=True)
class Block:
    block_id: str
    processing_id: str
    version_id: str
    order: int
    kind: BlockKind
    text: str
    origin: Literal["native", "ocr"]
    locator: Locator
    table: TableData | None = None
    image_artifact: str | None = None
    ocr_confidence: float | None = None
    relations: tuple[BlockRelation, ...] = ()

    def __post_init__(self) -> None:
        nonempty(self.block_id, self.processing_id, self.version_id)
        require(self.order >= 0, "Block order starts at zero")
        require(self.kind in ("heading", "paragraph", "table", "image", "list", "flow"), "Invalid block kind")
        require(self.origin in ("native", "ocr"), "Invalid text origin")
        require(self.kind != "table" or self.table is not None, "Table block requires structured table")
        require(self.kind != "image" or self.image_artifact is not None, "Image block requires original artifact")
        require(self.ocr_confidence is None or 0 <= self.ocr_confidence <= 1, "Confidence must be in [0,1]")
        if self.image_artifact is not None:
            artifact_path(self.image_artifact)
        object.__setattr__(self, "text", unicodedata.normalize("NFC", self.text))


@dataclass(frozen=True, kw_only=True)
class SafeBlock(Block):
    """Masker output: text AND table/notes/relations must have been scrubbed."""
    masking_config_id: str

    def __post_init__(self) -> None:
        super().__post_init__()
        nonempty(self.masking_config_id)


@dataclass(frozen=True, kw_only=True)
class TargetRef:
    source_id: str | None = None
    version_id: str | None = None
    block_id: str | None = None
    unit_revision_id: str | None = None
    chunk_id: str | None = None
    locator: Locator | None = None

    def __post_init__(self) -> None:
        require(any((self.source_id, self.version_id, self.block_id, self.unit_revision_id, self.chunk_id)),
                "Target needs at least one identifier")


@dataclass(frozen=True, kw_only=True)
class GeneratedContext:
    text: str
    origin: Literal["header", "llm"]
    input_checksum: str
    model_id: str | None = None
    prompt_config_id: str | None = None

    def __post_init__(self) -> None:
        checksum_value(self.input_checksum)
        require(self.origin in ("header", "llm"), "Invalid enrichment origin")
        require(self.origin != "llm" or bool(self.model_id and self.prompt_config_id), "LLM context needs provenance")


@dataclass(frozen=True, kw_only=True)
class ChunkV2(Record):
    chunk_id: str
    document_id: str
    version_id: str
    processing_id: str
    unit_revision_id: str
    chunk_set_id: str
    block_ids: tuple[str, ...]
    locators: tuple[Locator, ...]
    source: str
    text: str
    language: str
    kind: BlockKind
    masking_config_id: str
    quality_assessment_id: str
    page_start: int | None = None
    page_end: int | None = None
    section: str | None = None
    generated_context: GeneratedContext | None = None

    def __post_init__(self) -> None:
        nonempty(self.chunk_id, self.document_id, self.version_id, self.processing_id,
                 self.unit_revision_id, self.chunk_set_id, self.source, self.language,
                 self.masking_config_id, self.quality_assessment_id)
        require(bool(self.text.strip()) and bool(self.block_ids) and bool(self.locators), "Chunk lacks content/provenance")
        require(self.kind in ("heading", "paragraph", "table", "image", "list", "flow"), "Invalid chunk kind")
        require((self.page_start is None and self.page_end is None) or
                (self.page_start is not None and self.page_end is not None and 1 <= self.page_start <= self.page_end),
                "Invalid page range")

    @property
    def doc_id(self) -> str:
        """Legacy store dedups by this key: a document ID would drop new versions."""
        return self.chunk_set_id

    @property
    def context(self) -> str | None:
        return self.generated_context.text if self.generated_context else None

    @property
    def index_text(self) -> str:
        return f"{self.context}\n{self.text}" if self.context else self.text


@dataclass(frozen=True, kw_only=True)
class ChunkingConfig:
    strategy: Literal["fixed", "structural"]
    max_syllables: int = 300
    overlap_syllables: int = 0
    tokenizer_version: str = "whitespace-v1"
    table_policy: str = "repeat-header-preserve-row-v1"

    def __post_init__(self) -> None:
        require(self.strategy in ("fixed", "structural"), "Invalid chunk strategy")
        require(0 <= self.overlap_syllables < self.max_syllables, "Invalid size/overlap")
        nonempty(self.tokenizer_version, self.table_policy)


__all__ = [
    'Locator',
    'CellSpan',
    'TableData',
    'BlockRelation',
    'Block',
    'SafeBlock',
    'TargetRef',
    'GeneratedContext',
    'ChunkV2',
    'ChunkingConfig',
]
