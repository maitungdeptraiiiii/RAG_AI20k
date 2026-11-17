# Bộ nhớ hội thoại chung cho RAG và Think

`POST /api/chat` dùng cùng `session_id` cho cả hai chế độ. `think` và `as_of`
luôn lấy từ request hiện tại; bộ nhớ không khôi phục cấu hình ngày hay bằng chứng
pháp lý của lần tra cứu trước.

## Luồng xử lý

1. UI gửi `session_id`, `turn_id`, câu mới và lịch sử để bootstrap. Server đã có
   phiên thì dùng lịch sử của server, không cho bản UI cũ ghi đè.
2. `ConversationStore` giữ thứ tự các lượt, khóa một request trên mỗi phiên,
   không lưu câu lỗi như một lượt trả lời thành công. JSON và SSE chỉ ghi nhận
   kết quả hoàn tất. Ngắt kết nối không giải phóng phiên khi worker JSON còn chạy.
3. Pipeline che PII trong lịch sử bằng cùng `MaskState` của phiên trước mọi lời
   gọi model. Bộ nhớ gốc và bảng ánh xạ chỉ ở RAM, không thêm log hay API ngoài.
4. `conversation_context` tách `user_statements` có `turn_id`/thứ tự/nguồn `user`
   khỏi `recent_turns.assistant_context_unverified`. Không dùng bản tóm tắt do
   model sinh để ghi đè phát biểu gốc. Các đính chính giữ nguyên thứ tự để model
   xử lý; không tự suy diễn rằng hai phát biểu khác nhau là cùng một dữ kiện.
5. Condense nhận context chung để khôi phục chủ thể và dữ kiện liên quan.
   Think còn nhận context ở plan, assess, compose, verify và temporal review;
   RAG thường nhận context ở generation, TemporalQA thường cũng nhận ở generation.
   Câu trả lời cũ giúp giải quyết “mục 2”, đại từ và câu hỏi làm rõ, không là
   căn cứ pháp lý. Tài liệu và hiệu lực phải truy xuất, kiểm chứng lại.

## Giới hạn có chủ đích

Quy tắc diễn đạt dùng chung ở `rag/generate/style.py` tách trạng thái kiểm tra
nguồn khỏi nội dung trả lời: không lặp nhãn kho/phiên bản nội bộ, không suy diễn
lời giới thiệu tên thành câu hỏi pháp luật về đặt tên. Khi chưa đủ căn cứ, nói
ngắn giới hạn ảnh hưởng đến trường hợp cụ thể. Metadata kiểm chứng và backend
hạ mức chắc chắn vẫn giữ nguyên; không dùng chỉnh sửa cách diễn đạt để bỏ qua
bất định. UI không khẳng định “pháp luật hiện hành” chỉ vì mặc định ngày hôm nay.
Theo yêu cầu hiển thị mới, chat không còn khối mốc pháp lý, không tự thuyết minh
ngày đánh giá/hôm nay/ngày đã chọn. Agent không chèn tiêu đề kết luận theo mốc
hoặc ngày vào thông báo thiếu căn cứ. Timeline, lọc hiệu lực, ngày đã chọn và
certainty vẫn có trong xử lý/API/trace. Chỉ hỏi ngày xảy ra nếu thiếu ngày thực
sự cản trở kết luận; chỉ nói thời điểm trong lập luận khi người dùng hỏi hoặc
thay đổi quy định ảnh hưởng trực tiếp đến câu trả lời.
Kiểm chứng thay đổi ẩn mốc: **67 test offline passed**; kiểm tra cú pháp UI và
chạy riêng hàm render xác nhận timeline bị ẩn, câu hỏi làm rõ vẫn hiển thị.

### Chặn thuyết minh ngày ở đầu ra

`present_answer` bổ sung kiểm tra tại ranh giới `/api/chat`, không chỉ dựa vào
prompt. Nhận diện câu giải thích ngày đánh giá nội bộ và phần lặp giới hạn nguồn
liền sau; giữ nguyên phát biểu pháp lý, trích dẫn, ngày ký/ngày hiệu lực. Nếu đoạn
bị bỏ nêu thiếu căn cứ, giữ một câu giới hạn ngắn không nhắc ngày và không nâng
certainty. Dấu vết lọc nằm trong `trace.presentation`, version
`no-temporal-commentary-v1`. Đây là bộ nhận diện hẹp, không xóa mọi ngày tháng.

JSON và đáp án `done` của SSE dùng cùng bước kiểm tra trước khi lưu lịch sử.
Theo yêu cầu khôi phục streaming, **chế độ thường phát token ngay**, không giữ
toàn bộ chữ đến `done`. `TemporalQA.ask_stream` giải mã tăng dần trường
`answer_markdown` đầu tiên của JSON; issues/transition metadata không vào token.
Placeholder PII chia token được giữ đến khi đủ rồi mở che. `ask` và `ask_stream`
dùng chung phần truy xuất, hiệu lực, parse/enforce và log cuối.

