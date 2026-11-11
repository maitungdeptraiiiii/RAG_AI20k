"""Tương thích ngược: parser bảng đã chuyển sang ``rag.ingest.tables`` (W02-02b)."""

from rag.ingest.tables import ParsedTable, parse_csv, parse_xlsx

__all__ = ["ParsedTable", "parse_csv", "parse_xlsx"]
