"""Catalog-backed UI library. Never query warehouse 1 to list/read sources."""
from pathlib import Path

from rag.legal.chunks import export_chunks
from rag.legal.structure import parse_structure
from rag.temporal.status import is_amendment_only


def library_documents(service):
    snapshots = service.store.reference_snapshots()
    docs = []
    for doc in service.store.documents():
        snapshot = snapshots.get(doc.document_key)
        run = service.store.latest_build(doc.document_key)
        if run:
            snapshot = None
        source_only = doc.is_consolidated
        if not snapshot and not source_only:
            try:
                source_only = is_amendment_only(parse_structure(Path(doc.raw_text_path).read_text(encoding="utf-8"), doc.document_key))
            except OSError:
                pass
        chunks = (export_chunks(service.store, doc.document_key)
                  if not source_only and run else [])
        count = len(chunks) if chunks else len(snapshot["chunks"]) if snapshot else 0
        docs.append({"doc_id": doc.document_key, "source": doc.document_key, "title": doc.title,
                     "n_chunks": count, "store": "catalog", "source_name": snapshot["source"] if snapshot else doc.title,
                     "searchable": count > 0,
                     "verification_status": "needs_review" if snapshot and not chunks else
                         ("verified" if chunks and all(c.verification_status == "verified" for c in chunks) else "needs_review")})
    return docs


def library_content(service, identity):
    snapshots = service.store.reference_snapshots()
    doc = service.store.document(identity)
    if doc is None:
        key = next((key for key, row in snapshots.items()
                    if identity in (row["source"], row["old_doc_id"])), None)
        doc = service.store.document(key) if key else None
    if doc is None:
        return None
    snapshot = snapshots.get(doc.document_key)
    try:
        content = Path(doc.raw_text_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        content = "\n\n".join(c["text"] for c in snapshot["chunks"]) if snapshot else ""
    return {"source": doc.document_key, "title": doc.title, "content": content, "is_url": False,
            "store": "catalog", "n_chunks": len(snapshot["chunks"]) if snapshot else None}
