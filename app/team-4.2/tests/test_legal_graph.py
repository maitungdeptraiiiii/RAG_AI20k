"""Đồ thị corpus luật: dẫn chiếu, phụ lục, quan hệ văn bản, dựng và kiểm tra (không cần Neo4j)."""
from dataclasses import replace
from datetime import date, datetime, timezone

from rag.legal.graph.appendix import split_appendices
from rag.legal.graph.build import Edge, Node, build_legal_graph, validate
from rag.legal.graph.refs import DocIndex, find_refs, ref_kind, resolve
from rag.legal.graph.relations import doc_relations
from rag.legal.keys import document_key
from rag.legal.models import Address, DocumentRelation, LegalDocument
from rag.legal.service import LegalService
from rag.legal.store import LegalStore
from tests.test_legal_service import BASE, make_service

NOW = datetime(2026, 11, 13, tzinfo=timezone.utc)
BLLD19, BLLD12 = "bo-luat:45/2019/QH14", "bo-luat:10/2012/QH13"
ND145 = "nghi-dinh:145/2020/NĐ-CP"


def law(doc_type, number, title, issued, eff_from, eff_to=None, path="x.txt"):
    return LegalDocument(document_key(doc_type, number), "1", title, doc_type, number, None, issued, eff_from, eff_to,
                         "Còn hiệu lực", False, str(path), "f" * 64, NOW)


DOCS = [
    law("Bộ luật", "10/2012/QH13", "Bộ luật Lao động số 10/2012/QH13", date(2012, 6, 18), date(2013, 5, 1), date(2021, 1, 1)),
    law("Bộ luật", "45/2019/QH14", "Bộ luật Lao động số 45/2019/QH14", date(2019, 11, 20), date(2021, 1, 1)),
    law("Luật", "58/2014/QH13", "Luật Bảo hiểm xã hội số 58/2014/QH13", date(2014, 11, 20), date(2016, 1, 1), date(2025, 7, 1)),
    law("Nghị định", "145/2020/NĐ-CP", "Nghị định số 145/2020/NĐ-CP Quy định chi tiết và hướng dẫn thi hành một số điều "
        "của Bộ luật Lao động về điều kiện lao động và quan hệ lao động", date(2020, 12, 14), date(2021, 2, 1)),
    law("Nghị định", "122/2020/NĐ-CP", "Nghị định số 122/2020/NĐ-CP Quy định về phối hợp, liên thông thủ tục",
        date(2020, 10, 15), date(2020, 10, 15)),
]
INDEX = DocIndex(DOCS)
PIDS = frozenset({f"{BLLD19}#d21", f"{BLLD19}#d21.k4", f"{BLLD19}#d35.k1.d", f"{BLLD19}#d20", f"{BLLD19}#d20.k1",
                  f"{BLLD19}#d20.k2", f"{BLLD19}#d22", f"{BLLD12}#d21", f"{ND145}#d5", f"{ND145}#d5.k2", f"{ND145}#d5.k2.b",
                  f"{ND145}#d7"})


def _resolve(text, *, source=ND145, address=Address("5", "2"), day=date(2021, 2, 1), **kw):
    out = []
    for ref in find_refs(text):
        out += [(r.target, r.reason) for r in resolve(ref, source_key=source, source_address=address, valid_from=day,
                                                      index=INDEX, provision_ids=PIDS, **kw)]
    return out


# --- dẫn chiếu -------------------------------------------------------------------------------

def test_find_refs_forms():
    refs = find_refs("theo điểm a khoản 1 Điều 35, các khoản 1, 2 và 3 Điều 20; Điều 21 và Điều 22 của Bộ luật Lao động")
    assert [r.addresses for r in refs] == [
        (Address("35", "1", "a"),),
        (Address("20", "1"), Address("20", "2"), Address("20", "3")),
        (Address("21"), Address("22"))]
    assert refs[2].doc_kind == "Bộ luật" and refs[2].doc_tail.startswith("Lao động")
    assert refs[0].doc_kind is None


def test_find_refs_relative_heading_and_units():
    text = "Điều 5. Tên điều\n1. Theo khoản 2 Điều này và điểm b khoản này, trong thời hạn 10 ngày.\n2. Điều này áp dụng."
    refs = find_refs(text)
    assert [(r.raw, r.relative) for r in refs] == [("khoản 2 Điều này", "article"), ("điểm b khoản này", "clause")]
    assert all(text[r.offset:r.offset + len(r.raw)] == r.raw for r in refs)
    assert [r.addresses for r in find_refs("theo Điều 5, 10 ngày sau")] == [(Address("5"),)]


def test_find_refs_document_number_and_appendix():
    refs = find_refs("theo Nghị định số 122/2020/NĐ-CP ngày 15 tháng 10 năm 2020 và Phụ lục I ban hành kèm theo Nghị định này")
    assert [(r.raw, r.addresses, r.appendix) for r in refs] == [
        ("Nghị định số 122/2020/NĐ-CP", (), None), ("Phụ lục I", (), "I")]


