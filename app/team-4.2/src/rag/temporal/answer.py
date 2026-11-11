"""Hợp đồng với LLM cho hỏi đáp theo mốc: dựng prompt (mốc, căn cứ kèm phiên bản và trạng thái, quy định chuyển
tiếp), đọc JSON trả về, và để backend hạ mức chắc chắn khi kết luận dựa vào nguồn chưa xác minh, quy định chuyển tiếp
chưa giải quyết, hoặc luật đổi bên trong khoảng mốc."""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import date
from typing import Literal

from rag.temporal.models import LegalTimeline, TransitionRule
from rag.generate.style import ANSWER_STYLE

Certainty = Literal["firm", "qualified", "cannot_conclude"]
_RANK = {"firm": 2, "qualified": 1, "cannot_conclude": 0}
_RESOLVED = ("not_applicable", "applicable")
_ASSESSMENTS = ("not_applicable", "potentially_applicable", "applicable", "undetermined")

SYSTEM_PROMPT = """Bạn là trợ lý pháp lý về pháp luật Việt Nam. Kết luận pháp lý chỉ dùng căn cứ trong NGỮ CẢNH, trích dẫn bằng [n]. Dữ kiện người dùng tự nêu trong câu hỏi/lịch sử được dùng để hiểu vụ việc hoặc trả lời về hội thoại; không phải căn cứ pháp lý.
Quy tắc bắt buộc:
- Không tự chọn phiên bản luật: mỗi căn cứ đã được hệ thống gắn khoảng hiệu lực và mốc áp dụng; dùng đúng căn cứ cho đúng mốc.
- Phân tích từng vấn đề pháp lý theo đúng thời điểm và căn cứ tương ứng; ghi vai trò thời điểm vào issues.anchor_role để kiểm tra nội bộ. Không yêu cầu nêu mốc trong answer_markdown. Không mặc định luật tại ngày ký điều chỉnh mọi vấn đề phát sinh sau đó.
- Căn cứ source_kind=legacy hoặc source_kind=reference chỉ để tham khảo, không làm căn cứ duy nhất cho kết luận pháp lý chắc chắn.
- Căn cứ có trạng thái khác verified: nêu rõ giới hạn.
- Với mỗi QUY ĐỊNH CHUYỂN TIẾP: xác định (1) có liên quan đến loại sự kiện đang xét không, (2) người dùng đã cung cấp đủ dữ kiện chưa, (3) có ngoại lệ có thể đổi kết luận không. Thiếu dữ kiện thì đánh giá "undetermined" và đặt câu hỏi bổ sung, không suy diễn.
- Nếu mốc chỉ có năm/tháng mà luật thay đổi trong khoảng đó, trình bày khác biệt và yêu cầu ngày cụ thể nếu kết luận phụ thuộc vào nó.
Trả về DUY NHẤT một JSON. BẮT BUỘC ghi answer_markdown đầu tiên để streaming;
nội dung trường này chỉ là đáp án cho người dùng, không thuyết minh metadata/mốc.
Các thông tin kiểm tra thời điểm/nguồn chỉ ghi ở issues và transition_assessments phía sau:
{"answer_markdown": "...", "issues": [{"issue": "...", "anchor_role": "...", "citations": [1], "certainty": "firm|qualified|cannot_conclude", "limitation": "..."}],
 "transition_assessments": [{"rule_id": "...", "assessment": "not_applicable|potentially_applicable|applicable|undetermined", "reasons": ["..."], "citations": [1], "missing_information": ["..."]}],
 "follow_up_questions": ["..."]}""" + ANSWER_STYLE


@dataclass(frozen=True)
class ContextItem:
    n: int
    store: Literal["versioned", "legacy", "reference"]
    document_key: str | None
    title: str
    article_id: str | None
    section: str
    text: str
    valid_from: date | None
    valid_to: date | None
    document_status: str
    provision_status: str | None
    provenance: tuple[str, ...]
    anchor_roles: tuple[str, ...]
    chunk_id: str


@dataclass
class TemporalAnswer:
    answer_markdown: str
    issues: list[dict] = field(default_factory=list)
    transition_assessments: list[dict] = field(default_factory=list)
    follow_up_questions: list[str] = field(default_factory=list)
    certainty: Certainty = "qualified"
    downgrade_reasons: list[str] = field(default_factory=list)
    raw_ok: bool = True


def _fmt_anchor(a) -> str:
    when = "chưa xác định" if a.start is None else (a.start.isoformat() if a.start == a.end else
                                                     f"{a.start.isoformat()} → {a.end.isoformat()}")
    return f"- {a.role}: {when} (độ chính xác {a.precision}, nguồn {a.source})"


