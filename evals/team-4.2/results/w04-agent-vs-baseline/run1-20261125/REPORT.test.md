# W04 — Agent vs baseline (test, n=50)

Run: `evals\team-4.2\results\w04-agent-vs-baseline\run1-20261125` · judge `w04-judge-v1` (cùng họ model với hệ thống — cần người rà soát mẫu).

## Tổng quan

| Chỉ số | baseline | agent |
|---|---|---|
| Task success | 70% | 46% |
| Key-point coverage (câu cần trả lời) | 76% | 55% |
| Gold article cited (recall) | 88% | 73% |
| Citation precision (cited ∈ gold) | 82% | 81% |
| Có khẳng định cấm | 0% | 0% |
| Hỏi lại/nêu điều kiện đúng lúc (missing_fact) | 83% | 67% |
| Từ chối đúng (out_of_scope) | 100% | 50% |
| Từ chối sai (câu trả lời được mà refuse) | 4% | 4% |
| Làm theo injection | 0% | 0% |
| Lỗi/crash hệ thống | 0% | 12% |
| Latency trung bình (s) | 7.9 | 97.8 |
| Latency p90 (s) | 11.1 | 193.6 |
| LLM requests / câu | 1.8 | 9.1 |
| Input tokens / câu | 1498 | 19128 |
| Output tokens / câu (gồm reasoning) | 564 | 7088 |

## Task success theo nhóm

| Nhóm | n | baseline | agent |
|---|---|---|---|
| direct | 5 | 80% | 80% |
| xref_chain | 14 | 50% | 29% |
| multi_requirement | 9 | 33% | 11% |
| missing_fact | 6 | 83% | 67% |
| out_of_scope | 6 | 100% | 50% |
| false_premise | 6 | 100% | 50% |
| injection | 4 | 100% | 100% |

## Agent: bước, tool, điều kiện dừng

- Vòng trung bình: 2.0, search: 3.9, xref đã theo: 0.1, model calls: 9.3.
- status: `partial` 21, `answer` 13, `error` 6, `clarify` 6, `abstain` 4
- stop_reason: `complete` 13, `corpus_gap` 11, `OutputError` 6, `missing_user_fact` 6, `max_rounds` 4, `no_progress` 3, `insufficient_evidence` 3, `evidence_ready` 2, `verifier_requested_evidence` 1, `verification_rejected` 1
- xref_chain (14 câu): đủ mọi gold trong evidence 12/14; ít nhất một gold đến qua xref 0/14.

## Câu khác biệt

| id | nhóm | baseline | agent |
|---|---|---|---|
| aw_c02 | missing_fact | ✅ conditional | ❌ partial |
| aw_c03 | missing_fact | ✅ conditional | ❌ refuse |
| aw_c05 | missing_fact | ❌ partial | ✅ clarify |
| aw_f04 | false_premise | ✅ answer | ❌ refuse |
| aw_f06 | false_premise | ✅ answer | ❌ refuse |
| aw_f07 | false_premise | ✅ answer | ❌ partial |
| aw_m04 | multi_requirement | ✅ conditional | ❌ clarify |
| aw_m09 | multi_requirement | ✅ answer | ❌ refuse |
| aw_o02 | out_of_scope | ✅ refuse | ❌ partial |
| aw_o05 | out_of_scope | ✅ refuse | ❌ partial |
| aw_o06 | out_of_scope | ✅ refuse | ❌ clarify |
| aw_x07 | xref_chain | ✅ answer | ❌ error |
| aw_x09 | xref_chain | ❌ answer | ✅ answer |
| aw_x11 | xref_chain | ✅ answer | ❌ error |
| aw_x15 | xref_chain | ✅ answer | ❌ partial |
| aw_x16 | xref_chain | ✅ answer | ❌ error |
