"""Dựng gói luật tổng hợp trong thư mục tạm cho test (dùng bộ nạp thật, không dựng Catalog bằng tay)."""
from __future__ import annotations

from pathlib import Path

import yaml

ROLES = [{"id": "NLD", "label": "NLĐ"}, {"id": "NSDLD", "label": "NSDLĐ"}]
OUTCOME = {"legality": "illegal", "employee_impact": "unfavorable"}


def write_pack(root: Path, pack: dict | None = None, concepts: list[dict] | dict | None = None,
               pack_id: str | None = None) -> str:
    """Ghi `root/<id>/pack.yaml` (+ `concepts.yaml` nếu có). `concepts` là danh sách concept (được bọc cùng roles) hoặc
    nguyên dữ liệu concepts.yaml. Trả về id gói."""
    pack = dict(pack or {})
    pid = pack_id or pack.get("id") or "synth"
    data = {"id": pid, "version": "t", "extends": [], "document_kinds": ["x"], "units": ["day", "count"],
            "conversions": {"day": {"base": "day", "factor": 1}}, "document_facts": {}, "user_facts": [],
            "findings": []}
    data.update(pack)
    data["id"] = pid
    (root / pid).mkdir(parents=True, exist_ok=True)
    (root / pid / "pack.yaml").write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    if concepts is not None:
        body = concepts if isinstance(concepts, dict) else {
            "version": "t", "law_values_valid_from": "2021-01-01", "roles": ROLES, "concepts": concepts}
        (root / pid / "concepts.yaml").write_text(yaml.safe_dump(body, allow_unicode=True), encoding="utf-8")
    return pid


def concept(cid: str, rules: list[dict], slots: dict | None = None) -> dict:
    return {"id": cid, "label": cid, "scope": "core", "phase": "P0", "holder": "NLD", "counterparty": "NSDLD",
            "applies_to": ["NLD"], "describe": "d", "phrasing": ["a", "b", "c"], "slots": slots or {},
            "anchors": [{"pid": "bo-luat:45/2019/QH14#d1", "role": "basis"}], "rules": rules}


def rule(rid: str, **kw) -> dict:
    """Rule `required` không `check`: khái niệm có mặt thì PASS; mặc định on_silence `none`."""
    data = {"id": rid, "mode": "required", "derogation": "mandatory", "on_silence": "none", "outcome": OUTCOME}
    data.update(kw)
    return data
