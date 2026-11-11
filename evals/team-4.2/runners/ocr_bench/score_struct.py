"""Chấm Bộ 2 (OmniDocBench 30 trang) và kiểm tra chéo (MDPBench vi_*) — scorer TỰ VIẾT, không phải script chính thức.

    python evals/team-4.2/runners/ocr_bench/score_struct.py --suite struct   -> results/w02-ocr-struct/
    python evals/team-4.2/runners/ocr_bench/score_struct.py --suite cross    -> results/w02-ocr-cross/

Số theo script chính thức nằm ở official_eval.py → results/w02-ocr-official/. File này giữ các metric mà script chính thức
không có (heading, header/footer leak, block_ned, cjk_rate). Số ở đây KHÔNG so trực tiếp được với leaderboard.

Metric (page-level, GT theo layout_dets của json chính thức):
  TEDS / TEDS-S   bảng GT ghép với bảng dự đoán (greedy theo TEDS), bảng thiếu = 0. Tesseract: N/A.
  heading_rec     % title GT xuất hiện ở dòng heading Markdown (#) của dự đoán. Tesseract: N/A.
  order           % cặp block GT (đã định vị được trong dự đoán) đúng thứ tự đọc
  hf_leak         % header/footer/page_number GT bị chép vào dự đoán (thấp = tốt)
  block_ned       lỗi chữ theo block: mỗi block text GT căn vào vị trí khớp nhất trong dự đoán rồi đo edit distance
                  (không phụ thuộc thứ tự đọc; không phạt chữ thừa) — chỉ `cross` (tiếng Việt)
  text_ned        normalized edit distance cả trang (bỏ bảng/công thức/hình/header/footer) — nhạy với thứ tự đọc
  cjk_rate        % ký tự CJK trong dự đoán — bắt lỗi nhận tiếng Việt thành chữ Trung (chỉ `cross`)
"""

from __future__ import annotations

import argparse
import html as htmlmod
import json
import re
import statistics
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

from apted import APTED, Config
from lxml import etree, html as lhtml
from rapidfuzz import fuzz
from rapidfuzz.distance import Levenshtein

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_engine import BENCH, OUT, pages  # noqa: E402

RESULTS = Path(__file__).resolve().parents[2] / "results"
ENGINES = ["tesseract", "gemini", "gemini35lite", "mineru", "ppstructure"]
NO_STRUCT = {"tesseract"}  # plain text: không có bảng/heading
HF = {"header", "footer", "page_number", "page_footnote"}
TEXT = {"text_block", "title", "figure_caption", "table_caption", "table_footnote", "figure_footnote", "reference",
        "code_txt", "equation_caption", "list_group"}

# ---------------------------------------------------------------- TEDS (PubTabNet)


class Node:
    def __init__(self, tag, colspan=1, rowspan=1, content=""):
        self.tag, self.colspan, self.rowspan, self.content, self.children = tag, colspan, rowspan, content, []


class TedsConfig(Config):
    def rename(self, a, b):
        if a.tag != b.tag or a.colspan != b.colspan or a.rowspan != b.rowspan:
            return 1.0
        if a.tag == "td" and (a.content or b.content):
            return Levenshtein.normalized_distance(a.content, b.content)
        return 0.0

    def children(self, n):
        return n.children


def _tree(el, structure_only: bool) -> Node:
    tag = "td" if el.tag in ("td", "th") else el.tag
    n = Node(tag, int(el.attrib.get("colspan", 1) or 1), int(el.attrib.get("rowspan", 1) or 1),
             "" if structure_only or tag != "td" else re.sub(r"\s+", " ", el.text_content()).strip())
    if tag != "td":
        n.children = [_tree(c, structure_only) for c in el if c.tag in ("tr", "td", "th", "thead", "tbody")]
    return n


def _table_root(s: str):
    try:
        doc = lhtml.fromstring(s)
    except (etree.ParserError, ValueError):
        return None
    t = doc if doc.tag == "table" else doc.find(".//table")
    if t is None:
        return None
    for x in t.findall(".//thead") + t.findall(".//tbody"):
        x.drop_tag()
    return t


def _count(n: Node) -> int:
    return 1 + sum(_count(c) for c in n.children)


def teds(pred: str, gt: str, structure_only: bool = False) -> float:
    p, g = _table_root(pred), _table_root(gt)
    if g is None:
        return float("nan")
    if p is None:
        return 0.0
    tp, tg = _tree(p, structure_only), _tree(g, structure_only)
    d = APTED(tp, tg, TedsConfig()).compute_edit_distance()
    return 1 - d / max(_count(tp), _count(tg))


def md_pipe_tables_to_html(md: str) -> str:
    """Bảng Markdown |a|b| -> <table> để chấm chung."""
    out, buf = [], []

    def flush():
        rows = [r for r in buf if not re.fullmatch(r"\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?", r.strip())]
        if rows:
            cells = ["<tr>" + "".join(f"<td>{htmlmod.escape(c.strip())}</td>" for c in r.strip().strip("|").split("|")) + "</tr>" for r in rows]
            out.append("<table>" + "".join(cells) + "</table>")
        buf.clear()

    for line in md.splitlines():
        if line.strip().startswith("|") and line.count("|") >= 2:
            buf.append(line)
        else:
            if buf:
                flush()
            out.append(line)
    if buf:
        flush()
    return "\n".join(out)


