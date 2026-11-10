"""Dòng thời gian pháp lý: quy tắc trước, LLM chỉ khi cần (gán vai trò / cụm tương đối / nhiều mốc), backend kiểm
tra bằng chứng và quyết định ngày. LLM không được tạo mốc không có trong câu hỏi, không được đổi ngày quy tắc đã thấy.
"""

from __future__ import annotations

import calendar
import json
import re
import unicodedata
from collections.abc import Sequence
from dataclasses import replace
from datetime import date, datetime

from rag.temporal.models import ROLES, LegalTimeline, Precision, TimeAnchor, local_today
from rag.temporal.rules import extract_rule_anchors, resolve_relative

TIMELINE_PROMPT = (
    "Bạn trích các mốc thời gian pháp lý trong câu hỏi của người dùng về pháp luật Việt Nam. "
    "Trả về DUY NHẤT một JSON: {\"events\": [{\"role\": one of signing|contract_effective|performance|discovery|"
    "dispute|evaluation|unspecified, \"date\": {\"start\": \"YYYY-MM-DD|YYYY-MM|YYYY\" hoặc null, \"end\": ... hoặc null, "
    "\"precision\": \"day|month|year|range\"} hoặc null, \"relative_expression\": cụm nguyên văn như \"năm ngoái\" hoặc null, "
    "\"evidence\": đoạn trích NGUYÊN VĂN từ câu hỏi, \"confidence\": 0..1}]}. "
    "Không tạo mốc nào không có trong câu hỏi. Không tự quy cụm tương đối ra ngày cụ thể (để date=null và điền "
    "relative_expression). signing = ký/giao kết/mua; performance = thực hiện/bàn giao/thanh toán; discovery = phát hiện; "
    "dispute = tranh chấp/khởi kiện; evaluation = thời điểm muốn đánh giá theo luật (bây giờ, hiện nay)."
)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text)).strip().casefold()


_TEMPORAL_CUE = re.compile(r"(?<!\w)(?:hôm|tuần|gần đây|trước đây|dạo|lúc đó|khi đó|sau khi|trước khi|mấy năm|"
                           r"vài năm|mấy tháng|vài tháng|sắp tới|tới đây)(?!\w)", re.IGNORECASE)


def needs_llm(question: str, anchors: Sequence[TimeAnchor]) -> bool:
    """Gọi LLM khi: nhiều mốc, mốc chưa rõ vai trò, cụm tương đối, hoặc có từ chỉ thời gian mà quy tắc không giải."""
    covered = " ".join(a.matched_text or "" for a in anchors)
    cue = any(m.group(0) not in covered for m in _TEMPORAL_CUE.finditer(question))
    return (len(anchors) >= 2 or any(a.role == "unspecified" for a in anchors)
            or any(a.relative_expression for a in anchors) or cue)


def _parse_date(value: str | None) -> tuple[date, date, Precision] | None:
    if not value:
        return None
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            d = date.fromisoformat(value)
            return d, d, "day"
        if re.fullmatch(r"\d{4}-\d{1,2}", value):
            y, m = (int(x) for x in value.split("-"))
            return date(y, m, 1), date(y, m, calendar.monthrange(y, m)[1]), "month"
        if re.fullmatch(r"\d{4}", value):
            return date(int(value), 1, 1), date(int(value), 12, 31), "year"
    except ValueError:
        return None
    return None


def _json_object(raw: str) -> dict | None:
    m = re.search(r"\{.*\}", raw or "", re.DOTALL)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def parse_llm_events(raw: str, question: str, *, asked_at: datetime) -> tuple[list[TimeAnchor], list[str]]:
    data = _json_object(raw)
    if data is None or not isinstance(data.get("events"), list):
        return [], ["timeline.llm_failed"]
    q = _norm(question)
    out, warnings = [], []
    for ev in data["events"]:
        if not isinstance(ev, dict):
            continue
        evidence = str(ev.get("evidence") or "").strip()
        if not evidence or _norm(evidence) not in q:
            warnings.append("timeline.evidence_not_found")
            continue
        role = ev.get("role") if ev.get("role") in ROLES else "unspecified"
        rel = (ev.get("relative_expression") or None)
        if rel and _norm(rel) not in q:
            rel = None
        if rel:
            start, end, precision = resolve_relative(rel, asked_at)
        else:
            d = ev.get("date") if isinstance(ev.get("date"), dict) else {}
            a, b = _parse_date(d.get("start")), _parse_date(d.get("end"))
            if a is None:
                start, end, precision = None, None, "relative_unresolved"
            else:
                start, end, precision = a[0], (b[1] if b else a[1]), ("range" if b else a[2])
        try:
            confidence = max(0.0, min(1.0, float(ev.get("confidence", 0.5))))
        except (TypeError, ValueError):
            confidence = 0.5
        out.append(TimeAnchor(role, start, end, precision, "question", evidence, rel, confidence))  # type: ignore[arg-type]
    return out, warnings


def build_timeline(question: str, *, asked_at: datetime, calendar_date: date | None = None,
                   llm=None) -> LegalTimeline:
    anchors = extract_rule_anchors(question, asked_at=asked_at)
    warnings: list[str] = []
    if llm is not None and needs_llm(question, anchors):
        try:
            raw = llm.complete(TIMELINE_PROMPT, question)
        except Exception:  # noqa: BLE001 — LLM lỗi thì dùng kết quả quy tắc
            raw = ""
        events, ev_warnings = parse_llm_events(raw, question, asked_at=asked_at)
        warnings += ev_warnings
        for ev in events:
            ev_norm = _norm(ev.evidence or "")
            match = next((i for i, a in enumerate(anchors)
                          if a.matched_text and _norm(a.matched_text) in ev_norm), None)
            if match is not None:
                if ev.role != "unspecified":           # LLM chỉ gán vai trò; ngày giữ theo quy tắc
                    anchors[match] = replace(anchors[match], role=ev.role, confidence=max(anchors[match].confidence,
                                                                                         ev.confidence))
            else:
                anchors.append(ev)
    for a in anchors:
        if a.precision == "relative_unresolved":
            warnings.append(f"timeline.relative_unresolved:{a.relative_expression or a.evidence}")
    primary: TimeAnchor
    if calendar_date is not None:
        primary = TimeAnchor("unspecified", calendar_date, calendar_date, "day", "calendar", None, None, 1.0)
        for a in anchors:
            if a.start is not None and not (a.start <= calendar_date <= (a.end or a.start)):
                warnings.append(f"timeline.calendar_conflict:{a.role}")
        anchors = [primary, *anchors]
    elif not any(a.start is not None for a in anchors):
        # không có mốc nào quy được ra ngày (kể cả chỉ có cụm mơ hồ) -> đánh giá theo luật hiện hành, có cảnh báo
        today = local_today(asked_at)
        primary = TimeAnchor("evaluation", today, today, "day", "default", None, None, 1.0)
        anchors = [*anchors, primary]
        warnings.append("timeline.default_today")
    else:
        dated = [a for a in anchors if a.start is not None]
        primary = next((a for a in dated if a.role == "evaluation"), dated[0] if dated else anchors[0])
    return LegalTimeline(tuple(anchors), primary, tuple(dict.fromkeys(warnings)), asked_at)


__all__ = ["TIMELINE_PROMPT", "build_timeline", "needs_llm", "parse_llm_events"]
