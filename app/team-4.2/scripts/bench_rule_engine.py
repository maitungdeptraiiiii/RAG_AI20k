"""K2: benchmark rule engine `reference` vs `network`, 6 kịch bản × 2 trục (spec 2026-11-22-rete-rule-engine-design §9).

Chạy từ app/team-4.2 (không chạy việc nặng khác cùng lúc):
    .venv/Scripts/python.exe scripts/bench_rule_engine.py --seed 0
Ra reports/week-04/team-4.2/bench/<thời điểm>.json + summary.md + axis1.png + axis2.png.
`--quick`: cấu hình nhỏ (cho test). Hai evaluator lệch -> in ca lỗi, ghi phần đã đo, thoát mã 2 (không bỏ qua).
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import os
import platform
import sys
import tempfile
from datetime import datetime
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
REPO = APP.parents[1]
if str(APP / "src") not in sys.path:
    sys.path.insert(0, str(APP / "src"))

from rag.rules.bench.runner import Row, run_axis1, run_axis2  # noqa: E402
from rag.rules.bench.synth import AXIS1_SIZES, AXIS2_RULES, AXIS2_SIZES, REAL_AXIS1, ObjSpec, RuleSpec  # noqa: E402

SCENARIOS = {1: "Biên dịch mạng (evaluator_for)", 2: "Lần đánh giá đầu của một hợp đồng",
             3: "Cập nhật tăng dần 1 / 5 / 20 dữ kiện", 4: "100 hồ sơ dùng chung một evaluator (trung vị mỗi hồ sơ)",
             5: "next_questions() trên hợp đồng nhiều UNKNOWN", 6: "Thêm / xóa / đổi một đối tượng trong hồ sơ"}


def _ram_gb() -> str:
    try:
        if os.name == "nt":
            import ctypes

            class MS(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("sullAvailExtendedVirtual", ctypes.c_ulonglong)]
            m = MS()
            m.dwLength = ctypes.sizeof(MS)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
            return f"{m.ullTotalPhys / 2**30:.1f} GB"
        return f"{os.sysconf('SC_PAGE_SIZE') * os.sysconf('SC_PHYS_PAGES') / 2**30:.1f} GB"
    except Exception:  # noqa: BLE001
        return "không đo được"


def machine() -> dict:
    return {"CPU": platform.processor() or platform.machine(), "cores": os.cpu_count(), "RAM": _ram_gb(),
            "Python": platform.python_version(), "OS": platform.platform()}


def configs(quick: bool, seed: int) -> tuple[list, list[ObjSpec]]:
    if quick:
        return [REAL_AXIS1["labor"], RuleSpec(500, 0.5, 3, 50, seed)], [ObjSpec(n, 5, seed) for n in (1, 5)]
    axis1 = [REAL_AXIS1["labor"], REAL_AXIS1["ba_mien"]]
    axis1 += [RuleSpec(n, s, d, 500 if n >= 10000 else 50, seed) for n in AXIS1_SIZES for s in (0.2, 0.5) for d in (0, 3)]
    return axis1, [ObjSpec(n, r, seed) for r in AXIS2_RULES for n in AXIS2_SIZES]


def _rules_of(row: Row) -> int | None:
    for part in row.note.split(";"):
        if part.strip().endswith("rule"):
            return int(part.split()[-2])
    return None


def render_summary(rows: list[Row], mach: dict, params: dict, error: str | None = None) -> str:
    out = ["# Benchmark rule engine: reference vs network (K2)", "",
           f"Sinh bằng `app/team-4.2/scripts/bench_rule_engine.py` lúc {params['started']}. Tham số: seed {params['seed']}, "
           f"{params['repeats']} lần lặp (bỏ 1 lần khởi động){', chế độ --quick' if params['quick'] else ''}.", "",
           "Máy: " + ", ".join(f"{k} {v}" for k, v in mach.items()), "",
           "Thời gian: trung vị / p95, mili giây. `net/ref` < 1 nghĩa là network nhanh hơn. Bộ nhớ đỉnh: KB (tracemalloc). "
           "`tính lại`: số node (trục 1) / đối tượng (trục 2) network tính lại, trung vị.", ""]
    if error:
        out += ["## LỖI — chạy dừng giữa chừng; bảng dưới chỉ gồm phần đã đo (EvaluatorMismatch: báo Tùng)", "",
                "```", error, "```", ""]
    for axis, name in ((1, "Trục 1 — số rule"), (2, "Trục 2 — số đối tượng mỗi hồ sơ")):
        out += [f"## {name}", ""]
        for sc in (1, 2, 3, 4, 5, 6):
            sel = [r for r in rows if r.axis == axis and r.scenario == sc]
            if axis == 1 and sc == 6 or axis == 2 and sc not in (2, 6):
                continue
            out += [f"### Kịch bản {sc} — {SCENARIOS[sc]}", ""]
            if not sel:
                out += ["(chưa đo)", ""]
                continue
            out += ["| cấu hình | reference | network | net/ref | bộ nhớ ref / net | tính lại | ghi chú |",
                    "|---|---|---|---|---|---|---|"]
            for size in dict.fromkeys(r.size for r in sel):
                ref = next(r for r in sel if r.size == size and r.evaluator == "reference")
                net = next(r for r in sel if r.size == size and r.evaluator == "network")
                ratio = f"{net.median_ms / ref.median_ms:.2f}" if ref.median_ms else "—"
                out.append(f"| {size} | {ref.median_ms:.3f} / {ref.p95_ms:.3f} | {net.median_ms:.3f} / {net.p95_ms:.3f} | "
                           f"{ratio} | {ref.peak_kb:.0f} / {net.peak_kb:.0f} | "
                           f"{'—' if net.recomputed is None else net.recomputed} | {net.note or ref.note} |")
            out.append("")
    out += ["## Nhận xét", "", "(điền sau khi đọc số; ghi đúng như số, kể cả khi network chậm hơn)", ""]
    return "\n".join(out)


def plot(rows: list[Row], out_dir: Path) -> list[Path]:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("cảnh báo: chưa cài matplotlib (uv pip install matplotlib) — bỏ qua biểu đồ", file=sys.stderr)
        return []
    paths = []
    # trục 1: x = số rule; cấu hình tổng hợp chung 0.5 / sâu 3 + gói thật; kịch bản 3 lấy u5
    counts = {r.size: _rules_of(r) for r in rows if r.axis == 1 and r.scenario == 1}
    keep = {s for s in counts if "_s50_d3_" in s or not s.startswith("r")}
    fig, axes = plt.subplots(1, 5, figsize=(22, 4.5))
    for ax, sc in zip(axes, (1, 2, 3, 4, 5)):
        for ev, style in (("reference", "o-"), ("network", "s--")):
            pts = sorted((counts[r.size.split("/")[0]], r.median_ms) for r in rows
                         if r.axis == 1 and r.scenario == sc and r.evaluator == ev and r.size.split("/")[0] in keep
                         and (sc != 3 or r.size.endswith("/u5")) and counts.get(r.size.split("/")[0]))
            if pts:
                ax.plot(*zip(*pts), style, label=ev)
        ax.set(xscale="log", yscale="log", title=f"KB {sc}" + (" (u5)" if sc == 3 else ""), xlabel="số rule",
               ylabel="ms (trung vị)")
        ax.legend()
    fig.suptitle("Trục 1 — thời gian theo số rule (điểm trái: gói thật labor / ba miền; còn lại: gói tổng hợp chung 0.5, sâu 3). Giá trị 0 ms không vẽ được trên trục log")
    fig.tight_layout()
    paths.append(out_dir / "axis1.png")
    fig.savefig(paths[-1], dpi=110)
    plt.close(fig)
    # trục 2: x = số đối tượng; một đường mỗi (evaluator, số rule)
    panels = [("2", None), ("6", "add"), ("6", "remove"), ("6", "modify")]
    fig, axes = plt.subplots(1, 4, figsize=(18, 4.5))
    for ax, (sc, change) in zip(axes, panels):
        sel = [r for r in rows if r.axis == 2 and r.scenario == int(sc) and (change is None or r.size.endswith("/" + change))]
        for ev, style in (("reference", "o-"), ("network", "s--")):
            for nr in sorted({int(r.size.split("_r")[1].split("/")[0]) for r in sel}):
                pts = sorted((int(r.size[1:].split("_")[0]), r.median_ms) for r in sel
                             if r.evaluator == ev and int(r.size.split("_r")[1].split("/")[0]) == nr)
                if pts:
                    ax.plot(*zip(*pts), style, label=f"{ev}, {nr} rule")
        ax.set(xscale="log", yscale="log", title=f"KB {sc}" + (f" ({change})" if change else ""), xlabel="số đối tượng",
               ylabel="ms (trung vị)")
        ax.legend(fontsize=7)
    fig.suptitle("Trục 2 — thời gian theo số đối tượng mỗi hồ sơ")
    fig.tight_layout()
    paths.append(out_dir / "axis2.png")
    fig.savefig(paths[-1], dpi=110)
    plt.close(fig)
    return paths


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--repeats", type=int, default=20)
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--out", type=Path, default=REPO / "reports" / "week-04" / "team-4.2" / "bench")
    args = ap.parse_args(argv)
    repeats = 3 if args.quick else max(20, args.repeats)
    started = datetime.now()
    params = {"seed": args.seed, "repeats": repeats, "quick": args.quick, "started": started.isoformat(timespec="seconds")}
    axis1, axis2 = configs(args.quick, args.seed)
    rows: list[Row] = []
    error = None
    with tempfile.TemporaryDirectory() as tmp:
        try:
            for spec in axis1:
                print(f"trục 1: {spec}", flush=True)
                run_axis1(spec, seed=args.seed, repeats=repeats, root=Path(tmp), sink=rows)
            for spec in axis2:
                print(f"trục 2: {spec}", flush=True)
                run_axis2(spec, seed=args.seed, repeats=repeats, root=Path(tmp), sink=rows)
        except Exception as e:  # noqa: BLE001 — mọi lỗi: vẫn ghi phần đã đo, báo lỗi, thoát mã 2
            error = f"{type(e).__name__}: {e}"
            print(f"LỖI: {error}", file=sys.stderr)
    args.out.mkdir(parents=True, exist_ok=True)
    mach = machine()
    stamp = started.strftime("%Y%m%d-%H%M%S")
    (args.out / f"{stamp}.json").write_text(json.dumps({"params": params, "machine": mach, "error": error,
                                                        "rows": [dataclasses.asdict(r) for r in rows]},
                                                       ensure_ascii=False, indent=1), encoding="utf-8")
    (args.out / "summary.md").write_text(render_summary(rows, mach, params, error), encoding="utf-8")
    plot(rows, args.out)
    print(f"{len(rows)} dòng -> {args.out}")
    return 2 if error else 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
