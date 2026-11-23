"""Dữ kiện suy ra (spec §5.3): cây định nghĩa / ngoại lệ ba trị. Logic thuần, dùng chung cho Reference và Network.

Một dữ kiện suy ra có các định nghĩa; định nghĩa có `exception_of` là con của định nghĩa kia. Kết quả của một nút:
giá trị (`Fact`), `CONFLICT`, `UNKNOWN`, hoặc `None` (không áp dụng -> dữ kiện thiếu)."""
from __future__ import annotations

from typing import Iterable, Mapping, Sequence

from rag.rules.model import CatalogError, Context, Definition, DerivedFact, leaves
from rag.rules.semantics import CONFLICT, UNKNOWN, Fact, Facts, eval_cond, fact_names, is_unresolved


def definition_inputs(d: Definition) -> list[str]:
    """Tên dữ kiện mà một định nghĩa đọc: `from` và các lá của `when`."""
    return list(dict.fromkeys([*([d.from_fact] if d.from_fact else []),
                               *[leaf["fact"] for leaf in leaves(d.when) if leaf.get("fact")]]))


def derived_inputs(df: DerivedFact) -> tuple[str, ...]:
    return tuple(dict.fromkeys(n for d in df.definitions for n in definition_inputs(d)))


def find_cycle(graph: Mapping[str, Sequence[str]]) -> list[str] | None:
    """Một vòng trong đồ thị phụ thuộc (đường khép kín `a -> b -> a`), hoặc None. Cạnh tới nút ngoài đồ thị bị bỏ qua."""
    state: dict[str, int] = {}

    def visit(n: str, stack: list[str]) -> list[str] | None:
        state[n] = 1
        for m in graph.get(n, ()):
            if m not in graph:
                continue
            if state.get(m) == 1:
                return [*stack[stack.index(m):], n, m] if m in stack else [n, m]
            if m not in state and (c := visit(m, [*stack, n])):
                return c
        state[n] = 2
        return None

    for node in graph:
        if node not in state and (cycle := visit(node, [])):
            return cycle
    return None


def derived_order(derived: Mapping[str, DerivedFact]) -> tuple[str, ...]:
    """Thứ tự tính: dữ kiện suy ra mà một dữ kiện khác đọc đứng trước nó. Có vòng -> CatalogError."""
    deps = {name: derived_inputs(df) for name, df in derived.items()}
    if cycle := find_cycle(deps):
        raise CatalogError(["derived: phụ thuộc vòng giữa các dữ kiện suy ra " + " -> ".join(cycle)])
    done: dict[str, None] = {}

    def visit(name: str) -> None:
        if name in done:
            return
        for n in deps[name]:
            if n in deps:
                visit(n)
        done[name] = None

    for name in deps:
        visit(name)
    return tuple(done)


def _combine(results: Sequence[object]) -> object:
    """Bước 1–2 của §5.3 cho một nhóm anh em: CONFLICT > UNKNOWN > giá trị (cùng giá trị thì giữ, khác thì CONFLICT) > None.
    UNKNOWN đứng trên giá trị (lệch chữ §5.3 bước 1) để thiếu dữ kiện không thể biến thành giá trị rồi thành vi phạm."""
    if any(r is CONFLICT for r in results):
        return CONFLICT
    if any(r is UNKNOWN for r in results):
        return UNKNOWN          # ngoại lệ chưa biết có thể cho giá trị khác: không bỏ qua (xem ledger giai đoạn 3, Ruling)
    values = [r for r in results if isinstance(r, Fact)]
    if values:
        first = values[0]
        return first if all(v.value == first.value and v.unit == first.unit for v in values) else CONFLICT
    return None


