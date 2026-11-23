"""Nạp gói luật: `pack.yaml` -> PackSpec. Lỗi nào cũng dừng, báo hết một lần (như CatalogError cũ)."""
from __future__ import annotations

import dataclasses
from datetime import date
from pathlib import Path
from typing import Mapping, Sequence

import yaml

from rag.rules.derived import definition_inputs, find_cycle
from rag.rules.objects import BUILTIN_ATTRS, COUNT_OPS
from rag.rules.model import (CORE_FINDINGS, DOCUMENT_PARSERS, CORE_SILENCES, DEROGATIONS, EARLIER_CONTRACTS, MODES, OPS, SLOT_KINDS, Catalog, CatalogError,
                             Concept, Definition, DerivedFact, DocumentFact, ObjectType, PackSpec, Rule, Silence, Slot, UserQuestion, leaves)
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


_CLASH = "derived: {!r} trùng tên dữ kiện đầu vào (document_facts / user_facts)"


def _derived(data: dict, units: frozenset[str], inputs: set[str], problems: list[str]) -> dict[str, DerivedFact]:
    out: dict[str, DerivedFact] = {}
    entries = data.get("derived") or []
    if not isinstance(entries, list):
        problems.append("derived phải là danh sách")
        return out
    for entry in entries:
        name = entry.get("fact") if isinstance(entry, dict) else None
        if not isinstance(name, str) or not name:
            problems.append(f"derived: mỗi mục phải là dict có `fact` là chuỗi, gặp {entry!r}")
            continue
        if name in out:
            problems.append(f"derived: trùng tên, dữ kiện suy ra {name!r} khai báo hai lần")
        if name in inputs:
            problems.append(_CLASH.format(name))
        unit = entry.get("unit")
        if unit is not None and unit not in units:
            problems.append(f"derived: {name!r} có đơn vị lạ {unit!r}")
        raw_defs = entry.get("definitions")
        if not isinstance(raw_defs, list) or not raw_defs:
            problems.append(f"derived {name!r}: definitions phải là danh sách không rỗng")
            raw_defs = []
        defs, ids = [], set()
        for raw in raw_defs:
            if not isinstance(raw, dict) or not isinstance(raw.get("id"), str) or not raw.get("id"):
                problems.append(f"derived {name!r}: mỗi định nghĩa phải là dict có `id` là chuỗi, gặp {raw!r}")
                continue
            did = raw["id"]
            where = f"derived {name!r} định nghĩa {did!r}"
            if did in ids:
                problems.append(f"{where}: trùng id")
            ids.add(did)
            when, exc = raw.get("when"), raw.get("exception_of")
            if when is not None and not isinstance(when, dict):
                problems.append(f"{where}: when phải là điều kiện (dict), gặp {when!r}")
                when = None
            if exc is not None and not isinstance(exc, str):
                problems.append(f"{where}: exception_of phải là id định nghĩa (chuỗi), gặp {exc!r}")
                exc = None
            has_from, has_value = raw.get("from") is not None, "value" in raw
            if has_from == has_value:
                problems.append(f"{where}: cần đúng một trong `from` và `value`")
            for leaf in leaves(when):
                if leaf.get("op") not in OPS:
                    problems.append(f"{where}: toán tử {leaf.get('op')!r} không hợp lệ")
                if leaf.get("unit") is not None and leaf["unit"] not in units:
                    problems.append(f"{where}: đơn vị {leaf['unit']!r} không hợp lệ")
            defs.append(Definition(did, when, exc, raw.get("from"), has_value, raw.get("value"),
                                   tuple(raw.get("anchors") or ())))
        for d in defs:
            if d.exception_of is not None and d.exception_of not in ids:
                problems.append(f"derived {name!r} định nghĩa {d.id!r}: exception_of {d.exception_of!r} không có")
        parent = {d.id: d.exception_of for d in defs if d.exception_of in ids}
        if cycle := find_cycle({k: [v] for k, v in parent.items()}):
            problems.append(f"derived {name!r}: exception_of vòng " + " -> ".join(cycle))
        otype = entry.get("object_type")
        if otype is not None and not isinstance(otype, str):
            problems.append(f"derived {name!r}: object_type phải là tên kiểu (chuỗi)")
            otype = None
        out[name] = DerivedFact(name, unit, tuple(defs), otype)
    return out


