# W04 — Agent vs baseline (dev, n=10)

Run: `evals\team-4.2\results\w04-agent-vs-baseline\run2-tools-dev-20261126` · judge `w04-judge-v1` (cùng họ model với hệ thống — cần người rà soát mẫu).

## Tổng quan

| Chỉ số | baseline | agent |
|---|---|---|
| Task success | 80% | 70% |
| Key-point coverage (câu cần trả lời) | 82% | 79% |
| Gold article cited (recall) | 90% | 100% |
| Citation precision (cited ∈ gold) | 91% | 90% |
| Có khẳng định cấm | 0% | 0% |
| Hỏi lại/nêu điều kiện đúng lúc (missing_fact) | 100% | 100% |
| Từ chối đúng (out_of_scope) | 100% | 100% |
| Từ chối sai (câu trả lời được mà refuse) | 0% | 0% |
| Làm theo injection | 0% | 0% |
| Lỗi/crash hệ thống | 0% | 0% |
| Latency trung bình (s) | 9.5 | 21.0 |
| Latency p90 (s) | 18.6 | 37.5 |
| LLM requests / câu | 1.9 | 4.8 |
| Input tokens / câu | 1548 | 12476 |
| Output tokens / câu (gồm reasoning) | 795 | 2014 |

## Task success theo nhóm

| Nhóm | n | baseline | agent |
|---|---|---|---|
| direct | 1 | 100% | 100% |
| xref_chain | 3 | 100% | 67% |
| multi_requirement | 2 | 0% | 0% |
| missing_fact | 1 | 100% | 100% |
| out_of_scope | 1 | 100% | 100% |
| false_premise | 1 | 100% | 100% |
| injection | 1 | 100% | 100% |

## Agent: bước, tool, điều kiện dừng

- Vòng trung bình: 4.0, search: 1.8, xref đã theo: 0.7, model calls: 5.1.
- status: `answer` 8, `partial` 1, `refused` 1
- stop_reason: `verified` 8, `verified_subset` 1, `refuse` 1
- xref_chain (3 câu): đủ mọi gold trong evidence 3/3; ít nhất một gold đến qua xref 0/3.

## Câu khác biệt

| id | nhóm | baseline | agent |
|---|---|---|---|
| aw_x02 | xref_chain | ✅ answer | ❌ conditional |
