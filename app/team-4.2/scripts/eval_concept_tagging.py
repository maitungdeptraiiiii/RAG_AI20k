"""Đo gán khái niệm + trích dữ kiện bằng LLM thật trên hợp đồng mẫu của gói (hạn chế P / V.6: consumer, commercial).

Chạy luồng thật `check_contract(packs=[gói])`: LLM của app trích dữ kiện, CONCEPT_TAG_MODEL gán khái niệm. So với đáp án
viết tay trong `tests/fixtures/rete/<bộ>/facts.yaml` (khái niệm có mặt, giá trị slot) và `gold.yaml` (trạng thái rule).
Hai LLM đều có đệm sqlite trong <out>: chạy lại không gọi model (đổi prompt / model thì xóa đệm).

    uv run python scripts/eval_concept_tagging.py [--suite consumer --suite commercial] [--out DIR]
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import yaml

APP = Path(__file__).resolve().parents[1]
REPO = APP.parents[1]
FIXTURES = APP / "tests" / "fixtures" / "rete"
SUITES = {"consumer": "consumer", "commercial": "commercial"}       # thư mục mẫu -> gói
AT = datetime(2026, 11, 24, 9, 0)


@dataclass
class DocScore:
    doc: str
    gold_concepts: set[str]
    found: set[str]
    pending: set[str]
    slots_ok: int = 0
    slots_total: int = 0
    slot_errors: list[str] = field(default_factory=list)
    rules_ok: int = 0
    rules_total: int = 0
    rule_errors: list[str] = field(default_factory=list)
    false_fail: list[str] = field(default_factory=list)       # FAIL mà gold không ghi FAIL
    missed_fail: list[str] = field(default_factory=list)      # gold FAIL mà không ra FAIL
    quotes: dict[str, list[str]] = field(default_factory=dict)   # khái niệm -> câu trích LLM gán (để người xem phân xử)

    @property
    def tp(self) -> int:
        return len(self.found & self.gold_concepts)


def _same(pred, gold) -> bool:
    if isinstance(gold, bool) or isinstance(pred, bool):
        return pred is gold
    try:
        return abs(float(pred) - float(gold)) < 1e-9
    except (TypeError, ValueError):
        return str(pred).strip().casefold() == str(gold).strip().casefold()


def score(doc: str, gold_doc: dict, gold_status: dict[str, str], found: dict[str, dict], pending: set[str],
          statuses: dict[str, str], normalize=None) -> DocScore:
    """found: khái niệm -> slot đã chuẩn hóa {tên: {value, unit}} (ASSERT đang hiệu lực); statuses: rule -> trạng thái.
    normalize(cid, slot, chữ gốc, câu trích) -> giá trị gold đã chuẩn hóa bằng bộ đọc của luồng thật (None: giữ nguyên)."""
    gold_concepts = set(gold_doc.get("slots") or {}) | set(gold_doc.get("present_quotes") or {})
    s = DocScore(doc, gold_concepts, set(found), set(pending))
    for cid, slots in (gold_doc.get("slots") or {}).items():
        for name, pair in (slots or {}).items():
            gold_value = pair[0] if isinstance(pair, list) else pair
            if normalize is not None:
                gold_value = normalize(cid, name, gold_value, pair[1] if isinstance(pair, list) and len(pair) > 1 else "")
            s.slots_total += 1
            got = (found.get(cid) or {}).get(name)
            if got is not None and _same(got.get("value"), gold_value):
                s.slots_ok += 1
            else:
                s.slot_errors.append(f"{cid}.{name}: gold={gold_value!r} got={None if got is None else got.get('value')!r}")
    for rule, want in gold_status.items():
        s.rules_total += 1
        got = statuses.get(rule)
        if got == want:
            s.rules_ok += 1
        else:
            s.rule_errors.append(f"{rule}: gold={want} got={got}")
        if want == "FAIL" and got != "FAIL":
            s.missed_fail.append(rule)
    s.false_fail = sorted(r for r, st in statuses.items() if st == "FAIL" and gold_status.get(r) != "FAIL")
    return s


def summarize(scores: list[DocScore]) -> dict:
    tp = sum(s.tp for s in scores)
    found = sum(len(s.found) for s in scores)
    gold = sum(len(s.gold_concepts) for s in scores)
    return {"docs": len(scores), "concept_precision": round(tp / found, 3) if found else None,
            "concept_recall": round(tp / gold, 3) if gold else None,
            "slots": f"{sum(s.slots_ok for s in scores)}/{sum(s.slots_total for s in scores)}",
            "rules": f"{sum(s.rules_ok for s in scores)}/{sum(s.rules_total for s in scores)}",
            "false_fail": sum(len(s.false_fail) for s in scores), "missed_fail": sum(len(s.missed_fail) for s in scores)}


def _contract(doc: str, text: str):
    from rag.contracts.doc import PageText
    from rag.contracts.models import Contract
    from rag.contracts.structure import parse_contract, to_contract_units
    pages = [PageText(1, text)]
    parsed = parse_contract(pages)
    units = to_contract_units(parsed)
    return Contract(doc, f"{doc}.txt", False, datetime(2026, 11, 24, tzinfo=timezone.utc),
                    "\n".join(u.text for u in units), list(units), len(units), doc=parsed, page_texts=list(pages),
                    file_checksum=doc)


def _llms(out: Path):
    from rag.bridge.llm import concept_tag_llm
    from rag.config import Settings
    from rag.generate.llm import LLMCache, OpenAIChatLLM
    s = Settings.load()
    app = OpenAIChatLLM(s.llm_model, temperature=s.llm_temperature, base_url=s.llm_base_url, api_key=s.llm_api_key,
                        cache=LLMCache(out / "app_llm.sqlite"))
    tag = concept_tag_llm(s, cache=LLMCache(out / "tag_llm.sqlite"))
    return app, tag, s.llm_model, s.concept_tag_model


def run_doc(suite: str, doc: str, gold_doc: dict, gold_status: dict[str, str], app, tag, tag_model) -> DocScore:
    from rag.bridge.check import check_contract
    contract = _contract(doc, (FIXTURES / suite / f"{doc}.txt").read_text(encoding="utf-8"))
    report = check_contract(app, contract, at=AT, packs=[SUITES[suite]], tag_llm=tag, tag_model=tag_model,
                            user_facts=gold_doc.get("user_facts") or {})
    found, pending, quotes = {}, set(), {}
    for op in contract.oplog.all():
        if op.op_type == "ASSERT" and op.content.get("kind") == "concept":
            cid = op.content["concept_id"]
            quotes.setdefault(cid, []).extend(op.quote or ())
            if op.status in ("auto_accepted", "approved"):
                found.setdefault(cid, {}).update(op.content.get("slots") or {})
            elif op.status == "pending":
                pending.add(cid)
    statuses = {f"{r.concept_id}/{r.rule_id}": r.status for r in report.results}
    s = score(doc, gold_doc, gold_status, found, pending, statuses, normalize=_gold_normalizer(SUITES[suite]))
    s.quotes = quotes
    return s


def _gold_normalizer(pack: str):
    """Giá trị gold (chữ gốc) qua cùng bộ đọc slot của luồng thật, như tests/test_rete_pack_fixtures.py."""
    from rag.bridge.facts_map import normalize_slot
    from rag.rules.loader import load_packs
    cat = load_packs([pack])

    def norm(cid: str, name: str, raw, quote: str):
        slot = cat.concepts[cid].slots.get(name) if cid in cat.concepts else None
        if slot is None or isinstance(raw, bool):
            return raw
        f = normalize_slot(slot, raw, cat.context, quote=quote)
        return raw if f is None else f.value
    return norm


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--suite", action="append", choices=sorted(SUITES))
    ap.add_argument("--out", type=Path, default=REPO / "evals" / "team-4.2" / "results" / "w04-rule-engine" / "tagging")
    args = ap.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    app, tag, app_model, tag_model = _llms(args.out)
    report: dict = {"app_model": app_model, "tag_model": tag_model, "suites": {}}
    lines = [f"# Đo gán khái niệm bằng LLM thật ({datetime.now().date().isoformat()})", "",
             f"Trích dữ kiện: `{app_model}` · gán khái niệm: `{tag_model}` · luồng `check_contract(packs=[gói])`.", ""]
    for suite in args.suite or sorted(SUITES):
        facts = yaml.safe_load((FIXTURES / suite / "facts.yaml").read_text(encoding="utf-8"))
        gold = yaml.safe_load((FIXTURES / suite / "gold.yaml").read_text(encoding="utf-8"))
        scores = []
        for doc in sorted(facts):
            want = {e["rule"]: e["periods"][-1]["status"] for e in gold["expected"] if e.get("object") == doc}
            s = run_doc(suite, doc, facts[doc], want, app, tag, tag_model)
            scores.append(s)
            print(f"{suite}/{doc}: khái niệm {s.tp}/{len(s.gold_concepts)} (gán {len(s.found)}), slot {s.slots_ok}/"
                  f"{s.slots_total}, rule {s.rules_ok}/{s.rules_total}, FAIL thừa {len(s.false_fail)}", flush=True)
        summ = summarize(scores)
        report["suites"][suite] = {"summary": summ, "docs": [
            {"doc": s.doc, "missing": sorted(s.gold_concepts - s.found), "extra": sorted(s.found - s.gold_concepts),
             "pending": sorted(s.pending), "slot_errors": s.slot_errors, "rule_errors": s.rule_errors,
             "false_fail": s.false_fail, "missed_fail": s.missed_fail,
             "quotes_to_review": {c: s.quotes.get(c, []) for c in sorted((s.found - s.gold_concepts)
                                  | {r.split("/")[0] for r in s.false_fail + s.missed_fail})}} for s in scores]}
        lines += [f"## {suite}", "", "| Chỉ số | Giá trị |", "|---|---|", *[f"| {k} | {v} |" for k, v in summ.items()], "",
                  "| Hợp đồng | Thiếu khái niệm | Gán thừa | Chờ duyệt | Slot sai | Rule sai | FAIL thừa | FAIL bỏ sót |",
                  "|---|---|---|---|---|---|---|---|"]
        for s in scores:
            lines.append(f"| {s.doc} | {', '.join(sorted(s.gold_concepts - s.found)) or '—'} | "
                         f"{', '.join(sorted(s.found - s.gold_concepts)) or '—'} | {', '.join(sorted(s.pending)) or '—'} | "
                         f"{'; '.join(s.slot_errors) or '—'} | {'; '.join(s.rule_errors) or '—'} | "
                         f"{', '.join(s.false_fail) or '—'} | {', '.join(s.missed_fail) or '—'} |")
        lines.append("")
    (args.out / "tagging.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    (args.out / "summary.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({k: v["summary"] for k, v in report["suites"].items()}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
