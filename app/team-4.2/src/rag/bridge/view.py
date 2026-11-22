"""Soạn phần hiển thị cho kết quả Kiểm tra concept (spec 2026-11-17-concept-check-streaming-ui §4).

Trang chỉ vẽ: mọi chữ người xem đọc (tiêu đề, kết luận, giá trị luật, nhãn dữ kiện) được soạn ở đây từ danh mục và
căn cứ luật; mã nội bộ (concept_id, rule_id, pid) vẫn giữ trong kết quả gốc để hiện ở dòng phụ."""
from __future__ import annotations

from rag.bridge.catalog import Catalog
from rag.contracts.models import Contract

VERDICTS: dict[str, str] = {
    "violation": "Hợp đồng trái luật ở điểm này",
    "missing_content": "Hợp đồng thiếu nội dung mà luật bắt buộc phải có",
    "hidden_right": "Hợp đồng không nhắc, nhưng người lao động vẫn có quyền này theo luật",
    "conflict": "Hợp đồng ghi mâu thuẫn ở điểm này",
    "possible_right": "Có thể có quyền này — cần thêm thông tin về người lao động",
    "needs_facts": "Chưa kết luận được — cần thêm dữ kiện",
    "ok": "Hợp đồng phù hợp với luật ở điểm này",
}

FACT_LABELS: dict[str, str] = {
    # dữ kiện cấp hợp đồng
    "contract_kind": "Loại hợp đồng",
    "term_months": "Thời hạn hợp đồng",
    "base_salary_vnd": "Mức lương",
    "has_probation": "Có thử việc",
    "probation_length": "Thời gian thử việc",
    "probation_pay_pct": "Lương thử việc (% lương chính thức)",
    "job_level": "Trình độ / tính chất công việc",
    "sign_date": "Ngày ký",
    # dữ kiện về người lao động
    "work_condition": "Điều kiện làm việc",
    "pregnant": "Đang mang thai",
    "pregnancy_month": "Tháng thai kỳ",
    "child_under_12_months": "Nuôi con dưới 12 tháng",
    "employee_consent": "Người lao động đồng ý",
    "medical_certificate": "Giấy xác nhận của cơ sở y tế",
    "wage_region": "Vùng lương tối thiểu",
    "employee_is_female": "Người lao động là nữ",
    "worked_after_expiry_days": "Số ngày làm việc tiếp sau khi hợp đồng hết hạn",
    "new_contract_signed": "Hai bên đã ký hợp đồng lao động mới",
    "fixed_term_contract_count": "Số hợp đồng xác định thời hạn đã ký liên tiếp (kể cả hợp đồng này)",
    "is_state_enterprise_director": "Được thuê làm giám đốc doanh nghiệp có vốn nhà nước",
    "is_elderly_employee": "Người lao động cao tuổi",
    "is_foreign_employee": "Người lao động nước ngoài",
    "is_union_leader_in_term": "Thành viên ban lãnh đạo tổ chức đại diện người lao động tại cơ sở, đang trong nhiệm kỳ",
}

_UNITS = {"percent": "%", "day": " ngày", "workday": " ngày làm việc", "minute": " phút", "hour": " giờ",
          "month": " tháng", "vnd": " đồng"}


def _number(value) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, float) and not value.is_integer():
        return f"{value:,}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{int(value):,}".replace(",", ".")


def format_value(value, unit: str | None) -> str:
    """150, percent -> "150%"; 30, day -> "30 ngày"; 5000000, vnd -> "5.000.000 đồng"."""
    return _number(value) + _UNITS.get(unit or "", f" {unit}" if unit else "")


def _law_value_text(v) -> str:
    if isinstance(v, dict) and "value" in v:
        return format_value(v["value"], v.get("unit"))
    return str(v)


def _missing_label(name: str, concept) -> str:
    if concept is not None and name in concept.slots:
        return f"{concept.label} (nội dung trong hợp đồng)"
    return FACT_LABELS.get(name, name)


def citation_text(cite) -> str | None:
    """Trích dẫn từ đồ thị luật ({label, doc_title, ...}) -> "Khoản 2 Điều 27 — Bộ Luật lao động số 45/2019/QH14"."""
    if not cite:
        return None
    if isinstance(cite, str):
        return cite
    label = str(cite.get("label") or "").strip()
    label = label[:1].upper() + label[1:]
    title = str(cite.get("doc_title") or cite.get("doc_number") or "").strip()
    return " — ".join(x for x in (label, title) if x) or cite.get("provision_id")


_NOT_IN_FORCE = {
    "not_yet_in_force": "Chưa có hiệu lực ở ngày áp luật",
    "no_longer_in_force": "Đã hết hiệu lực ở ngày áp luật",
    "no_version_at_date": "Đồ thị luật không có phiên bản hiệu lực ở ngày áp luật",
    "overlapping_versions": "Đồ thị luật có nhiều phiên bản chồng nhau ở ngày áp luật — cần rà soát nguồn",
    "unknown_provision": "Đồ thị luật không có điều này",
}


def law_entry(pid: str, provision: dict | None) -> dict:
    """Một căn cứ luật để vẽ: kết quả `LegalGraph.text_at` -> trích dẫn, lời văn, hiệu lực, nguồn gốc và ghi chú.
    `in_force`: True / False / None (None: chưa có đồ thị, hoặc đồ thị không xác định được); `note` chỉ có khi không True."""
    p = provision or {}
    cite = p.get("citation") if isinstance(p.get("citation"), dict) else {}
    note = None
    if p and p.get("in_force") is not True:
        note = _NOT_IN_FORCE.get(p.get("reason") or "", "Không xác định được hiệu lực ở ngày áp luật")
        when = p.get("from") or p.get("until")
        if when and p.get("reason") in ("not_yet_in_force", "no_longer_in_force"):
            note += f" ({'từ' if p.get('from') else 'đến'} {when})"
    return {"pid": pid, "citation": citation_text(p.get("citation")), "text": p.get("text"),
            "in_force": p.get("in_force"), "source_url": cite.get("source_url"),
            "valid_from": cite.get("valid_from"), "valid_to": cite.get("valid_to"), "note": note}


def result_views(results: list[dict], catalog: Catalog, contract: Contract, basis: dict[str, dict]) -> list[dict]:
    """Mỗi kết quả (dạng report_json()["results"]) cộng khóa `view` để trang vẽ."""
    labels = {u.uid: u.label for u in contract.units}
    out = []
    for r in results:
        concept = catalog.concepts.get(r["concept_id"])
        holder = catalog.roles.get(concept.holder, {}).get("label") if concept else None
        anchors = (basis.get(r["concept_id"]) or {}).get("anchors") or []
        law = []
        for a in anchors:
            law.append(law_entry(a["pid"], a.get("provision")))
        view = {
            "title": concept.label if concept else r["concept_id"],
            "meaning": concept.describe if concept else "",
            "holder": holder,
            "verdict": VERDICTS.get(r["finding"], r["finding"]),
            "law_values": [{"key": k, "text": _law_value_text(v)} for k, v in (r.get("law_values") or {}).items()],
            "law": law,
            "contract": [{"label": labels.get(e.get("uid"), e.get("uid")), "quote": e.get("quote")}
                         for e in r.get("evidence") or []],
            "missing": [_missing_label(n, concept) for n in r.get("missing_facts") or []],
        }
        out.append({**r, "view": view})
    return out


__all__ = ["FACT_LABELS", "VERDICTS", "citation_text", "format_value", "law_entry", "result_views"]
