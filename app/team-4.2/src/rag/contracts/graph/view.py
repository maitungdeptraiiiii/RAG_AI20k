"""Giao diện đọc đồ thị hợp đồng (spec 2026-11-16-contract-graph-agent §5.4), hai bản chạy cho cùng kết quả:
`MemoryGraphView` trên `GraphBuild` vừa dựng và `Neo4jGraphView` trên bản đang công bố.

Quy ước chung: nút trả về `{"node_id", "node_type", **props}` (`node_type` = nhãn đồ thị; `label` là thuộc tính
"Điều 2" của Unit) không có `contract_id`/`build_id`, bỏ thuộc tính null
(Neo4j không lưu null), `text` dài hơn 600 ký tự bị cắt kèm `truncated: True`. Thứ tự tất định: láng giềng sắp theo
(rel, dir, node_id); đường đi ngắn nhất nhỏ nhất theo dãy (rel, dir, node_id). Mọi loại cạnh/nhãn kiểm theo SCHEMA
trước khi chạm Neo4j; giá trị luôn là tham số."""
from __future__ import annotations

from collections import deque
from typing import Literal, Protocol, Sequence, TypedDict

from rag.contracts.graph.build import SCHEMA, GraphBuild

TEXT_LIMIT = 600
UNIT_TEXT_LIMIT = 4000        # find_units: lời văn điều khoản đọc gần đủ; công cụ đi đồ thị vẫn cắt ở TEXT_LIMIT
MAX_HOPS = 6
_HIDDEN = ("contract_id", "build_id")
Direction = Literal["out", "in", "both"]


class Hop(TypedDict):
    rel: str
    dir: Literal["out", "in"]
    props: dict
    node: dict


def check_rel_types(rel_types: Sequence[str] | None) -> list[str] | None:
    if rel_types is None:
        return None
    bad = [t for t in rel_types if t not in SCHEMA["relations"]]
    if bad or isinstance(rel_types, str):
        raise ValueError(f"Loại cạnh không hợp lệ: {bad or rel_types!r}")
    return sorted(set(rel_types))


def _check_label(label: str) -> str:
    if label not in SCHEMA["nodes"]:
        raise ValueError(f"Nhãn nút không hợp lệ: {label!r}")
    return label


def _check_hops(n: int, hi: int = MAX_HOPS) -> int:
    if not isinstance(n, int) or isinstance(n, bool) or not 1 <= n <= hi:
        raise ValueError(f"Số bước phải là số nguyên 1..{hi}")
    return n


def _clean(props: dict) -> dict:
    return {k: v for k, v in props.items() if v is not None}


def _fmt(node_id: str, label: str, props: dict, limit: int | None = TEXT_LIMIT) -> dict:
    out = {"node_id": node_id, "node_type": label}
    out.update({k: v for k, v in _clean(props).items() if k not in _HIDDEN and k not in ("node_id", "node_type")})
    text = out.get("text")
    if isinstance(text, str) and limit is not None and len(text) > limit:
        out["text"], out["truncated"] = text[:limit], True
    return out


def _norm(s: str) -> str:
    return " ".join(str(s or "").casefold().split())


def _hop_key(h: Hop) -> tuple:
    return (h["rel"], h["dir"], h["node"]["node_id"])


class ContractGraphView(Protocol):
    contract_id: str
    backend: Literal["memory", "neo4j"]

    def node(self, node_id: str) -> dict | None: ...
    def find(self, label: str, _limit: int | None = ..., **props) -> list[dict]: ...
    def search_units(self, text: str, limit: int = 8) -> list[dict]: ...
    def neighbors(self, node_id: str, *, rel_types: Sequence[str] | None = None,
                  direction: Direction = "both") -> list[Hop]: ...
    def path(self, src: str, dst: str, *, rel_types: Sequence[str] | None = None,
             max_hops: int = 4) -> list[Hop] | None: ...
    def subgraph(self, node_id: str, *, hops: int = 1, rel_types: Sequence[str] | None = None,
                 limit: int = 60) -> dict: ...


