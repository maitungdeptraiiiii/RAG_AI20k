# Benchmark truy xuất căn cứ để phân tích hợp đồng lao động

Trạng thái: **v1 draft, chạy được; chưa có duyệt nhãn độc lập**.
Đây là benchmark riêng của dự án theo quy trình đánh giá truy xuất có đáp án nguồn;
không phải bộ dữ liệu pháp lý được cơ quan chuyên môn chứng nhận.

Đầu vào là **điều khoản hợp đồng + concept đã được cung cấp + bối cảnh**.
Đầu ra cần đánh giá là bằng chứng pháp lý. Không chấm hỏi đáp, kết luận vi phạm,
phát hiện concept từ hợp đồng hoặc rule engine. Không sửa bridge, concepts.yaml
hay graph đang phục vụ ứng dụng.

## Dữ liệu và phạm vi

- 74 tình huống tổng hợp, 34 family: 22 case dev và 52 case test.
- Các biến thể cùng family, kể cả các mốc thời gian của một bài toán, nằm chung một split.
  Đơn vị độc lập để tính khoảng tin cậy là family, không phải từng biến thể.
- 6 văn bản: BLLĐ 45/2019, NĐ 145/2020, TT 10/2020, NĐ 38/2022, 74/2024 và 293/2025.
  Corpus có toàn bộ các phiên bản cấp Điều của 6 văn bản, gồm 1.115 passage cố định.
  Có nhiều điều không phải đáp án để làm nhiễu; không chỉ index những đoạn gold.
- Có quy tắc đơn, điều kiện, ngoại lệ, nhiều căn cứ, qua nhiều điều/văn bản,
  mốc thay đổi lương tối thiểu, thiếu ngày áp dụng và nội dung ngoài quan hệ lao động.
- Ngày trong context là ngày cần kiểm tra việc thực hiện/kỳ lương; không tự coi là ngày ký.
  Nhóm lương vùng đã cho sẵn vùng I: **không đánh giá phân loại địa bàn từ địa chỉ**.
- Chưa bao phủ đầy đủ BHXH, phụ lục nghề/địa bàn, xử phạt, lao động đặc thù,
  hợp đồng thật nguyên bộ hoặc mọi quan hệ giữa các điều khoản.

