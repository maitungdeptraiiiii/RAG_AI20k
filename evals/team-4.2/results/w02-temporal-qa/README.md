# W02 — Hỏi đáp theo mốc thời gian (phần 2): kết quả đánh giá

Ngày chạy: 2026-11-10. Bộ câu hỏi: `evals/team-4.2/datasets/temporal_qa_realestate.jsonl` (18 câu, lĩnh vực bất động sản:
Luật Nhà ở 2014/2023, Luật Kinh doanh bất động sản 2014/2023, Luật Đất đai 2013/2024; mốc chuyển giao 01/08/2024 theo
Luật 43/2024/QH15). Kỳ vọng phiên bản lấy theo hiệu lực pháp lý thực tế, không lấy theo kết quả chạy.

Runner: `evals/team-4.2/runners/run_temporal_eval.py`.

- **Độ đúng mốc**: tập (vai trò, từ ngày, đến ngày) do quy tắc dựng ra khớp đúng với kỳ vọng.
- **Độ đúng phiên bản**: tại mỗi mốc, mọi văn bản kỳ vọng phải nằm trong top-10 và không có văn bản bị cấm (văn bản
  chưa/không còn hiệu lực tại mốc).

## Kết quả

| Kho | Độ đúng mốc | Độ đúng phiên bản | Ghi chú |
|---|---|---|---|
| Kho mẫu (fixture 8 văn bản, test tự động) | 18/18 (100%) | 18/18 (100%) | `tests/test_temporal_eval.py` |
| Kho thật đã crawl từ vbpl (kèm kho cũ 6 Bộ luật) | 18/18 (100%) | 17/18 (94,4%) | t17: xem bên dưới |

**Có LLM** (TemporalQA thật trên kho thật, 18 câu): firm 0, qualified 7, cannot_conclude 11, lỗi 0.
**Số câu `firm` dựa trên căn cứ chưa xác minh: 0** (yêu cầu bắt buộc).

Trong cả 18 câu, không có lần nào văn bản hết hiệu lực hoặc chưa có hiệu lực tại mốc lọt vào ngữ cảnh. Bước lọc theo
hiệu lực trước khi xếp hạng hoạt động đúng.

Chi tiết: `report.json` (từng câu: mốc dựng được, văn bản tìm thấy theo vai trò) và `answers.jsonl` (câu trả lời, mức
chắc chắn, lý do hạ mức, nguồn, quy định chuyển tiếp).

## Cập nhật: dùng bộ tìm kiếm của pipeline chính (`hybrid/`)

Kho luật có phiên bản giờ tìm bằng đúng `HybridRetriever` của pipeline chính, cùng cấu hình `.env`:

- BM25 + Dense (Jina v5, có cache embedding);
- HyDE trên nhánh dense (theo `ADVANCED`);
- gộp RRF, rerank Jev, gộp chunk theo Điều.

Mỗi nhánh tìm kiếm chỉ chấm và trả các chunk có hiệu lực tại mốc (`ValidityFilteredArm`), nên RRF, HyDE và reranker
không bao giờ thấy phiên bản sai.

| Chạy trên kho thật, 18 câu | BM25 (trước) | Hybrid + HyDE + rerank (sau) |
|---|---|---|
| Độ đúng mốc | 18/18 | 18/18 |
| Độ đúng phiên bản (top-10) | 17/18 | **18/18** |
| `cannot_conclude` | 11 | **6** |
| `qualified` / `firm` | 7 / 0 | 11 / 1 |
| `firm` dựa trên căn cứ chưa xác minh | 0 | 0 |
| Thời gian trả lời trung bình mỗi câu (gồm LLM) | không đo | 16,7 s |
| Dựng chỉ mục lần đầu | ~1 phút | ~8 phút |

Ghi chú khi đọc bảng:

- **Top-10 ở bản hybrid tính theo Điều**, các chunk cùng Điều được gộp lại. Bản BM25 tính theo chunk.
- **Dựng chỉ mục lần đầu ~8 phút** vì phải embed toàn kho qua Jina và bị giới hạn tốc độ (429). Các lần sau dùng
  cache embedding và Qdrant trên đĩa (`<legal-dir>/vector`).
- **Chỉ số `firm` dựa trên căn cứ chưa xác minh đã được tính lại** theo nguồn mà câu trả lời thực sự dẫn. Runner bản
  đầu đếm mọi nguồn có trong ngữ cảnh, nên lần chạy hybrid báo nhầm 1 câu (t13). Câu t13 chỉ dẫn [1], [2], [4], cả
  ba đều `verified`; hai điều Bộ luật Hình sự từ kho cũ không được dẫn.

Thay đổi rõ nhất:

- **t01** giờ tìm được Điều 21 Luật Nhà ở 2014 (điều kiện làm chủ đầu tư), nên không còn trả "chưa đủ căn cứ".
- **t17** có đủ cả Luật Đất đai 2013 và 2024 trong khoảng năm 2024: gộp theo Điều giữ được cả hai phiên bản.

