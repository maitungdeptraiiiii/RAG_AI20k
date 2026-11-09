from dataclasses import replace
from datetime import date

import pytest

from rag.legal.chunks import export_chunks
from tests.test_legal_service import BASE, make_service


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    svc = make_service(tmp_path_factory.mktemp("chunks"))
    svc.build_all()
    return svc


def test_one_group_per_article_version(built):
    chunks = [c for c in export_chunks(built.store, BASE) if c.article_id == f"{BASE}#d60"]
    assert sorted({c.valid_from for c in chunks}) == [date(2021, 1, 1), date(2022, 3, 1)]
    assert {c.verification_status for c in chunks} == {"verified"}
    assert chunks[0].section.endswith("Điều 60. Biên bản họp Hội đồng thành viên")
    assert "Chương" in chunks[0].section


def test_long_article_split_keeps_heading(built):
    chunks = export_chunks(built.store, BASE, max_syllables=120)
    by_article = {}
    for c in chunks:
        by_article.setdefault((c.article_id, c.valid_from), []).append(c)
    assert any(len(group) > 1 for group in by_article.values())
    for c in chunks:
        heading = c.text.split("\n")[0]
        assert heading.startswith("Điều ")
        assert len(c.text.split()) <= 120 + len(heading.split())
    assert len({c.chunk_id for c in chunks}) == len(chunks)


def test_metadata_carried(built):
    versions = built.store.versions(BASE)
    target = next(v for v in versions if v.provision_id == f"{BASE}#d61")
    flagged = replace(target, verification_status="needs_review", status_reasons=("operation.pending:x",),
                      notes=("note:y",))
    run = built.store.latest_build(BASE)
    built.store.save_build(run, [flagged if v is target else v for v in versions])
    (c, *_) = [c for c in export_chunks(built.store, BASE) if c.article_id == f"{BASE}#d61"]
    assert (c.verification_status, c.status_reasons, c.notes) == ("needs_review", ("operation.pending:x",), ("note:y",))
    assert c.build_id == run.build_id and c.valid_to is None