def _document_facts(raw: object, units: frozenset[str], problems: list[str]):
    """`document_facts`: `{tên: đơn vị}` (chỉ khai, không tự trích) hoặc `{tên: {unit, from, parse, values | contains}}`."""
    if not isinstance(raw, dict):
        problems.append("document_facts phải là dict")
        return {}, {}
    plain: dict[str, str | None] = {}
    specs: dict[str, DocumentFact] = {}
    for name, v in raw.items():
        if v is None or isinstance(v, str):
            unit, spec = v, None
        elif isinstance(v, dict):
            unit, spec = v.get("unit"), v
        else:
            problems.append(f"document_facts: {name!r} phải là đơn vị hoặc {{unit, from, parse}}")
            continue
        if unit is not None and unit not in units:
            problems.append(f"document_facts: dữ kiện {name!r} có đơn vị lạ {unit!r}")
        plain[name] = unit
        if spec is None:
            continue
        where = f"document_facts {name!r}"
        if not isinstance(spec.get("from"), str) or not spec["from"]:
            problems.append(f"{where}: thiếu `from` (khóa trường trích)")
            continue
        if spec.get("parse") not in DOCUMENT_PARSERS:
            problems.append(f"{where}: parse {spec.get('parse')!r} không thuộc {sorted(DOCUMENT_PARSERS)}")
            continue
        values: tuple = ()
        if spec["parse"] == "enum":
            m = spec.get("values")
            if not isinstance(m, dict) or not m:
                problems.append(f"{where}: parse enum cần `values` {{nhãn: mã}}")
                continue
            values = tuple((str(k), str(c)) for k, c in m.items())
        elif spec["parse"] == "contains":
            m = spec.get("contains")
            if not isinstance(m, list) or not m or not all(isinstance(x, list) and len(x) == 2 for x in m):
                problems.append(f"{where}: parse contains cần `contains` [[cụm chữ, mã], ...]")
                continue
            values = tuple((str(a), str(b)) for a, b in m)
        specs[name] = DocumentFact(name, unit, spec["from"], spec["parse"], values)
    return plain, specs


def _extract_fields(raw: object, problems: list[str]) -> tuple[dict, ...]:
    """Trường gói muốn LLM trích thêm: [{key, label, kind (text | enum | date), hint?, options?}]."""
    if not isinstance(raw, list):
        problems.append("extract_fields phải là danh sách")
        return ()
    out = []
    for f in raw:
        if not (isinstance(f, dict) and isinstance(f.get("key"), str) and isinstance(f.get("label"), str)
                and f.get("kind", "text") in ("text", "enum", "date")):
            problems.append(f"extract_fields: mỗi mục cần key, label (chuỗi) và kind text | enum | date, gặp {f!r}")
            continue
        out.append({"kind": "text", **f})
    return tuple(out)


def _kind_specs(raw, where: str, problems: list[str]) -> dict[str, tuple[str, ...]]:
    """{kind: {slot_kinds: [...]}} -> {kind: (loại slot, ...)}."""
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        problems.append(f"{where} phải là dict {{kind: {{slot_kinds: [...]}}}}")
        return {}
    out = {}
    for kind, spec in raw.items():
        sk = spec.get("slot_kinds") if isinstance(spec, dict) else None
        if not isinstance(sk, list) or not all(x in SLOT_KINDS for x in sk):
            problems.append(f"{where}: {kind!r} cần slot_kinds là danh sách các loại thuộc {sorted(SLOT_KINDS)}")
            sk = []
        out[kind] = tuple(sk)
    return out


