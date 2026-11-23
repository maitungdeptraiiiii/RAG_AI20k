"""K2: đo 6 kịch bản benchmark (spec 2026-11-22-rete-rule-engine-design §9) cho `reference` và `network`.

1 biên dịch (`evaluator_for`) · 2 lần đánh giá đầu · 3 cập nhật tăng dần 1/5/20 dữ kiện · 4 100 hồ sơ dùng chung một
evaluator · 5 `next_questions` trên hợp đồng nhiều UNKNOWN · 6 thêm / xóa / đổi một đối tượng (trục 2).

Trung vị + p95 trên `repeats` lần (bỏ `warmup` lần khởi động); bộ nhớ đỉnh đo riêng một lần bằng `tracemalloc`.
Mỗi kịch bản so kết quả hai evaluator trên cùng đầu vào (qua `_canon`); lệch -> `EvaluatorMismatch` kèm seed + đầu vào.
Gói thật (`REAL_AXIS1`): đầu vào lấy từ hồ sơ mẫu của các gói đó (`bench.cases`), không sinh ngẫu nhiên.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import random
import statistics
import time
import tracemalloc
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable, Sequence

from rag.rules.bench.cases import load_cases
from rag.rules.bench.synth import (ObjSpec, RuleSpec, load_object_pack, load_rule_pack, object_changes, present_all,
                                   random_facts, random_objects, update_batches)
from rag.rules.evaluator import evaluator_for
from rag.rules.loader import load_packs
from rag.rules.questions import next_questions

KINDS = ("reference", "network")
UPDATE_SIZES = (1, 5, 20)
N_DOSSIERS = 100
DAY = date(2025, 1, 1)


@dataclass(frozen=True)
class Timing:
    median_ms: float
    p95_ms: float
    runs: int


@dataclass(frozen=True)
class Row:
    scenario: int
    axis: int
    size: str
    evaluator: str
    median_ms: float
    p95_ms: float
    peak_kb: float
    recomputed: int | None
    digest: str
    note: str = ""


class EvaluatorMismatch(Exception):
    """`reference` và `network` ra kết quả khác nhau trên cùng đầu vào: lỗi engine, báo Tùng (không bỏ qua)."""


class DegenerateScenario(Exception):
    """Kịch bản ra đầu ra rỗng ở mọi bước (không kết quả / không câu hỏi / không thay đổi nào): số đo vô nghĩa và phép so
    hai evaluator đúng một cách tầm thường — dừng thay vì in số."""


def measure(fn: Callable[[], object], *, repeats: int = 20, warmup: int = 1) -> Timing:
    for _ in range(warmup):
        fn()
    times = []
    for _ in range(repeats):
        t = time.perf_counter()
        fn()
        times.append((time.perf_counter() - t) * 1000)
    times.sort()
    p95 = times[min(len(times) - 1, max(0, round(0.95 * len(times)) - 1))]
    return Timing(statistics.median(times), p95, len(times))


def peak_kb(fn: Callable[[], object]) -> float:
    tracemalloc.start()
    try:
        fn()
        return tracemalloc.get_traced_memory()[1] / 1024
    finally:
        tracemalloc.stop()


def _canon(results, kind: str = "") -> str:
    """Dạng so sánh duy nhất của kết quả / Diff / câu hỏi (kind chỉ để test ép lệch)."""
    items = results.changes if hasattr(results, "changes") else results
    return json.dumps([dataclasses.asdict(x) for x in items], default=str, sort_keys=True, ensure_ascii=False)


def _digest(parts: Sequence[str]) -> str:
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()[:16]


@dataclass
class _Input:
    day: date
    facts: dict
    present: set
    objects: tuple = ()


def _session(ev, inp: _Input):
    return ev.session(day=inp.day, facts=dict(inp.facts), present=set(inp.present), evidence={}, objects=inp.objects)


def _check(outs: dict[str, list[str]], scenario: int, size: str, seed: int, detail: str) -> str:
    if outs["reference"] != outs["network"]:
        i = next(k for k, (a, b) in enumerate(zip(outs["reference"], outs["network"])) if a != b) \
            if len(outs["reference"]) == len(outs["network"]) else -1
        raise EvaluatorMismatch(f"kịch bản {scenario}, {size}, seed {seed}, bước {i}: reference và network khác nhau. "
                                f"Đầu vào: {detail[:2000]}")
    if all(o == "[]" for o in outs["reference"]):
        raise DegenerateScenario(f"kịch bản {scenario}, {size}, seed {seed}: cả hai evaluator ra rỗng ở mọi bước")
    return _digest(outs["reference"])


def _row(scenario, axis, size, kind, t: Timing, peak, recomputed, digest, note="") -> Row:
    return Row(scenario, axis, size, kind, round(t.median_ms, 3), round(t.p95_ms, 3), round(peak, 1), recomputed, digest, note)


def _median_stat(values: list[int]) -> int | None:
    return int(statistics.median(values)) if values else None


# ───────────────────────────── trục 1 ─────────────────────────────

def _real_inputs(packs: list[str], seed: int):
    """Đầu vào thật: các ca hồ sơ mẫu có gói nằm trong `packs` (gộp)."""
    cases = [c for c in load_cases()[0] if set(c.packs) <= set(packs)]
    if not cases:
        raise ValueError(f"không có hồ sơ mẫu cho gói {packs}")
    cases.sort(key=lambda c: (-len(c.facts), c.case_id))
    inputs = [_Input(c.day, dict(c.facts), set(c.present), c.objects) for c in cases]
    return inputs[0], [inputs[i % len(inputs)] for i in range(N_DOSSIERS)]


def _real_updates(base: _Input, n: int, count: int, rng: random.Random) -> list[dict]:
    """Lô cập nhật trên dữ kiện thật của hồ sơ: lần lượt xóa rồi trả lại `n` dữ kiện (ít dữ kiện hơn n thì lấy hết)."""
    names = sorted(base.facts)
    out = []
    for i in range(count):
        if i % 2 == 0:
            pick = rng.sample(names, min(n, len(names)))
            out.append({k: None for k in pick})
        else:
            out.append({k: base.facts[k] for k in pick})
    return out


def run_axis1(spec: RuleSpec | list[str], *, seed: int, repeats: int, root: Path, sink: list | None = None) -> list[Row]:
    """`sink`: danh sách nhận từng dòng ngay khi đo xong (lỗi giữa chừng vẫn giữ các dòng đã đo)."""
    rng = random.Random(seed)
    t0 = time.perf_counter()
    if isinstance(spec, RuleSpec):
        cat = load_rule_pack(spec, root)
        load_s = time.perf_counter() - t0
        label = f"r{spec.n_rules}_s{round(spec.shared_ratio * 100)}_d{spec.depth}_f{spec.n_facts}"
        present = present_all(cat)
        base = _Input(DAY, random_facts(cat, spec, rng, missing=0.2), present)
        dossiers = [_Input(DAY, random_facts(cat, spec, rng, missing=0.2), present) for _ in range(N_DOSSIERS)]
        updates = {n: update_batches(cat, spec, rng, n, repeats + 1) for n in UPDATE_SIZES}
        unknown = _Input(DAY, random_facts(cat, spec, rng, missing=0.7), present)
    else:
        cat = load_packs(spec)
        load_s = time.perf_counter() - t0
        label = "+".join(spec) if len(spec) == 1 else "ba_mien"
        base, dossiers = _real_inputs(spec, seed)
        updates = {n: _real_updates(base, n, repeats + 1, rng) for n in UPDATE_SIZES}
        names = sorted(base.facts)
        drop = set(rng.sample(names, round(0.7 * len(names))))
        unknown = _Input(base.day, {k: v for k, v in base.facts.items() if k not in drop}, base.present, base.objects)
    load_note = f"nạp YAML {load_s:.1f} s; {sum(len(c.rules) for c in cat.concepts.values())} rule"
    rows: list[Row] = sink if sink is not None else []

    # 1. biên dịch
    for kind in KINDS:
        t = measure(lambda: evaluator_for(cat, kind), repeats=repeats)
        rows.append(_row(1, 1, label, kind, t, peak_kb(lambda: evaluator_for(cat, kind)), None, "", load_note))
    evs = {k: evaluator_for(cat, k) for k in KINDS}

    # 2. lần đánh giá đầu
    outs, timing, stats = {}, {}, {}
    for kind, ev in evs.items():
        outs[kind] = [_canon(_session(ev, base).results(), kind)]
        timing[kind] = measure(lambda: _session(ev, base).results(), repeats=repeats)
        s = _session(ev, base)
        stats[kind] = s.stats.get("nodes_recomputed") if hasattr(s, "stats") else None
    d = _check(outs, 2, label, seed, repr(base.facts))
    rows += [_row(2, 1, label, k, timing[k], peak_kb(lambda: _session(evs[k], base).results()), stats[k], d) for k in KINDS]

    # 3. cập nhật tăng dần
    for n in UPDATE_SIZES:
        batches = updates[n]
        outs, timing, rec, peaks = {}, {}, {}, {}
        for kind, ev in evs.items():
            s, it, seen, recs = _session(ev, base), iter(batches), [], []

            def step():
                diff = s.update(next(it))
                seen.append(_canon(diff, kind))
                if hasattr(s, "stats"):
                    recs.append(s.stats.get("nodes_recomputed", 0))
            timing[kind] = measure(step, repeats=len(batches) - 1)
            outs[kind], rec[kind] = seen, _median_stat(recs)
            probe = _session(ev, base)
            peaks[kind] = peak_kb(lambda: probe.update(batches[0]))
        d = _check(outs, 3, f"{label}/u{n}", seed, repr(batches))
        rows += [_row(3, 1, f"{label}/u{n}", k, timing[k], peaks[k], rec[k], d) for k in KINDS]

    # 4. 100 hồ sơ dùng chung một evaluator (mỗi lần lặp một hồ sơ)
    outs, timing = {}, {}
    for kind, ev in evs.items():
        it, seen = iter(dossiers + dossiers[:1]), []
        timing[kind] = measure(lambda: seen.append(_canon(_session(ev, next(it)).results(), kind)),
                               repeats=len(dossiers))
        outs[kind] = seen
    d = _check(outs, 4, label, seed, "100 hồ sơ")
    rows += [_row(4, 1, label, k, timing[k], peak_kb(lambda: [_session(evs[k], x).results() for x in dossiers[:10]]),
                  None, d, f"trung vị mỗi hồ sơ, {len(dossiers)} hồ sơ; bộ nhớ đo trên 10 hồ sơ") for k in KINDS]

    # 5. next_questions trên hợp đồng nhiều UNKNOWN
    outs, timing = {}, {}
    for kind, ev in evs.items():
        s = _session(ev, unknown)
        outs[kind] = [_canon(next_questions(cat, s), kind)]
        timing[kind] = measure(lambda: next_questions(cat, s), repeats=repeats)
    d = _check(outs, 5, label, seed, repr(unknown.facts))
    rows += [_row(5, 1, label, k, timing[k], peak_kb(lambda: next_questions(cat, _session(evs[k], unknown))), None, d)
             for k in KINDS]
    return rows


# ───────────────────────────── trục 2 ─────────────────────────────

def _apply(objects: list, ch) -> list:
    gone = set(ch.removed) | {o.id for o in ch.changed}
    return [o for o in objects if o.id not in gone] + list(ch.changed) + list(ch.added)


def run_axis2(spec: ObjSpec, *, seed: int, repeats: int, root: Path, sink: list | None = None) -> list[Row]:
    rng = random.Random(seed)
    cat = load_object_pack(spec, root)
    objs = tuple(random_objects(spec, rng))
    base = _Input(DAY, {}, set(), objs)
    label = f"o{spec.n_objects}_r{spec.n_cross_rules}"
    evs = {k: evaluator_for(cat, k) for k in KINDS}
    rows: list[Row] = sink if sink is not None else []

    outs, timing, stats = {}, {}, {}
    for kind, ev in evs.items():
        outs[kind] = [_canon(_session(ev, base).results(), kind)]
        timing[kind] = measure(lambda: _session(ev, base).results(), repeats=repeats)
        stats[kind] = _session(ev, base).stats.get("objects_recomputed") if kind == "network" else None
    d = _check(outs, 2, label, seed, repr(objs))
    rows += [_row(2, 2, label, k, timing[k], peak_kb(lambda: _session(evs[k], base).results()), stats[k], d) for k in KINDS]

    for change in ("add", "remove", "modify"):
        seq, cur, crng, fallback = [], list(objs), random.Random(seed * 1000 + len(change)), 0
        for i in range(repeats + 1):        # thay đổi nối tiếp trên trạng thái đang chạy; hồ sơ còn 1 đối tượng thì thêm
            kind_i = change if not (change == "remove" and len(cur) <= 1) else "add"
            fallback += kind_i != change
            ch = object_changes(cur, crng, kind_i)
            seq.append(ch)
            cur = _apply(cur, ch)
        outs, timing, rec, peaks = {}, {}, {}, {}
        for kind, ev in evs.items():
            s, it, seen, recs = _session(ev, base), iter(seq), [], []

            def step():
                diff = s.update({}, objects=next(it))
                seen.append(_canon(diff, kind))
                if hasattr(s, "stats"):
                    recs.append(s.stats.get("objects_recomputed", 0))
            timing[kind] = measure(step, repeats=len(seq) - 1)
            outs[kind], rec[kind] = seen, _median_stat(recs)
            probe = _session(ev, base)
            peaks[kind] = peak_kb(lambda: probe.update({}, objects=seq[0]))
        d = _check(outs, 6, f"{label}/{change}", seed, repr(seq[:3]))
        note = f"{fallback}/{len(seq)} bước xóa đổi thành thêm (hồ sơ còn 1 đối tượng)" if fallback else ""
        rows += [_row(6, 2, f"{label}/{change}", k, timing[k], peaks[k], rec[k], d, note) for k in KINDS]
    return rows


__all__ = ["DegenerateScenario", "EvaluatorMismatch", "Row", "Timing", "measure", "peak_kb", "run_axis1", "run_axis2"]
