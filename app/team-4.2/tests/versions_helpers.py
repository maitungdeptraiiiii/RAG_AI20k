"""Hợp đồng gốc + phụ lục nâng lương và LLM giả dùng chung cho test phiên bản."""
import json
from datetime import datetime, timezone

from rag.bridge.tagger import TAG_PROMPT
from rag.contracts.facts import FACTS_PROMPT
from rag.contracts.models import Contract
from rag.contracts.structure import parse_contract, to_contract_units
from rag.contracts.doc import PageText

from tests.test_bridge_check import PAGES, ScriptLLM

AT = datetime(2026, 11, 26, tzinfo=timezone.utc)
APPENDIX_TEXT = ("PHỤ LỤC HỢP ĐỒNG SỐ 01\nKý ngày 20 tháng 05 năm 2025.\n"
                 "Điều 1. Điều chỉnh Điều 1 Hợp đồng lao động: mức lương chính là 17.000.000 đồng/tháng.\n"
                 "Nội dung trên có hiệu lực từ ngày 01/06/2025.")
SALARY_QUOTE = "mức lương chính là 17.000.000 đồng/tháng"


class AppendixLLM(ScriptLLM):
    """ScriptLLM cho phần gốc; lô thuộc phụ lục trả lương mới và ngày của phụ lục."""

    salary = "17.000.000 đồng/tháng"
    quote = SALARY_QUOTE

    def complete(self, system, user):
        payload = json.loads(user)
        units = payload.get("units") or []
        appendix = units and all(u["uid"].startswith("p1.") for u in units)
        if appendix and system.startswith(FACTS_PROMPT[:40]):
            self.calls.append((system, payload))
            home = next((u["uid"] for u in units if self.quote in u["text"]), units[0]["uid"])
            signed = next((u["uid"] for u in units if "Ký ngày 20" in u["text"]), units[0]["uid"])
            return json.dumps({"type": "Phụ lục", "parties": [],
                               "sign_date": {"value": "2025-05-20", "unit": signed, "quote": "Ký ngày 20 tháng 05 năm 2025"},
                               "fields": {"salary": {"value": self.salary, "unit": home, "quote": self.quote}}},
                              ensure_ascii=False)
        if appendix and system.startswith(TAG_PROMPT[:40]):
            self.calls.append((system, payload))
            return json.dumps({"items": []})
        return super().complete(system, user)


def base_contract(cid="c" * 24):
    doc = parse_contract(PAGES)
    units = to_contract_units(doc)
    return Contract(cid, "hd.txt", False, AT, "\n".join(u.text for u in units), list(units), len(units), doc=doc,
                    page_texts=list(PAGES), file_checksum="x")
