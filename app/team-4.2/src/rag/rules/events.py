"""Sự kiện stream của bộ đánh giá rule (spec §8): `evaluation_diff` cho UI vẽ phần lan truyền sau mỗi `update`."""
from __future__ import annotations

from typing import Any, Mapping

from rag.rules.evaluator import Diff
from rag.rules.semantics import RuleResult


def _brief(r: RuleResult | None) -> dict | None:
    if r is None:
        return None
    return {"status": r.status, "finding": r.finding, "reasons": list(r.reasons), "missing_facts": list(r.missing_facts),
            "object": r.object}


def diff_event(diff: Diff, stats: Mapping[str, Any] | None = None) -> dict:
    """`{type: "evaluation_diff", changes: [{concept_id, rule_id, before, after}], stats}`; `stats` là số nút / rule được
    tính lại (chỉ Network có)."""
    return {"type": "evaluation_diff",
            "changes": [{"concept_id": c.concept_id, "rule_id": c.rule_id, "object": c.object,
                         "before": _brief(c.before), "after": _brief(c.after)} for c in diff.changes],
            "stats": dict(stats) if stats else None}
