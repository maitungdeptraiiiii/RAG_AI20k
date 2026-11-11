# W02-04 — Chunk cố định vs chunk theo cấu trúc

Bộ câu: `evals/team-4.2/datasets/benchmark_doi_thuong_w02.jsonl` (64 câu trong phạm vi). Cùng nguồn, cùng embedding `jina-embeddings-v5-text-small`, ADVANCED=`hyde`, rerank `jev`, MAX_SYLLABLES=300; fixed overlap=50. Chấm theo vị trí văn bản.

## Chỉ mục

| strategy | chunks | âm tiết TB | trung vị | chunk vắt ≥2 Điều | ingest (s) | định vị được |
|---|---|---|---|---|---|---|
| structural | 3422 | 163.0 | 154.0 | 0 | 386.4 | 3422 |
| fixed | 2125 | 299.7 | 300 | 1763 | 452.2 | 2125 |

Kiểm tra cách chấm: với structural, chấm theo vị trí khớp chấm theo `section` ở 256/256 lượt (câu × cấu hình).

## Kết quả

### Tất cả câu

| config | strategy | n | R@5 | Hit@5 | MRR@5 |
|---|---|---|---|---|---|
| bm25 | fixed | 64 | 0.328 | 0.391 | 0.226 |
| bm25 | structural | 64 | 0.258 | 0.281 | 0.157 |
| dense | fixed | 64 | 0.810 | 0.906 | 0.686 |
| dense | structural | 64 | 0.805 | 0.906 | 0.715 |
| hybrid | fixed | 64 | 0.589 | 0.688 | 0.503 |
| hybrid | structural | 64 | 0.677 | 0.781 | 0.515 |
| hybrid+rerank | fixed | 64 | 0.826 | 0.906 | 0.785 |
| hybrid+rerank | structural | 64 | 0.859 | 0.938 | 0.840 |

### Tập test

| config | strategy | n | R@5 | Hit@5 | MRR@5 |
|---|---|---|---|---|---|
| bm25 | fixed | 36 | 0.250 | 0.361 | 0.199 |
| bm25 | structural | 36 | 0.125 | 0.167 | 0.089 |
| dense | fixed | 36 | 0.718 | 0.889 | 0.668 |
| dense | structural | 36 | 0.708 | 0.889 | 0.665 |
| hybrid | fixed | 36 | 0.519 | 0.694 | 0.537 |
| hybrid | structural | 36 | 0.565 | 0.750 | 0.472 |
| hybrid+rerank | fixed | 36 | 0.745 | 0.889 | 0.773 |
| hybrid+rerank | structural | 36 | 0.806 | 0.944 | 0.817 |

### Theo loại câu

| config | type | strategy | n | R@5 | Hit@5 | MRR@5 |
|---|---|---|---|---|---|---|
| bm25 | multi | fixed | 27 | 0.259 | 0.407 | 0.240 |
| bm25 | multi | structural | 27 | 0.093 | 0.148 | 0.102 |
| bm25 | paraphrase | fixed | 37 | 0.378 | 0.378 | 0.215 |
| bm25 | paraphrase | structural | 37 | 0.378 | 0.378 | 0.197 |
| dense | multi | fixed | 27 | 0.698 | 0.926 | 0.693 |
| dense | multi | structural | 27 | 0.685 | 0.926 | 0.671 |
| dense | paraphrase | fixed | 37 | 0.892 | 0.892 | 0.681 |
| dense | paraphrase | structural | 37 | 0.892 | 0.892 | 0.748 |
| hybrid | multi | fixed | 27 | 0.543 | 0.778 | 0.622 |
| hybrid | multi | structural | 27 | 0.531 | 0.778 | 0.506 |
| hybrid | paraphrase | fixed | 37 | 0.622 | 0.622 | 0.416 |
| hybrid | paraphrase | structural | 37 | 0.784 | 0.784 | 0.522 |
| hybrid+rerank | multi | fixed | 27 | 0.735 | 0.926 | 0.796 |
| hybrid+rerank | multi | structural | 27 | 0.778 | 0.963 | 0.793 |
| hybrid+rerank | paraphrase | fixed | 37 | 0.892 | 0.892 | 0.777 |
| hybrid+rerank | paraphrase | structural | 37 | 0.919 | 0.919 | 0.874 |

## Nhận xét

- **Cấu hình chạy thật (hybrid + rerank): structural tốt hơn ở mọi chỉ số.** Tất cả câu: R@5 0.859 vs 0.826, Hit@5
  0.938 vs 0.906, MRR@5 0.840 vs 0.785. Tập test: R@5 0.806 vs 0.745, MRR@5 0.817 vs 0.773.
- **Dense gần như hoà** (R@5 0.805 vs 0.810); structural xếp gold cao hơn một chút ở paraphrase (MRR 0.748 vs 0.681).
- **Hybrid không rerank: structural thắng câu paraphrase** (R@5 0.784 vs 0.622) — chunk cố định trộn nhiều Điều làm
  RRF đẩy chunk lẫn chủ đề lên; câu multi gần hoà.
- **BM25: fixed thắng** (R@5 0.328 vs 0.258, nhất là câu multi 0.259 vs 0.093). Lý do chính là **độ dài**: chunk cố
  định dài gấp ~1,8 lần (300 vs 163 âm tiết) nên top-5 phủ ~1.500 âm tiết so với ~815 — chứa nhiều từ khoá hơn và có thể
  "trúng" 2–3 Điều một lúc (1.763/2.125 chunk cố định vắt ≥2 Điều).
- **Giới hạn**: chỉ 64 câu (test 36): chênh 3–6 điểm ≈ 2–4 câu, chưa đủ để khẳng định ý nghĩa thống kê. So sánh
  không cân bằng ngân sách văn bản — chấm "trúng Điều" thiên vị chunk dài. Chunk cố định còn đưa vào context đoạn của
  Điều không liên quan (xem `examples.md`).
- **Kết luận**: giữ **chunk theo cấu trúc** làm mặc định — tốt hơn ở cấu hình đang chạy thật, mỗi chunk thuộc đúng
  một Điều (trích dẫn sạch, khớp kho có phiên bản), và lợi thế của chunk cố định chỉ xuất hiện ở BM25 đơn lẻ, chủ yếu
  do chunk dài hơn.
- Chưa làm theo checklist W02-04: bộ `w02_quality.jsonl` (bảng / OCR / version) — lần chạy này chỉ dùng bộ câu đời
  thường theo yêu cầu.