Còn yếu:

- **t14, t16:** điều luật trả lời trực tiếp vẫn chưa lọt vào top.
- **t15:** lấy được Bộ luật Dân sự 2005 (còn hiệu lực ngày 05/08/2016, đúng phiên bản) nhưng câu trả lời dẫn số
  trích dẫn không hợp lệ, nên bị hạ xuống `cannot_conclude`.
- **Chưa dùng cho kho luật có phiên bản:** các phương pháp nâng cao dựng chỉ mục riêng (SPLADE, ColBERT, contextual).
  Hiện `ADVANCED=hyde` nên cấu hình đang giống hệt pipeline chính.

Chạy lại: thêm `--hybrid` vào lệnh dưới đây (cần `.env`).

## Ví dụ

- **t10** — "Ký hợp đồng mua nhà ngày 15/06/2023, bây giờ tôi muốn kiện chủ đầu tư…":
  - Hai mốc được dựng: Ký kết 15/06/2023 và Đánh giá 10/11/2026.
  - Tại mốc ký, ngữ cảnh lấy Luật Nhà ở 2014. Tại mốc đánh giá, lấy Luật Nhà ở 2023.
  - Đưa vào 2 quy định chuyển tiếp: Điều 198 Luật Nhà ở 2023 và Điều 83 Luật Kinh doanh bất động sản 2023.
  - Câu trả lời nêu rõ: hợp đồng xác lập theo luật cũ tiếp tục thực hiện theo luật cũ, không mặc định áp dụng luật mới.
- **t09** — "Cá nhân nước ngoài mua nhà ở ngày 01/01/2018…":
  - Trả lời đúng "tối đa 50 năm kể từ ngày được cấp Giấy chứng nhận".
  - Căn cứ là Điều 161 Luật Nhà ở 2014, bản có hiệu lực tại mốc.
  - Mức qualified.
- **t01** — Ký hợp đồng 15/06/2023, hỏi điều kiện làm chủ đầu tư:
  - Mô hình trả lời "chưa đủ căn cứ" thay vì bịa.
  - Lý do: top-6 không có Điều 21 Luật Nhà ở 2014, là điều trả lời trực tiếp câu hỏi (xem giới hạn 1).

## Giới hạn và việc nên làm tiếp

1. **Tìm kiếm còn yếu (nguyên nhân chính của 11 câu cannot_conclude).**
   - Kho mới mặc định chỉ dùng BM25; dense chỉ bật khi đặt `LEGAL_DENSE=1`.
   - Hậu quả: điều luật trả lời trực tiếp có thể không lọt vào top-6. Ví dụ t01 thiếu Điều 21, t12 thiếu khoản 1
     Điều 45 Luật Đất đai 2024.
   - Lỗi này nằm ở bước tìm kiếm, không phải ở phiên bản: những chunk tìm được đều đúng phiên bản.
   - Nên làm tiếp: bật dense cho kho mới, rerank, và mở rộng truy vấn theo tên điều.
2. **t17** (khoảng 01/01–31/12/2024, chuyển nhượng quyền sử dụng đất):
   - Kỳ vọng cả Luật Đất đai 2013 lẫn 2024 đều có trong top-10.
   - Trên kho thật, các luật khác chiếm chỗ, nên Luật Đất đai 2013 không lọt top-10.
   - Không có văn bản sai hiệu lực nào lọt vào: đây cũng là lỗi xếp hạng.
3. **Mô hình tự hạ mức khá thận trọng.**
   - Một số câu có đủ căn cứ verified vẫn ra cannot_conclude mà không có lý do hạ mức từ backend.
   - Ví dụ t02: câu trả lời đúng nội dung Điều 36 Luật Nhà ở 2023, nhưng mô hình đánh một issue là cannot_conclude
     vì thiếu nội dung khoản được dẫn chiếu.
   - Backend không bao giờ nâng mức chắc chắn. Đây là thiết kế có chủ đích: an toàn hơn chính xác.
4. **Kho cũ gây nhiễu.**
   - Kho cũ đôi khi thêm điều luật không liên quan (ví dụ Bộ luật Hình sự cho câu hỏi về chủ đầu tư).
   - Các điều này luôn được gắn nhãn "unversioned", và mô hình không dùng chúng làm căn cứ chính.
5. **Phạm vi đánh giá.**
   - Mốc chỉ được dựng bằng quy tắc, không có LLM (`llm=None`).
   - Phần LLM gán vai trò đã có unit test, nhưng chưa được đo trên bộ này.
   - 18 câu mới chỉ là bộ khởi đầu.

## Chạy lại

```bash
# kho mẫu, không gọi mạng
python evals/team-4.2/runners/run_temporal_eval.py --fixture
# kho thật + LLM (cần .env)
python evals/team-4.2/runners/run_temporal_eval.py --legal-dir <DATA_DIR>/legal --llm \
  --out evals/team-4.2/results/w02-temporal-qa/report.json \
  --answers evals/team-4.2/results/w02-temporal-qa/answers.jsonl
```
