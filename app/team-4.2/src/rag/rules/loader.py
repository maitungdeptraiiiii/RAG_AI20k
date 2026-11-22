"""Nạp gói luật: `pack.yaml` -> PackSpec. Lỗi nào cũng dừng, báo hết một lần (như CatalogError cũ)."""
from __future__ import annotations

from pathlib import Path

import yaml

from rag.rules.model import CORE_FINDINGS, CORE_SILENCES, CatalogError, PackSpec, Silence
from rag.rules.units import Units

PACKS_ROOT = Path(__file__).with_name("packs")
_STATUSES = frozenset({"PASS", "FAIL", "UNKNOWN", "NOT_APPLICABLE"})


def _names(data: dict, key: str, problems: list[str]) -> list[str]:
    v = data.get(key, [])
    if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
        problems.append(f"{key} phải là danh sách chuỗi")
        return []
    return v


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
    if problems:
        raise CatalogError(problems)
    return PackSpec(pack_id, str(data.get("version")), tuple(extends), tuple(kinds), Units(names, factors),
                    document_facts, user_facts, findings, silences)
