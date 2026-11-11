"""CLI kho luật: python -m rag.legal <crawl|build|show|report|fixture>. Dữ liệu ở DATA_DIR/legal/.

`crawl` / `build` ghi qua `SnapshotManager.write` (staging -> kiểm tra -> công bố nguyên khối) dưới cùng khoá ghi với
server: đang có lần cập nhật khác (vd. server đang áp dụng một upload) -> thoát mã 2, không ghi gì. `show` / `report`
đọc snapshot đang công bố. Server đang chạy KHÔNG tự chuyển chat sang snapshot do CLI công bố: nó thấy snapshot đó ở
lần "Dựng lại chỉ mục" (POST /api/legal/reindex) hoặc lần ghi kế tiếp của server (upload / quyết định duyệt).
"""

from __future__ import annotations

import argparse
import getpass
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


LOCKED_MESSAGE = "Đang có lần cập nhật kho khác, thử lại sau"


def _snapshots():
    from rag.legal.snapshots import SnapshotManager

    return SnapshotManager(_legal_dir())


def _service():
    """Service trên snapshot đang công bố (chỉ đọc)."""
    from rag.legal.service import LegalService

    return LegalService(_snapshots().store())


def _user() -> str:
    try:
        return getpass.getuser()
    except Exception:  # noqa: BLE001 - không có biến môi trường người dùng
        return "cli"


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

    from rag.legal.snapshots import WriteLockedError

    try:
        return _run(args)
    except WriteLockedError:
        print(LOCKED_MESSAGE)
        return 2


def _run(args: argparse.Namespace) -> int:
    if args.cmd == "crawl":
        from rag.ingest.vbpl import VbplClient
        from rag.legal.discovery import discover, load_seeds

        client, seeds, raw = VbplClient(), load_seeds(args.seeds), _legal_dir() / "raw"
        res = _snapshots().write("cli:crawl", _user(), lambda svc: discover(client, svc.store, seeds, raw,
                                                                            max_depth=args.max_depth))
        report = res.value
        print(json.dumps({"snapshot_id": res.snapshot.snapshot_id, "added": report.added, "rejected": report.rejected,
                          "suspicious": report.suspicious}, ensure_ascii=False, indent=2))
    elif args.cmd == "build":
        snapshots = _snapshots()
        res = snapshots.write("cli:build", _user(), lambda svc: None)
        store = snapshots.store(res.snapshot.snapshot_id)
        print(json.dumps({"snapshot_id": res.snapshot.snapshot_id,
                          "laws": [{"document": d.document_key, "build_id": run.build_id}
                                   for d in store.documents() if (run := store.latest_build(d.document_key))]},
                         ensure_ascii=False, indent=2))
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
        import tempfile

        from rag.ingest.vbpl import VbplClient
        from rag.legal.crawl import fetch_document, raw_path_for

        client = VbplClient()
        args.out.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory() as tmp:          # fixture: một file phẳng <key>.txt như trước
            for number in args.numbers:
                got = fetch_document(client, args.type, number, Path(tmp))
                if got:
                    path = raw_path_for(args.out, got[0].document_key)
                    path.write_text(got[1] + "\n", encoding="utf-8")
                print(f"{number}: {'ok ' + str(path) if got else 'không tìm thấy'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
