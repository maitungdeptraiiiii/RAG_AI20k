"""Nạp gói luật: `pack.yaml` -> PackSpec. Lỗi nào cũng dừng, báo hết một lần (như CatalogError cũ)."""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Mapping, Sequence

import yaml

from rag.rules.derived import definition_inputs, find_cycle
from rag.rules.model import (CORE_FINDINGS, CORE_SILENCES, DEROGATIONS, MODES, OPS, SLOT_KINDS, Catalog, CatalogError,
                             Concept, Definition, DerivedFact, PackSpec, Rule, Silence, Slot, leaves)
from rag.rules.units import Units

PACKS_ROOT = Path(__file__).with_name("packs")
_STATUSES = frozenset({"PASS", "FAIL", "UNKNOWN", "NOT_APPLICABLE"})


def _names(data: dict, key: str, problems: list[str]) -> list[str]:
    v = data.get(key, [])
    if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
        problems.append(f"{key} phải là danh sách chuỗi")
        return []
    return v


def _check_derived_cycles(derived: Mapping[str, DerivedFact], problems: list[str]) -> None:
    deps = {name: [x for d in df.definitions for x in definition_inputs(d)] for name, df in derived.items()}
    if cycle := find_cycle(deps):
        problems.append("derived: phụ thuộc vòng giữa các dữ kiện suy ra " + " -> ".join(cycle))


def _derived(data: dict, units: frozenset[str], inputs: set[str], problems: list[str]) -> dict[str, DerivedFact]:
    out: dict[str, DerivedFact] = {}
    for entry in data.get("derived") or []:
        name = (entry or {}).get("fact")
        if not isinstance(name, str) or not name:
            problems.append(f"derived: mỗi mục cần `fact` là chuỗi, gặp {entry!r}")
            continue
        if name in out:
            problems.append(f"derived: trùng tên, dữ kiện suy ra {name!r} khai báo hai lần")
        if name in inputs:
            problems.append(f"derived: {name!r} trùng tên dữ kiện đầu vào (document_facts / user_facts)")
        unit = entry.get("unit")
        if unit is not None and unit not in units:
            problems.append(f"derived: {name!r} có đơn vị lạ {unit!r}")
        defs, ids = [], set()
        for raw in entry.get("definitions") or []:
            did = str(raw.get("id"))
            where = f"derived {name!r} định nghĩa {did!r}"
            if did in ids:
                problems.append(f"{where}: trùng id")
            ids.add(did)
            has_from, has_value = raw.get("from") is not None, "value" in raw
            if has_from == has_value:
                problems.append(f"{where}: cần đúng một trong `from` và `value`")
            for leaf in leaves(raw.get("when")):
                if leaf.get("op") not in OPS:
                    problems.append(f"{where}: toán tử {leaf.get('op')!r} không hợp lệ")
            defs.append(Definition(did, raw.get("when"), raw.get("exception_of"), raw.get("from"), has_value,
                                   raw.get("value"), tuple(raw.get("anchors") or ())))
        for d in defs:
            if d.exception_of is not None and d.exception_of not in ids:
                problems.append(f"derived {name!r} định nghĩa {d.id!r}: exception_of {d.exception_of!r} không có")
        parent = {d.id: d.exception_of for d in defs if d.exception_of in ids}
        if cycle := find_cycle({k: [v] for k, v in parent.items()}):
            problems.append(f"derived {name!r}: exception_of vòng " + " -> ".join(cycle))
        out[name] = DerivedFact(name, unit, tuple(defs))
    return out


