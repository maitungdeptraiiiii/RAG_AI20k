"""Text văn bản pháp luật -> cây Provision (Điều / tên Điều / khoản / đoạn mở đầu khoản / điểm).

Máy trạng thái theo dòng. Đoạn trích dẫn của văn bản sửa đổi (mở bằng " hoặc “ ngay sau dòng kết thúc
bằng ":", đóng ở dòng kết thúc bằng " hoặc ”) được nối vào đơn vị hiện tại, không bao giờ tạo cấu trúc.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass, field

from rag.legal.keys import provision_id
from rag.legal.models import Address, Provision

ARTICLE_RE = re.compile(r"^Điều\s+(\d+[a-zđ]?)\s*[.:]\s*(.*)$")
CLAUSE_RE = re.compile(r"^(\d+[a-zđ]?)\.\s+\S")
POINT_RE = re.compile(r"^([a-zđ]\d*)\)\s+\S")
_HEADINGS = (
    (0, re.compile(r"^Phần\s+(?:thứ\s+\S+|[IVXLCDM]+|\d+)\b\s*[.:\-–]?\s*(.*)$")),
    (1, re.compile(r"^Chương\s+[IVXLCDM]+[a-zA-Z]?\b\s*[.:\-–]?\s*(.*)$|^Chương\s+\d+[a-z]?\b\s*[.:\-–]?\s*(.*)$")),
    (2, re.compile(r"^Mục\s+\d+[a-z]?\b\s*[.:\-–]?\s*(.*)$")),
    (3, re.compile(r"^Tiểu\s+mục\s+\d+[a-z]?\b\s*[.:\-–]?\s*(.*)$")),
)
_OPEN_QUOTE = ('"', "“")
_CLOSE_QUOTE = re.compile(r"[\"”][.;,]?$")
_DIRECTIVE_START = re.compile(r"^(?:\d+[a-zđ]?\.\s+|[a-zđ]\d*\)\s+)?(?:sửa\s+đổi|bổ\s+sung|bãi\s+bỏ|thay|bỏ|đình\s+chỉ)",
                              re.IGNORECASE)


@dataclass
class _Unit:
    address: Address
    first: int                       # chỉ số dòng đầu
    last: int                        # chỉ số dòng cuối (bao gồm)
    children: list["_Unit"] = field(default_factory=list)


def _heading(line: str) -> tuple[int, bool] | None:
    """(cấp, có tiêu đề cùng dòng không) nếu dòng là heading Phần/Chương/Mục."""
    for level, pattern in _HEADINGS:
        m = pattern.match(line)
        if m:
            rest = next((g for g in m.groups() if g), "")
            return level, bool(rest.strip())
    return None


def parse_structure(text: str, document_key: str) -> list[Provision]:
    text = unicodedata.normalize("NFC", text)
    lines = text.split("\n")
    starts, pos = [], 0
    for line in lines:
        starts.append(pos)
        pos += len(line) + 1

    def span(first: int, last: int) -> tuple[int, int]:
        return starts[first], starts[last] + len(lines[last])

    nonblank = [i for i, l in enumerate(lines) if l.strip()]
    next_line = {a: lines[b].strip() for a, b in zip(nonblank, nonblank[1:])}

    def closes_here(i: int) -> bool:
        """Dấu đóng ngoặc ở cuối dòng chỉ kết thúc đoạn trích dẫn nếu dòng sau mở chỉ dẫn mới (khoản/điểm bắt đầu
        bằng hành động, một Điều mới, dòng hành động) hoặc hết văn bản; câu trích dẫn bên trong (vd. gọi là
        “doanh nghiệp xã hội”.) không cắt ngang nội dung."""
        nxt = next_line.get(i)
        return nxt is None or ARTICLE_RE.match(nxt) is not None or _DIRECTIVE_START.match(nxt) is not None

    headings: list[str] = []                       # đường dẫn heading hiện tại
    article_headings: dict[int, tuple[str, ...]] = {}
    articles: list[_Unit] = []
    article = clause = point = None
    in_quote = False
    pending_heading_title: int | None = None       # cấp heading đang chờ dòng tiêu đề
    prev = ""

    for i, raw in enumerate(lines):
        line = raw.strip()
        if not line:
            continue
        if in_quote:
            for unit in (point, clause, article):
                if unit is not None:
                    unit.last = i
            if _CLOSE_QUOTE.search(line) and closes_here(i):
                in_quote = False
            prev = line
            continue
        if line.startswith(_OPEN_QUOTE) and prev.endswith(":") and article is not None:
            for unit in (point, clause, article):
                if unit is not None:
                    unit.last = i
            in_quote = not (len(line) > 1 and _CLOSE_QUOTE.search(line) and closes_here(i))
            prev = line
            continue

        heading = _heading(line)
        m_article = ARTICLE_RE.match(line)
        if heading is not None:
            level, inline_title = heading
            headings = headings[:level] + [line]
            pending_heading_title = None if inline_title else level
            article = clause = point = None
        elif pending_heading_title is not None and not m_article:
            headings[-1] = f"{headings[-1]} - {line}"
            pending_heading_title = None
        elif m_article:
            if any(a.address.article == m_article.group(1) for a in articles):
                break                              # Điều lặp số ngoài trích dẫn: biểu mẫu phụ lục, hết phần thân
            pending_heading_title = None
            article = _Unit(Address(m_article.group(1)), i, i)
            articles.append(article)
            article_headings[id(article)] = tuple(headings)
            clause = point = None
        elif article is not None and (m := CLAUSE_RE.match(line)):
            clause = _Unit(Address(article.address.article, m.group(1)), i, i)
            article.children.append(clause)
            article.last = i
            point = None
        elif clause is not None and (m := POINT_RE.match(line)):
            point = _Unit(Address(article.address.article, clause.address.clause, m.group(1)), i, i)
            clause.children.append(point)
            clause.last = article.last = i
        elif article is not None:
            for unit in (point, clause, article):
                if unit is not None:
                    unit.last = i
        prev = line

    out: list[Provision] = []

    def add(kind, address, parent, first, last, heading_path, text_override=None, span_override=None):
        pid = provision_id(document_key, address, kind)
        body = text_override if text_override is not None else "\n".join(lines[first:last + 1]).strip()
        out.append(Provision(pid, document_key, kind, address, parent, len(out), heading_path, body,
                             span_override or span(first, last)))
        return pid

    for art in articles:
        hp = article_headings[id(art)]
        art_pid = add("article", art.address, None, art.first, art.last, hp)
        heading_line = lines[art.first]
        m = ARTICLE_RE.match(heading_line.strip())
        title = m.group(2).strip()
        if title:
            t_start = starts[art.first] + heading_line.index(title)
            add("article_title", Address(art.address.article, part="title"), art_pid, art.first, art.first, hp,
                text_override=title, span_override=(t_start, t_start + len(title)))
        for cl in art.children:
            cl_pid = add("clause", cl.address, art_pid, cl.first, cl.last, hp)
            if cl.children:
                add("clause_lead_in", Address(cl.address.article, cl.address.clause, part="lead_in"), cl_pid,
                    cl.first, cl.children[0].first - 1, hp)
                for pt in cl.children:
                    add("point", pt.address, cl_pid, pt.first, pt.last, hp)
    return out


def index_provisions(provisions: Sequence[Provision]) -> dict[str, Provision]:
    return {p.provision_id: p for p in provisions}


__all__ = ["ARTICLE_RE", "CLAUSE_RE", "POINT_RE", "index_provisions", "parse_structure"]
