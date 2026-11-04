"""Crawl văn bản pháp luật từ vbpl.vn vào data/team-4.2/raw/vbpl/ (chạy tại gốc repo).

Theo số hiệu (cách dùng chính, chọn đúng văn bản cần thêm vào corpus):
    python scripts/team-4.2/crawl_vbpl.py 36/2005/QH11 27/2023/QH15 19/2023/QH15
Theo id vbpl (khi một số hiệu có nhiều bản ghi):
    python scripts/team-4.2/crawl_vbpl.py --id 139264
Duyệt danh sách theo loại văn bản / tình trạng hiệu lực (luôn đặt --limit):
    python scripts/team-4.2/crawl_vbpl.py --list --doc-types "Luật" --statuses "Còn hiệu lực" --limit 20

Mỗi văn bản: <tên>.txt (nội dung) + <tên>.meta.json (metadata, checksum); manifest.json gom tất cả.
Crawl lại văn bản đã có: nội dung không đổi thì không ghi lại; đổi thì ghi đè và báo "updated".
Sau đó ingest như thường:
    python scripts/team-4.2/ingest.py data/team-4.2/raw/vbpl/
"""

from __future__ import annotations

import argparse
import logging
import sys
from itertools import islice
from pathlib import Path

from rag.ingest.vbpl import (
    DOC_TYPE_IDS,
    EFFECTIVE_STATUS_IDS,
    VbplClient,
    load_manifest,
    pick_detail,
    save_document,
    write_manifest,
)

DEFAULT_OUT = Path("data/team-4.2/raw/vbpl")


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("numbers", nargs="*", help="số hiệu văn bản, vd. 36/2005/QH11")
    ap.add_argument("--id", action="append", default=[], dest="ids", help="id vbpl (lặp lại được)")
    ap.add_argument("--list", action="store_true", help="duyệt danh sách theo --doc-types/--statuses")
    ap.add_argument("--doc-types", nargs="+", choices=sorted(DOC_TYPE_IDS), default=["Luật"])
    ap.add_argument("--statuses", nargs="+", choices=sorted(EFFECTIVE_STATUS_IDS), default=["Còn hiệu lực"])
    ap.add_argument("--limit", type=int, default=10, help="số văn bản tối đa khi --list (mặc định 10)")
    ap.add_argument("--name", help="tên file (không đuôi) khi crawl đúng một văn bản")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--delay", type=float, default=0.5, help="giây nghỉ giữa các request")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    if not (args.numbers or args.ids or args.list):
        ap.error("cần ít nhất một số hiệu, --id hoặc --list")
    if args.name and len(args.numbers) + len(args.ids) != 1:
        ap.error("--name chỉ dùng khi crawl đúng một văn bản")

    client = VbplClient(delay=args.delay)
    manifest = load_manifest(args.out)
    failed = 0

    def save(detail: dict | None, label: str) -> None:
        nonlocal failed
        if detail is None:
            failed += 1
            print(f"LỖI       {label}: không tìm thấy văn bản có nội dung", file=sys.stderr)
            return
        r = save_document(detail, args.out, manifest, stem=args.name)
        if r.status == "empty":
            failed += 1
            print(f"LỖI       {label}: nội dung rỗng", file=sys.stderr)
            return
        print(f"{r.status:9} {r.doc_number} -> {r.text_file} ({r.n_chars} ký tự)")
        write_manifest(args.out, manifest)  # ghi sau mỗi văn bản để dừng giữa chừng không mất

    for number in args.numbers:
        try:
            save(pick_detail(client, client.search_by_number(number)), number)
        except Exception as e:  # noqa: BLE001 — báo lỗi từng văn bản, crawl tiếp
            failed += 1
            print(f"LỖI       {number}: {e}", file=sys.stderr)
    for doc_id in args.ids:
        try:
            save(pick_detail(client, [{"id": doc_id}]), doc_id)
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"LỖI       {doc_id}: {e}", file=sys.stderr)
    if args.list:
        items = client.iter_list(
            doc_type_ids=[DOC_TYPE_IDS[t] for t in args.doc_types],
            status_ids=[EFFECTIVE_STATUS_IDS[s] for s in args.statuses],
        )
        for item in islice(items, args.limit):
            try:
                save(pick_detail(client, [item]), str(item.get("docNum") or item.get("id")))
            except Exception as e:  # noqa: BLE001
                failed += 1
                print(f"LỖI       {item.get('docNum')}: {e}", file=sys.stderr)

    print(f"Manifest: {args.out / 'manifest.json'} ({len(manifest)} văn bản), lỗi: {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
