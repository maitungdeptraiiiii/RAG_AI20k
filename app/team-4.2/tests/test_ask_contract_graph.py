"""Đầu tới cuối: soát hợp đồng (ghi oplog, dựng đồ thị) rồi agent trả lời trên đồ thị vừa dựng."""
import json

from rag.contracts.graph.agent import AGENT_PROMPT, ask_contract_graph
from tests.test_bridge_check import AT, ScriptLLM, contract


class BothLLM(ScriptLLM):
    def __init__(self, agent_steps):
        super().__init__()
        self.agent_steps, self.agent_seen = list(agent_steps), []

    def complete(self, system, user):
        if system.startswith(AGENT_PROMPT[:40]):
            self.agent_seen.append(json.loads(user))
            return json.dumps(self.agent_steps.pop(0), ensure_ascii=False)
        return super().complete(system, user)


def test_check_then_agent_on_fresh_graph():
    llm = BothLLM([{"thought": "tìm Điều 2", "tool": "find_concept", "args": {"concept_id": "leave.annual"}},
                   {"final": {"answer": "Được nghỉ phép 08 ngày/năm (Điều 2).", "path": ["c1:p0.d2@1"],
                              "law": [], "confidence": "answer"}}])
    answer, report = ask_contract_graph(llm, contract(), "Tôi được nghỉ phép bao nhiêu ngày?", at=AT)
    assert answer.confidence == "answer" and answer.path[0]["node_id"] == "c1:p0.d2@1"
    assert answer.stats["backend"] == "memory" and report.stats["graph_backend"] == "memory"
    ctx = llm.agent_seen[0]["context"]
    assert any(c["concept_id"] == "leave.annual" and c["about"] == "c1:p0.d2@1" for c in ctx["concepts"])
    found = llm.agent_seen[1]["steps"][0]["result"]["instances"]
    assert [i["about"] for i in found] == ["c1:p0.d2@1"]
