"""Ghi đồ thị hợp đồng vào Neo4j: mỗi hợp đồng công bố nguyên khối trong một giao dịch."""
from __future__ import annotations

import os
from collections import defaultdict
from dataclasses import dataclass
from typing import Mapping

from rag.contracts.graph.build import SCHEMA, GraphBuild

_LABELS = frozenset(SCHEMA["nodes"])
_TYPES = frozenset(SCHEMA["relations"])


class GraphUnavailable(RuntimeError):
    """Không kết nối / xác thực được Neo4j."""


@dataclass(frozen=True)
class GraphConfig:
    uri: str
    user: str
    password: str
    database: str


def graph_config_from_env(env: Mapping[str, str] = os.environ) -> GraphConfig | None:
    """Đọc cấu hình từ biến môi trường; None khi CONTRACT_GRAPH != "1"."""
    if env.get("CONTRACT_GRAPH") != "1":
        return None
    password = env.get("NEO4J_PASSWORD", "")
    if not password:
        raise ValueError("Thiếu NEO4J_PASSWORD")
    return GraphConfig(env.get("NEO4J_URI") or "bolt://localhost:7687",
                       env.get("NEO4J_USER") or "neo4j", password,
                       env.get("NEO4J_DATABASE") or "neo4j")


def _check(value: str, allowed: frozenset, what: str) -> str:
    if value not in allowed:
        raise ValueError(f"{what} không hợp lệ: {value!r}")
    return value


class ContractGraphStore:
    """Kho đồ thị hợp đồng trên Neo4j (chỉ giữ bản dựng đang công bố)."""

    def __init__(self, config: GraphConfig):
        from neo4j import GraphDatabase  # import muộn: extra [graph] có thể chưa cài
        self.config = config
        # Neo4j sập: báo lỗi trong vài giây, không chờ ~44 s thử lại mặc định của driver
        self._driver = GraphDatabase.driver(config.uri, auth=(config.user, config.password),
                                            max_transaction_retry_time=2, connection_timeout=3,
                                            connection_acquisition_timeout=3)

    def _session(self):
        return self._driver.session(database=self.config.database)

    def _guard(self, fn):
        """Chạy fn, đổi lỗi kết nối / xác thực thành GraphUnavailable."""
        from neo4j.exceptions import AuthError, ServiceUnavailable, SessionExpired
        try:
            return fn()
        except (ServiceUnavailable, AuthError, SessionExpired, OSError) as e:
            reason = (str(e).splitlines() or [type(e).__name__])[0][:200]
            raise GraphUnavailable(f"Không kết nối được Neo4j: {reason}") from e

    def ensure_schema(self) -> None:
        """Tạo ràng buộc node_id và chỉ mục contract_id (chạy lại không lỗi)."""
        def go():
            with self._session() as s:
                s.run("CREATE CONSTRAINT cgnode_node_id IF NOT EXISTS "
                      "FOR (n:CGNode) REQUIRE n.node_id IS UNIQUE").consume()
                s.run("CREATE INDEX cgnode_contract_id IF NOT EXISTS "
                      "FOR (n:CGNode) ON (n.contract_id)").consume()
        self._guard(go)

    def publish(self, build: GraphBuild) -> None:
        """Thay toàn bộ đồ thị của hợp đồng bằng bản dựng mới trong một giao dịch."""
        by_label: dict[str, list] = defaultdict(list)
        for n in build.nodes:
            by_label[_check(n.label, _LABELS, "Nhãn nút")].append(
                {"node_id": n.node_id, "props": n.props})
        by_type: dict[str, list] = defaultdict(list)
        for e in build.edges:
            by_type[_check(e.type, _TYPES, "Loại cạnh")].append(
                {"src": e.src, "dst": e.dst, "props": e.props})
        cid = build.contract_id

        def tx(t):
            t.run("MATCH (n:CGNode {contract_id: $cid}) DETACH DELETE n", cid=cid).consume()
            for label, rows in by_label.items():
                t.run(f"UNWIND $rows AS r CREATE (n:CGNode:{label}) "
                      "SET n = r.props, n.node_id = r.node_id", rows=rows).consume()
            for typ, rows in by_type.items():
                t.run("UNWIND $rows AS r "
                      "MATCH (a:CGNode {node_id: r.src, contract_id: $cid}) "
                      "MATCH (b:CGNode {node_id: r.dst, contract_id: $cid}) "
                      f"CREATE (a)-[e:{typ}]->(b) SET e = r.props", rows=rows, cid=cid).consume()

        def go():
            with self._session() as s:
                s.execute_write(tx)
        self._guard(go)

    def current_build_id(self, contract_id: str) -> str | None:
        """build_id của nút Contract đang công bố, None nếu chưa có."""
        rows = self.run("MATCH (n:CGNode:Contract {node_id: $cid}) RETURN n.build_id AS b",
                        cid=contract_id)
        return rows[0]["b"] if rows else None

    def delete(self, contract_id: str) -> None:
        """Xóa toàn bộ đồ thị của một hợp đồng."""
        def go():
            with self._session() as s:
                s.execute_write(lambda t: t.run(
                    "MATCH (n:CGNode {contract_id: $cid}) DETACH DELETE n",
                    cid=contract_id).consume())
        self._guard(go)

    def run(self, query: str, **params) -> list[dict]:
        """Truy vấn chỉ đọc (cho kiểm thử và chẩn đoán)."""
        def go():
            with self._session() as s:
                return s.execute_read(lambda t: [r.data() for r in t.run(query, **params)])
        return self._guard(go)

    def close(self) -> None:
        self._driver.close()
