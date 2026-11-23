"""K1: báo cáo kho luật cho các luật hợp đồng mới (docs/phan_cong_w04/khanh.md §1 K1)."""
from datetime import date, datetime, timezone

import pytest

from rag.legal.ingest_report import TARGETS, Target, ingest_rows, render_markdown
from rag.legal.models import DocumentRelation, LegalDocument
from rag.legal.store import LegalStore

DAY = date(2026, 11, 23)
KEY = "luat:19/2023/QH15"


@pytest.fixture
def store(tmp_path):
    s = LegalStore(tmp_path / "x.sqlite")
    s.upsert_document(LegalDocument(KEY, "1", "Luật Bảo vệ quyền lợi người tiêu dùng", "Luật", "19/2023/QH15", None,
                                    date(2023, 6, 20), date(2024, 7, 1), None, "Còn hiệu lực", False, "x.txt", "f" * 64,
                                    datetime(2026, 11, 23, tzinfo=timezone.utc)))
    s.add_relation(DocumentRelation("luat:99/2025/QH15", KEY, "SUA_DOI_BO_SUNG", "sửa đổi", "confirmed"))
    return s


def test_present_document_with_matching_date(store):
    rows = ingest_rows(store, [Target(KEY, "BVQLNTD", date(2024, 7, 1))], day=DAY)
    assert rows[0].present and rows[0].date_ok is True and rows[0].effective_from == date(2024, 7, 1)
    assert rows[0].amended_by == ["luat:99/2025/QH15"]


def test_missing_target_is_reported_not_dropped(store):
    rows = ingest_rows(store, [Target("luat:99/2099/QH99", "X", None)], day=DAY)
    assert rows[0].present is False and rows[0].date_ok is None


def test_wrong_date_flagged(store):
    rows = ingest_rows(store, [Target(KEY, "BVQLNTD", date(2025, 1, 1))], day=DAY)
    assert rows[0].date_ok is False


def test_unchecked_expected_date_is_none(store):
    rows = ingest_rows(store, [Target(KEY, "BVQLNTD", None)], day=DAY)
    assert rows[0].present and rows[0].date_ok is None


def test_markdown_names_snapshot_and_every_row(store):
    rows = ingest_rows(store, [Target(KEY, "BVQLNTD", date(2024, 7, 1)), Target("luat:99/2099/QH99", "X", None)], day=DAY)
    md = render_markdown(rows, snapshot_id="s1", day=DAY)
    assert "s1" in md and "BVQLNTD" in md and "| X |" in md and "THIẾU" in md


def test_targets_cover_the_four_main_laws():
    keys = {t.key for t in TARGETS}
    assert {"bo-luat:91/2015/QH13", "luat:36/2005/QH11", "luat:19/2023/QH15", "luat:27/2023/QH15"} <= keys


# ───────────── nghiệm thu K1: Huy dựng được đồ thị từ văn bản đã nạp ─────────────
from types import SimpleNamespace  # noqa: E402


def _build(*doc_keys):
    return SimpleNamespace(nodes=tuple(SimpleNamespace(props={"document_key": k}) for k in doc_keys))


def test_row_counts_graph_nodes_of_its_document(store):
    graph = _build(KEY, KEY, KEY, "luat:khac")
    rows = ingest_rows(store, [Target(KEY, "BVQLNTD", None), Target("luat:99/2099/QH99", "X", None)], day=DAY, graph=graph)
    assert rows[0].graph_nodes == 3 and rows[1].graph_nodes is None


def test_document_without_graph_nodes_is_flagged_in_markdown(store):
    rows = ingest_rows(store, [Target(KEY, "BVQLNTD", None)], day=DAY, graph=_build("luat:khac"))
    assert rows[0].graph_nodes == 0
    assert "đồ thị" in render_markdown(rows, snapshot_id="s1", day=DAY) and f"`{KEY}`: không có node nào trong đồ thị" in render_markdown(rows, snapshot_id="s1", day=DAY)


def test_markdown_has_graph_column_only_when_graph_given(store):
    plain = render_markdown(ingest_rows(store, [Target(KEY, "B", None)], day=DAY), snapshot_id="s1", day=DAY)
    withg = render_markdown(ingest_rows(store, [Target(KEY, "B", None)], day=DAY, graph=_build(KEY)), snapshot_id="s1", day=DAY)
    assert "Node đồ thị" not in plain and "Node đồ thị" in withg
