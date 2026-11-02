"""Schema chung cho Sprint 1 — Baseline Hybrid RAG.

Mọi module trao đổi dữ liệu qua các kiểu trong file này (xem docs/phan_cong_sprint1.md, mục 3).
Thay đổi file này phải báo cả nhóm và TV5 duyệt.

Luồng dữ liệu:

    Parsing  (TV1)  path/url              -> list[Page]
    Chunking (TV1)  list[Page]            -> list[Chunk]
    BM25     (TV2)  build(list[Chunk]); search(query, k)   -> list[Hit] (arm="bm25")
    Dense    (TV3)  build(list[Chunk]); search(query, k)   -> list[Hit] (arm="dense")
    RRF      (TV2)  dict[arm, list[Hit]], k=60             -> list[Hit] (arm="fused")
    Rerank   (TV2)  query, top-N fused Hit, chunks, k      -> list[Hit] (arm="rerank")
                    (lỗi hoặc tắt rerank -> giữ nguyên fused Hit, arm="fused")
    Guardrail trước LLM (TV5)  query, list[Hit]            -> cho qua | Answer.refusal(...)
    Generation (TV4)  query, list[ContextBlock]            -> text có [n]
    Citation   (TV4)  text, list[ContextBlock]             -> Answer
    Guardrail sau LLM (TV5)  Answer                        -> Answer cuối
    Pipeline   (TV5)  ingest(path/url); ask(query)         -> Answer
    Eval       (TV3)  list[Question] + Answer.hits         -> Recall@5, MRR@5
"""

from __future__ import annotations

import hashlib
import unicodedata
from dataclasses import asdict, dataclass, field
from collections.abc import Mapping
from typing import Any, Literal, Protocol, get_args

# ---------------------------------------------------------------------------
# Quy ước chung
# ---------------------------------------------------------------------------

REFUSAL = "Không có trong tài liệu."
"""Câu từ chối thống nhất, dùng ở Generation và cả hai tầng Guardrail."""

Arm = Literal["bm25", "dense", "fused", "rerank"]
ARMS: tuple[str, ...] = get_args(Arm)

QuestionType = Literal["lookup", "paraphrase", "multi", "out_of_scope"]
QUESTION_TYPES: tuple[str, ...] = get_args(QuestionType)


def nfc(text: str) -> str:
    """Chuẩn hoá Unicode NFC. Mọi text phải đi qua hàm này trước khi xử lý."""
    return unicodedata.normalize("NFC", text)


def make_doc_id(content: bytes | str) -> str:
    """doc_id = hash nội dung, ổn định khi ingest lại cùng tài liệu.

    PDF: truyền bytes của file. URL/TXT: truyền text đã chuẩn hoá NFC.
    """
    if isinstance(content, str):
        content = nfc(content).encode("utf-8")
    return hashlib.sha1(content).hexdigest()[:16]


def make_chunk_id(doc_id: str, index: int) -> str:
    """chunk_id duy nhất toàn hệ thống: '<doc_id>:<số thứ tự chunk trong tài liệu>'."""
    if index < 0:
        raise ValueError(f"index phải >= 0, nhận {index}")
    return f"{doc_id}:{index:04d}"


def _require(cond: bool, msg: str) -> None:
    if not cond:
        raise ValueError(msg)


def _set_nfc(obj: Any, *names: str) -> None:
    """Chuẩn hoá NFC các trường text của dataclass (kể cả frozen)."""
    for name in names:
        value = getattr(obj, name)
        if value is not None:
            object.__setattr__(obj, name, nfc(value))


# ---------------------------------------------------------------------------
# Ingest: Parsing -> Chunking (TV1)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Page:
    """Một trang (PDF) hoặc toàn bộ tài liệu (URL/TXT) sau khi parse."""

    doc_id: str          # make_doc_id(...), ổn định khi ingest lại
    source: str          # tên file hoặc URL
    page: int | None     # đánh số từ 1; None với URL/TXT
    text: str            # tự chuẩn hoá NFC

    def __post_init__(self) -> None:
        _require(bool(self.doc_id), "Page.doc_id không được rỗng")
        _require(bool(self.source), "Page.source không được rỗng")
        _require(self.page is None or self.page >= 1, f"Page.page phải >= 1, nhận {self.page}")
        _set_nfc(self, "source", "text")

    @property
    def is_empty(self) -> bool:
        """True nếu trang không có text (thường là PDF scan) — parser cần cảnh báo."""
        return not self.text.strip()