def _shared_kinds(root: Path, problems: list[str]) -> dict[str, tuple[str, ...]]:
    """Danh sách kind chung cho mọi gói trong `root` (`root/kinds.yaml`, spec bản 3 §5.5); không có file thì rỗng."""
    path = root / "kinds.yaml"
    if not path.is_file():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return _kind_specs(data.get("kinds") or {}, "kinds.yaml", problems)


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
    document_facts, document_specs = _document_facts(data.get("document_facts") or {}, names, problems)
    extract_fields = _extract_fields(data.get("extract_fields") or [], problems)
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
    user_fact_units = data.get("user_fact_units") or {}
    if not isinstance(user_fact_units, dict):
        problems.append("user_fact_units phải là dict {dữ kiện: đơn vị}")
        user_fact_units = {}
    for name, unit in user_fact_units.items():
        if name not in user_facts:
            problems.append(f"user_fact_units: {name!r} không có trong user_facts")
        if unit not in names:
            problems.append(f"user_fact_units: dữ kiện {name!r} có đơn vị lạ {unit!r}")
    questions: dict[str, UserQuestion] = {}
    raw_q = data.get("user_fact_questions") or {}
    if not isinstance(raw_q, dict):
        problems.append("user_fact_questions phải là dict {dữ kiện: {question, values, unit?}}")
        raw_q = {}
    for name, q in raw_q.items():
        where = f"user_fact_questions: {name!r}"
        if name not in user_facts:
            problems.append(f"{where} không có trong user_facts")
        q = q if isinstance(q, dict) else {}
        if not isinstance(q.get("question"), str) or not q["question"]:
            problems.append(f"{where}: thiếu question (chuỗi)")
        if not isinstance(q.get("values"), list) or not q["values"]:
            problems.append(f"{where}: values phải là danh sách không rỗng")
        if q.get("unit") is not None and q["unit"] not in names:
            problems.append(f"{where}: đơn vị lạ {q['unit']!r}")
        questions[name] = UserQuestion(name, str(q.get("question")), tuple(q.get("values") or ()), q.get("unit"))
    shared = _shared_kinds(Path(root), problems)
    concept_kinds: dict[str, tuple[str, ...]] = dict(shared)
    for kind, sk in _kind_specs(data.get("concept_kinds"), "concept_kinds", problems).items():
        if kind in shared and shared[kind] != sk:
            problems.append(f"concept_kinds: {kind!r} là kind chung (kinds.yaml), không được khai lại khác đi")
            continue
        concept_kinds[kind] = sk
    object_types: dict[str, ObjectType] = {}
    raw_types = data.get("object_types") or {}
    if not isinstance(raw_types, dict):
        problems.append("object_types phải là dict {Kiểu: {attrs: [...], refs: [...]}}")
        raw_types = {}
    for tname, spec in raw_types.items():
        spec = spec if isinstance(spec, dict) else {}
        attrs, refs = spec.get("attrs", []), spec.get("refs", [])
        if not all(isinstance(x, list) and all(isinstance(y, str) for y in x) for x in (attrs, refs)):
            problems.append(f"object_types: {tname!r} cần attrs và refs là danh sách chuỗi")
            attrs, refs = [], []
        if BUILTIN_ATTRS & set(attrs):
            problems.append(f"object_types: {tname!r} khai thuộc tính dựng sẵn {sorted(BUILTIN_ATTRS & set(attrs))}")
        object_types[tname] = _object_type(tname, spec, attrs, refs, kinds, document_facts, problems)
    unit_forms: dict[str, tuple[str, ...]] = {}
    raw_forms = data.get("unit_forms") or {}
    if not isinstance(raw_forms, dict):
        problems.append("unit_forms phải là dict {đơn vị: [cách viết, ...]}")
        raw_forms = {}
    for unit, forms in raw_forms.items():
        if unit not in names:
            problems.append(f"unit_forms: đơn vị {unit!r} không có trong units")
        if not isinstance(forms, list) or not forms or not all(isinstance(x, str) and x.strip() for x in forms):
            problems.append(f"unit_forms: {unit!r} cần danh sách chuỗi không rỗng")
            continue
        unit_forms[unit] = tuple(forms)
    labels = data.get("document_labels") or {}
    if not isinstance(labels, dict) or not all(isinstance(v, str) and v.strip() for v in labels.values()):
        problems.append("document_labels phải là dict {document_kind: nhãn}")
        labels = {}
    for k in labels:
        if k not in kinds:
            problems.append(f"document_labels: {k!r} không có trong document_kinds")
    label = next((labels[k] for k in kinds if k in labels), "hợp đồng")
    pack_labels = _labels(data.get("labels"), findings, problems)
    if problems:
        raise CatalogError(problems)
    return PackSpec(pack_id, str(data.get("version")), tuple(extends), tuple(kinds), Units(names, factors),
                    document_facts, user_facts, findings, silences, derived, dict(user_fact_units), questions,
                    concept_kinds, object_types, unit_forms, document_specs, extract_fields, dict(labels), label, pack_labels)