class _Base:
    contract_id: str

    def _units(self, text_limit: int | None = TEXT_LIMIT) -> list[dict]:
        raise NotImplementedError

    def search_units(self, text: str, limit: int = 8) -> list[dict]:
        """Khớp trên lời văn ĐẦY ĐỦ (không phải bản đã cắt); trả về lời văn tới UNIT_TEXT_LIMIT."""
        q = _norm(text)
        if not q:
            return []
        hits = [u for u in self._units(None) if q in _norm(u.get("text", "")) or q in _norm(u.get("label", ""))]
        out = []
        for u in sorted(hits, key=lambda u: u["node_id"])[:limit]:
            t = u.get("text")
            if isinstance(t, str) and len(t) > UNIT_TEXT_LIMIT:
                u = {**u, "text": t[:UNIT_TEXT_LIMIT], "truncated": True}
            out.append(u)
        return out

    def subgraph(self, node_id: str, *, hops: int = 1, rel_types: Sequence[str] | None = None,
                 limit: int = 60) -> dict:
        types = check_rel_types(rel_types)
        _check_hops(hops, 2)
        start = self.node(node_id)
        if start is None:
            return {"nodes": [], "edges": []}
        nodes, order, frontier = {node_id: start}, [node_id], [node_id]
        edges: dict[tuple, dict] = {}
        for _ in range(hops):
            nxt = []
            for cur in frontier:
                for h in self.neighbors(cur, rel_types=types):
                    other = h["node"]["node_id"]
                    if other not in nodes:
                        if len(order) >= limit:
                            continue
                        nodes[other] = h["node"]
                        order.append(other)
                        nxt.append(other)
                    src, dst = (cur, other) if h["dir"] == "out" else (other, cur)
                    edges[(h["rel"], src, dst)] = {"type": h["rel"], "src": src, "dst": dst, "props": h["props"]}
            frontier = nxt
        keep = set(order)
        return {"nodes": [nodes[order[0]]] + sorted((nodes[i] for i in order[1:]), key=lambda n: n["node_id"]),
                "edges": [e for k, e in sorted(edges.items()) if e["src"] in keep and e["dst"] in keep]}


class MemoryGraphView(_Base):
    backend = "memory"

    def __init__(self, build: GraphBuild):
        self.contract_id = build.contract_id
        self._nodes = {n.node_id: n for n in build.nodes}
        self._adj: dict[str, list[tuple[str, str, str, dict]]] = {}
        for e in build.edges:
            self._adj.setdefault(e.src, []).append((e.type, "out", e.dst, _clean(e.props)))
            self._adj.setdefault(e.dst, []).append((e.type, "in", e.src, _clean(e.props)))

    def _out(self, node_id: str, limit: int | None = TEXT_LIMIT) -> dict:
        n = self._nodes[node_id]
        return _fmt(n.node_id, n.label, n.props, limit)

    def node(self, node_id: str) -> dict | None:
        return self._out(node_id) if node_id in self._nodes else None

    def find(self, label: str, _limit: int | None = TEXT_LIMIT, **props) -> list[dict]:
        _check_label(label)
        return [self._out(i, _limit) for i in sorted(self._nodes) if self._nodes[i].label == label
                and all(self._nodes[i].props.get(k) == v for k, v in props.items())]

    def _units(self, text_limit: int | None = TEXT_LIMIT) -> list[dict]:
        return self.find("Unit", text_limit)

    def neighbors(self, node_id, *, rel_types=None, direction="both") -> list[Hop]:
        types = check_rel_types(rel_types)
        if direction not in ("out", "in", "both"):
            raise ValueError("direction phải là out / in / both")
        hops = [Hop(rel=t, dir=d, props=dict(p), node=self._out(o)) for t, d, o, p in self._adj.get(node_id, [])
                if (types is None or t in types) and direction in ("both", d)]
        return sorted(hops, key=_hop_key)

    def path(self, src, dst, *, rel_types=None, max_hops=4) -> list[Hop] | None:
        types = check_rel_types(rel_types)
        _check_hops(max_hops)
        if src not in self._nodes or dst not in self._nodes:
            return None
        if src == dst:
            return []
        # BFS với láng giềng đã sắp: thứ tự hàng đợi trong mỗi tầng = thứ tự từ điển của đường đi
        prev: dict[str, tuple[str, Hop] | None] = {src: None}
        queue, depth = deque([src]), {src: 0}
        while queue:
            cur = queue.popleft()
            if depth[cur] >= max_hops:
                continue
            for h in self.neighbors(cur, rel_types=types):
                nxt = h["node"]["node_id"]
                if nxt in prev:
                    continue
                prev[nxt], depth[nxt] = (cur, h), depth[cur] + 1
                if nxt == dst:
                    out: list[Hop] = []
                    while prev[nxt] is not None:
                        nxt, hop = prev[nxt][0], prev[nxt][1]
                        out.append(hop)
                    return out[::-1]
                queue.append(nxt)
        return None


_NODE = "{labels: labels(n), props: properties(n)}"


def _from_row(row: dict, limit: int | None = TEXT_LIMIT) -> dict:
    label = next((x for x in row["labels"] if x != "CGNode"), "CGNode")
    return _fmt(row["props"].get("node_id"), label, row["props"], limit)


