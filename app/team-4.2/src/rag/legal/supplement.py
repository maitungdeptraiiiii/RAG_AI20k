"""Nạp văn bản đã tải (bộ bổ sung: `supplements/<phạm vi>/fetch-report.json`) vào kho luật có phiên bản.

Qua `SnapshotManager.write`: chép snapshot hiện tại sang snapshot mới, thêm văn bản, dựng lại phiên bản, kiểm tra rồi
mới đổi con trỏ CURRENT (snapshot cũ giữ nguyên, quay lại được). Chỉ nhận văn bản `downloaded` có tệp gốc đúng
checksum; văn bản đã có trong kho không nạp lại. Không gọi LLM, không duyệt nội dung pháp lý.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from rag.legal.models import LegalDocument
from rag.legal.service import LegalService
from rag.legal.snapshots import SnapshotManager, WriteResult
from rag.legal.store import decode


def _candidates(report_path: Path, present: set[str]) -> tuple[list[LegalDocument], dict[str, str]]:
    data = json.loads(Path(report_path).read_text(encoding="utf-8"))
    docs, skipped = [], {}
    for key, entry in (data.get("documents") or {}).items():
        raw = entry.get("legal_document")
        if entry.get("status") != "downloaded" or not raw:
            skipped[key] = f"status={entry.get('status')}"
            continue
        path = Path(raw.get("raw_text_path") or "")
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != raw.get("raw_checksum"):
            skipped[key] = "checksum: tệp gốc không có hoặc không khớp"
            continue
        if key in present:
            skipped[key] = "already_present"
            continue
        docs.append(decode(LegalDocument, raw))
    return docs, skipped


def import_supplement(manager: SnapshotManager, report_path: Path, *, actor: str) -> WriteResult[dict]:
    """Snapshot mới có thêm các văn bản hợp lệ của báo cáo tải. Không có văn bản nào để nạp -> ValueError (không tạo
    snapshot), thông báo nêu lý do từng văn bản."""
    present = {d.document_key for d in manager.store().documents()}
    docs, skipped = _candidates(report_path, present)
    if not docs:
        raise ValueError("Không có văn bản nào để nạp: " + "; ".join(f"{k}: {v}" for k, v in skipped.items()))

    def add(svc: LegalService) -> dict:
        for doc in docs:
            svc.store.upsert_document(doc)
        return {"imported": [d.document_key for d in docs], "skipped": skipped}
    return manager.write(f"supplement:{Path(report_path).parent.name}", actor, add)


__all__ = ["import_supplement"]
