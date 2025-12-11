"""Price data validator implementation."""

import polars as pl

from .base import BaseValidator, ValidationResult


class PriceValidator(BaseValidator):
    """
    Validator for OHLC price data合理性验证器.

    Validates:
    - All price values are positive
    - High >= max(open, close)
    - Low <= min(open, close)
    - Extreme price changes (>20%)
    """

    @property
    def name(self) -> str:
        """Get validator name."""
        return "price_validator"

    def validate(self, data: pl.DataFrame) -> ValidationResult:
        """
        Validate OHLC price data.

        Args:
            data: DataFrame containing OHLC price data with columns:
                  open, high, low, close, date

        Returns:
            ValidationResult with validation outcome and details.

        """
        errors = []
        details = {
            "total_records": len(data),
            "invalid_high": 0,
            "invalid_low": 0,
            "negative_prices": 0,
            "extreme_changes": 0,
        }

        # Check required columns exist
        required_cols = ["open", "high", "low", "close"]
        missing_cols = [col for col in required_cols if col not in data.columns]
        if missing_cols:
            return ValidationResult(
                is_valid=False,
                message=f"缺少必需列: {', '.join(missing_cols)}",
                details=details,
            )

        # Check for non-positive prices
        non_positive_mask = data.with_columns(
            [
                (pl.col("open") <= 0).alias("open_nonpos"),
                (pl.col("high") <= 0).alias("high_nonpos"),
                (pl.col("low") <= 0).alias("low_nonpos"),
                (pl.col("close") <= 0).alias("close_nonpos"),
            ]
        ).with_columns(
            [
                (
                    pl.col("open_nonpos")
                    | pl.col("high_nonpos")
                    | pl.col("low_nonpos")
                    | pl.col("close_nonpos")
                ).alias("has_nonpos")
            ]
        )
        negative_prices = non_positive_mask["has_nonpos"].sum()
        details["negative_prices"] = negative_prices
        if negative_prices > 0:
            errors.append(f"存在非正价格: {negative_prices} 条记录")

        # Check high >= max(open, close)
        invalid_high_mask = data.with_columns(
            [
                (
                    pl.col("high")
                    < pl.max_horizontal([pl.col("open"), pl.col("close")])
                ).alias("invalid_high")
            ]
        )
        invalid_high = invalid_high_mask["invalid_high"].sum()
        details["invalid_high"] = invalid_high
        if invalid_high > 0:
            errors.append(f"最高价不合理: {invalid_high} 条记录")

        # Check low <= min(open, close)
        invalid_low_mask = data.with_columns(
            [
                (
                    pl.col("low") > pl.min_horizontal([pl.col("open"), pl.col("close")])
                ).alias("invalid_low")
            ]
        )
        invalid_low = invalid_low_mask["invalid_low"].sum()
        details["invalid_low"] = invalid_low
        if invalid_low > 0:
            errors.append(f"最低价不合理: {invalid_low} 条记录")

        # Check for extreme price changes (>20%)
        if "date" in data.columns and len(data) > 1:
            data_sorted = data.sort("date")
            price_changes = data_sorted.with_columns(
                [pl.col("close").pct_change().abs().alias("price_change")]
            ).drop_nulls()

            extreme_changes = (price_changes["price_change"] > 0.2).sum()
            details["extreme_changes"] = extreme_changes
            if extreme_changes > 0:
                errors.append(f"极端价格变化(>20%): {extreme_changes} 条记录")

        is_valid = len(errors) == 0
        message = "; ".join(errors) if errors else "价格数据正常"

        return ValidationResult(is_valid=is_valid, message=message, details=details)
