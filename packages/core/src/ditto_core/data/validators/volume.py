"""Volume data validator implementation."""

import polars as pl

from .base import BaseValidator, ValidationResult


class VolumeValidator(BaseValidator):
    """
    Validator for trading volume data.

    Validates:
    - Volume is non-negative
    - No extreme volume spikes (>50x median)
    - No long zero-volume periods (>10 days)
    """

    @property
    def name(self) -> str:
        """Get validator name."""
        return "volume_validator"

    def validate(self, data: pl.DataFrame) -> ValidationResult:
        """
        Validate volume data.

        Args:
            data: DataFrame containing volume data with columns:
                  volume, date

        Returns:
            ValidationResult with validation outcome and details.

        """
        errors = []
        details = {
            "total_records": len(data),
            "negative_volume": 0,
            "extreme_volume": 0,
            "long_zero_volume": 0,
            "volume_stats": {},
        }

        # Check required columns exist
        if "volume" not in data.columns:
            return ValidationResult(
                is_valid=False, message="缺少必需列: volume", details=details
            )

        # Check for negative volume
        negative_volume_mask = data.with_columns(
            [(pl.col("volume") < 0).alias("is_negative")]
        )
        negative_volume = negative_volume_mask["is_negative"].sum()
        details["negative_volume"] = negative_volume
        if negative_volume > 0:
            errors.append(f"负成交量: {negative_volume} 条记录")

        # Calculate volume statistics
        volume_series = data["volume"]
        details["volume_stats"] = {
            "min": volume_series.min(),
            "max": volume_series.max(),
            "median": volume_series.median(),
            "mean": volume_series.mean(),
            "std": volume_series.std(),
        }

        # Check for extreme volume spikes (>50x median)
        volume_median = volume_series.median()
        if volume_median and volume_median > 0:
            extreme_volume_mask = data.with_columns(
                [(pl.col("volume") > (volume_median * 50)).alias("is_extreme")]
            )
            extreme_volume = extreme_volume_mask["is_extreme"].sum()
            details["extreme_volume"] = extreme_volume
            if extreme_volume > 0:
                errors.append(f"异常高成交量(>50倍中位数): {extreme_volume} 条记录")

        # Check for long zero-volume periods (>10 days)
        if "date" in data.columns and len(data) > 1:
            data_sorted = data.sort("date")

            # Calculate consecutive zero volume days
            zero_volume_groups = (
                data_sorted.with_columns([(pl.col("volume") == 0).alias("is_zero")])
                .with_columns(
                    [
                        (
                            pl.col("is_zero")
                            != pl.col("is_zero").shift(1).fill_null(True)
                        )
                        .cum_sum()
                        .alias("group_id")
                    ]
                )
                .filter(pl.col("is_zero"))
                .group_by("group_id")
                .len()
            )

            if len(zero_volume_groups) > 0:
                long_zero_volume_mask = zero_volume_groups.with_columns(
                    [(pl.col("len") > 10).alias("is_long")]
                )
                long_zero_volume = long_zero_volume_mask["is_long"].sum()
                details["long_zero_volume"] = long_zero_volume
                if long_zero_volume > 0:
                    max_zero_days = zero_volume_groups["len"].max()
                    errors.append(
                        f"长期零成交量(>10天): {long_zero_volume} 组, 最长{max_zero_days}天"
                    )

        is_valid = len(errors) == 0
        message = "; ".join(errors) if errors else "成交量数据正常"

        return ValidationResult(is_valid=is_valid, message=message, details=details)
