"""Điều phối hỏi đáp theo mốc: che PII -> dòng thời gian -> truy xuất kho có phiên bản theo từng mốc (+ kho cũ để tham
khảo, bỏ bản trùng) -> trạng thái hai tầng -> quy định chuyển tiếp -> LLM -> backend hạ mức chắc chắn -> nhật ký."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any

from rag.legal.chunks import VersionedChunk
from rag.legal.service import LegalService
from rag.legal.store import encode
from rag.quality.pii import QUERY_PREFIX, MaskState, mask_text
from rag.schema import Chunk
from rag.temporal.answer import ContextItem, TemporalAnswer, build_messages, enforce, parse_answer
from rag.temporal.index import VersionedIndex
from rag.temporal.log import QALog
from rag.temporal.models import LegalTimeline, TransitionRule
from rag.temporal.status import LegacyLaw, legacy_duplicates, legacy_status, versioned_status
from rag.temporal.timeline import build_timeline

REFUSAL = "Không có trong tài liệu."


@dataclass
class TemporalResult:
    timeline: LegalTimeline
    items: list[ContextItem]
    rules: list[TransitionRule]
    answer: TemporalAnswer
    log_id: str | None = None
    query_pii: dict[str, int] = field(default_factory=dict)
    llm_called: bool = False


def _now() -> datetime:
    return datetime.now(timezone.utc)


class TemporalQA:
    def __init__(self, service: LegalService, index: VersionedIndex, llm: Any, *,
                 legacy_search: Callable[[str, int], Sequence[Chunk]] | None = None,
                 legacy_map: Mapping[str, LegacyLaw] | None = None, log: QALog | None = None,
                 k_per_anchor: int = 6, k_legacy: int = 4, now: Callable[[], datetime] = _now) -> None:
        self.service, self.index, self.llm = service, index, llm
        self.legacy_search, self.legacy_map = legacy_search, dict(legacy_map or {})
        self.log, self.k_per_anchor, self.k_legacy, self.now = log, k_per_anchor, k_legacy, now

    # --- truy xuất ---------------------------------------------------------------------------

    def _versioned(self, query: str, timeline: LegalTimeline) -> tuple[list[VersionedChunk], dict[str, set[str]],
                                                                         dict[str, tuple[date, date]], bool]:
        picked: dict[str, VersionedChunk] = {}
        roles: dict[str, set[str]] = {}
        window: dict[str, tuple[date, date]] = {}          # chunk_id -> khoảng của mốc đã lấy nó
        year_change = False
        for anchor in timeline.anchors:
            if anchor.start is None:
                continue
            end = anchor.end or anchor.start
            for chunk, _ in self.index.search(query, anchor.start, end, self.k_per_anchor):
                picked.setdefault(chunk.chunk_id, chunk)
                roles.setdefault(chunk.chunk_id, set()).add(anchor.role)
                window.setdefault(chunk.chunk_id, (anchor.start, end))
                # phiên bản không phủ kín khoảng mốc -> luật (Điều hoặc cả văn bản) đổi bên trong khoảng
                if anchor.start != end and (chunk.valid_from > anchor.start
                                            or (chunk.valid_to is not None and chunk.valid_to <= end)):
                    year_change = True
        return list(picked.values()), roles, window, year_change

    def _document_status(self, key: str, start: date, end: date) -> str:
        at = [c for c in self.index.chunks.values() if c.document_key == key and c.valid_from <= end
              and (c.valid_to is None or c.valid_to > start)]
        return versioned_status(at)

    def _provenance(self, chunk: VersionedChunk) -> tuple[str, ...]:
        out = []
        for op_id in chunk.source_operations:
            op = self.service.store.operation(op_id)
            if op is not None and op.source_document_key not in out:
                out.append(op.source_document_key)
        return tuple(out)

    # --- hỏi ---------------------------------------------------------------------------------

    def ask(self, question: str, *, calendar_date: date | None = None,
            mask_state: MaskState | None = None) -> TemporalResult:
        asked_at = self.now()
        state = mask_state if mask_state is not None else MaskState(prefix=QUERY_PREFIX)
        before = dict(state.counts)
        query = mask_text(question, state=state).masked_text
        query_pii = {k: v - before.get(k, 0) for k, v in state.counts.items() if v - before.get(k, 0)}

        timeline = build_timeline(query, asked_at=asked_at, calendar_date=calendar_date, llm=self.llm)
        chunks, roles, window, year_change = self._versioned(query, timeline)
        store = self.service.store
        titles = {d.document_key: d.title for d in store.documents()}

        items: list[ContextItem] = []
        for c in chunks:
            start, end = window[c.chunk_id]
            items.append(ContextItem(
                len(items) + 1, "versioned", c.document_key, titles.get(c.document_key, c.document_key), c.article_id,
                c.section, c.text, c.valid_from, c.valid_to, self._document_status(c.document_key, start, end),
                c.verification_status, self._provenance(c), tuple(sorted(roles[c.chunk_id])), c.chunk_id))

        if self.legacy_search is not None:
            duplicates = legacy_duplicates(store, self.legacy_map)
            p = timeline.primary
            p_start = p.start or asked_at.date()
            p_end = p.end or p_start
            for chunk in self.legacy_search(query, self.k_legacy):
                if chunk.source in duplicates:
                    continue
                law = self.legacy_map.get(chunk.source)
                items.append(ContextItem(
                    len(items) + 1, "legacy", None, chunk.source, None, chunk.section or "", chunk.text, None, None,
                    legacy_status(store, law, start=p_start, end=p_end), None, (), (), chunk.chunk_id))

        rules = collect_rules(self.service, chunks, timeline) if chunks else []
        if not items:
            answer = TemporalAnswer(REFUSAL, certainty="cannot_conclude", downgrade_reasons=["certainty.no_context"])
            result = TemporalResult(timeline, items, rules, answer, query_pii=query_pii)
        else:
            system, user = build_messages(query, timeline, items, rules)
            raw = self.llm.complete(system, user)
            answer = enforce(parse_answer(raw), items, rules, timeline, year_change=year_change)
            result = TemporalResult(timeline, items, rules, answer, query_pii=query_pii, llm_called=True)
        if self.log is not None:
            result.log_id = self.log.record({
                "asked_at": asked_at.isoformat(), "question": query, "timeline": encode(timeline),
                "builds": {c.document_key: c.build_id for c in chunks},
                "items": [encode(i) | {"text": None} for i in items], "rules": encode(rules),
                "answer": encode(result.answer), "year_change": year_change})
        result.answer.answer_markdown = state.unmask(result.answer.answer_markdown)
        return result


def collect_rules(service: LegalService, chunks: Sequence[VersionedChunk], timeline: LegalTimeline):
    from rag.temporal.transitions import collect_transition_rules

    return collect_transition_rules(service, chunks, timeline)


__all__ = ["REFUSAL", "TemporalQA", "TemporalResult"]
