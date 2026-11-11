"""Kiểm tra chất lượng text trích xuất — "không index rác một cách im lặng" (kế hoạch tuần 1, Task 2).

    check_text(text) -> list[PageIssue]
        empty      < 20 ký tự (trang scan, không có text layer)
        bad_chars  font cũ TCVN3 (ABC) / VNI vỡ dấu, ký tự thay thế U+FFFD, ký tự điều khiển

Vì sao bắt được font cũ: trong dải Latin-1 (U+0080–U+00FF) tiếng Việt Unicode CHỈ dùng
``à á â ã è é ê ì í ò ó ô õ ù ú ý`` (và chữ hoa); các chữ có dấu khác (ạ, ề, ộ...) nằm ở U+1EA0+.
PDF/DOCX dùng font TCVN3/VNI khi đọc ra lại toàn ký tự Latin-1 "lạ":

    TCVN3:  §iÒu 5. Ph¹m vi ®iÒu chØnh. Ng­êi lao ®éng ...   (24 % chữ là ký tự lạ)
    VNI:    Ñieàu 5. Phaïm vi ñieàu chænh. Ngöôøi lao ñoäng ... (19 %)
    Unicode Điều 5. Phạm vi điều chỉnh. Người lao động ...      (0 %)

Chỉ đếm ký tự lạ DÍNH VỚI CHỮ CÁI (font cũ dùng chúng làm chữ: "®iÒu", "n¨m"); ký hiệu thật đứng riêng
hoặc cạnh số ("« trích", "© 2026", "§ 3", "25°C") không tính. Ngưỡng: ≥ 5 ký tự VÀ ≥ 3 % số chữ cái.
Đo 09/11/2026: 0/22 file và 0/3548 chunk của kho hiện có bị gắn cờ (tỉ lệ cao nhất 0,1 %).
Hạn chế: trang tiếng Đức/Pháp (ä ö ü ç ë trong từ) cũng vượt ngưỡng -> bị gắn cờ / OCR lại (chỉ tốn
thêm, không mất nội dung).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

MIN_TEXT_CHARS = 20
BAD_MIN_COUNT = 5
BAD_MIN_RATIO = 0.03

_VI_LATIN1 = frozenset("àáâãèéêìíòóôõùúýÀÁÂÃÈÉÊÌÍÒÓÔÕÙÚÝ")
_ALLOWED_CONTROL = frozenset("\n\r\t\f")
# Không có trong bảng mã TCVN3/VNI -> luôn là ký hiệu thật ("25°C", "± 2", khoảng trắng không ngắt)
_NEVER_LEGACY = frozenset("°±\xa0")

IssueKind = Literal["empty", "bad_chars"]


@dataclass(frozen=True)
class PageIssue:
    page: int | None
    kind: IssueKind
    detail: str


def _is_legacy_letter(text: str, i: int) -> bool:
    """Ký tự Latin-1 lạ ĐƯỢC DÙNG NHƯ CHỮ CÁI: dính với chữ cái bên trái hoặc phải ("®iÒu", "Ph¹m", "n¨m").
    Ký hiệu thật đứng riêng / cạnh chữ số ("« trích", "© 2026", "§ 3", "3 × 4") không tính."""
    c = text[i]
    if not ("\x80" <= c <= "\xff") or c in _VI_LATIN1 or c in _NEVER_LEGACY:
        return False
    left = text[i - 1] if i > 0 else " "
    right = text[i + 1] if i + 1 < len(text) else " "
    return left.isalpha() or right.isalpha()


def legacy_char_stats(text: str) -> dict[str, int]:
    """Đếm tín hiệu vỡ mã hoá: ký tự Latin-1 lạ dùng như chữ cái, U+FFFD, ký tự điều khiển."""
    odd = sum(1 for i in range(len(text)) if _is_legacy_letter(text, i))
    replacement = text.count("�")
    control = sum(1 for c in text if (c < " " or "\x7f" <= c <= "\x9f") and c not in _ALLOWED_CONTROL)
    letters = sum(1 for c in text if c.isalpha())
    return {"odd": odd, "replacement": replacement, "control": control, "letters": letters}


def is_bad_chars(text: str) -> tuple[bool, str]:
    s = legacy_char_stats(text)
    reasons = []
    if s["odd"] >= BAD_MIN_COUNT and s["odd"] >= BAD_MIN_RATIO * max(s["letters"], 1):
        reasons.append(f"{s['odd']}/{s['letters']} chữ là ký tự Latin-1 không thuộc tiếng Việt "
                       "(dấu hiệu font TCVN3/VNI)")
    if s["replacement"] >= 3:
        reasons.append(f"{s['replacement']} ký tự thay thế U+FFFD")
    if s["control"] >= 3:
        reasons.append(f"{s['control']} ký tự điều khiển")
    return bool(reasons), "; ".join(reasons)


def check_text(text: str, page: int | None = None) -> list[PageIssue]:
    if len(text.strip()) < MIN_TEXT_CHARS:
        return [PageIssue(page, "empty", f"{len(text.strip())} ký tự — có thể là trang scan")]
    bad, detail = is_bad_chars(text)
    return [PageIssue(page, "bad_chars", detail)] if bad else []


__all__ = ["MIN_TEXT_CHARS", "PageIssue", "check_text", "is_bad_chars", "legacy_char_stats"]
