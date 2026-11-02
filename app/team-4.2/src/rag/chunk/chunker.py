"""Sentence-aware document chunking conforming strictly to `rag.schema`.

Supports cross-page sentence stitching, section heading tracking,
and sliding-window overlap while maintaining exact `page_start`, `page_end`,
and `chunk_id` metadata.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from rag.schema import Chunk, Page, make_chunk_id, nfc


# Patterns for detecting headings in Vietnamese legal and general documents
SECTION_PATTERN = re.compile(
    r"^(?:(?:Chương|Điều|Mục|Phần)\s+[0-9IVXLCDM]+|#+\s+|[0-9]+\.\s+[A-ZÀ-Ỹ])",
    re.IGNORECASE,
)


def normalize_text(text: str) -> str:
    """Normalize text into Unicode NFC, clean whitespace and null characters."""
    text = unicodedata.normalize("NFC", text).replace("\x00", "")
    lines = [re.sub(r"[^\S\n]+", " ", line).strip() for line in text.splitlines()]
    lines = [line for line in lines if line]
    return "\n".join(lines).strip()


def split_into_sentences(text: str) -> list[str]:
    """Split text along natural sentence or structural clause boundaries.

    Splits by:
    - Double newlines (paragraphs)
    - Sentence enders (., !, ?) preceded by non-digit/non-space character
      (avoids splitting 'Điều 15.' or 'Khoản 1.')
    - Semicolon list terminators (;) at line ends (legal clauses)
    """
    pattern = r"(?<=[^0-9\s][.!?])\s+|\n{2,}|(?<=;)\n+"
    sentences = [p.strip() for p in re.split(pattern, text) if p.strip()]
    return sentences


class _SentenceSpan:
    """An internal representation of a sentence with page and section origin."""

    __slots__ = ("text", "pages", "section", "is_section_header")

    def __init__(
        self,
        text: str,
        pages: list[int],
        section: str | None = None,
        is_section_header: bool = False,
    ) -> None:
        self.text = text
        self.pages = pages
        self.section = section
        self.is_section_header = is_section_header


def _prepare_sentence_spans(pages: list[Page]) -> list[_SentenceSpan]:
    """Extract and cross-stitch sentences across pages."""
    spans: list[_SentenceSpan] = []
    current_section: str | None = None
    pending_span: _SentenceSpan | None = None

    for page in pages:
        page_num = page.page
        page_text = page.text.strip()
        if not page_text:
            continue

        raw_sentences = split_into_sentences(page_text)
        if not raw_sentences:
            continue

        for i, sent in enumerate(raw_sentences):
            first_line = sent.splitlines()[0].strip()
            is_header = bool(SECTION_PATTERN.match(first_line))
            if is_header:
                current_section = first_line[:150].strip()

            # Cross-page stitching:
            # If we have a pending sentence from previous page that lacked terminal punct
            # and current sentence is not a new section header
            if pending_span is not None:
                if not is_header:
                    stitched_text = pending_span.text
                    if stitched_text.endswith("-"):
                        stitched_text = stitched_text[:-1] + sent
                    else:
                        stitched_text = stitched_text + " " + sent

                    stitched_pages = list(pending_span.pages)
                    if page_num is not None and page_num not in stitched_pages:
                        stitched_pages.append(page_num)

                    pending_span = _SentenceSpan(
                        text=stitched_text,
                        pages=stitched_pages,
                        section=pending_span.section or current_section,
                        is_section_header=pending_span.is_section_header,
                    )
                else:
                    spans.append(pending_span)
                    sent_pages = [page_num] if page_num is not None else []
                    pending_span = _SentenceSpan(
                        text=sent,
                        pages=sent_pages,
                        section=current_section,
                        is_section_header=True,
                    )
                continue

            # Check if this is the last sentence on page and lacks terminal punctuation
            is_last_sentence_on_page = (i == len(raw_sentences) - 1)
            is_sentence_cut = is_last_sentence_on_page and not re.search(r"[.!?:]\s*$", sent)

            sent_pages = [page_num] if page_num is not None else []
            span = _SentenceSpan(
                text=sent,
                pages=sent_pages,
                section=current_section,
                is_section_header=is_header,
            )

            if is_sentence_cut and page_num is not None:
                pending_span = span
            else:
                spans.append(span)

    if pending_span is not None:
        spans.append(pending_span)

    return spans


def chunk_document(
    pages: list[Page],
    size: int = 1200,
    overlap: int = 200,
) -> list[Chunk]:
    """Segment a list of schema `Page` objects into schema `Chunk` objects.

    Uses recursive sentence-aware accumulation with semantic overlap:
    - Flushes previous chunk when a new section starts (e.g. Điều, Chương).
    - Preserves sentence integrity unless an individual sentence exceeds `size`.
    - Correctly sets `page_start` and `page_end` for single-page and cross-page spans.
    - Sets `page_start=None, page_end=None` for web/plain text documents.
    - Assigns deterministic unique `chunk_id` using `make_chunk_id(doc_id, index)`.

    Args:
        pages: List of `Page` objects from parsing.
        size: Target chunk size in characters (default 1200).
        overlap: Character overlap between consecutive chunks (default 200).

    Returns:
        List of `Chunk` objects conforming strictly to `rag.schema`.
    """
    if not pages:
        return []

    if not 0 <= overlap < size:
        raise ValueError(f"overlap ({overlap}) phải >= 0 và < size ({size})")

    doc_id = pages[0].doc_id
    source = pages[0].source
    is_paged = pages[0].page is not None

    spans = _prepare_sentence_spans(pages)
    if not spans:
        return []

    chunks: list[Chunk] = []
    chunk_index = 0
    step = size - overlap

    def _emit_chunk(text: str, page_nums: list[int], section: str | None) -> None:
        nonlocal chunk_index
        clean_text = nfc(text.strip())
        if not clean_text:
            return

        if is_paged and page_nums:
            p_start = min(page_nums)
            p_end = max(page_nums)
        else:
            p_start = None
            p_end = None

        cid = make_chunk_id(doc_id, chunk_index)
        chunks.append(
            Chunk(
                chunk_id=cid,
                doc_id=doc_id,
                source=source,
                page_start=p_start,
                page_end=p_end,
                section=section,
                text=clean_text,
            )
        )
        chunk_index += 1

    cur_spans: list[_SentenceSpan] = []
    cur_len = 0

    for span in spans:
        span_len = len(span.text)

        # Flush if new section starts (and current chunk is non-empty)
        if span.is_section_header and cur_spans:
            accum_text = "\n".join(s.text for s in cur_spans)
            accum_pages = [p for s in cur_spans for p in s.pages]
            accum_section = cur_spans[0].section or cur_spans[-1].section
            _emit_chunk(accum_text, accum_pages, accum_section)
            cur_spans = []
            cur_len = 0

        # Handle unusually large single sentence exceeding chunk size
        if span_len > size:
            if cur_spans:
                accum_text = "\n".join(s.text for s in cur_spans)
                accum_pages = [p for s in cur_spans for p in s.pages]
                accum_section = cur_spans[0].section or cur_spans[-1].section
                _emit_chunk(accum_text, accum_pages, accum_section)
                cur_spans = []
                cur_len = 0

            # Fallback to sliding window for this large sentence
            sent_text = span.text
            for start in range(0, span_len, step):
                end = min(start + size, span_len)
                slice_text = sent_text[start:end]
                _emit_chunk(slice_text, span.pages, span.section)
                if end == span_len:
                    break
            continue

        delimiter_len = 1 if cur_spans else 0
        if cur_len + span_len + delimiter_len > size and cur_spans:
            accum_text = "\n".join(s.text for s in cur_spans)
            accum_pages = [p for s in cur_spans for p in s.pages]
            accum_section = cur_spans[0].section or cur_spans[-1].section
            _emit_chunk(accum_text, accum_pages, accum_section)

            # Carry over trailing sentences for smooth overlap
            overlap_spans: list[_SentenceSpan] = []
            overlap_len = 0
            for s in reversed(cur_spans):
                add_len = len(s.text) + (1 if overlap_spans else 0)
                if overlap_len + add_len <= overlap:
                    overlap_spans.insert(0, s)
                    overlap_len += add_len
                else:
                    break

            cur_spans = overlap_spans
            cur_len = sum(len(s.text) for s in cur_spans) + max(0, len(cur_spans) - 1)

        cur_spans.append(span)
        cur_len += span_len + (1 if len(cur_spans) > 1 else 0)

    if cur_spans:
        accum_text = "\n".join(s.text for s in cur_spans)
        accum_pages = [p for s in cur_spans for p in s.pages]
        accum_section = cur_spans[0].section or cur_spans[-1].section
        _emit_chunk(accum_text, accum_pages, accum_section)

    return chunks


def make_chunks(
    pages: list[Page] | None = None,
    document_id: str | None = None,
    units: list[Any] | None = None,
    size: int = 1200,
    overlap: int = 200,
) -> list[Chunk]:
    """Backwards-compatible alias for `chunk_document`."""
    if pages is not None:
        return chunk_document(pages, size=size, overlap=overlap)

    if units is not None:
        doc_id = document_id or "legacy_doc"
        converted_pages = [
            Page(
                doc_id=doc_id,
                source="legacy",
                page=u.page,
                text=u.text,
            )
            for u in units
        ]
        return chunk_document(converted_pages, size=size, overlap=overlap)

    return []
