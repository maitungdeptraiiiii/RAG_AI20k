"""Chấm kết quả soát theo khái niệm với nhãn tay.

Chạy từ app/team-4.2:  uv run python scripts/score_concept_check.py <thư mục ra của check_contract_concepts> <gold.yaml>
In: precision / recall gán khái niệm, độ đúng slot, số báo nhầm "không được nhắc tới", số lời gọi, thời gian.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

_ACTIVE = ("auto_accepted", "approved")


def _same(got: dict | None, want) -> bool:
    if got is None:
        return False
    if isinstance(want, list):
        return got.get("value") == want[0] and got.get("unit") == want[1]
    return got.get("value") == want


def score(out_dir: Path, gold_path: Path) -> dict:
    ops = json.loads((out_dir / "oplog.json").read_text(encoding="utf-8"))
    report = json.loads((out_dir / "report.json").read_text(encoding="utf-8"))
    gold = yaml.safe_load(gold_path.read_text(encoding="utf-8"))
    want, ambiguous = gold["present"], set(gold.get("ambiguous") or [])
    tagged = [o for o in ops if o["op_type"] == "ASSERT" and o["status"] in _ACTIVE
              and o["content"].get("kind") == "concept"]
    pred = {o["content"]["concept_id"] for o in tagged}
    scored = pred - ambiguous
    tp = scored & set(want)
    slots_total = slots_ok = 0
    slot_misses = []
    for cid, entries in want.items():
        for e in entries:
            for name, value in (e.get("slots") or {}).items():
                slots_total += 1
                got = next((o["content"]["slots"].get(name) for o in tagged
                            if o["content"]["concept_id"] == cid and name in o["content"]["slots"]), None)
                if _same(got, value):
                    slots_ok += 1
                else:
                    slot_misses.append(f"{cid}.{name}: muốn {value}, được {got}")
    false_silent = sorted({r["concept_id"] for r in report["results"]
                           if r["finding"] in ("hidden_right", "missing_content") and r["concept_id"] in want})
    return {"precision": round(len(tp) / len(scored), 3) if scored else None,
            "recall": round(len(tp) / len(want), 3),
            "false_positive": sorted(scored - set(want)), "missed": sorted(set(want) - pred),
            "slot_accuracy": f"{slots_ok}/{slots_total}", "slot_misses": slot_misses,
            "false_not_mentioned": false_silent, "llm_calls": report["stats"]["llm_calls"],
            "seconds": report["stats"]["seconds"]}


if __name__ == "__main__":
    print(json.dumps(score(Path(sys.argv[1]), Path(sys.argv[2])), ensure_ascii=False, indent=2))
