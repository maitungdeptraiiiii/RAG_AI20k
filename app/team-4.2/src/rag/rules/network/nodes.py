"""Node điều kiện ba trị có bộ đếm, chia sẻ theo khóa cấu trúc (spec §6.1 phần 1, §6.2).

`CondGraph` là đồ thị bất biến sau khi dựng: mỗi biểu thức điều kiện (lá `{fact, op, ...}` hoặc `all` / `any` / `not`)
là một node, hai biểu thức giống hệt nhau dùng chung node. `CondState` giữ trị của mọi node theo phiên; khi dữ kiện đổi
chỉ lá phụ thuộc dữ kiện đó được tính lại, các node cha cập nhật bộ đếm T/F/U của con trong O(1)."""
from __future__ import annotations

import heapq
import json
from dataclasses import dataclass, field

from rag.rules.model import Context
from rag.rules.semantics import Facts, Tri, eval_cond

_IDX = {"T": 0, "F": 1, "U": 2}


def cond_key(cond: dict) -> str:
    return json.dumps(cond, sort_keys=True, ensure_ascii=False)


@dataclass
class CondGraph:
    kinds: list[str] = field(default_factory=list)                    # "leaf" | "all" | "any" | "not"
    conds: list[dict] = field(default_factory=list)
    children: list[tuple[int, ...]] = field(default_factory=list)
    parents: list[list[int]] = field(default_factory=list)            # mỗi lần xuất hiện của node làm con tính một lần
    rank: list[int] = field(default_factory=list)                     # lá 0; node ghép 1 + rank lớn nhất của con
    leaves_by_fact: dict[str, list[int]] = field(default_factory=dict)
    _index: dict[str, int] = field(default_factory=dict)

    def add(self, cond: dict | None) -> int | None:
        """Chỉ số node gốc của `cond`; biểu thức đã có thì dùng lại. `None` (không điều kiện) -> None."""
        if cond is None:
            return None
        key = cond_key(cond)
        if key in self._index:
            return self._index[key]
        if "all" in cond or "any" in cond:
            kind = "all" if "all" in cond else "any"
            kids = tuple(self.add(c) for c in cond[kind])
        elif "not" in cond:
            kind, kids = "not", (self.add(cond["not"]),)
        else:
            kind, kids = "leaf", ()
        node = len(self.kinds)
        self.kinds.append(kind)
        self.conds.append(cond)
        self.children.append(kids)
        self.parents.append([])
        self.rank.append(0 if kind == "leaf" else 1 + max((self.rank[k] for k in kids), default=0))
        for k in kids:
            self.parents[k].append(node)
        if kind == "leaf" and cond.get("fact") is not None:
            self.leaves_by_fact.setdefault(cond["fact"], []).append(node)
        self._index[key] = node
        return node


def _from_counts(kind: str, c: list[int]) -> Tri:
    if kind == "all":
        return "F" if c[1] else ("U" if c[2] else "T")
    if kind == "any":
        return "T" if c[0] else ("U" if c[2] else "F")
    return "F" if c[0] else ("T" if c[1] else "U")                    # not: một con


class CondState:
    """Trị của mọi node theo phiên. `values[i]` = trị của node i; `counts[i]` = số con T / F / U (node ghép)."""

    def __init__(self, graph: CondGraph, facts: Facts, ctx: Context):
        self._graph = graph
        n = len(graph.kinds)
        self.values: list[Tri] = [None] * n                           # type: ignore[list-item]
        self.counts: list[list[int]] = [[0, 0, 0] for _ in range(n)]
        self.last_recomputed = n
        for i in range(n):                                            # id tăng dần là thứ tự topo (con trước cha)
            if graph.kinds[i] == "leaf":
                self.values[i] = eval_cond(graph.conds[i], facts, ctx)
            else:
                for k in graph.children[i]:
                    self.counts[i][_IDX[self.values[k]]] += 1
                self.values[i] = _from_counts(graph.kinds[i], self.counts[i])

    def update(self, changed_facts: set[str], facts: Facts, ctx: Context) -> set[int]:
        """Tính lại lá phụ thuộc `changed_facts`, lan lên cha theo rank (mỗi node tối đa một lần); trả tập node có trị đổi."""
        g, changed, queued, heap = self._graph, set(), set(), []
        for name in changed_facts:
            for leaf in g.leaves_by_fact.get(name, ()):
                if leaf not in queued:
                    queued.add(leaf)
                    heapq.heappush(heap, (0, leaf))
        recomputed = 0
        while heap:
            _, i = heapq.heappop(heap)
            recomputed += 1
            old = self.values[i]
            new = (eval_cond(g.conds[i], facts, ctx) if g.kinds[i] == "leaf"
                   else _from_counts(g.kinds[i], self.counts[i]))
            if new == old:
                continue
            self.values[i] = new
            changed.add(i)
            for p in g.parents[i]:
                self.counts[p][_IDX[old]] -= 1
                self.counts[p][_IDX[new]] += 1
                if p not in queued:
                    queued.add(p)
                    heapq.heappush(heap, (g.rank[p], p))
        self.last_recomputed = recomputed
        return changed

    def copy(self) -> "CondState":
        clone = CondState.__new__(CondState)
        clone._graph = self._graph
        clone.values = list(self.values)
        clone.counts = [list(c) for c in self.counts]
        clone.last_recomputed = self.last_recomputed
        return clone
