"""HTML and plain text parser producing section-bounded TextUnits."""

from bs4 import BeautifulSoup

from .chunker import normalize_text
from .models import ParseError, TextUnit


def parse_web(data: bytes, media_type: str = "text/html", encoding: str = "utf-8") -> tuple[str, list[TextUnit]]:
    """Extract section-level TextUnits from HTML or plain text bytes.
    
    Boilerplate elements (scripts, styles, navigation, headers, footers) are stripped.
    Content is grouped under headings (h1-h6) to maintain section boundaries for citations.
    """
    if media_type == "text/plain":
        try:
            text = normalize_text(data.decode(encoding, errors="replace"))
        except LookupError:
            text = normalize_text(data.decode("utf-8", errors="replace"))
        if not text:
            raise ParseError("URL_NO_TEXT", "Trang không có nội dung văn bản.")
        return "Trang văn bản", [TextUnit(text)]

    try:
        soup = BeautifulSoup(data, "html.parser", from_encoding=encoding)
    except Exception:
        soup = BeautifulSoup(data, "html.parser")

    title = normalize_text(soup.title.get_text(" ")) if soup.title else "Trang web"

    # Remove irrelevant boilerplate elements
    for tag in soup(["script", "style", "nav", "header", "footer", "aside", "noscript", "svg", "iframe"]):
        tag.decompose()

    root = soup.find("main") or soup.find("article") or soup.body or soup
    blocks = ["h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "pre", "blockquote", "td"]
    units: list[TextUnit] = []
    section = None
    lines: list[str] = []

    for tag in root.find_all(blocks):
        if tag.find_parent(blocks):
            continue
        text = normalize_text(tag.get_text(" ", strip=True))
        if not text:
            continue
        if tag.name in blocks[:6]:  # Heading tag
            if lines:
                units.append(TextUnit("\n".join(lines), section=section))
            section, lines = text, [text]
        else:
            lines.append(text)

    if lines:
        units.append(TextUnit("\n".join(lines), section=section))

    if not units:
        text = normalize_text(root.get_text("\n", strip=True))
        if text:
            units = [TextUnit(text)]

    if not units:
        raise ParseError("URL_NO_TEXT", "Trang không có văn bản; trang yêu cầu JavaScript chưa được hỗ trợ.")

    return title[:200], units