def _labels(raw, findings, problems: list[str]) -> dict:
    """`labels: {findings: {finding: câu}, facts: {dữ kiện: nhãn}}` (D34); finding phải là finding lõi hoặc khai ở `findings`."""
    if raw is None:
        return {}
    if not isinstance(raw, dict) or set(raw) - {"findings", "facts"}:
        problems.append("labels: chỉ có hai khóa findings và facts")
        return {}
    out: dict[str, dict[str, str]] = {}
    for group in ("findings", "facts"):
        items = raw.get(group) or {}
        if not isinstance(items, dict) or not all(isinstance(k, str) and isinstance(v, str) and v.strip() for k, v in items.items()):
            problems.append(f"labels.{group} phải là dict {{tên: nhãn}}")
            continue
        out[group] = dict(items)
    for f in out.get("findings", {}):
        if f not in CORE_FINDINGS and f not in findings:
            problems.append(f"labels.findings: {f!r} không phải finding lõi và không khai trong findings")
    return out


def _object_type(tname: str, spec: dict, attrs: list, refs: list, kinds, document_facts, problems: list[str]) -> ObjectType:
    """Kiểu đối tượng + cách dựng từ văn bản (rag.contracts.dossier, H1): mọi tên trỏ tới phải đã khai."""
    where = f"object_types: {tname!r}"
    docs = spec.get("documents") or []
    if not isinstance(docs, list) or any(d != "amendment" and d not in kinds for d in docs):
        problems.append(f"{where}: documents phải là danh sách document_kinds của gói (hoặc 'amendment'), gặp {docs!r}")
        docs = []
    from_facts = spec.get("from_facts") or {}
    if not isinstance(from_facts, dict):
        problems.append(f"{where}: from_facts phải là dict {{thuộc tính: dữ kiện}}")
        from_facts = {}
    for a, f in from_facts.items():
        if a not in attrs:
            problems.append(f"{where}: from_facts: {a!r} không có trong attrs")
        if f not in document_facts:
            problems.append(f"{where}: from_facts: dữ kiện {f!r} không có trong document_facts")
    gap = spec.get("gap_after_end")
    if gap is not None:
        if not isinstance(gap, dict) or gap.get("attr") not in attrs or gap.get("ref") not in refs:
            problems.append(f"{where}: gap_after_end cần {{attr: <trong attrs>, ref: <trong refs>}}, gặp {gap!r}")
            gap = None
        else:
            gap = (gap["attr"], gap["ref"])
    amends = spec.get("amends")
    if amends is not None and amends not in refs:
        problems.append(f"{where}: amends {amends!r} không có trong refs")
    for key in ("states_target", "states_valid_from"):
        if spec.get(key) is not None and spec[key] not in attrs:
            problems.append(f"{where}: {key} {spec[key]!r} không có trong attrs")
    modifies = spec.get("modifies") or {}
    if not isinstance(modifies, dict) or any(a not in attrs for a in modifies):
        problems.append(f"{where}: modifies phải là dict {{thuộc tính trong attrs: trường trích}}")
        modifies = {}
    return ObjectType(tname, frozenset(attrs), frozenset(refs), tuple(docs), dict(from_facts), gap, amends,
                      spec.get("states_target"), spec.get("states_valid_from"), dict(modifies))


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
            keyed = v.get("by") is not None           # có `by`: mỗi kỳ một bảng values; không: mỗi kỳ một value
            for p in v["periods"]:
                if not isinstance(p, dict) or "valid_from" not in p:
                    problems.append(f"{where}: giá trị luật {name}: kỳ thiếu valid_from")
                elif keyed and "values" not in p:
                    problems.append(f"{where}: giá trị luật {name}: kỳ thiếu values (có by)")
                elif not keyed and ("value" not in p or "values" in p):
                    problems.append(f"{where}: giá trị luật {name}: không có by thì mỗi kỳ cần đúng một value")
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
    known = slots | set(pack.document_facts) | pack.user_facts | {n for n, d in pack.derived.items()
                                                                  if d.object_type is None}
    over, group_by = _object_rule(where, r, pack, problems)
    conds = [r.get("applicability"), None if over else r.get("check")] + [x.get("when") for x in r.get("cases") or []]
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
    standalone = r.get("standalone", False)
    if not isinstance(standalone, bool):
        problems.append(f"{where}: standalone phải là true / false")
        standalone = False
    exc = r.get("exception_of")
    if exc is not None and not (isinstance(exc, str) and exc.count("/") == 1 and all(exc.split("/"))):
        problems.append(f"{where}: exception_of {exc!r} phải có dạng <concept>/<rule>")
        exc = None
    return Rule(str(r.get("id")), r.get("mode"), r.get("derogation"), r.get("on_silence"), r.get("applicability"),
                dict(r.get("law") or {}), tuple(r.get("cases") or ()), r.get("check"), _outcome(where, r, problems),
                unstated, exc, standalone, over, group_by)


