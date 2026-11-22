"""Hồ sơ nhiều văn bản (C1, C2, C3b r1, C4, C5, C6, C7): định dạng tests/fixtures/rete/README.md.

Kiểm: dossier.yaml đúng định dạng và đúng gói; parser đọc được mọi văn bản (Điều, phụ lục, ngày hiệu lực); bảng đối
tượng khớp khai báo gói và câu trích nguyên văn; nhãn gold theo kỳ ở cả Reference và Network; không có FAIL ngoài
gold (trên rule xuyên đối tượng và rule có dữ kiện trong hồ sơ); kịch bản chạy từng bước bằng phiên tăng dần và mỗi bước
khớp kết quả tính lại từ đầu."""
from __future__ import annotations

import dataclasses
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

import pytest
import yaml

from legal_corpus import ROOTS, law_text
from rag.contracts.amendments import find_amendments
from rag.contracts.doc import PageText
from rag.contracts.structure import parse_contract
from rag.rules.evaluator import evaluator_for
from rag.rules.loader import load_pack, load_packs, packs_for_kind
from rag.rules.objects import ObjectChanges, WorkingObject
from rag.rules.semantics import Fact, fact_names

HERE = Path(__file__).parent / "fixtures" / "rete"
DOSSIERS = sorted(p.parent.name for p in HERE.glob("*/dossier.yaml"))
STATUSES = {"PASS", "FAIL", "UNKNOWN", "NOT_APPLICABLE"}


