"""Tải các văn bản của một hàng đợi phạm vi (data/team-4.2/legal/<phạm vi>-fetch-queue.json) vào kho, không đổi CURRENT.

python scripts/team-4.2/fetch_scope.py --queue data/team-4.2/legal/commerce-consumer-scope-fetch-queue.json     --staging commerce-consumer-scope-v1
Dùng lại đúng hàm tải của fetch_labor_scope.py (API công khai VBPL, đối chiếu loại / số hiệu, lưu nguồn theo checksum).
Văn bản vào app/team-4.2/data/team-4.2/legal/raw/; bản lưu nguồn vào supplements/<staging>/. Chưa nhập snapshot
(nạp bằng `python -m rag.legal import-supplement supplements/<staging>/fetch-report.json`).
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LEGAL = ROOT / "app/team-4.2/data/team-4.2/legal"


def _labor_module():
    spec = importlib.util.spec_from_file_location("fetch_labor_scope", Path(__file__).with_name("fetch_labor_scope.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--queue", type=Path, required=True)
    ap.add_argument("--staging", required=True, help="tên thư mục trong supplements/")
    args = ap.parse_args()
    QUEUE = args.queue if args.queue.is_absolute() else ROOT / args.queue
    lab = _labor_module()
    staging = LEGAL / "supplements" / args.staging
    staging.mkdir(parents=True, exist_ok=True)
    queue = json.loads(QUEUE.read_text(encoding="utf-8"))
    report = {"queue_sha256": lab.sha(QUEUE.read_bytes()), "scope_version": queue["scope_version"],
              "requested": len(queue["documents"]), "documents": {}, "failures": {}}
    current = (LEGAL / "CURRENT").read_bytes() if (LEGAL / "CURRENT").exists() else None
    client = lab.VbplClient(timeout=25, attempts=3, delay=.4)
    try:
        for item in queue["documents"]:
            key = item["document_key"]
            try:
                row = lab.fetch_one(client, item, LEGAL, staging, discovered_via=queue["scope_version"])
                report["documents"][key] = row
                print(json.dumps({"key": key, "status": "downloaded", "characters": row["characters"],
                                  "text_path": row["text_path"]}, ensure_ascii=False), flush=True)
            except Exception as exc:                      # ghi lỗi, tải tiếp văn bản khác
                report["failures"][key] = f"{type(exc).__name__}: {exc}"
                print(json.dumps({"key": key, "status": "failed", "error": str(exc)[:300]}, ensure_ascii=False), flush=True)
    finally:
        client.session.close()
        report["updated_at"] = datetime.now(timezone.utc).isoformat()
        lab.atomic_json(staging / "fetch-report.json", report)
    if current is not None and (LEGAL / "CURRENT").read_bytes() != current:
        raise RuntimeError("CURRENT changed concurrently")
    return 0 if not report["failures"] else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