def _outcome(where: str, r: dict, problems: list[str]) -> dict:
    """outcome của rule (spec bản 3 §5.2, G10): tên trung tính `party_impact`; `employee_impact` của YAML cũ được nhận
    và đổi thành `party_impact`. Khai cả hai mà khác nhau là lỗi."""
    out = dict(r.get("outcome") or {})
    if "employee_impact" in out:
        old = out.pop("employee_impact")
        if "party_impact" in out and out["party_impact"] != old:
            problems.append(f"{where}: outcome khai cả party_impact {out['party_impact']!r} và employee_impact {old!r} "
                            "khác nhau (employee_impact là tên cũ của party_impact)")
        out.setdefault("party_impact", old)
    return out


def _object_rule(where: str, r: dict, pack: PackSpec, problems: list[str]):
    """Kiểm và dựng phần xuyên đối tượng của rule (spec §5.6): `over`, `group_by`, `check` đếm / exists / not_exists."""
    raw, gb = r.get("over"), r.get("group_by")
    if raw is None:
        if gb:
            problems.append(f"{where}: group_by chỉ dùng được cùng over")
        return None, ()
    if not isinstance(raw, dict) or len(raw) != 1:
        problems.append(f"{where}: over phải khai đúng một biến {{biến: {{type, where}}}} (nối nhiều biến chưa hỗ trợ)")
        return None, ()
    (var, spec), = raw.items()
    spec = spec if isinstance(spec, dict) else {}
    typ = spec.get("type")
    otype = pack.object_types.get(typ)
    if otype is None:
        problems.append(f"{where}: kiểu đối tượng {typ!r} chưa khai trong object_types")
        return None, ()
    typed = {n for n, d in pack.derived.items() if d.object_type == typ} | BUILTIN_ATTRS
    where_cond = spec.get("where")
    if where_cond is not None and not isinstance(where_cond, dict):
        problems.append(f"{where}: over.{var}.where phải là điều kiện (dict), gặp {where_cond!r}")
        where_cond = None
    history = spec.get("history", False)
    if not isinstance(history, bool):
        problems.append(f"{where}: over.{var}.history phải là true / false")
        history = False
    if gb is not None and not isinstance(gb, dict):
        problems.append(f"{where}: group_by phải là dict {{tên: đường dẫn}}")
        gb = None
    for leaf in leaves(where_cond):
        if leaf.get("op") not in OPS:
            problems.append(f"{where}: toán tử {leaf.get('op')!r} không hợp lệ")
        if leaf.get("fact") not in otype.attrs | typed:
            problems.append(f"{where}: {leaf.get('fact')!r} không phải thuộc tính hay dữ kiện suy ra của {typ}")
        if leaf.get("unit") is not None and leaf["unit"] not in pack.units.names:
            problems.append(f"{where}: đơn vị {leaf['unit']!r} không hợp lệ")
    group = []
    for name, path in (gb or {}).items():
        head, _, rest = str(path).partition(".")
        if head != var:
            problems.append(f"{where}: group_by {name}: biến {head!r} chưa khai trong over")
        elif rest.startswith("refs."):
            if rest[5:] not in otype.refs:
                problems.append(f"{where}: group_by {name}: ref {rest[5:]!r} không có trong {typ}")
        elif rest not in otype.attrs | typed:
            problems.append(f"{where}: group_by {name}: thuộc tính {rest!r} không có trong {typ}")
        group.append((str(name), str(path)))
    check = r.get("check")
    if not isinstance(check, dict) or len(check) != 1 or next(iter(check)) not in ("count", "exists", "not_exists"):
        problems.append(f"{where}: rule có over cần check là count / exists / not_exists")
    elif "count" in check:
        c = check["count"] if isinstance(check["count"], dict) else {}
        if c.get("of") != var:
            problems.append(f"{where}: count.of {c.get('of')!r} không phải biến {var!r}")
        if c.get("op") not in COUNT_OPS:
            problems.append(f"{where}: count.op {c.get('op')!r} không hợp lệ ({sorted(COUNT_OPS)})")
        if ("value" in c) == ("law" in c):
            problems.append(f"{where}: count cần đúng một trong value và law")
        elif "value" in c and (isinstance(c["value"], bool) or not isinstance(c["value"], (int, float))):
            problems.append(f"{where}: count.value phải là số, gặp {c['value']!r}")
        elif "law" in c and c["law"] not in (r.get("law") or {}):
            problems.append(f"{where}: count dùng giá trị law {c['law']!r} không có trong law")
    elif check[next(iter(check))] != var:
        problems.append(f"{where}: {next(iter(check))} {check[next(iter(check))]!r} không phải biến {var!r}")
    return (var, typ, where_cond, history), tuple(group)


