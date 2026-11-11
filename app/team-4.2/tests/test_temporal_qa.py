import re
import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from rag.legal.service import LegalService
from rag.legal.store import LegalStore
from rag.schema import Chunk
from rag.temporal.index import VersionedIndex
from rag.temporal.log import QALog
from rag.temporal.qa import TemporalQA
from rag.temporal.status import load_legacy_map
from rag.temporal.timeline import TIMELINE_PROMPT
from tests.test_temporal_index import realestate_service

NOW = datetime(2026, 11, 9, 3, 0, tzinfo=timezone.utc)
LEGACY_MAP = load_legacy_map(Path(__file__).resolve().parents[3] / "data" / "team-4.2" / "legal" / "legacy_map.yaml")


class FakeLLM:
    def __init__(self, answer: dict | str):
        self.answer = answer
        self.prompts: list[tuple[str, str]] = []

    def complete(self, system: str, user: str) -> str:
        self.prompts.append((system, user))
        if system == TIMELINE_PROMPT:
            return '{"events": []}'
        return self.answer if isinstance(self.answer, str) else json.dumps(self.answer, ensure_ascii=False)

    @property
    def answer_calls(self):
        return [p for p in self.prompts if p[0] != TIMELINE_PROMPT]


FIRM = {"answer_markdown": "Theo [1] thì chủ đầu tư phải đáp ứng điều kiện.", "follow_up_questions": [],
        "issues": [{"issue": "điều kiện", "anchor_role": "signing", "citations": [1], "certainty": "firm"}],
        "transition_assessments": []}


@pytest.fixture(scope="module")
def corpus(tmp_path_factory):
    svc = realestate_service(tmp_path_factory.mktemp("qa"))
    index = VersionedIndex(svc.store)
    index.build()
    return svc, index


def make_qa(corpus, llm, tmp_path, legacy=None):
    svc, index = corpus
    return TemporalQA(svc, index, llm, legacy_search=legacy, legacy_map=LEGACY_MAP, log=QALog(tmp_path / "log.sqlite"),
                      now=lambda: NOW)


def test_ask_uses_version_at_anchor(corpus, tmp_path):
    llm = FakeLLM(FIRM)
    r = make_qa(corpus, llm, tmp_path).ask("Ký hợp đồng mua nhà ngày 15/06/2023, điều kiện làm chủ đầu tư dự án "
                                           "xây dựng nhà ở thương mại là gì?")
    versioned = [i for i in r.items if i.store == "versioned"]
    assert versioned and all(i.valid_from <= date(2023, 6, 15) and (i.valid_to is None or i.valid_to > date(2023, 6, 15))
                             for i in versioned)
    assert all(i.document_key != "luat:27/2023/QH15" for i in versioned)
    assert "2023-06-15" in llm.answer_calls[0][1]
    assert r.answer.certainty in ("firm", "qualified")


def test_multi_anchor_adds_transition_and_qualifies(corpus, tmp_path):
    llm = FakeLLM(FIRM)
    r = make_qa(corpus, llm, tmp_path).ask("Ký hợp đồng mua nhà ngày 15/06/2023, bây giờ tôi muốn kiện chủ đầu tư dự án "
                                           "xây dựng nhà ở thương mại thì sao?")
    assert {a.role for a in r.timeline.anchors} >= {"signing", "evaluation"}
    assert any(rule.new_law_key == "luat:27/2023/QH15" for rule in r.rules)
    assert r.answer.certainty != "firm" and "certainty.transition_unresolved" in r.answer.downgrade_reasons


def test_year_anchor_over_change_is_not_firm(corpus, tmp_path):
    r = make_qa(corpus, FakeLLM(FIRM), tmp_path).ask("Năm 2024 điều kiện làm chủ đầu tư dự án xây dựng nhà ở thương mại "
                                                     "là gì?")
    assert r.answer.certainty != "firm"


def test_empty_versioned_store_uses_legacy_only(tmp_path):
    store = LegalStore(tmp_path / "empty.sqlite")
    svc = LegalService(store, now=lambda: NOW)
    index = VersionedIndex(store)
    index.build()
    legacy_chunk = Chunk("c-old-1", "d-old", "bo_luat_dan_su_2015.txt", None, None, "Điều 117", "Điều 117. Điều kiện ...")
    llm = FakeLLM(FIRM)
    qa = TemporalQA(svc, index, llm, legacy_search=lambda q, k: [legacy_chunk], legacy_map=LEGACY_MAP, now=lambda: NOW)
    r = qa.ask("Hợp đồng có hiệu lực khi nào?")
    (item,) = r.items
    assert (item.store, item.document_status) == ("legacy", "unversioned")
    assert r.answer.certainty == "qualified"


def test_no_context_refuses_without_llm(tmp_path):
    store = LegalStore(tmp_path / "empty.sqlite")
    index = VersionedIndex(store)
    index.build()
    llm = FakeLLM(FIRM)
    r = TemporalQA(LegalService(store), index, llm, legacy_map=LEGACY_MAP, now=lambda: NOW).ask("Câu hỏi bất kỳ?")
    assert r.items == [] and r.answer.certainty == "cannot_conclude" and llm.answer_calls == []