TABLE_RX = re.compile(r"<table.*?</table>", re.S | re.I)

# ---------------------------------------------------------------- text helpers


def clean(s: str) -> str:
    s = unicodedata.normalize("NFC", htmlmod.unescape(s))
    return re.sub(r"\s+", " ", s).strip()


def strip_md(md: str) -> str:
    s = TABLE_RX.sub(" ", md)
    s = re.sub(r"\$\$.*?\$\$", " ", s, flags=re.S)
    s = re.sub(r"<img[^>]*>|!\[[^\]]*\]\([^)]*\)|<[^>]+>", " ", s)
    s = re.sub(r"^\s{0,3}#{1,6}\s*", "", s, flags=re.M)
    s = re.sub(r"\*\*|__", "", s)
    return clean(s)


def locate(needle: str, hay: str) -> int | None:
    if len(needle) < 8 or not hay:
        return None
    a = fuzz.partial_ratio_alignment(needle, hay)
    return a.dest_start if a and a.score >= 80 else None


def order_score(blocks: list[str], pred_text: str) -> tuple[int, int]:
    pos = [p for p in (locate(b, pred_text) for b in blocks) if p is not None]
    ok = tot = 0
    for i in range(len(pos)):
        for j in range(i + 1, len(pos)):
            tot += 1
            ok += pos[i] < pos[j]
    return ok, tot


# ---------------------------------------------------------------- per page


def score_page(gt_page: dict, md: str, struct_engine: bool, with_text: bool) -> dict:
    dets = sorted(gt_page["layout_dets"], key=lambda e: 10**6 if e.get("order") in (None, "") else int(e["order"]))
    md2 = md_pipe_tables_to_html(md)
    pred_tables = TABLE_RX.findall(md2)
    pred_text = strip_md(md2)
    r: dict = {}
    # bảng
    gt_tables = [e["html"] for e in dets if e["category_type"] == "table" and e.get("html")]
    r["n_gt_tables"], r["n_pred_tables"] = len(gt_tables), len(pred_tables)
    if struct_engine and gt_tables:
        used, t_full, t_struct = set(), [], []
        for g in gt_tables:
            best, bi = 0.0, None
            for i, p in enumerate(pred_tables):
                if i in used:
                    continue
                s = teds(p, g, True)
                if s > best:
                    best, bi = s, i
            if bi is not None:
                used.add(bi)
                t_struct.append(best)
                t_full.append(teds(pred_tables[bi], g))
            else:
                t_struct.append(0.0)
                t_full.append(0.0)
        r["teds"], r["teds_s"] = t_full, t_struct
    # heading
    titles = [clean(e["text"]) for e in dets if e["category_type"] == "title" and e.get("text")]
    if struct_engine and titles:
        heads = [clean(re.sub(r"^#+\s*", "", l)) for l in md2.splitlines() if re.match(r"^\s{0,3}#{1,6}\s", l)]
        r["title_total"] = len(titles)
        r["title_hit"] = sum(any(fuzz.ratio(t, h) >= 85 or (len(t) > 15 and fuzz.partial_ratio(t, h) >= 90) for h in heads)
                             for t in titles)
    # thứ tự đọc
    blocks = [clean(e["text"]) for e in dets if e["category_type"] in TEXT and e.get("text")]
    r["order_ok"], r["order_tot"] = order_score(blocks, pred_text)
    # header/footer
    hf = [clean(e["text"]) for e in dets if e["category_type"] in HF and len(clean(e.get("text") or "")) >= 3]
    r["hf_total"] = len(hf)
    r["hf_leak"] = sum(fuzz.partial_ratio(h, pred_text) >= 90 for h in hf)
    if with_text:
        # như OmniDocBench: header/footer dự đoán thừa không tính là lỗi text -> cắt khỏi pred trước khi đo
        for h in hf:
            al = fuzz.partial_ratio_alignment(h, pred_text)
            if al and al.score >= 90:
                pred_text = pred_text[:al.dest_start] + " " + pred_text[al.dest_end:]
        pred_text = clean(pred_text)
        gt_text = clean(" ".join(blocks))
        r["text_edits"], r["text_len"] = Levenshtein.distance(gt_text, pred_text), max(len(gt_text), len(pred_text))
        be = bl = 0
        for b in blocks:
            al = fuzz.partial_ratio_alignment(b, pred_text) if pred_text else None
            win = pred_text[al.dest_start:al.dest_end] if al and al.score >= 50 else ""
            be += Levenshtein.distance(b, win)
            bl += len(b)
        r["block_edits"], r["block_len"] = be, bl
        r["cjk"] = sum(1 for c in pred_text if "一" <= c <= "鿿")
        r["pred_chars"] = len(pred_text)
    return r


