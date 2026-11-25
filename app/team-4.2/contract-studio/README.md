# Contract Studio

UI React/Vite được tích hợp từ `Legal-contract-ui`, chạy tại **`/contract-studio/`**.
Các trang `/`, `/contracts/ask`, `/upload`, `/review` vẫn giữ nguyên. Trang soát cũ `/contracts` đã gỡ: đường dẫn này chuyển sang `/contract-studio/` (`?cid=<id>` thành `?contract=<id>`).

## Chạy

Từ thư mục này:

```powershell
npm ci
npm run build
```

Sau đó khởi động lại backend bằng lệnh hiện có, tại gốc repository:

```powershell
python app/team-4.2/ui/server.py
```

Mở `http://127.0.0.1:8501/contract-studio/`. Thư mục `dist/` là output build,
không commit. Server trả hướng dẫn build nếu chưa có output. Không cần Express,
Gemini server hay API key riêng cho frontend.

Khi phát triển: `npm run dev`; Vite proxy `/api` tới backend ở cổng 8501.
Cấu hình model, OCR và Neo4j tiếp tục dùng cấu hình của backend.

## Luồng thật

1. Chọn file PDF, DOCX, TXT, Markdown hoặc ảnh (50 MB, tối đa 150 trang theo backend).
   Hợp đồng chính và phụ lục cần nằm trong cùng file; không có cơ chế tự ghép file.
2. Upload qua `/api/contract-studio/upload/stream`. Parser và trích dữ kiện phát
   sự kiện; frontend vẽ cấu trúc đã nhận, không tạo graph bằng regex.
3. Xác nhận/sửa dữ kiện qua `/api/contracts/{cid}/facts`. Phải lưu các thay đổi
   trước khi phân tích. Thông tin bắt buộc chưa xác minh sẽ bị backend chặn.
4. Chạy `/api/contracts/{cid}/studio/analyze/stream`. Dùng concept-check hiện có,
   thêm sự kiện quan sát cho nhận diện, graph, đánh giá, recheck và căn cứ luật.
5. Chọn phát hiện để mở đoạn gốc và highlight graph. Hỏi tiếp qua API graph agent
   `/api/contracts/{cid}/ask/stream`; các bước truy vấn thật được dùng để highlight.

Không có demo, timer tiến bước, Play/Pause/Replay hay kết quả mẫu. Motion chỉ
hiển thị chuyển tiếp khi có sự kiện thật. Chín nhãn là nhóm thao tác, không ép
backend chạy tuần tự theo chín bước. Bước không có sự kiện không tự được đánh
dấu hoàn thành. Dữ liệu trả nhanh có thể được trình duyệt gom cùng một lần render.

Mỗi hạt tương ứng một neo căn cứ thực sự được kiểm tra, không phải một passage
hay document được tìm thấy bằng semantic search. Giữ/loại/chưa xác định theo kết
quả legal graph. Timeline chỉ chứa các phiên bản backend thực sự trả về; không
thêm phiên bản lịch sử hoặc cạnh hướng dẫn nếu backend chưa truy xuất chúng.

Nếu legal graph không khả dụng, UI hiển thị cảnh báo và giữ trống căn cứ chưa có.
Rule engine hiện vẫn đọc ngưỡng trong catalog; UI không biến ngưỡng đó thành lời
văn luật đã xác minh. Luồng này không thay retriever bằng structural benchmark adapter.

Nút upload có lựa chọn lưu hợp đồng; mặc định giữ theo phiên. Tab nhớ ID gần nhất
trong sessionStorage, có thể mở trực tiếp bằng `?contract=<cid>`. Đây không phải
cơ chế xác thực; tuân theo mô hình truy cập contract ID hiện tại của backend.
Đóng kết nối frontend không hủy model call đang chạy. Nếu mất stream, tải lại
trạng thái đã lưu trước khi chạy lại để tránh phát sinh thêm lượt model.

## API bổ sung

- `POST /api/contract-studio/upload/stream`: multipart `file`, `persist`.
- `GET /api/contracts/{cid}/studio`: tài liệu đầy đủ, graph chỉ đọc, thông tin
  xác minh và kết quả đã lưu. Không công bố lại graph khi lấy snapshot.
- `POST /api/contracts/{cid}/studio/analyze/stream`: kiểm tra xác minh, chặn hai
  lượt Studio đồng thời trên cùng hợp đồng, stream kết quả và snapshot cuối.

SSE dùng trường `type` trong JSON: `document`, `structure`, `fact_batch`,
`tag_batch`, `concept`, `graph`, `evaluation`, `partial`, `recheck`,
`legal_candidate`, `legal_resolution`, `stage`, `progress`, `done`, `error`.
Sự kiện tiến trình của Studio có `run_id` và `sequence`. Các callback là tùy chọn;
các caller cũ giữ nguyên kết quả nghiệp vụ.

## Kiểm tra

```powershell
npm run check
npm test
npm run build
```

Từ gốc repository:

```powershell
python -m pytest app/team-4.2/tests/test_contract_studio.py -q
```

Test dùng model và graph fixture để kiểm tra pipeline, không đưa fixture vào UI
production. Chạy với model/Neo4j thật phụ thuộc môi trường backend.
