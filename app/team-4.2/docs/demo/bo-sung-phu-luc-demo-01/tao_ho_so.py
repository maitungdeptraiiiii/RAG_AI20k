"""Sinh hợp đồng lao động gốc + phụ lục demo (DOCX) cho chức năng "Bổ sung văn bản". Dữ liệu hư cấu.

Chạy: python tao_ho_so.py <thư mục>  (cần python-docx)."""
import sys
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt

CO = "Công ty TNHH Thương Mại Ánh Dương Demo"
ADDR = "số 18 đường Hoa Sữa, phường Tân Định, Thành phố Hồ Chí Minh"
NLD = "Ông Phạm Minh Khoa, sinh ngày 14/03/1994, CCCD số 079094000000 (thông tin hư cấu)"
HEAD = [CO.upper(), "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM", "Độc lập - Tự do - Hạnh phúc"]
SIGN = "NGƯỜI LAO ĐỘNG                                        NGƯỜI SỬ DỤNG LAO ĐỘNG"

CONTRACT = [
    *HEAD, "Số: 007/2026/HĐLĐ-AD", "HỢP ĐỒNG LAO ĐỘNG",
    f"Hôm nay, ngày 05 tháng 01 năm 2026, tại trụ sở {CO}, chúng tôi gồm:",
    f"Bên A (Người sử dụng lao động): {CO}, địa chỉ {ADDR}, đại diện là Bà Đỗ Thu Hà, chức vụ Giám đốc.",
    f"Bên B (Người lao động): {NLD}.",
    "Hai bên thỏa thuận ký kết hợp đồng lao động với các điều khoản sau:",
    "Điều 1. Công việc, địa điểm làm việc và thời hạn của hợp đồng",
    "1. Loại hợp đồng: Hợp đồng lao động xác định thời hạn.",
    "2. Thời hạn hợp đồng: 24 tháng, từ ngày 05/01/2026 đến ngày 04/01/2028.",
    "3. Chức danh chuyên môn: Nhân viên kinh doanh, yêu cầu trình độ đại học.",
    f"4. Địa điểm làm việc: {ADDR}.",
    "Điều 2. Thử việc",
    "Thời gian thử việc: 90 ngày, từ ngày 05/01/2026. Tiền lương thử việc bằng 70% mức lương chính.",
    "Điều 3. Tiền lương",
    "1. Mức lương chính: 4.500.000 đồng/tháng.",
    "2. Hình thức trả lương: chuyển khoản, trả vào ngày 05 hằng tháng.",
    "Điều 4. Thời giờ làm việc",
    "Thời giờ làm việc bình thường: 10 giờ/ngày, 60 giờ/tuần.",
    "Điều 5. Nghỉ hằng năm",
    "Người lao động được nghỉ hằng năm 10 ngày làm việc, hưởng nguyên lương.",
    "Điều 6. Bảo hiểm xã hội, bảo hiểm y tế, bảo hiểm thất nghiệp",
    "Bên A đóng bảo hiểm xã hội, bảo hiểm y tế, bảo hiểm thất nghiệp cho Bên B theo quy định của pháp luật.",
    "Điều 7. Điều khoản thi hành",
    "Hợp đồng được lập thành 02 bản có giá trị như nhau, mỗi bên giữ 01 bản.",
    SIGN,
]

# Mỗi dòng sửa đổi ghi cả động từ sửa đổi lẫn điều khoản bị sửa trên cùng một dòng.
APPENDIX = [
    *HEAD, "PHỤ LỤC HỢP ĐỒNG LAO ĐỘNG SỐ 01", "Kèm theo Hợp đồng lao động số 007/2026/HĐLĐ-AD",
    f"Hôm nay, ngày 16 tháng 02 năm 2026, tại trụ sở {CO}, Bên A ({CO}) và Bên B ({NLD}) thỏa thuận như sau:",
    "Điều 1. Điều chỉnh tiền lương",
    "Sửa đổi Khoản 1 Điều 3 của Hợp đồng như sau: Mức lương chính: 8.000.000 đồng/tháng.",
    "Điều 2. Điều chỉnh thời giờ làm việc",
    "Sửa đổi Điều 4 của Hợp đồng như sau: Thời giờ làm việc bình thường: 08 giờ/ngày, 48 giờ/tuần.",
    "Điều 3. Điều chỉnh nghỉ hằng năm",
    "Sửa đổi Điều 5 của Hợp đồng như sau: Người lao động được nghỉ hằng năm 12 ngày làm việc, hưởng nguyên lương.",
    "Điều 4. Chế độ nâng lương",
    "Bổ sung vào Điều 3 của Hợp đồng: Người lao động được xét nâng lương mỗi năm 01 lần căn cứ kết quả công việc.",
    "Điều 5. Ký quỹ bảo đảm",
    "Bổ sung vào Hợp đồng: Bên B phải nộp cho Bên A số tiền 10.000.000 đồng làm tiền đặt cọc bảo đảm việc thực hiện "
    "hợp đồng lao động và Bên A giữ bản chính bằng tốt nghiệp của Bên B.",
    "Điều 6. Hiệu lực",
    "Phụ lục này có hiệu lực kể từ ngày 01/03/2026. Các nội dung khác của Hợp đồng giữ nguyên.",
    SIGN,
]


def save(out: Path, name: str, lines: list[str]) -> None:
    d = Document()
    style = d.styles["Normal"]
    style.font.name, style.font.size = "Times New Roman", Pt(13)
    for i, text in enumerate(lines):
        p = d.add_paragraph(text)
        if i < 3 or text.startswith(("HỢP ĐỒNG LAO ĐỘNG", "PHỤ LỤC", "Số:", "Kèm theo")):
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        if i < 3 or text.startswith(("Điều ", "HỢP ĐỒNG", "PHỤ LỤC")):
            for run in p.runs:
                run.bold = True
    d.save(out / name)


if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    out.mkdir(parents=True, exist_ok=True)
    save(out, "01-hop-dong-goc.docx", CONTRACT)
    save(out, "02-phu-luc-01.docx", APPENDIX)
    print("ok", sorted(p.name for p in out.glob("*.docx")))
