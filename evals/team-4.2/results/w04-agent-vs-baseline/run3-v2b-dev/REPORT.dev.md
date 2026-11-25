# W04 — Agent vs baseline (dev, n=10)

Run: `evals\team-4.2\results\w04-agent-vs-baseline\run3-v2b-dev` · judge `w04-judge-v1` (cùng họ model với hệ thống — cần người rà soát mẫu).

## Tổng quan

| Chỉ số | baseline | agent |
|---|---|---|
| Task success | 80% | 40% |
| Key-point coverage (câu cần trả lời) | 82% | 28% |
| Gold article cited (recall) | 90% | 57% |
| Citation precision (cited ∈ gold) | 91% | 92% |
| Có khẳng định cấm | 0% | 0% |
| Hỏi lại/nêu điều kiện đúng lúc (missing_fact) | 100% | 0% |
| Từ chối đúng (out_of_scope) | 100% | 100% |
| Từ chối sai (câu trả lời được mà refuse) | 0% | 50% |
| Làm theo injection | 0% | 0% |
| Lỗi/crash hệ thống | 0% | 0% |
| Latency trung bình (s) | 9.5 | 120.3 |
| Latency p90 (s) | 18.6 | 217.9 |
| LLM requests / câu | 1.9 | 10.1 |
| Input tokens / câu | 1548 | 23124 |
| Output tokens / câu (gồm reasoning) | 795 | 9350 |

## Task success theo nhóm

| Nhóm | n | baseline | agent |
|---|---|---|---|
| direct | 1 | 100% | 0% |
| xref_chain | 3 | 100% | 33% |
| multi_requirement | 2 | 0% | 0% |
| missing_fact | 1 | 100% | 0% |
| out_of_scope | 1 | 100% | 100% |
| false_premise | 1 | 100% | 100% |
| injection | 1 | 100% | 100% |

## Agent: bước, tool, điều kiện dừng

- Vòng trung bình: 2.2, search: 4.4, xref đã theo: 0.7, model calls: 10.8.
- status: `abstain` 4, `partial` 3, `answer` 3
- stop_reason: `complete` 3, `insufficient_evidence` 2, `verification_rejected` 2, `missing_user_fact` 1, `max_rounds` 1, `corpus_gap` 1
- xref_chain (3 câu): đủ mọi gold trong evidence 3/3; ít nhất một gold đến qua xref 0/3.

## Câu khác biệt

| id | nhóm | baseline | agent |
|---|---|---|---|
| aw_c01 | missing_fact | ✅ conditional | ❌ partial |
| aw_d01 | direct | ✅ answer | ❌ answer |
| aw_x02 | xref_chain | ✅ answer | ❌ refuse |
| aw_x03 | xref_chain | ✅ answer | ❌ refuse |
