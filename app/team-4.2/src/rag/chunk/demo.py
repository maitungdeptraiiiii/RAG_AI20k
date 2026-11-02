"""Standalone demonstration script for Document Parsing and Chunking.

Usage:
    python chunk/demo.py                 # Runs interactive demo with sample HTML
    python chunk/demo.py <file_path>     # Parses and chunks a PDF or HTML file
"""

import sys
from pathlib import Path

# Ensure UTF-8 output encoding for Vietnamese text in Windows console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Add project root to sys.path if running as script
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from chunk import make_chunks, parse_pdf, parse_web


SAMPLE_HTML = b"""
<!DOCTYPE html>
<html>
<head><title>Quy trinh Onboarding Nhan Vien Moi</title></head>
<body>
    <header><nav><a href="/">Trang chu</a></nav></header>
    <main>
        <h1>1. Tong quan ve Cong ty</h1>
        <p>Chao mung ban den voi RAG Sovereign Intelligence Lab. Chung toi chuyen phat trien he thong RAG cao cap.</p>
        <p>Dia chi lam viec: Tang 5, Toa nha Cong nghe, Ha Noi.</p>

        <h2>2. Chinh sach Nghi phep</h2>
        <p>Nhan vien chinh thuc duoc huong 12 ngay phep nam co luong.</p>
        <p>Neu khong su dung het, toi da 4 ngay phep duoc chuyen sang quy 1 nam ke tiep.</p>

        <h2>3. Che do Phuc loi va Bao hiem</h2>
        <p>Cong ty dong day du bao hiem xa hoi, bao hiem y te theo dung quy dinh cua phap luat Viet Nam.</p>
        <p>Ngoai ra, moi nhan vien duoc cap the bao hiem suc khoe cao cap hang nam.</p>
    </main>
    <footer><p>&copy; 2026 RAG Lab. All rights reserved.</p></footer>
</body>
</html>
"""


def run_demo(target_path: str | None = None):
    print("=" * 70)
    print(" RAG RECURSIVE SENTENCE-AWARE CHUNKING DEMO")
    print("=" * 70)

    if target_path and Path(target_path).is_file():
        path = Path(target_path)
        data = path.read_bytes()
        print(f"[*] Parsing local file: {path.name} ({len(data)} bytes)...")
        if path.suffix.lower() == ".pdf":
            units = parse_pdf(data)
            title = path.name
        else:
            title, units = parse_web(data)
    else:
        print("[*] No file provided. Running with built-in sample HTML document...")
        title, units = parse_web(SAMPLE_HTML)

    print(f"\n[+] Document Title: {title}")
    print(f"[+] Total Structural Units (TextUnits): {len(units)}")
    for i, u in enumerate(units[:8], 1):
        if u.pages and len(u.pages) > 1:
            meta = f"Pages {u.pages[0]}-{u.pages[-1]} (Cross-Page Merged)"
        elif u.page:
            meta = f"Page {u.page}"
        else:
            meta = f"Section: '{u.section}'"
        print(f"    Unit #{i} [{meta}]: {len(u.text)} chars")
    if len(units) > 8:
        print(f"    ... and {len(units) - 8} more units.")

    print("\n[*] Applying Recursive Sentence-Aware Chunking (target_size=800, overlap=150)...")
    chunk_size = 800
    chunk_overlap = 150
    chunks = make_chunks("doc_demo_001", units, size=chunk_size, overlap=chunk_overlap)

    print(f"[+] Total Chunks Produced: {len(chunks)} (size={chunk_size}, overlap={chunk_overlap})")
    print("-" * 70)

    for i, ch in enumerate(chunks, 1):
        pages_list = ch.get("pages", [ch.get("page")])
        if len(pages_list) > 1:
            meta = f"Pages: {pages_list[0]}-{pages_list[-1]}"
        elif pages_list and pages_list[0] is not None:
            meta = f"Page: {pages_list[0]}"
        else:
            meta = f"Section: '{ch.get('section')}'"

        print(f"\n--- [CHUNK {i:02d}] ID: {ch['chunk_id']} | {meta} | Length: {len(ch['text'])} chars ---")
        print(ch["text"])

    print("\n" + "=" * 70)
    print(" DEMO COMPLETED SUCCESSFULLY!")
    print("=" * 70)


if __name__ == "__main__":
    file_arg = sys.argv[1] if len(sys.argv) > 1 else None
    run_demo(file_arg)
