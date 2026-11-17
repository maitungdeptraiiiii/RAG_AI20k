"""Bảng dữ kiện cho rule engine đọc từ đồ thị hợp đồng (spec 2026-11-16-contract-graph-agent §5.5, §7).

Dữ kiện cấp hợp đồng = nút `ContractFact`. Giá trị B sửa giá trị A khi có cạnh `AMENDS x→y` với điều khoản cấp cao
nhất của x là của B và của y là của A. Giá trị tại ngày soát = giá trị gốc, thay bởi sửa đổi mới nhất có ngày hiệu
lực ≤ ngày soát; sửa đổi sau ngày soát đi vào `later_amendments`. Hai giá trị gốc khác nhau -> CONFLICT."""
from __future__ import annotations

import dataclasses
from datetime import date

from rag.bridge.engine import CONFLICT, Fact, Facts
from rag.bridge.facts_map import FactSet, _merge
from rag.contracts.graph.view import ContractGraphView

NO_DATE = "không rõ ngày hiệu lực của sửa đổi"


class _Tops:
    def __init__(self, view: ContractGraphView):
        self.view, self.cache = view, {}

    def __call__(self, node_id: str) -> str:
        if node_id not in self.cache:
            up = self.view.neighbors(node_id, rel_types=["CHILD_OF"], direction="out")
            self.cache[node_id] = self(up[0]["node"]["node_id"]) if up else node_id
        return self.cache[node_id]


def _evidence_unit(view: ContractGraphView, fact_id: str) -> dict | None:
    hops = view.neighbors(fact_id, rel_types=["EVIDENCE"], direction="out")
    return hops[0]["node"] if hops else None


def _old(f: Fact) -> dict:
    return {"value": f.value, "unit": f.unit, "uid": f.uid}


def _contract_level(view: ContractGraphView, day: date, sign_date: date | None, warnings: list[str]) -> Facts:
    top = _Tops(view)
    # sửa đổi: điều khoản cấp cao nhất nguồn -> {điều khoản đích: ngày hiệu lực}
    amends: dict[str, dict[str, date | None]] = {}
    for u in view.find("Unit"):
        for h in view.neighbors(u["node_id"], rel_types=["AMENDS"], direction="out"):
            vf = h["props"].get("valid_from")
            amends.setdefault(top(u["node_id"]), {})[top(h["node"]["node_id"])] = date.fromisoformat(vf) if vf else None
    by_name: dict[str, list[tuple[Fact, str]]] = {}
    for n in view.find("ContractFact"):
        unit = _evidence_unit(view, n["node_id"])
        uid = unit.get("uid") if unit else None
        f = Fact(n.get("value"), n.get("unit"), "contract", uid, n.get("quote"))
        group = by_name.setdefault(n["name"], [])
        if not any((g.value, g.unit) == (f.value, f.unit) for g, _ in group):
            group.append((f, top(unit["node_id"]) if unit else ""))
    out: Facts = {}
    for name, group in sorted(by_name.items()):
        originals, changes = [], []          # changes: (ngày hiệu lực, Fact)
        hosts = {t for _, t in group}
        for f, t in group:
            if t not in amends:
                originals.append(f)
                continue
            targets = amends[t]              # ưu tiên đích đang mang một giá trị của dữ kiện này
            dst = next((d for d in sorted(targets) if d in hosts), sorted(targets)[0])
            changes.append((targets[dst], f))
        dated = []
        for vf, f in changes:
            if vf is None:
                warnings.append(f"{name}: {NO_DATE} [{f.uid}]")
                vf = sign_date or date.min
            dated.append((vf, f))
        dated.sort(key=lambda x: (x[0], x[1].uid or ""))
        if len(originals) > 1:
            out[name] = CONFLICT
            continue
        live = [(vf, f) for vf, f in dated if vf <= day]
        later = tuple({**_old(f), "valid_from": vf.isoformat()} for vf, f in dated if vf > day)
        if live:
            if sum(1 for vf, _ in live if vf == live[-1][0]) > 1:      # hai sửa đổi cùng ngày, khác giá trị
                out[name] = CONFLICT
                continue
            current = live[-1][1]
            replaced = tuple(_old(f) for f in originals) + tuple(_old(f) for _, f in live[:-1])
            out[name] = dataclasses.replace(current, amended_from=replaced, later_amendments=later)
        elif originals:
            out[name] = dataclasses.replace(originals[0], later_amendments=later)
        elif later:
            warnings.append(f"{name}: chỉ có giá trị từ {later[0]['valid_from']}, chưa hiệu lực tại {day.isoformat()}")
    if sign_date is not None:
        out["sign_date"] = Fact(sign_date, None, "contract")
    return out


def factset_from_graph(view: ContractGraphView, *, day: date, sign_date: date | None) -> tuple[FactSet, list[str]]:
    warnings: list[str] = []
    out = _contract_level(view, day, sign_date, warnings)
    present: set[str] = set()
    evidence: dict[str, list[dict]] = {}
    for ci in view.find("ConceptInstance"):
        cid = ci["concept_id"]
        present.add(cid)
        about = view.neighbors(ci["node_id"], rel_types=["ABOUT"], direction="out")
        uid = about[0]["node"].get("uid") if about else None
        quote = ci.get("quote") or None
        evidence.setdefault(cid, []).append({"uid": uid, "quote": quote, "op_id": ci.get("op_id")})
        for key in sorted(ci):
            if key.startswith("slot_") and not key.endswith("_unit"):
                _merge(out, key[5:], Fact(ci[key], ci.get(f"{key}_unit"), "concept", uid, quote))
    contract = view.node(view.contract_id) or {}
    absent = frozenset(contract.get("absent_checked") or ()) - present
    return FactSet(out, frozenset(present), evidence, absent), warnings


__all__ = ["NO_DATE", "factset_from_graph"]
