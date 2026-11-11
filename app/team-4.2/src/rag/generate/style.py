"""User-facing answer policy shared by standard and agent generation."""

from dataclasses import dataclass
import re
import unicodedata

PRESENTATION_VERSION = "no-temporal-commentary-v1"
_QUALIFICATION = "Tôi chưa đủ căn cứ để kết luận chắc chắn cho trường hợp cụ thể."


@dataclass(frozen=True)
class PresentedAnswer:
    text: str
    suppressed_sentences: int = 0
    qualified: bool = False


def present_answer(answer: str) -> PresentedAnswer:
    """Suppress internal date commentary, not substantive dates/legal claims.

    Match internal evaluation-date explanations, never dates alone. Retain a
    plain qualification if the removed explanation said evidence was lacking.
    No model call or rewriting of surviving legal sentences/citations is used.
    """
    removed, qualified, paragraphs = 0, False, []
    for paragraph in re.split(r"\n[ \t]*\n", answer):
        kept, previous_metadata = [], False
        for sentence in re.split(r"(?<=[.!?])[ \t\n]+", paragraph):
            value = unicodedata.normalize("NFC", sentence).casefold()
            anchor = re.search(r"\b(?:mốc|ngày (?:đánh giá|tra cứu|đã chọn|mặc định|hôm nay))\b", value)
            explanation = re.search(
                r"đánh giá|tra cứu|mặc định|hôm nay|ngày đã chọn|hệ thống|backend|"
                r"ngữ cảnh|phiên bản|xác minh|tài liệu tham khảo", value)
            internal = bool(anchor and explanation)
            heading = re.sub(r"[*_#`]", "", value).strip()
            internal |= bool(re.fullmatch(
                r"(?:mốc pháp lý(?: đang sử dụng)?|mốc đánh giá|ngày đánh giá|ngày tra cứu)"
                r"\s*:?\s*(?:\d{1,2}/\d{1,2}/\d{4}|\d{4}-\d{2}-\d{2})?", heading))
            if (re.search(r"(?:điều\s+\d|luật\s+\w|nghị định|hợp đồng).*"
                          r"(?:có hiệu lực|được ký|ký ngày|hết hạn|thời hiệu)", value)
                    and not re.search(r"ngữ cảnh|đánh giá|mặc định|hôm nay|xác minh|tài liệu", value)):
                internal = False
            # The next sentence may merely restate the same source limitation.
            restatement = bool(previous_metadata and re.search(
                r"nhận định pháp lý trên|tài liệu tham khảo|nội dung tài liệu.*cung cấp", value)
                and not re.search(r"điều\s+\d|bộ luật|hình phạt|bồi thường|thời hiệu", value))
            if internal or restatement:
                removed += 1
                qualified |= bool(re.search(
                    r"chưa.*(?:căn cứ|xác minh|xác định|đủ)|không.*(?:căn cứ|đủ)|"
                    r"chỉ.*tham khảo|giới hạn|thiếu.*(?:căn cứ|nguồn)", value))
                previous_metadata = True
            else:
                kept.append(sentence)
                previous_metadata = False
        if kept:
            paragraphs.append(" ".join(kept))
    if not removed:
        return PresentedAnswer(answer)
    text = "\n\n".join(paragraphs).strip()
    if qualified and not re.search(r"chưa (?:đủ căn cứ|thể.*kết luận)|không thể.*kết luận", text, re.I):
        text = (text + "\n\n" if text else "") + _QUALIFICATION
    if not text:
        text = "Bạn muốn tìm hiểu vấn đề cụ thể nào?"
    return PresentedAnswer(text, removed, qualified)

ANSWER_STYLE = """
CÁCH TRẢ LỜI CHO NGƯỜI DÙNG:
- Trả lời đúng ý định được nêu. Lời chào, tự giới thiệu hoặc dữ kiện bổ sung không
  tự tạo thành câu hỏi pháp lý. Không suy đoán người dùng muốn hỏi tính hợp pháp
  của tên, đổi tên hay giấy tờ chỉ vì họ giới thiệu tên; chỉ chào hoặc hỏi họ cần gì.
- Khi người dùng hỏi về dữ kiện họ đã nói, dùng lịch sử hội thoại; không bắt dữ
  kiện đời thường phải có trích dẫn luật. Không biến đáp án cũ thành bằng chứng.
- Metadata nguồn và trạng thái kiểm tra dùng để quyết định mức chắc chắn, không
  phải nội dung cần thuyết minh. Không đưa nhãn kỹ thuật như “Kho cũ”, “kho có
  phiên bản”, “snapshot”, “legacy”, “chưa xác định phiên bản” vào câu trả lời.
- Nếu giới hạn nguồn thực sự ngăn kết luận, giải thích ngắn, cụ thể về tác động:
  ví dụ “Tôi chưa đủ căn cứ xác nhận quy định này còn áp dụng cho trường hợp của bạn.”
  Không bỏ qua bất định, không nâng mức chắc chắn, không lặp cảnh báo chung chung.
- Không tự nhắc “mốc pháp lý”, “ngày đánh giá”, ngày hôm nay hoặc giải thích
  ngày mặc định trong câu trả lời. Ngày do backend cung cấp dùng để kiểm tra ngầm;
  việc chọn ngày trên giao diện cũng không phải yêu cầu thuyết minh về ngày đó.
- Chỉ nêu thời điểm trong lập luận khi người dùng thực sự hỏi về thời điểm/so sánh
  quy định qua thời gian, hoặc sự thay đổi quy định quyết định trực tiếp kết luận.
  Không thêm đoạn mở đầu/kết luận hay cảnh báo riêng về mốc. Không mặc định hôm nay
  là ngày xảy ra sự việc hoặc là bằng chứng đã xác nhận pháp luật hiện hành.
- Nếu cần làm rõ, ưu tiên tối đa 3 câu hỏi về dữ kiện quyết định trực tiếp.
  Không tự hỏi ngày xảy ra ở mọi câu hỏi pháp lý; chỉ hỏi khi thiếu ngày thực sự
  cản trở việc xác định quy định áp dụng. Không lặp cùng câu hỏi trong đáp án và
  follow_up_questions. Ví dụ hỏi chung “đánh người có bị xử lý không?” thì trước
  hết giải thích các khả năng và hỏi hậu quả thương tích/hoàn cảnh nếu cần, không
  tự thêm một đoạn về ngày đánh giá hay yêu cầu ngày xảy ra theo thủ tục.
- Vẫn dẫn đúng điều luật và nguồn khi đưa ra kết luận pháp lý có căn cứ.
"""
