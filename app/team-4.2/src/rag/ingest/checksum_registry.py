"""Persistent exact-file reuse gate, not a version resolver or pipeline runner.

Only a completed, compatible result with confirmed identity may be reused.
The coordinator calls mark_completed only AFTER its index generation activates.
This ledger does not reserve an ingestion job or prevent concurrent duplicate
work; generation/catalog activation must provide that concurrency guarantee.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from collections.abc import Iterator
from uuid import uuid4

from rag.ingest.checksum import canonical_checksum, file_checksum
from rag.models.common import nonempty, require


@dataclass(frozen=True, kw_only=True)
class CompletionReceipt:
    document_id: str
    version_id: str
    chunk_set_id: str
    generation_id: str

    def __post_init__(self) -> None:
        nonempty(self.document_id, self.version_id, self.chunk_set_id, self.generation_id)


@dataclass(frozen=True, kw_only=True)
class FileCheck:
    check_id: str
    raw_checksum: str
    status: Literal["new", "reusable"]
    reusable_check_id: str | None = None
    receipt: CompletionReceipt | None = None


class ChecksumRegistry:
    """Use a separate week-2 DATA_DIR path; connections close after each call."""

    def __init__(self, database: str | Path) -> None:
        self.database = Path(database)
        require(str(database) != ":memory:", "Use a filesystem database for persistent registry")
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS w02_file_checks (
                    check_id TEXT PRIMARY KEY,
                    source_path TEXT NOT NULL,
                    raw_checksum TEXT NOT NULL,
                    document_id TEXT,
                    metadata_checksum TEXT NOT NULL,
                    config_checksum TEXT NOT NULL,
                    state TEXT NOT NULL CHECK (state IN ('observed', 'completed', 'failed', 'reused')),
                    version_id TEXT,
                    chunk_set_id TEXT,
                    generation_id TEXT,
                    reused_from TEXT,
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS w02_file_checks_lookup
                ON w02_file_checks(raw_checksum, document_id, metadata_checksum, config_checksum, state)
            """)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.database, timeout=30)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def check_file(self, path: str | Path, *, document_id: str | None,
                   version_metadata: object, processing_config: object) -> FileCheck:
        """Record each upload; no reuse when identity is unconfirmed.

        metadata/config must contain the complete relevant request (effective
        dates, replacement mapping, parser/OCR/mask/chunk/enrichment/index config).
        Missing metadata and missing/empty config are rejected to avoid accidental reuse.
        Pass an immutable source snapshot; the coordinator must parse those bytes.
        """
        require(version_metadata is not None and processing_config is not None,
                "Metadata and processing config must be explicit")
        require(bool(processing_config), "Processing config must not be empty")
        if document_id is not None:
            nonempty(document_id)
        source_path = str(Path(path).resolve(strict=True))
        checksum = file_checksum(source_path)
        metadata_checksum = canonical_checksum(version_metadata)
        config_checksum = canonical_checksum(processing_config)
        check_id = str(uuid4())
        with self._connect() as conn:
            previous = None
            if document_id is not None:
                previous = conn.execute("""
                    SELECT * FROM w02_file_checks
                    WHERE raw_checksum = ? AND document_id = ? AND metadata_checksum = ?
                      AND config_checksum = ? AND state = 'completed'
                    ORDER BY rowid DESC LIMIT 1
                """, (checksum, document_id, metadata_checksum, config_checksum)).fetchone()
            conn.execute("""
                INSERT INTO w02_file_checks
                    (check_id, source_path, raw_checksum, document_id, metadata_checksum,
                     config_checksum, state, reused_from, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (check_id, source_path, checksum, document_id, metadata_checksum, config_checksum,
                  "reused" if previous else "observed", previous["check_id"] if previous else None,
                  datetime.now(timezone.utc).isoformat()))
        receipt = None if previous is None else CompletionReceipt(
            document_id=previous["document_id"], version_id=previous["version_id"],
            chunk_set_id=previous["chunk_set_id"], generation_id=previous["generation_id"])
        return FileCheck(check_id=check_id, raw_checksum=checksum,
                         status="reusable" if previous else "new",
                         reusable_check_id=previous["check_id"] if previous else None, receipt=receipt)

    def mark_completed(self, check_id: str, receipt: CompletionReceipt) -> None:
        """Trust boundary: caller supplies receipt of an ACTUALLY activated index.

        Re-checking the file detects changed uploads, but cannot prove a caller
        parsed the same bytes. Coordinator must use immutable source artifacts.
        """
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM w02_file_checks WHERE check_id = ?", (check_id,)).fetchone()
            require(row is not None, "Unknown file check")
            require(row["document_id"] is None or row["document_id"] == receipt.document_id,
                    "Completion document does not match confirmed identity")
            if row["state"] == "completed":
                require((row["document_id"], row["version_id"], row["chunk_set_id"], row["generation_id"]) ==
                        (receipt.document_id, receipt.version_id, receipt.chunk_set_id, receipt.generation_id),
                        "Completion receipt conflicts with existing result")
                return
            require(row["state"] == "observed", "Only an observed check can complete")
            require(file_checksum(row["source_path"]) == row["raw_checksum"], "Source changed during ingestion")
            cursor = conn.execute("""
                UPDATE w02_file_checks SET state = 'completed', document_id = ?, version_id = ?,
                    chunk_set_id = ?, generation_id = ? WHERE check_id = ? AND state = 'observed'
            """, (receipt.document_id, receipt.version_id, receipt.chunk_set_id, receipt.generation_id, check_id))
            require(cursor.rowcount == 1, "Check changed concurrently; retry with current state")

    def mark_failed(self, check_id: str) -> None:
        """No raw exception text is stored here; failed attempts are never reused."""
        with self._connect() as conn:
            row = conn.execute("SELECT state FROM w02_file_checks WHERE check_id = ?", (check_id,)).fetchone()
            require(row is not None, "Unknown file check")
            if row["state"] == "failed":
                return
            require(row["state"] == "observed", "Cannot fail an already finalized check")
            cursor = conn.execute("UPDATE w02_file_checks SET state = 'failed' WHERE check_id = ? AND state = 'observed'",
                                  (check_id,))
            require(cursor.rowcount == 1, "Check changed concurrently")

    def invalidate_generation(self, generation_id: str) -> int:
        """Call when results are withdrawn/unavailable; new checks must process again."""
        nonempty(generation_id)
        with self._connect() as conn:
            return conn.execute("UPDATE w02_file_checks SET state = 'failed' WHERE generation_id = ? AND state = 'completed'",
                                (generation_id,)).rowcount
