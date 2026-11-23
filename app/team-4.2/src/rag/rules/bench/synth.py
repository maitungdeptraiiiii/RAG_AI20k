"""K2: sinh gói rule tổng hợp cho benchmark (spec 2026-11-22-rete-rule-engine-design §9).

Gói được GHI ra YAML theo định dạng `packs/<id>/pack.yaml` + `concepts.yaml` (packs/README.md) rồi nạp bằng
`rag.rules.loader.load_packs(..., root=...)` — không dựng `Rule` bằng tay. Mọi ngẫu nhiên đi qua `random.Random(seed)`
riêng; YAML ghi theo thứ tự cố định, nên cùng tham số cho cùng tệp.

Trục 1 (số rule): `n_facts` dữ kiện số `f0..` (user_facts, 0–100); mỗi rule một khái niệm, `check: f_k <= v`.
Tỉ lệ `shared_ratio` rule dùng `applicability` lấy từ một nhóm nhỏ điều kiện chung (mạng dùng chung node), phần còn lại
có điều kiện riêng. `depth > 0`: chuỗi dữ kiện suy ra d1..d{depth} (d1 từ f0, d{i+1} từ d{i}); điều kiện chung đọc d{depth}.
Trục 2 (số đối tượng mỗi hồ sơ): xem `ObjSpec`.
"""
from __future__ import annotations

import random
import shutil
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Literal

import yaml

from rag.rules.loader import PACKS_ROOT, load_packs
from rag.rules.model import Catalog
from rag.rules.objects import ObjectChanges, WorkingObject
from rag.rules.semantics import Fact

REAL_AXIS1: dict[str, list[str]] = {"labor": ["labor"], "ba_mien": ["labor", "civil_loan", "civil_lease"]}
AXIS1_SIZES = (500, 2000, 10000)
AXIS2_SIZES = (1, 5, 20, 100)
AXIS2_RULES = (5, 50)
_ROLES = [{"id": "A", "label": "Bên A"}, {"id": "B", "label": "Bên B"}]
_OUTCOME = {"legality": "illegal", "party_impact": "unfavorable"}


@dataclass(frozen=True)
class RuleSpec:
    n_rules: int
    shared_ratio: float
    depth: int
    n_facts: int
    seed: int

    @property
    def pack_id(self) -> str:
        return f"synth_r{self.n_rules}_s{round(self.shared_ratio * 100)}_d{self.depth}_f{self.n_facts}_x{self.seed}"


def _dump(path: Path, data: dict) -> None:
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=200), encoding="utf-8")


def _write(root: Path, pid: str, pack: dict, concepts: list[dict]) -> str:
    root = Path(root)
    (root / pid).mkdir(parents=True, exist_ok=True)
    shutil.copyfile(Path(PACKS_ROOT) / "kinds.yaml", root / "kinds.yaml")     # loader đọc kind chung từ root
    _dump(root / pid / "pack.yaml", {"id": pid, "version": "0.1", "document_kinds": [f"{pid}_contract"],
                                     "units": ["day"], "conversions": {"day": {"base": "day", "factor": 1}},
                                     **pack, "findings": []})
    _dump(root / pid / "concepts.yaml", {"version": "0.1", "law_values_valid_from": "2000-01-01", "roles": _ROLES,
                                         "concepts": concepts})
    return pid


def _concept(cid: str, rules: list[dict]) -> dict:
    return {"id": cid, "label": cid, "scope": "core", "phase": "P0", "holder": "B", "counterparty": "A",
            "applies_to": ["B"], "describe": cid, "rules": rules}


def _derived_chain(depth: int) -> list[dict]:
    out = []
    for i in range(1, depth + 1):
        when = {"fact": "f0", "op": "gte", "value": 10} if i == 1 else {"fact": f"d{i - 1}", "op": "eq", "value": True}
        out.append({"fact": f"d{i}", "unit": None, "definitions": [
            {"id": "base", "value": False}, {"id": "hold", "exception_of": "base", "when": when, "value": True}]})
    return out


def write_rule_pack(spec: RuleSpec, root: Path) -> str:
    rng = random.Random(spec.seed)
    facts = [f"f{i}" for i in range(spec.n_facts)]
    n_shared = round(spec.n_rules * spec.shared_ratio)
    pool_size = max(1, round(spec.n_rules * (1 - spec.shared_ratio) / 10))
    pool = []
    for _ in range(pool_size):
        cond = {"fact": rng.choice(facts), "op": "gte", "value": rng.randint(0, 40)}
        pool.append({"all": [{"fact": f"d{spec.depth}", "op": "eq", "value": True}, cond]} if spec.depth else cond)
    concepts = []
    for i in range(spec.n_rules):
        if i < n_shared:
            app = pool[rng.randrange(pool_size)]
        else:
            app = {"fact": facts[i % spec.n_facts], "op": "gte", "value": rng.randint(0, 40) + 41 * (i // spec.n_facts % 2)}
        rule = {"id": "r1", "mode": "threshold", "derogation": "mandatory", "on_silence": "none", "applicability": app,
                "check": {"fact": rng.choice(facts), "op": "lte", "value": rng.randint(30, 90)}, "outcome": _OUTCOME}
        concepts.append(_concept(f"synth.c{i}", [rule]))
    pack = {"user_facts": facts}
    if spec.depth:
        pack["derived"] = _derived_chain(spec.depth)
    return _write(root, spec.pack_id, pack, concepts)


def load_rule_pack(spec: RuleSpec, root: Path) -> Catalog:
    return load_packs([write_rule_pack(spec, root)], root=root)


def present_all(catalog: Catalog) -> set[str]:
    """Mọi khái niệm coi như có mặt trong hợp đồng: engine chỉ chạy phép kiểm của khái niệm có mặt (semantics.decide_rule)."""
    return set(catalog.concepts)


def random_facts(catalog: Catalog, spec: RuleSpec, rng: random.Random, *, missing: float) -> dict[str, Fact]:
    """Giá trị 0–100 cho f0..f{n-1}; tỉ lệ `missing` dữ kiện vắng (để có UNKNOWN)."""
    out = {}
    for i in range(spec.n_facts):
        v = rng.randint(0, 100)
        if rng.random() >= missing:
            out[f"f{i}"] = Fact(v, None, "user")
    return out


def update_batches(catalog: Catalog, spec: RuleSpec, rng: random.Random, size: int, count: int
                   ) -> list[dict[str, Fact | None]]:
    """`count` lô cập nhật, mỗi lô `size` dữ kiện khác nhau; ~1/5 là xóa dữ kiện (None)."""
    out = []
    for _ in range(count):
        names = rng.sample(range(spec.n_facts), size)
        out.append({f"f{i}": (None if rng.random() < 0.2 else Fact(rng.randint(0, 100), None, "user")) for i in names})
    return out


# ───────────────────────────── trục 2: số đối tượng mỗi hồ sơ ─────────────────────────────

@dataclass(frozen=True)
class ObjSpec:
    n_objects: int
    n_cross_rules: int
    seed: int

    @property
    def pack_id(self) -> str:
        return f"synth_obj_r{self.n_cross_rules}_x{self.seed}"


__all__ = ["AXIS1_SIZES", "AXIS2_RULES", "AXIS2_SIZES", "ObjSpec", "REAL_AXIS1", "RuleSpec", "load_rule_pack",
           "present_all", "random_facts", "update_batches", "write_rule_pack"]
