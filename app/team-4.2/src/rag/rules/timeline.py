"""Soát theo kỳ (checklist D28): đánh giá một hồ sơ ở các ngày ranh giới rồi gộp thành khoảng thời gian.

Kết quả của rule chỉ đổi khi ngày soát vượt một ranh giới: ngày một đối tượng bắt đầu / thôi hiệu lực, hoặc ngày một
kỳ giá trị luật bắt đầu (`periods[].valid_from`). Vì vậy đủ đánh giá ở các ngày đó, mỗi ngày một phiên mới (ngày soát là
đầu vào của phiên, spec §6.2)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Sequence

from rag.rules.model import Catalog
from rag.rules.objects import WorkingObject
from rag.rules.semantics import Facts, RuleResult


@dataclass(frozen=True)
class Period:
    concept_id: str
    rule_id: str
    object: str | None
    start: date
    end: date
    status: str
    finding: str


def review_days(catalog: Catalog, objects: Sequence[WorkingObject], start: date, end: date) -> list[date]:
    """Ngày ranh giới trong `[start, end]`: `start`, mỗi `valid_from`, ngày sau mỗi `valid_to`, đầu mỗi kỳ giá trị luật."""
    if end < start:
        raise ValueError(f"khoảng soát ngược: {start} > {end}")
    days = {start}
    for o in objects:
        if o.valid_from is not None and o.valid_from != date.min:
            days.add(o.valid_from)
        if o.valid_to is not None and o.valid_to < date.max:
            days.add(o.valid_to + timedelta(days=1))
    for concept in catalog.concepts.values():
        for rule in concept.rules:
            for law in (rule.law, *[c.get("law") or {} for c in rule.cases]):
                for v in law.values():
                    for p in (v.get("periods") or []) if isinstance(v, dict) else []:
                        days.add(date.fromisoformat(str(p["valid_from"])))
    return sorted(d for d in days if start <= d <= end)


def review_timeline(evaluator, *, days: Sequence[date], facts: Facts, present: set[str],
                    evidence: dict[str, list[dict]], objects: Sequence[WorkingObject] = ()) -> dict[date, list[RuleResult]]:
    """Kết quả toàn catalog tại từng ngày trong `days`."""
    return {d: evaluator.session(day=d, facts=facts, present=present, evidence=evidence, objects=objects).results()
            for d in days}


def periods(timeline: dict[date, list[RuleResult]], end: date) -> list[Period]:
    """Gộp các ngày liên tiếp cùng (status, finding) của mỗi (concept, rule, nhóm) thành khoảng; khoảng cuối kéo tới `end`."""
    days = sorted(timeline)
    out: list[Period] = []
    open_: dict[tuple, Period] = {}
    for i, d in enumerate(days):
        seen = set()
        for r in timeline[d]:
            key = (r.concept_id, r.rule_id, r.object)
            seen.add(key)
            cur = open_.get(key)
            if cur is not None and (cur.status, cur.finding) == (r.status, r.finding):
                continue
            if cur is not None:
                out.append(Period(*key, cur.start, d - timedelta(days=1), cur.status, cur.finding))
            open_[key] = Period(*key, d, end, r.status, r.finding)
        for key in [k for k in open_ if k not in seen]:          # nhóm biến mất (đối tượng thôi hiệu lực)
            cur = open_.pop(key)
            out.append(Period(*key, cur.start, d - timedelta(days=1), cur.status, cur.finding))
    out += open_.values()
    return sorted(out, key=lambda p: (p.concept_id, p.rule_id, p.object or "", p.start))
