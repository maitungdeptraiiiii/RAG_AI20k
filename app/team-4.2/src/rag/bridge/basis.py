"""Căn cứ luật của một khái niệm tại một ngày (thiết kế phía luật §6). Bản này lấy neo từ danh mục và lời văn qua
`LegalGraph.text_at`; khi LU làm xong `concept_basis` trên đồ thị luật thì thay bằng lớp gọi thẳng hàm đó.
Thiếu căn cứ không bao giờ làm dừng báo cáo."""
from __future__ import annotations

from datetime import date
from typing import Protocol

from rag.bridge.catalog import Catalog


class LawBasis(Protocol):
    def concept_basis(self, concept_id: str, day: date) -> dict: ...


class AnchorLawBasis:
    def __init__(self, catalog: Catalog, graph=None, *, on_event=None):
        self.catalog, self.graph = catalog, graph
        self.on_event = on_event

    def concept_basis(self, concept_id: str, day: date) -> dict:
        out = {"concept_id": concept_id, "day": day.isoformat(), "anchors": [], "problems": []}
        concept = self.catalog.concepts.get(concept_id)
        if concept is None:
            out["problems"].append("unknown_concept")
            return out
        available = self.graph is not None
        for a in concept.anchors:
            if self.on_event:
                self.on_event({"type": "legal_candidate", "concept_id": concept_id, "pid": a["pid"],
                               "role": a.get("role"), "day": day.isoformat(), "queried": available})
            provision = None
            if available:
                try:
                    provision = self.graph.text_at(a["pid"], day)
                except Exception:  # noqa: BLE001 — đồ thị chưa công bố / Neo4j tắt: báo cáo vẫn chạy
                    available = False
            out["anchors"].append({"pid": a["pid"], "role": a.get("role"), "note": a.get("note"),
                                   "provision": provision})
            if self.on_event:
                self.on_event({"type": "legal_resolution", "concept_id": concept_id, "pid": a["pid"],
                               "role": a.get("role"), "day": day.isoformat(), "provision": provision,
                               "decision": ("kept" if provision.get("in_force") is True else
                                            "excluded" if provision.get("in_force") is False and
                                            provision.get("reason") in ("not_yet_in_force", "no_longer_in_force", "no_version_at_date")
                                            else "unknown")
                                           if provision else "unknown"})
        if available and self.on_event and hasattr(self.graph, "_run") and hasattr(self.graph, "_bid"):
            seen_pids = {a["pid"] for a in concept.anchors}
            doc_keys = list(dict.fromkeys(
                [a["pid"].partition("#")[0] for a in concept.anchors if "#" in a["pid"]]
                + [vs.get("document_key") for vs in (getattr(concept, "value_sources", None) or []) if vs.get("document_key")]
            ))
            day_iso = day.isoformat()
            try:
                bid = self.graph._bid()
                for dk in doc_keys:
                    chain = self.graph._run(
                        "MATCH path=(s:LawDoc {node_id: $key, build_id: $bid})-[:REPLACES*0..12]-(doc:LawDoc) "
                        "WHERE all(n IN nodes(path) WHERE n.build_id = $bid AND n.graph = $graph) "
                        "RETURN DISTINCT doc.node_id AS id, doc.doc_number AS doc_number, doc.title AS title, "
                        "doc.effective_from AS ef, doc.effective_to AS et",
                        key=dk, bid=bid,
                    )
                    for row in chain:
                        rid = row.get("id")
                        if not rid or rid in seen_pids:
                            continue
                        seen_pids.add(rid)
                        ef, et = row.get("ef") or "", row.get("et")
                        in_f = bool(ef <= day_iso and (not et or et > day_iso))
                        reason = None if in_f else ("not_yet_in_force" if ef > day_iso else "no_longer_in_force")
                        prov = {
                            "in_force": in_f,
                            "reason": reason,
                            "citation": {
                                "provision_id": rid,
                                "document_key": rid,
                                "doc_number": row.get("doc_number") or rid,
                                "doc_title": row.get("title") or rid,
                                "valid_from": ef or None,
                                "valid_to": et,
                            },
                        }
                        self.on_event({"type": "legal_candidate", "concept_id": concept_id, "pid": rid,
                                       "role": "chain", "day": day_iso, "queried": True})
                        self.on_event({"type": "legal_resolution", "concept_id": concept_id, "pid": rid,
                                       "role": "chain", "day": day_iso, "provision": prov,
                                       "decision": "kept" if in_f else "excluded"})
                for a in concept.anchors[:2]:
                    for g in self.graph.guidance(a["pid"], day)[:3]:
                        g_cite = g.get("citation") or {}
                        gpid = g_cite.get("provision_id")
                        if not gpid or gpid in seen_pids:
                            continue
                        seen_pids.add(gpid)
                        gprov = {"in_force": True, "text": g.get("text") or "", "citation": g_cite}
                        self.on_event({"type": "legal_candidate", "concept_id": concept_id, "pid": gpid,
                                       "role": "guidance", "day": day_iso, "queried": True})
                        self.on_event({"type": "legal_resolution", "concept_id": concept_id, "pid": gpid,
                                       "role": "guidance", "day": day_iso, "provision": gprov,
                                       "decision": "kept"})
            except Exception:  # noqa: BLE001 — không để lỗi mở rộng chuỗi làm hỏng báo cáo
                pass
        if not available:
            for a in out["anchors"]:
                a["provision"] = None
            out["problems"].append("basis_unavailable")
        return out


__all__ = ["AnchorLawBasis", "LawBasis"]
