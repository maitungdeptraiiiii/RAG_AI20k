"""Deterministic lexical near-duplicate baseline over masked source blocks.

Similarity is evidence for review, never proof of identity, correctness or
replacement. No source, version or index is modified. For the small week-2
corpus this compares full token sequences without hidden truncation.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from difflib import SequenceMatcher
import re
import unicodedata
from typing import Callable, Sequence

from rag.ingest.checksum import canonical_checksum
from rag.ingest.dedup import DedupConfig, DedupMatch, DedupResult
from rag.ingest.interfaces import MaskConfig, PIIMasker
from rag.versioning.interfaces import CatalogView
from rag.models.common import nonempty, require, to_json_value
from rag.models.content import SafeBlock, TargetRef
from rag.models.document import IdentityHint, SourceRecord
from rag.models.quality import QualityIssue
from rag.models.results import MaskResult, ParseResult

BASELINE_CONFIG = DedupConfig(algorithm="token-sequence", algorithm_version="1",
                             threshold=0.85, fingerprint_config_id="nfc-casefold-whitespace-v1")
DEFAULT_CONFIG = replace(BASELINE_CONFIG, algorithm_version="2")
_TOKEN = re.compile(r"\d+(?:[.,]\d+)*|[^\W\d_]+|[^\w\s]", re.UNICODE)
_MAX_HUNKS = 6
_MAX_EXCERPT = 300


@dataclass(frozen=True, kw_only=True)
class ComparisonMetadata:
    """Explicit metadata, not guessed from filenames or similarity.

    confirmed=True must come from a validated inventory/reviewer. Different
    document IDs alone never prove independent scope. Raw metadata names are
    not copied into issue evidence; only comparison signals are exposed.
    """
    external_key: str | None = None
    issuer: str | None = None
    scope: tuple[tuple[str, str], ...] = ()
    confirmed: bool = False

    def __post_init__(self) -> None:
        require(type(self.confirmed) is bool, "Metadata confirmation must be boolean")
        for value in (self.external_key, self.issuer):
            if value is not None:
                nonempty(value)
        require(all(isinstance(pair, tuple) and len(pair) == 2 for pair in self.scope), "Scope must contain key/value tuples")
        for key, value in self.scope:
            nonempty(key, value)
        require(len({_normalize(key) for key, _ in self.scope}) == len(self.scope), "Duplicate scope dimension")
        object.__setattr__(self, "scope", tuple(sorted(self.scope)))


@dataclass(frozen=True, kw_only=True)
class ComparisonDocument:
    """Only SafeBlocks accepted. Masking policy is validated, not performed here."""
    document_id: str
    version_id: str
    processing_id: str
    blocks: tuple[SafeBlock, ...]
    masking_config_id: str
    coverage: str = "unknown"
    metadata: ComparisonMetadata = field(default_factory=ComparisonMetadata)

    def __post_init__(self) -> None:
        nonempty(self.document_id, self.version_id, self.processing_id, self.masking_config_id)
        require(self.coverage in ("complete", "incomplete", "unknown"), "Invalid coverage")
        require(len({b.block_id for b in self.blocks}) == len(self.blocks)
                and len({b.order for b in self.blocks}) == len(self.blocks), "Duplicate block IDs/order")
        require(all(isinstance(b, SafeBlock) and b.version_id == self.version_id
                    and b.processing_id == self.processing_id and b.masking_config_id == self.masking_config_id
                    for b in self.blocks), "Comparison needs SafeBlocks from one processing/version/mask policy")
        object.__setattr__(self, "blocks", tuple(sorted(self.blocks, key=lambda block: block.order)))

    @property
    def identity(self) -> tuple[str, str, str]:
        return self.document_id, self.version_id, self.processing_id

    @classmethod
    def from_parse(cls, parsed: ParseResult, masked: MaskResult, *, document_id: str,
                   metadata: ComparisonMetadata | None = None) -> ComparisonDocument:
        raw = {b.block_id: b for b in parsed.blocks}
        require(len(masked.blocks) == len(raw) and {b.block_id for b in masked.blocks} == set(raw),
                "Masker must preserve every source block")
        require(all(b.locator == raw[b.block_id].locator and b.order == raw[b.block_id].order
                    and b.kind == raw[b.block_id].kind for b in masked.blocks), "Masker changed source provenance")
        return cls(document_id=document_id, version_id=parsed.processing.version_id,
                   processing_id=parsed.processing.processing_id, blocks=masked.blocks,
                   masking_config_id=masked.masking_config_id, coverage=parsed.processing.coverage,
                   metadata=metadata or ComparisonMetadata())


@dataclass(frozen=True, kw_only=True)
class NearDuplicateComparison:
    left: tuple[str, str, str]
    right: tuple[str, str, str]
    similarity: float | None
    classification: str  # self, not_comparable, different, near_duplicate, same_content_candidate
    issue: QualityIssue | None = None
    body_similarity: float | None = None
    review_priority: str | None = None
    routing_category: str = "lexical"
    difference_types: tuple[str, ...] = ()
    decision_reasons: tuple[str, ...] = ()


def _normalize(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).casefold().split())


def _block_text(block: SafeBlock) -> str:
    parts = [block.text]
    if block.table is not None:
        table = block.table
        # Table structure participates even if block.text is empty or lossy.
        parts.append("<table>")
        for row in table.headers:
            parts.append("<header> " + " <cell> ".join(row))
        for row in table.rows:
            parts.append("<row> " + " <cell> ".join(row))
        parts.extend(("<units> " + " <cell> ".join(unit or "<unknown>" for unit in table.column_units),
                      "<caption> " + (table.caption or ""), "<period> " + (table.period or ""),
                      "<notes> " + " ".join(table.notes)))
        parts.append("<merged> " + canonical_checksum(table.merged_cells))
    for relation in block.relations:
        parts.append(f"<relation> {relation.relation} {relation.condition or ''}")
    return "\n".join(parts)


def _sequence(document: ComparisonDocument):
    tokens, refs = [], []
    for block in sorted(document.blocks, key=lambda b: b.order):
        block_tokens = _TOKEN.findall(_normalize(_block_text(block)))
        # Human-readable heading/sheet/table names may contain PII; references
        # preserve opaque block IDs and numeric positions without copying names.
        locator = replace(block.locator, heading_path=(), sheet=None, table_id=None)
        ref = TargetRef(source_id=block.locator.source_id, version_id=document.version_id,
                        block_id=block.block_id, locator=locator)
        tokens.extend(block_tokens)
        refs.extend([ref] * len(block_tokens))
    return tuple(tokens), tuple(refs)


def _body_tokens(document: ComparisonDocument) -> tuple[str, ...]:
    """Scoring view only: suppress recognizable preamble/footer lines.

    Never discard operative article/effectivity lines or structured tables.
    Source blocks, full-sequence score and full diff remain unchanged.
    """
    result, footer, preamble = [], False, False
    for block in document.blocks:
        if block.table is not None:
            result.extend(_TOKEN.findall(_normalize(_block_text(block))))
            continue
        for raw_line in block.text.splitlines():
            line = _normalize(raw_line)
            operative = bool(re.match(r"điều\s+\d", line) or re.search(r"hiệu\s+lực|chuyển\s+tiếp", line))
            if operative:
                footer = preamble = False
            elif re.match(r"nơi\s+nhận\s*:", line):
                footer, preamble = True, False
                continue
            elif re.match(r"căn\s+cứ\b", line):
                preamble = not line.endswith((";", "."))
                continue
            elif footer:
                continue
            elif preamble:
                preamble = not line.endswith((";", "."))
                continue
            result.extend(_TOKEN.findall(line))
        # Flow conditions remain part of the scoring view too.
        for relation in block.relations:
            result.extend(_TOKEN.findall(_normalize(f"{relation.relation} {relation.condition or ''}")))
    return tuple(result)


def _metadata_signals(left: ComparisonDocument, right: ComparisonDocument):
    a, b = left.metadata, right.metadata
    confirmed = a.confirmed and b.confirmed
    has_keys = bool(a.external_key and b.external_key and a.issuer and b.issuer)
    same_key = bool(has_keys and _normalize(a.external_key) == _normalize(b.external_key))
    same_issuer = bool(has_keys and _normalize(a.issuer) == _normalize(b.issuer))
    same_identity = left.document_id == right.document_id or bool(confirmed and same_key and same_issuer)
    x, y = dict((_normalize(k), _normalize(v)) for k, v in a.scope), dict((_normalize(k), _normalize(v)) for k, v in b.scope)
    different_scope = any(x[key] != y[key] for key in x.keys() & y.keys())
    # Time/version differences are NOT independent jurisdictions or audiences.
    independent_dimensions = {"province", "jurisdiction", "locality", "entity", "service", "audience"}
    def disjoint_values(first, second):
        universal = {"*", "all", "any", "toàn quốc", "cả nước", "toàn bộ", "tất cả", "national", "unknown"}
        if first == second or first in universal or second in universal:
            return False
        # Multi-valued/hierarchical free text is not proof of disjoint coverage.
        return not any(re.search(r"[,;/|]|\bvà\b|\bhoặc\b|bao gồm", value) for value in (first, second))
    independent_scope = any(disjoint_values(x[key], y[key]) for key in x.keys() & y.keys() & independent_dimensions)
    independent = bool(confirmed and has_keys and not same_identity and (not same_key or not same_issuer) and independent_scope)
    return {"same_identity": same_identity, "metadata_confirmed": confirmed,
            "independent_scope": independent,
            "distinct_identifiers": bool(confirmed and has_keys and (not same_key or not same_issuer)),
            "scope_difference": different_scope}


def _difference_types(a, b) -> tuple[str, ...]:
    changed = []
    for tag, i, j, k, l in SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag != "equal":
            changed.extend((*a[i:j], *b[k:l]))
    result = []
    if any(re.search(r"\d", token) for token in changed):
        result.append("numeric")
    if set(changed) & {"không", "chưa", "cấm", "phải", "được"}:
        result.append("negation_or_obligation")
    if set(changed) & {"đồng", "triệu", "tỷ", "ngày", "tháng", "năm", "%", "kg", "m2", "m²"}:
        result.append("unit_or_time")
    return tuple(result)


def _refs(refs, start, end):
    # For insert/delete, use a neighboring source position as an explicit anchor.
    anchor = start == end
    selected = refs[start:end] if not anchor else refs[max(0, min(start, len(refs) - 1)):max(0, min(start, len(refs) - 1)) + 1]
    result = []
    for ref in selected:
        value = to_json_value(ref)
        if value not in result:
            result.append(value)
    return result[:8], anchor, len(result) > 8


class NearDuplicateDetector:
    def __init__(self, *, masker: PIIMasker | None = None, mask_config: MaskConfig | None = None,
                 metadata_provider: Callable[[str], ComparisonMetadata] | None = None,
                 now: Callable[[], datetime] | None = None) -> None:
        require((masker is None) == (mask_config is None), "Supply both masker and mask_config")
        self.masker, self.mask_config = masker, mask_config
        self.metadata_provider = metadata_provider
        self.now = now or (lambda: datetime.now(timezone.utc))

    def compare(self, left: ComparisonDocument, right: ComparisonDocument, *,
                config: DedupConfig = DEFAULT_CONFIG) -> NearDuplicateComparison:
        require(config.algorithm == DEFAULT_CONFIG.algorithm and config.algorithm_version in ("1", "2")
                and config.fingerprint_config_id == DEFAULT_CONFIG.fingerprint_config_id,
                "Unsupported near-duplicate algorithm/normalization config")
        require(left.masking_config_id == right.masking_config_id, "Use the same masking policy for both sources")
        left, right = sorted((left, right), key=lambda doc: doc.identity)
        if left.identity == right.identity:
            require(canonical_checksum(left) == canonical_checksum(right), "Processing ID reused with different extraction")
            return NearDuplicateComparison(left=left.identity, right=right.identity, similarity=None, classification="self")
        a, a_refs = _sequence(left)
        b, b_refs = _sequence(right)
        if not a or not b:
            return NearDuplicateComparison(left=left.identity, right=right.identity, similarity=None, classification="not_comparable")
        matcher = SequenceMatcher(None, a, b, autojunk=False)
        score = matcher.ratio()
        body_a, body_b = _body_tokens(left), _body_tokens(right)
        body_score = SequenceMatcher(None, body_a, body_b, autojunk=False).ratio() if body_a and body_b else None
        signals = _metadata_signals(left, right)
        differences = _difference_types(body_a, body_b)
        important = bool(differences)
        priority, routing, reasons = "normal", "lexical", []
        improved = config.algorithm_version == "2"
        same_identity_change = improved and signals["same_identity"] and important
        if improved and score >= config.threshold and signals["independent_scope"]:
            return NearDuplicateComparison(left=left.identity, right=right.identity, similarity=score,
                classification="independent_template", body_similarity=body_score, routing_category="independent_scope",
                difference_types=differences, decision_reasons=("Confirmed distinct identifiers and scope; retain both independent sources",))
        template_only = (body_score is not None and body_score < config.threshold and min(len(body_a), len(body_b)) >= 5)
        if score < config.threshold and not same_identity_change:
            return NearDuplicateComparison(left=left.identity, right=right.identity, similarity=score,
                                           classification="different", body_similarity=body_score,
                                           difference_types=differences)
        if improved:
            if important:
                priority, routing = "high", "important_difference"
                reasons.append("Numbers, units, time or negation/obligation differ in substantive text")
            elif template_only and not signals["same_identity"]:
                priority, routing = "low", "boilerplate_similarity"
                reasons.append("Full-text similarity is dominated by preamble/footer; insufficient identity evidence to dismiss review")
            elif signals["distinct_identifiers"] and not signals["same_identity"]:
                priority, routing = "low", "shared_template_candidate"
                reasons.append("Distinct identifiers but insufficient scope evidence; keep review")
            elif any(block.ocr_confidence is not None and block.ocr_confidence < .8 for doc in (left, right) for block in doc.blocks):
                priority, routing = "low", "possible_ocr_difference"
                reasons.append("Low OCR confidence; OCR error is only a hypothesis, not confirmed")
            if same_identity_change and score < config.threshold:
                reasons.append("Important change for the same identity is reviewed even below the lexical threshold")
        classification = "same_content_candidate" if a == b else "near_duplicate"
        changes = []
        opcodes = [op for op in matcher.get_opcodes() if op[0] != "equal"]
        for tag, i, j, k, l in opcodes[:_MAX_HUNKS]:
            old, new = " ".join(a[i:j]), " ".join(b[k:l])
            left_refs, left_anchor, left_refs_truncated = _refs(a_refs, i, j)
            right_refs, right_anchor, right_refs_truncated = _refs(b_refs, k, l)
            changes.append({"operation": tag, "left": old[:_MAX_EXCERPT], "right": new[:_MAX_EXCERPT],
                            "left_token_range": [i, j], "right_token_range": [k, l],
                            "left_targets": left_refs, "right_targets": right_refs,
                            "left_is_anchor": left_anchor, "right_is_anchor": right_anchor,
                            "targets_truncated": left_refs_truncated or right_refs_truncated,
                            "excerpt_truncated": len(old) > _MAX_EXCERPT or len(new) > _MAX_EXCERPT})
        config_id = canonical_checksum(config)
        warnings = []
        if left.coverage != "complete" or right.coverage != "complete":
            warnings.append("extraction_coverage_not_complete")
        if any(block.image_artifact is not None or block.kind in ("image", "flow") for doc in (left, right) for block in doc.blocks):
            warnings.append("visual_or_flow_structure_not_fully_compared")
        evidence = {"left": list(left.identity), "right": list(right.identity), "similarity": score,
                    "classification": classification, "normalization": config.fingerprint_config_id,
                    "threshold": config.threshold, "masking_config_id": left.masking_config_id,
                    "left_token_count": len(a), "right_token_count": len(b), "changes": changes,
                    "total_diff_hunks": len(opcodes), "diff_truncated": len(opcodes) > _MAX_HUNKS,
                    "warnings": warnings,
                    "meaning": "Lexical similarity only; not a verified conflict, duplicate or replacement"}
        if improved:
            evidence.update({"body_similarity": body_score, "metadata_signals": signals, "review_priority": priority,
                             "routing_category": routing, "difference_types": list(differences), "decision_reasons": reasons})
        issue = QualityIssue(
            issue_id=canonical_checksum({"detector": "near_duplicate-v" + config.algorithm_version, "config": config_id,
                                         "left": left, "right": right}),
            code="dedup.same_content_candidate" if a == b else "dedup.near", severity="info" if priority == "low" else "warning",
            targets=tuple(TargetRef(version_id=doc.version_id,
                                   source_id=min(doc.blocks, key=lambda blk: blk.order).locator.source_id)
                          for doc in (left, right)),
            message="Similar masked source content requires review; retain both sources",
            safe_evidence=evidence, detector_name="near_duplicate", detector_version=config.algorithm_version,
            config_id=config_id, created_at=self.now())
        return NearDuplicateComparison(left=left.identity, right=right.identity, similarity=score,
                                       classification=classification, issue=issue, body_similarity=body_score,
                                       review_priority=priority, routing_category=routing,
                                       difference_types=differences, decision_reasons=tuple(reasons))

    def scan(self, documents: Sequence[ComparisonDocument], *, config: DedupConfig = DEFAULT_CONFIG) -> tuple[NearDuplicateComparison, ...]:
        """All unique unordered pairs, including below-threshold diagnostics."""
        unique = {}
        for document in documents:
            if document.identity in unique:
                require(canonical_checksum(unique[document.identity]) == canonical_checksum(document), "Conflicting processing identity")
            unique[document.identity] = document
        ordered = sorted(unique.values(), key=lambda doc: doc.identity)
        return tuple(self.compare(left, right, config=config) for index, left in enumerate(ordered) for right in ordered[index + 1:])

    def detect(self, source: SourceRecord, parsed: ParseResult, *, hint: IdentityHint,
               catalog: CatalogView, config: DedupConfig = DEFAULT_CONFIG) -> DedupResult:
        """DedupDetector adapter: mask candidate AND catalog extraction before diff.

        Nothing is auto-linked, even when all masked tokens match. The original
        exact-file registry remains responsible for compatible completed reuse.
        """
        require(self.masker is not None and self.mask_config is not None, "detect requires the team's PIIMasker implementation")
        require(source.source_id == parsed.processing.source_id, "Source differs from extraction")
        require(source.document_id is None or hint.document_id is None or source.document_id == hint.document_id,
                "Source and hint disagree on document identity")
        candidate_mask = self.masker.mask(parsed.blocks, config=self.mask_config)
        candidate = ComparisonDocument.from_parse(parsed, candidate_mask,
            document_id=hint.document_id or source.document_id or f"unresolved:{source.source_id}",
            metadata=self.metadata_provider(hint.document_id or source.document_id or f"unresolved:{source.source_id}") if self.metadata_provider
                else ComparisonMetadata(external_key=hint.external_key, issuer=hint.issuer))
        matches, findings = [], list(candidate_mask.findings)
        for document in catalog.documents(IdentityHint()):
            for version in catalog.versions(document.document_id):
                for processing in catalog.processing(version.version_id):
                    blocks = catalog.blocks(processing.processing_id)
                    existing = ParseResult(processing=processing, blocks=blocks)
                    masked = self.masker.mask(blocks, config=self.mask_config)
                    findings.extend(masked.findings)
                    compared = ComparisonDocument.from_parse(existing, masked, document_id=document.document_id,
                        metadata=self.metadata_provider(document.document_id) if self.metadata_provider
                            else ComparisonMetadata(external_key=document.external_key, issuer=document.issuer))
                    result = self.compare(candidate, compared, config=config)
                    if result.issue:
                        findings.append(result.issue)
                        matches.append(DedupMatch(candidate_version_id=version.version_id, kind=result.classification,
                                                 similarity=result.similarity, targets=result.issue.targets,
                                                 explanation="Lexically similar masked content; review both sources"))
        return DedupResult(matches=tuple(matches), action="review" if findings else "continue",
                           existing_version_id=None, findings=tuple(findings))
