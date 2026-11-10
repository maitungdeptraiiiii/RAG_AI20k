"""Chấm Bộ 1 (OCR tiếng Việt, nrl-ai) cho mọi engine đã chạy.

    python evals/team-4.2/runners/ocr_bench/score_vi.py
-> evals/team-4.2/results/w02-ocr-vi/{summary.md, per_page.jsonl}

Chuẩn hoá chung (W02-02c): NFC · kiểu bỏ dấu cũ/mới (hoà≡hòa, thuý≡thúy) · gộp khoảng trắng · gỡ gạch nối cuối dòng
· bỏ cú pháp Markdown/HTML ở output (GT là plain text).
Metric:
  CER, WER                       edit distance / độ dài GT (sau chuẩn hoá)
  CER_card                       chỉ NFC + gộp khoảng trắng (như card nrl-ai, để sanity check 12.62% của Tesseract trên `real`)
  diacritic_err                  lỗi dấu / số ký tự có dấu trong GT, tách: mất dấu · sai dấu ; base_err = sai chữ cái gốc
  num_acc                        token số/ngày trong GT được chép đúng tại vị trí đã căn (không dùng "chứa chuỗi")
  plausible_num_err              số sai nhưng vẫn là số hợp lệ (03→08) — loại lỗi "trông hợp lệ"
  dieu_acc                       "Điều N"/"Khoản N" đúng tại vị trí căn
  khong_drop                     số lần chữ "không" trong GT bị mất/sai (lỗi phủ định)
"""

from __future__ import annotations

import html
import json
import re
import statistics
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

from rapidfuzz.distance import Levenshtein

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_engine import OUT, pages  # noqa: E402

RES = Path(__file__).resolve().parents[2] / "results" / "w02-ocr-vi"
ENGINES = ["tesseract", "gemini", "gemini35lite", "mineru", "ppstructure"]

# ---------------------------------------------------------------- chuẩn hoá

# kiểu bỏ dấu cũ -> mới trên oa/oe/uy (hoà -> hòa, thuý -> thúy)
_TONES = "̣̀́̃̉"


def _tone_new_style(s: str) -> str:
    d = unicodedata.normalize("NFD", s)
    # o/a/e/u/y + dấu thanh nằm ở nguyên âm sau trong "oa","oe","uy" (không có phụ âm cuối) -> chuyển về nguyên âm trước
    d = re.sub(rf"([oO])([aAeE])([{_TONES}])(?![a-zA-Z])", r"\1\3\2", d)
    d = re.sub(rf"([uU])([yY])([{_TONES}])(?![a-zA-Z])", r"\1\3\2", d)
    return unicodedata.normalize("NFC", d)


