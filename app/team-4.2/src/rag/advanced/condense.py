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

log = logging.getLogger("rag.condense")

CONDENSE_SYSTEM_PROMPT = """Bạn là trợ lý giải nén ngữ cảnh hội thoại.
Nhiệm vụ: Dựa vào [LỊCH SỬ TRAO ĐỔI], hãy viết lại [CÂU HỎI MỚI] thành ĐÚNG MỘT câu hỏi độc lập, tự đủ nghĩa mà người đọc không cần nhìn lại lịch sử vẫn hiểu được.

QUY TẮC BẮT BUỘC:
1. KHÔNG TRẢ LỜI CÂU HỎI. Chỉ viết lại câu hỏi.
2. KHÔNG PHÂN RÃ THÀNH NHIỀU CÂU. Đầu ra luôn luôn là MỘT câu hỏi duy nhất.
3. CHỈ KHÔI PHỤC CHỦ NGỮ / ĐẠI TỪ:
   - Thay thế các đại từ chỉ định hoặc từ mơ hồ ("nó", "điều đó", "trường hợp này", "họ", "thời hạn này", "thế còn...") bằng thực thể/chủ đề đã được xác định trong lịch sử.
   - Giữ nguyên toàn bộ câu chữ, phong cách và dữ kiện gốc của câu hỏi mới.
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
    max_history_turns: int = 3

    def condense(self, query: str, history: Sequence[dict[str, Any]] | None = None) -> str:
        q = nfc(query).strip()
        if not q or not history:
            return q

        # Lọc và định dạng lịch sử tinh gọn (chỉ lấy tối đa max_history_turns gần nhất)
        recent = history[-self.max_history_turns:]
        history_lines: list[str] = []
        for turn in recent:
            if not isinstance(turn, dict):
                continue
            u_query = (turn.get("query") or "").strip()
            b_answer = (turn.get("answer") or "").strip()
            if u_query:
                history_lines.append(f"User: {u_query}")
            if b_answer:
                # Chỉ lấy tối đa 150 ký tự đầu của câu trả lời để tiết kiệm token và tránh nhiễu
                short_ans = " ".join(b_answer.split())[:150]
                history_lines.append(f"Bot: {short_ans}")

        if not history_lines:
            return q

        user_content = (
            f"[LỊCH SỬ TRAO ĐỔI]\n"
            + "\n".join(history_lines)
            + f"\n\n[CÂU HỎI MỚI]\n{q}"
        )

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
                if rewritten:
                    return rewritten
        except Exception as e:
            log.warning("Condense failed: %s; falling back to original query", e)

        return q


__all__ = ["CONDENSE_SYSTEM_PROMPT", "QueryCondenser"]
