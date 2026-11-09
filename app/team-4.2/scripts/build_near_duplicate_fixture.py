"""Build a transparent synthetic dev/test pair fixture, independent of detector.

Labels mean 'needs duplicate-review triage', not 'lexically similar' or 'true
legal conflict'. This fixture cannot establish real-world legal accuracy.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DATASET = ROOT / "evals/team-4.2/datasets/near_duplicate/pairs.json"

PREAMBLE = "\n".join([
    "Căn cứ quy định về tổ chức và hoạt động của cơ quan quản lý nhà nước;",
    "Căn cứ quy định về trình tự ban hành văn bản và thẩm quyền quyết định;",
    "Căn cứ quy định về trách nhiệm tổ chức thực hiện và phối hợp giữa các đơn vị;",
    "Căn cứ đề nghị của cơ quan chuyên môn về việc ban hành quy định dịch vụ;",
] * 3)
FOOTER = "Nơi nhận:\nCác cơ quan liên quan;\nCác đơn vị thực hiện;\nLưu văn thư và hồ sơ theo quy định."
FEE = ("Điều 3. Mức phí dịch vụ là 100.000 đồng mỗi tháng. "
       "Mức phí đã bao gồm thuế và áp dụng cho khách hàng cá nhân. "
       "Thanh toán qua ngân hàng vào ngày đầu tiên của tháng tiếp theo.")


def metadata(key="01/2026/QĐ", issuer="Cơ quan A", province="A", confirmed=True):
    return {"external_key": key, "issuer": issuer, "scope": {"province": province}, "confirmed": confirmed}


def document(body, *, template=False, meta=None, confidence=None):
    text = "\n".join((PREAMBLE, body, FOOTER)) if template else body
    return {"text": text, "metadata": meta or {}, "ocr_confidence": confidence}


def build_dataset() -> dict:
    pairs = []
    for split in ("dev", "test"):
        # Held-out source IDs and amounts differ. Template families are shared:
        # disclose that this is not an independent real-document benchmark.
        fee = FEE if split == "dev" else FEE.replace("100.000", "180.000")
        revised = fee.replace("100.000" if split == "dev" else "180.000", "250.000")
        different = metadata("09/2026/QĐ", "Cơ quan B", "B")
        same = metadata()
        cases = [
            ("independent-provinces", False, "Cùng mẫu, khác cơ quan/số hiệu và địa phương đã xác nhận",
             document(fee, template=True, meta=same), document(revised, template=True, meta=different)),
            ("independent-same-body", False, "Cùng nội dung mẫu nhưng áp dụng độc lập cho địa phương khác",
             document(fee, template=True, meta=same), document(fee, template=True, meta=different)),
            ("boilerplate-only", False, "Chỉ phần căn cứ/nơi nhận giống; nội dung nghiệp vụ khác nhau",
             document("Điều 3. Trồng cây xanh tạo bóng mát cho công viên đô thị.", template=True),
             document("Điều 3. Chăm sóc trẻ em tại trường học bằng bữa ăn dinh dưỡng.", template=True)),
            ("same-identity-number", True, "Cùng identity nhưng thay mức phí cần xem xét",
             document(fee, template=True, meta=same), document(revised, template=True, meta=same)),
            ("negation", True, "Thêm từ “không” làm thay đổi nội dung áp dụng",
             document(fee, meta=same), document(fee.replace("đã bao gồm", "không bao gồm"), meta=same)),
            ("short-number", True, "Cùng identity, thay số trong đoạn ngắn dưới ngưỡng lexical cũ",
             document("Phí 100.000 đồng", meta=same), document("Phí 250.000 đồng", meta=same)),
            ("ocr-candidate", True, "Nghi khác biệt OCR vẫn cần kiểm tra, không tự sửa/xóa",
             document(fee, meta=same, confidence=.6), document(fee.replace("khách hàng", "khach hang"), meta=same, confidence=.6)),
            ("unknown-identity-copy", True, "Thiếu metadata nhưng nội dung gần giống vẫn cần review",
             document(fee), document(revised)),
            ("unrelated", False, "Nội dung không liên quan",
             document(fee), document("Cá voi sống ở đại dương và di cư theo mùa.")),
            ("masked-identical", True, "Giống sau masking chưa đủ để gộp nguồn",
             document(fee + " Liên hệ [EMAIL]."), document(fee + " Liên hệ [EMAIL].")),
            ("unknown-independent", False, "Hai nguồn thực tế độc lập nhưng metadata thiếu: bài kiểm tra giới hạn bảo thủ",
             document(fee, template=True), document(revised, template=True)),
            ("identity-contradiction", True, "Số hiệu/cơ quan giống nhau nhưng scope khác: metadata cần review",
             document(fee, template=True, meta=same), document(revised, template=True, meta=metadata(province="B"))),
        ]
        for name, label, reason, left, right in cases:
            pair_id = f"{split}-{name}"
            for suffix, doc in (("a", left), ("b", right)):
                doc["document_id"] = f"{pair_id}-{suffix}"
            pairs.append({"id": pair_id, "split": split, "label_review": label, "label_reason": reason,
                          "left": left, "right": right})
    return {"schema_version": "near-duplicate-eval.v1", "synthetic": True,
            "label_definition": "Needs duplicate-review triage, not truth of a legal conflict",
            "limitations": ["Synthetic examples, shared template families across dev/test",
                            "Source IDs are split-disjoint; labels are handcrafted, not independently adjudicated",
                            "Do not infer real-corpus precision/recall from this fixture"], "pairs": pairs}


def main() -> None:
    DATASET.parent.mkdir(parents=True, exist_ok=True)
    DATASET.write_text(json.dumps(build_dataset(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(DATASET)


if __name__ == "__main__":
    main()
