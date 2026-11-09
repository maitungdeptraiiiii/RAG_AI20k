"""Chấm Bộ 2 (OmniDocBench) và kiểm tra chéo (MDPBench-VI) bằng SCRIPT CHÍNH THỨC, rồi đối chiếu leaderboard.

    .venv/Scripts/python -I evals/team-4.2/runners/ocr_bench/official_eval.py            # chạy cả hai
    .venv/Scripts/python -I evals/team-4.2/runners/ocr_bench/official_eval.py --only mdp
    .venv/Scripts/python -I evals/team-4.2/runners/ocr_bench/official_eval.py --collect  # chỉ gom kết quả đã chấm

Yêu cầu (đã có trong data/team-4.2/ocr_bench/, gitignore):
  _tools/OmniDocBench       git clone opendatalab/OmniDocBench          (đo ở commit 0604d98, v1.6.0)
  _tools/MultimodalOCR      git clone Yuliang-Liu/MultimodalOCR         (đo ở commit 6ddb0a5, thư mục MDPBench/)
  _envs/officialeval        uv venv --python 3.11 + MDPBench/requirements.txt (bỏ notebook) + beautifulsoup4 nltk "pyarrow<20"

Khác biệt so với cách chấm leaderboard (ghi trong summary.md):
  - TẮT CDM (cần LaTeX/ImageMagick/Ghostscript trên Linux). Công thức chỉ chấm Edit_dist.
    MDPBench: điểm trang = trung bình các phần CÓ MẶT (text, table; formula bị bỏ vì không có CDM).
    OmniDocBench: không tính được Overall chính thức → báo từng thành phần + (text + TEDS)/2.
  - Không chạy đủ tập: MDPBench-VI public có 40 trang gốc + 120 ảnh chụp; local chạy 40 + 40, Gemini 10 + 10.
    MDPBench bỏ qua trang không có dự đoán; OmniDocBench chấm trang thiếu là trang rỗng → Gemini/common dùng GT 20 trang.
  - Tesseract chỉ ra plain text → bảng bị chấm như leaderboard (TEDS ≈ 0), không phải N/A.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
BENCH = ROOT / "data" / "team-4.2" / "ocr_bench"
OUT = BENCH / "_out"
TOOLS = BENCH / "_tools"
PY = BENCH / "_envs" / "officialeval" / "Scripts" / "python.exe"
WORK = BENCH / "_work" / "official"
RESULTS = HERE.parents[1] / "results" / "w02-ocr-official"
MDP = TOOLS / "MultimodalOCR" / "MDPBench"
ODB = TOOLS / "OmniDocBench"
ENGINES = ["tesseract", "gemini", "gemini35lite", "mineru"]

# Leaderboard công khai, chép từ README của repo đã clone (cùng commit ở trên).
MDP_LEADERBOARD_VI = {  # cột Latin/VI, bảng "Main Results"
    "Gemini-3-pro-preview": 85.9, "MinerU-2.5-Pro-1.2B": 74.2, "PaddleOCR-VL-1.6": 80.9,
    "PP-StructureV3": 52.7, "MinerU-2.5-VLM": 46.0, "MinerU-2.5-pipeline": 27.6,
}
ODB_LEADERBOARD = {  # Overall, TextEdit, TableTEDS, TableTEDS-S, ReadOrderEdit (end-to-end, bảng chính)
    "MinerU2.5-Pro": (95.75, 0.036, 93.42, 95.92, 0.120),
    "MinerU-2.5": (93.04, 0.045, 87.88, 91.47, 0.130),
    "Gemini 3 Flash": (92.62, 0.066, 89.29, 93.51, 0.172),
    "Gemini 3 Pro": (92.91, 0.064, 89.15, 92.96, 0.165),
    "MinerU-Pipeline": (86.47, 0.055, 81.88, 88.68, 0.153),
}

METRICS = {
    "text_block": {"metric": ["Edit_dist"]},
    "display_formula": {"metric": ["Edit_dist"]},  # CDM tắt
    "table": {"metric": ["TEDS", "Edit_dist"], "teds_workers": 6},
    "reading_order": {"metric": ["Edit_dist"]},
}


def posix(p: Path) -> str:
    return p.resolve().as_posix()


def write_yaml(path: Path, cfg: dict) -> None:
    # JSON là YAML hợp lệ → khỏi phụ thuộc PyYAML trong .venv chính
    path.write_text(json.dumps(cfg, ensure_ascii=False, indent=1), encoding="utf-8")


def stage_preds(suite_dir: str, prefix: str) -> dict[str, Path]:
    """Chép .md của từng engine vào thư mục tên riêng (script đặt tên kết quả theo basename thư mục)."""
    base = WORK / prefix / "pred"
    dirs = {}
    gem_ids = sorted(p.name for p in (OUT / "gemini" / suite_dir).glob("*.md"))
    for e in ENGINES:
        d = base / f"{prefix}_{e}"
        shutil.rmtree(d, ignore_errors=True)
        d.mkdir(parents=True)
        for f in (OUT / e / suite_dir).glob("*.md"):
            shutil.copy2(f, d / f.name)
        dirs[e] = d
    for e in ["tesseract", "mineru"]:  # cùng đúng các trang Gemini đã chạy
        d = base / f"{prefix}_{e}_common"
        shutil.rmtree(d, ignore_errors=True)
        d.mkdir(parents=True)
        for name in gem_ids:
            shutil.copy2(dirs[e] / name, d / name)
        dirs[f"{e}_common"] = d
    return dirs


def run(cmd: list[str], cwd: Path, log: Path) -> None:
    env = dict(os.environ, PYTHONUTF8="1")
    with log.open("w", encoding="utf-8") as f:
        r = subprocess.run(cmd, cwd=cwd, env=env, stdout=f, stderr=subprocess.STDOUT)
    if r.returncode:
        sys.exit(f"Lỗi khi chạy {' '.join(cmd)} — xem {log}")


# ---------------------------------------------------------------- MDPBench


def eval_mdp() -> None:
    work = WORK / "mdp"
    dirs = stage_preds("cross", "mdp")
    for name, d in dirs.items():
        cfg = {"end2end_eval": {"metrics": METRICS, "dataset": {
            "dataset_name": "end2end_dataset",
            "ground_truth": {"data_path": posix(BENCH / "mdpbench" / "MDPBench_public.json")},
            "prediction": {"data_path": posix(d)},
            "match_method": "quick_match",
            "filter": {"language": "Vietnamese"},
        }}}
        y = work / f"mdp_{name}.yaml"
        write_yaml(y, cfg)
        print(f"[mdp] {name} ({len(list(d.glob('*.md')))} trang)", flush=True)
        run([str(PY), str(MDP / "pdf_validation.py"), "-c", str(y)], work, work / f"mdp_{name}.log")
        run([str(PY), str(MDP / "tools" / "calculate_scores.py"), "--result_folder", f"result/mdp_{name}_result"],
            work, work / f"mdp_{name}_scores.log")


def collect_mdp() -> dict:
    work = WORK / "mdp"
    out = {}
    for log in sorted(work.glob("mdp_*_scores.log")):
        name = log.stem[len("mdp_"):-len("_scores")]
        txt = log.read_text(encoding="utf-8")
        g = lambda k: float(re.search(rf"^\s*{k}\s*:\s*([\d.]+)", txt, re.M).group(1))  # noqa: E731
        m = json.loads((work / "result" / f"mdp_{name}_result" / f"mdp_{name}_result_metric_result.json")
                       .read_text(encoding="utf-8"))
        n_pred = len(list((work / "pred" / f"mdp_{name}").glob("*.md")))
        row = {"n_pages": n_pred, "VI_all": g("All"), "digital": g(r"Digit\."), "photo": g(r"Photo\.")}
        # trọng số như leaderboard: 40 gốc + 120 ảnh chụp
        row["VI_reweighted_1to3"] = round(0.25 * row["digital"] + 0.75 * row["photo"], 1)
        for split, key in [("all", "all"), ("digital", "all_digit"), ("photo", "all_photo")]:
            row[f"text_edit_{split}"] = round(m["text_block"][key]["Edit_dist"]["ALL_page_avg"] * 100, 1)
            row[f"table_TEDS_{split}"] = round(m["table"][key]["TEDS"]["all"] * 100, 1)
        row["order_edit_all"] = round(m["reading_order"]["all"]["Edit_dist"]["ALL_page_avg"] * 100, 1)
        out[name] = row
    return out


# ---------------------------------------------------------------- OmniDocBench


def eval_odb() -> None:
    work = WORK / "odb"
    dirs = stage_preds("struct", "odb")
    gt30 = BENCH / "omnidocbench" / "OmniDocBench_subset30.json"
    gem = {p.stem for p in dirs["gemini"].glob("*.md")}
    gt20 = work / "gt_subset20.json"
    rows = json.loads(gt30.read_text(encoding="utf-8"))
    sub = [r for r in rows if Path(r["page_info"]["image_path"]).stem in gem]
    gt20.write_text(json.dumps(sub, ensure_ascii=False), encoding="utf-8")
    for name, d in dirs.items():
        gt = gt30 if name in ("tesseract", "mineru") else gt20
        cfg = {"end2end_eval": {"metrics": METRICS, "dataset": {
            "dataset_name": "end2end_dataset",
            "ground_truth": {"data_path": posix(gt)},
            "prediction": {"data_path": posix(d)},
            "match_method": "quick_match", "match_workers": 6,
            "quick_match_truncated_timeout_sec": 300, "match_timeout_sec": 420,
            "timeout_fallback_max_chunk_span": 10, "timeout_fallback_order_penalty": 0.10,
        }}}
        y = work / f"odb_{name}.yaml"
        write_yaml(y, cfg)
        print(f"[odb] {name} ({len(list(d.glob('*.md')))} trang, GT {gt.name})", flush=True)
        run([str(PY), "pdf_validation.py", "-c", str(y)], ODB, work / f"odb_{name}.log")
        res = ODB / "result"
        dst = work / "result" / f"odb_{name}"
        shutil.rmtree(dst, ignore_errors=True)
        dst.mkdir(parents=True)
        for f in res.glob(f"odb_{name}_quick_match_*"):
            shutil.move(str(f), dst / f.name)


def collect_odb() -> dict:
    work = WORK / "odb"
    out = {}
    for d in sorted((work / "result").glob("odb_*")):
        name = d.name[len("odb_"):]
        m = json.loads((d / f"odb_{name}_quick_match_metric_result.json").read_text(encoding="utf-8"))
        te = m["text_block"]["all"]["Edit_dist"]["ALL_page_avg"]
        teds = m["table"]["all"]["TEDS"]["all"] * 100
        out[name] = {
            "n_pages": len(list((work / "pred" / f"odb_{name}").glob("*.md"))),
            "text_edit": round(te * 100, 1),
            "table_TEDS": round(teds, 1),
            "table_TEDS_S": round(m["table"]["all"]["TEDS_structure_only"]["all"] * 100, 1),
            "order_edit": round(m["reading_order"]["all"]["Edit_dist"]["ALL_page_avg"] * 100, 1),
            "formula_edit": round(m["display_formula"]["all"]["Edit_dist"]["ALL_page_avg"] * 100, 1),
            "text_TEDS_mean_noCDM": round(((1 - te) * 100 + teds) / 2, 1),
            "text_edit_by_page_attr": {k: round(v * 100, 1) for k, v in m["text_block"]["page"]["Edit_dist"].items()},
        }
    return out


# ---------------------------------------------------------------- báo cáo

LABEL = {"tesseract": "Tesseract", "gemini": "Gemini 2.5 Flash", "gemini35lite": "Gemini 3.5 Flash-Lite", "mineru": "MinerU 4.1.7",
         "tesseract_common": "Tesseract (20 trang chung)", "mineru_common": "MinerU 4.1.7 (20 trang chung)"}
ORDER = ["tesseract", "gemini", "gemini35lite", "mineru", "tesseract_common", "mineru_common"]


def write_report(mdp: dict, odb: dict) -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "summary.json").write_text(json.dumps({"mdpbench_vi": mdp, "omnidocbench": odb,
                                                       "leaderboard_mdp_vi": MDP_LEADERBOARD_VI,
                                                       "leaderboard_omnidocbench": ODB_LEADERBOARD},
                                                      ensure_ascii=False, indent=1), encoding="utf-8")
    L = ["# W02 · Chấm bằng script chính thức — MDPBench-VI + OmniDocBench", "",
         "Tạo bởi `evals/team-4.2/runners/ocr_bench/official_eval.py`. Script chấm: "
         "`MultimodalOCR/MDPBench` @6ddb0a5 (`pdf_validation.py` + `tools/calculate_scores.py`), "
         "`OmniDocBench` @0604d98 v1.6.0 (`pdf_validation.py`). Đơn vị %.", "",
         "**Khác leaderboard (đọc trước khi so):** CDM công thức **tắt** (cần LaTeX trên Linux) · "
         "không chạy đủ tập (xem `n`) · output là của lần chạy engine ngày 2026-11-07 (Gemini 3.5 Flash-Lite: 2026-11-08), không chạy lại engine.", "",
         "## MDPBench — tiếng Việt", "",
         "Điểm trang = trung bình các phần có mặt: (1 − text edit) và TEDS bảng (công thức bị bỏ vì không có CDM). "
         "`VI` = trung bình theo trang trên các trang đã chạy. Leaderboard chấm 40 trang gốc + 120 ảnh chụp, "
         "nên có thêm cột `VI (trọng số 1:3)` = 0.25·digital + 0.75·photo cho gần với cách leaderboard cân trọng số.", "",
         "| engine | n | **VI** | VI (trọng số 1:3) | digital | photo | text edit ↓ (dig / photo) | TEDS bảng (dig / photo) | order edit ↓ |",
         "|---|---|---|---|---|---|---|---|---|"]
    for k in ORDER:
        if k in mdp:
            r = mdp[k]
            L.append(f"| {LABEL[k]} | {r['n_pages']} | **{r['VI_all']}** | {r['VI_reweighted_1to3']} | {r['digital']} | "
                     f"{r['photo']} | {r['text_edit_all']} ({r['text_edit_digital']} / {r['text_edit_photo']}) | "
                     f"{r['table_TEDS_all']} ({r['table_TEDS_digital']} / {r['table_TEDS_photo']}) | {r['order_edit_all']} |")
    L += ["", "Leaderboard công khai, cột VI (160 trang public, có CDM): " +
          " · ".join(f"{k} {v}" for k, v in MDP_LEADERBOARD_VI.items()) +
          ". Không có Gemini 2.5 Flash, Gemini 3.5 Flash-Lite, Tesseract hay MinerU 4.x trên leaderboard.", "",
          "## OmniDocBench — cấu trúc (EN/ZH)", "",
          "Không tính được Overall chính thức (= ((1 − text edit)·100 + TEDS + CDM) / 3) vì thiếu CDM. "
          "Cột cuối là (text + TEDS)/2, **không** so được với Overall leaderboard.", "",
          "| engine | n | text edit ↓ | TEDS | TEDS-S | order edit ↓ | formula edit ↓ | (text+TEDS)/2 |",
          "|---|---|---|---|---|---|---|---|"]
    for k in ORDER:
        if k in odb:
            r = odb[k]
            L.append(f"| {LABEL[k]} | {r['n_pages']} | {r['text_edit']} | {r['table_TEDS']} | {r['table_TEDS_S']} | "
                     f"{r['order_edit']} | {r['formula_edit']} | {r['text_TEDS_mean_noCDM']} |")
    L += ["", "Leaderboard end-to-end (toàn bộ 1.355 trang; text/order edit đổi sang %):", "",
          "| model | Overall | text edit ↓ | TEDS | TEDS-S | order edit ↓ |", "|---|---|---|---|---|---|"]
    for k, (ov, te, teds, tedss, ro) in ODB_LEADERBOARD.items():
        L.append(f"| {k} | {ov} | {te * 100:.1f} | {teds} | {tedss} | {ro * 100:.1f} |")
    (RESULTS / "summary.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"-> {RESULTS / 'summary.md'}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=["mdp", "odb"])
    ap.add_argument("--collect", action="store_true", help="không chấm lại, chỉ gom kết quả")
    a = ap.parse_args()
    if not PY.exists():
        sys.exit(f"Thiếu venv chấm chính thức: {PY} (xem docstring)")
    if not a.collect:
        if a.only in (None, "mdp"):
            eval_mdp()
        if a.only in (None, "odb"):
            eval_odb()
    write_report(collect_mdp(), collect_odb())


if __name__ == "__main__":
    main()