def _check_exceptions(concepts: Mapping[str, Concept], problems: list[str], *, strict: bool) -> None:
    """`exception_of` trỏ tới rule có thật, không tự trỏ, không vòng. `strict=False` (một concepts.yaml): đích thuộc concept
    không có trong file được bỏ qua (có thể nằm ở gói khác, `load_packs` kiểm sau khi gộp)."""
    rules = {f"{cid}/{r.id}": r for cid, c in concepts.items() for r in c.rules}
    for key, r in rules.items():
        target = r.exception_of
        if target is None:
            continue
        if r.over is not None or (target in rules and rules[target].over is not None):
            problems.append(f"{key}: exception_of không dùng với rule xuyên đối tượng (viết ngoại lệ bằng applicability)")
        if target == key:
            problems.append(f"{key}: exception_of trỏ chính nó")
        elif target not in rules and (strict or target.split("/")[0] in concepts):
            problems.append(f"{key}: exception_of {target!r} không phải rule có trong danh mục")
    graph = {k: [r.exception_of] for k, r in rules.items() if r.exception_of and r.exception_of != k}
    if cycle := find_cycle(graph):
        problems.append("exception_of: vòng " + " -> ".join(cycle))


def _slots(c: dict, pack: PackSpec, problems: list[str]) -> dict[str, Slot]:
    out = {}
    for name, s in (c.get("slots") or {}).items():
        if s.get("kind") not in SLOT_KINDS:
            problems.append(f"{c.get('id')}: slot {name} có kind lạ {s.get('kind')!r}")
        if s.get("unit") is not None and s["unit"] not in pack.units.names:
            problems.append(f"{c.get('id')}: slot {name} có đơn vị lạ {s['unit']!r}")
        out[name] = Slot(name, s.get("kind"), s.get("unit"), tuple(s.get("options") or ()))
    return out


def _date(where: str, raw: object, problems: list[str]) -> date | None:
    try:
        return raw if isinstance(raw, date) else date.fromisoformat(str(raw))
    except ValueError:
        problems.append(f"{where}: {raw!r} không phải ngày YYYY-MM-DD")
        return None


def _in_force(where: str, raw: object, default: tuple[date, str], problems: list[str]) -> tuple[date, str]:
    """`in_force: {from, earlier_contracts}` (ngày luật có hiệu lực, cách áp cho hợp đồng ký trước ngày đó); khóa vắng lấy
    theo `default` (gói: `law_values_valid_from` + "skip"; khái niệm: giá trị của gói)."""
    if raw is None:
        return default
    if not isinstance(raw, dict) or set(raw) - {"from", "earlier_contracts"}:
        problems.append(f"{where}: phải là {{from, earlier_contracts}}, gặp {raw!r}")
        return default
    start = _date(f"{where}.from", raw["from"], problems) if "from" in raw else default[0]
    earlier = raw.get("earlier_contracts", default[1])
    if earlier not in EARLIER_CONTRACTS:
        problems.append(f"{where}.earlier_contracts {earlier!r} phải là một trong {sorted(EARLIER_CONTRACTS)}")
        earlier = default[1]
    return start or default[0], earlier