def aggregate(rows: list[dict], struct_engine: bool, with_text: bool) -> dict:
    pct = lambda a, b: round(100 * a / b, 1) if b else None  # noqa: E731
    sm = lambda k: sum(r.get(k, 0) for r in rows)  # noqa: E731
    teds_all = [x for r in rows for x in r.get("teds", [])]
    teds_s = [x for r in rows for x in r.get("teds_s", [])]
    secs = [r["sec"] for r in rows if r.get("sec") is not None]
    a = {
        "n": len(rows),
        "gt_tables": sm("n_gt_tables"),
        "TEDS": round(100 * statistics.mean(teds_all), 1) if struct_engine and teds_all else "N/A",
        "TEDS_S": round(100 * statistics.mean(teds_s), 1) if struct_engine and teds_s else "N/A",
        "heading_rec": pct(sm("title_hit"), sm("title_total")) if struct_engine else "N/A",
        "order": pct(sm("order_ok"), sm("order_tot")),
        "hf_leak": pct(sm("hf_leak"), sm("hf_total")),
        "sec_page": round(statistics.median(secs), 2) if secs else None,
    }
    if with_text:
        a["text_ned"] = round(100 * sm("text_edits") / sm("text_len"), 1) if sm("text_len") else None
        a["block_ned"] = round(100 * sm("block_edits") / sm("block_len"), 1) if sm("block_len") else None
        a["cjk_rate"] = round(100 * sm("cjk") / sm("pred_chars"), 2) if sm("pred_chars") else None
    return a


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--suite", required=True, choices=["struct", "cross"])
    a = ap.parse_args()
    if a.suite == "struct":
        gt = json.loads((BENCH / "omnidocbench" / "OmniDocBench_subset30.json").read_text(encoding="utf-8"))
        res = RESULTS / "w02-ocr-struct"
    else:
        gt = [x for x in json.loads((BENCH / "mdpbench" / "MDPBench_public.json").read_text(encoding="utf-8"))
              if x["page_info"]["image_path"].startswith("vi_")]
        res = RESULTS / "w02-ocr-cross"
    gt_by = {Path(x["page_info"]["image_path"]).stem: x for x in gt}
    plist = {p["id"]: p for p in pages(a.suite)}
    with_text = a.suite == "cross"
    res.mkdir(parents=True, exist_ok=True)
    table, per_page, by_eng = {}, [], {}
    for eng in ENGINES:
        d = OUT / eng / a.suite
        if not d.exists():
            continue
        meta = {}
        if (d / "_meta.jsonl").exists():
            meta = {json.loads(l)["id"]: json.loads(l) for l in (d / "_meta.jsonl").read_text(encoding="utf-8").splitlines() if l}
        rows = []
        for f in sorted(d.glob("*.md")):
            if f.stem not in gt_by:
                continue
            r = {"engine": eng, "id": f.stem, "group": plist[f.stem]["group"], "sec": meta.get(f.stem, {}).get("sec"),
                 **score_page(gt_by[f.stem], f.read_text(encoding="utf-8"), eng not in NO_STRUCT, with_text)}
            rows.append(r)
        by_eng[eng] = rows
        per_page += rows
    common = set.intersection(*({r["id"] for r in rows} for rows in by_eng.values())) if by_eng else set()
    for eng, rows in by_eng.items():
        se = eng not in NO_STRUCT
        groups = defaultdict(list)
        for r in rows:
            groups[r["group"]].append(r)
            if r["id"] in common:
                groups["COMMON (trang mọi engine đều chạy)"].append(r)
        table[eng] = {"ALL": aggregate(rows, se, with_text), **{g: aggregate(v, se, with_text) for g, v in sorted(groups.items())}}
    with (res / "per_page.jsonl").open("w", encoding="utf-8") as f:
        for r in per_page:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    (res / "summary.json").write_text(json.dumps(table, ensure_ascii=False, indent=1), encoding="utf-8")
    cols = ["n", "gt_tables", "TEDS", "TEDS_S", "heading_rec", "order", "hf_leak", "sec_page"] + (["block_ned", "text_ned", "cjk_rate"] if with_text else [])
    title = "Bộ 2 — cấu trúc (OmniDocBench, 30 trang)" if a.suite == "struct" else "Kiểm tra chéo — MDPBench tiếng Việt"
    lines = [f"# W02 · {title}", "",
             "Scorer tự viết (`evals/team-4.2/runners/ocr_bench/score_struct.py`), **không phải script chính thức** → không so trực tiếp với leaderboard. "
             "Đơn vị %; `hf_leak`, `block_ned`, `text_ned`, `cjk_rate` thấp = tốt; còn lại cao = tốt. Engine chạy trên tập trang khác nhau (xem `n`).", ""]
    groups = sorted({g for t in table.values() for g in t if g != "ALL"})
    for g in ["ALL", *groups]:
        lines += [f"## {g}", "", "| engine | " + " | ".join(cols) + " |", "|---" * (len(cols) + 1) + "|"]
        for eng, t in table.items():
            if g in t:
                lines.append(f"| {eng} | " + " | ".join("" if t[g].get(c) is None else str(t[g][c]) for c in cols) + " |")
        lines.append("")
    (res / "summary.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
