"""Soạn phần hiển thị cho kết quả Kiểm tra concept (spec 2026-11-17-concept-check-streaming-ui §4).

Trang chỉ vẽ: mọi chữ người xem đọc (tiêu đề, kết luận, giá trị luật, nhãn dữ kiện) được soạn ở đây từ danh mục và
căn cứ luật; mã nội bộ (concept_id, rule_id, pid) vẫn giữ trong kết quả gốc để hiện ở dòng phụ."""
from __future__ import annotations

from rag.bridge.catalog import Catalog
from rag.contracts.models import Contract

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


def _missing_label(name: str, concept, catalog: Catalog) -> str:
    if concept is not None and name in concept.slots:
        return f"{concept.label} (nội dung trong hợp đồng)"
    return catalog.fact_label(name)


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
            "verdict": catalog.verdict_label(r["finding"]),
            "law_values": [{"key": k, "text": _law_value_text(v)} for k, v in (r.get("law_values") or {}).items()],
            "law": law,
            "contract": [{"label": labels.get(e.get("uid"), e.get("uid")), "quote": e.get("quote")}
                         for e in r.get("evidence") or []],
            "missing": [_missing_label(n, concept, catalog) for n in r.get("missing_facts") or []],
        }
        out.append({**r, "view": view})
    return out


__all__ = ["citation_text", "format_value", "law_entry", "result_views"]
