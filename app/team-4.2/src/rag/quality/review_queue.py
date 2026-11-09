"""Durable review queue and atomic re-planning against the latest catalog.

Safe issue/decision payloads are caller-provided; this module is not a masker.
Pending raw extraction is kept in a separate internal input table, never in
public list/detail responses or in the queryable version catalog.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Callable, Literal, Sequence
from rag.ingest.checksum import canonical_checksum
from rag.ingest.dedup import DedupResult
from rag.models.common import canonical_json, require, to_json_value
from rag.models.content import TargetRef
from rag.models.document import ChangeRequest, IdentityHint, SourceRecord
from rag.models.quality import QualityIssue, ReviewDecision, ReviewItem
from rag.models.results import ParseResult
from rag.models.serialization import from_dict, from_json
from rag.versioning.interfaces import VersionPlan
from rag.versioning.repository import ConcurrentUpdateError, VersionCommit, VersionRepository
from rag.versioning.resolver import FullVersionResolver


class ReviewBlockedError(ValueError):
    """The corrected request still cannot safely produce a version plan."""

    def __init__(self, reasons: tuple[str, ...]) -> None:
        self.reasons = reasons
        super().__init__("Review cannot apply yet: " + "; ".join(reasons))


@dataclass(frozen=True, kw_only=True)
class ReviewDetails:
    item: ReviewItem
    revision: int
    issues: tuple[QualityIssue, ...]
    decision: ReviewDecision | None = None
    application: VersionCommit | None = None


@dataclass(frozen=True, kw_only=True)
class VersionReviewInput:
    """Internal extraction, not returned by the public review API."""
    source: SourceRecord
    parsed: ParseResult
    hint: IdentityHint
    change: ChangeRequest
    dedup: DedupResult


def _issue_checksum(issue: QualityIssue) -> str:
    payload = issue.to_dict()
    payload.pop("created_at")  # detector retries may have a new observation time
    return canonical_checksum(payload)


class SQLiteReviewService:
    def __init__(self, repository: VersionRepository, *, now: Callable[[], datetime] | None = None) -> None:
        self.repository = repository
        self._now = now or (lambda: datetime.now(timezone.utc))
        # SAME SQLite database as versions: decision and catalog update commit together.
        with repository._connection(write=True) as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS w02_review_issues (
                issue_id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, payload TEXT NOT NULL)""")
            conn.execute("""CREATE TABLE IF NOT EXISTS w02_reviews (
                review_id TEXT PRIMARY KEY, revision INTEGER NOT NULL, payload TEXT NOT NULL)""")
            conn.execute("""CREATE TABLE IF NOT EXISTS w02_review_decisions (
                decision_id TEXT PRIMARY KEY, review_id TEXT NOT NULL UNIQUE,
                fingerprint TEXT NOT NULL, payload TEXT NOT NULL)""")
            conn.execute("""CREATE TABLE IF NOT EXISTS w02_review_inputs (
                review_id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, payload TEXT NOT NULL)""")
            conn.execute("""CREATE TABLE IF NOT EXISTS w02_review_applications (
                review_id TEXT PRIMARY KEY, payload TEXT NOT NULL)""")

    @staticmethod
    def _store_issue(conn, issue: QualityIssue) -> None:
        fingerprint = _issue_checksum(issue)
        old = conn.execute("SELECT fingerprint FROM w02_review_issues WHERE issue_id=?", (issue.issue_id,)).fetchone()
        if old:
            require(old["fingerprint"] == fingerprint, "Issue ID reused with changed evidence/config; create a new issue ID")
        else:
            conn.execute("INSERT INTO w02_review_issues VALUES (?, ?, ?)",
                         (issue.issue_id, fingerprint, canonical_json(issue)))

    def _enqueue(self, conn, issues: Sequence[QualityIssue]) -> ReviewItem:
        require(bool(issues), "Review requires at least one issue")
        for issue in issues:
            self._store_issue(conn, issue)
        issue_ids = tuple(sorted({issue.issue_id for issue in issues}))
        review_id = canonical_checksum({"issues": issue_ids})
        existing = conn.execute("SELECT payload FROM w02_reviews WHERE review_id=?", (review_id,)).fetchone()
        if existing:
            return from_json(ReviewItem, existing["payload"])
        targets = []
        for issue in issues:
            for target in issue.targets:
                if target not in targets:
                    targets.append(target)
        item = ReviewItem(review_id=review_id, issue_ids=issue_ids, targets=tuple(targets), created_at=self._now())
        conn.execute("INSERT INTO w02_reviews VALUES (?, 0, ?)", (review_id, canonical_json(item)))
        return item

    def enqueue(self, issues: Sequence[QualityIssue]) -> tuple[ReviewItem, ...]:
        """One review per issue; repeated identical findings keep the old state."""
        with self.repository._connection(write=True) as conn:
            result = {}
            for issue in issues:
                item = self._enqueue(conn, (issue,))
                result[item.review_id] = item
            return tuple(result.values())

    def enqueue_version(self, plan: VersionPlan, parsed: ParseResult, source: SourceRecord, *,
                        hint: IdentityHint, change: ChangeRequest, dedup: DedupResult) -> ReviewItem:
        """Persist a pending input so the reviewer can correct metadata later.

        Caller must supply the original dedup result. Findings are retained and
        are not silently cleared when a relationship/date is confirmed.
        """
        require(plan.action == "review" and bool(plan.review_reasons), "Expected a version plan needing review")
        require(plan.document_id == hint.document_id == plan.candidate_version.document_id,
                "Pending identity differs from the version plan")
        require(plan.candidate_version.version_id == parsed.processing.version_id,
                "Pending extraction version differs from plan")
        require(source.source_id == parsed.processing.source_id and source.document_id in (None, plan.document_id),
                "Pending source differs from extraction/document")
        require(source.version_id in (None, parsed.processing.version_id), "Pending source version mismatch")
        context = VersionReviewInput(source=source, parsed=parsed, hint=hint, change=change, dedup=dedup)
        # No text or filenames in generated evidence; raw extraction is stored separately.
        issue = QualityIssue(
            issue_id=canonical_checksum({"kind": "version.review", "document_id": plan.document_id,
                "version_id": parsed.processing.version_id, "processing_id": parsed.processing.processing_id,
                "change": change, "reasons": plan.review_reasons,
                "findings": sorted(i.issue_id for i in (*parsed.findings, *dedup.findings))}),
            code="version.review", severity="warning",
            targets=(TargetRef(source_id=source.source_id, version_id=parsed.processing.version_id),),
            message="Version relationship or effective date requires confirmation",
            safe_evidence={"document_id": plan.document_id, "reasons": list(plan.review_reasons)},
            detector_name="version_resolver", detector_version="w02-review-v1", config_id="explicit-relationships-v1",
            created_at=self._now())
        with self.repository._connection(write=True) as conn:
            item = self._enqueue(conn, (issue, *parsed.findings, *dedup.findings))
            fingerprint = canonical_checksum(context)
            previous = conn.execute("SELECT fingerprint FROM w02_review_inputs WHERE review_id=?", (item.review_id,)).fetchone()
            if previous:
                require(previous["fingerprint"] == fingerprint, "Pending input changed; create a new processing/issue ID")
            else:
                conn.execute("INSERT INTO w02_review_inputs VALUES (?, ?, ?)",
                             (item.review_id, fingerprint, canonical_json(context)))
            return item

    @staticmethod
    def _details(conn, review_id: str) -> ReviewDetails:
        row = conn.execute("SELECT * FROM w02_reviews WHERE review_id=?", (review_id,)).fetchone()
        if row is None:
            raise KeyError("Unknown review")
        item = from_json(ReviewItem, row["payload"])
        issues = tuple(from_json(QualityIssue, conn.execute(
            "SELECT payload FROM w02_review_issues WHERE issue_id=?", (issue_id,)).fetchone()[0]) for issue_id in item.issue_ids)
        decision = conn.execute("SELECT payload FROM w02_review_decisions WHERE review_id=?", (review_id,)).fetchone()
        application = conn.execute("SELECT payload FROM w02_review_applications WHERE review_id=?", (review_id,)).fetchone()
        return ReviewDetails(item=item, revision=row["revision"], issues=issues,
                             decision=from_json(ReviewDecision, decision[0]) if decision else None,
                             application=from_json(VersionCommit, application[0]) if application else None)

    def get(self, review_id: str) -> ReviewDetails:
        with self.repository._connection() as conn:
            return self._details(conn, review_id)

    def list_items(self, *, status: Literal["open", "resolved"] | None = "open",
                   limit: int = 100, offset: int = 0) -> tuple[ReviewDetails, ...]:
        require(status in (None, "open", "resolved") and 1 <= limit <= 1000 and offset >= 0,
                "Invalid review filter/page")
        with self.repository._connection() as conn:
            # Filter inside SQL before pagination; schema payload carries the status.
            rows = conn.execute("""SELECT review_id FROM w02_reviews
                WHERE (? IS NULL OR json_extract(payload, '$.status')=?) ORDER BY rowid LIMIT ? OFFSET ?""",
                (status, status, limit, offset)).fetchall()
            return tuple(self._details(conn, row[0]) for row in rows)

    def resolve(self, review_id: str, decision: ReviewDecision, *, expected_revision: int) -> ReviewItem:
        """Resolve once. Version application and decision are ONE transaction."""
        require(decision.review_id == review_id, "Decision belongs to another review")
        require(type(expected_revision) is int and expected_revision >= 0, "Invalid review revision")
        fingerprint = canonical_checksum(decision)
        with self.repository._connection(write=True) as conn:
            details = self._details(conn, review_id)
            existing = conn.execute("SELECT * FROM w02_review_decisions WHERE decision_id=?", (decision.decision_id,)).fetchone()
            if existing:
                require(existing["review_id"] == review_id and existing["fingerprint"] == fingerprint,
                        "Decision ID reused with different data")
                return details.item
            if details.revision != expected_revision:
                raise ConcurrentUpdateError("Review changed; reload it before deciding")
            require(details.item.status == "open", "Review is already resolved")
            require(decision.created_at >= details.item.created_at, "Decision cannot precede review creation")
            context = conn.execute("SELECT payload FROM w02_review_inputs WHERE review_id=?", (review_id,)).fetchone()
            application = None
            if decision.action in ("confirm_replacement", "link_existing"):
                require(context is not None, "Version action requires a linked version review input")
            if context is not None and decision.action in ("accept", "confirm_replacement", "link_existing"):
                application = self._apply_version(conn, from_json(VersionReviewInput, context[0]), decision)
            resolved = replace(details.item, status="resolved", resolved_at=decision.created_at)
            conn.execute("INSERT INTO w02_review_decisions VALUES (?, ?, ?, ?)",
                         (decision.decision_id, review_id, fingerprint, canonical_json(decision)))
            if application:
                conn.execute("INSERT INTO w02_review_applications VALUES (?, ?)", (review_id, canonical_json(application)))
            conn.execute("UPDATE w02_reviews SET revision=revision+1, payload=? WHERE review_id=?",
                         (canonical_json(resolved), review_id))
            return resolved

    def _apply_version(self, conn, context: VersionReviewInput, decision: ReviewDecision) -> VersionCommit:
        allowed = {"kind", "effective_from", "supersedes_version_ids", "unit_mapping", "unit_assignments"}
        if decision.action == "link_existing":
            allowed.add("version_id")
        require(not (set(decision.payload) - allowed), "Unsupported version decision fields")
        base = to_json_value(context.change)
        assert isinstance(base, dict)
        correction = {key: value for key, value in decision.payload.items() if key != "version_id"}
        change = from_dict(ChangeRequest, {**base, **correction})
        if decision.action == "confirm_replacement":
            require(change.kind in ("full", "partial"), "Replacement decision requires full/partial kind")
        dedup = context.dedup
        if decision.action == "link_existing":
            dedup = replace(dedup, action="link_existing", existing_version_id=decision.payload["version_id"])
        # Latest snapshot, not the stale proposal the reviewer first saw.
        catalog = self.repository._snapshot(conn)
        plan = FullVersionResolver().propose(context.parsed, hint=context.hint, change=change, dedup=dedup, catalog=catalog)
        if plan.action == "review":
            raise ReviewBlockedError(plan.review_reasons)
        plan = replace(plan, applicability_changes=tuple(
            replace(c, proposed=replace(c.proposed, decision_id=decision.decision_id)) if c.previous is None else c
            for c in plan.applicability_changes))
        return self.repository._commit_in_transaction(conn, plan, context.parsed, context.source, approve=True)
