"""Kiểm tra số liệu bảng và ngày tháng -> QualityIssue — W02-02h.

    validate_table(table, config)        kiểu cột, locale số, đơn vị, kỳ, quy tắc tổng
    extract_facts(table, config)         NumericFact theo (metric, cột giá trị, kỳ, dimensions)
    detect_conflicts(new, existing)      cùng ngữ cảnh mà khác giá trị -> numeric.conflict
    validate_dates(...)                  published_at / effective_from / effective_to hợp lệ

Nhất quán số học KHÔNG chứng minh nguồn đúng: tổng khớp chỉ có nghĩa "không thấy lỗi tổng",
không ai đặt ``verified=True``. Conflict chỉ là tín hiệu để review, không tự chọn bản đúng.

Chạy trên bảng ĐÃ mask PII; cột có header PII bị bỏ qua, nên ``detail`` không chứa PII.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date

from rag.ingest.tables import ParsedTable
from rag.quality.issues import (
    DATE_INVALID,
    DATE_RANGE_INVALID,
    NUMERIC_CONFLICT,
    NUMERIC_INVALID_LOCALE,
    NUMERIC_SUM_MISMATCH,
    TABLE_INVALID_PERIOD,
    TABLE_MISSING_PERIOD,
    TABLE_MISSING_UNIT,
    TABLE_TYPE_MISMATCH,
    QualityIssue,
)
from rag.quality.numeric import (
    CSV_MACHINE,
    NumericFactDraft,
    NumericNormalizationConfig,
    compare,
    normalize_unit,
    parse_decimal,
    sum_matches,
)
from rag.quality.pii import column_pii_type

DETECTOR = "validate.v1"

_UNIT_HEADERS = ("đơn vị",)
_PERIOD_HEADERS = ("kỳ", "quý", "tháng", "period")
_NOTE_HEADERS = ("ghi chú", "chú thích")
# Header gợi ý cột là số tiền/đại lượng cần đơn vị (khác với cột đếm như "Số hồ sơ")
_AMOUNT_HINTS = ("mức", "giá trị", "số tiền", "khung", "phí", "lệ phí", "khoản thu", "kinh phí",
                 "ngân sách", "áp dụng", "thành tiền", "đơn giá")
_TOTAL_RE = re.compile(r"^\s*(tổng|cộng)\b", re.IGNORECASE)
_PLACEHOLDER_RE = re.compile(r"^\[[A-Z]+_\d+\]$")
_EMPTY_VALUES = {"", "-", "–", "—"}

_ROMAN = {"I": 1, "II": 2, "III": 3, "IV": 4}
_PERIOD_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"^(?P<y>\d{4})-Q(?P<q>\d)$", re.I), "quarter"),
    (re.compile(r"^(?P<y>\d{4})-(?P<m>\d{1,2})$"), "month"),
    (re.compile(r"^(?P<y>\d{4})$"), "year"),
    (re.compile(r"^quý\s+(?P<q>[IV]+|\d)\s*[/-]\s*(?P<y>\d{4})$", re.I), "quarter"),
    (re.compile(r"^tháng\s+(?P<m>\d{1,2})\s*[/-]\s*(?P<y>\d{4})$", re.I), "month"),
    (re.compile(r"^năm\s+(?P<y>\d{4})$", re.I), "year"),
    (re.compile(r"^(?P<m>\d{1,2})/(?P<y>\d{4})$"), "month"),
)
_PERIOD_IN_TEXT = re.compile(r"(?:kỳ|quý|tháng|năm)\s*[:\s]*(\d{4}(?:-Q\d|-\d{1,2})?|[IV]+/\d{4}|\d{1,2}/\d{4})", re.I)


@dataclass(frozen=True)
class TableFact:
    """NumericFactDraft + vị trí trong bảng (để ghi location của issue)."""

    fact: NumericFactDraft
    location: str
    is_total: bool = False


# ---------------------------------------------------------------------------
# Kỳ báo cáo
# ---------------------------------------------------------------------------


def normalize_period(raw: str | None) -> str | None:
    """'2026-Q1' / 'Quý I/2026' -> '2026-Q1'; '2026-01' / 'tháng 1/2026' -> '2026-01'; sai -> None."""
    if raw is None:
        return None
    text = " ".join(raw.split())
    for pattern, kind in _PERIOD_PATTERNS:
        m = pattern.match(text)
        if not m:
            continue
        year = int(m.group("y"))
        if not 1900 <= year <= 2100:
            return None
        if kind == "year":
            return f"{year}"
        if kind == "month":
            month = int(m.group("m"))
            return f"{year}-{month:02d}" if 1 <= month <= 12 else None
        q_raw = m.group("q").upper()
        quarter = _ROMAN.get(q_raw) or (int(q_raw) if q_raw.isdigit() else 0)
        return f"{year}-Q{quarter}" if 1 <= quarter <= 4 else None
    return None


def _period_contains(outer: str, inner: str) -> bool:
    """Kỳ ``inner`` có nằm trong kỳ ``outer`` không (năm ⊇ quý ⊇ tháng)."""
    if outer == inner:
        return True
    if inner.startswith(outer + "-") and len(outer) == 4:
        return True
    if "-Q" in outer and len(inner) == 7 and "-Q" not in inner:
        year, q = outer.split("-Q")
        month = int(inner[5:])
        return inner[:4] == year and (month - 1) // 3 + 1 == int(q)
    return False


def table_level_period(table: ParsedTable) -> str | None:
    """Kỳ khai báo ở caption / ghi chú / tên sheet, vd. 'Kỳ 2026-Q1'."""
    texts = [table.caption or "", table.sheet or ""]
    texts += [" ".join(c for c in note if c.strip()) for note in table.notes]
    for text in texts:
        for m in _PERIOD_IN_TEXT.finditer(text):
            candidate = m.group(1)
            if "/" in candidate and candidate.split("/")[0] in _ROMAN:
                candidate = f"Quý {candidate}"
            period = normalize_period(candidate)
            if period:
                return period
    return None


# ---------------------------------------------------------------------------
# Phân loại cột
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Columns:
    metric: int
    unit: int | None
    period: int | None
    values: tuple[int, ...]
    dimensions: tuple[int, ...]
    labels: tuple[str, ...]


def _has_digit(text: str) -> bool:
    return any(ch.isdigit() for ch in text)


def _classify(table: ParsedTable) -> _Columns:
    labels = table.column_labels()
    lowered = [label.casefold() for label in labels]

    def last_level(i: int) -> str:
        return lowered[i].rsplit(" / ", 1)[-1]

    unit = next((i for i in range(len(labels)) if any(h in last_level(i) for h in _UNIT_HEADERS)), None)
    period = next((i for i in range(len(labels)) if any(last_level(i).startswith(h) for h in _PERIOD_HEADERS)), None)
    notes = {i for i in range(len(labels)) if any(h in last_level(i) for h in _NOTE_HEADERS)}
    pii = {i for i, label in enumerate(labels) if column_pii_type(label)}
    skip = {0, unit, period, *notes, *pii}
    values: list[int] = []
    dims: list[int] = []
    for i in range(1, len(labels)):
        if i in skip:
            continue
        cells = [r[i].strip() for r in table.rows if i < len(r) and r[i].strip() not in _EMPTY_VALUES]
        cells = [c for c in cells if not _PLACEHOLDER_RE.match(c)]
        amount_header = any(h in last_level(i) for h in _AMOUNT_HINTS)
        if cells and all(_has_digit(c) for c in cells) or (amount_header and cells):
            values.append(i)
        else:
            dims.append(i)
    return _Columns(0, unit, period, tuple(values), tuple(dims), labels)


def _unit_from_label(label: str) -> str | None:
    """Đơn vị trong nhãn cột, ở BẤT KỲ tầng header nào: 'Mức thu tối đa (nghìn đồng) / Mầm non'
    -> 'nghìn đồng'; tầng gần cột nhất được ưu tiên."""
    for part in reversed(label.split(" / ")):
        for m in reversed(list(re.finditer(r"\(([^)]+)\)", part))):
            if normalize_unit(m.group(1)) is not None:
                return m.group(1)
        if normalize_unit(part) is not None:
            return part
    return None


# ---------------------------------------------------------------------------
# Facts + kiểm tra bảng
# ---------------------------------------------------------------------------


def extract_facts(table: ParsedTable) -> list[TableFact]:
    cols = _classify(table)
    level_period = table_level_period(table)
    facts: list[TableFact] = []
    for r, row in enumerate(table.rows):
        def cell(i: int | None) -> str:
            return row[i].strip() if i is not None and i < len(row) else ""

        metric = cell(cols.metric) or None
        period_raw = cell(cols.period) if cols.period is not None else None
        period = normalize_period(period_raw) if period_raw else level_period
        dims = tuple((cols.labels[i], cell(i)) for i in cols.dimensions if cell(i))
        for v in cols.values:
            raw = cell(v)
            if raw in _EMPTY_VALUES or _PLACEHOLDER_RE.match(raw):
                continue
            unit = cell(cols.unit) or _unit_from_label(cols.labels[v]) or table.unit
            facts.append(TableFact(
                NumericFactDraft(raw, f"{metric} :: {cols.labels[v]}" if metric else None,
                                 unit or None, period, dims),
                location=f"{table.table_id}/row:{r}/col:{cols.labels[v]}",
                is_total=bool(metric and _TOTAL_RE.match(metric)),
            ))
    return facts


def validate_table(table: ParsedTable, config: NumericNormalizationConfig = CSV_MACHINE) -> list[QualityIssue]:
    """Issue theo thứ tự: kiểu/locale từng ô, đơn vị, kỳ, quy tắc tổng."""
    cols = _classify(table)
    issues: list[QualityIssue] = []

    def issue(code: str, severity: str, location: str, detail: str) -> None:
        issues.append(QualityIssue(code, severity, location, detail, DETECTOR))  # type: ignore[arg-type]

    # 1. Kiểu + locale
    for v in cols.values:
        for r, row in enumerate(table.rows):
            raw = row[v].strip() if v < len(row) else ""
            if raw in _EMPTY_VALUES or _PLACEHOLDER_RE.match(raw):
                continue
            loc = f"{table.table_id}/row:{r}/col:{cols.labels[v]}"
            if not _has_digit(raw):
                issue(TABLE_TYPE_MISMATCH, "warning", loc, f"Cột số chứa giá trị không phải số: {raw!r}")
            elif parse_decimal(raw, config=config) is None:
                issue(NUMERIC_INVALID_LOCALE, "warning", loc,
                      f"Không đọc được số {raw!r} theo locale {config.locale!r}; không đoán dấu thập phân")

    # 2. Đơn vị: cột "Đơn vị" có ô trống, hoặc cột tiền không có đơn vị ở đâu cả
    # chỉ xét tầng header gần cột nhất (như _classify): tầng trên "Các khoản thu, mức thu ..." phủ cả cột "TT"
    amount_cols = [v for v in cols.values
                   if any(h in cols.labels[v].casefold().rsplit(" / ", 1)[-1] for h in _AMOUNT_HINTS)]
    if cols.unit is not None:
        empty = [r for r, row in enumerate(table.rows) if not row[cols.unit].strip()]
        if empty and cols.values:
            issue(TABLE_MISSING_UNIT, "warning", f"{table.table_id}/col:{cols.labels[cols.unit]}",
                  f"{len(empty)}/{len(table.rows)} hàng thiếu đơn vị")
    elif amount_cols and not table.unit and not all(_unit_from_label(cols.labels[v]) for v in amount_cols):
        issue(TABLE_MISSING_UNIT, "warning", table.table_id, "Cột số tiền không có đơn vị (header/caption/cột)")

    # 3. Kỳ: thiếu, sai định dạng, hoặc khác kỳ khai báo ở tiêu đề/ghi chú
    level_period = table_level_period(table)
    if cols.period is not None:
        empty = 0
        for r, row in enumerate(table.rows):
            raw = row[cols.period].strip()
            if not raw:
                empty += 1
                continue
            loc = f"{table.table_id}/row:{r}/col:{cols.labels[cols.period]}"
            period = normalize_period(raw)
            if period is None:
                issue(TABLE_INVALID_PERIOD, "warning", loc, f"Kỳ không hợp lệ: {raw!r}")
            elif level_period and not _period_contains(level_period, period):
                issue(TABLE_INVALID_PERIOD, "warning", loc, f"Kỳ {period} khác kỳ tiêu đề {level_period}")
        if empty and not level_period:
            issue(TABLE_MISSING_PERIOD, "warning", f"{table.table_id}/col:{cols.labels[cols.period]}",
                  f"{empty}/{len(table.rows)} hàng thiếu kỳ")
    # Không có cột Kỳ: KHÔNG báo. Bảng mức thu/mức phạt trong văn bản luật áp dụng theo ngày hiệu lực
    # của văn bản (phần version quản lý), không theo kỳ báo cáo. (Sửa sau báo nhầm trên dev w02-24.)

    # 4. Quy tắc tổng: hàng "Tổng/Cộng" = tổng các hàng phía trên (từ hàng tổng trước đó)
    facts = extract_facts(table)
    by_col: dict[str, list[TableFact]] = {}
    for f in facts:
        by_col.setdefault(f.location.rsplit("/col:", 1)[-1], []).append(f)
    for label, col_facts in by_col.items():
        parts: list[TableFact] = []
        for f in col_facts:
            if not f.is_total:
                parts.append(f)
                continue
            if parts:
                # so trong cùng metric giả định: thay metric của phần tử bằng metric của hàng tổng
                aligned = tuple(NumericFactDraft(p.fact.raw_value, f.fact.metric, p.fact.unit, p.fact.period,
                                                 p.fact.dimensions) for p in parts)
                result = sum_matches(aligned, f.fact, config=config)
                if result.relation == "different":
                    issue(NUMERIC_SUM_MISMATCH, "error", f.location,
                          f"Tổng ghi {result.right_value} khác tổng tính {result.left_value} (VND); "
                          "chỉ là kiểm tra số học, không xác minh nguồn")
            parts = []
    return issues


# ---------------------------------------------------------------------------
# Conflict giữa tài liệu
# ---------------------------------------------------------------------------


def detect_conflicts(
    new: Iterable[TableFact],
    existing: Iterable[tuple[str, TableFact]],
    *,
    config: NumericNormalizationConfig = CSV_MACHINE,
) -> list[QualityIssue]:
    """So fact mới với fact đã có (``(nguồn, fact)``). Chỉ ``different`` mới là conflict;
    ``incomparable`` (khác kỳ/đơn vị/dimension) và ``invalid`` không tạo conflict."""
    index: dict[tuple, list[tuple[str, TableFact]]] = {}
    for source, fact in existing:
        key = (fact.fact.metric, fact.fact.period, fact.fact.dimensions)
        index.setdefault(key, []).append((source, fact))
    issues: list[QualityIssue] = []
    for fact in new:
        if fact.fact.metric is None:
            continue
        for source, other in index.get((fact.fact.metric, fact.fact.period, fact.fact.dimensions), []):
            result = compare(fact.fact, other.fact, config=config)
            if result.relation == "different":
                issues.append(QualityIssue(
                    NUMERIC_CONFLICT, "error", fact.location,
                    f"Khác giá trị với {source} ({result.left_value} vs {result.right_value} VND) "
                    "cùng metric/kỳ/dimension; cần review, không tự chọn bản đúng",
                    DETECTOR,
                ))
    return issues


# ---------------------------------------------------------------------------
# Ngày tháng
# ---------------------------------------------------------------------------


def _parse_date(value: str | date | None) -> date | None | str:
    if value is None or isinstance(value, date):
        return value
    try:
        return date.fromisoformat(value)
    except ValueError:
        return "invalid"


def validate_dates(
    *,
    published_at: str | date | None = None,
    effective_from: str | date | None = None,
    effective_to: str | date | None = None,
    location: str = "document",
) -> list[QualityIssue]:
    """Ngày phải đúng ISO; effective_from < effective_to (khoảng nửa mở); published_at ≤ effective_from."""
    issues: list[QualityIssue] = []
    parsed: dict[str, date | None] = {}
    for name, value in (("published_at", published_at), ("effective_from", effective_from),
                        ("effective_to", effective_to)):
        result = _parse_date(value)
        if result == "invalid":
            issues.append(QualityIssue(DATE_INVALID, "error", f"{location}/{name}",
                                       f"{name} không phải ngày ISO: {value!r}", DETECTOR))
            parsed[name] = None
        else:
            parsed[name] = result  # type: ignore[assignment]
    start, end, pub = parsed["effective_from"], parsed["effective_to"], parsed["published_at"]
    if start and end and not start < end:
        issues.append(QualityIssue(DATE_RANGE_INVALID, "error", f"{location}/effective",
                                   f"effective_from {start} phải trước effective_to {end}", DETECTOR))
    if pub and start and pub > start:
        issues.append(QualityIssue(DATE_RANGE_INVALID, "warning", f"{location}/published_at",
                                   f"published_at {pub} sau effective_from {start} (hồi tố?) — cần review",
                                   DETECTOR))
    return issues


def validate_tables(tables: Sequence[ParsedTable], config: NumericNormalizationConfig = CSV_MACHINE) -> list[QualityIssue]:
    return [issue for table in tables for issue in validate_table(table, config)]


__all__ = [
    "DETECTOR",
    "TableFact",
    "detect_conflicts",
    "extract_facts",
    "normalize_period",
    "table_level_period",
    "validate_dates",
    "validate_table",
    "validate_tables",
]
