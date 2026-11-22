"""Giải thích một kết quả rule (spec §8): cây từ RuleResult tới điều kiện, giá trị luật (kèm nguồn kỳ), dữ kiện (kèm
quote hợp đồng), dữ kiện suy ra (định nghĩa thắng, ngoại lệ bị loại) và ngoại lệ giữa rule. Chỉ đọc, không đổi ngữ nghĩa."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from rag.rules.model import Catalog, Context, DerivedFact, Rule
from rag.rules.semantics import (CONFLICT, UNKNOWN, Facts, check_cond, eval_cond, is_unresolved, referenced)


@dataclass
class ExplanationNode:
    kind: str                       # rule | applicability | case | law | check | all | any | not | condition | exception | fact | derived | definition
    label: str
    status: str | None = None       # trạng thái rule (PASS...) hoặc trị T / F / U của điều kiện
    detail: dict[str, Any] = field(default_factory=dict)
    children: list["ExplanationNode"] = field(default_factory=list)

    def to_json(self) -> dict:
        return {"kind": self.kind, "label": self.label, "status": self.status, "detail": self.detail,
                "children": [c.to_json() for c in self.children]}

    def to_markdown(self, depth: int = 0) -> str:
        brief = "; ".join(f"{k}={v}" for k, v in self.detail.items() if v not in (None, [], {}, ()) and k != "anchors")
        head = f"{'  ' * depth}- **{self.kind}** {self.label}" + (f" [{self.status}]" if self.status else "")
        lines = [head + (f" — {brief}" if brief else "")]
        lines += [c.to_markdown(depth + 1) for c in self.children]
        return "\n".join(lines)


def _fact_detail(name: str, facts: Facts) -> dict:
    f = facts.get(name)
    if f is None:
        return {"value": "thiếu"}
    if is_unresolved(f):
        return {"value": repr(f)}
    out = {"value": f.value, "unit": f.unit, "source": f.source, "uid": f.uid, "quote": f.quote}
    if f.derived_by:
        out["derived_by"] = f.derived_by
    if f.amended_from:
        out["amended_from"] = list(f.amended_from)
    if f.later_amendments:
        out["later_amendments"] = list(f.later_amendments)
    return out


def _cond_node(cond: dict, facts: Facts, ctx: Context, law: dict | None = None) -> ExplanationNode:
    check = law is not None
    for key in ("all", "any"):
        if key in cond:
            st = (check_cond(cond, facts, law, ctx) if check and key == "all" else eval_cond(cond, facts, ctx))
            return ExplanationNode(key, key, st, children=[_cond_node(c, facts, ctx, law) for c in cond[key]])
    if "not" in cond:
        return ExplanationNode("not", "not", eval_cond(cond, facts, ctx), children=[_cond_node(cond["not"], facts, ctx, law)])
    st = check_cond(cond, facts, law, ctx) if check else eval_cond(cond, facts, ctx)
    right = f"law:{cond['law']}" if "law" in cond else cond.get("value")
    detail = {"fact": cond.get("fact"), "op": cond.get("op"), "value": right, "unit": cond.get("unit")}
    node = ExplanationNode("condition", f"{cond.get('fact')} {cond.get('op')} {right}", st, detail)
    node.children.append(_fact_node(cond["fact"], facts, ctx)) if cond.get("fact") else None
    return node


def _definition_nodes(df: DerivedFact, facts: Facts, ctx: Context) -> list[ExplanationNode]:
    winner = getattr(facts.get(df.fact), "derived_by", None)
    kids: dict[str | None, list] = {}
    for d in df.definitions:
        kids.setdefault(d.exception_of, []).append(d)

    def subtree(d) -> list:
        ids = {d.id}
        for c in kids.get(d.id, ()):
            ids |= {x.id for x in df.definitions if x.id == c.id} | {n for n in subtree(c)}
        return list(ids)

    out = []
    for d in df.definitions:
        when = eval_cond(d.when, facts, ctx)
        if d.id == winner:
            outcome = "chosen"
        elif when == "F":
            outcome = "excluded_when_false"
        elif winner in subtree(d):
            outcome = "overridden_by_exception"
        else:
            outcome = "not_chosen"
        node = ExplanationNode("definition", d.id, when, {
            "outcome": outcome, "exception_of": d.exception_of, "anchors": [dict(a) for a in d.anchors],
            "from": d.from_fact, "value": d.value if d.has_value else None})
        if d.when is not None:
            node.children.append(_cond_node(d.when, facts, ctx))
        out.append(node)
    return out


def _fact_node(name: str, facts: Facts, ctx: Context) -> ExplanationNode:
    node = ExplanationNode("fact", name, None, _fact_detail(name, facts))
    if name in ctx.derived:
        f = facts.get(name)
        node.children.append(ExplanationNode("derived", name, None, {
            "value": _fact_detail(name, facts).get("value"), "derived_by": getattr(f, "derived_by", None)},
            _definition_nodes(ctx.derived[name], facts, ctx)))
    return node


def _law_nodes(rule: Rule, chosen: dict | None, facts: Facts, day: date) -> list[ExplanationNode]:
    merged = {**rule.law, **((chosen or {}).get("law") or {})}
    out = []
    for name, v in merged.items():
        detail: dict[str, Any] = {"unit": v.get("unit")}
        if "periods" in v:
            live = [p for p in v["periods"] if date.fromisoformat(str(p["valid_from"])) <= day]
            if live:
                p = max(live, key=lambda p: str(p["valid_from"]))
                detail |= {"by": v.get("by"), "source": p.get("source"), "valid_from": str(p["valid_from"])}
                if v.get("by") is None:
                    detail["value"] = p.get("value")
                else:
                    key = facts.get(v.get("by"))
                    detail["value"] = None if key is None or is_unresolved(key) else p["values"].get(key.value)
        else:
            detail["value"] = v.get("value")
        out.append(ExplanationNode("law", name, None, detail))
    return out


def explain(catalog: Catalog, session, concept_id: str, rule_id: str, obj: str | None = None) -> ExplanationNode:
    """Cây giải thích kết quả của `concept_id/rule_id` (nhóm `obj` với rule xuyên đối tượng) trong `session`.
    Rule xuyên đối tượng: cây dừng ở số đếm của nhóm (`reasons` có `count:a..b`); chưa mở tới từng đối tượng."""
    rule = next((r for r in catalog.concepts[concept_id].rules if r.id == rule_id), None) if concept_id in catalog.concepts else None
    matches = [x for x in session.results() if (x.concept_id, x.rule_id) == (concept_id, rule_id)
               and (obj is None or x.object == obj)]
    if obj is None and len(matches) > 1:
        raise KeyError(f"{concept_id}/{rule_id} có {len(matches)} nhóm: truyền obj (một trong "
                       f"{[x.object for x in matches]})")
    result = matches[0] if matches else None
    if rule is None or result is None:
        raise KeyError(f"{concept_id}/{rule_id}")
    ctx, facts, day = catalog.context, session.facts(), session.day
    root = ExplanationNode("rule", f"{concept_id}/{rule_id}", result.status, {
        "finding": result.finding, "reasons": list(result.reasons), "missing_facts": list(result.missing_facts),
        "mode": rule.mode, "derogation": rule.derogation, "object": result.object})
    if rule.applicability is not None:
        root.children.append(ExplanationNode("applicability", "applicability", eval_cond(rule.applicability, facts, ctx),
                                             children=[_cond_node(rule.applicability, facts, ctx)]))
    chosen = None
    if rule.cases:
        chosen = next((c for c in rule.cases if eval_cond(c.get("when"), facts, ctx) == "T"), None)
        first = True
        for case in rule.cases:
            st = eval_cond(case.get("when"), facts, ctx)
            is_chosen = case is chosen and first
            first = first and not is_chosen
            root.children.append(ExplanationNode("case", str(case.get("when")), st, {"chosen": is_chosen},
                                                 [_cond_node(case["when"], facts, ctx)] if case.get("when") else []))
    root.children += _law_nodes(rule, chosen, facts, day)
    if rule.over is not None:
        var, typ, where, history = rule.over
        root.children.append(ExplanationNode("objects", f"{var}: {typ}", None, {
            "where": where, "history": history, "group_by": dict(rule.group_by), "check": rule.check,
            "count": next((r.split(":", 1)[1] for r in result.reasons if r.startswith("count:")), None)}))
    elif rule.check is not None:
        root.children.append(ExplanationNode("check", "check", check_cond(rule.check, facts, result.law_values, ctx),
                                             children=[_cond_node(rule.check, facts, ctx, result.law_values)]))
    by_key = {f"{x.concept_id}/{x.rule_id}": x for x in session.results()}
    for reason in result.reasons:
        for rel in ("overridden_by", "exception_unknown"):
            if reason.startswith(rel + ":"):
                key = reason.split(":", 1)[1]
                other = by_key.get(key)
                root.children.append(ExplanationNode("exception", key, other.status if other else None,
                                                     {"relation": rel, "finding": other.finding if other else None}))
    for name in referenced(rule):
        if not any(n.kind == "fact" and n.label == name for n in root.children):
            root.children.append(_fact_node(name, facts, ctx))
    return root
