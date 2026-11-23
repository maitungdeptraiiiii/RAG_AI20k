"""K3: chấm engine cũ (`rag.bridge.engine.evaluate`), `reference`, `network` theo gold của hồ sơ mẫu; bảng chọn gói.

Engine cũ không nhận đối tượng hồ sơ: rule xuyên đối tượng không có kết quả -> "MISSING" (không phải lỗi script).
Nhận diện loại hợp đồng: `classify_contract` (LLM thật) qua `cached_classifier`, đệm theo sha256(văn bản) + model."""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from rag.bridge import engine as legacy
from rag.rules.bench.cases import FIXTURES, Case, catalog_for, expect_key, result_key
from rag.rules.evaluator import evaluator_for
from rag.rules.explain import explain
from rag.rules.loader import packs_for_kind
from rag.rules.semantics import RuleResult

ENGINES = ("legacy", "reference", "network")
STATUSES = ("PASS", "FAIL", "UNKNOWN", "NOT_APPLICABLE", "MISSING")


def _session(case: Case, engine: str):
    return evaluator_for(catalog_for(case.packs), engine).session(
        day=case.day, facts=dict(case.facts), present=set(case.present), evidence={}, objects=case.objects)


def run_case(case: Case, engine: str) -> dict[str, RuleResult]:
    if engine == "legacy":
        res = legacy.evaluate(catalog_for(case.packs), dict(case.facts), set(case.present), {}, case.day)
    elif engine in ("reference", "network"):
        res = _session(case, engine).results()
    else:
        raise ValueError(f"engine lạ {engine!r}")
    return {result_key(r): r for r in res}


@dataclass
class Miss:
    suite: str
    case_id: str
    path: str
    rule: str
    object: str | None
    day: str
    want: str
    got: str
    explain_md: str | None


@dataclass
class Score:
    engine: str
    by_pack: dict[str, Counter] = field(default_factory=dict)
    by_kind: dict[str, Counter] = field(default_factory=dict)
    confusion: Counter = field(default_factory=Counter)      # (gold, got) -> số nhãn
    misses: list[Miss] = field(default_factory=list)


def _outcome(want: str, got: str) -> str:
    if got == want:
        return "right"
    return {"MISSING": "missing", "UNKNOWN": "unknown"}.get(got, "wrong")


def _explain(case: Case, engine: str, rule: str, obj: str | None) -> str | None:
    if engine == "legacy":
        return None
    cid, rid = rule.split("/")
    try:
        return explain(catalog_for(case.packs), _session(case, engine), cid, rid, obj).to_markdown()
    except Exception as e:  # noqa: BLE001 — giải thích hỏng không được làm mất ca sai
        return f"(không dựng được giải thích: {type(e).__name__}: {e})"


def _rel(path: Path) -> str:
    """Đường dẫn tính từ app/team-4.2 (vd. tests/fixtures/rete/b1) để báo cáo không chứa đường dẫn máy."""
    try:
        return Path(path).resolve().relative_to(FIXTURES.parents[2]).as_posix()
    except ValueError:
        return Path(path).as_posix()


def score(cases: list[Case], engine: str) -> Score:
    s = Score(engine)
    for case in cases:
        got_all = run_case(case, engine)
        cat = catalog_for(case.packs)
        for e in case.expected:
            r = got_all.get(expect_key(e))
            got = r.status if r is not None else "MISSING"
            kind = cat.concepts[e.rule.split("/")[0]].kind or "(không kind)"
            o = _outcome(e.status, got)
            s.by_pack.setdefault("+".join(case.packs), Counter())[o] += 1
            s.by_kind.setdefault(kind, Counter())[o] += 1
            s.confusion[(e.status, got)] += 1
            if o != "right":
                s.misses.append(Miss(case.suite, case.case_id, _rel(case.path), e.rule, e.object,
                                     case.day.isoformat(), e.status, got, _explain(case, engine, e.rule, e.object)))
    return s


@dataclass(frozen=True)
class PackRow:
    suite: str
    case_id: str
    fixture_kind: str
    classified_kind: str | None
    packs_run: tuple[str, ...]
    wrong_domain: bool | None


def pack_choice(cases: list[Case], classify: Callable[[Case], str] | None = None) -> list[PackRow]:
    """Một dòng mỗi văn bản chính (hồ sơ soát nhiều ngày vẫn một dòng). Sai miền = gói của loại nhận diện khác gói của hồ sơ."""
    rows, seen = [], set()
    for c in cases:
        doc = (c.suite, c.doc_files)
        if doc in seen:
            continue
        seen.add(doc)
        if classify is None:
            rows.append(PackRow(c.suite, c.case_id, c.document_kind, None, c.packs, None))
            continue
        kind = classify(c)
        packs = tuple(packs_for_kind(kind))
        rows.append(PackRow(c.suite, c.case_id, c.document_kind, kind, packs, set(packs) != set(c.packs)))
    return rows


