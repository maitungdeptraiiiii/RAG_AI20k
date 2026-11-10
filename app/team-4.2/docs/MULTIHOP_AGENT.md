# Think: multi-hop agent v1

Think là chế độ opt-in trên composer. Mặc định tắt vẫn chạy `RAGPipeline` cũ;
`think: true` chọn `AgentPipeline` dùng chung index và cache, nhưng state/ngân sách/client
có giới hạn nằm riêng trong từng request. Không cần ingest lại để bật agent.

## Luồng thực thi

```text
condense một lần (nếu có history)
→ pin snapshot và lập requirements/dependency
→ search Dense hoặc hybrid + rerank theo query
→ đọc các Điều tìm được và đánh giá nguyên văn bằng chứng
→ tìm phần thiếu / theo xref trong vòng tiếp theo
→ compose các claims có evidence IDs
→ verify từng claim và toàn bộ requirements
→ render citation bằng code → gửi đáp án cuối
```

JSON và SSE đi qua cùng `run_events()`. SSE phát tiến độ trước; kênh token chỉ phát
văn bản cuối sau bước kiểm chứng. Khi kết nối bị đóng, generator ngừng lập lịch công việc
ở điểm yield tiếp theo. Không bảo đảm hủy ngay một SDK call đang chạy; timeout của backend
và kiểm tra deadline giới hạn thời gian chờ ở các ranh giới công việc.

`HybridRetriever.search_candidates()` không tự decompose/rewrite/listwise. Agent không
tạm thay đổi các thuộc tính dùng chung. Các query khác nhau giữ score và provenance riêng;
không cộng xác suất Jev chéo query. Pool đầu giữ nhánh câu gốc trước, rồi bổ sung nhánh nhu cầu.
Các vòng sau có quota riêng và không xóa bằng chứng cũ khỏi ledger.

## Trạng thái kết quả

| status | Ý nghĩa |
|---|---|
| answer | Tất cả requirements và dependency được đánh giá đủ, claim/citation qua verifier |
| partial | Chỉ xuất các claim đã được hỗ trợ; nêu các nhu cầu chưa giải quyết |
| clarify | Cần làm rõ dữ kiện hoặc thu hẹp câu hỏi |
| abstain | Chưa đủ bằng chứng để xuất kết luận được kiểm chứng |
| error | Công cụ/schema/ngân sách/snapshot khiến run không hoàn tất an toàn |

`trace.agent.verified` là kết quả kiểm tra nội bộ, không phải chứng nhận đúng pháp lý.
`answer` có nghĩa đáp ứng checklist trong corpus snapshot, không chứng minh corpus chứa
tất cả văn bản liên quan. `Answer.refused` legacy vẫn giữ invariant REFUSAL; client mới
phải đọc thêm `status` và `trace.agent.stop_reason`.

## Cấu hình

Các biến `AGENT_*` chỉ áp dụng khi bật Think. Defaults trong `Settings`:

| Biến | Default |
|---|---:|
| AGENT_MAX_ROUNDS | 3 |
| AGENT_MAX_SEARCHES | 8 |
| AGENT_INITIAL_SUBQUERIES | 3 |
| AGENT_FOLLOWUP_SEARCHES | 2 |
| AGENT_CANDIDATES_PER_SEARCH | 10 |
| AGENT_INITIAL_POOL_SIZE | 30 |
| AGENT_NEW_UNITS_PER_ROUND | 10 |
| AGENT_MAX_UNITS | 50 |
| AGENT_MAX_XREF_DEPTH | 2 |
| AGENT_XREFS_PER_ROUND | 6 |
| AGENT_MAX_XREF_TARGETS | 12 |
| AGENT_MAX_REQUIREMENTS | 8 |
| AGENT_MAX_MODEL_CALLS | 24 |
| AGENT_MAX_SERVICE_REQUESTS | 240 |
| AGENT_MAX_MODEL_BYTES | 600000 |
| AGENT_MAX_INPUT_CHARS | 60000 |
| AGENT_MAX_OUTPUT_TOKENS | 3000 |
| AGENT_DEADLINE_S | 180 |
| AGENT_RETRIEVAL_MODE | dense |

Mỗi round là một đợt fetch, không phải một Điều hay một model call. Lần tìm bổ sung do
verifier yêu cầu cũng tiêu quota rounds/searches hiện có. Xref depth là số cạnh trên một
đường dẫn; không đồng nhất với round. Tối đa một lần repair đáp án, sau đó verify lại.

Model gateway đếm logical calls, cache hits, các lần gọi LLM không cache và token usage
khi SDK trả usage. Tổng byte đầu vào/đầu ra được giới hạn riêng; byte không đồng nghĩa
token. Admission giữ chỗ cho finalization, giới hạn output mỗi lần gọi. Cache hit không
tái tạo token usage không được provider báo. `service_requests` đếm embedding/Jev thực
gọi qua các adapter tích hợp, tách khỏi LLM counters. Không diễn giải số query thành số HTTP request.

