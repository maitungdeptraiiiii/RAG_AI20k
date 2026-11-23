"""K1 (docs/phan_cong_w04/khanh.md): đối chiếu kho luật có phiên bản với danh sách văn bản các gói hợp đồng mới cần.

Chỉ đọc kho; không tải, không sửa. Ngày hiệu lực kỳ vọng ghi tay từ văn bản (None = chưa đối chiếu)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from rag.legal.store import LegalStore


@dataclass(frozen=True)
class Target:
    key: str
    name: str
    expected_from: date | None


TARGETS: tuple[Target, ...] = (
    Target("bo-luat:91/2015/QH13", "Bộ luật Dân sự 2015", date(2017, 1, 1)),
    Target("luat:36/2005/QH11", "Luật Thương mại 2005", date(2006, 1, 1)),
    Target("luat:19/2023/QH15", "Luật Bảo vệ quyền lợi người tiêu dùng 2023", date(2024, 7, 1)),
    Target("luat:27/2023/QH15", "Luật Nhà ở 2023 (hiệu lực sớm theo Luật 43/2024/QH15)", date(2024, 8, 1)),
    Target("nghi-dinh:55/2024/NĐ-CP", "NĐ 55/2024 hướng dẫn Luật BVQLNTD", date(2024, 7, 1)),
    Target("quyet-dinh:07/2024/QĐ-TTG", "QĐ 07/2024 danh mục hợp đồng theo mẫu phải đăng ký", date(2024, 7, 1)),
    Target("luat:54/2010/QH12", "Luật Trọng tài thương mại 2010", date(2011, 1, 1)),
    Target("nghi-quyet:01/2014/NQ-HĐTP", "NQ 01/2014 hướng dẫn Luật Trọng tài thương mại", date(2014, 7, 2)),
    Target("luat:05/2017/QH14", "Luật Quản lý ngoại thương 2017", date(2018, 1, 1)),
    Target("nghi-dinh:95/2024/NĐ-CP", "NĐ 95/2024 hướng dẫn Luật Nhà ở", date(2024, 8, 1)),
    Target("nghi-dinh:96/2024/NĐ-CP", "NĐ 96/2024 hướng dẫn Luật Kinh doanh bất động sản", date(2024, 8, 1)),
)


@dataclass(frozen=True)
class IngestRow:
    key: str
    name: str
    present: bool
    title: str | None = None
    status: str | None = None
    effective_from: date | None = None
    expected_from: date | None = None
    date_ok: bool | None = None
    articles: int = 0
    amended_by: list[str] = field(default_factory=list)
    built: bool = False
    graph_nodes: int | None = None     # số node của văn bản trong đồ thị luật (None: không kiểm)


def ingest_rows(store: LegalStore, targets, *, day: date, graph=None) -> list[IngestRow]:
    """`graph`: LegalGraphBuild của snapshot (rag.legal.graph.service.build_current) để đếm node mỗi văn bản; None: bỏ cột."""
    per_doc: dict[str, int] = {}
    for n in (graph.nodes if graph is not None else ()):
        k = n.props.get("document_key")
        if k:
            per_doc[k] = per_doc.get(k, 0) + 1
    rows = []
    for t in targets:
        doc = store.document(t.key)
        if doc is None:
            rows.append(IngestRow(t.key, t.name, False, expected_from=t.expected_from))
            continue
        built = store.latest_build(t.key) is not None
        eff = (store.first_valid_from(t.key) if built else None) or doc.vbpl_effective_from
        sources = {op.source_document_key for op in store.operations(target_key=t.key)}
        sources |= {r.source_key for r in store.relations(t.key) if r.target_key == t.key and r.status != "rejected"}
        articles = sum(p.kind == "article" for p in store.provisions_as_of(t.key, day)) if built else 0
        rows.append(IngestRow(t.key, t.name, True, doc.title, doc.eff_status, eff, t.expected_from,
                              None if t.expected_from is None or eff is None else eff == t.expected_from,
                              articles, sorted(sources), built, per_doc.get(t.key, 0) if graph is not None else None))
    return rows


def _d(v: date | None) -> str:
    return v.isoformat() if v else "—"


def render_markdown(rows: list[IngestRow], *, snapshot_id: str, day: date) -> str:
    with_graph = any(r.graph_nodes is not None for r in rows)
    out = [f"# Kho luật cho các gói hợp đồng mới (K1)", "",
           f"Snapshot: **{snapshot_id}** · đếm Điều tại ngày {day.isoformat()} · sinh bằng `scripts/legal_ingest_report.py`.", "",
           "| Văn bản | Khóa | Có trong kho | Trạng thái (vbpl) | Hiệu lực trong kho | Hiệu lực kỳ vọng | Khớp | Số Điều | Sửa đổi / quan hệ |"
           + (" Node đồ thị |" if with_graph else ""),
           "|---|---|---|---|---|---|---|---|---|" + ("---|" if with_graph else "")]
    notes = []
    for r in rows:
        ok = {True: "✓", False: "LỆCH", None: "chưa đối chiếu"}[r.date_ok]
        out.append(f"| {r.name} | `{r.key}` | {'có' if r.present else 'THIẾU'} | {r.status or '—'} | {_d(r.effective_from)} | "
                   f"{_d(r.expected_from)} | {ok if r.present else '—'} | {r.articles if r.present else '—'} | "
                   f"{', '.join(r.amended_by) or '—'} |" + (f" {'—' if r.graph_nodes is None else r.graph_nodes} |" if with_graph else ""))
        if with_graph and r.present and r.graph_nodes == 0:
            notes.append(f"- `{r.key}`: không có node nào trong đồ thị luật (Huy không dựng được đồ thị từ văn bản này).")
        if not r.present:
            notes.append(f"- `{r.key}` ({r.name}): THIẾU trong kho.")
        elif r.date_ok is False:
            notes.append(f"- `{r.key}`: ngày hiệu lực trong kho {_d(r.effective_from)} khác kỳ vọng {_d(r.expected_from)}.")
        elif r.present and not r.built:
            notes.append(f"- `{r.key}`: chưa có bản dựng phiên bản (không đếm được Điều).")
        if r.present and r.status and "Hết hiệu lực" in r.status and not r.amended_by:
            notes.append(f"- `{r.key}`: vbpl ghi \"{r.status}\" nhưng kho chưa có thao tác / quan hệ sửa đổi trỏ tới văn bản này.")
    out += ["", "## Ghi chú", ""] + (notes or ["- Không có văn bản thiếu hoặc lệch ngày."])
    return "\n".join(out) + "\n"


__all__ = ["IngestRow", "TARGETS", "Target", "ingest_rows", "render_markdown"]
