"""Đóng gói / giải nén kho luật để cả nhóm dùng cùng một bộ dữ liệu.

    python scripts/team-4.2/legal_corpus.py pack      # tạo data/team-4.2/legal/corpus-bundle.tar.gz + corpus-manifest.json
    python scripts/team-4.2/legal_corpus.py unpack    # giải nén vào data/team-4.2/legal/ (kiểm checksum trước)
    python scripts/team-4.2/legal_corpus.py verify    # so kho local với manifest

Kho mà app đọc: app/team-4.2/data/team-4.2/legal/ (DATA_DIR=data/team-4.2 tính từ app/team-4.2). Bundle + manifest
nằm ở data/team-4.2/legal/ (cạnh seeds.yaml) để commit.
Bundle gồm: raw/ (văn bản gốc theo checksum), CURRENT, snapshots/index.sqlite và snapshot đang công bố.
Không gồm: vector/ (chỉ mục embedding, dựng lại bằng "Dựng lại chỉ mục" / ingest), qa_log.sqlite, uploads/,
các snapshot cũ (là lịch sử cục bộ, mỗi cái ~80 MB).
`unpack` không ghi đè kho local đã khác bundle trừ khi có --force (kho cũ được đổi tên thành legal.bak-<giờ>).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tarfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LEGAL = ROOT / "app" / "team-4.2" / "data" / "team-4.2" / "legal"      # kho app đọc (đích của unpack)
SHARED = ROOT / "data" / "team-4.2" / "legal"                          # nơi commit bundle
BUNDLE = SHARED / "corpus-bundle.tar.gz"
MANIFEST = SHARED / "corpus-manifest.json"


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _files(base: Path) -> list[Path]:
    current = (base / "CURRENT").read_text(encoding="utf-8").strip()
    include = [base / "raw", base / "CURRENT", base / "snapshots" / "index.sqlite", base / "snapshots" / current]
    out: list[Path] = []
    for p in include:
        if p.is_file():
            out.append(p)
        elif p.is_dir():
            out += sorted(x for x in p.rglob("*") if x.is_file() and not x.name.endswith((".lock", ".tmp")))
    return out


def _tree_digest(base: Path) -> dict[str, str]:
    if not (base / "CURRENT").exists():
        return {}
    return {f.relative_to(base).as_posix(): _sha(f) for f in _files(base)}


def pack() -> None:
    if not (LEGAL / "CURRENT").exists():
        sys.exit(f"Không thấy {LEGAL / 'CURRENT'}: chưa có kho luật để đóng gói")
    files = _tree_digest(LEGAL)
    with tarfile.open(BUNDLE, "w:gz", compresslevel=9) as tar:
        for rel in sorted(files):
            info = tar.gettarinfo(LEGAL / rel, arcname=rel)
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            info.mtime = 0
            with (LEGAL / rel).open("rb") as f:
                tar.addfile(info, f)
    current = (LEGAL / "CURRENT").read_text(encoding="utf-8").strip()
    manifest = {"current_snapshot": current, "files": files, "bundle_sha256": _sha(BUNDLE)}
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"đã đóng gói {len(files)} file, snapshot {current}, {BUNDLE.stat().st_size / 1e6:.1f} MB")


def verify() -> bool:
    if not MANIFEST.exists():
        sys.exit("Thiếu corpus-manifest.json")
    want = json.loads(MANIFEST.read_text(encoding="utf-8"))["files"]
    have = _tree_digest(LEGAL)
    cur = json.loads(MANIFEST.read_text(encoding="utf-8"))["current_snapshot"]
    have = {k: v for k, v in have.items() if not k.startswith("snapshots/s") or k.startswith(f"snapshots/{cur}/")}
    missing = sorted(set(want) - set(have))
    extra = sorted(set(have) - set(want))
    changed = sorted(k for k in want if k in have and want[k] != have[k])
    ok = not (missing or changed)
    print("khớp manifest" if ok else f"LỆCH: thiếu {len(missing)}, khác {len(changed)}")
    for label, items in (("thiếu", missing), ("khác", changed)):
        for k in items[:10]:
            print(f"  {label}: {k}")
    if extra:
        print(f"  (có {len(extra)} file ngoài manifest, ví dụ snapshot từ lần crawl riêng của bạn)")
    return ok


def unpack(force: bool) -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if _sha(BUNDLE) != manifest["bundle_sha256"]:
        sys.exit("Bundle hỏng hoặc không khớp manifest, không giải nén")
    LEGAL.mkdir(parents=True, exist_ok=True)
    if LEGAL.joinpath("CURRENT").exists() and not force:
        if verify():
            print("kho local đã khớp bundle, không làm gì")
            return
        sys.exit("Kho local khác bundle. Chạy lại với --force để thay (kho cũ được đổi tên, không xóa)")
    backup = None
    if force:
        backup = LEGAL.parent / f"legal.bak-{time.strftime('%Y%m%d-%H%M%S')}"
        shutil.copytree(LEGAL, backup)
        for p in (LEGAL / "raw", LEGAL / "snapshots", LEGAL / "CURRENT"):
            shutil.rmtree(p) if p.is_dir() else p.unlink(missing_ok=True)
    with tarfile.open(BUNDLE, "r:gz") as tar:
        tar.extractall(LEGAL, filter="data")            # filter="data": chặn đường dẫn thoát khỏi thư mục đích
    if not verify():
        sys.exit("Giải nén xong nhưng checksum không khớp manifest")
    print(f"đã giải nén, snapshot {manifest['current_snapshot']}" + (f"; kho cũ ở {backup}" if backup else ""))


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")            # console Windows mặc định cp1252, không in được tiếng Việt
    ap =argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["pack", "unpack", "verify"])
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    if a.cmd == "pack":
        pack()
    elif a.cmd == "unpack":
        unpack(a.force)
    else:
        sys.exit(0 if verify() else 1)


if __name__ == "__main__":
    main()
