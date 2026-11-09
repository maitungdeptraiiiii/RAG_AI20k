"""Đo bộ lọc header/footer (app/team-4.2/src/rag/ingest/headers.py) trên output OCR ĐÃ CACHE.

Không gọi API. Với mỗi engine/suite, chấm cùng trang hai lần — output gốc và output sau
``strip_page_furniture`` — bằng ``score_struct.score_page``:

- ``hf_leak``   % header/footer/page_number GT còn lọt vào output (thấp = tốt) -> bộ lọc có tác dụng không
- ``block_ned`` sai lệch text các block nội dung GT (thấp = tốt; chỉ suite cross) -> bộ lọc có XOÁ NHẦM không
- số dòng bị bỏ, và các dòng bị bỏ để đọc tay

Ảnh benchmark là trang rời nên chỉ đo tầng 1 (mẫu theo trang); tầng 2 (lặp qua nhiều trang) cần PDF nhiều trang.

    .venv/Scripts/python -I evals/team-4.2/runners/ocr_bench/eval_hf_filter.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "app/team-4.2/src"))

import score_struct as ss  # noqa: E402
from rag.ingest.headers import strip_page_furniture  # noqa: E402

RESULTS = ROOT / "evals/team-4.2/results/w02-ocr-hf-filter"


def gt_for(suite: str) -> dict[str, dict]:
    if suite == "struct":
        gt = json.loads((ss.BENCH / "omnidocbench" / "OmniDocBench_subset30.json").read_text(encoding="utf-8"))
    else:
        gt = [x for x in json.loads((ss.BENCH / "mdpbench" / "MDPBench_public.json").read_text(encoding="utf-8"))
              if x["page_info"]["image_path"].startswith("vi_")]
    return {Path(x["page_info"]["image_path"]).stem: x for x in gt}


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    RESULTS.mkdir(parents=True, exist_ok=True)
    summary: dict = {}
    removed_log: list[dict] = []
    for suite in ("cross", "struct"):
        gt_by = gt_for(suite)
        with_text = suite == "cross"
        for eng in ss.ENGINES:
            d = ss.OUT / eng / suite
            if not d.exists():
                continue
            before, after, n_removed = [], [], 0
            for f in sorted(d.glob("*.md")):
                if f.stem not in gt_by:
                    continue
                md = f.read_text(encoding="utf-8")
                cleaned, removed = strip_page_furniture(md)
                n_removed += len(removed)
                removed_log += [{"suite": suite, "engine": eng, "page": f.stem, "line": line} for line in removed]
                struct = eng not in ss.NO_STRUCT
                before.append(ss.score_page(gt_by[f.stem], md, struct, with_text))
                after.append(ss.score_page(gt_by[f.stem], cleaned, struct, with_text))
            if not before:
                continue
            b = ss.aggregate(before, eng not in ss.NO_STRUCT, with_text)
            a = ss.aggregate(after, eng not in ss.NO_STRUCT, with_text)
            summary[f"{suite}/{eng}"] = {
                "pages": len(before), "lines_removed": n_removed,
                "hf_leak_before": b["hf_leak"], "hf_leak_after": a["hf_leak"],
                **({"block_ned_before": b["block_ned"], "block_ned_after": a["block_ned"]} if with_text else {}),
            }
    (RESULTS / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    (RESULTS / "removed_lines.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in removed_log), encoding="utf-8")
    lines = ["# W02-02c — Bộ lọc header/footer trên output OCR đã cache", "",
             "Không gọi API. `hf_leak` = % header/footer/số trang GT còn lọt (thấp = tốt). "
             "`block_ned` = sai lệch text nội dung (thấp = tốt; tăng = bộ lọc xoá nhầm nội dung). "
             "Chỉ tầng 1 (mẫu theo trang) vì ảnh benchmark là trang rời.", "",
             "| Suite / engine | Trang | Dòng bị bỏ | hf_leak trước → sau | block_ned trước → sau |",
             "|---|---:|---:|---|---|"]
    for key, r in summary.items():
        ned = f"{r['block_ned_before']} → {r['block_ned_after']}" if "block_ned_before" in r else "—"
        lines.append(f"| {key} | {r['pages']} | {r['lines_removed']} | {r['hf_leak_before']} → {r['hf_leak_after']} | {ned} |")
    lines += ["", "Các dòng bị bỏ: `removed_lines.jsonl` (đọc tay để kiểm tra xoá nhầm).", "",
              "Chạy lại: `.venv/Scripts/python -I evals/team-4.2/runners/ocr_bench/eval_hf_filter.py`", ""]
    (RESULTS / "summary.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
