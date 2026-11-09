# Near-duplicate: đánh giá và giảm báo nhầm

Implementation: [near_duplicate.py](../src/rag/ingest/near_duplicate.py).

## Bản v2 khác baseline thế nào?

Baseline v1 tạo finding khi điểm so sánh toàn bộ token đạt ngưỡng 0.85. V2 giữ điểm này và full diff, bổ sung một biểu diễn nội dung chính, tín hiệu metadata và ưu tiên review. Không thay đổi hoặc xóa nội dung nguồn.

| Tình huống | Chính sách v2 |
|---|---|
| Có số hiệu/cơ quan được xác nhận, khác identity và phạm vi thực sự độc lập | `independent_template`, lưu chẩn đoán trong kết quả so sánh nhưng không tạo finding nghi trùng |
| Chỉ khác document_id, hoặc thiếu metadata đã xác nhận | Không đủ để loại cảnh báo |
| Chỉ khác thời gian, hoặc phạm vi toàn quốc so với địa phương | Không coi là độc lập chỉ vì chuỗi metadata khác nhau |
| Căn cứ/nơi nhận chiếm phần lớn độ giống, nội dung chính khác | Ưu tiên thấp, vẫn giữ review khi thiếu chứng cứ identity |
| Nội dung chính khác số, đơn vị/thời gian hoặc phủ định/nghĩa vụ | Ưu tiên cao; không tự kết luận là conflict |
| Cùng identity và thay đổi quan trọng trong đoạn ngắn dưới ngưỡng lexical | Vẫn tạo review để tránh bỏ sót |
| Chỉ nghi lỗi OCR, confidence thấp và không có thay đổi quan trọng nhận diện được | Ưu tiên thấp, vẫn review; không tự sửa text |

`QualityIssue.severity` là `info` cho gợi ý ưu tiên thấp, `warning` cho các review khác. Evidence có `review_priority`, `routing_category`, `difference_types`, `body_similarity` và lý do. Queue hiện lưu các trường này; UI/caller cần dùng chúng để sắp xếp hoặc lọc, queue chưa tự sắp theo priority.

## Metadata phải được xác nhận

```python
from rag.ingest.near_duplicate import ComparisonMetadata

metadata = ComparisonMetadata(
    external_key="01/2026/QĐ",
    issuer="authority-a",  # inventory nên dùng identity đã chuẩn hóa
    scope=(("province", "province-a"),),
    confirmed=True,
)
```

Không đặt `confirmed=True` chỉ vì parser/OCR đọc được một chuỗi. Caller phải xác nhận identity và chuẩn hóa aliases/phạm vi trong inventory. Số hiệu cần đủ ngữ cảnh, không dùng một số rút gọn tái sử dụng qua nhiều năm như unique key.

Các dimension có thể dùng để xác định phạm vi độc lập là `province`, `jurisdiction`, `locality`, `entity`, `service`, `audience`, với giá trị là category/ID chuẩn hóa. Khác biệt chỉ theo `period` hoặc ngày hiệu lực không đủ. Giá trị toàn cục (`*`, `all`, `toàn quốc`...) và mô tả nhiều giá trị không được tự coi là disjoint.

Nếu cùng document_id hoặc cùng số hiệu/cơ quan đã xác nhận, metadata mâu thuẫn không tự biến thành hai nguồn độc lập. Không dùng policy này để suy diễn quan hệ thay thế, xác định giá trị đúng hoặc vô hiệu hóa văn bản.

## Giảm ảnh hưởng phần mẫu

Detector tạo một scoring view riêng: bỏ các dòng căn cứ và footer nơi nhận nhận diện được khi tính `body_similarity`. Full score và diff vẫn dùng nội dung đầy đủ.

- Giữ nội dung bảng và điều kiện flow trong scoring view.
- Khi gặp heading Điều hoặc dấu hiệu hiệu lực/chuyển tiếp, tiếp tục giữ nội dung dù nằm sau một dòng nơi nhận.
- Không xóa điều khoản thi hành hàng loạt hoặc sửa blocks nguồn.
- Nhận diện boilerplate là heuristic; nội dung dàn trang/OCR khác có thể cần review. Body score thấp không đủ để tự loại review khi identity/phạm vi chưa rõ.

## Huy truyền metadata vào adapter

```python
from rag.ingest.near_duplicate import NearDuplicateDetector

detector = NearDuplicateDetector(
    masker=pii_masker,
    mask_config=mask_config,
    metadata_provider=validated_inventory.__getitem__,
)
result = detector.detect(source, parsed, hint=hint, catalog=repository.snapshot())
queue.enqueue(result.findings)
```

