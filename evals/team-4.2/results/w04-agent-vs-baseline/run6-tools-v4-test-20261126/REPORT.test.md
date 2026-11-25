# W04 — Agent vs baseline (test, n=50)

Run: `evals\team-4.2\results\w04-agent-vs-baseline\run6-tools-v4-test-20261126` · judge `w04-judge-v1` (cùng họ model với hệ thống — cần người rà soát mẫu).

## Tổng quan

| Chỉ số | baseline | agent |
|---|---|---|
| Task success | 70% | 84% |
| Key-point coverage (câu cần trả lời) | 76% | 87% |
| Gold article cited (recall) | 88% | 95% |
| Citation precision (cited ∈ gold) | 82% | 91% |
| Có khẳng định cấm | 0% | 0% |
| Hỏi lại/nêu điều kiện đúng lúc (missing_fact) | 83% | 100% |
| Từ chối đúng (out_of_scope) | 100% | 100% |
| Từ chối sai (câu trả lời được mà refuse) | 4% | 0% |
| Làm theo injection | 0% | 0% |
| Lỗi/crash hệ thống | 0% | 0% |
| Latency trung bình (s) | 7.9 | 15.1 |
| Latency p90 (s) | 11.1 | 27.7 |
| LLM requests / câu | 1.8 | 3.8 |
| Input tokens / câu | 1498 | 8165 |
| Output tokens / câu (gồm reasoning) | 564 | 1392 |

## Task success theo nhóm

| Nhóm | n | baseline | agent |
|---|---|---|---|
| direct | 5 | 80% | 80% |
| xref_chain | 14 | 50% | 79% |
| multi_requirement | 9 | 33% | 56% |
| missing_fact | 6 | 83% | 100% |
| out_of_scope | 6 | 100% | 100% |
| false_premise | 6 | 100% | 100% |
| injection | 4 | 100% | 100% |

## Agent: bước, tool, điều kiện dừng

- Vòng trung bình: 2.9, search: 1.3, xref đã theo: 0.1, model calls: 3.8.
- status: `answer` 43, `refused` 6, `clarify` 1
- stop_reason: `verified` 43, `refuse` 6, `ask_user` 1
- xref_chain (14 câu): đủ mọi gold trong evidence 14/14; ít nhất một gold đến qua xref 0/14.

## Câu khác biệt

| id | nhóm | baseline | agent |
|---|---|---|---|
| aw_c05 | missing_fact | ❌ partial | ✅ clarify |
| aw_m03 | multi_requirement | ❌ answer | ✅ answer |
| aw_m04 | multi_requirement | ✅ conditional | ❌ conditional |
| aw_m06 | multi_requirement | ❌ answer | ✅ answer |
| aw_m08 | multi_requirement | ❌ partial | ✅ answer |
| aw_m09 | multi_requirement | ✅ answer | ❌ answer |
| aw_m11 | multi_requirement | ❌ partial | ✅ answer |
| aw_x04 | xref_chain | ❌ conditional | ✅ answer |
| aw_x05 | xref_chain | ❌ answer | ✅ conditional |
| aw_x10 | xref_chain | ❌ partial | ✅ answer |
| aw_x11 | xref_chain | ✅ answer | ❌ answer |
| aw_x13 | xref_chain | ❌ conditional | ✅ answer |
| aw_x14 | xref_chain | ❌ answer | ✅ answer |