@dataclass(frozen=True)
class Chunk:
    """Đơn vị được index và retrieve."""

    chunk_id: str             # make_chunk_id(doc_id, i), duy nhất toàn hệ thống
    doc_id: str
    source: str
    page_start: int | None    # None với URL/TXT
    page_end: int | None      # = page_start nếu chunk nằm gọn trong một trang
    section: str | None       # heading / mục gần nhất
    text: str                 # text gốc (NFC); Dense encode trường này, BM25 tự tách từ

    def __post_init__(self) -> None:
        _require(bool(self.chunk_id), "Chunk.chunk_id không được rỗng")
        _require(bool(self.doc_id), "Chunk.doc_id không được rỗng")
        _require(
            (self.page_start is None) == (self.page_end is None),
            "Chunk.page_start và page_end phải cùng None hoặc cùng có giá trị",
        )
        if self.page_start is not None and self.page_end is not None:
            _require(self.page_start >= 1, f"Chunk.page_start phải >= 1, nhận {self.page_start}")
            _require(
                self.page_start <= self.page_end,
                f"Chunk.page_start ({self.page_start}) > page_end ({self.page_end})",
            )
        _set_nfc(self, "source", "section", "text")

    def covers_page(self, page: int) -> bool:
        """Chunk có chứa nội dung của trang `page` không (dùng để quy đổi gold)."""
        if self.page_start is None or self.page_end is None:
            return False
        return self.page_start <= page <= self.page_end

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Chunk:
        return cls(**d)


# ---------------------------------------------------------------------------
# Retrieval: BM25, Dense (TV2, TV3) -> RRF (TV2)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Hit:
    """Một kết quả retrieve. Danh sách Hit luôn sắp theo rank tăng dần."""

    chunk_id: str
    score: float         # thang điểm riêng của từng arm, KHÔNG so sánh giữa các arm
    rank: int            # bắt đầu từ 1
    arm: Arm             # "bm25" | "dense" | "fused"

    def __post_init__(self) -> None:
        _require(bool(self.chunk_id), "Hit.chunk_id không được rỗng")
        _require(self.rank >= 1, f"Hit.rank phải >= 1, nhận {self.rank}")
        _require(self.arm in ARMS, f"Hit.arm phải thuộc {ARMS}, nhận {self.arm!r}")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Hit:
        return cls(**d)


class Retriever(Protocol):
    """Interface chung cho BM25Index (TV2) và VectorIndex (TV3)."""

    def build(self, chunks: list[Chunk]) -> None:
        """Index thêm chunk. Chunk có chunk_id đã tồn tại thì bỏ qua (không nhân đôi)."""
        ...

    def search(self, query: str, k: int) -> list[Hit]:
        """Trả tối đa k Hit, rank 1..n, cùng một giá trị arm."""
        ...


class Reranker(Protocol):
    """Interface chung cho JevReranker và NoopReranker (tắt rerank).

    Hit trả về có arm="rerank" và score = xác suất liên quan trong [0, 1]; thang điểm này
    khác điểm RRF, nên guardrail đặt ngưỡng riêng cho từng loại.
    Nếu rerank bị tắt hoặc lỗi, Hit giữ nguyên arm="fused" để guardrail biết dùng ngưỡng RRF.
    """

    name: str   # "none" | "jev"

    def rerank(
        self, query: str, hits: list[Hit], chunks: Mapping[str, Chunk], k: int
    ) -> list[Hit]: ...


# ---------------------------------------------------------------------------
# Generation + Citation (TV4), Guardrail (TV5)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ContextBlock:
    """Một đoạn context đưa cho LLM, đánh số [n] (n bắt đầu từ 1).

    Generation dùng để dựng prompt; Citation dùng để ánh xạ [n] -> chunk.
    """

    n: int
    chunk: Chunk

    def __post_init__(self) -> None:
        _require(self.n >= 1, f"ContextBlock.n phải >= 1, nhận {self.n}")


class LLM(Protocol):
    """Interface cho LLMClient (TV4). Test dùng LLM giả cài đặt cùng interface."""

    def complete(self, prompt: str) -> str: ...


@dataclass(frozen=True)
class Citation:
    n: int               # số [n] trong câu trả lời
    chunk_id: str
    source: str
    page: int | None     # page_start của chunk; None với URL/TXT
    quote: str           # trích đoạn (NFC)

    def __post_init__(self) -> None:
        _require(self.n >= 1, f"Citation.n phải >= 1, nhận {self.n}")
        _require(bool(self.chunk_id), "Citation.chunk_id không được rỗng")
        _set_nfc(self, "source", "quote")

    @classmethod
    def from_block(cls, block: ContextBlock, quote: str | None = None) -> Citation:
        """Tạo Citation từ ContextBlock; mặc định trích 200 ký tự đầu của chunk."""
        c = block.chunk
        return cls(
            n=block.n,
            chunk_id=c.chunk_id,
            source=c.source,
            page=c.page_start,
            quote=quote if quote is not None else c.text[:200],
        )


