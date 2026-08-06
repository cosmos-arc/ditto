"""Strict scalar and window decoders for persisted preflight evidence."""

from __future__ import annotations

from datetime import date
from typing import cast

from ditto_application.processes.experiments._process_error import (
    experiment_process_error,
)
from ditto_application.research_validation_protocol import CalendarMonth

__all__ = [
    "decode_boolean",
    "decode_date",
    "decode_integer",
    "decode_list",
    "decode_mapping",
    "decode_month",
    "decode_string",
    "decode_window_dates",
]

_CALENDAR_MONTH_PART_COUNT = 2


def decode_mapping(value: object, field_name: str) -> dict[str, object]:
    if type(value) is not dict:
        raise experiment_process_error(f"{field_name} must be an object")
    return cast("dict[str, object]", value)


def decode_list(value: object, field_name: str) -> list[object]:
    if type(value) is not list:
        raise experiment_process_error(f"{field_name} must be a list")
    return cast("list[object]", value)


def decode_string(value: object, field_name: str) -> str:
    if type(value) is not str:
        raise experiment_process_error(f"{field_name} must be a string")
    return value


def decode_integer(value: object, field_name: str) -> int:
    if type(value) is not int:
        raise experiment_process_error(f"{field_name} must be an integer")
    return value


def decode_boolean(value: object, field_name: str) -> bool:
    if type(value) is not bool:
        raise experiment_process_error(f"{field_name} must be a boolean")
    return value


def decode_date(value: object, field_name: str) -> date:
    text = decode_string(value, field_name)
    parsed = date.fromisoformat(text)
    if parsed.isoformat() != text:
        raise experiment_process_error(f"{field_name} is not a canonical date")
    return parsed


def decode_month(value: object, field_name: str) -> CalendarMonth:
    text = decode_string(value, field_name)
    parts = text.split("-")
    if len(parts) != _CALENDAR_MONTH_PART_COUNT:
        raise experiment_process_error(f"{field_name} is not a calendar month")
    month = CalendarMonth(int(parts[0]), int(parts[1]))
    if str(month) != text:
        raise experiment_process_error(
            f"{field_name} is not a canonical calendar month"
        )
    return month


def decode_window_dates(value: object, field_name: str) -> tuple[date, date]:
    payload = decode_mapping(value, field_name)
    if set(payload) != {"start", "end"}:
        raise experiment_process_error(f"{field_name} has an invalid shape")
    return (
        decode_date(payload.get("start"), f"{field_name}.start"),
        decode_date(payload.get("end"), f"{field_name}.end"),
    )
