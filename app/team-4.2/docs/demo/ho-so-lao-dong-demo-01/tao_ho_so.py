"""Sinh hồ sơ lao động demo (DOCX) cho màn Hồ sơ nhiều văn bản. Dữ liệu hư cấu."""
import sys
from pathlib import Path
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt

OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
CO = "Công ty TNHH Thương Mại Ánh Dương Demo"
ADDR = "số 18 đường Hoa Sữa, phường Tân Định, Thành phố Hồ Chí Minh"
NLD = "Ông Phạm Minh Khoa, sinh ngày 14/03/1994, CCCD số 079094000000 (thông tin hư cấu)"
HEAD = [CO.upper(), "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM", "Độc lập - Tự do - Hạnh phúc"]

def contract(no, signed, start, end, probation, salary, months="12"):
    lines = [*HEAD, f"Số: {no}", "HỢP ĐỒNG LAO ĐỘNG",
        f"Hôm nay, ngày {signed}, tại trụ sở {CO}, chúng tôi gồm:",
        f"Bên A (Người sử dụng lao động): {CO}, địa chỉ {ADDR}, đại diện là Bà Đỗ Thu Hà, chức vụ Giám đốc.",
        f"Bên B (Người lao động): {NLD}.",
        "Hai bên thỏa thuận ký kết hợp đồng lao động với các điều khoản sau:",
        "Điều 1. Công việc, địa điểm làm việc và thời hạn của hợp đồng",
        "1. Loại hợp đồng: Hợp đồng lao động xác định thời hạn.",
        f"2. Thời hạn hợp đồng: {months} tháng, từ ngày {start} đến ngày {end}.",
        "3. Chức danh chuyên môn: Nhân viên kinh doanh.",
        f"4. Địa điểm làm việc: {ADDR}.",
        "Điều 2. Thử việc",
        probation,
        "Điều 3. Tiền lương",
        f"1. Mức lương chính: {salary} đồng/tháng.",
        "2. Hình thức trả lương: chuyển khoản, trả vào ngày 05 hằng tháng.",
        "Điều 4. Thời giờ làm việc, nghỉ ngơi",
        "Thời giờ làm việc: 08 giờ/ngày, 48 giờ/tuần. Nghỉ hằng năm 12 ngày làm việc, hưởng nguyên lương.",
        "Điều 5. Bảo hiểm xã hội, bảo hiểm y tế, bảo hiểm thất nghiệp",
        "Bên A đóng bảo hiểm xã hội, bảo hiểm y tế, bảo hiểm thất nghiệp cho Bên B theo quy định của pháp luật.",
        "Điều 6. Điều khoản thi hành",
        "Hợp đồng được lập thành 02 bản có giá trị như nhau, mỗi bên giữ 01 bản.",
        "NGƯỜI LAO ĐỘNG                                        NGƯỜI SỬ DỤNG LAO ĐỘNG"]
    return lines

def appendix(n, of, signed, change, valid):
    return [*HEAD, f"PHỤ LỤC HỢP ĐỒNG LAO ĐỘNG SỐ {n}", f"Kèm theo Hợp đồng lao động số {of}",
        f"Hôm nay, ngày {signed}, tại trụ sở {CO}, Bên A ({CO}) và Bên B ({NLD}) thỏa thuận như sau:",
        "Điều 1. Nội dung thay đổi", change,
        "Điều 2. Hiệu lực", f"Phụ lục này có hiệu lực kể từ ngày {valid}. Các nội dung khác của Hợp đồng giữ nguyên.",
        "NGƯỜI LAO ĐỘNG                                        NGƯỜI SỬ DỤNG LAO ĐỘNG"]

def save(name, lines):
    d = Document(); st = d.styles["Normal"]; st.font.name = "Times New Roman"; st.font.size = Pt(13)
    for i, t in enumerate(lines):
        p = d.add_paragraph(t)
        if i < 3 or t.startswith(("HỢP ĐỒNG LAO ĐỘNG", "PHỤ LỤC", "Số:", "Kèm theo")):
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        if t.startswith(("Điều ", "HỢP ĐỒNG", "PHỤ LỤC")) or i < 3:
            for r in p.runs: r.bold = True
    d.save(OUT / name)
    (OUT / name).with_suffix(".txt").write_text("\n".join(lines), encoding="utf-8") if "--txt" in sys.argv else None

save("01-hdld-2023.docx", contract("015/2023/HĐLĐ-AD", "28 tháng 12 năm 2022", "01/01/2023", "31/12/2023",
     "Thời gian thử việc: 02 tháng, hưởng 85% mức lương chính.", "9.000.000"))
save("02-phu-luc-01-hdld-2023.docx", appendix("01", "015/2023/HĐLĐ-AD", "20 tháng 6 năm 2023",
     "Sửa đổi Khoản 1 Điều 3 của Hợp đồng như sau: Mức lương chính: 10.000.000 đồng/tháng.", "01/07/2023"))
save("03-hdld-2024.docx", contract("004/2024/HĐLĐ-AD", "27 tháng 12 năm 2023", "01/01/2024", "31/12/2024",
     "Hai bên không thỏa thuận thử việc.", "10.500.000"))
save("04-hdld-2025.docx", contract("002/2025/HĐLĐ-AD", "26 tháng 12 năm 2024", "01/01/2025", "31/12/2026",
     "Thời gian thử việc: 02 tháng, hưởng 85% mức lương chính.", "11.000.000", "24"))
save("05-phu-luc-01-hdld-2025.docx", appendix("01", "002/2025/HĐLĐ-AD", "20 tháng 5 năm 2026",
     "Sửa đổi Khoản 2 Điều 1 của Hợp đồng như sau: Thời hạn hợp đồng: 30 tháng, từ ngày 01/01/2025 đến ngày 30/06/2027.", "01/06/2026"))
print("ok", sorted(p.name for p in OUT.iterdir()))
