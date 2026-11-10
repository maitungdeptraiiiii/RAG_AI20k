"""Nhật ký phân tích hỏi đáp theo mốc (câu hỏi đã che PII): timeline, căn cứ + trạng thái, quy định chuyển tiếp + đánh
giá của LLM, mức chắc chắn sau khi backend hạ cấp. Dùng cho audit và làm dữ liệu cho bộ máy quy tắc chuyển tiếp sau này."""

from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any


class QALog:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as c:
            c.execute("CREATE TABLE IF NOT EXISTS qa_log (id TEXT PRIMARY KEY, asked_at TEXT, payload TEXT NOT NULL)")

    def record(self, entry: dict[str, Any]) -> str:
        log_id = uuid.uuid4().hex[:16]
        with sqlite3.connect(self.path) as c:
            c.execute("INSERT INTO qa_log VALUES (?, ?, ?)",
                      (log_id, str(entry.get("asked_at", "")), json.dumps(entry, ensure_ascii=False, default=str)))
        return log_id

    def get(self, log_id: str) -> dict[str, Any] | None:
        with sqlite3.connect(self.path) as c:
            row = c.execute("SELECT payload FROM qa_log WHERE id=?", (log_id,)).fetchone()
        return json.loads(row[0]) if row else None


__all__ = ["QALog"]
