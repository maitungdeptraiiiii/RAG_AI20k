"""H3: mọi neo (`anchors`), nguồn giá trị (`value_sources`) và nguồn của kỳ giá trị luật (`law.*.periods[].source`)
của các gói giải được trên ĐỒ THỊ LUẬT dựng từ snapshot đang công bố (như `text_at(pid, ngày)`): điều khoản có trên đồ
thị và có phiên bản hiệu lực trong kỳ mà giá trị luật được dùng. Dựng đồ thị thuần Python (không cần Neo4j)."""
from __future__ import annotations

from datetime import date
from functools import lru_cache
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
LEGAL = ROOT / "data" / "team-4.2" / "legal"
PACKS = ROOT / "src" / "rag" / "rules" / "packs"
pytestmark = pytest.mark.skipif(not (LEGAL / "CURRENT").is_file(), reason="không có kho luật cục bộ")


@lru_cache(maxsize=1)
def graph() -> tuple[set[str], dict[str, list[tuple[date, date | None]]], set[str]]:
    from rag.legal.graph.build import build_legal_graph
    from rag.legal.snapshots import SnapshotManager
    mgr = SnapshotManager(LEGAL)
    sid = mgr.current().snapshot_id
    build = build_legal_graph(mgr.store(sid), sid)
    provisions = {n.node_id for n in build.nodes if n.label == "Provision"}
    versions: dict[str, list[tuple[date, date | None]]] = {}
    for n in build.nodes:
        if n.label == "ProvisionVersion":
            p = n.props
            versions.setdefault(p["provision_id"], []).append(
                (date.fromisoformat(p["valid_from"]), date.fromisoformat(p["valid_to"]) if p.get("valid_to") else None))
    for n in build.nodes:                     # nguồn là cả văn bản: khoảng hiệu lực của văn bản
        if n.label == "LawDoc" and n.props.get("effective_from"):
            to = n.props.get("effective_to")
            versions[n.node_id] = [(date.fromisoformat(n.props["effective_from"]), date.fromisoformat(to) if to else None)]
    return provisions, versions, {n.node_id for n in build.nodes if n.label == "LawDoc"}


def references():
    """(gói, khái niệm, pid, kỳ [từ, đến) hoặc None) cho mọi tham chiếu luật của các gói."""
    for f in sorted(PACKS.glob("*/concepts.yaml")):
        data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        for c in data.get("concepts") or []:
            for a in c.get("anchors") or []:
                yield f.parent.name, c["id"], a["pid"], None
            for r in c.get("rules") or []:
                for law in (r.get("law") or {}).values():
                    ps = sorted(law.get("periods") or [], key=lambda p: str(p["valid_from"]))
                    for i, p in enumerate(ps):
                        if p.get("source"):
                            end = date.fromisoformat(str(ps[i + 1]["valid_from"])) if i + 1 < len(ps) else None
                            yield f.parent.name, c["id"], p["source"], (date.fromisoformat(str(p["valid_from"])), end)


def _overlaps(versions, period) -> bool:
    lo, hi = period
    return any((vto is None or vto > lo) and (hi is None or vfrom < hi) for vfrom, vto in versions)


def value_sources():
    for f in sorted(PACKS.glob("*/concepts.yaml")):
        for c in (yaml.safe_load(f.read_text(encoding="utf-8")) or {}).get("concepts") or []:
            for v in c.get("value_sources") or []:
                yield f.parent.name, c["id"], v["document_key"]


def test_value_source_documents_are_on_the_legal_graph():
    docs = graph()[2]
    assert [x for x in value_sources() if x[2] not in docs] == []


def test_every_pack_reference_resolves_on_the_legal_graph():
    provisions, versions, _ = graph()
    refs = list(references())
    missing = [(p, c, pid) for p, c, pid, _ in refs if pid not in (provisions if "#" in pid else graph()[2])]
    no_version = [(p, c, pid) for p, c, pid, _ in refs if pid in provisions and not versions.get(pid)]
    assert len(refs) >= 100 and missing == [] and no_version == []


def test_law_value_sources_are_in_force_during_their_period():
    """Nguồn của một kỳ giá trị luật phải có phiên bản hiệu lực giao với kỳ đó (vd. NĐ lương tối thiểu theo kỳ)."""
    _, versions, _ = graph()
    bad = [(p, c, pid, period) for p, c, pid, period in references()
           if period is not None and not _overlaps(versions.get(pid, []), period)]
    assert bad == []
