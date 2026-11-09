"""Contracts giữa các bước ingestion để có thể thay nguồn và cách xử lý độc lập."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Literal, Protocol

from rag.ingest.dedup import DedupConfig
from rag.models.common import artifact_path, nonempty, require
from rag.models.content import Block, ChunkV2, ChunkingConfig, Locator, SafeBlock
from rag.models.document import ChangeRequest, IdentityHint, SourceRecord, UnitRevision
from rag.models.quality import QualityAssessment, QualityIssue
from rag.models.results import MaskResult, ParseResult
from rag.quality.interfaces import ConflictConfig, NumericConfig, ValidationConfig
from rag.schema import Chunk, Page


SourceKind = str


@dataclass(frozen=True)
class RawSource:
    """Dữ liệu thô do Reader tạo ra và Parser tiếp nhận."""

    source: str
    kind: SourceKind
    content: bytes | str


class Reader(Protocol):
    def read(self, value: str | Path, *, source: str | None = None) -> RawSource:
        """Đọc file/URL thành dữ liệu thô, chưa chuyển thành Page."""
        ...


class Parser(Protocol):
    def parse(self, raw: RawSource) -> list[Page]:
        """Chuyển dữ liệu thô thành các Page đã chuẩn hoá."""
        ...


class Chunker(Protocol):
    def chunk(
        self,
        pages: Sequence[Page],
        *,
        max_syllables: int = 300,
        overlap: bool = True,
    ) -> list[Chunk]:
        """Chuyển các Page cùng tài liệu thành Chunk."""
        ...


class Indexer(Protocol):
    def index(self, chunks: Sequence[Chunk]) -> int:
        """Index/lưu chunk và trả số chunk mới được thêm."""
        ...


__all__ = [
    'Chunker',
    'Indexer',
    'Parser',
    'RawSource',
    'Reader',
    'SourceKind',
]


# Extended ingestion contracts. Existing interfaces above remain compatible.


@dataclass(frozen=True, kw_only=True)
class RawSourceV2:
    source: SourceRecord
    content: bytes


@dataclass(frozen=True, kw_only=True)
class OCRConfig:
    engine: str
    engine_version: str
    language: str
    timeout_seconds: float
    cache_config_id: str
    model: str | None = None

    def __post_init__(self) -> None:
        from rag.models.common import nonempty, require
        nonempty(self.engine, self.engine_version, self.language, self.cache_config_id)
        require(self.timeout_seconds > 0, "OCR timeout must be positive")


@dataclass(frozen=True, kw_only=True)
class ParseConfig:
    parser_name: str
    parser_version: str
    normalization_config_id: str
    language: str
    ocr_page_policy_id: str


@dataclass(frozen=True, kw_only=True)
class OCRPageInput:
    source_id: str
    page: int
    image_artifact: str
    width: int
    height: int
    rotation: Literal[0, 90, 180, 270] = 0

    def __post_init__(self) -> None:
        from rag.models.common import artifact_path, nonempty, require
        nonempty(self.source_id)
        artifact_path(self.image_artifact)
        require(self.page >= 1 and self.width > 0 and self.height > 0, "Invalid OCR page dimensions")
        require(self.rotation in (0, 90, 180, 270), "Invalid rotation")


@dataclass(frozen=True, kw_only=True)
class OCRRegion:
    text: str
    bbox: tuple[float, float, float, float]
    order: int
    confidence: float | None
    kind: Literal["heading", "paragraph", "table", "image", "list", "flow"]

    def __post_init__(self) -> None:
        from rag.models.common import require
        Locator(source_id="ocr-region", bbox=self.bbox)
        require(self.order >= 0, "Region order starts at zero")
        require(self.confidence is None or 0 <= self.confidence <= 1, "Invalid OCR confidence")
        require(self.kind in ("heading", "paragraph", "table", "image", "list", "flow"), "Invalid region kind")


@dataclass(frozen=True, kw_only=True)
class OCRResult:
    regions: tuple[OCRRegion, ...]
    engine_name: str
    engine_version: str
    cost_usd: Decimal
    elapsed_ms: int
    findings: tuple[QualityIssue, ...] = ()

    def __post_init__(self) -> None:
        from rag.models.common import nonempty, require
        nonempty(self.engine_name, self.engine_version)
        require(self.cost_usd.is_finite() and self.cost_usd >= 0 and self.elapsed_ms >= 0,
                "Invalid OCR cost/latency")


class BudgetLedger(Protocol):
    def reserve(self, max_cost_usd: Decimal) -> str: ...
    def settle(self, reservation_id: str, actual_cost_usd: Decimal) -> None: ...
    def release(self, reservation_id: str) -> None: ...


class SourceReaderV2(Protocol):
    def read(self, value: str | Path, *, display_name: str | None = None) -> RawSourceV2: ...


class OCREngine(Protocol):
    def extract(self, page: OCRPageInput, *, config: OCRConfig, budget: BudgetLedger) -> OCRResult: ...


class DocumentParserV2(Protocol):
    def parse(self, raw: RawSourceV2, *, candidate_version_id: str,
              config: ParseConfig, ocr: OCREngine | None = None) -> ParseResult: ...


@dataclass(frozen=True, kw_only=True)
class MaskConfig:
    detector_name: str
    detector_version: str
    pii_types: tuple[str, ...]
    placeholder_policy_id: str


class PIIMasker(Protocol):
    def mask(self, blocks: Sequence[Block], *, config: MaskConfig) -> MaskResult: ...


class ChunkerV2(Protocol):
    def chunk(self, blocks: Sequence[SafeBlock], *, units: Sequence[UnitRevision],
              assessments: Sequence[QualityAssessment], config: ChunkingConfig) -> tuple[ChunkV2, ...]: ...


@dataclass(frozen=True, kw_only=True)
class IngestConfig:
    """Every processing-affecting choice must participate in reuse fingerprint."""
    data_dir: str
    parse: ParseConfig
    ocr: OCRConfig | None
    mask: MaskConfig
    validation: ValidationConfig
    numeric: NumericConfig
    dedup: DedupConfig
    conflict: ConflictConfig
    chunking: ChunkingConfig
    enrichment_config_id: str
    index_config_id: str
    budget_policy_id: str


@dataclass(frozen=True, kw_only=True)
class IngestReportV2:
    run_id: str
    source_id: str
    document_id: str | None
    version_id: str | None
    processing_id: str | None
    status: Literal["duplicate", "needs_review", "activated", "failed"]
    new_chunk_count: int
    issue_ids: tuple[str, ...]
    review_ids: tuple[str, ...]
    generation_id: str | None
    safe_errors: tuple[str, ...] = ()


class IngestionCoordinator(Protocol):
    def ingest(self, value: str | Path, *, hint: IdentityHint,
               change: ChangeRequest, config: IngestConfig) -> IngestReportV2: ...


__all__ += [
    'RawSourceV2',
    'OCRConfig',
    'ParseConfig',
    'OCRPageInput',
    'OCRRegion',
    'OCRResult',
    'BudgetLedger',
    'SourceReaderV2',
    'OCREngine',
    'DocumentParserV2',
    'MaskConfig',
    'PIIMasker',
    'ChunkerV2',
    'IngestConfig',
    'IngestReportV2',
    'IngestionCoordinator',
]
