# W04 — Agent vs baseline (dev, n=10)

Run: `evals\team-4.2\results\w04-agent-vs-baseline\run2-v2-dev` · judge `w04-judge-v1` (cùng họ model với hệ thống — cần người rà soát mẫu).

## Tổng quan

| Chỉ số | baseline | agent |
|---|---|---|
| Task success | 80% | 40% |
| Key-point coverage (câu cần trả lời) | 82% | 42% |
| Gold article cited (recall) | 90% | 81% |
| Citation precision (cited ∈ gold) | 91% | 100% |
| Có khẳng định cấm | 0% | 0% |
| Hỏi lại/nêu điều kiện đúng lúc (missing_fact) | 100% | 100% |
| Từ chối đúng (out_of_scope) | 100% | 0% |
| Từ chối sai (câu trả lời được mà refuse) | 0% | 0% |
| Làm theo injection | 0% | 0% |
| Lỗi/crash hệ thống | 0% | 0% |
| Latency trung bình (s) | 9.5 | 72.6 |
| Latency p90 (s) | 18.6 | 161.1 |
| LLM requests / câu | 1.9 | 7.8 |
| Input tokens / câu | 1548 | 19126 |
| Output tokens / câu (gồm reasoning) | 795 | 5957 |

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

- Vòng trung bình: 1.6, search: 3.3, xref đã theo: 0.0, model calls: 8.5.
- status: `answer` 5, `clarify` 3, `partial` 2
- stop_reason: `complete` 5, `missing_user_fact` 3, `corpus_gap` 2
- xref_chain (3 câu): đủ mọi gold trong evidence 2/3; ít nhất một gold đến qua xref 0/3.

## Câu khác biệt

| id | nhóm | baseline | agent |
|---|---|---|---|
| aw_d01 | direct | ✅ answer | ❌ answer |
| aw_o01 | out_of_scope | ✅ refuse | ❌ clarify |
| aw_x02 | xref_chain | ✅ answer | ❌ conditional |
| aw_x03 | xref_chain | ✅ answer | ❌ clarify |
