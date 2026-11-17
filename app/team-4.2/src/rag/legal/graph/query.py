"""Lớp đọc đồ thị luật: năm câu hỏi của spec §1. Mọi kết quả kèm trích dẫn (số hiệu, nhãn điều khoản, khoảng
hiệu lực của phiên bản, trạng thái xác minh). Chỉ đọc build mà con trỏ LGMeta đang trỏ tới."""
from __future__ import annotations

from datetime import date

from rag.legal.graph.neo4j_store import LegalGraphStore

_LIVE = "v.valid_from <= $day AND (v.valid_to IS NULL OR v.valid_to > $day)"
_CITE = ("{provision_id: p.node_id, label: p.label, kind: p.kind, document_key: d.node_id, doc_type: d.doc_type, "
         "doc_number: d.doc_number, doc_title: d.title, valid_from: v.valid_from, valid_to: v.valid_to, "
         "verification_status: v.verification_status, version_id: v.node_id, build_id: v.build_id, "
         "source_url: d.source_url, raw_checksum: d.raw_checksum, text_source: d.text_source, "
         "source_verified: d.source_verified}")
_DOC = ("{document_key: d.node_id, doc_type: d.doc_type, doc_number: d.doc_number, title: d.title, "
        "issued_on: d.issued_on, effective_from: d.effective_from, effective_to: d.effective_to, eff_status: d.eff_status}")
_OWNER = "MATCH (d:LawDoc {node_id: p.document_key, build_id: $bid})"


class GraphNotPublished(RuntimeError):
    """Chưa có đồ thị luật nào được công bố."""


def _ancestors(pid: str) -> list[str]:
    key, _, path = pid.partition("#")
    parts = path.split(".")
    return [f"{key}#{'.'.join(parts[:i])}" for i in range(1, len(parts) + 1)]


