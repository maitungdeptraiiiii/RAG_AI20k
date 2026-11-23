"""K3: eval rule engine theo gói trên hồ sơ mẫu tests/fixtures/rete/* -> evals/team-4.2/results/w04-rule-engine/eval/summary.md.

Chạy từ app/team-4.2: .venv/Scripts/python.exe scripts/eval_rule_engine.py [--out DIR] [--no-classify]
Nhận diện loại hợp đồng dùng LLM thật (classify_contract), có đệm ở <out>/classify_cache.json: chạy lại không gọi LLM."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
REPO = APP.parents[1]


def _llm():
    from rag.config import Settings
    from rag.generate.llm import OpenAIChatLLM
    s = Settings.load()
    return OpenAIChatLLM(s.llm_model, temperature=s.llm_temperature, base_url=s.llm_base_url, api_key=s.llm_api_key,
                         cache=None), s.llm_model


class _Counting:
    def __init__(self, llm):
        self.llm, self.calls = llm, 0

    def complete(self, system, user):
        self.calls += 1
        return self.llm.complete(system, user)


def main(argv: list[str] | None = None) -> int:
    from rag.rules.bench.cases import load_cases
    from rag.rules.bench.evalrun import ENGINES, cached_classifier, pack_choice, render_summary, score

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=REPO / "evals" / "team-4.2" / "results" / "w04-rule-engine" / "eval")
    ap.add_argument("--no-classify", action="store_true", help="không gọi LLM nhận diện loại")
    args = ap.parse_args(argv)
    cases, no_gold = load_cases()
    scores = [score(cases, e) for e in ENGINES]
    classify, counter = None, None
    if not args.no_classify:
        llm, model = _llm()
        counter = _Counting(llm)
        classify = cached_classifier(counter, args.out / "classify_cache.json", model)
    rows = pack_choice(cases, classify)
    pending = sorted({c.suite for c in cases if "CHỜ" in c.labeled_by.upper() or "CẦN TÙNG DUYỆT" in c.labeled_by.upper()})
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "summary.md").write_text(render_summary(scores, rows, no_gold, classified=classify is not None,
                                                        pending=pending), encoding="utf-8")
    for s in scores:
        print(f"{s.engine}: {sum(len(c.expected) for c in cases)} nhãn, {len(s.misses)} ca không đúng")
    if counter is not None:
        print(f"classify: {counter.calls} lần gọi LLM; sai miền: {sum(bool(r.wrong_domain) for r in rows)}/{len(rows)}")
    print(f"-> {args.out / 'summary.md'}")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.path.insert(0, str(APP / "src"))
    sys.exit(main())