def _with_in_force(rule: Rule, start: date, earlier: str, *, explicit: bool) -> Rule:
    """Rule có giá trị luật theo kỳ (`periods`): các kỳ đã nói luật nào áp từ ngày nào (trước kỳ đầu -> UNKNOWN
    `law_period_not_covered`), nên không nhận `in_force` của gói; chỉ nhận khi khái niệm khai `in_force` riêng."""
    laws = [rule.law, *[c.get("law") or {} for c in rule.cases]]
    if not explicit and any(isinstance(v, dict) and "periods" in v for law in laws for v in law.values()):
        return rule
    return dataclasses.replace(rule, in_force_from=start, earlier_contracts=earlier)


def load_concepts(path: Path, pack: PackSpec) -> Catalog:
    """Nạp một concepts.yaml, kiểm theo khai báo của `pack`. Lỗi nào cũng dừng, báo hết một lần."""
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    problems: list[str] = []
    roles = {r["id"]: r for r in data.get("roles") or []}
    for r in roles.values():
        if r.get("subtype_of") is not None and r["subtype_of"] not in roles:
            problems.append(f"role {r['id']}: subtype_of {r['subtype_of']!r} không có")
    concepts: dict[str, Concept] = {}
    valid_from = _date("law_values_valid_from", data.get("law_values_valid_from"), problems) or date.min
    pack_in_force = _in_force("in_force", data.get("in_force"), (valid_from, "skip"), problems)
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
        own = c.get("in_force")
        start, earlier = _in_force(f"{cid}: in_force", own, pack_in_force, problems)
        rules = tuple(_with_in_force(_rule(c, r, pack, problems), start, earlier, explicit=own is not None)
                      for r in c.get("rules") or [])
        concepts[cid] = Concept(cid, c.get("label", ""), c.get("scope", ""), c.get("phase", ""), c.get("holder"),
                                c.get("counterparty"), tuple(c.get("applies_to") or ()), c.get("describe", ""),
                                tuple(c.get("phrasing") or ()), slots, tuple(c.get("anchors") or ()),
                                tuple(c.get("value_sources") or ()), rules,
                                tuple(dict(x) for x in c.get("not_about") or ()), c.get("kind"))
    for cid, concept in concepts.items():
        if concept.kind is not None and not isinstance(concept.kind, str):
            problems.append(f"{cid}: kind phải là chuỗi, gặp {concept.kind!r}")
            continue
        if concept.kind is None:
            continue
        if concept.kind not in pack.concept_kinds:
            problems.append(f"{cid}: kind {concept.kind!r} chưa khai báo trong concept_kinds của gói")
            continue
        have = {s.kind for s in concept.slots.values()}
        for needed in pack.concept_kinds[concept.kind]:
            if needed not in have:
                problems.append(f"{cid}: kind {concept.kind!r} cần slot loại {needed!r}")
    _check_exceptions(concepts, problems, strict=False)
    slot_names = {n for c in concepts.values() for n in c.slots}
    for name in pack.derived:
        if name in slot_names:
            problems.append(f"derived: {name!r} trùng tên slot của một khái niệm")
    known_inputs = slot_names | set(pack.document_facts) | pack.user_facts | {
        n for n, d in pack.derived.items() if d.object_type is None}
    for df in pack.derived.values():
        if df.object_type is not None and df.object_type not in pack.object_types:
            problems.append(f"derived {df.fact!r}: object_type {df.object_type!r} chưa khai trong object_types")
            continue
        allowed = known_inputs if df.object_type is None else pack.object_types[df.object_type].attrs | BUILTIN_ATTRS | {
            n for n, d in pack.derived.items() if d.object_type == df.object_type}
        for d in df.definitions:
            for n in definition_inputs(d):
                if n not in allowed:
                    problems.append(f"derived {df.fact!r} định nghĩa {d.id!r}: dữ kiện {n!r} không phải slot, dữ kiện "
                                    "hợp đồng, người dùng hay dữ kiện suy ra")
    for cid, concept in concepts.items():
        for x in concept.not_about:
            if not x.get("text") or x.get("see") not in concepts:
                problems.append(f"{cid}: not_about cần text và see là khái niệm có trong danh mục: {x!r}")
    if problems:
        raise CatalogError(problems)
    return Catalog(str(data.get("version")), valid_from, roles, concepts, pack.context())


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
    user_fact_units: dict[str, str | None] = {}
    questions: dict[str, UserQuestion] = {}
    concept_kinds: dict[str, tuple[str, ...]] = {}
    object_types: dict[str, ObjectType] = {}
    unit_forms: dict[str, tuple[str, ...]] = {}
    document_specs: dict[str, DocumentFact] = {}
    extract_fields: dict[str, dict] = {}
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
        for name, spec in s.document_specs.items():
            if name in document_specs and document_specs[name] != spec:
                problems.append(f"document_facts: cách trích {name!r} khác nhau giữa các gói")
            document_specs[name] = spec
        for f in s.extract_fields:
            if f["key"] in extract_fields and extract_fields[f["key"]] != f:
                problems.append(f"extract_fields: trường {f['key']!r} khai báo khác nhau giữa các gói")
            extract_fields[f["key"]] = f
        for unit, forms in s.unit_forms.items():
            unit_forms[unit] = tuple(dict.fromkeys([*unit_forms.get(unit, ()), *forms]))
        for name, ot in s.object_types.items():
            if name in object_types and object_types[name] != ot:
                problems.append(f"object_types: {name!r} khai báo khác nhau giữa các gói")
            object_types[name] = ot
        for name, sk in s.concept_kinds.items():
            if name in concept_kinds and concept_kinds[name] != sk:
                problems.append(f"concept_kinds: {name!r} khai báo khác nhau giữa các gói")
            concept_kinds[name] = sk
        for name, q in s.user_fact_questions.items():
            if name in questions and questions[name] != q:
                problems.append(f"user_fact_questions: {name!r} khai báo khác nhau giữa các gói")
            questions[name] = q
        for name, unit in s.user_fact_units.items():
            if name in user_fact_units and user_fact_units[name] != unit:
                problems.append(f"user_fact_units: dữ kiện {name!r} có đơn vị mặc định khác nhau giữa các gói")
            user_fact_units[name] = unit
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
    for name in derived:
        if name in document_facts or name in user_facts:
            problems.append(_CLASH.format(name))
    parents = {p for s in specs for p in s.extends}
    leaves = [s for s in specs if s.id not in parents]           # gói lá: miền cụ thể (civil_loan), không phải gói cha
    label = leaves[0].document_label if len(leaves) == 1 else "hợp đồng"
    labels = {k: v for s in specs for k, v in s.document_labels.items()}
    pack_labels: dict[str, dict[str, str]] = {"findings": {}, "facts": {}}
    for s in specs:
        for group, items in s.labels.items():
            for name, text in items.items():
                if pack_labels[group].get(name, text) != text:
                    problems.append(f"labels.{group}: {name!r} có nhãn khác nhau giữa các gói")
                pack_labels[group][name] = text
    return PackSpec("+".join(s.id for s in specs), "+".join(f"{s.id}@{s.version}" for s in specs), (), tuple(kinds),
                    Units(frozenset(names), factors), document_facts, frozenset(user_facts), frozenset(findings),
                    silences, derived, user_fact_units, questions, concept_kinds, object_types, unit_forms,
                    document_specs, tuple(extract_fields.values()), labels, label, pack_labels)


def packs_for_kind(document_kind: str, *, root: Path = PACKS_ROOT) -> list[str]:
    """Gói (có concepts.yaml) khai `document_kind` trong `document_kinds`, theo tên thư mục. Không gói nào -> []
    (người gọi không chạy rule nào thay vì rơi về một gói mặc định; spec bản 3 G9)."""
    out = []
    for d in sorted(p for p in Path(root).iterdir() if (p / "pack.yaml").is_file() and (p / "concepts.yaml").is_file()):
        if document_kind in load_pack(d.name, root=root).document_kinds:
            out.append(d.name)
    return out


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
    _check_exceptions(concepts, problems, strict=True)
    if not catalogs:
        problems.append("không gói nào có concepts.yaml")
    if problems:
        raise CatalogError(list(dict.fromkeys(problems)))
    version = catalogs[0][1].version if len(catalogs) == 1 else "+".join(f"{pid}@{c.version}" for pid, c in catalogs)
    return Catalog(version, max(c.law_values_valid_from for _, c in catalogs), roles, concepts, merged.context())
