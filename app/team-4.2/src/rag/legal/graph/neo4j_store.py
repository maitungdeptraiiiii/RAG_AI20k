"""Ghi đồ thị luật vào Neo4j. Công bố bằng con trỏ: ghi build mới theo lô -> đổi `LGMeta.current_build` -> xóa
build cũ. Mọi truy vấn lọc theo `current_build`, nên người đọc không bao giờ thấy đồ thị dở dang."""
from __future__ import annotations

import os
from collections import defaultdict
from collections.abc import Callable, Mapping
from datetime import datetime, timezone

from rag.contracts.graph.neo4j_store import GraphConfig, GraphUnavailable
from rag.legal.graph.build import SCHEMA, LegalGraphBuild

_LABELS = frozenset(SCHEMA["nodes"])
_TYPES = frozenset(SCHEMA["relations"])


def legal_graph_config_from_env(env: Mapping[str, str] = os.environ) -> GraphConfig | None:
    """Cấu hình từ biến môi trường; None khi LEGAL_GRAPH != "1"."""
    if env.get("LEGAL_GRAPH") != "1":
        return None
    password = env.get("NEO4J_PASSWORD", "")
    if not password:
        raise ValueError("Thiếu NEO4J_PASSWORD")
    return GraphConfig(env.get("NEO4J_URI") or "bolt://localhost:7687", env.get("NEO4J_USER") or "neo4j", password,
                       env.get("NEO4J_DATABASE") or "neo4j")


def _check(value: str, allowed: frozenset, what: str) -> str:
    if value not in allowed:
        raise ValueError(f"{what} không hợp lệ: {value!r}")
    return value


def _batches(rows: list, size: int):
    for i in range(0, len(rows), size):
        yield rows[i:i + size]


class LegalGraphStore:
    def __init__(self, config: GraphConfig, *, name: str = "legal"):
        """`name`: không gian tên của đồ thị (con trỏ LGMeta và thuộc tính `graph` trên nút); kiểm thử dùng tên
        riêng để không đụng đồ thị đang công bố."""
        from neo4j import GraphDatabase  # import muộn: extra [graph] có thể chưa cài
        self.config = config
        self.name = name
        self._driver = GraphDatabase.driver(config.uri, auth=(config.user, config.password),
                                            max_transaction_retry_time=5, connection_timeout=5,
                                            connection_acquisition_timeout=5,
                                            notifications_min_severity="OFF")   # nhãn chưa tồn tại ở lần đầu

    def _session(self):
        return self._driver.session(database=self.config.database)

    def _guard(self, fn):
        from neo4j.exceptions import AuthError, ServiceUnavailable, SessionExpired
        try:
            return fn()
        except (ServiceUnavailable, AuthError, SessionExpired, OSError) as e:
            reason = (str(e).splitlines() or [type(e).__name__])[0][:200]
            raise GraphUnavailable(f"Không kết nối được Neo4j: {reason}") from e

    def _write(self, query: str, **params) -> None:
        def go():
            with self._session() as s:
                s.execute_write(lambda t: t.run(query, **params).consume())
        self._guard(go)

    def ensure_schema(self) -> None:
        for q in ("CREATE INDEX lgnode_id IF NOT EXISTS FOR (n:LGNode) ON (n.node_id, n.build_id)",
                  "CREATE INDEX lgnode_build IF NOT EXISTS FOR (n:LGNode) ON (n.build_id)",
                  "CREATE INDEX lgversion_pid IF NOT EXISTS FOR (n:ProvisionVersion) ON (n.provision_id, n.build_id)",
                  "CREATE CONSTRAINT lgmeta_id IF NOT EXISTS FOR (m:LGMeta) REQUIRE m.id IS UNIQUE"):
            def go(q=q):
                with self._session() as s:
                    s.run(q).consume()
            self._guard(go)

    def _delete_build(self, where: str, **params) -> None:
        """Xóa theo lô các nút LGNode thỏa `where` (kèm cạnh)."""
        while True:
            def go():
                with self._session() as s:
                    return s.execute_write(lambda t: t.run(
                        f"MATCH (n:LGNode) WHERE n.graph = $graph AND {where} WITH n LIMIT 5000 DETACH DELETE n "
                        "RETURN count(*) AS c", graph=self.name, **params).single()["c"])
            if not self._guard(go):
                return

    def publish(self, build: LegalGraphBuild, *, batch: int = 2000,
                before_switch: Callable[[], None] | None = None) -> None:
        """Ghi build rồi đổi con trỏ. Lỗi trước bước đổi con trỏ: build cũ vẫn là build đang công bố.
        `before_switch` chỉ dùng cho kiểm thử (mô phỏng bị ngắt giữa chừng)."""
        bid = build.build_id
        by_label: dict[str, list] = defaultdict(list)
        for n in build.nodes:
            by_label[_check(n.label, _LABELS, "Nhãn nút")].append({"node_id": n.node_id, "props": n.props})
        by_type: dict[str, list] = defaultdict(list)
        for e in build.edges:
            by_type[_check(e.type, _TYPES, "Loại cạnh")].append({"src": e.src, "dst": e.dst, "props": e.props})
        self.ensure_schema()
        current = self.current()
        if current and current["current_build"] == bid:
            return                                         # cùng snapshot, cùng phiên bản đồ thị: đã công bố
        self._delete_build("n.build_id = $bid", bid=bid)   # dọn phần dở dang của một lần ghi trước bị ngắt
        for label, rows in by_label.items():
            for chunk in _batches(rows, batch):
                self._write(f"UNWIND $rows AS r CREATE (n:LGNode:{label}) SET n = r.props, n.node_id = r.node_id, "
                            "n.graph = $graph", rows=chunk, graph=self.name)
        for typ, rows in by_type.items():
            for chunk in _batches(rows, batch):
                self._write("UNWIND $rows AS r MATCH (a:LGNode {node_id: r.src, build_id: $bid}) "
                            "MATCH (b:LGNode {node_id: r.dst, build_id: $bid}) "
                            f"CREATE (a)-[e:{typ}]->(b) SET e = r.props", rows=chunk, bid=bid)
        if before_switch:
            before_switch()
        self._write("MERGE (m:LGMeta {id: $graph}) SET m.current_build = $bid, m.snapshot_id = $sid, "
                    "m.published_at = $at, m.n_nodes = $nn, m.n_edges = $ne",
                    bid=bid, sid=build.snapshot_id, at=datetime.now(timezone.utc).isoformat(),
                    nn=len(build.nodes), ne=len(build.edges), graph=self.name)
        self._delete_build("n.build_id <> $bid", bid=bid)

    def current(self) -> dict | None:
        """Con trỏ đang công bố: current_build, snapshot_id, published_at, n_nodes, n_edges. None nếu chưa có."""
        rows = self.run("MATCH (m:LGMeta {id: $graph}) RETURN properties(m) AS p", graph=self.name)
        return rows[0]["p"] if rows else None

    def run(self, query: str, **params) -> list[dict]:
        """Truy vấn chỉ đọc."""
        def go():
            with self._session() as s:
                return s.execute_read(lambda t: [r.data() for r in t.run(query, **params)])
        return self._guard(go)

    def clear(self) -> None:
        """Xóa toàn bộ đồ thị luật và con trỏ (kiểm thử / dựng lại từ đầu)."""
        self._delete_build("true")
        self._write("MATCH (m:LGMeta {id: $graph}) DELETE m", graph=self.name)

    def close(self) -> None:
        self._driver.close()


__all__ = ["GraphUnavailable", "LegalGraphStore", "legal_graph_config_from_env"]