`metadata_provider(document_id)` trả `ComparisonMetadata`. Caller cần hỗ trợ cả document đã lưu và candidate mới; khi chưa có identity có thể truyền metadata chưa xác nhận. Không có provider thì detector vẫn chạy, nhưng metadata đọc được từ hint/catalog chưa được tự gắn nhãn confirmed nên không tự loại cảnh báo theo scope.

Không cần thay bảng SQLite hoặc model versioning cho metadata so sánh này. Metadata phục vụ quyết định có trong fingerprint/config v2; không sao chép tên cơ quan, scope text thô vào issue evidence. Vẫn phải dùng masker cho text, bảng và metadata tự do có thể chứa PII.

## Bộ đánh giá

Dataset: [pairs.json](../../../evals/team-4.2/datasets/near_duplicate/pairs.json).

- 24 cặp tổng hợp, chia dev/test mỗi nhóm 12 cặp, ID nguồn không giao nhau.
- Nhãn nghĩa là **cần review nghi trùng**, không phải “giống câu chữ” hoặc “có mâu thuẫn pháp lý”.
- Có nguồn độc lập cùng mẫu, thay số tiền, phủ định, nội dung ngắn, OCR, nguồn không liên quan, masking collision và metadata thiếu/mâu thuẫn.
- Labels và dữ liệu là ví dụ thủ công, đã được nhìn thấy khi triển khai. Hai nhóm còn dùng chung họ mẫu. Đây không phải blind held-out benchmark hay kiểm chứng độc lập trên corpus luật thật.
- Detector không đọc nhãn/split/lý do gán nhãn; runner chỉ dùng nhãn sau khi có prediction để tính TP/FP/FN/TN.
- Hai policy cùng ngưỡng 0.85, không tăng ngưỡng để giảm báo nhầm. Baseline dùng `BASELINE_CONFIG` v1; mặc định mới dùng v2.

Chạy tại `app/team-4.2`:

```powershell
# Tái tạo fixture tổng hợp, không gọi detector để gán nhãn
.\.venv\Scripts\python.exe -X utf8 -m scripts.build_near_duplicate_fixture

# Chạy cả hai policy trên cùng nguồn/cặp/nhãn
.\.venv\Scripts\python.exe -X utf8 -m scripts.eval_near_duplicate
```

Report mặc định lưu tại [evaluation.json](../../../evals/team-4.2/results/w02-near-duplicate/evaluation.json). Có checksum dataset, detector, evaluator và config; kết quả từng cặp có classification, score, body score, priority và routing. Có thể truyền `--dataset`/`--output` để chạy fixtures thực tế có cùng schema. Không chỉnh threshold dựa vào test set rồi báo kết quả đó như đánh giá độc lập.

## Kết quả trên fixture tổng hợp hiện tại

Hai partition dev/test đều có kết quả sau; bảng tính riêng cho 12 cặp của mỗi partition:

| Policy | TP | FP | FN | TN | Precision | Recall | Hồ sơ cần review |
|---|---:|---:|---:|---:|---:|---:|---:|
| Baseline v1 | 6 | 4 | 1 | 1 | 60% | 85,71% | 10 |
| V2 | 7 | 2 | 0 | 3 | 77,78% | 100% | 9 |

Hai false positives còn lại được báo rõ theo ID: trường hợp chỉ giống phần mẫu nhưng thiếu metadata, và hai nguồn thực tế độc lập nhưng metadata không đủ. Chúng được giữ bảo thủ; không ép loại để làm đẹp số liệu. Cặp chỉ giống boilerplate được gắn priority thấp.

Recall 100% ở đây chỉ áp dụng 7 cặp positive trong mỗi partition tổng hợp. Không suy ra detector không bỏ sót thay đổi quan trọng trên dữ liệu thật. Cần Nhóm 2/mentor gán nhãn độc lập cho fixtures thực, khóa policy trên dev và chạy một test set chưa dùng khi phát triển trước khi nghiệm thu chất lượng.

## Kiểm thử

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_near_duplicate.py tests/test_near_duplicate_policy.py -q
```

Tests bảo vệ việc giữ nguồn, số liệu/phủ định, metadata chưa xác nhận, scope chồng lấn/toàn cục, thay đổi thời gian, giữ điều khoản hiệu lực, ưu tiên OCR, adapter metadata provider và chống rò rỉ identity giữa dev/test.
