"""HTML nội dung vbpl -> text cho parser cấu trúc: xuống dòng ở thẻ khối, nối liền thẻ nội dòng.

vbpl bọc từng mẩu chữ trong <span> (lớp text của trình xem PDF); `rag.ingest.vbpl.html_to_text` xuống
dòng giữa mọi phần tử nên cắt vụn chữ ("Th\\nủ\\nt\\nướng"). Hàm cũ giữ nguyên vì snapshot 6 Bộ luật dựa
vào nó; kho luật dùng hàm này.
"""

from __future__ import annotations

import re
import unicodedata

_BLOCKS = ["p", "div", "li", "tr", "td", "th", "table", "h1", "h2", "h3", "h4", "h5", "h6",
           "blockquote", "section", "article", "header", "footer", "body"]


def html_to_legal_text(html: str) -> str:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup(["script", "style", "noscript", "head"]):
        tag.decompose()
    for br in soup.find_all("br"):
        br.replace_with("\n")
    for tag in soup.find_all(_BLOCKS):
        tag.insert_before("\n")
        tag.append("\n")
    lines = (re.sub(r"\s+", " ", line).strip() for line in soup.get_text("").splitlines())
    return unicodedata.normalize("NFC", "\n".join(line for line in lines if line))


__all__ = ["html_to_legal_text"]