Prompt yêu cầu không sinh thuyết minh ngày trong đáp án; metadata chỉ nằm ở
các trường kiểm tra. Chữ đang stream là nội dung đang sinh; nếu model vẫn vi phạm
cách diễn đạt, đáp án cuối được làm sạch và UI cập nhật lại ở `done`. Không thể
cam kết tuyệt đối không có câu thừa trong bản đang stream chỉ bằng prompt.
Think vẫn chỉ phát nội dung sau kiểm chứng. Lịch sử assistant cũ được làm sạch
khi tạo context, phát biểu user không bị chỉnh sửa. Thời gian chuẩn bị/truy xuất
trước khi sinh đáp án chưa bị loại bỏ bởi thay đổi này.

Bộ hồi quy streaming mới đạt **73 passed** (offline): mọi ranh giới chia token
JSON/escape/Unicode, token đầu trước khi model xong, không lộ metadata/PII,
JSON/SSE, chế độ thường và Think. Fixture API được cô lập khỏi Qdrant của app.

`test_answer_presentation.py` tái hiện nguyên văn đoạn người dùng gửi, token bị
chia giữa câu, JSON/SSE, cả hai chế độ, lưu memory, giữ uncertainty và ngày luật
thực chất. Nhóm hồi quy presentation/conversation/routing/stream/dated/temporal QA
đạt **63 passed**; không gọi model thật. Backend dev không bật reload đã được
restart; kiểm tra localhost: UI 200, chat với câu hỏi rỗng 400, khối mốc bị ẩn.
Bộ hồi quy cho thay đổi cách diễn đạt (temporal answer/QA, agent, dated HTTP,
conversation và stream): **83 passed**; JavaScript UI qua kiểm tra cú pháp.
Không gọi model thật để đánh giá cách diễn đạt trong đợt sửa này.

- RAM một process: tối đa 500 phiên, hết hạn sau 2 giờ không hoạt động; phiên
  đang xử lý không bị eviction. Restart/expiry bootstrap lại từ lịch sử UI.
- Mỗi phiên giữ tối đa 64 lượt và 128.000 ký tự; bỏ đáp án cũ trước khi bỏ phát
  biểu người dùng. Mỗi câu hỏi tối đa 8.000, mỗi đáp án lưu tối đa 16.000 ký tự.
- Context model có tối đa 24.000 ký tự phát biểu người dùng và 24.000 ký tự đáp án
  của 8 lượt gần nhất. Đây là giới hạn ký tự, không phải phép đếm token chính xác.
- `truncated`, `answer_truncated`, `assistant_history_truncated` thể hiện phần
  thiếu. Response có `conversation.history_turns/truncated`; UI báo khi context
  bị cắt. Prompt yêu cầu hỏi lại nếu tham chiếu thiếu hoặc mơ hồ.
- Không thêm model call cho memory. Prompt có thể dài hơn trước. Không bảo đảm
  nhớ vô hạn hoặc bảo đảm model hiểu đúng mọi đính chính/đổi chủ đề chỉ nhờ prompt.
- Nếu chạy nhiều worker/process, cần thay store RAM và PII state bằng kho dùng
  chung cùng khóa theo phiên (ví dụ Redis); bản hiện tại dành cho server một process.

## Kiểm chứng

`tests/test_conversation.py` kiểm tra luồng thường → Think → thường qua JSON/SSE,
giữ ngày ở phạm vi request, phát biểu cách hơn 3 lượt, danh sách sau 250 ký tự,
provenance của đính chính, che PII đến mọi role, khôi phục lịch sử, cách ly phiên,
idempotency, budget, lỗi và hủy request. `test_temporal_qa.py` kiểm tra context
được che PII và tách khỏi bằng chứng temporal. Test dùng model giả để kiểm tra
đường truyền và hợp đồng dữ liệu; không đại diện đánh giá ngữ nghĩa model thật.

Kết quả ngày 10/11/2026: **95 passed** (83,11 giây), kiểm tra cú pháp JavaScript
UI thành công. Lệnh hồi quy:

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
python -m pytest -p pytest_asyncio.plugin app/team-4.2/tests/test_conversation.py app/team-4.2/tests/test_condense.py app/team-4.2/tests/test_think_routing.py app/team-4.2/tests/test_agent.py app/team-4.2/tests/test_dated_agent_e2e.py app/team-4.2/tests/test_temporal_qa.py app/team-4.2/tests/test_stream.py -q
```
