"""Đo trích dữ kiện nền (rag.contracts.facts.extract_facts) trên CUAD v1 (CC-BY-4.0, hợp đồng tiếng Anh).

Chạy (từ app/team-4.2; dữ liệu đặt NGOÀI repo):
    uv run python scripts/bench_cuad_facts.py --data <CUAD_v1.json> --out <thư mục kết quả> --n 30
    uv run python scripts/bench_cuad_facts.py --data <CUAD_v1.json> --out <thư mục> --score-only   # chấm lại, không gọi LLM

Nhãn CUAD dùng: Parties, Agreement Date, Effective Date, Expiration Date (đáp án là ĐOẠN TRÍCH, không phải giá trị
chuẩn hóa). Cách chấm (chốt trước khi chạy):
- Parties: F1 trên tập tên + vai trò. Một đáp án được tìm thấy nếu chuỗi chuẩn hóa của nó chứa / nằm trong tên hoặc
  vai trò của một bên do hệ thống trích, hoặc trùng >= 60% token.
- Agreement Date / Effective Date: lấy các ngày đọc ra được từ đoạn đáp án (regex); đúng nếu ngày hệ thống trích nằm trong
  tập đó. Đáp án "không có" mà hệ thống vẫn trả ngày là dương tính giả.
- Term: hệ thống không có trường "ngày hết hạn"; chấm bằng việc câu trích của `term` trùng (>= 50% đoạn ngắn hơn) với
  đoạn đáp án Expiration Date hoặc Renewal Term.
- Câu trích của sign_date / effective_date có trùng đoạn đáp án không (kiểm tra "tìm đúng chỗ").

Chỉ số thêm sau lần đo 1 (xem notes/2026-11-13-cuad-facts-benchmark.md, mục S5):
- `party_duplicates`: số mục bên trùng tên (đã chuẩn hóa) với một mục khác của cùng hợp đồng.
- `parties_named`: như Parties nhưng bỏ khỏi đáp án các nhãn định nghĩa (`the "Company"`, `Party A`, `(together the
  "Parties" …)`). Bộ lọc viết SAU khi xem kết quả lần 1 -> chỉ là chỉ số phụ.
- Ngày ký: `correct` = hệ thống có đúng MỘT ứng viên và nó khớp (giá trị sẽ được tự đặt); `in_candidates` = đáp án nằm
  trong các ứng viên (kể cả khi mâu thuẫn, chờ người dùng chọn); `conflicts` = số hợp đồng có hơn một ứng viên;
  `in_sign_or_effective` = đáp án khớp ngày ký hoặc ngày hiệu lực (CUAD gọi "effective as of" là ngày thỏa thuận).
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from pathlib import Path

MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november",
     "december"], 1)}
MONTHS |= {k[:3]: v for k, v in list(MONTHS.items())} | {"sept": 9}
_MON = "|".join(sorted(MONTHS, key=len, reverse=True))
_D_MDY = re.compile(rf"\b({_MON})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?\s*,?\s+(\d{{4}})\b", re.I)
_D_DMY = re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:day\s+of\s+)?({_MON})\.?\s*,?\s+(\d{{4}})\b", re.I)
_D_NUM = re.compile(r"\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})\b")
_DEFINITIONAL = re.compile(r'["“”]|\b(collectively|individually|hereinafter|referred to|each a|together)\b', re.I)
_GENERIC = {"company", "customer", "agent", "bank", "distributor", "party a", "party b", "professional", "franchisee",
            "you", "contractor", "licensor", "licensee", "supplier", "buyer", "seller"}
CATEGORIES = ("Parties", "Agreement Date", "Effective Date", "Expiration Date", "Renewal Term")


def dates_in(text: str) -> set[date]:
    """Mọi ngày đọc ra được trong `text` (tháng-chữ; số dạng M/D/Y)."""
    text = " ".join(unicodedata.normalize("NFC", text or "").split())
    out: set[date] = set()
    for m in _D_MDY.finditer(text):
        out.add(_mk(m.group(3), MONTHS[m.group(1).lower()], m.group(2)))
    for m in _D_DMY.finditer(text):
        out.add(_mk(m.group(3), MONTHS[m.group(2).lower()], m.group(1)))
    for m in _D_NUM.finditer(text):
        out.add(_mk(m.group(3), m.group(1), m.group(2)))
    return {d for d in out if d}


def _mk(y, mo, d) -> date | None:
    y = int(y)
    y = y + (2000 if y < 30 else 1900) if y < 100 else y
    try:
        return date(y, int(mo), int(d))
    except ValueError:
        return None


_SUFFIX = re.compile(r"\b(inc|incorporated|corp|corporation|co|company|llc|l l c|ltd|limited|lp|llp|plc|the)\b")


def norm_name(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").casefold()
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return " ".join(_SUFFIX.sub(" ", s).split())


def name_match(a: str, b: str) -> bool:
    if "/" in b:                                      # vai trò ghép "ISO / FDMS": khớp từng phần
        return any(name_match(a, part) for part in b.split("/") if part.strip())
    a, b = norm_name(a), norm_name(b)
    if not a or not b:
        return False
    if a in b or b in a:
        return True
    ta, tb = set(a.split()), set(b.split())
    return len(ta & tb) / max(1, min(len(ta), len(tb))) >= 0.6 and len(ta & tb) >= 2


def locate(context: str, quote: str) -> tuple[int, int] | None:
    """Vị trí `quote` trong `context` (khớp không phân biệt hoa thường / khoảng trắng)."""
    tokens = unicodedata.normalize("NFC", quote or "").split()
    if not tokens:
        return None
    m = re.search(r"\s+".join(re.escape(t) for t in tokens), context, re.I)
    return (m.start(), m.end()) if m else None


def overlap(a: tuple[int, int], b: tuple[int, int]) -> float:
    inter = max(0, min(a[1], b[1]) - max(a[0], b[0]))
    return inter / max(1, min(a[1] - a[0], b[1] - b[0]))


def load_cuad(path: Path) -> list[dict]:
    out = []
    for c in json.loads(path.read_text(encoding="utf-8"))["data"]:
        par = c["paragraphs"][0]
        gold = {}
        for q in par["qas"]:
            cat = q["id"].split("__")[-1]
            if cat in CATEGORIES:
                gold[cat] = [(a["text"], a["answer_start"], a["answer_start"] + len(a["text"])) for a in q["answers"]]
        out.append({"title": c["title"], "context": par["context"], "gold": gold})
    return out


def sample(docs: list[dict], n: int, seed: int) -> list[dict]:
    """n hợp đồng, chia đều ba nhóm độ dài (ngắn / vừa / dài), hạt giống cố định."""
    ordered = sorted(docs, key=lambda d: len(d["context"]))
    k = len(ordered) // 3
    groups = [ordered[:k], ordered[k:2 * k], ordered[2 * k:]]
    rng = random.Random(seed)
    per = [n // 3 + (1 if i < n % 3 else 0) for i in range(3)]
    picked = [d for g, m in zip(groups, per) for d in rng.sample(g, m)]
    return sorted(picked, key=lambda d: d["title"])


# --- chạy -------------------------------------------------------------------------------------------

class CountingLLM:
    def __init__(self, llm):
        self.llm, self.calls, self.chars = llm, 0, 0

    def complete(self, system, user):
        self.calls += 1
        self.chars += len(system) + len(user)
        return self.llm.complete(system, user)


def run_one(doc: dict, llm_factory) -> dict:
    from rag.contracts.doc import PageText
    from rag.contracts.facts import extract_facts
    from rag.contracts.models import Contract
    from rag.contracts.structure import parse_contract, to_contract_units

    text = doc["context"]
    t0 = time.time()
    rec = {"title": doc["title"], "chars": len(text)}
    llm = CountingLLM(llm_factory())
    try:
        parsed = parse_contract([PageText(None, text)])
        c = Contract("bench", doc["title"], False, datetime.now(timezone.utc), text, to_contract_units(parsed),
                     len(parsed.top_units()), doc=parsed)
        facts = extract_facts(llm, c)
        rec |= {"units": len(c.units), "facts": {k: facts.get(k) for k in (
            "parties", "sign_date", "effective_date", "term", "type", "coverage", "warnings")}}
        rec["facts"]["sign_candidates"] = facts["candidates"].get("sign_date") or []
    except Exception as e:  # noqa: BLE001 — ghi lại, không làm hỏng cả lần chạy
        rec["error"] = f"{type(e).__name__}: {str(e)[:200]}"
    rec |= {"llm_calls": llm.calls, "prompt_chars": llm.chars, "seconds": round(time.time() - t0, 1)}
    return rec


def run(args) -> None:
    from rag.config import Settings
    from rag.generate.llm import OpenAIChatLLM

    s = Settings.load()

    def llm_factory():
        return OpenAIChatLLM(s.llm_model, temperature=s.llm_temperature, base_url=s.llm_base_url,
                             api_key=s.llm_api_key, cache=None)

    docs = sample(load_cuad(args.data), args.n, args.seed)
    out = args.out / "runs.jsonl"
    done = {json.loads(l)["title"] for l in out.read_text(encoding="utf-8").splitlines()} if out.exists() else set()
    todo = [d for d in docs if d["title"] not in done]
    print(f"model={s.llm_model} n={len(docs)} đã có={len(done)} còn={len(todo)}", flush=True)
    with ThreadPoolExecutor(max_workers=args.workers) as pool, out.open("a", encoding="utf-8") as f:
        for rec in pool.map(lambda d: run_one(d, llm_factory), todo):
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()
            print(f"{rec['title'][:60]:60} chars={rec['chars']:>7} calls={rec['llm_calls']:>3} "
                  f"{rec['seconds']:>6}s {rec.get('error', '')}", flush=True)
    (args.out / "meta.json").write_text(json.dumps({
        "model": s.llm_model, "temperature": s.llm_temperature, "seed": args.seed, "n": args.n,
        "dataset": "CUAD_v1 (aok_v1.0)", "at": datetime.now(timezone.utc).isoformat()}, indent=1), encoding="utf-8")


# --- chấm -------------------------------------------------------------------------------------------

def _prf(tp: int, fp: int, fn: int) -> dict:
    p, r = tp / max(1, tp + fp), tp / max(1, tp + fn)
    return {"precision": round(p, 3), "recall": round(r, 3), "f1": round(2 * p * r / max(1e-9, p + r), 3),
            "tp": tp, "fp": fp, "fn": fn}


def score(args) -> dict:
    gold_by = {d["title"]: d for d in load_cuad(args.data)}
    recs = [json.loads(l) for l in (args.out / "runs.jsonl").read_text(encoding="utf-8").splitlines()]
    ok = [r for r in recs if "error" not in r]
    res: dict = {"contracts": len(recs), "failed": [{"title": r["title"], "error": r["error"]} for r in recs if "error" in r]}

    ptp = pfp = pfn = ntp = nfn = 0
    dup = total_parties = 0
    sign_extra = {"single_candidate": 0, "conflicts": 0, "in_candidates": 0, "in_sign_or_effective": 0}
    per_doc = []
    cats = {c: {"n": 0, "gold_present": 0, "ours_present": 0, "correct": 0, "gold_parsable": 0, "fp_on_absent": 0,
                "absent": 0, "span_hit": 0, "span_located": 0} for c in ("sign_date", "effective_date", "term")}
    for r in ok:
        doc, facts = gold_by[r["title"]], r["facts"]
        ctx = doc["context"]
        gold = doc["gold"]
        # Parties
        golds = list(dict.fromkeys(t.strip() for t, _, _ in gold.get("Parties", []) if t.strip()))
        # tên gọi tắt hệ thống trích (aliases) được coi như một phần của vai trò khi so với đáp án
        ours = [(p.get("name") or "", " / ".join([p.get("role") or "", *(p.get("aliases") or [])]))
                for p in facts.get("parties") or []]
        tp_g = sum(any(name_match(g, n) or name_match(g, rl) for n, rl in ours) for g in golds)
        tp_o = sum(any(name_match(g, n) or name_match(g, rl) for g in golds) for n, rl in ours)
        ptp += tp_g
        pfn += len(golds) - tp_g
        pfp += len(ours) - tp_o
        named = [g for g in golds if not _DEFINITIONAL.search(g) and g.casefold().strip(" .,") not in _GENERIC
                 and norm_name(g) not in _GENERIC and not g.casefold().startswith("the ")]
        hit_n = sum(any(name_match(g, n) or name_match(g, rl) for n, rl in ours) for g in named)
        ntp += hit_n
        nfn += len(named) - hit_n
        keys = [norm_name(n) for n, _ in ours if norm_name(n)]
        dup += len(keys) - len(set(keys))
        total_parties += len(ours)
        # ngày ký: ứng viên, mâu thuẫn, và khớp ở ô ngày ký hoặc ô ngày hiệu lực
        gdates = set().union(set(), *(dates_in(t) for t, _, _ in gold.get("Agreement Date", [])))
        cand = facts.get("sign_candidates")
        if cand is None:                                  # lần chạy cũ: chỉ có một giá trị
            cand = [facts["sign_date"]] if facts.get("sign_date") else []
        cvals = set()
        for x in cand:
            try:
                cvals.add(date.fromisoformat(str(x.get("value"))[:10]))
            except ValueError:
                pass
        sign_extra["single_candidate"] += len(cvals) == 1
        sign_extra["conflicts"] += len(cvals) > 1
        if gdates:
            sign_extra["in_candidates"] += bool(cvals & gdates)
            evals = set(cvals)
            try:
                evals.add(date.fromisoformat(str((facts.get("effective_date") or {}).get("value"))[:10]))
            except ValueError:
                pass
            sign_extra["in_sign_or_effective"] += bool(evals & gdates)
        per_doc.append({"title": r["title"], "gold": golds, "ours": [f"{n} / {rl}" for n, rl in ours]})
        # ngày + thời hạn
        for key, gcats in (("sign_date", ("Agreement Date",)), ("effective_date", ("Effective Date",)),
                           ("term", ("Expiration Date", "Renewal Term"))):
            c = cats[key]
            spans = [(s, e) for cat in gcats for _, s, e in gold.get(cat, [])]
            gtexts = [t for cat in gcats for t, _, _ in gold.get(cat, [])]
            item = facts.get(key)
            c["n"] += 1
            if not spans:
                c["absent"] += 1
                c["fp_on_absent"] += bool(item)
            else:
                c["gold_present"] += 1
            if item:
                c["ours_present"] += 1
                loc = locate(ctx, item.get("quote") or "")
                c["span_located"] += bool(loc)
                if spans and loc and any(overlap(loc, sp) >= 0.5 for sp in spans):
                    c["span_hit"] += 1
            if key != "term" and spans:
                gd = set().union(*(dates_in(t) for t in gtexts))
                if gd:
                    c["gold_parsable"] += 1
                    single = key != "sign_date" or len(facts.get("sign_candidates") or [item]) == 1
                    if item and item.get("value") and single:
                        try:
                            c["correct"] += date.fromisoformat(str(item["value"])[:10]) in gd
                        except ValueError:
                            pass
    res["parties"] = _prf(ptp, pfp, pfn)
    res["parties_named"] = {"recall": round(ntp / max(1, ntp + nfn), 3), "tp": ntp, "fn": nfn}
    res["party_duplicates"] = {"duplicates": dup, "entries": total_parties, "rate": round(dup / max(1, total_parties), 3)}
    res["sign_date_extra"] = sign_extra
    res["fields"] = cats
    res["avg_units"] = round(sum(r["units"] for r in ok) / max(1, len(ok)), 1)
    res["llm_calls"] = sum(r["llm_calls"] for r in recs)
    res["prompt_chars"] = sum(r["prompt_chars"] for r in recs)
    res["seconds"] = round(sum(r["seconds"] for r in recs), 1)
    res["coverage_full"] = sum(1 for r in ok if r["facts"]["coverage"]["read"] == r["facts"]["coverage"]["total"])
    res["with_warnings"] = [{"title": r["title"], "warnings": r["facts"]["warnings"]} for r in ok if r["facts"]["warnings"]]
    (args.out / "scores.json").write_text(json.dumps(res | {"per_doc_parties": per_doc}, indent=1, ensure_ascii=False),
                                          encoding="utf-8")
    return res


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--seed", type=int, default=20261113)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--score-only", action="store_true")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    if not args.score_only:
        run(args)
    print(json.dumps(score(args), indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
