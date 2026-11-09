"""Decode persisted week-2 dataclasses without importing runtime backends."""

from __future__ import annotations

import json
from dataclasses import fields, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from types import UnionType
from typing import Literal, TypeVar, Union, get_args, get_origin, get_type_hints


T = TypeVar("T")


def _decode(kind, value):
    origin, args = get_origin(kind), get_args(kind)
    if origin in (UnionType, Union):
        for member in args:
            try:
                return _decode(member, value)
            except (ValueError, TypeError, KeyError):
                continue
        raise ValueError("Stored field does not match its schema")
    if kind is type(None):
        if value is not None:
            raise ValueError("Expected null")
        return None
    if origin is Literal:
        if value not in args:
            raise ValueError("Invalid stored enum")
        return value
    if is_dataclass(kind):
        return from_dict(kind, value)
    if origin is tuple:
        if not isinstance(value, list):
            raise ValueError("Expected JSON array")
        if len(args) == 2 and args[1] is Ellipsis:
            return tuple(_decode(args[0], item) for item in value)
        if len(value) != len(args):
            raise ValueError("Unexpected tuple size")
        return tuple(_decode(member, item) for member, item in zip(args, value))
    if origin is dict:
        # Persisted evidence/decision payloads are JSON values, not typed records.
        from rag.models.common import to_json_value
        if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
            raise ValueError("Expected JSON object with string keys")
        return to_json_value(value)
    if kind in (datetime, date):
        return kind.fromisoformat(value)
    if kind is Decimal:
        return Decimal(value)
    if kind in (str, int, bool, float):
        if kind is float and type(value) in (int, float):
            return float(value)
        if type(value) is not kind:
            raise ValueError("Unexpected stored scalar type")
        return value
    raise ValueError(f"Unsupported persisted field type: {kind}")


def from_dict(model: type[T], value: dict) -> T:
    if not isinstance(value, dict):
        raise ValueError("Expected stored object")
    if "schema_version" in value and value["schema_version"] != "w02.v1":
        raise ValueError("Unsupported schema version")
    allowed = {f.name for f in fields(model)}
    if set(value) - allowed:
        raise ValueError("Unknown stored fields")
    hints = get_type_hints(model)
    return model(**{f.name: _decode(hints[f.name], value[f.name])
                    for f in fields(model) if f.init and f.name in value})


def from_json(model: type[T], payload: str) -> T:
    return from_dict(model, json.loads(payload))