def build_messages(question: str, timeline: LegalTimeline, items: Sequence[ContextItem],
                   rules: Sequence[TransitionRule]) -> tuple[str, str]:
    parts = [f"CÂU HỎI: {question}", "", "MỐC PHÁP LÝ:", *(_fmt_anchor(a) for a in timeline.anchors)]
    if timeline.warnings:
        parts += ["Cảnh báo về mốc: " + "; ".join(timeline.warnings)]
    parts += ["", "NGỮ CẢNH:"]
    for it in items:
        valid = ("effective_period=unknown" if it.valid_from is None else
                 f"hiệu lực từ {it.valid_from.isoformat()} đến {it.valid_to.isoformat() if it.valid_to else 'nay'}")
        store = f"source_kind={it.store}; metadata_only"
        status = f"trạng thái văn bản: {it.document_status}" + (
            f"; điều khoản: {it.provision_status}" if it.provision_status else "")
        prov = f"; sửa đổi bởi: {', '.join(it.provenance)}" if it.provenance else ""
        parts += [f"[{it.n}] ({store}) {it.title} — {it.section} | {valid} | {status} | mốc: "
                  f"{', '.join(it.anchor_roles) or '—'}{prov}", it.text, ""]
    if rules:
        parts += ["QUY ĐỊNH CHUYỂN TIẾP (cần đánh giá):"]
        for r in rules:
            parts += [f"[{r.rule_id}] {r.source_article} — văn bản {r.source_document_key}; luật cũ {r.old_law_key or '—'} "
                      f"→ luật mới {r.new_law_key or '—'} (hiệu lực từ {r.new_law_effective_from or '—'}); "
                      f"liên quan mốc: {', '.join(r.related_roles) or '—'}", r.text, ""]
    return SYSTEM_PROMPT, "\n".join(parts)


def parse_answer(raw: str) -> TemporalAnswer:
    text = raw or ""
    block = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL) or re.search(r"(\{.*\})", text, re.DOTALL)
    data = None
    if block:
        try:
            data = json.loads(block.group(1))
        except ValueError:
            data = None
    if not isinstance(data, dict) or not isinstance(data.get("answer_markdown"), str):
        return TemporalAnswer(answer_markdown=text.strip(), certainty="qualified", raw_ok=False)
    issues = [i for i in data.get("issues") or [] if isinstance(i, dict)]
    for i in issues:
        if i.get("certainty") not in _RANK:
            i["certainty"] = "qualified"
    certainty = min((i["certainty"] for i in issues), key=_RANK.get, default="qualified")
    return TemporalAnswer(
        answer_markdown=data["answer_markdown"], issues=issues,
        transition_assessments=[t for t in data.get("transition_assessments") or [] if isinstance(t, dict)],
        follow_up_questions=[str(q) for q in data.get("follow_up_questions") or [] if str(q).strip()],
        certainty=certainty, raw_ok=True)


def _unverified(item: ContextItem) -> bool:
    return (item.store in ("legacy", "reference") or item.document_status != "verified"
            or item.provision_status not in (None, "verified"))


def _cite_num(value) -> int | None:
    """Số trích dẫn: nhận int hoặc chuỗi số ("1", "[1]"); bỏ bool và giá trị khác."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().strip("[]").isdigit():
        return int(value.strip().strip("[]"))
    return None


def enforce(answer: TemporalAnswer, items: Sequence[ContextItem], rules: Sequence[TransitionRule],
            timeline: LegalTimeline, *, year_change: bool) -> TemporalAnswer:
    by_n = {it.n: it for it in items}
    reasons: list[str] = []

    def keep(m: re.Match) -> str:
        return m.group(0) if int(m.group(1)) in by_n else ""

    text = re.sub(r"\[(\d+)\]", keep, answer.answer_markdown)

    assessments = {t.get("rule_id"): dict(t) for t in answer.transition_assessments if t.get("rule_id")}
    for t in assessments.values():
        if t.get("assessment") not in _ASSESSMENTS:
            t["assessment"] = "undetermined"
    for r in rules:
        assessments.setdefault(r.rule_id, {"rule_id": r.rule_id, "assessment": "undetermined",
                                           "reasons": ["not_assessed"], "citations": [], "missing_information": []})
    unresolved = any(t["assessment"] not in _RESOLVED for rid, t in assessments.items()
                     if rid in {r.rule_id for r in rules})

    issues = []
    for issue in answer.issues:
        issue = dict(issue)
        cites = [c for c in (_cite_num(x) for x in issue.get("citations") or []) if c in by_n]
        issue["citations"] = cites
        certainty = issue.get("certainty", "qualified")
        if not cites:
            certainty = "cannot_conclude"
            reasons.append("certainty.no_valid_citation")
        if certainty == "firm":
            if any(_unverified(by_n[n]) for n in cites):
                certainty = "qualified"
                reasons.append("certainty.unverified_source")
            if unresolved:
                certainty = "qualified"
                reasons.append("certainty.transition_unresolved")
            if year_change:
                certainty = "qualified"
                reasons.append("certainty.version_changes_within_anchor")
        issue["certainty"] = certainty
        issues.append(issue)

    cited_any = any(int(n) in by_n for n in re.findall(r"\[(\d+)\]", text))
    if issues:
        overall = min((i["certainty"] for i in issues), key=_RANK.get)
    else:
        overall = "qualified" if cited_any else "cannot_conclude"
        if not cited_any:
            reasons.append("certainty.no_valid_citation")
    if overall == "firm" and not answer.raw_ok:
        overall = "qualified"
    return replace(answer, answer_markdown=text, issues=issues, transition_assessments=list(assessments.values()),
                   certainty=overall, downgrade_reasons=list(dict.fromkeys(reasons)))


__all__ = ["ContextItem", "SYSTEM_PROMPT", "TemporalAnswer", "build_messages", "enforce", "parse_answer"]