OpenAI bounded completion, Jina/OpenAI embedding và Jev tích hợp dùng client riêng theo
request, tắt retry ngầm và áp timeout theo thời gian còn lại. Giữ cache và index dùng chung.
Backend custom chỉ có protocol `search`/`complete` cần tự bảo đảm timeout; deadline tổng
được kiểm tra ở ranh giới và không phải cơ chế preempt mọi Python call.

## Snapshot và xref

V1 chạy ở `snapshot_only`: hash chính xác nội dung/metadata chunks được pin cho mỗi run.
Không tự bịa `unit_revision_id`, ngày hiệu lực hoặc giả định văn bản đang có hiệu lực.
Nếu index đổi trong lúc còn phải search, run dừng thay vì trộn thế hệ. Index build lỗi
không được dùng để cấp snapshot agent mới. Nội dung đã pin là các `Chunk` bất biến.

Xref index được dựng lười trong request từ các Điều đã đọc. Mỗi cạnh có source chunk,
offset/span nguyên văn, target unit và trạng thái resolve. Hiện hỗ trợ dẫn chiếu `Điều N`
trong cùng văn bản, tên luật chuẩn từ filename, và các viết tắt BLDS/BLHS/BLTTDS/BLTTHS/
BLLĐ/BLHH khi ánh xạ không mơ hồ. Hai văn bản cùng tên sẽ giữ ambiguity.

Không đoán đích khi tên luật chưa xác định hoặc target không có. Không tự theo reverse
xref, không coi xref là kết luận pháp lý, không tự hợp nhất văn bản sửa đổi. Parser chưa
bao phủ đầy đủ khoảng Điều, danh sách số không lặp chữ “Điều”, dẫn chiếu khoản/điểm ngầm,
hoặc mọi cách viết tắt. Đây là giới hạn cần đo riêng, không phải mọi tham chiếu đều resolve được.

Materialize toàn bộ chunks cùng Điều trong snapshot, giữ source IDs. Context là một bộ
excerpt có giới hạn theo `CONTEXT_MAX_BLOCKS/WORDS`, có cờ truncated; cửa sổ ưu tiên chunk
thực sự khớp retrieval thay vì luôn đầu Điều. Verifier chỉ được dùng excerpt đã cung cấp.
Điều kiện nằm ngoài cửa sổ có thể chưa được tìm thấy; không được coi absence là đã phủ hết ngoại lệ.

## Kiểm chứng và trace

Planner, assessor, composer và verifier có schema riêng. Code kiểm tra ID/dependency,
mọi requirement phải được đánh giá đúng một lần, quote phải đúng nguyên văn, và nguồn
phải nằm trong bundle đã gửi. Composer không được tự đánh số citation. Verifier cần xác
nhận mỗi claim với các span nguồn cụ thể; code render `[n]` sau khi đã chốt nguồn cuối.

Các output lỗi schema, ID bịa, quote không tồn tại, HTML/ảnh nhúng hoặc claim bị bác bỏ
không được phát như đáp án. Model verifier vẫn có thể sai cùng generator: tests với fake
model chỉ kiểm tra cơ chế. Cần benchmark thật và review độc lập để đánh giá chất lượng.

Trace chứa config/prompt version, snapshot hash, requirements, assessments, nguồn gốc
evidence theo round/query/xref, claims, quotes đã kiểm chứng, budget, stop reason và progress
events. Không ghi chain-of-thought, API key hoặc raw exception từ SDK ra response agent.

## Chạy và đánh giá

Tại gốc repo, đã cấu hình `.env` và dependencies:

```powershell
$env:PYTHONPATH='app/team-4.2/src'
$env:PYTHONIOENCODING='utf-8'
python scripts/team-4.2/ask.py --think --trace-out .test-tmp/agent-response.json "Câu hỏi nhiều bước"
python evals/team-4.2/runners/run_agent_eval.py --limit 1 --out evals/team-4.2/results/<thu-muc-moi>
python -m pytest app/team-4.2/tests -q
```

Runner agent chỉ đưa `question` vào runtime; gold/reference dùng ở phía chấm sau khi
run kết thúc. Giữ metric retrieval theo candidate pool và context cuối riêng biệt. Vì
context cuối trong response chỉ giữ nguồn được trích dẫn, metric đó đo bộ nguồn phục vụ
đáp án đã xuất, không phải tất cả excerpt assessor từng xem. Runner yêu cầu thư mục output
mới, checkpoint mỗi câu và không tự tuyên bố correctness từ verdict của agent.

Mốc kiểm tra implementation: bộ tests offline; smoke/API thật chỉ khi có chấp thuận phù hợp.
Không coi một smoke test là bằng chứng tăng accuracy. Temporal integration end-to-end,
quality-approved generation publication và expert-reviewed holdout vẫn là phần cần hoàn thiện
trước khi cam kết trả lời theo pháp luật hiện hành.
