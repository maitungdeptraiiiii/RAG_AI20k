"""Data models and exception types for parsing and chunking.

Re-exports schema classes from `rag.schema` to ensure 100% compliance
with the team Sprint 1 contract.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from rag.schema import (
    Chunk,
    Page,
    make_chunk_id,
    make_doc_id,
    nfc,
)


class ParseError(Exception):
    """Raised when parsing a PDF, web document, or text file fails."""

    def __init__(self, code: str, message: str, status: int = 422):
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message
        self.status = status


@dataclass(frozen=True)
class TextUnit:
    """A logical segment of text with page and section tracking.
    
    Used internally during parsing and chunking before constructing final Chunks.
    """
    text: str
    page: int | None = None
    section: str | None = None
    pages: tuple[int, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.pages and self.page is not None:
            object.__setattr__(self, "pages", (self.page,))
        elif self.pages and self.page is None:
            object.__setattr__(self, "page", self.pages[0])


__all__ = [
    "Chunk",
    "Page",
    "ParseError",
    "TextUnit",
    "make_chunk_id",
    "make_doc_id",
    "nfc",
]
