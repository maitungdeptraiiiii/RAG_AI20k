import sys; sys.path.insert(0,'src')
from rag.bridge.facts_map import _duration, _salary, _first
from rag.contracts.values import extract_values
dur = ["12 tháng","24 (hai mươi bốn) tháng","hai mươi bốn tháng","ba mươi (30) ngày","30 ngày làm việc","01 năm","1,5 năm","một năm","từ 01/01/2024 đến 31/12/2025","2 năm 6 tháng","không xác định thời hạn","36 tháng kể từ ngày ký","12 tháng, gia hạn thêm 6 tháng","thời hạn 1 năm (12 tháng)"]
print("DURATION"); [print(f"  {t!r:50} -> {_duration(t)}") for t in dur]
mon = ["100.000.000 đồng","100 triệu đồng","một trăm triệu đồng","5.000.000 VNĐ/tháng","5,5 triệu đồng","5tr","năm triệu đồng","100.000.000đ","100.000.000 (một trăm triệu) đồng","điều chỉnh từ 4.700.000 đồng lên 5.000.000 đồng","10 triệu đồng/tháng","USD 1,000","1.000 USD","5.000.000 đồng, trong đó 1.000.000 đồng phụ cấp"]
print("MONEY"); [print(f"  {t!r:60} -> {_salary(t)}") for t in mon]
pct = ["1%/tháng","1,5 %/tháng","18%/năm","một phẩy năm phần trăm một tháng","0,05%/ngày","20 phần trăm/năm","20 %"]
print("PERCENT"); [print(f"  {t!r:40} -> {[(v.kind,v.norm) for v in extract_values(t)]}") for t in pct]
dt = ["ngày 01 tháng 3 năm 2024","01/03/2024","1-3-2024","ngày 1/3/2024","mùng 1 tháng 3 năm 2024","March 1, 2024","01.03.2024","ngày 01 tháng 03 năm 2024","tháng 3 năm 2024"]
print("DATE"); [print(f"  {t!r:40} -> {[(v.norm) for v in extract_values(t) if v.kind=='date']}") for t in dt]
