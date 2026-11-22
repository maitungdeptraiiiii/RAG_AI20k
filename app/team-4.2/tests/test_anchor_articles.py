"""B6: mọi neo (`anchors.pid`) của các gói trỏ tới Điều (và Khoản, nếu ghi) có thật trong văn bản gốc của kho luật."""
import re

import pytest

from legal_corpus import ROOTS, law_text
from rag.rules.loader import load_packs


def _anchors():
    cat = load_packs(["labor", "civil_loan", "civil_lease"])
    for c in cat.concepts.values():
        for a in c.anchors:
            yield c.id, a["pid"] if isinstance(a, dict) else a.pid


@pytest.mark.skipif(not ROOTS, reason="không có kho luật cục bộ")
def test_every_anchor_points_to_an_existing_article_and_clause():
    bad, n = [], 0
    for cid, pid in _anchors():
        n += 1
        key, _, frag = pid.partition("#")
        m = re.match(r"d(\d+)(?:\.k(\d+))?", frag)
        text = law_text(key)
        assert m and text is not None, (cid, pid)
        art = re.search(rf"(?ms)^\s*Điều {m.group(1)}\.(.*?)(?=^\s*Điều \d+\.|\Z)", text)
        if not art:
            bad.append((cid, pid, "không thấy Điều"))
        elif m.group(2) and not re.search(rf"(?m)^\s*{m.group(2)}\.\s", art.group(1)):
            bad.append((cid, pid, "không thấy khoản"))
    assert n >= 100 and bad == []