def load_pack(pack_id: str, *, root: Path = PACKS_ROOT) -> PackSpec:
    path = Path(root) / pack_id / "pack.yaml"
    if not path.is_file():
        raise CatalogError([f"pack {pack_id!r} không có ({path})"])
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    problems: list[str] = []
    if data.get("id") != pack_id:
        problems.append(f"id {data.get('id')!r} không khớp tên thư mục {pack_id!r}")
    extends = _names(data, "extends", problems)
    kinds = _names(data, "document_kinds", problems)
    names = frozenset(_names(data, "units", problems))
    user_facts = frozenset(_names(data, "user_facts", problems))
    findings = frozenset(_names(data, "findings", problems))
    factors: dict[str, tuple[str, float]] = {}
    for unit, c in (data.get("conversions") or {}).items():
        if unit not in names:
            problems.append(f"conversions: đơn vị {unit!r} không có trong units")
        base, factor = (c or {}).get("base"), (c or {}).get("factor")
        if base not in names:
            problems.append(f"conversions: gốc {base!r} của {unit!r} không có trong units")
        if isinstance(factor, bool) or not isinstance(factor, (int, float)) or factor <= 0:
            problems.append(f"conversions: factor của {unit!r} phải là số > 0, gặp {factor!r}")
        else:
            factors[unit] = (base, factor)
    for unit, (base, factor) in list(factors.items()):
        # đơn vị gốc phải quy về chính nó với factor 1: thiếu thì tự thêm, sai thì báo (không thì mọi phép so khác đơn vị ra U)
        if base == unit:
            if factor != 1:
                problems.append(f"conversions: đơn vị gốc {unit!r} phải có factor 1, gặp {factor!r}")
        elif base in factors:
            if factors[base] != (base, 1):
                problems.append(f"conversions: gốc {base!r} của {unit!r} phải tự quy về chính nó với factor 1")
        elif base in names:
            factors[base] = (base, 1)
    document_facts = dict(data.get("document_facts") or {})
    for name, unit in document_facts.items():
        if unit is not None and unit not in names:
            problems.append(f"document_facts: dữ kiện {name!r} có đơn vị lạ {unit!r}")
    silences = dict(CORE_SILENCES)
    for name, s in (data.get("silences") or {}).items():
        if name in CORE_SILENCES:
            problems.append(f"silences: {name!r} đã có sẵn trong lõi")
        pair = {}
        for key in ("applicable", "unknown"):
            v = (s or {}).get(key)
            if not (isinstance(v, list) and len(v) == 2 and v[0] in _STATUSES):
                problems.append(f"silences: {name}.{key} phải là [status, finding] với status thuộc {sorted(_STATUSES)}")
            elif v[1] not in CORE_FINDINGS | findings:
                problems.append(f"silences: {name}.{key} dùng finding {v[1]!r} chưa khai báo trong findings")
            else:
                pair[key] = (v[0], v[1])
        if len(pair) == 2 and name not in CORE_SILENCES:
            silences[name] = Silence(pair["applicable"], pair["unknown"])
    derived = _derived(data, names, set(document_facts) | user_facts, problems)
    _check_derived_cycles(derived, problems)
    if problems:
        raise CatalogError(problems)
    return PackSpec(pack_id, str(data.get("version")), tuple(extends), tuple(kinds), Units(names, factors),
                    document_facts, user_facts, findings, silences, derived)


# ── concepts.yaml ──
def _law_names(rule: dict) -> tuple[set[str], list[set[str]]]:
    return set(rule.get("law") or {}), [set(c.get("law") or {}) for c in rule.get("cases") or []]


def _check_law_values(where: str, law: dict, pack: PackSpec, problems: list[str]) -> None:
    for name, v in (law or {}).items():
        if not isinstance(v, dict):
            problems.append(f"{where}: giá trị luật {name} phải là {{value, unit}}")
            continue
        if v.get("unit") is not None and v["unit"] not in pack.units.names:
            problems.append(f"{where}: giá trị luật {name} có đơn vị lạ {v['unit']!r}")
        if "periods" in v:
            for p in v["periods"]:
                if "valid_from" not in p or "values" not in p:
                    problems.append(f"{where}: giá trị luật {name}: kỳ thiếu valid_from / values")
        elif "value" not in v:
            problems.append(f"{where}: giá trị luật {name} thiếu value")


def _fits_unstated_false(check: object, slots: set[str]) -> bool:
    """check là một slot có/không "= false" không kèm giá trị luật (hợp đồng không có hạn chế / hành vi cấm)."""
    return (isinstance(check, dict) and check.get("op") == "eq" and check.get("value") is False
            and "law" not in check and check.get("fact") in slots)


def _rule(c: dict, r: dict, pack: PackSpec, problems: list[str]) -> Rule:
    where = f"{c.get('id')}/{r.get('id')}"
    for key, allowed in (("mode", MODES), ("derogation", DEROGATIONS), ("on_silence", set(pack.silences))):
        if r.get(key) not in allowed:
            problems.append(f"{where}: {key} {r.get(key)!r} không hợp lệ")
    slots = set(c.get("slots") or {})
    known = slots | set(pack.document_facts) | pack.user_facts | set(pack.derived)
    conds = [r.get("applicability"), r.get("check")] + [x.get("when") for x in r.get("cases") or []]
    for leaf in [leaf for cond in conds for leaf in leaves(cond)]:
        if leaf.get("op") not in OPS:
            problems.append(f"{where}: toán tử {leaf.get('op')!r} không hợp lệ")
        if leaf.get("fact") not in known:
            problems.append(f"{where}: dữ kiện {leaf.get('fact')!r} không phải slot, dữ kiện hợp đồng hay người dùng")
        if leaf.get("unit") is not None and leaf["unit"] not in pack.units.names:
            problems.append(f"{where}: đơn vị {leaf['unit']!r} không hợp lệ")
    fixed, per_case = _law_names(r)
    for leaf in leaves(r.get("check")):
        name = leaf.get("law")
        if name is not None and name not in fixed and not (per_case and all(name in s for s in per_case)):
            problems.append(f"{where}: check dùng giá trị law {name!r} không có trong law / mọi cases")
    _check_law_values(where, r.get("law") or {}, pack, problems)
    for case in r.get("cases") or []:
        _check_law_values(where, case.get("law") or {}, pack, problems)
    for law in [r.get("law") or {}, *[c.get("law") or {} for c in r.get("cases") or []]]:
        for name, v in law.items():
            if isinstance(v, dict) and v.get("by") is not None and v["by"] not in known:
                problems.append(f"{where}: dữ kiện {v['by']!r} (by của {name}) không xác định")
    fits = _fits_unstated_false(r.get("check"), slots)
    explicit = r.get("unstated_false")
    if explicit is None:
        unstated = fits
    elif not isinstance(explicit, bool):
        problems.append(f"{where}: unstated_false phải là true / false")
        unstated = False
    else:
        unstated = explicit
        if explicit and not fits:
            problems.append(f"{where}: unstated_false: true cần check dạng {{fact: <slot>, op: eq, value: false}}")
    return Rule(str(r.get("id")), r.get("mode"), r.get("derogation"), r.get("on_silence"), r.get("applicability"),
                dict(r.get("law") or {}), tuple(r.get("cases") or ()), r.get("check"), dict(r.get("outcome") or {}),
                unstated)


