"""Chuẩn hoá và so sánh số liệu theo metric, đơn vị, kỳ và dimensions.

Không hàm nào ở đây đặt ``verified=True``: tổng số học khớp chỉ là một finding,
không chứng minh số liệu hay nguồn đúng.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Literal


ComparisonRelation = Literal["equal", "different", "incomparable", "invalid"]

_SCALES = {"": Decimal("1"), "nghìn": Decimal("1000"), "ngàn": Decimal("1000"),
           "triệu": Decimal("1000000"), "tỷ": Decimal("1000000000"), "tỉ": Decimal("1000000000")}
_CURRENCIES = ("vnd", "vnđ", "đồng", "đ")
UNIT_SCALES: dict[str, Decimal] = {
    f"{scale} {cur}".strip(): factor for scale, factor in _SCALES.items() for cur in _CURRENCIES
}
UNIT_SCALES.update({"trđ": Decimal("1000000"), "tr đồng": Decimal("1000000"), "nghìn đ": Decimal("1000")})
"""Đơn vị tiền -> hệ số quy về đồng (VND): đồng / nghìn / triệu / tỷ, nhiều cách viết."""


@dataclass(frozen=True)
class NumericNormalizationConfig:
    """Config tạm cho lõi; adapter sẽ map sang NumericConfig Contract v1.

    Không có default locale ngầm: caller phải chốt cách đọc dấu thập phân và
    ngăn cách nhóm trước khi parse. ``locale='und'`` chỉ chấp nhận integer.
    """

    locale: str
    decimal_separator: str | None
    group_separator: str | None
    tolerance: Decimal = Decimal("0")
    unit_conversion_version: str = "w02.unit.v1"

    def __post_init__(self) -> None:
        if not self.locale:
            raise ValueError("locale không được rỗng")
        if self.decimal_separator not in {None, ".", ","}:
            raise ValueError("decimal_separator phải là '.', ',' hoặc None")
        if self.group_separator not in {None, ".", ",", " "}:
            raise ValueError("group_separator không hợp lệ")
        if self.decimal_separator is not None and self.decimal_separator == self.group_separator:
            raise ValueError("decimal_separator và group_separator không được trùng")
        if self.tolerance < 0:
            raise ValueError("tolerance phải >= 0")


CSV_MACHINE = NumericNormalizationConfig(locale="csv-machine", decimal_separator=".", group_separator=None)
"""CSV/XLSX xuất từ máy: dấu chấm thập phân, không ngăn cách nhóm (1500000, 1.5)."""

VI_TEXT = NumericNormalizationConfig(locale="vi-VN", decimal_separator=",", group_separator=".")
"""Văn bản tiếng Việt: 1.500.000 = 1500000, 1,5 = 1.5."""


@dataclass(frozen=True)
class NumericFactDraft:
    raw_value: str
    metric: str | None
    unit: str | None
    period: str | None
    dimensions: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class NumericComparisonDraft:
    relation: ComparisonRelation
    left_value: Decimal | None
    right_value: Decimal | None
    canonical_unit: str | None
    reason: str


def parse_decimal(raw_value: str, *, config: NumericNormalizationConfig) -> Decimal | None:
    """Parse khi format rõ ràng; chuỗi mơ hồ trả None thay vì đoán âm thầm."""
    value = raw_value.strip()
    if not value:
        return None
    if config.decimal_separator is None:
        return Decimal(value) if value.lstrip("+-").isdigit() else None
    allowed = set("0123456789+-" + config.decimal_separator + (config.group_separator or ""))
    if any(char not in allowed for char in value) or value.count(config.decimal_separator) > 1:
        return None
    if config.group_separator:
        integer_part, _, fraction = value.partition(config.decimal_separator)
        if config.group_separator in fraction:      # "1,500.000" theo vi-VN: nhóm nằm sau dấu thập phân
            return None
        groups = integer_part.lstrip("+-").split(config.group_separator)
        if len(groups) > 1 and (not groups[0] or any(len(group) != 3 or not group.isdigit() for group in groups[1:])):
            return None
        value = value.replace(config.group_separator, "")
    value = value.replace(config.decimal_separator, ".")
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def normalize_unit(unit: str | None) -> Decimal | None:
    if unit is None:
        return None
    return UNIT_SCALES.get(" ".join(unit.casefold().split()))


def canonical_value(fact: NumericFactDraft, *, config: NumericNormalizationConfig) -> Decimal | None:
    value = parse_decimal(fact.raw_value, config=config)
    scale = normalize_unit(fact.unit)
    return value * scale if value is not None and scale is not None else None


def compare(left: NumericFactDraft, right: NumericFactDraft, *, config: NumericNormalizationConfig) -> NumericComparisonDraft:
    """Chỉ kết luận equal/different nếu toàn bộ context có thể so sánh."""
    left_value, right_value = canonical_value(left, config=config), canonical_value(right, config=config)
    if parse_decimal(left.raw_value, config=config) is None or parse_decimal(right.raw_value, config=config) is None:
        return NumericComparisonDraft("invalid", left_value, right_value, None, "ambiguous_or_invalid_number")
    if left.metric is None or right.metric is None or left.metric != right.metric:
        return NumericComparisonDraft("incomparable", left_value, right_value, None, "metric_mismatch_or_missing")
    if left.period is None or right.period is None or left.period != right.period:
        return NumericComparisonDraft("incomparable", left_value, right_value, None, "period_mismatch_or_missing")
    if left.dimensions != right.dimensions:
        return NumericComparisonDraft("incomparable", left_value, right_value, None, "dimension_mismatch")
    if left_value is None or right_value is None:
        return NumericComparisonDraft("incomparable", left_value, right_value, None, "unit_missing_or_unsupported")
    relation: ComparisonRelation = "equal" if abs(left_value - right_value) <= config.tolerance else "different"
    return NumericComparisonDraft(relation, left_value, right_value, "VND", "compatible_context")


def sum_matches(parts: tuple[NumericFactDraft, ...], total: NumericFactDraft, *, config: NumericNormalizationConfig) -> NumericComparisonDraft:
    """So sánh tổng trong cùng context; không xác minh nguồn hay giá trị OCR."""
    total_value = canonical_value(total, config=config)
    part_values = [canonical_value(part, config=config) for part in parts]
    if total_value is None or any(value is None for value in part_values):
        return NumericComparisonDraft("incomparable", None, total_value, None, "invalid_or_unknown_unit")
    if any(part.metric != total.metric or part.period != total.period or part.dimensions != total.dimensions for part in parts):
        return NumericComparisonDraft("incomparable", sum(part_values), total_value, None, "context_mismatch")
    computed = sum(part_values, start=Decimal("0"))
    relation: ComparisonRelation = "equal" if abs(computed - total_value) <= config.tolerance else "different"
    return NumericComparisonDraft(relation, computed, total_value, "VND", "arithmetic_only_not_verified")
