"""K1: ghi reports/week-04/team-4.2/legal_ingest.md từ kho luật có phiên bản hiện tại (chỉ đọc kho).

Chạy từ app/team-4.2: .venv/Scripts/python.exe scripts/legal_ingest_report.py [--out PATH] [--day YYYY-MM-DD]"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]


def main(argv: list[str] | None = None) -> int:
    from rag.legal.__main__ import _snapshots
    from rag.legal.ingest_report import TARGETS, ingest_rows, render_markdown

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=REPO / "reports" / "week-04" / "team-4.2" / "legal_ingest.md")
    ap.add_argument("--day", type=date.fromisoformat, default=date.today())
    args = ap.parse_args(argv)
    manager = _snapshots()
    snap = manager.current().snapshot_id
    rows = ingest_rows(manager.store(), TARGETS, day=args.day)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render_markdown(rows, snapshot_id=snap, day=args.day), encoding="utf-8")
    missing = [r.key for r in rows if not r.present]
    print(f"snapshot {snap}: {len(rows) - len(missing)}/{len(rows)} văn bản có trong kho -> {args.out}")
    return 1 if missing else 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
