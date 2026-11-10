"""Lưu văn bản gốc theo nội dung: mỗi checksum một file bất biến, không bao giờ ghi đè."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path


def content_path(raw_dir: Path, key: str, checksum: str) -> Path:
    return Path(raw_dir) / re.sub(r"[^A-Za-z0-9_-]+", "_", key) / f"{checksum}.txt"


def write_text(raw_dir: Path, key: str, text: str) -> tuple[Path, str]:
    checksum = hashlib.sha256(text.encode("utf-8")).hexdigest()
    path = content_path(raw_dir, key, checksum)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="")
    return path, checksum


__all__ = ["content_path", "write_text"]
