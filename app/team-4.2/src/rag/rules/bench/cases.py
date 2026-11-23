"""Hồ sơ mẫu `tests/fixtures/rete/*` -> ca eval (định dạng: tests/fixtures/rete/README.md).

Hai dạng thư mục:
- hồ sơ nhiều văn bản (`dossier.yaml` + `objects.yaml` + `facts.yaml` theo kỳ + `gold.yaml` theo kỳ): một ca cho mỗi ngày
  soát mà gold cần (mọi `from` và ngày trước `from` kế tiếp), dựng như `tests/test_rete_dossiers.py`;
- bộ hợp đồng đơn lẻ (`facts.yaml` theo hợp đồng + `gold.yaml`): một ca cho mỗi hợp đồng ở ngày ký, dữ kiện đọc qua đúng
  các bộ đọc của luồng thật như `tests/test_rete_pack_fixtures.py`.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

import yaml

from rag.bridge.check import user_fact_set
from rag.bridge.facts_map import contract_facts, normalize_slot
from rag.rules.loader import load_packs
from rag.rules.model import Catalog
from rag.rules.objects import WorkingObject
from rag.rules.semantics import Fact, RuleResult

FIXTURES = Path(__file__).resolve().parents[4] / "tests" / "fixtures" / "rete"
# thư mục bộ đơn lẻ -> (gói, loại văn bản)
FLAT_SUITES: dict[str, tuple[str, str]] = {
    "loan": ("civil_loan", "loan_contract"),
    "lease": ("civil_lease", "lease_contract"),
    "consumer": ("consumer", "consumer_contract"),
    "commercial": ("commercial", "commercial_sale_contract"),
}


@dataclass(frozen=True)
class Expect:
    rule: str                 # "concept/rule"
    object: str | None        # nhóm của rule xuyên đối tượng; None với rule trên dữ kiện phẳng
    status: str


@dataclass(frozen=True)
class Case:
    suite: str
    case_id: str
    path: Path
    packs: tuple[str, ...]
    document_kind: str
    day: date
    facts: dict
    present: frozenset[str]
    objects: tuple[WorkingObject, ...]
    expected: tuple[Expect, ...]
    doc_files: tuple[str, ...] = ()    # văn bản chính của ca (không gồm phụ lục), để nhận diện loại
    labeled_by: str = ""


def result_key(r: RuleResult) -> str:
    return f"{r.concept_id}/{r.rule_id}" + (f"@{r.object}" if r.object else "")


def expect_key(e: Expect) -> str:
    return e.rule + (f"@{e.object}" if e.object else "")


@lru_cache(maxsize=None)
def catalog_for(packs: tuple[str, ...]) -> Catalog:
    return load_packs(list(packs))


def _yaml(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else None


def _day(v) -> date:
    return v if isinstance(v, date) else date.fromisoformat(str(v))


def gold_days(label: dict) -> list[tuple[date, str]]:
    """Mọi `from` của nhãn + ngày trước `from` kế tiếp (giữ trạng thái kỳ trước) — như tests/test_rete_dossiers.py."""
    ps = sorted(((_day(p["from"]), p["status"]) for p in label["periods"]), key=lambda x: x[0])
    out = list(ps)
    for (d0, s0), (d1, _) in zip(ps, ps[1:]):
        if d1 - d0 > timedelta(days=1):
            out.append((d1 - timedelta(days=1), s0))
    return out


def _objects(raw: list) -> tuple[WorkingObject, ...]:
    out = []
    for o in raw or []:
        attrs = {k: Fact(a["value"], a.get("unit"), "contract", None, a.get("quote")) for k, a in o["attrs"].items()}
        out.append(WorkingObject(o["id"], o["type"], attrs, _day(o["valid_from"]) if o.get("valid_from") else None,
                                 _day(o["valid_to"]) if o.get("valid_to") else None, dict(o.get("refs") or {})))
    return tuple(out)


def _facts_at(dossier: dict, facts: dict, day: date) -> dict:
    out = {k: Fact(v, None, "user") for k, v in (dossier.get("user_facts") or {}).items()}
    for name, values in (facts or {}).items():
        live = [v for v in values if _day(v["from"]) <= day]
        if live:
            v = max(live, key=lambda x: _day(x["from"]))
            out[name] = Fact(v["value"], v.get("unit"), "contract", None, v.get("quote"))
    return out


def _dossier_cases(here: Path, gold: dict) -> list[Case]:
    d = _yaml(here / "dossier.yaml")
    objects, facts = _objects(_yaml(here / "objects.yaml")), _yaml(here / "facts.yaml") or {}
    main = [x for x in d["documents"] if x["kind"] != "amendment"]
    by_day: dict[date, list[Expect]] = {}
    for label in gold["expected"]:
        for day, status in gold_days(label):
            by_day.setdefault(day, []).append(Expect(label["rule"], label.get("object"), status))
    return [Case(here.name, f"{here.name}@{day.isoformat()}", here, tuple(d["packs"]), main[0]["kind"], day,
                 _facts_at(d, facts, day), frozenset(), objects, tuple(exp),
                 tuple(x["file"] for x in main), str(gold.get("labeled_by") or ""))
            for day, exp in sorted(by_day.items())]


def _flat_facts(spec: dict, cat: Catalog, day: date) -> dict:
    candidates = {k: [{"value": v, "unit": "p0.d1", "quote": q}] for k, (v, q) in (spec.get("document") or {}).items()}
    facts = dict(contract_facts({"candidates": candidates}, sign_date=day, ctx=cat.context))
    for cid, slots in spec["slots"].items():
        for name, (raw, _q) in (slots or {}).items():
            f = normalize_slot(cat.concepts[cid].slots[name], raw, cat.context)
            if f is None:
                raise ValueError(f"slot không đọc được: {cid}.{name}={raw!r}")
            facts[name] = f
    facts.update(user_fact_set(spec.get("user_facts") or {}, cat.context))
    return facts


def _flat_cases(here: Path, gold: dict) -> list[Case]:
    pack, kind = FLAT_SUITES[here.name]
    cat, specs = catalog_for((pack,)), _yaml(here / "facts.yaml")
    labels: dict[str, list[Expect]] = {}
    for label in gold["expected"]:       # gold ghi object = hợp đồng; kết quả của rule phẳng không có object
        labels.setdefault(label["object"], []).append(Expect(label["rule"], None, label["periods"][0]["status"]))
    out = []
    for doc in sorted(specs):
        spec = specs[doc]
        day = _day(spec["sign_date"])
        out.append(Case(here.name, doc, here, (pack,), kind, day, _flat_facts(spec, cat, day), frozenset(spec["slots"]),
                        (), tuple(labels.get(doc, ())), (f"{doc}.txt",), str(gold.get("labeled_by") or "")))
    return out


def load_cases(root: Path = FIXTURES) -> tuple[list[Case], list[str]]:
    """(ca, thư mục không có gold.yaml). Thư mục không thuộc dạng nào cũng báo ở danh sách thứ hai."""
    cases, no_gold = [], []
    for here in sorted(p for p in Path(root).iterdir() if p.is_dir()):
        gold = _yaml(here / "gold.yaml")
        if not gold or not gold.get("expected"):
            no_gold.append(here.name)
        elif (here / "dossier.yaml").exists():
            cases += _dossier_cases(here, gold)
        elif here.name in FLAT_SUITES:
            cases += _flat_cases(here, gold)
        else:
            no_gold.append(here.name)
    return cases, no_gold


__all__ = ["Case", "Expect", "FIXTURES", "FLAT_SUITES", "catalog_for", "expect_key", "gold_days", "load_cases",
           "result_key"]
