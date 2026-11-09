"""Synthetic article demo: keep articles 1/2 of v1, replace article 3 by v2."""

from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import date, datetime, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import NAMESPACE_URL, uuid5

from rag.versioning.articles import legal_article_assignments
from rag.ingest.checksum import canonical_checksum
from rag.ingest.dedup import DedupResult
if __package__ in (None, ""):
    from demo_versioning import fake_ocr_bundle
else:
    from .demo_versioning import fake_ocr_bundle
from rag.models.common import require
from rag.models.content import Block, Locator
from rag.models.document import ChangeRequest, DocumentRecord, IdentityHint, QueryScope
from rag.models.results import ParseResult
from rag.versioning.repository import VersionRepository
from rag.versioning.resolver import FullVersionResolver
from rag.versioning.scope import UnitScopeResolver

DOCUMENT_ID = str(uuid5(NAMESPACE_URL, "w02-partial-demo/document"))
V1 = str(uuid5(NAMESPACE_URL, "w02-partial-demo/v1"))
V2 = str(uuid5(NAMESPACE_URL, "w02-partial-demo/v2"))


def article_bundle(version_id: str, texts: tuple[str, ...], root: Path, name: str):
    source, original = fake_ocr_bundle(version_id, "\n\n".join(texts), root, name)
    content = [{"kind": "paragraph", "text": text} for text in texts]
    processing_id = canonical_checksum({"version": version_id, "source": source.source_id,
                                        "parser": "fake-ocr-v1", "content": content})
    processing = replace(original.processing, processing_id=processing_id, content_checksum=canonical_checksum(content))
    blocks = tuple(Block(block_id=f"{processing_id}:{i}", processing_id=processing_id,
                         version_id=version_id, order=i, kind="paragraph", text=text, origin="ocr",
                         locator=Locator(source_id=source.source_id, page=i + 1)) for i, text in enumerate(texts))
    return source, ParseResult(processing=processing, blocks=blocks)


def run_demo(database: Path) -> dict:
    repository = VersionRepository(database)
    repository.add_document(DocumentRecord(document_id=DOCUMENT_ID, title="Quy định — demo sửa Điều 3",
                                            document_type="policy", language="vi",
                                            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc)))
    planner, selector = FullVersionResolver(), UnitScopeResolver()
    results = []
    for version, name, texts in (
        (V1, "partial-demo-v1", ("Điều 1. Đối tượng\nÁp dụng cho khách hàng cá nhân.",
                                 "Điều 2. Thanh toán\nThanh toán bằng chuyển khoản.",
                                 "Điều 3. Mức phí\nMức phí là 100.000 đồng.")),
        (V2, "partial-demo-v2", ("Điều 3. Mức phí\nMức phí là 120.000 đồng.",)),
    ):
        source, parsed = article_bundle(version, texts, database.parent, name)
        catalog = repository.snapshot()
        assignments = legal_article_assignments(parsed, confirm_complete=True)
        if version == V1:
            change = ChangeRequest(kind="initial", effective_from=date(2026, 1, 1), unit_assignments=assignments)
        else:
            article3 = next(u for u in catalog.units(DOCUMENT_ID) if u.unit_key == "article:3")
            old = next(r for r in catalog.revisions(article3.unit_id) if r.version_id == V1)
            change = ChangeRequest(kind="partial", effective_from=date(2026, 7, 1), supersedes_version_ids=(V1,),
                                   unit_mapping=((old.unit_revision_id, "article:3"),), unit_assignments=assignments)
        duplicate = any(v.version_id == version for v in catalog.versions(DOCUMENT_ID))
        plan = planner.propose(parsed, hint=IdentityHint(document_id=DOCUMENT_ID), change=change, catalog=catalog,
                               dedup=DedupResult(matches=(), action="link_existing" if duplicate else "continue",
                                                 existing_version_id=version if duplicate else None, findings=()))
        require(plan.action != "review", "; ".join(plan.review_reasons))
        results.append(repository.commit(plan, parsed, source, approve=True).status)

    def select(repo, day):
        selection = selector.resolve_units(QueryScope(mode="as_of", as_of=day), catalog=repo.snapshot())
        return [{"unit": item.unit.unit_key, "version": "v1" if item.revision.version_id == V1 else "v2",
                 "text": "\n".join(b.text for b in item.blocks)} for item in selection.units]

    before = select(repository, date(2026, 6, 30))
    after = select(repository, date(2026, 7, 1))
    reopened = VersionRepository(database)
    require([item["version"] for item in before] == ["v1", "v1", "v1"], "Incorrect historical selection")
    require([item["version"] for item in after] == ["v1", "v1", "v2"], "Unaffected articles were lost")
    require(after == select(reopened, date(2026, 7, 1)), "Restart lost article data")
    return {"mode": "synthetic OCR; explicit complete article replacement; no index activation",
            "imports": results, "before_2026_07_01": before, "from_2026_07_01": after,
            "restart_preserved": True}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path)
    args = parser.parse_args()
    if args.database:
        result = run_demo(args.database)
    else:
        with TemporaryDirectory(prefix="w02-partial-") as folder:
            result = run_demo(Path(folder) / "catalog.sqlite")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
