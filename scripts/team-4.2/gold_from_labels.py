"""Sinh gold.yaml từ bảng nhãn viết tay (người soạn quyết định trạng thái từ luật); câu căn cứ lấy từ bản liệt kê.
python scripts/team-4.2/gold_from_labels.py <inventory.yaml[,inventory2.yaml...]> <facts.yaml> <labels.yaml> <out gold.yaml> <dossier_id> <header>"""
import sys
import yaml
from pathlib import Path

inv = {e["id"]: e for f in sys.argv[1].split(",") for e in yaml.safe_load(Path(f).read_text(encoding="utf-8"))}
facts = yaml.safe_load(Path(sys.argv[2]).read_text(encoding="utf-8"))
labels = yaml.safe_load(Path(sys.argv[3]).read_text(encoding="utf-8"))
out = []
for doc, items in labels.items():
    day = str(facts[doc]["sign_date"])
    for it in items:
        rule, status = it[0], it[1]
        note = it[2] if len(it) > 2 else None
        e = next(x for x in inv.values() if str(x.get("yaml_rule", "")).split(" ")[0] == rule)
        per = {"from": day, "status": status}
        if status == "FAIL":
            per["finding"] = "missing_content" if e["on_silence"] == "missing_content" and e["type"] == "required" else "violation"
        row = {"rule": rule, "object": doc, "periods": [per], "basis": {"pid": e["source"]["pid"], "quote": e["source"]["quote"]}}
        if note:
            row["note"] = note
        out.append(row)
gold = {"dossier_id": sys.argv[5], "labeled_by": "Claude (theo yêu cầu của Tùng) — CHỜ TÙNG DUYỆT", "expected": out}
Path(sys.argv[4]).write_text(sys.argv[6] + "\n" + yaml.safe_dump(gold, allow_unicode=True, sort_keys=False, width=200), encoding="utf-8")
print(len(out))
