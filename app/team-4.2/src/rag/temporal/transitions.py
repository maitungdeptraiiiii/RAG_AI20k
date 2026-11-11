"""Quy định chuyển tiếp (phương án a): backend tìm các Điều chuyển tiếp liên quan và đưa TOÀN VĂN vào ngữ cảnh dưới
dạng `TransitionRule`; LLM đánh giá. Không suy diễn điều kiện áp dụng ở đây."""

from __future__ import annotations

import re
from collections.abc import Sequence

from rag.legal.chunks import VersionedChunk
from rag.legal.service import LegalService
from rag.legal.targets import law_name
from rag.temporal.models import LegalTimeline, TransitionRule

_TRANSITION_TITLE = re.compile(r"chuyển\s+tiếp", re.IGNORECASE)


def _transition_articles(service: LegalService, key: str) -> list[tuple[str, str]]:
    """(số Điều, toàn văn) của mọi Điều có tiêu đề "chuyển tiếp" trong văn bản."""
    provisions = service.provisions_for(key)
    titles = {p.address.article: p.text for p in provisions if p.kind == "article_title"}
    return [(p.address.article, p.text) for p in provisions
            if p.kind == "article" and _TRANSITION_TITLE.search(titles.get(p.address.article, ""))]


def _article_text(service: LegalService, key: str, article: str) -> str | None:
    return next((p.text for p in service.provisions_for(key) if p.kind == "article" and p.address.article == article),
                None)


def collect_transition_rules(service: LegalService, used: Sequence[VersionedChunk],
                             timeline: LegalTimeline) -> list[TransitionRule]:
    store = service.store
    rules: dict[str, TransitionRule] = {}
    roles = tuple(dict.fromkeys(a.role for a in timeline.anchors if a.source != "default"))

    # (i) phiên bản do văn bản sửa đổi có Điều chuyển tiếp tạo ra
    for c in used:
        for note in c.notes:
            if not note.startswith("note:transition:"):
                continue
            ref = note[len("note:transition:"):]
            doc_key, _, art = ref.rpartition("#d")
            if not doc_key or store.document(doc_key) is None or ref in rules:
                continue
            text = _article_text(service, doc_key, art)
            if text:
                rules[ref] = TransitionRule(ref, doc_key, f"Điều {art}", text, None, c.document_key,
                                            service.current_effective_from(doc_key), roles)

    # (ii) cùng một luật (theo tên) nhưng các mốc rơi vào các văn bản khác nhau -> Điều chuyển tiếp của văn bản mới hơn
    families: dict[str, set[str]] = {}
    for c in used:
        doc = store.document(c.document_key)
        if doc is not None:
            families.setdefault(law_name(doc.title), set())
    dated = [a for a in timeline.anchors if a.start is not None]
    for name in families:
        members = {d.document_key: d for d in store.law_family(name)}
        if len(members) < 2:
            continue
        in_force: dict[str, set[str]] = {}
        for a in dated:
            # mốc là khoảng (năm, tháng...) có thể trùm ngày đổi luật: xét cả đầu và cuối khoảng
            for day in dict.fromkeys((a.start, a.end or a.start)):
                for d in store.laws_in_force(day):
                    if d.document_key in members:
                        in_force.setdefault(d.document_key, set()).add(a.role)
        if len(in_force) < 2:
            continue
        ordered = sorted(in_force, key=lambda k: members[k].issued_on or members[k].fetched_at.date())
        new_key, old_keys = ordered[-1], ordered[:-1]
        related = tuple(dict.fromkeys(r for k in ordered for r in sorted(in_force[k])))
        for art, text in _transition_articles(service, new_key):
            rule_id = f"{new_key}#d{art}"
            if rule_id not in rules:
                rules[rule_id] = TransitionRule(rule_id, new_key, f"Điều {art}", text, old_keys[-1], new_key,
                                                service.current_effective_from(new_key), related)
    return list(rules.values())


__all__ = ["collect_transition_rules"]
