"""Node điều kiện ba trị có bộ đếm, chia sẻ theo khóa cấu trúc (spec §6.1 phần 1, §6.2)."""
import random

from rag.rules.loader import load_pack
from rag.rules.network.nodes import CondGraph, CondState
from rag.rules.semantics import CONFLICT, UNKNOWN, Fact, eval_cond

CTX = load_pack("labor").context()
NAMES = ["a", "b", "c", "d", "e", "f"]


def rand_leaf(rng):
    name, op = rng.choice(NAMES), rng.choice(["eq", "lt", "in", "present", "absent"])
    if op == "eq" or op == "lt":
        return {"fact": name, "op": op, "value": rng.randint(0, 2)}
    if op == "in":
        return {"fact": name, "op": op, "value": [0, 1]}
    return {"fact": name, "op": op}


def rand_cond(rng, depth=3):
    if depth == 0 or rng.random() < 0.3:
        return rand_leaf(rng)
    kind = rng.choice(["all", "any", "not"])
    if kind == "not":
        return {"not": rand_cond(rng, depth - 1)}
    return {kind: [rand_cond(rng, depth - 1) for _ in range(rng.randint(1, 3))]}


def rand_value(rng):
    return rng.choice([Fact(0), Fact(1), Fact(2), CONFLICT, UNKNOWN, None])


A = {"fact": "a", "op": "eq", "value": 1}
B = {"fact": "b", "op": "lt", "value": 2}


def test_shared_subexpression_is_one_node():
    g = CondGraph()
    first, second = g.add({"all": [A, B]}), g.add({"any": [A, {"not": B}]})
    assert g.add(A) == g.add(dict(A)) and g.add({"all": [A, B]}) == first and first != second
    assert len(g.kinds) == 5                       # A, B, all, not, any (không phải 3 + 4)
    assert g.add(None) is None
    assert g.leaves_by_fact["a"] == [g.add(A)] and g.kinds[g.add(A)] == "leaf"


def test_state_values_equal_eval_cond_after_random_updates():
    rng = random.Random(7)
    g, conds = CondGraph(), [rand_cond(rng) for _ in range(200)]
    roots = [g.add(c) for c in conds]
    facts = {}
    state = CondState(g, facts, CTX)
    for step in range(100):
        changed = set(rng.sample(NAMES, rng.randint(1, 3)))
        for name in changed:
            v = rand_value(rng)
            facts.pop(name, None) if v is None else facts.__setitem__(name, v)
        state.update(changed, facts, CTX)
        for cond, root in zip(conds, roots):
            assert state.values[root] == eval_cond(cond, facts, CTX), (step, cond)


def test_update_returns_only_changed_nodes_and_touches_only_dependents():
    g = CondGraph()
    root = g.add({"all": [A, B]})
    facts = {"a": Fact(1), "b": Fact(0)}
    state = CondState(g, facts, CTX)
    assert state.values[root] == "T"
    assert state.update({"z"}, facts, CTX) == set() and state.last_recomputed == 0
    before = list(state.values)
    facts["a"] = Fact(2)
    changed = state.update({"a"}, facts, CTX)
    assert changed == {i for i, (x, y) in enumerate(zip(before, state.values)) if x != y} and root in changed
    assert state.values[root] == "F" and state.last_recomputed >= 2


def test_copy_is_independent():
    g = CondGraph()
    root = g.add({"any": [A, B]})
    facts = {"a": Fact(1), "b": Fact(5)}
    state = CondState(g, facts, CTX)
    clone = state.copy()
    facts2 = {"a": Fact(2), "b": Fact(5)}
    clone.update({"a"}, facts2, CTX)
    assert clone.values[root] == "F" and state.values[root] == "T"
    state.update({"b"}, {"a": Fact(1), "b": Fact(0)}, CTX)      # bộ đếm của bản gốc vẫn đúng sau khi bản sao đổi
    assert state.values[root] == "T"


def test_date_values_get_their_own_node_without_crashing():
    import datetime as dt
    g = CondGraph()
    d = g.add({"fact": "start", "op": "gte", "value": dt.date(2021, 1, 1)})
    s = g.add({"fact": "start", "op": "gte", "value": "2021-01-01"})
    assert d is not None and s is not None and d != s
    assert g.add({"fact": "start", "op": "gte", "value": dt.date(2021, 1, 1)}) == d
