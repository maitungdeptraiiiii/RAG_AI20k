# Legal Graph acceptance run — 2026-11-17

Published to namespace `legal` in the dedicated development Neo4j instance
(`bolt://127.0.0.1:17687`, container `rag-legal-graph-dev`).
Snapshot: `s20261117024643-c06f0c`; build: `12622da3d53bc9ed`.

The graph has 114 documents, 56,792 provisions, 72,088 provision versions and
39 appendices. Structural validation reported no errors. The real Neo4j API
benchmark passed 28/28 curated cases. Local query latency was approximately
16.6 ms p50 and 199.2 ms p95; this is not a concurrent-load measurement.
See `evaluation.json` for individual assertions, source URLs, verification
statuses, dataset checksum and graph diagnostics.

This run covers temporal retrieval, version boundaries, citations, a known
reference target, guidance scope and selected appendix content. It does not
measure exhaustive legal coverage or reference precision/recall. The report
still contains unresolved references. Passing cases included six occurrences
of `needs_review` results; a retrieval pass does not approve those legal texts.

Technical validation: 125 targeted parser, versioning, store, service and graph
tests passed; eight integration tests passed against real Neo4j. A broader
legal-suite run stalled and was interrupted, so no full-suite pass is claimed.

Twenty supplementary documents and eight source attachments were downloaded.
Original attachment bytes and extraction receipts are retained in the corpus
bundle, whose manifest was verified after packing. Extracted appendices remain
`needs_review`. Luat Dan so 113/2025/QH15 contains inconsistent statute numbers
in Article 29 in both the public HTML and the original Gazette PDF. These were
preserved rather than silently corrected; absent amendment operations are
flagged during consolidation checks. A legal reviewer must resolve them before
using affected text for legal conclusions.

Original Gazette source for 113/2025/QH15:
[signed PDF](https://congbaocdn.chinhphu.vn/180507251028987904/2026/1/23/113signed-176916373445848348042.pdf).

The implementation preserves source provenance and dated amendment evidence,
does not split a continuous unchanged text version for a no-op amendment, and
keeps separate versions across changed text or temporal gaps. Partial appendix
repeals are not treated as full-document repeals. Published builds are retained
for pinned readers; storage cleanup requires separate offline maintenance.

The graph publication and changes are limited to Legal Graph and its corpus.
No Contract Graph, concept/anchor bridge or application connection was changed.

Run instructions and scope: `../../datasets/legal_graph_labor_v1.README.md`.
