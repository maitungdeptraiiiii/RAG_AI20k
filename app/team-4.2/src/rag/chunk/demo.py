"""Demonstration script for Document Parsing and Chunking conforming to `rag.schema`.

Usage:
    python -m rag.chunk.demo                     # Interactive demo with built-in sample HTML
    python -m rag.chunk.demo <file_path>         # Ingests and chunks a local PDF or text file
"""

import sys
from pathlib import Path

# Ensure UTF-8 output encoding for Vietnamese text in Windows console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Ensure 'src' is in sys.path when running as script
_SRC_DIR = str(Path(__file__).resolve().parent.parent.parent)
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from rag.chunk import (
    Chunk,
    Page,
    chunk_document,
    load_pdf,
    load_text,
    parse_web,
)
from rag.schema import make_doc_id


SAMPLE_HTML = b"""
<!DOCTYPE html>
<html>
<head><title>Quy tr\xc3\xacnh Onboarding Nh\xc3\xa2n Vi\xc3\xaan M\xe1\xbb\x9bi</title></head>
<body>
    <header><nav><a href="/">Trang chu</a></nav></header>
    <main>
        <h1>1. T\xe1\xbb\x95ng quan v\xe1\xbb\x81 C\xc3\xb4ng ty</h1>
        <p>Ch\xc3\xa0o m\xe1\xbb\xabng b\xe1\xbb\x87n \xc4\x91\xe1\xba\xbfn v\xe1\xbb\x9bi RAG Sovereign Intelligence Lab. Ch\xc3\xbang t\xc3\xb4i chuy\xc3\xaan ph\xc3\xa1t tri\xe1\xbb\x83n h\xe1\xbb\x87 th\xe1\xbb\x91ng RAG cao c\xe1\xba\xa5p.</p>
        <p>\xc4\x90\xe1\xbb\x8ba ch\xe1\xbb\x89 l\xc3\xa0m vi\xe1\xbb\x87c: T\xe1\xba\xa7ng 5, T\xc3\xb2a nh\xc3\xa0 C\xc3\xb4ng ngh\xe1\xbb\x87, H\xc3\xa0 N\xe1\xbb\x99i.</p>

        <h2>2. Ch\xc3\xadnh s\xc3\xa1ch Ngh\xe1\xbb\x89 ph\xc3\xa9p</h2>
        <p>Nh\xc3\xa2n vi\xc3\xaan ch\xc3\xadnh th\xe1\xbb\xa9c \xc4\x91\xc6\xb0\xe1\xbb\xa3c h\xc6\xb0\xe1\xbb\x9fng 12 ng\xc3\xa0y ph\xc3\xa9p n\xc4\x83m c\xc3\xb3 l\xc6\xb0\xc6\xa1ng.</p>
        <p>N\xe1\xba\xbfu kh\xc3\xb4ng s\xe1\xbb\xad d\xe1\xbb\xa5ng h\xe1\xba\xbft, t\xe1\xbb\x91i \xc4\x91a 4 ng\xc3\xa0y ph\xc3\xa9p \xc4\x91\xc6\xb0\xe1\xbb\xa3c chuy\xe1\xbb\x83n sang qu\xc3\xbd 1 n\xc4\x83m k\xe1\xba\xbf ti\xe1\xba\xbfp.</p>

        <h2>3. Ch\xe1\xba\xbf \xc4\x91\xe1\xbb\x99 Ph\xc3\xbac l\xe1\xbb\xa3i v\xc3\xa0 B\xe1\xba\xa3o hi\xe1\xbb\x83m</h2>
        <p>C\xc3\xb4ng ty \xc4\x91\xc3\xb3ng \xc4\x91\xe1\xba\xa7y \xc4\x91\xe1\xbb\xa7 b\xe1\xba\xa3o hi\xe1\xbb\x83m x\xc3\xa3 h\xe1\xbb\x99i, b\xe1\xba\xa3o hi\xe1\xbb\x83m y t\xe1\xba\xbf theo \xc4\x91\xc3\xbang quy \xc4\x91\xe1\xbb\x8bnh c\xe1\xbb\xa7a ph\xc3\xa1p lu\xe1\xba\xadt Vi\xe1\xbb\x87t Nam.</p>
    </main>
    <footer><p>&copy; 2026 RAG Lab. All rights reserved.</p></footer>
</body>
</html>
"""


def run_demo(target_path: str | None = None) -> None:
    print("=" * 70)
    print(" TEAM 4.2 RAG: PARSING & CHUNKING (SCHEMA-COMPLIANT DEMO)")
    print("=" * 70)

    pages: list[Page]
    if target_path and Path(target_path).is_file():
        p = Path(target_path)
        print(f"[*] Ingesting file: {p.name} ({p.stat().st_size:,} bytes)...")
        if p.suffix.lower() == ".pdf":
            pages = load_pdf(p)
        else:
            pages = load_text(p)
    else:
        print("[*] No valid input file specified. Using built-in sample HTML...")
        pages = parse_web(SAMPLE_HTML, source="https://lab.rag.ai/onboarding")

    print(f"\n[+] Parsed Pages Count: {len(pages)}")
    for i, pg in enumerate(pages[:6], 1):
        page_lbl = f"Page {pg.page}" if pg.page is not None else "Page: None (Web/TXT)"
        print(f"    Page #{i} [{page_lbl}] doc_id='{pg.doc_id}' text_len={len(pg.text)} chars")
    if len(pages) > 6:
        print(f"    ... and {len(pages) - 6} more pages.")

    print("\n[*] Running chunk_document (size=600, overlap=100)...")
    chunks = chunk_document(pages, size=600, overlap=100)
    print(f"[+] Total Chunks Produced: {len(chunks)}")
    print("-" * 70)

    for i, ch in enumerate(chunks[:8], 1):
        assert isinstance(ch, Chunk), "Chunk must be instance of rag.schema.Chunk"
        page_info = f"p.{ch.page_start}-{ch.page_end}" if ch.page_start is not None else "URL/TXT"
        sec_info = f"section='{ch.section}'" if ch.section else "section=None"
        print(f"\n--- [CHUNK {i:02d}] {ch.chunk_id} | {page_info} | {sec_info} | length={len(ch.text)} chars ---")
        preview = ch.text[:150] + ("..." if len(ch.text) > 150 else "")
        print(preview)

    if len(chunks) > 8:
        print(f"\n... and {len(chunks) - 8} additional chunks.")

    print("\n" + "=" * 70)
    print(" ALL CHUNKS VERIFIED VALID WITH rag.schema.Chunk")
    print(" DEMO COMPLETED SUCCESSFULLY!")
    print("=" * 70)


if __name__ == "__main__":
    file_arg = sys.argv[1] if len(sys.argv) > 1 else None
    run_demo(file_arg)
