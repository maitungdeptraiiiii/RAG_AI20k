"""K1: ghi evals/team-4.2/results/w04-rule-engine/legal_ingest.md từ kho luật có phiên bản hiện tại (chỉ đọc kho).

Chạy từ app/team-4.2: .venv/Scripts/python.exe scripts/legal_ingest_report.py [--out PATH] [--day YYYY-MM-DD]"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]


def main(argv: list[str] | None = None) -> int:
    from rag.legal.__main__ import _snapshots
    from rag.legal.graph.service import build_current
    from rag.legal.ingest_report import TARGETS, ingest_rows, render_markdown

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=REPO / "evals" / "team-4.2" / "results" / "w04-rule-engine" / "legal_ingest.md")
    ap.add_argument("--no-graph", action="store_true", help="bỏ bước dựng đồ thị luật (chỉ đọc kho, mất vài giây)")
    ap.add_argument("--day", type=date.fromisoformat, default=date.today())
    args = ap.parse_args(argv)
    manager = _snapshots()
    snap = manager.current().snapshot_id
    build, errors = (None, []) if args.no_graph else build_current(manager)   # chỉ dựng trong bộ nhớ, không công bố Neo4j
    rows = ingest_rows(manager.store(), TARGETS, day=args.day, graph=build)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render_markdown(rows, snapshot_id=snap, day=args.day), encoding="utf-8")
    missing = [r.key for r in rows if not r.present]
    print(f"snapshot {snap}: {len(rows) - len(missing)}/{len(rows)} văn bản có trong kho -> {args.out}")
    no_graph = [r.key for r in rows if r.graph_nodes == 0]
    if errors:
        print(f"đồ thị luật: {len(errors)} lỗi kiểm tra (xem `python -m rag.legal graph check`)", file=sys.stderr)
    return 1 if missing or no_graph else 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
