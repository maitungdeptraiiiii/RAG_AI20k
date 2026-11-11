"""Nạp nhóm luật bất động sản (fixture phần 1) vào kho luật có phiên bản để demo phần 4.

    python scripts/team-4.2/seed_legal_demo.py            # vào DATA_DIR/legal theo .env

Đi qua `SnapshotManager.write` (staging -> build_all -> validate -> công bố) như mọi lần ghi kho khác.
Chạy lại khi mọi văn bản đã có cùng nội dung thì không tạo snapshot mới.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_TEAM = _ROOT / "app" / "team-4.2"
for p in (_TEAM / "src", _ROOT):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from rag.legal import rawfiles  # noqa: E402
from rag.legal.models import LegalDocument  # noqa: E402
from rag.legal.snapshots import SnapshotManager  # noqa: E402
from rag.legal.store import decode  # noqa: E402

DEFAULT_FIXTURES = _TEAM / "tests" / "fixtures" / "legal" / "realestate"


def _documents(fixtures: Path) -> list[tuple[LegalDocument, str]]:
    out = []
    for row in json.loads((fixtures / "manifest.json").read_text(encoding="utf-8")):
        text = (fixtures / row["raw_text_path"]).read_text(encoding="utf-8")
        row = {**row, "raw_text_path": "", "raw_checksum": hashlib.sha256(text.encode("utf-8")).hexdigest()}
        out.append((decode(LegalDocument, row), text))
    return out


def seed(legal_dir: Path, fixtures: Path = DEFAULT_FIXTURES, actor: str = "demo-seed") -> str:
    """Trả snapshot_id đang công bố sau khi nạp."""
    mgr = SnapshotManager(Path(legal_dir))
    docs = _documents(Path(fixtures))
    current = {d.document_key: d.raw_checksum for d in mgr.store().documents()}
    if all(current.get(doc.document_key) == doc.raw_checksum for doc, _ in docs):
        return mgr.current().snapshot_id

    def apply(svc) -> None:
        for doc, text in docs:
            path, checksum = rawfiles.write_text(mgr.legal_dir / "raw", doc.document_key, text)
            svc.store.upsert_document(dataclasses.replace(doc, raw_text_path=str(path), raw_checksum=checksum))

    return mgr.write("cli:seed-demo", actor, apply).snapshot.snapshot_id


if __name__ == "__main__":
    from rag.config import Settings

    sid = seed(Settings.load().data_dir / "legal")
    print(f"Kho luật demo đã sẵn sàng: snapshot {sid}")
