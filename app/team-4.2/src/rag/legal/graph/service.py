"""Đồng bộ đồ thị luật với snapshot kho luật đang công bố. Neo4j sập / cấu hình thiếu không làm hỏng kho:
hàm trả trạng thái, không ném lỗi kết nối ra ngoài."""
from __future__ import annotations

import logging

from rag.legal.graph.build import LegalGraphBuild, build_legal_graph, graph_build_id, validate
from rag.legal.graph.neo4j_store import GraphUnavailable, LegalGraphStore, legal_graph_config_from_env

log = logging.getLogger(__name__)


def build_current(manager) -> tuple[LegalGraphBuild, list[str]]:
    """(bản dựng từ snapshot đang công bố, lỗi kiểm tra). Không ghi gì."""
    snapshot = manager.current()
    store = manager.store(snapshot.snapshot_id)
    build = build_legal_graph(store, snapshot.snapshot_id)
    return build, validate(build, store)


def open_store() -> LegalGraphStore | None:
    """Kho đồ thị theo biến môi trường; None khi LEGAL_GRAPH != "1"."""
    config = legal_graph_config_from_env()
    return LegalGraphStore(config) if config else None


def graph_status(manager, store: LegalGraphStore | None) -> dict:
    """So snapshot mà đồ thị đang phản ánh với snapshot kho đang công bố."""
    current = manager.current().snapshot_id
    out = {"store_snapshot": current, "graph_snapshot": None, "graph_build": None, "stale": True, "enabled": store is not None}
    if store is None:
        return out
    try:
        meta = store.current()
    except GraphUnavailable as e:
        return out | {"error": str(e)}
    if meta:
        out |= {"graph_snapshot": meta.get("snapshot_id"), "graph_build": meta.get("current_build"),
                "published_at": meta.get("published_at"),
                "stale": meta.get("current_build") != graph_build_id(current)}
    return out


def sync_legal_graph(manager, store: LegalGraphStore | None) -> dict:
    """Dựng, kiểm tra và công bố đồ thị cho snapshot đang công bố. Trả {"status": ...}:
    disabled / up_to_date / published / invalid (kèm errors) / unavailable (kèm error)."""
    if store is None:
        return {"status": "disabled"}
    snapshot_id = manager.current().snapshot_id
    try:
        meta = store.current()
        if meta and meta.get("current_build") == graph_build_id(snapshot_id):
            return {"status": "up_to_date", "snapshot_id": snapshot_id, "build_id": meta["current_build"]}
        build, errors = build_current(manager)
        if errors:
            log.error("Đồ thị luật không hợp lệ, không công bố: %s", errors[:5])
            return {"status": "invalid", "snapshot_id": snapshot_id, "errors": errors, "report": build.report}
        store.publish(build)
        return {"status": "published", "snapshot_id": snapshot_id, "build_id": build.build_id, "report": build.report}
    except GraphUnavailable as e:
        log.warning("Đồ thị luật chưa cập nhật (snapshot %s): %s", snapshot_id, e)
        return {"status": "unavailable", "snapshot_id": snapshot_id, "error": str(e)}


__all__ = ["build_current", "graph_status", "open_store", "sync_legal_graph"]
