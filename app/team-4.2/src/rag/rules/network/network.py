"""Mạng được biên dịch một lần từ catalog, dùng chung cho mọi phiên (spec §6.2).

Node điều kiện (applicability, cases[*].when) nằm trong `CondGraph` và chia sẻ giữa các rule. Phần còn lại của rule (giá trị
luật, check, kết quả) tính lại theo từng rule; chỉ mục dưới đây cho biết rule nào phải tính lại khi cái gì đổi."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Sequence

from rag.rules.derived import derived_inputs, derived_order, global_derived
from rag.rules.exceptions import ExceptionIndex
from rag.rules.model import Catalog, Rule
from rag.rules.network.nodes import CondGraph
from rag.rules.semantics import Facts, referenced


@dataclass(frozen=True)
class RuleSlot:
    index: int                              # vị trí trong catalog (concept rồi rule)
    concept_id: str
    rule: Rule
    app_node: int | None                    # node gốc của applicability (None: không điều kiện)
    when_nodes: tuple[int | None, ...]      # node gốc của cases[i].when


@dataclass(frozen=True)
class Network:
    catalog: Catalog
    graph: CondGraph
    rules: tuple[RuleSlot, ...]
    rules_by_fact: dict[str, tuple[int, ...]]       # dữ kiện -> rule tham chiếu nó (referenced)
    rules_by_node: dict[int, tuple[int, ...]]       # node điều kiện gốc -> rule dùng nó
    rules_by_concept: dict[str, tuple[int, ...]]
    derived_order: tuple[str, ...] = ()              # thứ tự tính dữ kiện suy ra (đầu vào trước)
    derived_deps: dict[str, frozenset[str]] = field(default_factory=dict)   # dữ kiện suy ra -> đầu vào trực tiếp
    exceptions: ExceptionIndex | None = None         # quan hệ exception_of giữa rule, theo RuleSlot.index
    object_slots_by_type: dict[str, tuple[int, ...]] = field(default_factory=dict)   # kiểu đối tượng -> rule xuyên đối tượng

    @staticmethod
    def compile(catalog: Catalog) -> "Network":
        derived = global_derived(catalog.context.derived)        # dữ kiện suy ra theo kiểu đối tượng nằm ở ObjectMemory
        deps = {name: frozenset(derived_inputs(df)) for name, df in derived.items()}

        def closure(name: str) -> set[str]:
            """Mọi dữ kiện (đầu vào lẫn suy ra) mà `name` phụ thuộc bắc cầu, kể cả chính nó."""
            out, todo = set(), [name]
            while todo:
                n = todo.pop()
                if n not in out:
                    out.add(n)
                    todo.extend(deps.get(n, ()))
            return out

        graph, slots = CondGraph(), []
        by_fact: dict[str, list[int]] = {}
        by_node: dict[int, list[int]] = {}
        by_concept: dict[str, list[int]] = {}
        for cid, concept in catalog.concepts.items():
            for rule in concept.rules:
                i = len(slots)
                app = graph.add(rule.applicability)
                whens = tuple(graph.add(c.get("when")) for c in rule.cases)
                slots.append(RuleSlot(i, cid, rule, app, whens))
                by_concept.setdefault(cid, []).append(i)
                for name in dict.fromkeys(m for n in referenced(rule) for m in closure(n)):
                    by_fact.setdefault(name, []).append(i)
                for node in {n for n in (app, *whens) if n is not None}:
                    by_node.setdefault(node, []).append(i)
        by_type: dict[str, list[int]] = {}
        for s in slots:
            if s.rule.over is not None:
                by_type.setdefault(s.rule.over[1], []).append(s.index)
        return Network(catalog, graph, tuple(slots), {k: tuple(v) for k, v in by_fact.items()},
                       {k: tuple(v) for k, v in by_node.items()}, {k: tuple(v) for k, v in by_concept.items()},
                       derived_order(derived) if derived else (), deps,
                       ExceptionIndex.build([(s.concept_id, s.rule) for s in slots]),
                       {k: tuple(v) for k, v in by_type.items()})


class NetworkEvaluator:
    """Biên dịch mạng một lần; mỗi `session` là trạng thái riêng của một hồ sơ."""

    def __init__(self, catalog: Catalog):
        self.network = Network.compile(catalog)

    def session(self, *, day: date, facts: Facts, present: set[str], evidence: dict[str, list[dict]],
                objects: Sequence[Any] = ()):
        from rag.rules.network.session import NetworkSession
        return NetworkSession(self.network, day, facts, present, evidence, objects)
