"""Synthetic review demo: missing effective date -> confirm -> apply version."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import NAMESPACE_URL, uuid5

from rag.ingest.dedup import DedupResult
if __package__ in (None, ""):
    from demo_versioning import fake_ocr_bundle
else:
    from .demo_versioning import fake_ocr_bundle
from rag.models.common import require
from rag.models.document import ChangeRequest, DocumentRecord, IdentityHint, QueryScope
from rag.models.quality import ReviewDecision
from rag.quality.review_queue import SQLiteReviewService
from rag.versioning.repository import VersionRepository
from rag.versioning.resolver import FullVersionResolver
from rag.versioning.scope import UnitScopeResolver

DOCUMENT_ID = str(uuid5(NAMESPACE_URL, "w02-review-demo/document"))
V1 = str(uuid5(NAMESPACE_URL, "w02-review-demo/v1"))
V2 = str(uuid5(NAMESPACE_URL, "w02-review-demo/v2"))
NOW = datetime(2026, 11, 6, 12, tzinfo=timezone.utc)


def run_demo(database: Path) -> dict:
    repository = VersionRepository(database)
    queue = SQLiteReviewService(repository, now=lambda: NOW)
    planner, selector = FullVersionResolver(), UnitScopeResolver()
    hint = IdentityHint(document_id=DOCUMENT_ID)
    clear = DedupResult(matches=(), action="continue", existing_version_id=None, findings=())
    repository.add_document(DocumentRecord(document_id=DOCUMENT_ID, title="Quy định phí — demo review",
                                            document_type="policy", language="vi", created_at=NOW))
    if not repository.snapshot().versions(DOCUMENT_ID):
        source, parsed = fake_ocr_bundle(V1, "Điều 1. Mức phí là 100.000 đồng.", database.parent, "review-v1")
        change = ChangeRequest(kind="initial", effective_from=date(2026, 1, 1))
        plan = planner.propose(parsed, hint=hint, dedup=clear, change=change, catalog=repository.snapshot())
        repository.commit(plan, parsed, source, approve=True)

    existing = next((item for item in queue.list_items(status=None)
                     if any(t.version_id == V2 for t in item.item.targets)), None)
    if existing is None:
        source, parsed = fake_ocr_bundle(V2, "Điều 1. Mức phí là 120.000 đồng.", database.parent, "review-v2")
        change = ChangeRequest(kind="full", supersedes_version_ids=(V1,))  # deliberately missing date
        plan = planner.propose(parsed, hint=hint, dedup=clear, change=change, catalog=repository.snapshot())
        item = queue.enqueue_version(plan, parsed, source, hint=hint, change=change, dedup=clear)
        require(queue.enqueue_version(plan, parsed, source, hint=hint, change=change, dedup=clear).review_id == item.review_id,
                "Repeated enqueue created a duplicate review")
        before = selector.resolve_units(QueryScope(mode="as_of", as_of=date(2026, 8, 1)), catalog=repository.snapshot())
        require(before.units[0].revision.version_id == V1, "Pending version became queryable")
        details = queue.get(item.review_id)
        decision = ReviewDecision(decision_id=str(uuid5(NAMESPACE_URL, "w02-review-demo/decision")),
                                  review_id=item.review_id, action="confirm_replacement", reviewer="Khánh — demo",
                                  reason="Đã kiểm tra nguồn và xác nhận ngày hiệu lực trong dữ liệu giả lập",
                                  payload={"effective_from": "2026-07-01", "supersedes_version_ids": [V1]},
                                  created_at=NOW + timedelta(minutes=1))
        queue.resolve(item.review_id, decision, expected_revision=details.revision)
        # Exact retry is idempotent, even with the revision seen before first resolve.
        queue.resolve(item.review_id, decision, expected_revision=details.revision)
        review_id = item.review_id
    else:
        review_id = existing.item.review_id

    reopened = VersionRepository(database)
    details = SQLiteReviewService(reopened).get(review_id)
    selection = selector.resolve_units(QueryScope(mode="as_of", as_of=date(2026, 8, 1)), catalog=reopened.snapshot())
    require(details.item.status == "resolved" and selection.units[0].revision.version_id == V2, "Review did not persist/apply")
    return {"mode": "synthetic OCR; SQLite review + standalone version catalog; no index activation",
            "review_id": review_id, "status": details.item.status, "review_revision": details.revision,
            "issue": details.issues[0].safe_evidence, "reviewer": details.decision.reviewer,
            "application": details.application.status,
            "as_of_2026_08_01": "\n".join(b.text for b in selection.units[0].blocks),
            "open_reviews": len(queue.list_items()), "restart_preserved": True}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path)
    args = parser.parse_args()
    if args.database:
        report = run_demo(args.database)
    else:
        with TemporaryDirectory(prefix="w02-review-") as folder:
            report = run_demo(Path(folder) / "catalog.sqlite")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
