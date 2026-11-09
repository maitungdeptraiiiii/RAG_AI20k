"""Standalone fake-OCR demo: v1/v2, temporal selection and SQLite restart.

Run from app/team-4.2: python -m scripts.demo_versioning
Use --database PATH to keep the demo catalog; default uses a temporary folder.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import NAMESPACE_URL, uuid4, uuid5

from rag.ingest.checksum import canonical_checksum
from rag.ingest.dedup import DedupResult
from rag.models.common import require
from rag.models.content import Block, Locator
from rag.models.document import ChangeRequest, DocumentRecord, IdentityHint, ProcessingRecord, QueryScope, SourceRecord
from rag.models.results import ParseResult
from rag.versioning.repository import VersionRepository
from rag.versioning.resolver import FullVersionResolver
from rag.versioning.scope import UnitScopeResolver


DOCUMENT_ID = str(uuid5(NAMESPACE_URL, "w02-demo/fee-policy"))
V1 = str(uuid5(NAMESPACE_URL, "w02-demo/fee-policy/v1"))
V2 = str(uuid5(NAMESPACE_URL, "w02-demo/fee-policy/v2"))


def fake_ocr_bundle(version_id: str, text: str, root: Path, name: str) -> tuple[SourceRecord, ParseResult]:
    """Synthetic text stands in for OCR; no real OCR or PII validation runs."""
    raw = text.encode("utf-8")
    artifact = root / "raw" / f"{name}.txt"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    if artifact.exists():
        require(artifact.read_bytes() == raw, "Demo artifact already contains different bytes")
    else:
        artifact.write_bytes(raw)
    source_id = str(uuid4())
    now = datetime.now(timezone.utc)
    source = SourceRecord(source_id=source_id, source_uri=f"demo://{name}", display_name=f"{name}.txt",
                          media_type="text/plain", raw_artifact=f"raw/{name}.txt",
                          raw_checksum=hashlib.sha256(raw).hexdigest(), collected_at=now)
    content = [{"kind": "paragraph", "text": text}]
    processing_id = canonical_checksum({"source": source_id, "version": version_id, "content": content,
                                        "parser": "fake-ocr-v1"})
    processing = ProcessingRecord(processing_id=processing_id, version_id=version_id, source_id=source_id,
                                  parser_name="fake-ocr", parser_version="1", normalization_config_id="nfc-v1",
                                  content_checksum=canonical_checksum(content), created_at=now, coverage="complete",
                                  ocr_engine="fake", ocr_config_id="fake-v1")
    block = Block(block_id=f"{processing_id}:0", processing_id=processing_id, version_id=version_id, order=0,
                  kind="paragraph", text=text, origin="ocr", locator=Locator(source_id=source_id, page=1),
                  ocr_confidence=None)
    return source, ParseResult(processing=processing, blocks=(block,))


def run_demo(database: Path) -> dict:
    repository = VersionRepository(database)
    # Fixed timestamp makes registering the same document idempotent on rerun.
    repository.add_document(DocumentRecord(document_id=DOCUMENT_ID, title="Quy định phí — demo",
                                            document_type="policy", language="vi",
                                            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc)))
    planner, selector = FullVersionResolver(), UnitScopeResolver()
    imports = []
    for version_id, name, text, change in (
        (V1, "v1", "Điều 1. Mức phí là 100.000 đồng.",
         ChangeRequest(kind="initial", effective_from=date(2026, 1, 1))),
        (V2, "v2", "Điều 1. Mức phí là 120.000 đồng.",
         ChangeRequest(kind="full", effective_from=date(2026, 7, 1), supersedes_version_ids=(V1,))),
    ):
        source, parsed = fake_ocr_bundle(version_id, text, database.parent, name)
        catalog = repository.snapshot()
        exists = any(v.version_id == version_id for v in catalog.versions(DOCUMENT_ID))
        dedup = DedupResult(matches=(), action="link_existing" if exists else "continue",
                            existing_version_id=version_id if exists else None, findings=())
        plan = planner.propose(parsed, hint=IdentityHint(document_id=DOCUMENT_ID),
                               dedup=dedup, change=change, catalog=catalog)
        result = repository.commit(plan, parsed, source, approve=True)
        imports.append({"version": name, "status": result.status})

    def select(repository, day):
        result = selector.resolve_units(QueryScope(mode="as_of", as_of=day), catalog=repository.snapshot())
        return [{"version_id": u.revision.version_id, "text": "\n".join(b.text for b in u.blocks)} for u in result.units]

    march = select(repository, date(2026, 3, 1))
    july = select(repository, date(2026, 7, 1))
    august = select(repository, date(2026, 8, 1))
    restarted = VersionRepository(database)
    history = selector.resolve_units(QueryScope(mode="all_versions"), catalog=restarted.snapshot())
    require(march[0]["version_id"] == V1 and july[0]["version_id"] == V2, "Temporal demo failed")
    require(august == select(restarted, date(2026, 8, 1)), "Restart lost version data")
    return {"mode": "standalone catalog; synthetic OCR; no index activation",
            "imports": imports, "as_of_2026_03_01": march, "as_of_2026_07_01": july,
            "as_of_2026_08_01": august, "history_version_count": len(history.units),
            "restart_preserved": True}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, help="Keep demo data here; otherwise use a temporary folder")
    args = parser.parse_args()
    if args.database:
        report = run_demo(args.database)
    else:
        with TemporaryDirectory(prefix="w02-versioning-") as folder:
            report = run_demo(Path(folder) / "catalog.sqlite")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
