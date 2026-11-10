"""Chạy 1 engine OCR trên 1 bộ benchmark, ghi markdown mỗi trang.

Chỉ dùng stdlib + Pillow ở phần chung, để chạy được bằng venv của từng engine:
    .venv/Scripts/python                    -> tesseract, gemini
    data/team-4.2/ocr_bench/_envs/mineru    -> mineru
    data/team-4.2/ocr_bench/_envs/paddle    -> ppstructure

    python evals/team-4.2/runners/ocr_bench/run_engine.py --engine tesseract --suite vi
    python evals/team-4.2/runners/ocr_bench/run_engine.py --engine gemini --suite vi --limit 5

Output: data/team-4.2/ocr_bench/_out/<engine>/<suite>/<page_id>.md  (+ _meta.jsonl: giây/trang, conf, cost)
Suite:
    vi      nrl-ai/vn-ocr-documents-eval (real + synthetic, GT plain text)
    struct  OmniDocBench 30 trang (omnidocbench_ids.json)
    cross   MDPBench vi_* (40 gốc + 120 ảnh chụp)
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from PIL import Image, ImageOps

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
BENCH = ROOT / "data" / "team-4.2" / "ocr_bench"
OUT = BENCH / "_out"
ENV_FILE = ROOT / "app" / "team-4.2" / ".env"

# ---------------------------------------------------------------- datasets


def pages(suite: str) -> list[dict]:
    """[{id, image, group, gemini}] — `gemini` = trang nằm trong tập con chạy Gemini (ngân sách)."""
    rows: list[dict] = []
    if suite == "vi":
        for meta in sorted((BENCH / "vi").glob("*/metadata.jsonl")):
            for line in meta.read_text(encoding="utf-8").splitlines():
                r = json.loads(line)
                group = "real" if meta.parent.name == "real" else meta.parent.name
                rows.append({"id": r["doc_id"], "image": meta.parent / r["file_name"], "group": group})
    elif suite == "struct":
        for i, r in enumerate(json.loads((HERE / "omnidocbench_ids.json").read_text(encoding="utf-8"))):
            rows.append({"id": Path(r["image_path"]).stem, "image": BENCH / "omnidocbench" / "images" / r["image_path"],
                         "group": r["data_source"], "gemini": r["gemini"]})
    elif suite == "cross":
        for p in sorted(x for x in (BENCH / "mdpbench" / "MDPBench_img_public").glob("vi_*") if x.suffix in (".jpg", ".png")):
            m = re.match(r"vi_([a-z]+)_(\d+)(_.*)?$", p.stem)
            rows.append({"id": p.stem, "image": p, "group": "photo" if m.group(3) else "digital",
                         "doc": f"vi_{m.group(1)}_{m.group(2)}"})
    else:
        raise SystemExit(f"suite không hợp lệ: {suite}")
    return rows


def gemini_subset(suite: str, rows: list[dict]) -> list[dict]:
    """Tập trang Gemini chạy, theo ngân sách W02-02c (không có Batch API trên OpenRouter cho 2.5 Flash)."""
    if suite == "vi":
        return rows  # toàn bộ; bị cắt bởi --limit/ngưỡng chi phí nếu cần
    if suite == "struct":
        return [r for r in rows if r.get("gemini")]
    # cross: 10 trang gốc + ảnh chụp đầu tiên (theo tên) của chính 10 trang đó
    digital = sorted(r["doc"] for r in rows if r["group"] == "digital")
    step = max(1, len(digital) // 10)
    docs = set(digital[::step][:10])
    out, seen_photo = [], set()
    for r in sorted(rows, key=lambda r: r["id"]):
        if r["doc"] in docs and (r["group"] == "digital" or r["doc"] not in seen_photo):
            out.append(r)
            if r["group"] == "photo":
                seen_photo.add(r["doc"])
    return out


def local_subset(suite: str, rows: list[dict]) -> list[dict]:
    """Engine local: toàn bộ, trừ cross = 40 gốc + 1 ảnh chụp/trang (40) như plan."""
    if suite != "cross":
        return rows
    out, seen = [], set()
    for r in sorted(rows, key=lambda r: r["id"]):
        if r["group"] == "digital" or r["doc"] not in seen:
            out.append(r)
            if r["group"] == "photo":
                seen.add(r["doc"])
    return out


# ---------------------------------------------------------------- engines


def env_value(name: str) -> str:
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        k, _, v = line.partition("=")
        if k.strip().lower() == name.lower() and v.strip():
            return v.strip().strip('"').strip("'")
    v = os.environ.get(name) or os.environ.get(name.upper())
    if not v:
        raise SystemExit(f"thiếu {name} trong {ENV_FILE}")
    return v


TESSERACT = os.environ.get("TESSERACT_CMD", r"C:\Program Files\Tesseract-OCR\tesseract.exe")


def tesseract_page(img_path: Path, lang: str = "vie") -> tuple[str, dict]:
    img = ImageOps.exif_transpose(Image.open(img_path)).convert("L")
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "in.png"
        img.save(p)
        # Xoay theo OSD (bỏ qua nếu OSD không chắc)
        osd = subprocess.run([TESSERACT, str(p), "stdout", "--psm", "0"], capture_output=True, text=True)
        m = re.search(r"Rotate: (\d+)", osd.stdout)
        conf = re.search(r"Orientation confidence: ([\d.]+)", osd.stdout)
        rot = int(m.group(1)) if m and conf and float(conf.group(1)) > 2 else 0
        if rot:
            img.rotate(-rot, expand=True).save(p)
        # Một lần image_to_data (TSV) -> dựng dòng/đoạn + confidence
        tsv = subprocess.run([TESSERACT, str(p), "stdout", "-l", lang, "--psm", "3", "tsv"],
                             capture_output=True, text=True, encoding="utf-8").stdout
    lines: dict[tuple, list[str]] = {}
    confs = []
    for row in tsv.splitlines()[1:]:
        f = row.split("\t")
        if len(f) < 12 or f[0] != "5" or not f[11].strip():
            continue
        key = (int(f[2]), int(f[3]), int(f[4]))  # block, par, line
        lines.setdefault(key, []).append(f[11])
        if float(f[10]) >= 0:
            confs.append(float(f[10]))
    out, prev = [], None
    for key in sorted(lines):
        if prev and key[:2] != prev[:2]:
            out.append("")
        out.append(" ".join(lines[key]))
        prev = key
    return "\n".join(out), {"ocr_confidence": round(sum(confs) / len(confs), 2) if confs else None, "rotate": rot}


# engine -> model OpenRouter. Thư mục output đặt theo tên engine nên các model không ghi đè nhau.
GEMINI_ENGINES = {
    "gemini": os.environ.get("GEMINI_MODEL", "google/gemini-2.5-flash"),
    "gemini35lite": "google/gemini-3.5-flash-lite",
}
# 2.5 Flash tắt được thinking; 3.x bắt buộc reasoning ("cannot be disabled") -> mức thấp nhất.
REASONING = {"google/gemini-2.5-flash": {"enabled": False}}
REASONING_DEFAULT = {"effort": "minimal"}
PROMPT_VERSION = "v1"
PROMPT = """Bạn là công cụ OCR. Chép lại NGUYÊN VĂN toàn bộ chữ trong ảnh tài liệu, theo đúng thứ tự đọc.
Quy tắc:
- Không sửa chính tả, không sửa số, không thêm, không bỏ, không tóm tắt, không dịch. Giữ đúng dấu tiếng Việt.
- Chép cả quốc hiệu, tiêu ngữ, số hiệu, nơi nhận, chữ ký, chữ trong con dấu nếu đọc được.
- Định dạng Markdown: tiêu đề dùng #, ##; danh sách giữ nguyên ký hiệu gốc.
- Bảng: viết bằng HTML <table> (dùng rowspan/colspan nếu có ô gộp).
- Công thức toán: LaTeX trong $...$ hoặc $$...$$.
- Hình ảnh không có chữ: bỏ qua.
- Chỗ không đọc được: ghi [không đọc được].
Chỉ trả về nội dung đã chép, không giải thích, không bọc trong ```."""
COST_CAP = float(os.environ.get("OCR_COST_CAP_USD", "1.8"))
COST_LOG = BENCH / "_out" / "gemini" / "cost_log.jsonl"
CACHE = BENCH / "_out" / "gemini" / "_cache"


def spent() -> float:
    if not COST_LOG.exists():
        return 0.0
    return sum(json.loads(l).get("cost", 0) for l in COST_LOG.read_text(encoding="utf-8").splitlines() if l)


def gemini_page(img_path: Path, key: str, model: str) -> tuple[str, dict]:
    img = ImageOps.exif_transpose(Image.open(img_path)).convert("RGB")
    s = 1600 / max(img.size)
    if s < 1:
        img = img.resize((round(img.width * s), round(img.height * s)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    data = buf.getvalue()
    sha = hashlib.sha256(img_path.read_bytes()).hexdigest()
    cache = CACHE / f"{sha[:16]}_{model.replace('/', '_')}_{PROMPT_VERSION}.json"
    if cache.exists():
        resp = json.loads(cache.read_text(encoding="utf-8"))
        return resp["text"], {**resp["meta"], "cached": True}
    if spent() >= COST_CAP:
        raise RuntimeError(f"đã chạm ngưỡng chi phí {COST_CAP} USD")
    body = {
        "model": model,
        "temperature": 0,
        "max_tokens": 8192,
        "reasoning": REASONING.get(model, REASONING_DEFAULT),
        "usage": {"include": True},
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": PROMPT},
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(data).decode()}},
        ]}],
    }
    for attempt in range(5):
        req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", json.dumps(body).encode(),
                                     {"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
        try:
            r = json.load(urllib.request.urlopen(req, timeout=180))
            if "error" in r:
                raise RuntimeError(r["error"])
            c0 = r["choices"][0]
            if c0.get("finish_reason") == "error" and not c0.get("native_finish_reason"):
                # lỗi tạm thời phía provider (không phải RECITATION/SAFETY) -> retry, không cache
                raise RuntimeError(f"provider error: {c0.get('error') or c0}")
            break
        except (urllib.error.URLError, RuntimeError, TimeoutError) as e:
            if attempt == 4:
                raise
            print(f"  retry {attempt + 1}: {e}", file=sys.stderr)
            time.sleep(5 * 2 ** attempt)
    ch = r["choices"][0]
    u = r.get("usage", {})
    meta = {"model": r.get("model"), "prompt_version": PROMPT_VERSION, "finish_reason": ch.get("finish_reason"),
            "native_finish_reason": ch.get("native_finish_reason"),
            "prompt_tokens": u.get("prompt_tokens"), "completion_tokens": u.get("completion_tokens"),
            "reasoning_tokens": (u.get("completion_tokens_details") or {}).get("reasoning_tokens"),
            "cost": u.get("cost", 0), "date": time.strftime("%Y-%m-%d")}
    if meta["finish_reason"] not in ("stop", None) or str(meta["native_finish_reason"]).upper() in ("RECITATION", "MAX_TOKENS"):
        meta["issue"] = "truncated_or_recitation"
    text = (ch["message"].get("content") or "").strip()
    text = re.sub(r"^```(?:markdown|md)?\n|\n```$", "", text)
    COST_LOG.parent.mkdir(parents=True, exist_ok=True)
    with COST_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"image": img_path.name, **meta}) + "\n")
    CACHE.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps({"text": text, "meta": meta}, ensure_ascii=False), encoding="utf-8")
    return text, meta


MINERU_TIER = os.environ.get("MINERU_TIER", "standard")


def run_mineru(rows: list[dict], out: Path, lang: str) -> None:
    """MinerU 4.x (`mineru-kit parse`, chạy cục bộ — KHÔNG dùng --remote), cả thư mục 1 lần để load model 1 lần.
    Tier `standard` = hybrid VLM (llama.cpp) + OCR ONNX; MinerU 4.x không còn tham số lang."""
    work = BENCH / "_work" / "mineru" / out.name
    src = work / "in"
    shutil.rmtree(work, ignore_errors=True)
    src.mkdir(parents=True)
    for r in rows:
        shutil.copy(r["image"], src / f"{r['id']}{r['image'].suffix}")
    exe = Path(sys.executable).parent / "mineru-kit.exe"
    t0 = time.time()
    subprocess.run([str(exe), "parse", str(src), "-o", str(work / "out"), "--tier", MINERU_TIER], check=True)
    dt = (time.time() - t0) / len(rows)  # gồm cả thời gian load model, chia đều
    with (out / "_meta.jsonl").open("w", encoding="utf-8") as m:
        for r in rows:
            md = work / "out" / f"{r['id']}.md"
            (out / f"{r['id']}.md").write_text(md.read_text(encoding="utf-8") if md.exists() else "", encoding="utf-8")
            m.write(json.dumps({"id": r["id"], "group": r["group"], "sec": round(dt, 2), "tier": MINERU_TIER,
                                "missing": not md.exists()}) + "\n")


def run_ppstructure(rows: list[dict], out: Path, lang: str) -> None:
    from paddleocr import PPStructureV3  # venv paddle

    pipe = PPStructureV3(lang=lang, use_doc_orientation_classify=True, use_doc_unwarping=False)
    with (out / "_meta.jsonl").open("w", encoding="utf-8") as m:
        for r in rows:
            t0 = time.time()
            res = list(pipe.predict(str(r["image"])))
            md = "\n\n".join(x.markdown["markdown_texts"] for x in res)
            (out / f"{r['id']}.md").write_text(md, encoding="utf-8")
            m.write(json.dumps({"id": r["id"], "group": r["group"], "sec": round(time.time() - t0, 2)}) + "\n")
            print(r["id"], f"{time.time() - t0:.1f}s", flush=True)


# ---------------------------------------------------------------- main


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", required=True, choices=["tesseract", *GEMINI_ENGINES, "mineru", "ppstructure"])
    ap.add_argument("--suite", required=True, choices=["vi", "struct", "cross"])
    ap.add_argument("--limit", type=int)
    ap.add_argument("--lang", help="mineru: latin|ch|en ; ppstructure: vi|ch|en (mặc định theo suite)")
    ap.add_argument("--out-tag", default="", help="hậu tố thư mục output, vd. _pilot")
    a = ap.parse_args()

    rows = pages(a.suite)
    rows = gemini_subset(a.suite, rows) if a.engine in GEMINI_ENGINES else local_subset(a.suite, rows)
    if a.limit:
        rows = rows[: a.limit]
    out = OUT / a.engine / (a.suite + a.out_tag)
    out.mkdir(parents=True, exist_ok=True)
    print(f"{a.engine} / {a.suite}: {len(rows)} trang -> {out}")

    if a.engine == "mineru":
        return run_mineru(rows, out, a.lang or ("latin" if a.suite != "struct" else "ch"))
    if a.engine == "ppstructure":
        return run_ppstructure(rows, out, a.lang or ("vi" if a.suite != "struct" else "ch"))

    key = env_value("openrouter") if a.engine in GEMINI_ENGINES else None
    with (out / "_meta.jsonl").open("w", encoding="utf-8") as m:
        for i, r in enumerate(rows, 1):
            t0 = time.time()
            try:
                if a.engine == "tesseract":
                    lang = "vie" if a.suite != "struct" else "eng+chi_sim"
                    text, meta = tesseract_page(r["image"], lang)
                else:
                    text, meta = gemini_page(r["image"], key, GEMINI_ENGINES[a.engine])
            except RuntimeError as e:
                print(f"DỪNG: {e}")
                break
            (out / f"{r['id']}.md").write_text(text, encoding="utf-8")
            meta = {"id": r["id"], "group": r["group"], "sec": round(time.time() - t0, 2), **meta}
            m.write(json.dumps(meta, ensure_ascii=False) + "\n")
            m.flush()
            extra = f" cost={meta.get('cost', 0):.5f} total={spent():.4f}" if a.engine in GEMINI_ENGINES else ""
            print(f"[{i}/{len(rows)}] {r['id']} {meta['sec']}s{extra}", flush=True)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