def md_to_text(s: str) -> str:
    s = re.sub(r"<img[^>]*>|!\[[^\]]*\]\([^)]*\)", " ", s)
    s = re.sub(r"</t[dh]>", " ", s)
    s = re.sub(r"</tr>|<br\s*/?>", "\n", s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    s = re.sub(r"^\s{0,3}#{1,6}\s*", "", s, flags=re.M)          # heading
    s = re.sub(r"\*\*|__|(?<!\w)\*(?!\s)|(?<!\s)\*(?!\w)", "", s)  # bold/italic
    s = re.sub(r"^\s*\|?\s*:?-{3,}.*$", "", s, flags=re.M)         # md table separator
    s = s.replace("|", " ")
    s = s.replace("$", "")
    return s


def norm(s: str) -> str:
    s = unicodedata.normalize("NFC", s)
    s = re.sub(r"(\w)-\n(\w)", r"\1\2", s)  # gạch nối cuối dòng
    s = _tone_new_style(s)
    s = re.sub(r"[“”]", '"', s)
    s = re.sub(r"[‘’]", "'", s)
    s = re.sub(r"[–—]", "-", s)
    return re.sub(r"\s+", " ", s).strip()


def norm_card(s: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", s)).strip()


# ---------------------------------------------------------------- căn chỉnh


def strip_marks(c: str) -> str:
    return "".join(x for x in unicodedata.normalize("NFD", c) if not unicodedata.combining(x)).replace("đ", "d").replace("Đ", "D")


def has_mark(c: str) -> bool:
    return strip_marks(c) != c


def align_map(gt: str, pred: str) -> list[int]:
    """gt_index -> pred_index nếu ký tự đó khớp đúng, -1 nếu bị sửa/xoá."""
    m = [-1] * len(gt)
    for blk in Levenshtein.opcodes(gt, pred):
        if blk.tag == "equal":
            for k in range(blk.src_end - blk.src_start):
                m[blk.src_start + k] = blk.dest_start + k
    return m


def diacritics(gt: str, pred: str) -> dict:
    missing = wrong = base = 0
    for op in Levenshtein.editops(gt, pred):
        if op.tag != "replace":
            continue
        g, p = gt[op.src_pos], pred[op.dest_pos]
        if strip_marks(g).lower() == strip_marks(p).lower():
            if has_mark(g) and not has_mark(p):
                missing += 1
            else:
                wrong += 1
        elif g.isalpha():
            base += 1
    marked = sum(has_mark(c) for c in gt)
    return {"marked": marked, "dia_missing": missing, "dia_wrong": wrong, "base_err": base}


NUM = re.compile(r"\d+(?:[.,/:-]\d+)*")
DIEU = re.compile(r"(?:Điều|Khoản|Điểm)\s+\d+[a-zđ]?", re.I)


def token_check(gt: str, pred: str, amap: list[int], rx: re.Pattern) -> tuple[int, int, int]:
    """(tổng, đúng, sai-nhưng-hợp-lệ) cho token khớp rx trong GT, chấm tại vị trí căn."""
    total = ok = plausible = 0
    for m in rx.finditer(gt):
        total += 1
        span = amap[m.start():m.end()]
        if all(i >= 0 for i in span) and span == list(range(span[0], span[0] + len(span))):
            # chặn ranh giới: ký tự ngay trước/sau ở pred không được là chữ số dính thêm
            a, b = span[0], span[-1] + 1
            if not (a > 0 and pred[a - 1].isdigit()) and not (b < len(pred) and pred[b].isdigit()):
                ok += 1
                continue
        # sai: xem đoạn pred tương ứng có phải 1 số hợp lệ khác không
        left = next((amap[i] for i in range(m.start() - 1, -1, -1) if amap[i] >= 0), -1) + 1
        right = next((amap[i] for i in range(m.end(), len(gt)) if amap[i] >= 0), len(pred))
        seg = pred[left:right].strip()
        if rx is NUM and seg and NUM.fullmatch(seg) and seg != m.group():
            plausible += 1
    return total, ok, plausible


def khong_drops(gt: str, amap: list[int]) -> tuple[int, int]:
    tot = bad = 0
    for m in re.finditer(r"(?<!\w)không(?!\w)", gt, re.I):
        tot += 1
        if any(i < 0 for i in amap[m.start():m.end()]):
            bad += 1
    return tot, bad


# ---------------------------------------------------------------- main


def score_page(gt_raw: str, pred_raw: str) -> dict:
    gt, pred = norm(gt_raw), norm(md_to_text(pred_raw))
    amap = align_map(gt, pred)
    n_tot, n_ok, n_pl = token_check(gt, pred, amap, NUM)
    d_tot, d_ok, _ = token_check(gt, pred, amap, DIEU)
    k_tot, k_bad = khong_drops(gt, amap)
    gw, pw = gt.split(), pred.split()
    return {
        "gt_chars": len(gt), "char_edits": Levenshtein.distance(gt, pred),
        "card_edits": Levenshtein.distance(norm_card(gt_raw), norm_card(md_to_text(pred_raw))), "card_chars": len(norm_card(gt_raw)),
        "gt_words": len(gw), "word_edits": Levenshtein.distance(gw, pw),
        **diacritics(gt, pred),
        "num_total": n_tot, "num_ok": n_ok, "num_plausible_err": n_pl,
        "dieu_total": d_tot, "dieu_ok": d_ok, "khong_total": k_tot, "khong_bad": k_bad,
    }


def aggregate(rows: list[dict]) -> dict:
    s = defaultdict(float)
    for r in rows:
        for k, v in r.items():
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                s[k] += v
    div = lambda a, b: round(100 * a / b, 2) if b else None  # noqa: E731
    secs = [r["sec"] for r in rows if r.get("sec") is not None]
    return {
        "n": len(rows),
        "CER": div(s["char_edits"], s["gt_chars"]), "WER": div(s["word_edits"], s["gt_words"]),
        "CER_card": div(s["card_edits"], s["card_chars"]),
        "dia_missing": div(s["dia_missing"], s["marked"]), "dia_wrong": div(s["dia_wrong"], s["marked"]),
        "base_err": div(s["base_err"], s["gt_chars"]),
        "num_acc": div(s["num_ok"], s["num_total"]), "num_plausible_err": int(s["num_plausible_err"]),
        "num_total": int(s["num_total"]),
        "dieu_acc": div(s["dieu_ok"], s["dieu_total"]), "dieu_total": int(s["dieu_total"]),
        "khong_bad": f"{int(s['khong_bad'])}/{int(s['khong_total'])}",
        "sec_page": round(statistics.median(secs), 2) if secs else None,
    }


def main() -> None:
    gts = {}
    for meta in (OUT.parent / "vi").glob("*/metadata.jsonl"):
        for line in meta.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            gts[r["doc_id"]] = r["text"]
    # Sửa lỗi GT đã kiểm tra bằng mắt trên ảnh gốc (xem gt_fixes_vi.json, có bằng chứng từng dòng)
    for fx in json.loads((Path(__file__).resolve().parent / "gt_fixes_vi.json").read_text(encoding="utf-8")):
        assert gts[fx["doc_id"]].count(fx["old"]) == 1, fx
        gts[fx["doc_id"]] = gts[fx["doc_id"]].replace(fx["old"], fx["new"])
    plist = pages("vi")
    RES.mkdir(parents=True, exist_ok=True)
    per_page, table = [], {}
    for eng in ENGINES:
        d = OUT / eng / "vi"
        if not d.exists():
            continue
        meta = {}
        if (d / "_meta.jsonl").exists():
            meta = {json.loads(l)["id"]: json.loads(l) for l in (d / "_meta.jsonl").read_text(encoding="utf-8").splitlines() if l}
        rows = []
        for p in plist:
            f = d / f"{p['id']}.md"
            if not f.exists():
                continue
            r = {"engine": eng, "id": p["id"], "group": p["group"], "sec": meta.get(p["id"], {}).get("sec"),
                 **score_page(gts[p["id"]], f.read_text(encoding="utf-8"))}
            rows.append(r)
        per_page += rows
        groups = defaultdict(list)
        for r in rows:
            groups[r["group"]].append(r)
            groups["synthetic (all)" if r["group"] != "real" else "_real"].append(r)
        table[eng] = {"ALL": aggregate(rows), **{g: aggregate(v) for g, v in sorted(groups.items()) if not g.startswith("_")}}
    with (RES / "per_page.jsonl").open("w", encoding="utf-8") as f:
        for r in per_page:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    (RES / "summary.json").write_text(json.dumps(table, ensure_ascii=False, indent=1), encoding="utf-8")

    cols = ["n", "CER", "WER", "CER_card", "dia_missing", "dia_wrong", "base_err", "num_acc", "num_plausible_err",
            "dieu_acc", "khong_bad", "sec_page"]
    lines = ["# W02 · Bộ 1 — OCR tiếng Việt (nrl-ai/vn-ocr-documents-eval)", "",
             "Tạo bởi `evals/team-4.2/runners/ocr_bench/score_vi.py`. Đơn vị %, trừ `n`, `num_plausible_err` (số lần), "
             "`khong_bad` (mất/sai / tổng), `sec_page` (trung vị giây/trang).", ""]
    groups = sorted({g for t in table.values() for g in t if g != "ALL"}, key=lambda g: (g != "real", g))
    for g in ["ALL", *groups]:
        lines += [f"## {g}", "", "| engine | " + " | ".join(cols) + " |", "|---" * (len(cols) + 1) + "|"]
        for eng, t in table.items():
            if g in t:
                lines.append(f"| {eng} | " + " | ".join("" if t[g][c] is None else str(t[g][c]) for c in cols) + " |")
        lines.append("")
    (RES / "summary.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
