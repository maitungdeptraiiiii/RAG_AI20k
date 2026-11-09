"""Streaming file SHA-256 and canonical JSON fingerprints. No OCR dependencies."""

from __future__ import annotations

import hashlib
from pathlib import Path

from rag.models.common import canonical_json


def file_checksum(path: str | Path) -> str:
    """Hash file bytes, independent of filename; supports large PDFs."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(part)
    return digest.hexdigest()


def canonical_checksum(payload: object) -> str:
    """Hash a semantic payload/config; caller chooses the meaningful fields.

    For content dedup, exclude occurrence IDs/paths and include all source
    structure/images. Matching extracted text alone is only a candidate match.
    """
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
