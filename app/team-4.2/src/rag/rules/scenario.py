"""E3: chạy hồ sơ nhiều văn bản theo kịch bản từng bước thành dòng sự kiện (UI Contract Studio, spec 2026-11-22 §8).

Không phụ thuộc UI: `run_scenario` là generator các dict JSON được; route SSE ở `ui/contracts_api.py` chỉ chuyển tiếp.
Đọc hồ sơ theo định dạng `tests/fixtures/rete/README.md` (dossier.yaml, objects.yaml, facts.yaml, scenario.yaml).

Sự kiện (mỗi bước, theo thứ tự): `step` → `evaluation` (bước load: toàn bộ kết quả) hoặc `evaluation_diff` (các bước còn lại: rule
đổi trạng thái + số nút tính lại) → `explain` (cây giải thích của từng rule vừa đổi) → `expect` (so với `expect` trong kịch bản)
→ `questions` (câu hỏi gợi ý tiếp theo). Kết thúc luồng (`done` / `error`) do nơi gọi thêm."""
from __future__ import annotations

import dataclasses
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterator

import yaml

from rag.rules.evaluator import Diff, diff_results, evaluator_for
from rag.rules.events import diff_event
from rag.rules.explain import explain
from rag.rules.loader import load_packs
from rag.rules.objects import ObjectChanges, WorkingObject
from rag.rules.questions import next_questions
from rag.rules.semantics import Fact

DOSSIER_ROOT = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "rete"
EVALUATORS = ("reference", "network")
STEPS = ("load", "set_review_date", "add", "remove", "answer")


def _yaml(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else None


def _day(v) -> date:
    return v if isinstance(v, date) else date.fromisoformat(str(v))


@lru_cache(maxsize=None)
def _catalog(packs: tuple[str, ...]):
    return load_packs(list(packs))


def _dossier(did: str, root: Path) -> dict:
    d = _yaml(Path(root) / did / "dossier.yaml")
    if d is None:
        raise ValueError(f"Hồ sơ {did!r} không có")
    d["objects"] = _yaml(Path(root) / did / "objects.yaml") or []
    d["facts"] = _yaml(Path(root) / did / "facts.yaml") or {}
    d["scenario"] = _yaml(Path(root) / did / "scenario.yaml")
    return d


def list_dossiers(root: Path = DOSSIER_ROOT) -> list[dict]:
    out = []
    for p in sorted(Path(root).glob("*/dossier.yaml")):
        d = _yaml(p)
        out.append({"dossier_id": p.parent.name, "packs": list(d.get("packs") or []),
                    "has_scenario": (p.parent / "scenario.yaml").exists()})
    return out


def objects_of(d: dict) -> list[WorkingObject]:
    out = []
    for o in d["objects"]:
        attrs = {k: Fact(a["value"], a.get("unit"), "contract", None, a.get("quote")) for k, a in o["attrs"].items()}
        out.append(WorkingObject(o["id"], o["type"], attrs, _day(o["valid_from"]) if o.get("valid_from") else None,
                                 _day(o["valid_to"]) if o.get("valid_to") else None, dict(o.get("refs") or {})))
    return out


def facts_at(d: dict, day: date) -> dict:
    facts = {k: Fact(v, None, "user") for k, v in (d.get("user_facts") or {}).items()}
    for name, values in d["facts"].items():
        live = [v for v in values if _day(v["from"]) <= day]
        if live:
            v = max(live, key=lambda x: _day(x["from"]))
            facts[name] = Fact(v["value"], v.get("unit"), "contract", None, v.get("quote"))
    return facts


def object_changes(before: list[WorkingObject], after: list[WorkingObject]) -> ObjectChanges:
    old, new = {o.id: o for o in before}, {o.id: o for o in after}
    return ObjectChanges(added=tuple(o for i, o in new.items() if i not in old),
                         removed=tuple(i for i in old if i not in new),
                         changed=tuple(o for i, o in new.items() if i in old and old[i] != o))


def result_key(r) -> str:
    return f"{r.concept_id}/{r.rule_id}" + (f"@{r.object}" if r.object else "")


def run_scenario(dossier_id: str, *, evaluator: str = "network", root: Path = DOSSIER_ROOT,
                 answers: dict[str, Any] | None = None) -> Iterator[dict]:
    """`answers`: dữ kiện người dùng trả lời trước khi chạy ({tên: giá trị}). Hồ sơ không có kịch bản: chỉ một bước load ở
    ngày soát của hồ sơ."""
    if evaluator not in EVALUATORS:
        raise ValueError(f"evaluator phải là một trong {EVALUATORS}, không phải {evaluator!r}")
    first = _dossier(dossier_id, root)
    steps = (first["scenario"] or {}).get("steps") or [
        {"do": "load", "state": dossier_id, "review_date": first.get("review_date"), "say": "Soát hồ sơ"}]
    answered: dict[str, Fact] = {k: Fact(v, None, "user") for k, v in (answers or {}).items()}
    session = cat = state = day = d = None
    for i, step in enumerate(steps):
        do = step.get("do")
        if do not in STEPS:
            raise ValueError(f"bước {i}: thao tác lạ {do!r}")
        changed: list = []
        if do in ("load", "set_review_date"):
            state = step.get("state", state) or dossier_id
            day = _day(step["review_date"] if do == "load" else step["value"])
            d = _dossier(state, root)
            cat = _catalog(tuple(d["packs"]))
            before = session.results() if session is not None and do == "set_review_date" else None
            session = evaluator_for(cat, evaluator).session(day=day, facts={**facts_at(d, day), **answered},
                                                            present=set(), evidence={}, objects=objects_of(d))
            if before is not None:
                diff = Diff(tuple(diff_results(before, session.results())))
        elif do in ("add", "remove"):
            before_objects, state = objects_of(d), step["state"]
            d = _dossier(state, root)
            diff = session.update({}, objects=object_changes(before_objects, objects_of(d)))
        else:
            facts = {k: Fact(v, None, "user") for k, v in step["facts"].items()}
            answered.update(facts)
            diff = session.update(facts)
        yield {"type": "step", "index": i, "do": do, "say": step.get("say"), "dossier": state,
               "review_date": day.isoformat()}
        if do == "load" or (do == "set_review_date" and before is None):
            results = session.results()
            yield {"type": "evaluation", "step": i, "results": [dataclasses.asdict(r) for r in results]}
        else:
            cause = {"kind": do, **({"value": day.isoformat()} if do == "set_review_date" else {}),
                     **({"docs": step.get("docs")} if do in ("add", "remove") else {}),
                     **({"facts": step["facts"]} if do == "answer" else {})}
            yield {**diff_event(diff, getattr(session, "stats", None)), "step": i, "cause": cause}
            changed = [c for c in diff.changes if c.after is not None]
            results = session.results()
        for c in changed:
            yield {"type": "explain", "step": i, "concept_id": c.concept_id, "rule_id": c.rule_id, "object": c.object,
                   "tree": explain(cat, session, c.concept_id, c.rule_id, c.object).to_json()}
        got = {result_key(r): r.status for r in results}
        expected = step.get("expect") or {}
        yield {"type": "expect", "step": i,
               "results": [{"key": k, "expected": v, "got": got.get(k), "ok": got.get(k) == v} for k, v in expected.items()]}
        yield {"type": "questions", "step": i, "items": [dataclasses.asdict(q) for q in next_questions(cat, session)]}