class Neo4jGraphView(_Base):
    backend = "neo4j"

    def __init__(self, store, contract_id: str):
        self.store, self.contract_id = store, contract_id

    def _run(self, query: str, **params) -> list[dict]:
        return self.store.run(query, cid=self.contract_id, **params)

    def node(self, node_id: str) -> dict | None:
        rows = self._run(f"MATCH (n:CGNode {{node_id: $id, contract_id: $cid}}) RETURN {_NODE} AS n", id=node_id)
        return _from_row(rows[0]["n"]) if rows else None

    def find(self, label: str, _limit: int | None = TEXT_LIMIT, **props) -> list[dict]:
        _check_label(label)
        rows = self._run(f"MATCH (n:CGNode:{label} {{contract_id: $cid}}) "
                         "WHERE all(k IN keys($props) WHERE n[k] = $props[k]) "
                         f"RETURN {_NODE} AS n ORDER BY n.node_id", props=props)
        return [_from_row(r["n"], _limit) for r in rows]

    def _units(self, text_limit: int | None = TEXT_LIMIT) -> list[dict]:
        return self.find("Unit", text_limit)

    def neighbors(self, node_id, *, rel_types=None, direction="both") -> list[Hop]:
        types = check_rel_types(rel_types)
        if direction not in ("out", "in", "both"):
            raise ValueError("direction phải là out / in / both")
        rows = self._run(
            "MATCH (a:CGNode {node_id: $id, contract_id: $cid})-[r]-(n:CGNode {contract_id: $cid}) "
            "WHERE $types IS NULL OR type(r) IN $types "
            f"RETURN type(r) AS rel, startNode(r) = a AS out, properties(r) AS props, {_NODE} AS n",
            id=node_id, types=types)
        hops = [Hop(rel=r["rel"], dir="out" if r["out"] else "in", props=_clean(r["props"]), node=_from_row(r["n"]))
                for r in rows]
        return sorted([h for h in hops if direction in ("both", h["dir"])], key=_hop_key)

    def path(self, src, dst, *, rel_types=None, max_hops=4) -> list[Hop] | None:
        types = check_rel_types(rel_types)
        n = _check_hops(max_hops)
        ends = self._run("MATCH (n:CGNode {contract_id: $cid}) WHERE n.node_id IN [$a, $b] RETURN n.node_id AS id",
                         a=src, b=dst)
        if {r["id"] for r in ends} != {src, dst}:
            return None
        if src == dst:
            return []
        rows = self._run(
            "MATCH (a:CGNode {node_id: $a, contract_id: $cid}), (b:CGNode {node_id: $b, contract_id: $cid}) "
            f"MATCH p = allShortestPaths((a)-[*..{n}]-(b)) "
            "WHERE all(r IN relationships(p) WHERE ($types IS NULL OR type(r) IN $types)) "
            "AND all(x IN nodes(p) WHERE x.contract_id = $cid) "
            "RETURN [x IN nodes(p) | {labels: labels(x), props: properties(x)}] AS ns, "
            "[r IN relationships(p) | {rel: type(r), src: startNode(r).node_id, props: properties(r)}] AS rs",
            a=src, b=dst, types=types)
        best = None
        for row in rows:
            ns = [_from_row(x) for x in row["ns"]]
            hops = [Hop(rel=r["rel"], dir="out" if r["src"] == ns[i]["node_id"] else "in", props=_clean(r["props"]),
                        node=ns[i + 1]) for i, r in enumerate(row["rs"])]
            if best is None or [_hop_key(h) for h in hops] < [_hop_key(h) for h in best]:
                best = hops
        return best


def run_cypher(view, query: str) -> dict:
    """Text2Cypher có rào chắn (rag.contracts.graph.cypher); chỉ bản Neo4j. Lỗi -> {"error"} để agent sửa câu."""
    from rag.contracts.graph.cypher import MAX_ROWS, TIMEOUT_S, check_cypher, clean_rows
    if getattr(view, "backend", None) != "neo4j":
        return {"error": "cypher_query cần Neo4j; đồ thị đang đọc trong bộ nhớ"}
    problem = check_cypher(query)
    if problem:
        return {"error": f"câu Cypher bị từ chối: {problem}"}
    from neo4j.exceptions import ClientError
    try:
        rows, more = view.store.run_read(query, {"cid": view.contract_id}, timeout=TIMEOUT_S, max_rows=MAX_ROWS)
    except ClientError as exc:
        return {"error": f"Cypher lỗi: {(exc.message or str(exc))[:300]}"}
    try:
        return {"rows": clean_rows(rows, view.contract_id), "truncated": more}
    except ValueError as exc:
        return {"error": f"kết quả Cypher bị từ chối: {exc}"}


def open_view(build: GraphBuild, status: dict, store) -> ContractGraphView:
    """Neo4j khi bản dựng vừa được công bố và có kho; ngược lại bộ nhớ trên chính bản dựng đó."""
    if store is not None and status.get("published"):
        return Neo4jGraphView(store, build.contract_id)
    return MemoryGraphView(build)


__all__ = ["ContractGraphView", "Hop", "MemoryGraphView", "Neo4jGraphView", "check_rel_types", "open_view", "run_cypher"]
