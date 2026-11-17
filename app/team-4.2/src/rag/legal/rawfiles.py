"""Lưu văn bản gốc theo nội dung: mỗi checksum một file bất biến, không bao giờ ghi đè."""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
from pathlib import Path


def content_path(raw_dir: Path, key: str, checksum: str) -> Path:
    return Path(raw_dir) / re.sub(r"[^A-Za-z0-9_-]+", "_", key) / f"{checksum}.txt"


def _intact(path: Path, checksum: str) -> bool:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest() == checksum
    except OSError:
        return False


def write_text(raw_dir: Path, key: str, text: str) -> tuple[Path, str]:
    checksum = hashlib.sha256(text.encode("utf-8")).hexdigest()
    path = content_path(raw_dir, key, checksum)
    if not _intact(path, checksum):
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(text.encode("utf-8"))
            os.replace(tmp, path)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise
    return path, checksum


__all__ = ["content_path", "write_text"]
