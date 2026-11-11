"""Offline, idempotent warehouse-1 → catalog migration; no inferred effectivity.

Run: python -m rag.legal.migrate --apply (default is dry-run).
Source files and original chunk records are preserved. A SQLite online backup
and a manifest are written BEFORE the single catalog transaction.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3

from rag.config import Settings
from rag.legal.keys import document_key
from rag.legal.models import LegalDocument
from rag.legal.store import LegalStore
from rag.temporal.status import load_legacy_map


def migrate(data_dir: Path, legacy_map_path: Path, *, apply=False, only_doc_ids=None, records=None):
    data_dir = Path(data_dir).resolve()
    source_path = data_dir / "processed" / "chunks.jsonl"
    source_bytes = (source_path.read_bytes() if source_path.exists() else
                    "\n".join(json.dumps(r, ensure_ascii=False) for r in records or []).encode("utf-8"))
    if records is None and not source_path.exists():
        raise FileNotFoundError(source_path)
    groups = defaultdict(list)
    records = records if records is not None else [json.loads(line) for line in source_bytes.decode("utf-8").splitlines() if line.strip()]
    for row in records:
        groups[row["doc_id"]].append(row)
    known = load_legacy_map(legacy_map_path) if legacy_map_path.exists() else {}
    catalog = data_dir / "legal" / "catalog.sqlite"
    now = datetime.now(timezone.utc)
    entries, manifest = [], []
    for old_id, chunks in groups.items():
        if only_doc_ids is not None and old_id not in only_doc_ids:
            continue
        chunks.sort(key=lambda row: row["chunk_id"])
        source = chunks[0]["source"]
        if any(row["source"] != source for row in chunks):
            raise ValueError("One source document has conflicting source identities")
        law = known.get(source)
        key = document_key(law.doc_type, law.doc_number) if law else f"reference:{old_id}"
        # Never resolve a user-provided path or URL as an arbitrary local file.
        original = None
        if Path(source).name == source and not source.startswith(("http:", "https:")):
            roots = [data_dir / "raw", Path("data/team-4.2/raw").resolve()]
            original = next((root / source for root in roots if (root / source).is_file()), None)
        raw = original.read_bytes() if original else "\n\n".join(c["text"] for c in chunks).encode("utf-8")
        display = raw
        if original and original.suffix.lower() not in {".txt", ".md", ".markdown", ".html", ".htm", ".csv"}:
            display = "\n\n".join(c["text"] for c in chunks).encode("utf-8")
        else:
            try:
                display.decode("utf-8")
            except UnicodeDecodeError:
                display = "\n\n".join(c["text"] for c in chunks).encode("utf-8")
        checksum = hashlib.sha256(raw + json.dumps(chunks, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        target = data_dir / "legal" / "sources" / old_id / checksum / "source.txt"
        names = {"bo_luat_dan_su_2015.txt": "Bộ luật Dân sự 2015",
                 "bo_luat_hang_hai_2015.txt": "Bộ luật Hàng hải 2015",
                 "bo_luat_hinh_su_2015.txt": "Bộ luật Hình sự 2015",
                 "bo_luat_lao_dong_2019.txt": "Bộ luật Lao động 2019",
                 "bo_luat_to_tung_dan_su_2015.txt": "Bộ luật Tố tụng dân sự 2015",
                 "bo_luat_to_tung_hinh_su_2015.txt": "Bộ luật Tố tụng hình sự 2015"}
        title = names.get(source, source)
        doc = LegalDocument(key, "", title, law.doc_type if law else "reference",
                            law.doc_number if law else "", law.issuer if law else None,
                            None, None, None, "unverified_import", False, str(target),
                            hashlib.sha256(display).hexdigest(), now, f"warehouse1:{old_id}")
        snapshot = {"checksum": checksum, "old_doc_id": old_id, "source": source,
                    "applicability": "unverified", "chunks": chunks,
                    "original_path": str(original) if original else None,
                    "source_reconstructed": original is None, "imported_at": now.isoformat()}
        snapshot.update(original_archive=str(target.parent / "original.bin"),
                        original_checksum=hashlib.sha256(raw).hexdigest(), display_reconstructed=display != raw)
        entries.append((doc, snapshot, display, raw))
        manifest.append({"old_doc_id": old_id, "document_key": key, "source": source,
                         "checksum": checksum, "chunks": len(chunks), "applicability": "unverified",
                         "source_reconstructed": original is None})
    if len({doc.document_key for doc, _, _, _ in entries}) != len(entries):
        raise ValueError("Several source documents map to one legal identity; review before importing")
    report = {"mode": "apply" if apply else "dry_run", "documents": len(entries),
              "chunks": sum(len(snapshot["chunks"]) for _, snapshot, _, _ in entries),
              "source_checksum": hashlib.sha256(source_bytes).hexdigest(), "entries": manifest}
    if not apply:
        return report
    backup_dir = data_dir / "legal" / "backups" / now.strftime("%Y%m%dT%H%M%S%fZ")
    backup_dir.mkdir(parents=True, exist_ok=False)
    if catalog.exists():
        with sqlite3.connect(catalog.as_uri() + "?mode=ro", uri=True) as src:
            with sqlite3.connect(backup_dir / "catalog.sqlite") as dst:
                src.backup(dst)
    (backup_dir / "chunks.jsonl").write_bytes(source_bytes)
    (backup_dir / "migration.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    store = LegalStore(catalog)
    for doc, snapshot, display, raw in entries:
        target = Path(doc.raw_text_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and target.read_bytes() != display:
            raise ValueError("Source snapshot checksum collision")
        target.write_bytes(display)
        Path(snapshot["original_archive"]).write_bytes(raw)
    report["changed_documents"] = store.import_reference_snapshots([(doc, row) for doc, row, _, _ in entries])
    report["backup_dir"] = str(backup_dir)
    (backup_dir / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[5]
    result = migrate(Settings.load().data_dir, root / "data/team-4.2/legal/legacy_map.yaml", apply=args.apply)
    print(json.dumps(result, ensure_ascii=True, indent=2))
