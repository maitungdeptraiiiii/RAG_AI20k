"""Publish a validated build by pointer under a renewable namespace writer lease.

Old builds remain available to pinned readers. Removal is explicit offline
maintenance, never part of the pointer switch.
"""
from __future__ import annotations

import os
import uuid
from collections import defaultdict
from collections.abc import Callable, Mapping
from datetime import datetime, timezone

from rag.contracts.graph.neo4j_store import GraphConfig, GraphUnavailable
from rag.legal.graph.build import SCHEMA, LegalGraphBuild

_LABELS = frozenset(SCHEMA["nodes"])
_TYPES = frozenset(SCHEMA["relations"])


class GraphPublicationBusy(RuntimeError):
    """Another publisher holds this namespace's renewable lease."""


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
                  "CREATE CONSTRAINT lgnode_identity IF NOT EXISTS FOR (n:LGNode) REQUIRE (n.graph, n.build_id, n.node_id) IS UNIQUE",
                  "CREATE INDEX lgprovision_lookup IF NOT EXISTS FOR (n:Provision) ON (n.graph, n.build_id, n.node_id)",
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
        self.ensure_schema()
        token = uuid.uuid4().hex
        def acquire():
            with self._session() as session:
                return session.execute_write(lambda tx: list(tx.run(
                    "MERGE (m:LGMeta {id: $graph}) "
                    "SET m.lock_version = coalesce(m.lock_version, 0) + 1 "
                    "WITH m WHERE m.publisher IS NULL OR m.lease_until < datetime() "
                    "SET m.publisher = $token, m.lease_until = datetime() + duration('PT10M') "
                    "RETURN m.id AS id", graph=self.name, token=token)))
        if not self._guard(acquire):
            raise GraphPublicationBusy(f'Graph {self.name} đang được công bố')
        try:
            self._publish(build, token=token, batch=batch, before_switch=before_switch)
        finally:
            self._write("MATCH (m:LGMeta {id: $graph}) WHERE m.publisher = $token "
                        "REMOVE m.publisher, m.lease_until", graph=self.name, token=token)

    def _renew(self, token: str) -> None:
        def go():
            with self._session() as session:
                return session.execute_write(lambda tx: list(tx.run(
                    "MATCH (m:LGMeta {id: $graph}) WHERE m.publisher = $token "
                    "SET m.lease_until = datetime() + duration('PT10M') RETURN m.id AS id",
                    graph=self.name, token=token)))
        if not self._guard(go):
            raise GraphPublicationBusy('Mất quyền công bố graph')

    def _publish(self, build: LegalGraphBuild, *, token: str, batch: int = 2000,
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
                self._renew(token)
                self._write(f"UNWIND $rows AS r CREATE (n:LGNode:{label}) SET n = r.props, n.node_id = r.node_id, "
                            "n.graph = $graph", rows=chunk, graph=self.name)
        for typ, rows in by_type.items():
            for chunk in _batches(rows, batch):
                self._renew(token)
                self._write("UNWIND $rows AS r MATCH (a:LGNode {node_id: r.src, build_id: $bid, graph: $graph}) "
                            "MATCH (b:LGNode {node_id: r.dst, build_id: $bid, graph: $graph}) "
                            f"CREATE (a)-[e:{typ}]->(b) SET e = r.props", rows=chunk, bid=bid, graph=self.name)
        if before_switch:
            before_switch()
        self._renew(token)
        self._write("MERGE (m:LGMeta {id: $graph}) SET m.current_build = $bid, m.snapshot_id = $sid, "
                    "m.published_at = $at, m.n_nodes = $nn, m.n_edges = $ne",
                    bid=bid, sid=build.snapshot_id, at=datetime.now(timezone.utc).isoformat(),
                    nn=len(build.nodes), ne=len(build.edges), graph=self.name)
        # Do not delete old builds here: in-flight pinned readers still need them.
        # clear() remains the explicit offline maintenance operation.

    def current(self) -> dict | None:
        """Con trỏ đang công bố: current_build, snapshot_id, published_at, n_nodes, n_edges. None nếu chưa có."""
        rows = self.run("MATCH (m:LGMeta {id: $graph}) RETURN properties(m) AS p", graph=self.name)
        return rows[0]["p"] if rows and rows[0]['p'].get('current_build') else None

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


__all__ = ["GraphUnavailable", "GraphPublicationBusy", "LegalGraphStore", "legal_graph_config_from_env"]
