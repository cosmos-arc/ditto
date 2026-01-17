"""DQ rule definitions and check functions."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import polars as pl
from ditto_foundation import logger

from ..models import DQSeverity


@dataclass(frozen=True)
class DQRule:
    """DQ rule definition."""

    name: str
    severity: DQSeverity
    check_fn: Callable[[pl.DataFrame, dict[str, Any]], tuple[bool, int, str]]
    params: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        """Initialize params if None (required for frozen dataclass)."""
        # frozen=True requires object.__setattr__
        if self.params is None:
            object.__setattr__(self, "params", {})


# ============ 检查函数 ============
def check_pk_unique(df: pl.DataFrame, params: dict[str, Any]) -> tuple[bool, int, str]:
    """Check primary key uniqueness."""
    keys = params.get("keys", ["sid", "trade_date"])
    total_rows = len(df)
    unique_rows = df.select(keys).n_unique()

    duplicate_count = total_rows - unique_rows

    if duplicate_count > 0:
        logger.warning(
            "dq_rule_pk_duplicate",
            event="dq_check",
            rule="primary_key_unique",
            keys=keys,
            duplicate_count=duplicate_count,
        )

    return (
        duplicate_count == 0,
        duplicate_count,
        f"Found {duplicate_count} duplicate {keys}"
        if duplicate_count > 0
        else "Primary key unique",
    )


def check_sid_not_null(
    df: pl.DataFrame, params: dict[str, Any]
) -> tuple[bool, int, str]:
    """Check sid is not null."""
    null_count = df.filter(pl.col("sid").is_null()).height

    if null_count > 0:
        logger.warning(
            "dq_rule_null_sid",
            event="dq_check",
            rule="sid_not_null",
            null_count=null_count,
        )

    return (
        null_count == 0,
        null_count,
        f"Found {null_count} null sid" if null_count > 0 else "All sid not null",
    )


def check_ohlc_positive(
    df: pl.DataFrame, params: dict[str, Any]
) -> tuple[bool, int, str]:
    """Check OHLC prices are positive."""
    price_cols = ["open", "high", "low", "close"]
    bad_count = 0

    for col in price_cols:
        if col in df.columns:
            bad_count += df.filter(pl.col(col) <= 0).height

    if bad_count > 0:
        logger.warning(
            "dq_rule_non_positive_ohlc",
            event="dq_check",
            rule="ohlc_positive",
            bad_count=bad_count,
        )

    return (
        bad_count == 0,
        bad_count,
        f"Found {bad_count} non-positive OHLC prices"
        if bad_count > 0
        else "All OHLC prices positive",
    )


def check_ohlc_relationship(
    df: pl.DataFrame, params: dict[str, Any]
) -> tuple[bool, int, str]:
    """Check OHLC price relationships."""
    required_cols = ["open", "high", "low", "close"]
    if not all(col in df.columns for col in required_cols):
        return True, 0, "OHLC columns not all present"

    # high >= max(open, close) and low <= min(open, close)
    bad_count = df.filter(
        (pl.col("high") < pl.col("open"))
        | (pl.col("high") < pl.col("close"))
        | (pl.col("low") > pl.col("open"))
        | (pl.col("low") > pl.col("close"))
    ).height

    return (
        bad_count == 0,
        bad_count,
        f"Found {bad_count} OHLC relationship violations"
        if bad_count > 0
        else "OHLC relationships valid",
    )


def check_volume_amount_consistency(
    df: pl.DataFrame, params: dict[str, Any]
) -> tuple[bool, int, str]:
    """Check volume and amount consistency."""
    if not all(col in df.columns for col in ["volume", "amount"]):
        return True, 0, "Volume/amount columns not both present"

    # amount should be >= volume * low and <= volume * high
    # Simplified check: amount should be positive when volume is positive
    inconsistent = df.filter((pl.col("volume") > 0) & (pl.col("amount") <= 0)).height

    return (
        inconsistent == 0,
        inconsistent,
        f"Found {inconsistent} volume/amount inconsistencies"
        if inconsistent > 0
        else "Volume/amount consistent",
    )


def check_weight_positive(
    df: pl.DataFrame, params: dict[str, Any]
) -> tuple[bool, int, str]:
    """Check weight is non-negative."""
    if "weight" not in df.columns:
        return True, 0, "Weight column not present"

    bad_count = df.filter(pl.col("weight") < 0).height
    return (
        bad_count == 0,
        bad_count,
        f"Found {bad_count} negative weights"
        if bad_count > 0
        else "All weights non-negative",
    )


def check_required_columns(
    df: pl.DataFrame, params: dict[str, Any]
) -> tuple[bool, int, str]:
    """
    Check required columns exist.

    Args:
        df: Data to check
        params: Dict with "columns" key containing list of required column names

    Returns:
        Tuple of (passed, affected_columns, message)

    """
    required = params.get("columns", [])
    missing = [col for col in required if col not in df.columns]

    if missing:
        logger.warning(
            "dq_rule_missing_columns",
            event="dq_check",
            rule="required_columns",
            missing_columns=missing,
        )

    return (
        len(missing) == 0,
        len(missing),
        f"Missing columns: {missing}" if missing else "All required columns present",
    )


# ============ 规则配置(替代 YAML) ============
# B.5: Updated DQSeverity.FAIL -> ERROR, WARN -> WARNING
DQ_RULES: dict[str, list[DQRule]] = {
    "stock_daily": [  # 股票日线数据（主要命名）
        DQRule(
            "primary_key_unique",
            DQSeverity.ERROR,
            check_pk_unique,
            {"keys": ["sid", "trade_date"]},
        ),
        DQRule("sid_not_null", DQSeverity.ERROR, check_sid_not_null),
        DQRule("ohlc_positive", DQSeverity.ERROR, check_ohlc_positive),
        DQRule("ohlc_relationship", DQSeverity.ERROR, check_ohlc_relationship),
        DQRule(
            "volume_amount_consistency",
            DQSeverity.WARNING,
            check_volume_amount_consistency,
        ),
    ],
    "etf_daily": [
        DQRule(
            "primary_key_unique",
            DQSeverity.ERROR,
            check_pk_unique,
            {"keys": ["sid", "trade_date"]},
        ),
        DQRule("sid_not_null", DQSeverity.ERROR, check_sid_not_null),
        DQRule("ohlc_positive", DQSeverity.ERROR, check_ohlc_positive),
    ],
    "index_daily": [
        DQRule(
            "primary_key_unique",
            DQSeverity.ERROR,
            check_pk_unique,
            {"keys": ["sid", "trade_date"]},
        ),
        DQRule("sid_not_null", DQSeverity.ERROR, check_sid_not_null),
    ],
    "index_weight": [
        DQRule(
            "primary_key_unique",
            DQSeverity.ERROR,
            check_pk_unique,
            {"keys": ["index_sid", "con_sid", "trade_date"]},
        ),
        DQRule("weight_positive", DQSeverity.WARNING, check_weight_positive),
    ],
    "adj_factor": [
        DQRule(
            "primary_key_unique",
            DQSeverity.ERROR,
            check_pk_unique,
            {"keys": ["sid", "trade_date"]},
        ),
        DQRule(
            "has_knowledge_date",
            DQSeverity.ERROR,
            check_required_columns,
            {"columns": ["knowledge_date"]},
        ),
    ],
}
