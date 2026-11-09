"""Mask PII trước embedding / BM25 / contextual LLM / log / chunks.jsonl — W02-02f.

Loại hỗ trợ (placeholder có loại, đánh số ổn định trong một tài liệu):

    email    a.b@example.test                      -> [EMAIL_1]
    phone    0912 345 678, 0912.345.678, 0912 345678, +84 912 345 678, 024 3974 1234 -> [PHONE_1]
    cccd     12 số, mã tỉnh 001–096 (có hoặc không có từ khoá "CCCD")  -> [CCCD_1]
    cmnd     9 số, CHỈ khi có từ khoá "CMND"/"chứng minh nhân dân"     -> [CMND_1]
    mst      10 hoặc 10-3 / 13 số, CHỈ khi có từ khoá "MST"/"mã số thuế" -> [MST_1]
    bank     6–19 số, CHỈ khi có từ khoá "STK"/"số tài khoản"          -> [BANK_1]
    name     sau "Họ và tên:" / "Họ tên:" (các từ viết hoa liên tiếp, ≥2 từ), hoặc cột bảng tên người -> [NAME_1]

Nguyên tắc chống báo nhầm (văn bản luật đầy số):
- Dãy số chỉ bị coi là CMND/MST/STK khi có từ khoá ngay trước. Số tiền ("84.000.000.000 đồng"),
  số hiệu văn bản ("45/2019/QH14"), ngày ("01.07.2026"), số Điều/khoản không bị mask.
- Số điện thoại phải đúng đầu số (di động 03/05/07/08/09, cố định 02x) và đúng kiểu nhóm số;
  dấu chấm chỉ chấp nhận ở dạng 0xxx.xxx.xxx, không chấp nhận sau tiền tố 84.

Kết quả không chứa PII gốc hay bảng tra ngược. Bảng giá trị -> placeholder chỉ sống trong RAM
trong lúc mask một tài liệu (để cùng giá trị lặp lại ra cùng placeholder), không ghi ra đĩa.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field

EntityType = str  # "email" | "phone" | "cccd" | "cmnd" | "mst" | "bank" | "name"

_B = r"(?<![\w./,+-])"        # không dính vào chữ/số/dấu phân cách phía trước
_E = r"(?![\w]|[./,-]\d)"     # không dính tiếp chữ/số phía sau

# Lookahead cho phép dấu chấm KẾT THÚC CÂU ngay sau email ("... a@b.vn."), chỉ cấm ".chữ" (email dài hơn)
EMAIL_RE = re.compile(r"(?<![\w.@+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?![\w@+-]|\.\w)")

PHONE_RE = re.compile(
    _B
    + r"(?:"
    + r"0[35789]\d{8}"                              # 0912345678
    + r"|0[35789]\d{2}[ .-]\d{3}[ .-]\d{3}"         # 0912 345 678 / 0912.345.678
    + r"|0[35789]\d[ .-]\d{3}[ .-]\d{4}"            # 091 234 5678
    + r"|0[35789]\d{2}[ .-]\d{6}"                   # 0912 345678
    + r"|(?:\+84|84)[35789]\d{8}"                   # +84912345678 / 84912345678
    + r"|\+84[ -]?[35789]\d{1,2}[ -]\d{3}[ -]\d{3,4}"  # +84 912 345 678
    + r"|02\d{9}|02\d[ .-]\d{4}[ .-]\d{4}"          # cố định 024 3974 1234
    + r")"
    + _E
)

# CCCD 12 số: 3 số mã tỉnh (001–096) + 1 số giới tính/thế kỷ + 2 số năm sinh + 6 số ngẫu nhiên.
CCCD_RE = re.compile(_B + r"0(?:0[1-9]|[1-8]\d|9[0-6])\d{9}" + _E)

_KEYWORD_SEP = r"(?:\s*(?:số|:|：|\.|#|-|là)\s*)*\s*"
KEYWORD_RE = re.compile(
    r"(?P<kw>\bCCCD\b|căn cước(?: công dân)?|\bCMND\b|\bCMTND\b|chứng minh(?: nhân dân| thư)?"
    r"|\bMST\b|mã số thuế|\bSTK\b|số tài khoản|tài khoản(?: ngân hàng)?)"
    + _KEYWORD_SEP
    + r"(?P<num>\d[\d .-]{4,24}\d)" + _E,
    re.IGNORECASE,
)

NAME_RE = re.compile(
    r"(?P<kw>(?:Họ[ \t]+và[ \t]+tên|Họ[ \t]+tên)[ \t]*(?:người[ \t]+\S+[ \t]*)?[:：][ \t]*)"
    r"(?P<name>[^\W\d_][\w]*(?:[ \t]+[^\W\d_][\w]*){1,5})"     # chỉ trong 1 dòng
)

# Header cột bảng gợi ý cả cột là PII (so khớp không dấu hoa thường)
_COLUMN_HINTS: tuple[tuple[str, EntityType], ...] = (
    ("email", "email"),
    ("thư điện tử", "email"),
    ("số điện thoại", "phone"),
    ("điện thoại", "phone"),
    ("sđt", "phone"),
    ("cccd", "cccd"),
    ("căn cước", "cccd"),
    ("cmnd", "cmnd"),
    ("chứng minh", "cmnd"),
    ("mã số thuế", "mst"),
    ("mst", "mst"),
    ("số tài khoản", "bank"),
    ("stk", "bank"),
    ("họ và tên", "name"),
    ("họ tên", "name"),
    ("người nộp", "name"),
    ("người khai", "name"),
)


def _keyword_type(keyword: str) -> EntityType:
    k = keyword.casefold()
    if "cccd" in k or "căn cước" in k:
        return "cccd"
    if "cmnd" in k or "cmtnd" in k or "chứng minh" in k:
        return "cmnd"
    if "mst" in k or "thuế" in k:
        return "mst"
    return "bank"


def _valid_for(kind: EntityType, digits: str) -> bool:
    n = len(digits)
    if kind == "cccd":
        return n == 12
    if kind == "cmnd":
        return n in (9, 12)
    if kind == "mst":
        return n in (10, 13)
    return 6 <= n <= 19   # bank


@dataclass(frozen=True)
class SafePIIFinding:
    """Chứng cứ an toàn: loại, thứ tự placeholder, vị trí (không có giá trị gốc)."""

    code: str
    entity_type: EntityType
    occurrence: int
    location: str | None = None


@dataclass(frozen=True)
class MaskedText:
    masked_text: str
    safe_findings: tuple[SafePIIFinding, ...]


QUERY_PREFIX = "USER_"
"""Placeholder của câu hỏi người dùng: [USER_PHONE_1]. Khác hẳn placeholder trong kho tài liệu
([PHONE_1] che lúc ingest), để bước mở che câu trả lời không bao giờ thay nhầm placeholder của kho."""


@dataclass
class MaskState:
    """Bộ đếm placeholder + bảng tra hai chiều cho một tài liệu hoặc một phiên hỏi đáp.

    Chỉ nằm trong RAM: không ghi đĩa, không log. Các trường chứa giá trị gốc có ``repr=False``
    để ``repr(state)`` (vd. trong log/traceback/AskTrace) không làm lộ PII.
    """

    prefix: str = ""
    _seen: dict[tuple[EntityType, str], int] = field(default_factory=dict, repr=False)
    _count: Counter = field(default_factory=Counter, repr=False)
    known: dict[str, str] = field(default_factory=dict, repr=False)      # giá trị gốc -> placeholder
    _raw: dict[str, str] = field(default_factory=dict, repr=False)       # placeholder -> giá trị gốc

    def placeholder(self, kind: EntityType, value: str) -> tuple[str, int]:
        key = (kind, re.sub(r"\s+", "", value).casefold())
        if key not in self._seen:
            self._count[kind] += 1
            self._seen[key] = self._count[kind]
        n = self._seen[key]
        token = f"[{self.prefix}{kind.upper()}_{n}]"
        self._raw.setdefault(token, value.strip())          # lần đầu gặp: giữ đúng cách viết gốc
        if len(value.strip()) >= 4:
            self.known[value.strip()] = token
        return token, n

    def unmask(self, text: str) -> str:
        """Thay placeholder CỦA STATE NÀY về giá trị gốc (dùng cho câu trả lời hiển thị cho người hỏi).

        Chấp nhận LLM viết lệch nhẹ: thêm khoảng trắng trong ngoặc, đổi hoa thường. Placeholder
        không thuộc state (vd. [PHONE_1] của kho tài liệu) được giữ nguyên.
        """
        if not self._raw:
            return text
        by_key = {token[1:-1].upper(): raw for token, raw in self._raw.items()}
        pattern = re.compile(r"\[\s*(" + "|".join(re.escape(k) for k in by_key) + r")\s*\]", re.IGNORECASE)
        return pattern.sub(lambda m: by_key[m.group(1).upper()], text)

    @property
    def counts(self) -> dict[str, int]:
        """Số giá trị PII khác nhau theo loại (không có giá trị gốc)."""
        return dict(self._count)

    def mask_known(self, text: str) -> tuple[str, int]:
        """Thay mọi giá trị PII đã gặp ở chỗ khác trong tài liệu (vd. ô bảng có header 'Mã số thuế'
        nhưng cũng xuất hiện trong thân văn bản không có ngữ cảnh). Trả (text, số lần thay)."""
        replaced = 0
        for raw in sorted(self.known, key=len, reverse=True):
            pattern = re.compile(r"(?<![\w])" + re.escape(raw) + r"(?![\w])")
            text, n = pattern.subn(self.known[raw], text)
            replaced += n
        return text, replaced


_WORD_RE = re.compile(r"[^\W\d_]\w*")


def _name_end(text: str, start: int, end: int) -> int | None:
    """Tên người Việt viết hoa chữ cái đầu mỗi từ: chỉ giữ các từ viết hoa liên tiếp từ đầu.

    'Nguyễn Minh An sinh năm' -> dừng trước 'sinh'. Cần ít nhất 2 từ viết hoa, nếu không thì
    không coi là tên (vd. 'Họ và tên: chưa khai báo').
    """
    last, words = None, 0
    for w in _WORD_RE.finditer(text, start, end):
        if not w.group()[0].isupper():
            break
        last, words = w.end(), words + 1
    return last if words >= 2 else None


def _spans(text: str) -> list[tuple[int, int, EntityType]]:
    spans: list[tuple[int, int, EntityType]] = []
    spans.extend((m.start(), m.end(), "email") for m in EMAIL_RE.finditer(text))
    for m in KEYWORD_RE.finditer(text):
        kind = _keyword_type(m.group("kw"))
        digits = re.sub(r"\D", "", m.group("num"))
        if _valid_for(kind, digits):
            spans.append((m.start("num"), m.end("num"), kind))
    for m in NAME_RE.finditer(text):
        end = _name_end(text, m.start("name"), m.end("name"))
        if end is not None:
            spans.append((m.start("name"), end, "name"))
    spans.extend((m.start(), m.end(), "cccd") for m in CCCD_RE.finditer(text))
    spans.extend((m.start(), m.end(), "phone") for m in PHONE_RE.finditer(text))
    # ưu tiên span bắt đầu sớm hơn; cùng điểm bắt đầu thì span dài hơn / có từ khoá (đứng trước)
    order = {"email": 0, "name": 1, "cccd": 2, "cmnd": 2, "mst": 2, "bank": 2, "phone": 3}
    spans.sort(key=lambda s: (s[0], -(s[1] - s[0]), order[s[2]]))
    return spans


def mask_text(text: str, *, state: MaskState | None = None, location: str | None = None) -> MaskedText:
    """Mask mọi PII nhận ra trong ``text``. Truyền chung ``state`` để đánh số ổn định cả tài liệu."""
    state = state or MaskState()
    findings: list[SafePIIFinding] = []
    pieces: list[str] = []
    cursor = 0
    for start, end, kind in _spans(text):
        if start < cursor:          # đã bị span khác bao trùm
            continue
        token, n = state.placeholder(kind, text[start:end])
        pieces.extend((text[cursor:start], token))
        findings.append(SafePIIFinding("pii.detected", kind, n, location))
        cursor = end
    pieces.append(text[cursor:])
    return MaskedText("".join(pieces), tuple(findings))


def column_pii_type(header: str) -> EntityType | None:
    """Loại PII mà header cột gợi ý, vd. 'Số điện thoại' -> 'phone'."""
    h = " ".join(header.casefold().split())
    for hint, kind in _COLUMN_HINTS:
        if hint in h:
            return kind
    return None


def mask_cells(
    cells: tuple[tuple[str, ...], ...],
    *,
    column_types: dict[int, EntityType] | None = None,
    state: MaskState | None = None,
    location_prefix: str = "",
) -> tuple[tuple[tuple[str, ...], ...], tuple[SafePIIFinding, ...]]:
    """Mask toàn bộ cell. ``column_types`` (từ header) mask nguyên cell dù regex không bắt được."""
    state = state or MaskState()
    column_types = column_types or {}
    findings: list[SafePIIFinding] = []
    masked_rows: list[tuple[str, ...]] = []
    for r, row in enumerate(cells):
        masked_row: list[str] = []
        for c, cell in enumerate(row):
            loc = f"{location_prefix}row:{r}/col:{c}"
            result = mask_text(cell, state=state, location=loc)
            kind = column_types.get(c)
            if kind and cell.strip() and not result.safe_findings:
                token, n = state.placeholder(kind, cell)
                masked_row.append(token)
                findings.append(SafePIIFinding("pii.detected", kind, n, loc))
                continue
            masked_row.append(result.masked_text)
            findings.extend(result.safe_findings)
        masked_rows.append(tuple(masked_row))
    return tuple(masked_rows), tuple(findings)


def count_by_type(findings: Iterable[SafePIIFinding]) -> dict[str, int]:
    """Số lần phát hiện theo loại — đưa vào IngestReport."""
    return dict(Counter(f.entity_type for f in findings))


__all__ = [
    "QUERY_PREFIX",
    "MaskState",
    "MaskedText",
    "SafePIIFinding",
    "column_pii_type",
    "count_by_type",
    "mask_cells",
    "mask_text",
]