def _own(d: Definition, df: DerivedFact, facts: Facts, ctx: Context) -> object:
    if d.from_fact is None:
        return Fact(d.value, df.unit, source="derived", derived_by=d.id)
    src = facts.get(d.from_fact)
    if src is None:
        return None                                    # `from` thiếu: không áp dụng
    if is_unresolved(src):
        return src                                     # CONFLICT / UNKNOWN giữ nguyên
    if df.unit is not None and src.unit is not None and src.unit != df.unit:   # về đơn vị đã khai (hạn chế 3.11)
        value = ctx.units.convert(src.value, src.unit, df.unit) if _number(src.value) else None
        return UNKNOWN if value is None else Fact(value, df.unit, source="derived", derived_by=d.id)
    return Fact(src.value, src.unit, source="derived", derived_by=d.id)


def _number(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def eval_derived(df: DerivedFact, facts: Facts, ctx: Context) -> Fact | object | None:
    """Giá trị của một dữ kiện suy ra trên bảng `facts` (đã chứa các dữ kiện suy ra mà nó đọc)."""
    children: dict[str | None, list[Definition]] = {}
    for d in df.definitions:
        children.setdefault(d.exception_of, []).append(d)

    def node(d: Definition) -> object:
        sub = _combine([node(c) for c in children.get(d.id, ())])
        if sub is not None:
            return sub
        when = eval_cond(d.when, facts, ctx)
        if when == "F":
            return None
        if when == "U":
            return UNKNOWN
        return _own(d, df, facts, ctx)

    return _combine([node(d) for d in children.get(None, ())])


def global_derived(derived: Mapping[str, DerivedFact]) -> dict[str, DerivedFact]:
    """Dữ kiện suy ra của bảng dữ kiện phẳng (không khai `object_type`)."""
    return {n: d for n, d in derived.items() if d.object_type is None}


def derive_all(ctx: Context, facts: Facts) -> Facts:
    """Bản sao `facts` đã bỏ khóa trùng tên dữ kiện suy ra, cộng các dữ kiện suy ra tính theo thứ tự topo (chuỗi được).
    Kết quả `None` (không áp dụng) thì dữ kiện vắng mặt."""
    flat = global_derived(ctx.derived)
    if not flat:
        return dict(facts)
    out = {k: v for k, v in facts.items() if k not in flat}
    for name in derived_order(flat):
        result = eval_derived(flat[name], out, ctx)
        if result is not None:
            out[name] = result
    return out


def _inputs_where(names: Iterable[str], facts: Facts, ctx: Context, pick) -> tuple[str, ...]:
    """Dữ kiện đầu vào thỏa `pick` của `names`: dữ kiện thường -> chính nó; dữ kiện suy ra chưa có giá trị (vắng / UNKNOWN)
    -> mở thành dữ kiện đầu vào của các định nghĩa chưa quyết định (đệ quy qua dữ kiện suy ra khác)."""
    out: dict[str, None] = {}

    def visit(n: str) -> None:
        got = facts.get(n)
        if n not in ctx.derived:
            if pick(got):
                out[n] = None
            return
        if got is not None and got is not UNKNOWN:
            return
        for d in ctx.derived[n].definitions:
            when = eval_cond(d.when, facts, ctx)
            if when == "F":
                continue
            if when == "U":
                for leaf_name in fact_names(d.when):
                    visit(leaf_name)
            if d.from_fact:
                visit(d.from_fact)

    for n in names:
        visit(n)
    return tuple(out)


def missing_inputs(names: Iterable[str], facts: Facts, ctx: Context) -> tuple[str, ...]:
    """Dữ kiện đầu vào còn thiếu để quyết định `names` (người dùng / hợp đồng có thể bổ sung)."""
    return _inputs_where(names, facts, ctx, lambda got: got is None)


def conflicted_inputs(names: Iterable[str], facts: Facts, ctx: Context) -> tuple[str, ...]:
    """Dữ kiện đầu vào mâu thuẫn (CONFLICT) làm dữ kiện suy ra trong `names` chưa xác định (hạn chế 3.7)."""
    return _inputs_where(names, facts, ctx, lambda got: got is CONFLICT)
