"""Web and plain text parser producing `list[Page]` compliant with `rag.schema`.

Extracts clean textual content from HTML or plain text, removing boilerplate
scripts/styles/navigation. Sets `page=None` for all web/text pages as required
by the schema.
"""

from __future__ import annotations

from pathlib import Path
import urllib.request
import urllib.error

from bs4 import BeautifulSoup
from rag.schema import Page, make_doc_id, nfc
from .models import ParseError


def parse_web(
    data: bytes | str,
    source: str,
    doc_id: str | None = None,
    media_type: str = "text/html",
    encoding: str = "utf-8",
) -> list[Page]:
    """Parse HTML or plain text content into a `list[Page]`.

    Args:
        data: Raw HTML/text bytes or decoded string.
        source: URL or filename for citations.
        doc_id: Optional document hash (defaults to `make_doc_id(data)`).
        media_type: "text/html" or "text/plain".
        encoding: Text decoding fallback.

    Returns:
        A list containing a single `Page` with `page=None`.

    Raises:
        ParseError: If parsing fails or resulting text is empty.
    """
    clean_source = nfc(source.strip() or "web_document")

    # Plain text parsing
    if media_type == "text/plain":
        if isinstance(data, bytes):
            try:
                raw_text = data.decode(encoding, errors="replace")
            except Exception:
                raw_text = data.decode("utf-8", errors="replace")
        else:
            raw_text = str(data)

        text = nfc(raw_text.strip())
        if not text:
            raise ParseError("URL_NO_TEXT", "Tài liệu văn bản không có nội dung.")

        computed_doc_id = doc_id or make_doc_id(text)
        return [
            Page(
                doc_id=computed_doc_id,
                source=clean_source,
                page=None,
                text=text,
            )
        ]

    # HTML parsing: Try trafilatura first if available
    raw_html = data.decode(encoding, errors="replace") if isinstance(data, bytes) else str(data)
    extracted_text = ""

    try:
        import trafilatura  # type: ignore
        extracted_text = trafilatura.extract(raw_html, include_links=False, include_comments=False) or ""
    except ImportError:
        pass

    # Fallback to BeautifulSoup
    if not extracted_text:
        try:
            soup = BeautifulSoup(raw_html, "html.parser")
        except Exception as exc:
            raise ParseError("HTML_PARSE_ERROR", f"Lỗi phân tích cú pháp HTML: {exc}") from exc

        # Remove boilerplate elements
        for tag in soup(["script", "style", "nav", "header", "footer", "aside", "noscript", "svg", "iframe", "form"]):
            tag.decompose()

        root = soup.find("main") or soup.find("article") or soup.body or soup
        extracted_text = root.get_text("\n", strip=True)

    text = nfc(extracted_text.strip())
    if not text:
        raise ParseError(
            "URL_NO_TEXT",
            "Trang web không có nội dung văn bản trích xuất được; trang có thể yêu cầu JavaScript.",
        )

    computed_doc_id = doc_id or make_doc_id(text)
    return [
        Page(
            doc_id=computed_doc_id,
            source=clean_source,
            page=None,
            text=text,
        )
    ]


def load_url(url: str, timeout: int = 15) -> list[Page]:
    """Fetch a web page via HTTP GET and parse it into `list[Page]`."""
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Team4.2-RAG/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content_type = resp.headers.get("Content-Type", "")
            media_type = "text/plain" if "text/plain" in content_type else "text/html"
            data = resp.read()
    except urllib.error.URLError as exc:
        raise ParseError("FETCH_ERROR", f"Không thể tải URL '{url}': {exc}") from exc
    except Exception as exc:
        raise ParseError("FETCH_ERROR", f"Lỗi khi tải URL '{url}': {exc}") from exc

    return parse_web(data, source=url, media_type=media_type)


def load_text(path: Path | str, doc_id: str | None = None, encoding: str = "utf-8") -> list[Page]:
    """Read a local plain text file into `list[Page]`."""
    file_path = Path(path)
    if not file_path.is_file():
        raise ParseError("FILE_NOT_FOUND", f"Không tìm thấy tệp: {file_path}")

    data = file_path.read_bytes()
    return parse_web(data, source=file_path.name, doc_id=doc_id, media_type="text/plain", encoding=encoding)
