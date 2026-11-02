"""Standalone Parsing and Chunking module for RAG pipelines.

Contains boundary-aware document extraction (PDF, Web) and sliding-window chunking
with exact metadata (page, section, chunk_id).
"""

from .models import ParseError, TextUnit
from .chunker import make_chunks, normalize_text
from .pdf_parser import parse_pdf
from .web_parser import parse_web

__all__ = [
    "ParseError",
    "TextUnit",
    "make_chunks",
    "normalize_text",
    "parse_pdf",
    "parse_web",
]

