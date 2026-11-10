"""Bản nháp upload văn bản pháp luật: một thư mục mỗi bản nháp, `draft.json` + file gốc (spec §4.0).

Bố cục dưới `root` (thường là `legal_dir/uploads`):
- `<upload_id>/draft.json`       trạng thái bản nháp (ghi bằng file tạm + `os.replace`)
- `<upload_id>/original<ext>`    file người dùng tải lên (nguồn file), để dựng lại ảnh trang
"""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path
from typing import Literal

from rag.legal.store import decode, encode

DraftState = Literal["step1", "step2", "step3", "queued", "building", "published",
                     "failed", "stale", "duplicate", "cancelled"]
INTERRUPTED = "server khởi động lại giữa chừng"
UPLOAD_ID_RE = re.compile(r"u\d{14}-[0-9a-f]{6}")      # "u" + yyyymmddHHMMSS + "-" + 6 hex (UploadService._new_id)


@dataclass
class Draft:
    upload_id: str
    created_at: datetime
    state: DraftState
    origin: Literal["file", "url"]
    source_name: str                    # tên file hoặc URL
    text: str                           # đã chuẩn hoá, KHÔNG che PII
    checksum: str
    pages: list[dict]                   # page_details (file) | [] (url)
    structure: dict                     # encode(StructureCheck)
    fields: dict[str, dict]             # tên -> encode(FieldValue)
    source_verified: bool
    base_snapshot_id: str
    duplicate: dict | None              # {"document_key","checksum","text_source","diff","replace_allowed",...}
    replace: bool = False
    preview: dict | None = None         # encode(Preview), gán ở bước ②
    confirmations: dict[str, dict] = field(default_factory=dict)   # "step1"/"step2"/"step3" -> {"by","at","note"}
    snapshot_id: str | None = None
    error: str | None = None
    progress: dict | None = None        # {"stage", "done", "total"}
    result: dict | None = None          # sau khi công bố: {"laws": [{"document_key","title","changed_provisions",...}]}
    job_id: str | None = None           # việc ghi gần nhất trong hàng đợi (chỉ sống trong tiến trình server)
    index_error: str | None = None      # kho đã công bố nhưng dựng chỉ mục lỗi (chat giữ cặp cũ) -> "Dựng lại chỉ mục"


class DraftStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def folder(self, upload_id: str) -> Path:
        """Chỉ nhận id đúng dạng do `UploadService` sinh: không bao giờ thoát khỏi `root` ("C:foo", "..\\x")."""
        if not isinstance(upload_id, str) or not UPLOAD_ID_RE.fullmatch(upload_id):
            raise KeyError(upload_id)
        return self.root / upload_id

    def save_original(self, upload_id: str, src: Path, ext: str) -> Path:
        dst = self.folder(upload_id) / f"original{ext.lower()}"
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        return dst

    def original(self, upload_id: str) -> Path | None:
        return next(iter(sorted(self.folder(upload_id).glob("original*"))), None)

    def discard(self, upload_id: str) -> None:
        shutil.rmtree(self.folder(upload_id), ignore_errors=True)

    def save(self, draft: Draft) -> None:
        folder = self.folder(draft.upload_id)
        folder.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=folder, prefix="draft.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(encode(draft), f, ensure_ascii=False)
            os.replace(tmp, folder / "draft.json")
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise

    def load(self, upload_id: str) -> Draft:
        path = self.folder(upload_id) / "draft.json"
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise KeyError(upload_id) from None
        return decode(Draft, payload)

    def list(self) -> list[Draft]:
        out = []
        for path in self.root.glob("*/draft.json"):
            try:
                out.append(self.load(path.parent.name))
            except (KeyError, ValueError):
                continue
        return sorted(out, key=lambda d: d.created_at, reverse=True)

    def mark_interrupted(self) -> list[str]:
        ids = []
        for d in self.list():
            if d.state in ("queued", "building"):
                self.save(replace(d, state="failed", error=INTERRUPTED))
                ids.append(d.upload_id)
        return ids


__all__ = ["Draft", "DraftState", "DraftStore", "INTERRUPTED", "UPLOAD_ID_RE"]
