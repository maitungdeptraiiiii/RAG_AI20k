"""Shared document/content data models; independent of OCR and index backends."""

from __future__ import annotations

import json, math, re, unicodedata
from dataclasses import dataclass, field, fields, is_dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import PurePosixPath, PureWindowsPath
from typing import Literal, Mapping, TypeAlias


JSONValue: TypeAlias = None | bool | int | float | str | list["JSONValue"] | dict[str, "JSONValue"]


Approval = Literal["pending", "approved", "rejected"]


QualityStatus = Literal["pending", "passed", "needs_review", "rejected"]


ChangeKind = Literal["initial", "full", "partial"]


BlockKind = Literal["heading", "paragraph", "table", "image", "list", "flow"]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def nonempty(*values: str) -> None:
    require(all(isinstance(v, str) and bool(v.strip()) for v in values), "Identifiers must not be empty")


def checksum_value(value: str) -> None:
    require(bool(re.fullmatch(r"[0-9a-f]{64}", value)), "Expected lowercase SHA-256 hex digest")


def aware(value: datetime) -> None:
    require(value.tzinfo is not None and value.utcoffset() is not None, "Timestamp must include timezone")


def artifact_path(value: str) -> None:
    nonempty(value)
    paths = (PurePosixPath(value), PureWindowsPath(value))
    require(not any(p.is_absolute() or ".." in p.parts for p in paths)
            and not PureWindowsPath(value).drive and not value.startswith(("/", "\\")),
            "Artifact path must be relative to DATA_DIR without parent traversal")


def to_json_value(value: object) -> JSONValue:
    """JSON-safe serialization; not a PII scrubber. Decimal never goes via float."""
    if is_dataclass(value) and not isinstance(value, type):
        return {f.name: to_json_value(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, datetime):
        aware(value)
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        require(value.is_finite(), "Decimal must be finite")
        return format(value, "f")
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        require(math.isfinite(value), "Float must be finite")
        return value
    if isinstance(value, Mapping):
        result: dict[str, JSONValue] = {}
        for key, item in value.items():
            require(isinstance(key, str), "JSON keys must be strings")
            normalized = unicodedata.normalize("NFC", key)
            require(normalized not in result, "Duplicate key after Unicode normalization")
            result[normalized] = to_json_value(item)
        return result
    if isinstance(value, (tuple, list)):
        return [to_json_value(item) for item in value]
    raise TypeError(f"Unsupported serialization type: {type(value).__name__}")


def canonical_json(value: object) -> str:
    return json.dumps(to_json_value(value), ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


@dataclass(frozen=True, kw_only=True)
class Record:
    schema_version: Literal["w02.v1"] = field(default="w02.v1", init=False)

    def to_dict(self) -> dict[str, JSONValue]:
        result = to_json_value(self)
        assert isinstance(result, dict)
        return result


__all__ = [
    'JSONValue',
    'Approval',
    'QualityStatus',
    'ChangeKind',
    'BlockKind',
    'require',
    'nonempty',
    'checksum_value',
    'aware',
    'artifact_path',
    'to_json_value',
    'canonical_json',
    'Record',
]
