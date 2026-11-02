"""Parsing and Chunking module for Team 4.2 RAG pipeline.

Strictly adheres to `rag.schema`:
- Output of Parsing: `list[Page]`
- Input of Chunking: `list[Page]`
- Output of Chunking: `list[Chunk]`
"""

from .models import (
    Chunk,
    Page,
    ParseError,
    TextUnit,
    make_chunk_id,
    make_doc_id,
    nfc,
)
from .pdf_parser import load_pdf, parse_pdf
from .web_parser import load_text, load_url, parse_web
from .chunker import chunk_document, make_chunks, normalize_text

__all__ = [
    "Chunk",
    "Page",
    "ParseError",
    "TextUnit",
    "chunk_document",
    "load_pdf",
    "load_text",
    "load_url",
    "make_chunk_id",
    "make_chunks",
    "make_doc_id",
    "nfc",
    "normalize_text",
    "parse_pdf",
    "parse_web",
]