def test_resolve_rules():
    assert _resolve("khoản 1 Điều 20 của Bộ luật Lao động") == [(f"{BLLD19}#d20.k1", None)]          # tên luật, theo ngày
    assert _resolve("Điều 21 của Bộ luật Lao động", day=date(2015, 1, 1)) == [(f"{BLLD12}#d21", None)]  # đời luật cũ
    assert _resolve("khoản 2 Điều 5 của Nghị định này") == [(f"{ND145}#d5.k2", None)]
    assert _resolve("điểm b khoản này") == [(f"{ND145}#d5.k2.b", None)]
    assert _resolve("khoản 2 Điều này") == [(f"{ND145}#d5.k2", None)]
    assert _resolve("Điều 7") == [(f"{ND145}#d7", None)]                                              # cùng văn bản
    assert _resolve("Nghị định số 122/2020/NĐ-CP") == [("nghi-dinh:122/2020/NĐ-CP", None)]


def test_resolve_scope_article_points_at_guided_law():
    got = _resolve("Hợp đồng lao động theo khoản 4 Điều 21; điểm d khoản 1 Điều 35.", address=Address("1", "2"),
                   guided_key=BLLD19, in_scope_article=True)
    assert got == [(f"{BLLD19}#d21.k4", None), (f"{BLLD19}#d35.k1.d", None)]
    ref = find_refs("theo khoản 4 Điều 21")[0]
    assert ref_kind(ref, BLLD19, "theo khoản 4 Điều 21", guided_keys=[BLLD19], in_scope_article=True) == "details"
    assert ref_kind(ref, ND145, "theo khoản 4 Điều 21", guided_keys=[BLLD19], in_scope_article=True) == "cite"


def test_resolve_unresolved_reasons():
    assert _resolve("Điều 99 của Bộ luật Lao động") == [(None, "provision_not_found")]
    assert _resolve("Điều 5 của Luật Doanh nghiệp") == [(None, "doc_not_in_store")]
    assert _resolve("Nghị định số 999/2020/NĐ-CP") == [(None, "doc_not_in_store")]
    twins = DocIndex(DOCS + [law("Bộ luật", "99/2019/QH14", "Bộ luật Lao động số 99/2019/QH14", date(2019, 1, 1), date(2021, 1, 1))])
    assert twins.resolve("Bộ luật", "Lao động", date(2022, 1, 1)) == (None, "ambiguous_law")


# --- phụ lục ---------------------------------------------------------------------------------

BODY = "NGHỊ ĐỊNH\nĐiều 1. Phạm vi\nNội dung.\nĐiều 2. Hiệu lực\nNghị định này có hiệu lực.\n"


def test_split_appendices_list_and_form():
    text = (BODY + "Nơi nhận:\n- Như trên;\nTM. CHÍNH PHỦ\nPhụ lục I\nDANH MỤC ĐỊA BÀN ÁP DỤNG\n1. Vùng I gồm quận A.\n"
            "Phụ lục II\nMẫu số 01\nHỢP ĐỒNG\nĐiều 1. Thời hạn\n- Từ ngày ..........\n")
    end, parts = split_appendices(text)
    assert text[end:].startswith("Nơi nhận:")
    assert [(p.number, p.kind) for p in parts] == [("I", "list"), ("II", "form")]
    assert parts[0].title == "Phụ lục I - DANH MỤC ĐỊA BÀN ÁP DỤNG" and "quận A" in parts[0].text
    assert text[parts[1].span[0]:parts[1].span[1]] == parts[1].text


def test_split_appendices_none_and_body_headings():
    assert split_appendices(BODY) == (None, [])
    # "DANH MỤC …" là tên chương trong phần thân; câu "Phụ lục I là phần …" không phải tiêu đề
    text = "Điều 1. A\nDANH MỤC NGHỀ\nĐiều 2. B\nNội dung.\nBỘ TRƯỞNG\nPhụ lục I là phần không tách rời của Thông tư.\n"
    end, parts = split_appendices(text)
    assert text[end:].startswith("BỘ TRƯỞNG") and parts == []


def test_split_appendices_restarted_articles_without_signature():
    end, parts = split_appendices("Điều 1. A\nNội dung.\nĐiều 2. B\nNội dung.\nMẫu số 01\nĐiều 1. Thời hạn\n- ........\n")
    assert end is not None and parts == []            # không có tiêu đề phụ lục sau ranh giới: chỉ ghi ranh giới


# --- quan hệ văn bản --------------------------------------------------------------------------

