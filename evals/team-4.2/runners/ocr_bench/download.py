"""Tải các bộ benchmark OCR cho W02-02c vào data/team-4.2/ocr_bench/ (gitignore).

    python evals/team-4.2/runners/ocr_bench/download.py            # tải tất cả
    python evals/team-4.2/runners/ocr_bench/download.py --only omnidocbench mdpbench

Bộ:
  vi            nrl-ai/vn-ocr-documents-eval   tải hết (~0.31 GB)
  niits         niits/vietnamese-legal-ocr     tải hết (~1.3 MB, chỉ nhãn)
  omnidocbench  opendatalab/OmniDocBench       OmniDocBench.json + 30 trang chọn (xem omnidocbench_ids.json)
  mdpbench      Delores-Lin/MDPBench           MDPBench_public.json + toàn bộ ảnh vi_* (40 gốc + 120 ảnh chụp, ~0.79 GB)
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from huggingface_hub import HfApi, hf_hub_download, snapshot_download

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / "data" / "team-4.2" / "ocr_bench"
HERE = Path(__file__).resolve().parent
ODB_IDS = HERE / "omnidocbench_ids.json"

# Quota chọn trang OmniDocBench: loại gần tài liệu của mình, ưu tiên có bảng + nhiều cột.
ODB_QUOTA = {
    "research_report": 10,
    "book": 8,
    "academic_literature": 6,
    "exam_paper": 3,
    "magazine": 3,
}
ODB_GEMINI_N = 20
MULTI_COL = {"double_column", "three_column", "1andmore_column"}


def dl_vi() -> None:
    snapshot_download("nrl-ai/vn-ocr-documents-eval", repo_type="dataset", local_dir=OUT / "vi")


def dl_niits() -> None:
    snapshot_download("niits/vietnamese-legal-ocr", repo_type="dataset", local_dir=OUT / "niits")


def _select_odb(pages: list[dict]) -> list[dict]:
    def score(p: dict) -> tuple:
        cats = [e.get("category_type") for e in p["layout_dets"]]
        layout = p["page_info"]["page_attribute"].get("layout")
        img = p["page_info"]["image_path"]
        # có bảng > nhiều cột > số bảng; hash để thứ tự cố định, không phụ thuộc thứ tự json
        return (-("table" in cats), -(layout in MULTI_COL), -cats.count("table"),
                hashlib.sha1(img.encode()).hexdigest())

    picked: list[dict] = []
    for src, n in ODB_QUOTA.items():
        cand = sorted((p for p in pages if p["page_info"]["page_attribute"].get("data_source") == src), key=score)
        picked += cand[:n]
    # Xen kẽ theo loại để 20 trang đầu (Gemini) vẫn đủ loại
    by_src: dict[str, list[dict]] = {}
    for p in picked:
        by_src.setdefault(p["page_info"]["page_attribute"]["data_source"], []).append(p)
    order: list[dict] = []
    while any(by_src.values()):
        for src in ODB_QUOTA:
            if by_src.get(src):
                order.append(by_src[src].pop(0))
    rows = []
    for i, p in enumerate(order):
        a = p["page_info"]["page_attribute"]
        cats = [e.get("category_type") for e in p["layout_dets"]]
        rows.append({
            "image_path": p["page_info"]["image_path"],
            "data_source": a.get("data_source"),
            "language": a.get("language"),
            "layout": a.get("layout"),
            "n_tables": cats.count("table"),
            "gemini": i < ODB_GEMINI_N,
        })
    return rows


def dl_omnidocbench() -> None:
    dst = OUT / "omnidocbench"
    repo = "opendatalab/OmniDocBench"
    js = hf_hub_download(repo, "OmniDocBench.json", repo_type="dataset", local_dir=dst)
    if ODB_IDS.exists():
        rows = json.loads(ODB_IDS.read_text(encoding="utf-8"))
    else:
        rows = _select_odb(json.loads(Path(js).read_text(encoding="utf-8")))
        ODB_IDS.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    for r in rows:
        hf_hub_download(repo, f"images/{r['image_path']}", repo_type="dataset", local_dir=dst)
    # json con chỉ chứa 30 trang, để chạy script chấm chính thức trên đúng tập con
    keep = {r["image_path"] for r in rows}
    full = json.loads(Path(js).read_text(encoding="utf-8"))
    sub = [p for p in full if p["page_info"]["image_path"] in keep]
    (dst / "OmniDocBench_subset30.json").write_text(json.dumps(sub, ensure_ascii=False), encoding="utf-8")
    print(f"omnidocbench: {len(sub)} pages")


def dl_mdpbench() -> None:
    repo = "Delores-Lin/MDPBench"
    files = HfApi().list_repo_files(repo, repo_type="dataset")
    vi = [f for f in files if f.startswith("MDPBench_img_public/vi_")]
    snapshot_download(repo, repo_type="dataset", local_dir=OUT / "mdpbench",
                      allow_patterns=["MDPBench_public.json", "README.md", "eval.yaml", *vi])
    print(f"mdpbench: {len(vi)} images vi_")


TASKS = {"vi": dl_vi, "niits": dl_niits, "omnidocbench": dl_omnidocbench, "mdpbench": dl_mdpbench}

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="+", choices=list(TASKS), default=list(TASKS))
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    for name in args.only:
        print(f"== {name}")
        TASKS[name]()
