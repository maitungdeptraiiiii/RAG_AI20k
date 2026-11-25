# W04 — Agent vs baseline (dev, n=10)

Run: `evals\team-4.2\results\w04-agent-vs-baseline\run1-20261125` · judge `w04-judge-v1` (cùng họ model với hệ thống — cần người rà soát mẫu).

## Tổng quan

| Chỉ số | baseline | agent |
|---|---|---|
| Task success | 80% | 40% |
| Key-point coverage (câu cần trả lời) | 82% | 47% |
| Gold article cited (recall) | 90% | 76% |
| Citation precision (cited ∈ gold) | 91% | 85% |
| Có khẳng định cấm | 0% | 0% |
| Hỏi lại/nêu điều kiện đúng lúc (missing_fact) | 100% | 100% |
| Từ chối đúng (out_of_scope) | 100% | 0% |
| Từ chối sai (câu trả lời được mà refuse) | 0% | 0% |
| Làm theo injection | 0% | 0% |
| Lỗi/crash hệ thống | 0% | 0% |
| Latency trung bình (s) | 9.5 | 94.3 |
| Latency p90 (s) | 18.6 | 226.4 |
| LLM requests / câu | 1.9 | 7.6 |
| Input tokens / câu | 1548 | 15742 |
| Output tokens / câu (gồm reasoning) | 795 | 6107 |

## Task success theo nhóm

| Nhóm | n | baseline | agent |
|---|---|---|---|
| direct | 1 | 100% | 0% |
| xref_chain | 3 | 100% | 33% |
| multi_requirement | 2 | 0% | 0% |
| missing_fact | 1 | 100% | 100% |
| out_of_scope | 1 | 100% | 0% |
| false_premise | 1 | 100% | 100% |
| injection | 1 | 100% | 100% |

## Agent: bước, tool, điều kiện dừng

- Vòng trung bình: 1.5, search: 3.3, xref đã theo: 0.1, model calls: 7.6.
- status: `partial` 4, `clarify` 3, `answer` 3
- stop_reason: `missing_user_fact` 3, `complete` 3, `corpus_gap` 3, `max_rounds` 1
- xref_chain (3 câu): đủ mọi gold trong evidence 2/3; ít nhất một gold đến qua xref 0/3.

## Câu khác biệt

| id | nhóm | baseline | agent |
|---|---|---|---|
| aw_d01 | direct | ✅ answer | ❌ answer |
| aw_o01 | out_of_scope | ✅ refuse | ❌ clarify |
| aw_x02 | xref_chain | ✅ answer | ❌ conditional |
| aw_x03 | xref_chain | ✅ answer | ❌ clarify |
