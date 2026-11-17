"""Soát một hợp đồng lao động theo danh mục khái niệm (spec 2026-11-14-contract-concept-check).

Chạy từ app/team-4.2:  uv run python scripts/check_contract_concepts.py <file hợp đồng> <thư mục ra>
                          [--tag-model <id model OpenRouter> | app [--tag-temp 0]]
Bước gán khái niệm mặc định dùng CONCEPT_TAG_MODEL (Claude Haiku 5.5 qua OpenRouter, rag.bridge.llm); các bước khác
giữ model của app. --tag-model <id>: đổi model qua OpenRouter, không cache (so model); --tag-model app: dùng LLM của
app. --tag-temp chỉ gửi khi model nhận temperature (Claude 5.x, GPT-6 không nhận).
--fact tên=giá_trị (lặp lại được): dữ kiện người dùng trả lời, vd. --fact wage_region=I --fact job_level=cao_dang_tro_len
--fact pregnant=false. Tên hợp lệ: USER_FACTS và CONTRACT_FACTS trong rag.bridge.catalog.
Ghi report.json, report.md, oplog.json. LLM lấy từ cấu hình app (như scripts/trace_contract_pipeline.py).
Đồ thị luật dùng khi LEGAL_GRAPH=1 và Neo4j đã công bố; không có thì báo cáo chỉ có neo, không có lời văn luật.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

APP = Path.cwd()
sys.path[:0] = [str(APP), str(APP / "ui"), str(APP / "src")]

import server  # noqa: E402  — cấu hình contracts_api.CONFIG như khi chạy app
import contracts_api as api  # noqa: E402


def _parse_fact(text: str) -> tuple[str, object]:
    name, _, raw = text.partition("=")
    low = raw.strip().casefold()
    if low in ("true", "false"):
        return name.strip(), low == "true"
    try:
        return name.strip(), int(raw) if raw.strip().lstrip("-").isdigit() else float(raw)
    except ValueError:
        return name.strip(), raw.strip()


def main(src: Path, out: Path, tag_model: str | None = None, tag_temp: float | None = None,
         user_facts: dict | None = None) -> None:
    out.mkdir(parents=True, exist_ok=True)
    api.CONFIG.root = lambda: out / "contracts_store"
    llm = server.get_pipeline()[0].llm
    api.CONFIG.llm_factory = lambda: llm
    card = api.create(src.read_bytes(), src.name, persist=False)
    contract = api.get(card["contract_id"])
    result = api.concept_check(contract.contract_id, user_facts, tag_model=tag_model, tag_temp=tag_temp)
    print(json.dumps({"contract_id": contract.contract_id, "graph": result["graph"]}, ensure_ascii=False, default=str))
    (out / "report.json").write_text(json.dumps(result["report"], ensure_ascii=False, indent=2, default=str),
                                     encoding="utf-8")
    (out / "report.md").write_text(result["markdown"], encoding="utf-8")
    (out / "oplog.json").write_text(json.dumps(contract.oplog.to_json(), ensure_ascii=False, indent=2, default=str),
                                    encoding="utf-8")
    print(json.dumps(result["report"]["stats"], ensure_ascii=False))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("src", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--tag-model")
    ap.add_argument("--tag-temp", type=float)
    ap.add_argument("--fact", action="append", default=[], type=_parse_fact)
    a = ap.parse_args()
    main(a.src, a.out, a.tag_model, a.tag_temp, dict(a.fact))