def _yaml(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else None


def _day(v) -> date:
    return v if isinstance(v, date) else date.fromisoformat(str(v))


def _norm(s: str) -> str:
    return " ".join(str(s).split())


@lru_cache(maxsize=None)
def dossier(did: str) -> dict:
    d = _yaml(HERE / did / "dossier.yaml")
    d["objects"] = _yaml(HERE / did / "objects.yaml") or []
    d["facts"] = _yaml(HERE / did / "facts.yaml") or {}
    d["gold"] = _yaml(HERE / did / "gold.yaml")
    d["scenario"] = _yaml(HERE / did / "scenario.yaml")
    return d


@lru_cache(maxsize=None)
def catalog(packs: tuple[str, ...]):
    return load_packs(list(packs))


def text(did: str, doc_id: str) -> str:
    return (HERE / did / f"{doc_id}.txt").read_text(encoding="utf-8")


def objects_of(did: str) -> list[WorkingObject]:
    out = []
    for o in dossier(did)["objects"]:
        attrs = {k: Fact(a["value"], a.get("unit"), "contract", None, a.get("quote")) for k, a in o["attrs"].items()}
        out.append(WorkingObject(o["id"], o["type"], attrs, _day(o["valid_from"]) if o.get("valid_from") else None,
                                 _day(o["valid_to"]) if o.get("valid_to") else None, dict(o.get("refs") or {})))
    return out


def facts_at(did: str, day: date) -> dict:
    d = dossier(did)
    facts = {k: Fact(v, None, "user") for k, v in (d.get("user_facts") or {}).items()}
    for name, values in d["facts"].items():
        live = [v for v in values if _day(v["from"]) <= day]
        if live:
            v = max(live, key=lambda x: _day(x["from"]))
            facts[name] = Fact(v["value"], v.get("unit"), "contract", None, v.get("quote"))
    return facts


def key(r) -> str:
    return f"{r.concept_id}/{r.rule_id}" + (f"@{r.object}" if r.object else "")


def run(did: str, day: date, kind: str, *, facts=None, objects=None) -> dict:
    cat = catalog(tuple(dossier(did)["packs"]))
    s = evaluator_for(cat, kind).session(day=day, facts=facts if facts is not None else facts_at(did, day),
                                         present=set(), evidence={},
                                         objects=objects if objects is not None else objects_of(did))
    return {key(r): r for r in s.results()}


# ───────────────────────────── định dạng (C7) ─────────────────────────────

def test_every_dossier_of_the_plan_exists():
    assert {"a1", "b1", "b2", "b3", "b4", "b5", "r1"} <= set(DOSSIERS)


@pytest.mark.parametrize("did", DOSSIERS)
def test_dossier_format(did):
    d = dossier(did)
    assert d["dossier_id"] == did and isinstance(_day(d["review_date"]), date)
    cat = catalog(tuple(d["packs"]))
    parties = {p["id"]: p for p in d["parties"]}
    assert len(parties) == len(d["parties"])
    for p in d["parties"]:
        assert p["role"] in cat.roles, (did, p)
    docs = {x["doc_id"]: x for x in d["documents"]}
    assert len(docs) == len(d["documents"])
    for x in d["documents"]:
        assert (HERE / did / x["file"]).exists(), x
        if x["kind"] == "amendment":
            assert docs[x["refs"]["contract"]]["kind"] != "amendment", x
        else:
            assert set(packs_for_kind(x["kind"])) & set(d["packs"]), x
        for ref in x["refs"].values():
            assert ref in parties or ref in docs, (x["doc_id"], ref)
    for name in d.get("user_facts") or {}:
        assert name in cat.context.input_units, name                   # dữ kiện người dùng / hợp đồng của gói


@pytest.mark.parametrize("did", DOSSIERS)
def test_objects_match_pack_declaration_and_quotes(did):
    d = dossier(did)
    types = {name: t for p in d["packs"] for name, t in load_pack(p).object_types.items()}
    docs = {x["doc_id"] for x in d["documents"]}
    for o in d["objects"]:
        assert o["id"] in docs, o["id"]
        spec = types[o["type"]]
        assert set(o["attrs"]) <= set(spec.attrs), (o["id"], set(o["attrs"]) - set(spec.attrs))
        assert set(o.get("refs") or {}) <= set(spec.refs), o["id"]
        for name, a in o["attrs"].items():
            assert a.get("quote") or a.get("why"), (o["id"], name)
            if a.get("quote"):
                assert _norm(a["quote"]) in _norm(text(did, o["id"])), (o["id"], name, a["quote"])
    for name, values in d["facts"].items():
        for v in values:
            assert _norm(v["quote"]) in _norm(text(did, v["doc"])), (name, v["quote"])


# ───────────────────────────── parser (C6) ─────────────────────────────

@pytest.mark.parametrize("did", DOSSIERS)
def test_parser_reads_every_document_and_appendix_dates(did):
    d = dossier(did)
    valid = {o["id"]: _day(o["valid_from"]) for o in d["objects"] if o["type"] == "Amendment"}
    for main in (x for x in d["documents"] if x["kind"] != "amendment"):
        parts = [x for x in d["documents"] if x["kind"] == "amendment" and x["refs"]["contract"] == main["doc_id"]]
        pages = [PageText(i + 1, text(did, x["doc_id"])) for i, x in enumerate([main, *parts])]
        parsed = parse_contract(pages)
        assert parsed.report.counts["article"] >= 3, (main["doc_id"], parsed.report.counts)
        found = find_amendments(parsed)
        for i, x in enumerate(parts, start=1):
            mine = [a for a in found if a.src_uid.startswith(f"p{i}.")]
            assert mine and all(a.valid_from for a in mine), (x["doc_id"], found)
            assert all(a.dst_uid.startswith("p0.") for a in mine), mine
            if x["doc_id"] in valid:
                assert {a.valid_from for a in mine} == {valid[x["doc_id"]]}, x["doc_id"]


# ───────────────────────────── gold theo kỳ (C4) ─────────────────────────────

def _gold_days(label) -> list[tuple[date, str]]:
    ps = sorted(((_day(p["from"]), p["status"]) for p in label["periods"]), key=lambda x: x[0])
    out = list(ps)
    for (d0, s0), (d1, _) in zip(ps, ps[1:]):
        if d1 - d0 > timedelta(days=1):
            out.append((d1 - timedelta(days=1), s0))
    return out


@pytest.mark.parametrize("did", DOSSIERS)
def test_gold_labels_have_law_basis(did):
    gold = dossier(did)["gold"]
    assert gold["dossier_id"] == did and gold["expected"]
    for label in gold["expected"]:
        assert label["periods"] and {p["status"] for p in label["periods"]} <= STATUSES, label["rule"]
        b = label["basis"]
        if ROOTS:
            t = law_text(b["pid"])
            assert t is not None and _norm(b["quote"]) in _norm(t), (label["rule"], b["pid"])


@pytest.mark.parametrize("did", DOSSIERS)
def test_gold_on_both_evaluators(did):
    bad = []
    for label in dossier(did)["gold"]["expected"]:
        k = label["rule"] + (f"@{label['object']}" if label.get("object") else "")
        for day, want in _gold_days(label):
            got = {kind: run(did, day, kind).get(k) for kind in ("reference", "network")}
            assert got["reference"] is not None, (k, day, "không có kết quả")
            assert dataclasses.asdict(got["reference"]) == dataclasses.asdict(got["network"]), (k, day)
            if got["reference"].status != want:
                bad.append((k, day.isoformat(), want, got["reference"].status, got["reference"].reasons))
    assert bad == []


def _checked(did: str, r) -> bool:
    """Rule mà hồ sơ có dữ kiện để kết luận: rule xuyên đối tượng, hoặc rule đọc dữ kiện có trong facts.yaml."""
    cat = catalog(tuple(dossier(did)["packs"]))
    rule = next(x for x in cat.concepts[r.concept_id].rules if x.id == r.rule_id)
    return rule.over is not None or bool(set(fact_names(rule.check)) & set(dossier(did)["facts"]))


@pytest.mark.parametrize("did", DOSSIERS)
def test_no_fail_outside_gold(did):
    labelled = {label["rule"] + (f"@{label['object']}" if label.get("object") else "")
                for label in dossier(did)["gold"]["expected"]}
    days = {d for label in dossier(did)["gold"]["expected"] for d, _ in _gold_days(label)}
    extra = {(k, d.isoformat()) for d in days for k, r in run(did, d, "reference").items()
             if r.status == "FAIL" and k not in labelled and _checked(did, r)}
    assert extra == set()


# ───────────────────────────── kịch bản (C5) ─────────────────────────────

def _changes(before: list[WorkingObject], after: list[WorkingObject]) -> ObjectChanges:
    old, new = {o.id: o for o in before}, {o.id: o for o in after}
    return ObjectChanges(added=tuple(o for i, o in new.items() if i not in old),
                         removed=tuple(i for i in old if i not in new),
                         changed=tuple(o for i, o in new.items() if i in old and old[i] != o))


SCENARIOS = [d for d in DOSSIERS if dossier(d)["scenario"]]


def test_scenarios_of_the_plan_exist():
    assert {"a1", "b1", "b4", "r1"} <= set(SCENARIOS)


@pytest.mark.parametrize("did", SCENARIOS)
def test_scenario_steps(did):
    sc = dossier(did)["scenario"]
    assert sc["dossier_id"] == did and sc["steps"][0]["do"] == "load"
    session = state = day = None
    answered: dict = {}
    for i, step in enumerate(sc["steps"]):
        do = step["do"]
        assert step.get("say"), i
        if do in ("load", "set_review_date"):
            state = step.get("state", state)
            day = _day(step["review_date"] if do == "load" else step["value"])
            cat = catalog(tuple(dossier(state)["packs"]))
            session = evaluator_for(cat, "network").session(day=day, facts={**facts_at(state, day), **answered},
                                                            present=set(), evidence={}, objects=objects_of(state))
        elif do in ("add", "remove"):
            before, state = objects_of(state), step["state"]
            changes = _changes(before, objects_of(state))
            ids = {o.id for o in changes.added} if do == "add" else set(changes.removed)
            assert ids == set(step["docs"]), (i, ids)
            session.update({}, objects=changes)
        elif do == "answer":
            facts = {k: Fact(v, None, "user") for k, v in step["facts"].items()}
            answered.update(facts)
            session.update(facts)
        else:
            raise AssertionError(f"bước {i}: thao tác lạ {do!r}")
        got = {key(r): r for r in session.results()}
        fresh = run(state, day, "reference", facts={**facts_at(state, day), **answered})
        assert {k: dataclasses.asdict(v) for k, v in got.items()} == \
            {k: dataclasses.asdict(v) for k, v in fresh.items()}, f"bước {i}: phiên tăng dần khác tính lại"
        for k, want in (step.get("expect") or {}).items():
            assert k in got and got[k].status == want, (i, k, want, got.get(k) and got[k].status)
