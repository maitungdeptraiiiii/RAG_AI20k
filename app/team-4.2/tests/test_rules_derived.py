"""Ngữ nghĩa dữ kiện suy ra (spec §5.3): cây ngoại lệ ba trị, UNKNOWN, chuỗi, mở dữ kiện thiếu."""
import dataclasses
import itertools

import pytest

from rag.rules.derived import derive_all, derived_inputs, derived_order, eval_derived, missing_inputs
from rag.rules.loader import load_pack
from rag.rules.model import CatalogError, Definition, DerivedFact
from rag.rules.semantics import CONFLICT, UNKNOWN, Fact, eval_cond

BASE_CTX = dataclasses.replace(load_pack("labor").context(), derived={})      # nền không có dữ kiện suy ra


def cond(name, value=1):
    return {"fact": name, "op": "eq", "value": value}


def d(did, when=None, exc=None, frm=None, **kw):
    return Definition(did, when, exc, frm, "value" in kw, kw.get("value"))


def df(name, *defs, unit=None):
    return DerivedFact(name, unit, tuple(defs))


def ctx_of(*dfs):
    return dataclasses.replace(BASE_CTX, derived={x.fact: x for x in dfs})


TRI_FACTS = {"T": {"x": Fact(1)}, "F": {"x": Fact(2)}, "U": {}}      # lá {x eq 1} ra T / F / U


def value_of(result):
    return result.value if isinstance(result, Fact) else result


def test_single_definition_when_truth_table():
    one = df("k", d("only", cond("x"), value="V"))
    got = {t: value_of(eval_derived(one, f, ctx_of(one))) for t, f in TRI_FACTS.items()}
    assert got == {"T": "V", "F": None, "U": UNKNOWN}
    always = df("k", d("only", None, value="V"))
    assert value_of(eval_derived(always, {}, ctx_of(always))) == "V"


def test_from_fact_missing_conflict_unknown_and_provenance():
    k = df("k", d("base", frm="src"))
    ctx = ctx_of(k)
    assert eval_derived(k, {}, ctx) is None
    assert eval_derived(k, {"src": CONFLICT}, ctx) is CONFLICT
    assert eval_derived(k, {"src": UNKNOWN}, ctx) is UNKNOWN
    got = eval_derived(k, {"src": Fact(5, "day", source="contract", uid="u1", quote="q")}, ctx)
    assert (got.value, got.unit, got.source, got.derived_by) == (5, "day", "derived", "base")
    const = df("k", d("c", None, value=3), unit="day")
    got = eval_derived(const, {}, ctx_of(const))
    assert (got.value, got.unit, got.derived_by) == (3, "day", "c")


def test_one_exception_all_nine_combinations():
    k = df("k", d("base", cond("p"), value="P"), d("exc", cond("c"), exc="base", value="X"))
    ctx = ctx_of(k)
    for parent, child in itertools.product("TFU", "TFU"):
        facts = {}
        if parent != "U":
            facts["p"] = Fact(1 if parent == "T" else 2)
        if child != "U":
            facts["c"] = Fact(1 if child == "T" else 2)
        expected = {"T": "X", "U": UNKNOWN}.get(child, {"T": "P", "F": None, "U": UNKNOWN}[parent])
        assert value_of(eval_derived(k, facts, ctx)) == expected, (parent, child)


def test_two_exceptions_same_value_different_value_unknown_and_conflict():
    def make(v1, v2):
        return df("k", d("base", None, value="P"), d("e1", cond("a"), exc="base", value=v1),
                  d("e2", cond("b"), exc="base", value=v2))

    both_true = {"a": Fact(1), "b": Fact(1)}
    k = make("X", "X")
    assert value_of(eval_derived(k, both_true, ctx_of(k))) == "X"
    k = make("X", "Y")
    assert eval_derived(k, both_true, ctx_of(k)) is CONFLICT
    # một ngoại lệ cho giá trị, một ngoại lệ UNKNOWN -> UNKNOWN (không bỏ qua ngoại lệ chưa biết: bất biến "thiếu dữ
    # kiện không thành vi phạm"; lệch khỏi chữ §5.3 bước 1, xem ledger giai đoạn 3)
    assert eval_derived(k, {"a": Fact(1)}, ctx_of(k)) is UNKNOWN
    assert eval_derived(k, {"b": Fact(1)}, ctx_of(k)) is UNKNOWN
    assert eval_derived(k, {}, ctx_of(k)) is UNKNOWN                              # hai ngoại lệ đều U
    assert value_of(eval_derived(k, {"a": Fact(2), "b": Fact(2)}, ctx_of(k))) == "P"
    # một ngoại lệ cho giá trị, ngoại lệ kia CONFLICT (ở `from`) -> CONFLICT (quyết định của kế hoạch)
    k2 = df("k", d("base", None, value="P"), d("e1", cond("a"), exc="base", value="X"),
            d("e2", cond("b"), exc="base", frm="src"))
    assert eval_derived(k2, {"a": Fact(1), "b": Fact(1), "src": CONFLICT}, ctx_of(k2)) is CONFLICT