@dataclass
class Answer:
    """Đầu ra cuối của pipeline.ask(query)."""

    text: str
    citations: list[Citation]
    refused: bool
    hits: list[Hit] = field(default_factory=list)   # fused hits, để debug / eval

    def __post_init__(self) -> None:
        self.text = nfc(self.text)
        if self.refused:
            _require(self.text == REFUSAL, f"Answer từ chối phải có text = {REFUSAL!r}")
            _require(not self.citations, "Answer từ chối không được có citation")

    @classmethod
    def refusal(cls, hits: list[Hit] | None = None) -> Answer:
        """Câu trả lời từ chối chuẩn (Guardrail trước/sau LLM)."""
        return cls(text=REFUSAL, citations=[], refused=True, hits=list(hits or []))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Answer:
        return cls(
            text=d["text"],
            citations=[Citation(**c) for c in d.get("citations", [])],
            refused=d["refused"],
            hits=[Hit.from_dict(h) for h in d.get("hits", [])],
        )


# ---------------------------------------------------------------------------
# Evaluation (TV3) — định dạng eval/questions.jsonl
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GoldRef:
    """Đáp án đúng trỏ tới source + page (hoặc source + section), KHÔNG trỏ tới chunk_id.

    Nhờ vậy đổi cách chunk thì gold vẫn đúng; lúc eval mới quy đổi bằng `matches`.
    """

    source: str
    page: int | None = None
    section: str | None = None

    def __post_init__(self) -> None:
        _require(bool(self.source), "GoldRef.source không được rỗng")
        _require(
            self.page is not None or self.section is not None,
            "GoldRef cần ít nhất page hoặc section",
        )
        _set_nfc(self, "source", "section")

    def matches(self, chunk: Chunk) -> bool:
        if chunk.source != self.source:
            return False
        if self.page is not None:
            return chunk.covers_page(self.page)
        return chunk.section is not None and self.section == chunk.section


@dataclass(frozen=True)
class Question:
    """Một dòng trong eval/questions.jsonl."""

    id: str
    question: str
    type: QuestionType
    author: str                       # "TV1".."TV5"
    gold: tuple[GoldRef, ...] = ()    # có thể nhiều đáp án đúng; rỗng với out_of_scope
    reference: str | None = None      # đáp án mẫu cho RAGAS: LLM soạn nháp từ trang gold,
                                      # người viết câu hỏi kiểm tra lại; None nếu chưa kiểm tra

    def __post_init__(self) -> None:
        _require(bool(self.id), "Question.id không được rỗng")
        _require(
            self.type in QUESTION_TYPES,
            f"Question.type phải thuộc {QUESTION_TYPES}, nhận {self.type!r}",
        )
        if self.type == "out_of_scope":
            _require(not self.gold, f"{self.id}: câu out_of_scope không được có gold")
            _require(self.reference is None, f"{self.id}: câu out_of_scope không được có reference")
        else:
            _require(bool(self.gold), f"{self.id}: câu {self.type} phải có ít nhất 1 gold")
        if self.reference is not None:
            _require(bool(self.reference.strip()), f"{self.id}: reference không được rỗng, dùng None")
        _set_nfc(self, "question", "reference")

    @property
    def in_scope(self) -> bool:
        """Câu out_of_scope không tính vào Recall/MRR, chỉ dùng đo Guardrail."""
        return self.type != "out_of_scope"

    def is_relevant(self, chunk: Chunk) -> bool:
        return any(g.matches(chunk) for g in self.gold)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Question:
        return cls(
            id=d["id"],
            question=d["question"],
            type=d["type"],
            author=d["author"],
            gold=tuple(GoldRef(**g) for g in d.get("gold", [])),
            reference=d.get("reference"),
        )

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["gold"] = [{k: v for k, v in g.items() if v is not None} for g in d["gold"]]
        if d["reference"] is None:
            del d["reference"]
        return d


__all__ = [
    "ARMS",
    "QUESTION_TYPES",
    "REFUSAL",
    "LLM",
    "Answer",
    "Arm",
    "Chunk",
    "Citation",
    "ContextBlock",
    "GoldRef",
    "Hit",
    "Page",
    "Question",
    "QuestionType",
    "Reranker",
    "Retriever",
    "make_chunk_id",
    "make_doc_id",
    "nfc",
]
