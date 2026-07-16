"""Authoritative validation for immutable execution fill facts."""

from __future__ import annotations

from datetime import date
from math import isfinite

from ditto_execution.errors import FillProcessingError
from ditto_execution.models import FillAdjustmentRecord, FillRecord

__all__ = ["validate_fill_adjustment_record", "validate_fill_record"]

_SQLITE_INTEGER_MAX = 2**63 - 1
_SQLITE_INTEGER_MIN = -(2**63)


def _is_non_blank(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_string(value: object) -> bool:
    return isinstance(value, str)


def _is_direction(value: object) -> bool:
    return isinstance(value, str) and value in ("buy", "sell")


def _is_positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _is_finite_number(value: object) -> bool:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return False
    if isinstance(value, int) and not (
        _SQLITE_INTEGER_MIN <= value <= _SQLITE_INTEGER_MAX
    ):
        return False
    if isinstance(value, int) and int(float(value)) != value:
        return False
    try:
        return isfinite(value)
    except OverflowError:
        return False


def _require_calendar_date(value: str) -> None:
    try:
        parsed = date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise FillProcessingError("trade_date must be a valid YYYY-MM-DD date") from exc
    if parsed.isoformat() != value:
        raise FillProcessingError("trade_date must be a valid YYYY-MM-DD date")


def _validate_fill_identity(record: FillRecord) -> None:
    if not _is_non_blank(record.fill_id):
        raise FillProcessingError("fill_id is required")
    if not _is_non_blank(record.intent_id):
        raise FillProcessingError("intent_id is required")
    if not _is_non_blank(record.strategy_id):
        raise FillProcessingError("strategy_id is required")
    _require_calendar_date(record.trade_date)
    if not _is_positive_int(record.instrument_id):
        raise FillProcessingError("instrument_id must be positive")
    if record.instrument_id > _SQLITE_INTEGER_MAX:
        raise FillProcessingError("instrument_id exceeds SQLite INTEGER range")
    if not _is_direction(record.direction):
        raise FillProcessingError("direction must be 'buy' or 'sell'")


def _validate_fill_economics(record: FillRecord) -> None:
    if not _is_positive_int(record.quantity):
        raise FillProcessingError("quantity must be positive")
    if record.quantity > _SQLITE_INTEGER_MAX:
        raise FillProcessingError("quantity exceeds SQLite INTEGER range")
    if not _is_finite_number(record.fill_price) or record.fill_price <= 0.0:
        raise FillProcessingError("fill_price must be positive and finite")
    if not _is_finite_number(record.fee) or record.fee < 0.0:
        raise FillProcessingError("fee must be non-negative and finite")
    if not _is_finite_number(record.slippage):
        raise FillProcessingError("slippage must be finite")


def _validate_fill_metadata(record: FillRecord) -> None:
    if not _is_string(record.notes):
        raise FillProcessingError("notes must be a string")
    if not _is_string(record.settlement_date):
        raise FillProcessingError("settlement_date must be a string")
    if record.settlement_date:
        try:
            _require_calendar_date(record.settlement_date)
        except FillProcessingError as exc:
            raise FillProcessingError(
                "settlement_date must be empty or a valid YYYY-MM-DD date"
            ) from exc
    if not _is_string(record.created_at):
        raise FillProcessingError("created_at must be a string")


def validate_fill_record(record: FillRecord) -> None:
    """Fail closed before an immutable fill enters the authoritative ledger."""
    _validate_fill_identity(record)
    _validate_fill_economics(record)
    _validate_fill_metadata(record)


def validate_fill_adjustment_record(record: FillAdjustmentRecord) -> None:
    """Fail closed before an immutable fill-adjustment fact enters the ledger."""
    if not _is_non_blank(record.adjustment_id):
        raise FillProcessingError("adjustment_id is required")
    if not _is_non_blank(record.fill_id):
        raise FillProcessingError("fill_id is required")
    if not _is_non_blank(record.reason):
        raise FillProcessingError("Fill adjustment reason is required")
    if not _is_non_blank(record.created_at):
        raise FillProcessingError("Fill adjustment created_at is required")
