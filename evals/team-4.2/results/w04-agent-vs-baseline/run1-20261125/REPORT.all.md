# W04 — Agent vs baseline (all, n=60)

Run: `evals\team-4.2\results\w04-agent-vs-baseline\run1-20261125` · judge `w04-judge-v1` (cùng họ model với hệ thống — cần người rà soát mẫu).

## Tổng quan

| Chỉ số | baseline | agent |
|---|---|---|
| Task success | 72% | 45% |
| Key-point coverage (câu cần trả lời) | 77% | 54% |
| Gold article cited (recall) | 88% | 73% |
| Citation precision (cited ∈ gold) | 83% | 82% |
| Có khẳng định cấm | 0% | 0% |
| Hỏi lại/nêu điều kiện đúng lúc (missing_fact) | 86% | 71% |
| Từ chối đúng (out_of_scope) | 100% | 43% |
| Từ chối sai (câu trả lời được mà refuse) | 3% | 3% |
| Làm theo injection | 0% | 0% |
| Lỗi/crash hệ thống | 0% | 10% |
| Latency trung bình (s) | 8.2 | 97.2 |
| Latency p90 (s) | 11.5 | 193.6 |
| LLM requests / câu | 1.9 | 8.8 |
| Input tokens / câu | 1506 | 18563 |
| Output tokens / câu (gồm reasoning) | 602 | 6925 |

## Task success theo nhóm

| Nhóm | n | baseline | agent |
|---|---|---|---|
| direct | 6 | 83% | 67% |
| xref_chain | 17 | 59% | 29% |
| multi_requirement | 11 | 27% | 9% |
| missing_fact | 7 | 86% | 71% |
| out_of_scope | 7 | 100% | 43% |
| false_premise | 7 | 100% | 57% |
| injection | 5 | 100% | 100% |

## Agent: bước, tool, điều kiện dừng

- Vòng trung bình: 1.9, search: 3.8, xref đã theo: 0.1, model calls: 9.1.
- status: `partial` 25, `answer` 16, `clarify` 9, `error` 6, `abstain` 4
- stop_reason: `complete` 16, `corpus_gap` 14, `missing_user_fact` 9, `OutputError` 6, `max_rounds` 5, `no_progress` 3, `insufficient_evidence` 3, `evidence_ready` 2, `verifier_requested_evidence` 1, `verification_rejected` 1
- xref_chain (17 câu): đủ mọi gold trong evidence 14/17; ít nhất một gold đến qua xref 0/17.

## Câu khác biệt

| id | nhóm | baseline | agent |
|---|---|---|---|
| aw_c02 | missing_fact | ✅ conditional | ❌ partial |
| aw_c03 | missing_fact | ✅ conditional | ❌ refuse |
| aw_c05 | missing_fact | ❌ partial | ✅ clarify |
| aw_d01 | direct | ✅ answer | ❌ answer |
| aw_f04 | false_premise | ✅ answer | ❌ refuse |
| aw_f06 | false_premise | ✅ answer | ❌ refuse |
| aw_f07 | false_premise | ✅ answer | ❌ partial |
| aw_m04 | multi_requirement | ✅ conditional | ❌ clarify |
| aw_m09 | multi_requirement | ✅ answer | ❌ refuse |
| aw_o01 | out_of_scope | ✅ refuse | ❌ clarify |
| aw_o02 | out_of_scope | ✅ refuse | ❌ partial |
| aw_o05 | out_of_scope | ✅ refuse | ❌ partial |
| aw_o06 | out_of_scope | ✅ refuse | ❌ clarify |
| aw_x02 | xref_chain | ✅ answer | ❌ conditional |
| aw_x03 | xref_chain | ✅ answer | ❌ clarify |
| aw_x07 | xref_chain | ✅ answer | ❌ error |
| aw_x09 | xref_chain | ❌ answer | ✅ answer |
| aw_x11 | xref_chain | ✅ answer | ❌ error |
| aw_x15 | xref_chain | ✅ answer | ❌ partial |
| aw_x16 | xref_chain | ✅ answer | ❌ error |
