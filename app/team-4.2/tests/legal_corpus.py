"""Tìm văn bản luật trong kho cục bộ cho test đối chiếu trích dẫn / giá trị luật.

Kho mà ứng dụng dùng là `app/team-4.2/data/team-4.2/legal/raw/` (Settings.data_dir = data/team-4.2, chạy từ
app/team-4.2). Thư mục `data/team-4.2/legal/raw/` ở gốc repo là bản cũ, ít văn bản hơn (không có nghị định): chỉ dùng
khi kho ứng dụng thiếu. Tên thư mục theo `rag.legal.rawfiles.content_path`."""
from __future__ import annotations

import re
from pathlib import Path

APP_RAW = Path(__file__).resolve().parents[1] / "data" / "team-4.2" / "legal" / "raw"
ROOT_RAW = Path(__file__).resolve().parents[3] / "data" / "team-4.2" / "legal" / "raw"
ROOTS = [r for r in (APP_RAW, ROOT_RAW) if r.is_dir()]


def _folder(key: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", key)


def law_text(pid_or_key: str) -> str | None:
    """`bo-luat:91/2015/QH13#d468.k1` hoặc `nghi-dinh:74/2024/NĐ-CP` -> nội dung văn bản, None nếu kho không có."""
    key = pid_or_key.split("#", 1)[0]
    for root in ROOTS:
        files = sorted((root / _folder(key)).glob("*.txt"))
        if files:
            return files[0].read_text(encoding="utf-8")
    return None