def cached_classifier(llm, cache_path: Path, model: str) -> Callable[[Case], str]:
    """Nhận diện loại văn bản chính của ca bằng `classify_contract`; mỗi văn bản (theo nội dung) gọi LLM một lần, lưu đệm."""
    from rag.contracts.classify import classify_contract
    from rag.contracts.models import Contract
    from rag.contracts.parse import split_units

    cache_path = Path(cache_path)
    cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}

    def classify(case: Case) -> str:
        text = "\n".join((case.path / f).read_text(encoding="utf-8") for f in case.doc_files[:1])
        key = hashlib.sha256(text.encode("utf-8")).hexdigest() + ":" + model
        if key not in cache:
            units = split_units(text)
            c = Contract(case.case_id, case.doc_files[0], False, datetime.now(timezone.utc), text, units, len(units))
            r = classify_contract(llm, c)
            cache[key] = {"kind": r["kind"], "confidence": r.get("confidence"), "reason": r.get("reason"),
                          "file": f"{case.suite}/{case.doc_files[0]}"}
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
        return cache[key]["kind"]

    return classify


def _table(head: list[str], rows: list[list]) -> list[str]:
    return ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)] + ["| " + " | ".join(map(str, r)) + " |" for r in rows]


def _counts(c: Counter) -> list:
    n = sum(c.values())
    return [c["right"], c["wrong"], c["unknown"], c["missing"], n, f"{c['right'] / n:.0%}" if n else "—"]


def render_summary(scores: list[Score], packs: list[PackRow], no_gold: list[str], *, classified: bool,
                   pending: list[str] = ()) -> str:
    out = ["# Eval rule engine theo gói (K3)", "",
           "Sinh bằng `app/team-4.2/scripts/eval_rule_engine.py` từ `tests/fixtures/rete/*/gold.yaml`. "
           "Engine: " + ", ".join(f"`{s.engine}`" for s in scores) + ". `legacy` = `rag.bridge.engine.evaluate` "
           "(không nhận đối tượng hồ sơ: rule xuyên đối tượng ra MISSING).", ""]
    head = ["đúng", "sai", "UNKNOWN", "thiếu kết quả", "tổng nhãn", "tỉ lệ đúng"]
    out += ["## Theo gói", ""]
    out += _table(["engine", "gói"] + head, [[s.engine, p] + _counts(c) for s in scores for p, c in sorted(s.by_pack.items())])
    out += ["", "## Theo loại rule (kind)", ""]
    out += _table(["engine", "kind"] + head, [[s.engine, k] + _counts(c) for s in scores for k, c in sorted(s.by_kind.items())])
    for s in scores:
        out += ["", f"## Ma trận nhầm — `{s.engine}` (hàng: gold, cột: engine)", ""]
        out += _table(["gold \\ engine"] + list(STATUSES),
                      [[g] + [s.confusion.get((g, x), 0) for x in STATUSES] for g in STATUSES[:4]])
    out += ["", "## Chọn gói theo loại hợp đồng", ""]
    if not classified:
        out += ["classify: chưa chạy (`--no-classify`); cột loại nhận diện để trống.", ""]
    out += _table(["hồ sơ", "ca", "loại theo hồ sơ", "loại nhận diện (classify_contract)", "gói được chạy", "sai miền"],
                  [[r.suite, r.case_id, r.fixture_kind, r.classified_kind or "—", ", ".join(r.packs_run) or "(không gói)",
                    {True: "**CÓ**", False: "không", None: "—"}[r.wrong_domain]] for r in packs])
    out += ["", "## Hồ sơ chưa có gold", ""] + ([f"- `{d}`" for d in no_gold] or ["- Không có."])
    if pending:
        out += ["", "## Gold chờ Tùng duyệt", ""] + [f"- `{d}`" for d in pending]
    for s in scores:
        out += ["", f"## Ca sai — `{s.engine}` ({len(s.misses)})", ""]
        if not s.misses:
            out.append("- Không có.")
        for m in s.misses:
            out.append(f"- `{m.path}` · ca `{m.case_id}` · rule `{m.rule}`{f' @{m.object}' if m.object else ''} · "
                       f"ngày {m.day}: gold {m.want}, engine {m.got}")
            if m.explain_md:
                out += ["", "  <details><summary>explain</summary>", "", "```", m.explain_md.rstrip(), "```", "", "  </details>"]
    return "\n".join(out) + "\n"


__all__ = ["ENGINES", "Miss", "PackRow", "Score", "cached_classifier", "pack_choice", "render_summary", "run_case", "score"]
