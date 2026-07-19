"""Shared internal validation for experiment domain contracts."""

from datetime import datetime, timedelta

from ditto_analysis.errors import ExperimentSpecError


def require_utc_datetime(value: object, field_name: str) -> datetime:
    """Return an aware UTC datetime or raise a stable typed contract error."""
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() != timedelta(0)
    ):
        raise ExperimentSpecError(
            f"{field_name} must be an aware UTC datetime",
            details={
                "reason_code": "datetime_not_utc",
                "field": field_name,
            },
        )
    return value