def test_guides_and_based_on():
    decree = DOCS[3]
    text = ("NGHỊ ĐỊNH\nCăn cứ Luật Tổ chức Chính phủ ngày 19 tháng 6 năm 2015;\nCăn cứ Bộ luật Lao động ngày 20 tháng 11 năm 2019;\n"
            "Căn cứ Luật Bảo hiểm xã hội ngày 20 tháng 11 năm 2014;\nĐiều 1. Phạm vi điều chỉnh\nCăn cứ Bộ luật Lao động cũ.")
    assert [(t, k) for t, k, _ in doc_relations(decree, text, INDEX)] == [("GUIDES", BLLD19), ("BASED_ON", "luat:58/2014/QH13")]
    assert doc_relations(DOCS[1], text, INDEX) == []                     # luật không "hướng dẫn" luật
    wage = law("Nghị định", "293/2025/NĐ-CP", "Nghị định số 293/2025/NĐ-CP Quy định mức lương tối thiểu đối với người lao "
               "động làm việc theo hợp đồng lao động", date(2025, 11, 10), date(2026, 1, 1))
    assert [(t, k) for t, k, _ in doc_relations(wage, text, INDEX)] == [("BASED_ON", BLLD19), ("BASED_ON", "luat:58/2014/QH13")]


# --- dựng ------------------------------------------------------------------------------------

def _built(tmp_path):
    svc = make_service(tmp_path)
    svc.store.add_relation(DocumentRelation("luat:03/2022/QH15", BASE, "SUA_DOI_BO_SUNG", "Điều 7", "confirmed"))
    svc.build_all()
    return svc, build_legal_graph(svc.store, "s1")


def test_build_structure_versions_and_changed_by(tmp_path):
    svc, build = _built(tmp_path)
    assert validate(build, svc.store) == []
    nodes = {n.node_id: n for n in build.nodes}
    assert nodes[BASE].label == "LawDoc" and nodes[BASE].props["doc_number"] == "59/2020/QH14"
    k3 = nodes[f"{BASE}#d60.k3"]
    assert (k3.label, k3.props["kind"], k3.props["label"]) == ("Provision", "clause", "khoản 3 Điều 60")
    versions = sorted(n.node_id for n in build.nodes if n.props.get("provision_id") == f"{BASE}#d60.k3")
    assert versions == [f"{BASE}#d60.k3@2021-01-01", f"{BASE}#d60.k3@2022-03-01"]
    assert nodes[versions[0]].props["valid_to"] == "2022-03-01" and "valid_to" not in nodes[versions[1]].props
    assert nodes[f"{BASE}#d60@2021-01-01"].props["title"]              # tên Điều là thuộc tính, không phải nút
    assert not any(n.node_id.endswith((".title", ".lead")) for n in build.nodes)
    edges = {(e.type, e.src, e.dst) for e in build.edges}
    assert ("HAS_PROVISION", BASE, f"{BASE}#d60") in edges and ("CHILD_OF", f"{BASE}#d60.k3", f"{BASE}#d60") in edges
    assert ("AMENDS", "luat:03/2022/QH15", BASE) in edges
    changed = [e for e in build.edges if e.type == "CHANGED_BY" and e.src == versions[1]]
    assert changed and changed[0].dst.startswith("luat:03/2022/QH15#d7")
    refs = [e for e in build.edges if e.type == "REFERS_TO"]
    assert refs and all(e.props["kind"] in ("cite", "details") for e in refs)
    assert build.report["refs"]["resolved"] > 0


def test_build_is_deterministic(tmp_path):
    svc, build = _built(tmp_path)
    again = build_legal_graph(svc.store, "s1")
    assert (again.build_id, again.nodes, again.edges) == (build.build_id, build.nodes, build.edges)
    assert build_legal_graph(svc.store, "s2").build_id != build.build_id


def test_validate_catches_bad_graphs(tmp_path):
    svc, build = _built(tmp_path)
    vid = f"{BASE}#d60.k3@2022-03-01"
    bad_edge = replace(build, edges=build.edges + (Edge("HAS_VERSION", "nowhere", vid, {}), Edge("LIKES", BASE, BASE, {})))
    assert {e.split(":")[0] for e in validate(bad_edge, svc.store)} == {"dangling_edge", "unknown_relation"}
    overlap = tuple(replace(n, props=n.props | {"valid_to": "2023-01-01"}) if n.node_id == f"{BASE}#d60.k3@2021-01-01" else n
                    for n in build.nodes)
    assert f"overlapping_versions:{BASE}#d60.k3" in validate(replace(build, nodes=overlap), svc.store)
    extra = build.nodes + (Node("x", "Ghost", {}), Node(BASE, "LawDoc", {}))
    kinds = {e.split(":")[0] for e in validate(replace(build, nodes=extra), svc.store)}
    assert {"unknown_label", "duplicate_node"} <= kinds
    missing = tuple(n for n in build.nodes if n.node_id != vid)
    assert any(e.startswith("version_count_mismatch") for e in validate(replace(build, nodes=missing), svc.store))