def test_nested_exception_and_sibling_roots():
    k = df("k", d("base", None, value="P"), d("mid", cond("a"), exc="base", value="M"),
           d("deep", cond("b"), exc="mid", value="D"))
    ctx = ctx_of(k)
    assert value_of(eval_derived(k, {"a": Fact(1), "b": Fact(1)}, ctx)) == "D"      # lá sâu nhất thắng
    assert value_of(eval_derived(k, {"a": Fact(1), "b": Fact(2)}, ctx)) == "M"
    assert value_of(eval_derived(k, {"a": Fact(2), "b": Fact(2)}, ctx)) == "P"
    roots = df("k", d("r1", cond("a"), value="A"), d("r2", cond("b"), value="B"))
    assert eval_derived(roots, {"a": Fact(1), "b": Fact(1)}, ctx_of(roots)) is CONFLICT
    assert value_of(eval_derived(roots, {"a": Fact(1), "b": Fact(2)}, ctx_of(roots))) == "A"
    assert eval_derived(roots, {"a": Fact(2), "b": Fact(2)}, ctx_of(roots)) is None


def test_chain_and_overwrite_of_raw_fact():
    a_eff = df("a_eff", d("b", frm="src"))
    b_eff = df("b_eff", d("b", cond("a_eff", "V"), value=True))
    ctx = ctx_of(a_eff, b_eff)
    out = derive_all(ctx, {"src": Fact("V")})
    assert out["a_eff"].value == "V" and out["b_eff"].value is True
    # khóa thô trùng tên dữ kiện suy ra bị bỏ, và bị xóa hẳn khi kết quả suy ra là "không áp dụng"
    out = derive_all(ctx, {"a_eff": Fact("RAW"), "b_eff": Fact(False), "src": Fact("W")})
    assert out["a_eff"].value == "W" and "b_eff" not in out                          # a_eff = W nên b_eff "không áp dụng"
    # mốc UNKNOWN / CONFLICT được ghi vào bảng
    unk = df("u", d("d", cond("x"), value=1))
    assert derive_all(ctx_of(unk), {})["u"] is UNKNOWN
    assert derive_all(ctx, {"src": CONFLICT})["a_eff"] is CONFLICT
    assert derive_all(BASE_CTX, {"z": Fact(1)}) == {"z": Fact(1)}                  # không có dữ kiện suy ra: giữ nguyên


def test_derived_order_topological_and_cycle_error():
    first = df("first", d("a", frm="src"))
    second = df("second", d("a", frm="first"))
    third = df("third", d("a", cond("second", 1), value=1))
    order = derived_order({x.fact: x for x in (third, second, first)})
    assert order.index("first") < order.index("second") < order.index("third")
    loop_a, loop_b = df("la", d("a", frm="lb")), df("lb", d("a", frm="la"))
    with pytest.raises(CatalogError) as e:
        derived_order({"la": loop_a, "lb": loop_b})
    assert "la" in str(e.value) and "lb" in str(e.value)
    assert derived_inputs(df("k", d("a", cond("x"), frm="src"), d("b", cond("x"), exc="a", value=1))) == ("src", "x")


def test_missing_inputs_expansion():
    k = df("k", d("base", None, frm="kind"),
           d("exc", {"all": [cond("a"), cond("b"), cond("c", 9)]}, exc="base", value="X"))
    ctx = ctx_of(k)
    # kind có, a / b thiếu, c = 3 (F nên cả `all` là F): ngoại lệ đã quyết định -> không còn gì thiếu
    done = derive_all(ctx, {"kind": Fact("K"), "c": Fact(3)})
    assert done["k"].value == "K" and missing_inputs(["k"], done, ctx) == ()
    # c = 9 (T): ngoại lệ chưa quyết định vì a, b thiếu -> UNKNOWN; mở ra đúng hai tên đó
    facts = derive_all(ctx, {"kind": Fact("K"), "c": Fact(9)})
    assert facts["k"] is UNKNOWN
    assert missing_inputs(["k"], facts, ctx) == ("a", "b")
    # `from` thiếu cũng được liệt kê; dữ kiện thường thiếu thì là chính nó; dữ kiện đã có không thêm gì
    assert missing_inputs(["k", "zz", "c"], derive_all(ctx, {"c": Fact(9)}), ctx) == ("kind", "a", "b", "zz")
    resolved = derive_all(ctx, {"kind": Fact("K"), "a": Fact(1), "b": Fact(1), "c": Fact(9)})
    assert resolved["k"].value == "X" and missing_inputs(["k"], resolved, ctx) == ()
    # dữ kiện suy ra lồng dữ kiện suy ra: mở đệ quy tới dữ kiện đầu vào
    outer = df("outer", d("o", cond("k", "X"), value=1))
    ctx2 = ctx_of(k, outer)
    facts2 = derive_all(ctx2, {"c": Fact(9)})
    assert missing_inputs(["outer"], facts2, ctx2) == ("kind", "a", "b")


def test_unknown_derived_is_unresolved_at_leaf():
    facts = {"k": UNKNOWN}
    for op in ("eq", "lt", "in", "present", "absent"):
        assert eval_cond({"fact": "k", "op": op, "value": 1}, facts, BASE_CTX) == "U", op