def _slots(c: dict, pack: PackSpec, problems: list[str]) -> dict[str, Slot]:
    out = {}
    for name, s in (c.get("slots") or {}).items():
        if s.get("kind") not in SLOT_KINDS:
            problems.append(f"{c.get('id')}: slot {name} có kind lạ {s.get('kind')!r}")
        if s.get("unit") is not None and s["unit"] not in pack.units.names:
            problems.append(f"{c.get('id')}: slot {name} có đơn vị lạ {s['unit']!r}")
        out[name] = Slot(name, s.get("kind"), s.get("unit"), tuple(s.get("options") or ()))
    return out


def load_concepts(path: Path, pack: PackSpec) -> Catalog:
    """Nạp một concepts.yaml, kiểm theo khai báo của `pack`. Lỗi nào cũng dừng, báo hết một lần."""
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    problems: list[str] = []
    roles = {r["id"]: r for r in data.get("roles") or []}
    for r in roles.values():
        if r.get("subtype_of") is not None and r["subtype_of"] not in roles:
            problems.append(f"role {r['id']}: subtype_of {r['subtype_of']!r} không có")
    concepts: dict[str, Concept] = {}
    for c in data.get("concepts") or []:
        cid = c.get("id")
        if cid in concepts:
            problems.append(f"{cid}: trùng id")
        for key in ("holder", "counterparty"):
            if c.get(key) not in roles:
                problems.append(f"{cid}: role {key} {c.get(key)!r} không khai báo")
        for role in c.get("applies_to") or []:
            if role not in roles:
                problems.append(f"{cid}: role applies_to {role!r} không khai báo")
        slots = _slots(c, pack, problems)
        rules = tuple(_rule(c, r, pack, problems) for r in c.get("rules") or [])
        concepts[cid] = Concept(cid, c.get("label", ""), c.get("scope", ""), c.get("phase", ""), c.get("holder"),
                                c.get("counterparty"), tuple(c.get("applies_to") or ()), c.get("describe", ""),
                                tuple(c.get("phrasing") or ()), slots, tuple(c.get("anchors") or ()),
                                tuple(c.get("value_sources") or ()), rules,
                                tuple(dict(x) for x in c.get("not_about") or ()))
    slot_names = {n for c in concepts.values() for n in c.slots}
    for name in pack.derived:
        if name in slot_names:
            problems.append(f"derived: {name!r} trùng tên slot của một khái niệm")
    known_inputs = slot_names | set(pack.document_facts) | pack.user_facts | set(pack.derived)
    for df in pack.derived.values():
        for d in df.definitions:
            for n in definition_inputs(d):
                if n not in known_inputs:
                    problems.append(f"derived {df.fact!r} định nghĩa {d.id!r}: dữ kiện {n!r} không phải slot, dữ kiện "
                                    "hợp đồng, người dùng hay dữ kiện suy ra")
    for cid, concept in concepts.items():
        for x in concept.not_about:
            if not x.get("text") or x.get("see") not in concepts:
                problems.append(f"{cid}: not_about cần text và see là khái niệm có trong danh mục: {x!r}")
    if problems:
        raise CatalogError(problems)
    return Catalog(str(data.get("version")), date.fromisoformat(str(data["law_values_valid_from"])), roles, concepts,
                   pack.context())