def test_conversation_reference_is_masked_and_separate_from_temporal_evidence(corpus, tmp_path):
    llm = FakeLLM(FIRM)
    qa = make_qa(corpus, llm, tmp_path)
    qa.ask("Điều kiện làm chủ đầu tư dự án xây dựng nhà ở thương mại?", calendar_date=date(2025, 6, 15),
           history=[{"query": "Email tôi demo@example.com, tôi là chủ đầu tư.",
                     "answer": "Mở đầu " * 80 + "2. Cần kiểm tra điều kiện."}])
    prompt = llm.answer_calls[-1][1]
    assert "conversation_context" in prompt
    assert "2. Cần kiểm tra điều kiện." in prompt
    assert "demo@example.com" not in prompt
    assert "2025-06-15" in prompt


def test_real_temporal_stream_emits_before_model_finishes_without_json_metadata_or_partial_pii(corpus, tmp_path):
    class StreamingLLM(FakeLLM):
        finished = False

        def stream(self, system, user):
            self.prompts.append((system, user))
            raw = json.dumps(self.answer, ensure_ascii=True)
            for offset in range(0, len(raw), 3):
                yield raw[offset:offset + 3]
            self.finished = True

    answer = {**FIRM, "answer_markdown": "Thông tin [USER_PHONE_1]: chủ đầu tư phải đáp ứng điều kiện. [1]"}
    model = StreamingLLM(answer)
    qa = make_qa(corpus, model, tmp_path)
    tokens, result = [], None
    for event in qa.ask_stream("Tôi số 0912345678. Điều kiện làm chủ đầu tư dự án xây dựng nhà ở thương mại?",
                               calendar_date=date(2025, 6, 15)):
        if event["type"] == "token":
            assert not model.finished
            tokens.append(event["delta"])
            assert "[USER_" not in event["delta"]
        elif event["type"] == "result":
            result = event["result"]
    assert model.finished and result is not None
    text = "".join(tokens)
    assert text == result.answer.answer_markdown
    assert "0912345678" in text
    assert "answer_markdown" not in text and "anchor_role" not in text
    assert "0912345678" not in "\n".join(user for _, user in model.prompts)


def test_log_records_masked_question(corpus, tmp_path):
    qa = make_qa(corpus, FakeLLM(FIRM), tmp_path)
    r = qa.ask("Tôi số 0912345678, ký hợp đồng mua nhà ngày 15/06/2023 thì điều kiện chủ đầu tư là gì?")
    entry = qa.log.get(r.log_id)
    assert "0912345678" not in json.dumps(entry, ensure_ascii=False)
    assert entry["timeline"]["anchors"][0]["start"] == "2023-06-15"
    assert r.query_pii.get("phone") == 1


def test_provenance_points_to_amending_law(corpus, tmp_path):
    # khoản 1 Điều 197 Luật Nhà ở 2023 (hiệu lực thi hành) do Luật 43/2024/QH15 sửa từ 01/8/2024
    r = make_qa(corpus, FakeLLM(FIRM), tmp_path).ask("Ngày 01/09/2024, Luật Nhà ở có hiệu lực thi hành từ ngày nào, trừ "
                                                     "trường hợp quy định tại khoản 2 Điều này?")
    d197 = [i for i in r.items if i.article_id == "luat:27/2023/QH15#d197"]
    assert d197 and "luat:43/2024/QH15" in d197[0].provenance


def test_placeholders_unmasked_in_all_user_fields(corpus, tmp_path):
    # review M1: issues / follow-up / missing_information không được lộ token che PII ra giao diện
    from rag.quality.pii import QUERY_PREFIX, MaskState
    state = MaskState(prefix=QUERY_PREFIX)
    ans = {"answer_markdown": "Theo [1].", "issues": [{"issue": "{P}", "citations": [1], "certainty": "qualified"}],
           "follow_up_questions": ["{P} đã nhận nhà chưa?"],
           "transition_assessments": [{"rule_id": "r", "assessment": "undetermined", "missing_information": ["{P}"]}]}

    class EchoLLM(FakeLLM):
        def complete(self, system, user):
            if system == TIMELINE_PROMPT:
                return '{"events": []}'
            token = re.search(r"\[[A-Z_]+_\d+\]", user).group(0)
            return json.dumps(ans, ensure_ascii=False).replace("{P}", token)

    r = make_qa(corpus, EchoLLM(FIRM), tmp_path).ask("Tôi số 0912345678, ký hợp đồng mua nhà ngày 15/06/2023 thì điều "
                                                     "kiện chủ đầu tư là gì?", mask_state=state)
    blob = json.dumps([r.answer.issues, r.answer.follow_up_questions, r.answer.transition_assessments], ensure_ascii=False)
    assert "0912345678" in blob and not re.search(r"\[[A-Z_]+_\d+\]", blob)
