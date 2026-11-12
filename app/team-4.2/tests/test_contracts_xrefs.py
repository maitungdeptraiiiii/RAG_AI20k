from rag.contracts.doc import PartSpec, Unit
from rag.contracts.xrefs import find_xrefs


def U(uid, level, text, parent=None, part="p0"):
    return Unit(uid, part, parent, level, uid.rsplit(".", 1)[-1], uid, text, 0, len(text), None, None)


UNITS = [U("p0.d2", "article", "Điều 2."), U("p0.d2.k1", "clause", "1. Giá", "p0.d2"),
         U("p0.d9", "article", "Điều 9."),
         U("p0.d9.k1", "clause", "1. Bên A chấm dứt.", "p0.d9"),
         U("p0.d9.k3", "clause", "3. Trường hợp tại khoản 1 Điều này và khoản 1 Điều 2; xem Điều 15; "
                                  "theo Điều 328 Bộ luật Dân sự; giá tại Phụ lục 1.", "p0.d9")]
PARTS = [PartSpec("p0", "main", "", 0, None), PartSpec("p1", "appendix", "PHỤ LỤC 1", 999, 1)]


def test_resolution_kinds():
    refs = {(r.raw, r.to_uid, r.kind) for r in find_xrefs(UNITS, PARTS)}
    assert ("khoản 1 Điều này", "p0.d9.k1", "internal") in refs
    assert ("khoản 1 Điều 2", "p0.d2.k1", "internal") in refs
    assert ("Điều 15", None, "missing") in refs
    assert ("Điều 328 Bộ luật Dân sự", None, "external_law") in refs
    assert ("Phụ lục 1", None, "appendix") in refs


def test_self_and_ancestor_refs_dropped():
    units = [U("p0.d3", "article", "Điều 3. Theo Điều này các bên…")]
    assert find_xrefs(units, PARTS[:1]) == []


def test_appendix_scoping_point_and_dedup():
    units = [U("p0.d1", "article", "Điều 1."),
             U("p1.pre", "preamble", "Phụ lục số 01: Điều 1 của Hợp đồng và Điều 1; Điều 1.", None, "p1"),
             U("p1.d1", "article", "Điều 1.", None, "p1"),
             U("p0.d4", "article", "Điều 4."),
             U("p0.d4.k2", "clause", "2. Chung", "p0.d4"),
             U("p0.d4.k3", "clause", "3. Theo điểm a khoản 2 Điều 4, điểm b và khoản 2.", "p0.d4"),
             U("p0.d4.k2.b", "point", "b) Xem điểm đ khoản 2 Điều 4.", "p0.d4.k2")]
    got = [(r.from_uid, r.raw, r.to_uid, r.kind) for r in find_xrefs(units, PARTS)]
    assert ("p1.pre", "Điều 1", "p0.d1", "internal") in got
    assert ("p1.pre", "Điều 1", "p1.d1", "internal") in got
    assert sum(1 for g in got if g[:2] == ("p1.pre", "Điều 1")) == 2  # dedup
    assert not any(g[1] == "Phụ lục số 01" for g in got)  # đích là chính nó -> bỏ
    assert ("p0.d4.k3", "điểm a khoản 2 Điều 4", None, "missing") in got
    assert ("p0.d4.k3", "điểm b", None, "missing") in got
    assert ("p0.d4.k3", "khoản 2", "p0.d4.k2", "internal") in got
    assert ("p0.d4.k2.b", "điểm đ khoản 2 Điều 4", None, "missing") in got