# ── nhiều gói ──
def _merge_packs(specs: list[PackSpec], problems: list[str]) -> PackSpec:
    """Hợp nhất khai báo của các gói (đơn vị, dữ kiện, finding, on_silence); khai báo xung đột ghi vào `problems`."""
    names: set[str] = set()
    factors: dict[str, tuple[str, float]] = {}
    owner: dict[str, str] = {}
    document_facts: dict[str, str | None] = {}
    user_facts: set[str] = set()
    findings: set[str] = set()
    silences: dict[str, Silence] = dict(CORE_SILENCES)
    derived: dict[str, DerivedFact] = {}
    kinds: list[str] = []
    for s in specs:
        names |= s.units.names
        for unit, f in s.units.factors.items():
            if unit in factors and factors[unit] != f:
                problems.append(f"conversions: đơn vị {unit!r} có hệ số khác nhau giữa các gói ({owner[unit]} và {s.id})")
            else:
                factors[unit], owner[unit] = f, s.id
        for name, unit in s.document_facts.items():
            if name in document_facts and document_facts[name] != unit:
                problems.append(f"document_facts: dữ kiện {name!r} có đơn vị khác nhau giữa các gói")
            document_facts[name] = unit
        user_facts |= s.user_facts
        findings |= s.findings
        for name, silence in s.silences.items():
            if name in silences and silences[name] != silence:
                problems.append(f"silences: {name!r} khai báo khác nhau giữa các gói")
            silences[name] = silence
        kinds += [k for k in s.document_kinds if k not in kinds]
        for name, df in s.derived.items():
            if name in derived:
                problems.append(f"derived: dữ kiện suy ra {name!r} trùng tên giữa các gói")
            derived[name] = df
    _check_derived_cycles(derived, problems)
    return PackSpec("+".join(s.id for s in specs), "+".join(f"{s.id}@{s.version}" for s in specs), (), tuple(kinds),
                    Units(frozenset(names), factors), document_facts, frozenset(user_facts), frozenset(findings),
                    silences, derived)


def load_packs(pack_ids: Sequence[str], *, root: Path = PACKS_ROOT) -> Catalog:
    """Nạp và gộp nhiều gói. Gói cha (`extends`) nạp trước; gói con thấy khai báo của cha. Lỗi nào cũng dừng, báo hết.
    Một gói: giữ nguyên `version` của concepts.yaml; nhiều gói: `<gói>@<version>` nối bằng `+`;
    `law_values_valid_from` lấy ngày lớn nhất."""
    problems: list[str] = []
    specs: dict[str, PackSpec] = {}
    order: list[str] = []

    def visit(pid: str, via: str | None, stack: list[str]) -> None:
        if pid in order:
            return
        if pid in stack:
            problems.append(f"extends: vòng {' -> '.join([*stack, pid])}")
            return
        try:
            spec = specs[pid] = specs.get(pid) or load_pack(pid, root=root)
        except CatalogError as e:
            problems.append(f"{'extends' if via else 'pack'}: không nạp được gói {pid!r}"
                            f"{f' (extends của {via})' if via else ''}: " + "; ".join(e.problems))
            return
        for parent in spec.extends:
            visit(parent, pid, [*stack, pid])
        order.append(pid)

    for pid in pack_ids:
        visit(pid, None, [])
    if problems:
        raise CatalogError(list(dict.fromkeys(problems)))

    def lineage(pid: str) -> set[str]:
        return {pid}.union(*(lineage(p) for p in specs[pid].extends))

    catalogs: list[tuple[str, Catalog]] = []
    for pid in order:
        path = Path(root) / pid / "concepts.yaml"
        if not path.is_file():
            continue
        view = _merge_packs([specs[p] for p in order if p in lineage(pid)], problems)
        try:
            catalogs.append((pid, load_concepts(path, view)))
        except CatalogError as e:
            problems += [f"[{pid}] {p}" for p in e.problems]
    merged = _merge_packs([specs[p] for p in order], problems)
    concepts: dict[str, Concept] = {}
    owner: dict[str, str] = {}
    roles: dict[str, dict] = {}
    for pid, cat in catalogs:
        for cid, c in cat.concepts.items():
            if cid in concepts:
                problems.append(f"{cid}: trùng id giữa gói {owner[cid]} và {pid}")
            else:
                concepts[cid], owner[cid] = c, pid
        for rid, r in cat.roles.items():
            if rid in roles and roles[rid] != r:
                problems.append(f"role {rid!r}: khai báo khác nhau giữa các gói")
            roles.setdefault(rid, r)
    if not catalogs:
        problems.append("không gói nào có concepts.yaml")
    if problems:
        raise CatalogError(list(dict.fromkeys(problems)))
    version = catalogs[0][1].version if len(catalogs) == 1 else "+".join(f"{pid}@{c.version}" for pid, c in catalogs)
    return Catalog(version, max(c.law_values_valid_from for _, c in catalogs), roles, concepts, merged.context())
