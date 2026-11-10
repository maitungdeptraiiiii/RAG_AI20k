"""CLI kho luật: python -m rag.legal <crawl|build|show|report|fixture>. Dữ liệu ở DATA_DIR/legal/."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[3]
DEFAULT_SEEDS = PROJECT.parent.parent / "data" / "team-4.2" / "legal" / "seeds.yaml"


def _legal_dir() -> Path:
    from rag.config import Settings

    return Settings.load().data_dir / "legal"


def _service():
    from rag.legal.service import LegalService
    from rag.legal.store import LegalStore

    return LegalService(LegalStore(_legal_dir() / "catalog.sqlite"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m rag.legal", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    crawl = sub.add_parser("crawl", help="tải seed + tự tìm văn bản liên quan từ vbpl.vn")
    crawl.add_argument("--seeds", type=Path, default=DEFAULT_SEEDS)
    crawl.add_argument("--max-depth", type=int, default=2)
    sub.add_parser("build", help="lập thao tác + dựng phiên bản cho mọi luật trong kho")
    show = sub.add_parser("show", help="nội dung một luật tại một ngày")
    show.add_argument("key")
    show.add_argument("--as-of", required=True, type=date.fromisoformat)
    show.add_argument("--provision", help="vd. d60.k3")
    sub.add_parser("report", help="thống kê thao tác / phiên bản / mục duyệt")
    fixture = sub.add_parser("fixture", help="lưu text của văn bản (Luật) làm fixture test")
    fixture.add_argument("numbers", nargs="+")
    fixture.add_argument("--type", default="Luật")
    fixture.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    if args.cmd == "crawl":
        from rag.ingest.vbpl import VbplClient
        from rag.legal.discovery import discover, load_seeds

        svc = _service()
        report = discover(VbplClient(), svc.store, load_seeds(args.seeds), _legal_dir() / "raw", max_depth=args.max_depth)
        print(json.dumps({"added": report.added, "rejected": report.rejected, "suspicious": report.suspicious},
                         ensure_ascii=False, indent=2))
    elif args.cmd == "build":
        runs = _service().build_all()
        print(json.dumps([{"document": r.document_key, "build_id": r.build_id, "operations": len(r.operation_ids)}
                          for r in runs], ensure_ascii=False, indent=2))
    elif args.cmd == "show":
        svc = _service()
        for v in svc.store.provisions_as_of(args.key, args.as_of):
            if args.provision and v.provision_id != f"{args.key}#{args.provision}":
                continue
            end = v.valid_to.isoformat() if v.valid_to else "…"
            print(f"{v.provision_id} | {v.valid_from.isoformat()} → {end} | {v.verification_status}"
                  f"{' | ' + ', '.join(v.status_reasons) if v.status_reasons else ''}")
            print("  " + v.text.replace("\n", "\n  "))
    elif args.cmd == "report":
        rep = _service().report()
        rep["operations"] = {f"{p}/{r}": n for (p, r), n in rep["operations"].items()}
        print(json.dumps(rep, ensure_ascii=False, indent=2))
    elif args.cmd == "fixture":
        from rag.ingest.vbpl import VbplClient
        from rag.legal.crawl import fetch_document

        client = VbplClient()
        args.out.mkdir(parents=True, exist_ok=True)
        for number in args.numbers:
            got = fetch_document(client, args.type, number, args.out)
            print(f"{number}: {'ok ' + got[0].raw_text_path if got else 'không tìm thấy'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
