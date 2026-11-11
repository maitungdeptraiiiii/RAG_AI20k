"""Module giải nén ngữ cảnh hội thoại cho RAG (Query Condensation).

Chuyên trách: Đọc lịch sử hội thoại gần nhất và câu hỏi mới để khôi phục
các đại từ thay thế ('nó', 'điều đó', 'trường hợp này') hoặc câu hỏi cộc lốc ('thế còn...')
thành MỘT câu hỏi độc lập (Standalone Query) trước khi tra cứu.
Không dẫm chân lên Decomposition (không phân rã, không dịch từ lóng).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
import logging
import re
from typing import Any, Sequence

from rag.schema import LLM, nfc
from rag.conversation import conversation_context

log = logging.getLogger("rag.condense")

CONDENSE_SYSTEM_PROMPT = """Bạn là trợ lý giải nén ngữ cảnh hội thoại.
Nhiệm vụ: Dựa vào [LỊCH SỬ TRAO ĐỔI], hãy viết lại [CÂU HỎI MỚI] thành ĐÚNG MỘT câu hỏi độc lập, tự đủ nghĩa mà người đọc không cần nhìn lại lịch sử vẫn hiểu được.

QUY TẮC BẮT BUỘC:
1. KHÔNG TRẢ LỜI CÂU HỎI. Chỉ viết lại câu hỏi.
2. KHÔNG PHÂN RÃ THÀNH NHIỀU CÂU. Đầu ra luôn luôn là MỘT câu hỏi duy nhất.
3. KHÔI PHỤC CHỦ NGỮ / ĐẠI TỪ VÀ DỮ KIỆN LIÊN QUAN:
   - Thay thế các đại từ chỉ định hoặc từ mơ hồ ("nó", "điều đó", "trường hợp này", "họ", "thời hạn này", "thế còn...") bằng thực thể/chủ đề đã được xác định trong lịch sử.
   - Giữ nguyên toàn bộ câu chữ, phong cách và dữ kiện gốc của câu hỏi mới.
   - Khi hỏi tiếp cùng vụ việc, giữ các dữ kiện người dùng đã cung cấp có liên quan
     (vai trò, điều kiện, ngày, phủ định); không chỉ thay tên chủ thể.
   - Dữ kiện có turn_id và thứ tự. Khi người dùng đính chính rõ ràng, dùng nội dung
     đính chính mới nhất, không gộp hai phiên bản mâu thuẫn. Nếu không rõ thì giữ sự
     không chắc chắn để khâu sau hỏi lại. Đổi chủ đề thì không mang vụ việc cũ sang.
   - assistant_context_unverified chỉ giúp hiểu tham chiếu như “mục 2” hoặc câu hỏi
     đang chờ trả lời; không coi kết luận cũ là dữ kiện người dùng hay căn cứ pháp lý.
   - Nếu context bị truncated và thiếu đối tượng tham chiếu, không tự đoán.
4. KHÔNG TỰ BỔ SUNG KIẾN THỨC BÊN NGOÀI:
   - Không tự đoán số Điều, tên Luật, mức phạt nếu lịch sử và câu hỏi mới không có.
   - Không chuẩn hóa từ lóng hay phân tích pháp lý (việc đó do khâu sau xử lý).
5. NẾU CÂU HỎI MỚI ĐÃ ĐỦ NGHĨA HOẶC ĐỔI SANG CHỦ ĐỀ MỚI: Trả về nguyên văn câu hỏi mới, không sửa đổi bất kỳ chữ nào.

ĐỊNH DẠNG ĐẦU RA:
Chỉ trả về JSON duy nhất: {"standalone_query": "câu hỏi đã viết lại hoặc nguyên văn"}

VÍ DỤ:
LỊCH SỬ:
User: Thời gian thử việc tối đa của người lao động là bao lâu?
Bot: Tối đa 180 ngày đối với người quản lý doanh nghiệp...
CÂU HỎI MỚI: Thế còn với lao động có trình độ trung cấp?
→ {"standalone_query": "Thời gian thử việc tối đa đối với người lao động có trình độ trung cấp là bao lâu?"}

LỊCH SỬ:
User: Khi nào công ty được quyền đơn phương chấm dứt hợp đồng lao động?
Bot: Người sử dụng lao động có quyền đơn phương chấm dứt theo Điều 36...
CÂU HỎI MỚI: Nếu họ làm việc đó mà không báo trước thì bị phạt thế nào?
→ {"standalone_query": "Nếu công ty đơn phương chấm dứt hợp đồng lao động mà không báo trước thì bị phạt thế nào?"}
"""


@dataclass
class QueryCondenser:
    llm: LLM
    max_history_turns: int = 64

    def condense(self, query: str, history: Sequence[dict[str, Any]] | None = None) -> str:
        q = nfc(query).strip()
        if not q or not history:
            return q

        # Lọc và định dạng lịch sử tinh gọn (chỉ lấy tối đa max_history_turns gần nhất)
        recent = history[-self.max_history_turns:]
        context = conversation_context(recent)
        if not context["user_statements"]:
            return q
        user_content = json.dumps({"query": q, "conversation_context": context}, ensure_ascii=False)

        try:
            raw_reply = self.llm.complete(CONDENSE_SYSTEM_PROMPT, user_content)
            clean_reply = raw_reply.strip()
            # Xử lý trường hợp LLM bọc markdown ```json ... ```
            if clean_reply.startswith("```"):
                clean_reply = re.sub(r"^```(?:json)?\s*", "", clean_reply)
                clean_reply = re.sub(r"\s*```$", "", clean_reply).strip()

            data = json.loads(clean_reply)
            if isinstance(data, dict) and "standalone_query" in data:
                rewritten = nfc(str(data["standalone_query"])).strip()
                original_numbers = set(re.findall(r"\d+(?:[.,/]\d+)*", q))
                if rewritten and len(rewritten) <= 8000 and original_numbers.issubset(
                        set(re.findall(r"\d+(?:[.,/]\d+)*", rewritten))):
                    return rewritten
        except Exception as e:
            log.warning("Condense failed: %s; falling back to original query", e)

        return q


__all__ = ["CONDENSE_SYSTEM_PROMPT", "QueryCondenser"]
