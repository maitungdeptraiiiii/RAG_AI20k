"""Functional interfaces and handoff data; protocols do not implement backends."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, TYPE_CHECKING
from rag.models.quality import QualityIssue
from rag.models.results import ResolvedScope


if TYPE_CHECKING:
    from rag.retrieve.hybrid import RetrievalResult


@dataclass(frozen=True, kw_only=True)
class RetrievalResultV2:
    retrieval: RetrievalResult
    scope: ResolvedScope
    warnings: tuple[QualityIssue, ...] = ()


class ScopedRetriever(Protocol):
    def retrieve(self, query: str, *, scope: ResolvedScope, k: int = 5,
                 mode: str = "hybrid", rerank: bool = True) -> RetrievalResultV2: ...


__all__ = [
    'RetrievalResultV2',
    'ScopedRetriever',
]
