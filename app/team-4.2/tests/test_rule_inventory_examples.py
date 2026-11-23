"""Ví dụ của bản liệt kê rule (viết từ luật, TRƯỚC khi có YAML) chạy qua engine thật: mỗi mục có `yaml_rule` dạng
`<khái niệm>/<rule>` phải cho đúng trạng thái ở mọi ví dụ có dữ kiện (cả reference lẫn network).

Quy ước ví dụ: `facts` là {dữ kiện: giá trị} (đơn vị mặc định của slot / dữ kiện) hoặc {dữ kiện: [giá trị, đơn vị]} khi
cần nói rõ đơn vị (null = hợp đồng không ghi đơn vị); `present: true` = hợp đồng có điều khoản của khái niệm (nội dung
bắt buộc, không có slot); `day` (tùy chọn) là ngày soát. Ví dụ `facts: {}` là trường hợp
bước trích chưa đọc được điều khoản (không phải việc của engine) nên không chạy ở đây."""
from datetime import date
from pathlib import Path

import pytest
import yaml

from rag.rules.evaluator import evaluator_for
from rag.rules.loader import load_packs
from rag.rules.semantics import Fact

ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "docs" / "rule_inventory"
PACK_OF = {"civil_general.yaml": "civil_general", "civil_loan.yaml": "civil_loan", "civil_lease.yaml": "civil_lease",
           "consumer.yaml": "consumer"}
DAY = date(2025, 3, 1)


def _cases():
    for name, pack in PACK_OF.items():
        for e in yaml.safe_load((INVENTORY / name).read_text(encoding="utf-8")):
            ref = str(e.get("yaml_rule") or "").split(" ")[0]
            if "/" not in ref or not ref.split("/")[0].count("."):
                continue
            for i, ex in enumerate(e["examples"]):
                if ex.get("facts") and isinstance(ex.get("expected"), str):
                    yield pytest.param(pack, ref, ex, id=f"{e['id']}#{i}")


def _facts(cat, raw, ref):
    slots = {n: s for c in cat.concepts.values() for n, s in c.slots.items()}
    units = dict(cat.context.input_units)
    out, present = {}, set()
    for name, v in raw.items():
        if name == "present":
            present |= {ref.split("/")[0]} if v else set()
            continue
        value, unit = v if isinstance(v, list) else (v, slots[name].unit if name in slots else units.get(name))
        out[name] = Fact(value, unit)
        present |= {cid for cid, c in cat.concepts.items() if name in c.slots}
    return out, present


@pytest.mark.parametrize("pack,ref,example", list(_cases()))
@pytest.mark.parametrize("kind", ["reference", "network"])
def test_inventory_example_matches_engine(pack, ref, example, kind):
    cat = load_packs([pack])
    facts, present = _facts(cat, example["facts"], ref)
    day = date.fromisoformat(str(example["day"])) if example.get("day") else DAY
    results = {f"{r.concept_id}/{r.rule_id}": r
               for r in evaluator_for(cat, kind).session(day=day, facts=facts, present=present, evidence={}).results()}
    got = results[ref]
    assert got.status == example["expected"], (ref, example, got.status, got.reasons, got.missing_facts)