class LegalGraph:
    def __init__(self, store: LegalGraphStore, *, build_id: str | None = None, snapshot_id: str | None = None):
        self.store = store
        self.build_id = build_id
        self.snapshot_id = snapshot_id

    def pinned(self) -> LegalGraph:
        """Capture one published build for a multi-query request. Old builds are retained."""
        if self.build_id:
            return self
        current = self.status()
        if not current:
            raise GraphNotPublished("Chưa công bố đồ thị luật")
        return LegalGraph(self.store, build_id=current['current_build'], snapshot_id=current.get('snapshot_id'))

    def status(self) -> dict | None:
        """Con trỏ đang công bố (current_build, snapshot_id, published_at …) để so với snapshot của kho."""
        return self.store.current()

    def _run(self, query: str, **params) -> list[dict]:
        # A build hash may exist in independent graph namespaces (e.g. tests).
        query = query.replace('build_id: $bid', 'build_id: $bid, graph: $graph')
        return self.store.run(query, graph=self.store.name, **params)

    def _bid(self) -> str:
        if self.build_id:
            return self.build_id
        current = self.store.current()
        if not current:
            raise GraphNotPublished("Chưa công bố đồ thị luật: chạy `python -m rag.legal graph build`")
        return current["current_build"]

    def text_at(self, pid: str, day: date) -> dict:
        """Phiên bản của điều khoản hiệu lực ngày `day`. Không hiệu lực: `in_force=False` kèm `reason`
        (`unknown_provision` / `not_yet_in_force` / `no_longer_in_force`) và mốc ngày liên quan."""
        bid, d = self._bid(), day.isoformat()
        rows = self._run(
            "MATCH (p:Provision {node_id: $pid, build_id: $bid})-[:HAS_VERSION]->(v) " + _OWNER +
            " RETURN v.text AS text, v.title AS title, v.notes AS notes, v.status_reasons AS status_reasons, "
            f"({_LIVE}) AS live, {_CITE} AS citation ORDER BY v.valid_from", pid=pid, bid=bid, day=d)
        if not rows:
            return {"in_force": False, "reason": "unknown_provision", "provision_id": pid}
        live = [r for r in rows if r["live"]]
        if len(live) > 1:
            return {"in_force": None, "reason": "overlapping_versions", "provision_id": pid, "build_id": bid}
        if live:
            r = live[-1]
            return {"in_force": True, "text": r["text"], "title": r["title"], "notes": r["notes"],
                    "status_reasons": r["status_reasons"], "citation": r["citation"]}
        first, last = rows[0]["citation"], rows[-1]["citation"]
        if d < first["valid_from"]:
            return {"in_force": False, "reason": "not_yet_in_force", "from": first["valid_from"], "citation": first}
        if last['valid_to'] is None or d < last['valid_to']:
            return {"in_force": False, "reason": "no_version_at_date", "provision_id": pid, "build_id": bid}
        return {"in_force": False, "reason": "no_longer_in_force", "until": last["valid_to"], "citation": last,
                "notes": rows[-1]["notes"]}

    def changes(self, pid: str, from_day: date, to_day: date) -> list[dict]:
        """Các phiên bản của điều khoản có hiệu lực trong [from_day, to_day], mỗi phiên bản kèm văn bản đã tạo ra nó."""
        return self._run(
            "MATCH (p:Provision {node_id: $pid, build_id: $bid})-[:HAS_VERSION]->(v) " + _OWNER +
            " WHERE v.valid_from <= $to AND (v.valid_to IS NULL OR v.valid_to > $from) "
            "OPTIONAL MATCH (v)-[c:CHANGED_BY]->(s:Provision) "
            "OPTIONAL MATCH (sd:LawDoc {node_id: s.document_key, build_id: $bid}) "
            f"WITH v, {_CITE} AS citation, [x IN collect(DISTINCT {{provision_id: s.node_id, label: s.label, "
            "doc_number: sd.doc_number, doc_title: sd.title, operation_type: c.operation_type, "
            "operation_id: c.operation_id, effective_from: c.effective_from}) "
            "WHERE x.provision_id IS NOT NULL] AS changed_by "
            "RETURN v.text AS text, citation, changed_by ORDER BY v.valid_from",
            pid=pid, bid=self._bid(), **{"from": from_day.isoformat(), "to": to_day.isoformat()})

    def guidance(self, pid: str, day: date) -> list[dict]:
        """Điều khoản dưới luật quy định chi tiết `pid` (hoặc cha / con của nó), đang hiệu lực ngày `day`."""
        return self._run(
            "MATCH (t:Provision {build_id: $bid}) "
            f"WHERE (t.node_id IN $anc OR t.node_id STARTS WITH $prefix) "
            "MATCH (v:ProvisionVersion {build_id: $bid})-[r:REFERS_TO {kind: 'details'}]->(t) "
            f"WHERE {_LIVE} "
            "MATCH (p:Provision {node_id: v.provision_id, build_id: $bid}) " + _OWNER +
            f" RETURN t.node_id AS target, r.raw AS raw, v.text AS text, {_CITE} AS citation, "
            "coalesce(r.guidance_scope, 'unclassified') AS guidance_scope "
            "ORDER BY d.node_id, p.order, t.node_id",
            bid=self._bid(), anc=_ancestors(pid), prefix=pid + ".", day=day.isoformat())

    def references(self, pid: str, day: date, direction: str = "out") -> list[dict]:
        """Một bước dẫn chiếu. `out`: `pid` (và con của nó) dẫn chiếu tới đâu; `in`: điều khoản nào dẫn chiếu tới
        `pid` (hoặc con của nó). Chỉ tính phiên bản nguồn hiệu lực ngày `day`."""
        bid, d = self._bid(), day.isoformat()
        target_version = (
            "OPTIONAL MATCH (t)-[:HAS_VERSION]->(tv:ProvisionVersion {build_id: $bid}) "
            "WHERE tv.valid_from <= $day AND (tv.valid_to IS NULL OR tv.valid_to > $day) ")
        target_fields = (
            "CASE WHEN t:Provision THEN tv IS NOT NULL ELSE null END AS target_in_force, "
            "tv.node_id AS target_version_id, tv.text AS target_text, "
            "tv.verification_status AS target_verification_status, "
            "tv.valid_from AS target_valid_from, tv.valid_to AS target_valid_to")
        if direction == "out":
            return self._run(
                "MATCH (v:ProvisionVersion {build_id: $bid})-[r:REFERS_TO]->(t) "
                f"WHERE (v.provision_id = $pid OR v.provision_id STARTS WITH $prefix) AND {_LIVE} "
                + target_version +
                "RETURN v.provision_id AS source, t.node_id AS target, labels(t) AS target_labels, "
                "coalesce(t.label, t.title) AS target_label, r.raw AS raw, r.kind AS kind, " + target_fields +
                " ORDER BY source, r.offset",
                bid=bid, pid=pid, prefix=pid + ".", day=d)
        if direction != "in":
            raise ValueError("direction phải là 'out' hoặc 'in'")
        return self._run(
            "MATCH (t:Provision {build_id: $bid}) "
            f"WHERE (t.node_id = $pid OR t.node_id STARTS WITH $prefix) "
            "MATCH (v:ProvisionVersion {build_id: $bid})-[r:REFERS_TO]->(t) "
            f"WHERE {_LIVE} "
            "MATCH (p:Provision {node_id: v.provision_id, build_id: $bid}) " + _OWNER + target_version +
            f" RETURN t.node_id AS target, r.raw AS raw, r.kind AS kind, {_CITE} AS citation, " + target_fields +
            " ORDER BY d.node_id, p.order", bid=bid, pid=pid, prefix=pid + ".", day=d)

    def applicable(self, document_key: str, day: date) -> list[dict]:
        """Văn bản trong chuỗi thay thế nhau (`REPLACES`) chứa `document_key` có hiệu lực ngày `day`.
        Bình thường là đúng một văn bản; rỗng nếu không văn bản nào trong chuỗi hiệu lực ngày đó."""
        return self._run(
            "MATCH path=(s:LawDoc {node_id: $key, build_id: $bid})-[:REPLACES*0..12]-(d:LawDoc) "
            "WHERE all(n IN nodes(path) WHERE n.build_id = $bid AND n.graph = $graph) WITH DISTINCT d "
            "WHERE d.effective_from <= $day AND (d.effective_to IS NULL OR d.effective_to > $day) "
            f"RETURN {_DOC} AS document ORDER BY d.effective_from", key=document_key, bid=self._bid(),
            day=day.isoformat())

    def appendices(self, document_key: str, day: date | None = None) -> list[dict]:
        return self._run(
            "MATCH (:LawDoc {node_id: $key, build_id: $bid})-[:HAS_APPENDIX]->(a:Appendix) "
            "WHERE $day IS NULL OR ((a.valid_from IS NULL OR a.valid_from <= $day) "
            "AND (a.valid_to IS NULL OR a.valid_to > $day)) "
            "RETURN a.node_id AS appendix_id, a.number AS number, a.title AS title, a.kind AS kind, a.text AS text, "
            "a.source_url AS source_url, a.raw_checksum AS raw_checksum, "
            "a.verification_status AS verification_status, a.valid_from AS valid_from, a.valid_to AS valid_to "
            ", a.validity_source AS validity_source "
            "ORDER BY a.span_start", key=document_key, bid=self._bid(), day=day.isoformat() if day else None)

    def appendix_status(self, document_key: str) -> dict:
        """Distinguish an unassessed source from a confirmed empty appendix list."""
        rows = self._run(
            "MATCH (d:LawDoc {node_id: $key, build_id: $bid}) "
            "RETURN d.appendix_status AS status, d.source_url AS source_url",
            key=document_key, bid=self._bid())
        return rows[0] if rows else {'status': 'unknown_document'}


__all__ = ["GraphNotPublished", "LegalGraph"]