Nguồn tham khảo phương pháp:
[LegalBench-RAG](https://arxiv.org/abs/2408.10343) về truy xuất đoạn căn cứ pháp lý;
[BEIR](https://github.com/beir-cellar/beir) về đánh giá truy xuất.
Ngưỡng pass dưới đây là quy ước riêng được đóng băng cho thí nghiệm này.

## Một case pass khi nào?

Với case `ready`, tất cả điều kiện sau phải đúng:

1. Tìm đủ **mọi nhóm bằng chứng bắt buộc**. Một nhóm chấp nhận một trong các nguồn
   thay thế đã ghi trong `alternatives`; không cần tìm tất cả các nguồn thay thế.
2. Trả các passage trong corpus chuẩn, bao phủ 100% span gold, đúng version_key.
   Chỉ tìm đúng tài liệu hoặc ghi tên số điều mà không cung cấp đoạn bằng chứng là chưa đủ.
   Nhiều passage liên tiếp được ghép để bao phủ một span; không được để hở đoạn giữa.
3. Mọi passage trả về đều có hiệu lực tại `assessment_date`, theo khoảng `[from,to)`.
   Trả đúng căn cứ rồi kèm một bản hết hiệu lực cũng fail trong track này.
4. Không quá **20 passage và 16.000 byte UTF-8** nội dung bằng chứng.
   Ngân sách byte là cách đếm xác định, độc lập tokenizer/model; không gọi đây là 4.000 token.
   Passage trùng bị từ chối; phần overlap vẫn tính chi phí vì được gửi cho downstream.
5. Nguồn `needs_review`/`conflicted` phải được khai báo trong `source_warnings`.
   Việc khai báo giúp pass kiểm tra tính minh bạch, không biến nguồn đó thành đã xác minh.
6. Đầu ra khai báo đúng `decision`; với case `ready`, `missing_context` phải rỗng.

Với case `insufficient_context`, phải chỉ ra đúng trường còn thiếu, không tự dùng ngày hôm nay.
Với case `out_of_scope`, phải trả trạng thái đó và không đưa căn cứ lao động như căn cứ áp dụng.
Trả danh sách rỗng cho mọi case không thể đạt benchmark.

Ví dụ: case về ngày phép sau 5 năm làm việc cần cả căn cứ phép năm và căn cứ tăng
theo thâm niên. Tìm được một trong hai chỉ đạt coverage 0,5 và **fail** case.
Đó là pass về truy xuất; không chấm phép so sánh số ngày trong hợp đồng.

## Tệp và định dạng adapter

- `inputs.jsonl`: dữ liệu public duy nhất được đưa vào retriever. ID là mã vô nghĩa,
  không để tên case như “thiếu ngày” làm lộ đáp án.
- `gold.jsonl`: nhãn riêng của evaluator; có đoạn trích, offset ký tự, version_key,
  checksum nguồn, lý do và các nhóm bằng chứng. Không đưa vào prompt/index.
- `manifest.json`: snapshot, checksum bundle và từng file, phạm vi corpus, split, ngân sách.
- `seeds.json`, `build_seeds.py`: tài liệu tác giả tạo bộ dữ liệu; **không** dùng làm
  bảng neo cho structural hoặc dữ liệu tuning của test.
- `corpus.generated.jsonl`: corpus chuẩn, sinh lại từ bundle; được gitignore để tránh
  lưu lặp toàn bộ nội dung luật. `verify` kiểm checksum trước khi chấm.

Mỗi dòng prediction có dạng:

```json
{"id":"ce1-001-01","decision":"ready","evidence":["<passage_id>"],"missing_context":[],"source_warnings":[],"latency_ms":12.3}
```

`evidence` phải xếp theo thứ tự ưu tiên truy xuất. `source_warnings` có thể chứa
`needs_review` hoặc `conflicted`. Decision là `ready`, `insufficient_context`,
`out_of_scope`; lỗi adapter dùng `error` và được tính fail.

Structural có thể map `ProvisionVersion` và span sang passage chuẩn; HippoRAG
nên index chính những passage này, giữ passage_id trong metadata; hybrid dùng
cùng tập đó. Nếu structural dùng anchors, anchors phải lấy từ cấu hình hệ thống
được đóng băng độc lập trước khi mở test, không lấy từ gold của benchmark.

Tất cả cùng nhận concept + mô tả ngắn không chứa anchors/ngưỡng luật. Structural
có thể chỉ dùng concept, HippoRAG dùng thêm lời văn điều khoản. Đây là so sánh
các cấu hình thực tế trên một input contract chung; không phải thí nghiệm cô lập
chỉ riêng thuật toán graph. Muốn cô lập tác động từng trường cần tạo track ablation riêng.

Adapter Python do cấu hình cung cấp cần có:

```python
def build_retriever(corpus_path, config):
    # Index/load this exact corpus, then return an object with:
    # retrieve(case: dict) -> dict containing decision/evidence/missing_context/source_warnings
    # Optional close() releases resources. Never read gold/seeds/review files.
    ...
```

Runner giữ riêng checksum adapter, config, phiên bản Python, thời gian khởi tạo,
thời gian mỗi case và manifest hash. Config nên ghi model/checkpoint, prompt hash,
seed, tham số graph, embedding và các ngưỡng. Không ghi API key vào config.
Adapter structural đã có tại `structural_adapter.py`, dùng danh mục neo gốc
ngày 2026-11-14 được chiếu sang JSON trong `configs/structural-concepts-v1.json`.
Không sửa anchors theo gold. Adapter chỉ đọc graph đang publish, pin build/snapshot,
kiểm checksum và ánh xạ lời văn graph sang passage chuẩn. Cấu hình ở
`configs/structural-v1.json`; mật khẩu lấy từ môi trường. HippoRAG/hybrid chưa có adapter.

```powershell
python evals/team-4.2/contract_graph_benchmark/run_adapter.py --adapter evals/team-4.2/contract_graph_benchmark/structural_adapter.py --config evals/team-4.2/contract_graph_benchmark/configs/structural-v1.json --split all --out .test-tmp/contract-structural
python evals/team-4.2/contract_graph_benchmark/benchmark.py score --run .test-tmp/contract-structural/run.json --split test --out .test-tmp/contract-structural/test.json
```

## Chạy từ thư mục gốc dự án

Tool benchmark chỉ cần Python standard library; không cần Neo4j hoặc API key để chấm.
Các retriever thực tế có dependency/key riêng.

```powershell
# Nếu máy chưa có corpus local:
python scripts/team-4.2/legal_corpus.py unpack

# Khôi phục đúng snapshot đã đóng băng trong manifest, không lấy CURRENT mới tùy ý:
python evals/team-4.2/contract_graph_benchmark/benchmark.py prepare
python evals/team-4.2/contract_graph_benchmark/benchmark.py verify

# Baseline TF-IDF đơn giản, không đọc gold để truy xuất:
python evals/team-4.2/contract_graph_benchmark/benchmark.py lexical --out .test-tmp/contract-lexical
python evals/team-4.2/contract_graph_benchmark/benchmark.py score --run .test-tmp/contract-lexical/run.json --split test --out .test-tmp/contract-lexical/test.json

# Retriever của bạn: thay adapter/config bằng file thực tế đã chuẩn bị:
python evals/team-4.2/contract_graph_benchmark/run_adapter.py --adapter PATH_TO_ADAPTER.py --config PATH_TO_CONFIG.json --split dev --out .test-tmp/contract-system-dev
python evals/team-4.2/contract_graph_benchmark/benchmark.py score --run .test-tmp/contract-system-dev/run.json --split dev --out .test-tmp/contract-system-dev/evaluation.json
```

Tune trên dev. Đóng băng config rồi chạy lại adapter với `--split test` và chấm test.
Giữ mọi lần chạy, không chọn seed có kết quả đẹp nhất; model ngẫu nhiên nên chạy
nhiều seed đã định trước. Cùng corpus, ngân sách, phần cứng và chính sách cache khi
so tốc độ. Không đưa thời gian build/index vào latency truy vấn; báo riêng.

Nếu đã có predictions từ pipeline khác, tạo `run.json` với các trường `system`,
`config`, `manifest_sha256` (hash bytes của manifest.json), `predictions_file`;
sau đó gọi `score`. Thiếu prediction bị tính fail; trùng ID hoặc ID lạ làm run không hợp lệ.
Exit code 0 của `score` nghĩa là chấm xong, **không** nghĩa là mọi case đều pass;
đọc `summary.passed`, `summary.total` và `score_status`.

So sánh cặp report:

```powershell
python evals/team-4.2/contract_graph_benchmark/benchmark.py compare REPORT_A.json REPORT_B.json
```

Report có pass rate, family-macro pass rate và khoảng tin cậy bootstrap theo family,
coverage nhóm bằng chứng, coverage@5/@10 theo từng case, lỗi temporal, lỗi cụ thể
và latency. Các case phân loại/thiếu thông tin được báo riêng theo category; chỉ số
`ready_case_retrieval_pass_rate` tách phần truy xuất khỏi tổng điểm.
Không báo precision/nDCG vì nhãn ở đây chưa phải toàn bộ tập đoạn liên quan.
Chưa có ngưỡng “hệ thống đủ tốt để triển khai”; pass từng case và đạt nghiệm thu
toàn hệ thống là hai quyết định khác nhau.

## Kiểm chứng bộ chấm và duyệt nhãn

```powershell
python -m pytest app/team-4.2/tests/test_contract_graph_benchmark.py -q
python evals/team-4.2/contract_graph_benchmark/benchmark.py oracle --out .test-tmp/contract-oracle
python evals/team-4.2/contract_graph_benchmark/benchmark.py score --run .test-tmp/contract-oracle/run.json --split all --out .test-tmp/contract-oracle/check.json
python evals/team-4.2/contract_graph_benchmark/review_packet.py --out .test-tmp/contract-review
```

Oracle đọc gold và đạt 74/74 để kiểm chứng corpus/ngân sách/scorer nhất quán.
**Đây không phải kết quả chất lượng của bất kỳ graph/model nào.**
Baseline TF-IDF hiện có kết quả tạm thời 43/52 test, family-macro 80,43%;
xem `validation/lexical-test.json`. Chưa dùng kết quả đó để điều chỉnh nhãn/ngưỡng.

Tất cả gold hiện mang nhãn `source_checked_draft`. Trích đoạn đã được kiểm tra
khớp text nguồn gốc bất biến trong corpus; chưa chứng minh đủ mọi ngoại lệ pháp lý
hoặc đúng toàn bộ xử lý phiên bản. Cần người có chuyên môn rà soát độc lập qua
`review.md`, sửa nhãn nếu cần và ghi reviewer/date/note/decision vào template.
Sau đó lưu ledger thật thành `reviews.jsonl` trong thư mục benchmark.
Không điền reviewer thay người duyệt. Approval gắn hash của đúng gold row;
sửa nhãn sẽ làm approval cũ mất hiệu lực. Quy trình này là audit nội bộ,
không phải xác thực chữ ký người duyệt.

Trước khi đủ duyệt, scorer luôn ghi `provisional_pending_independent_review`.
Muốn đổi nhãn/corpus khi đang tác giả hóa có thể dùng `prepare --rebuild`;
sau khi bắt đầu so sánh chính thức phải phát hành phiên bản benchmark mới.
Tập test hiện có trong repo nên là **held-out theo quy trình**, không phải test bí mật.
Cần bổ sung hợp đồng thật đã ẩn danh và nhãn độc lập trước khi gọi đây là benchmark
đại diện cho chất lượng phân tích hợp đồng trong thực tế.
