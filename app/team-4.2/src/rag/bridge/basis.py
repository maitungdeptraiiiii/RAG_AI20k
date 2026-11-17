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
    def __init__(self, catalog: Catalog, graph=None):
        self.catalog, self.graph = catalog, graph

    def concept_basis(self, concept_id: str, day: date) -> dict:
        out = {"concept_id": concept_id, "day": day.isoformat(), "anchors": [], "problems": []}
        concept = self.catalog.concepts.get(concept_id)
        if concept is None:
            out["problems"].append("unknown_concept")
            return out
        available = self.graph is not None
        for a in concept.anchors:
            provision = None
            if available:
                try:
                    provision = self.graph.text_at(a["pid"], day)
                except Exception:  # noqa: BLE001 — đồ thị chưa công bố / Neo4j tắt: báo cáo vẫn chạy
                    available = False
            out["anchors"].append({"pid": a["pid"], "role": a.get("role"), "note": a.get("note"),
                                   "provision": provision})
        if not available:
            for a in out["anchors"]:
                a["provision"] = None
            out["problems"].append("basis_unavailable")
        return out


__all__ = ["AnchorLawBasis", "LawBasis"]
