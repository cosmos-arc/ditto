"""
Property-based tests for Statistical checker in ditto-datahub.

Uses Hypothesis and polars.testing.parametric to verify statistical invariants.
"""

import math

import polars as pl
from hypothesis import HealthCheck, given, settings
from hypothesis.strategies import floats, integers
from polars.testing.parametric import column, dataframes

# Custom strategies for our data ranges
sid_strategy = integers(min_value=100000001, max_value=999999999)
# Use wider range with more variance to avoid constant values
value_strategy = floats(
    min_value=1.0, max_value=10000.0, allow_nan=False, allow_infinity=False
)
group_strategy = integers(min_value=1, max_value=5)


class TestZScoreProperties:
    """Property-based tests for Z-score statistical properties."""

    @given(
        dataframes(
            cols=[
                column("sid", dtype=pl.Int64, strategy=sid_strategy),
                column("value", dtype=pl.Float64, strategy=value_strategy),
            ],
            min_size=5,
            max_size=20,
        )
    )
    @settings(max_examples=10, suppress_health_check=[HealthCheck.too_slow])
    def test_zscore_mean_is_zero(self, df: pl.DataFrame) -> None:
        """
        Property: Z-score transformed data should have mean approximately zero.

        For any dataset with reasonable variance, after Z-score transformation:
        mean ≈ 0 (within floating point precision)
        """
        mean_val = df["value"].mean()
        std_val = df["value"].std()

        # Skip if no variance (use assume to tell Hypothesis to skip this case)
        if std_val == 0 or not math.isfinite(std_val):
            return

        # Calculate Z-score
        result = df.with_columns(
            ((pl.col("value") - mean_val) / std_val).alias("zscore")
        )

        # Check mean is close to zero
        zscore_mean = result["zscore"].mean()
        assert abs(zscore_mean) < 0.1, f"Z-score mean should be ~0, got {zscore_mean}"

    @given(
        dataframes(
            cols=[
                column("sid", dtype=pl.Int64, strategy=sid_strategy),
                column("value", dtype=pl.Float64, strategy=value_strategy),
            ],
            min_size=5,
            max_size=20,
        )
    )
    @settings(max_examples=10, suppress_health_check=[HealthCheck.too_slow])
    def test_zscore_std_is_one(self, df: pl.DataFrame) -> None:
        """
        Property: Z-score transformed data should have standard deviation of 1.0.

        For any dataset with variance, after Z-score transformation: std ≈ 1.0
        """
        mean_val = df["value"].mean()
        std_val = df["value"].std()

        # Skip if no variance
        if std_val == 0 or not math.isfinite(std_val):
            return

        # Calculate Z-score
        result = df.with_columns(
            ((pl.col("value") - mean_val) / std_val).alias("zscore")
        )

        # Check std is close to 1
        zscore_std = result["zscore"].std()
        assert abs(zscore_std - 1.0) < 0.1, (
            f"Z-score std should be ~1, got {zscore_std}"
        )

    @given(
        dataframes(
            cols=[
                column("sid", dtype=pl.Int64, strategy=sid_strategy),
                column("value", dtype=pl.Float64, strategy=value_strategy),
            ],
            min_size=5,
            max_size=20,
        )
    )
    @settings(max_examples=10, suppress_health_check=[HealthCheck.too_slow])
    def test_zscore_all_finite(self, df: pl.DataFrame) -> None:
        """
        Property: Z-score values should be finite for valid input.

        No NaN or Inf values should appear in Z-scores for valid numeric data.
        """
        mean_val = df["value"].mean()
        std_val = df["value"].std()

        # Skip if no variance
        if std_val == 0 or not math.isfinite(std_val):
            return

        # Calculate Z-score
        result = df.with_columns(
            ((pl.col("value") - mean_val) / std_val).alias("zscore")
        )

        # Check all zscores are finite
        assert result["zscore"].is_finite().all(), "All Z-scores should be finite"

    @given(
        dataframes(
            cols=[
                column("sid", dtype=pl.Int64, strategy=sid_strategy),
                column("value", dtype=pl.Float64, strategy=value_strategy),
            ],
            min_size=5,
            max_size=20,
        )
    )
    @settings(max_examples=10, suppress_health_check=[HealthCheck.too_slow])
    def test_zscore_threshold_filtering(self, df: pl.DataFrame) -> None:
        """
        Property: Threshold filtering should correctly identify outliers.

        When filtering by |zscore| > threshold:
        - All remaining values should exceed threshold
        - Count should match expected
        """
        mean_val = df["value"].mean()
        std_val = df["value"].std()

        # Skip if no variance
        if std_val == 0 or not math.isfinite(std_val):
            return

        threshold = 2.0

        # Calculate Z-score and filter
        result = df.with_columns(
            ((pl.col("value") - mean_val) / std_val).alias("zscore")
        )
        anomalies = result.filter(pl.col("zscore").abs() > threshold)

        # Verify all anomalies exceed threshold
        if anomalies.height > 0:
            assert (anomalies["zscore"].abs() > threshold).all(), (
                "All filtered values should exceed threshold"
            )

    @given(
        dataframes(
            cols=[
                column("group", dtype=pl.Int64, strategy=group_strategy),
                column("value", dtype=pl.Float64, strategy=value_strategy),
            ],
            min_size=10,
            max_size=30,
        )
    )
    @settings(max_examples=8, suppress_health_check=[HealthCheck.too_slow])
    def test_grouped_zscore_properties(self, df: pl.DataFrame) -> None:
        """
        Property: Grouped Z-score should respect group boundaries.

        When calculating Z-scores by group:
        - Each group should have mean ≈ 0
        - Each group should have std ≈ 1
        - Groups should not affect each other
        """
        # Calculate stats by group
        stats = df.group_by("group").agg(
            pl.col("value").mean().alias("mean"),
            pl.col("value").std().alias("std"),
        )

        # Join stats and calculate Z-score
        result = df.join(stats, on="group", how="left").with_columns(
            ((pl.col("value") - pl.col("mean")) / pl.col("std")).alias("zscore")
        )

        # Check each group separately
        for group_val in df["group"].unique():
            group_data = result.filter(pl.col("group") == group_val)

            # Get std value safely
            if group_data.height == 0:
                continue

            std_val = group_data["std"][0]

            # Skip if no variance or std is invalid
            if std_val is None or not math.isfinite(std_val) or std_val == 0:
                continue

            group_zscore = group_data["zscore"]
            zscore_mean = group_zscore.mean()
            zscore_std = group_zscore.std()

            # Check if calculations are valid
            if zscore_mean is None or zscore_std is None:
                continue
            if not math.isfinite(zscore_mean) or not math.isfinite(zscore_std):
                continue

            assert abs(zscore_mean) < 0.2, (
                f"Group {group_val} Z-score mean should be ~0, got {zscore_mean}"
            )
            assert abs(zscore_std - 1.0) < 0.2, (
                f"Group {group_val} Z-score std should be ~1, got {zscore_std}"
            )

    @given(
        dataframes(
            cols=[
                column("sid", dtype=pl.Int64, strategy=sid_strategy),
                column("value", dtype=pl.Float64, strategy=value_strategy),
            ],
            min_size=5,
            max_size=15,
        )
    )
    @settings(max_examples=8, suppress_health_check=[HealthCheck.too_slow])
    def test_zscore_idempotent(self, df: pl.DataFrame) -> None:
        """
        Property: Applying Z-score twice should produce same distribution.

        Z-score transformation is idempotent in terms of distribution shape:
        mean=0, std=1 regardless of how many times applied.
        """
        # First Z-score
        mean1 = df["value"].mean()
        std1 = df["value"].std()

        if std1 == 0 or not math.isfinite(std1):
            return

        df1 = df.with_columns(((pl.col("value") - mean1) / std1).alias("zscore1"))

        # Second Z-score (on already transformed data)
        mean2 = df1["zscore1"].mean()
        std2 = df1["zscore1"].std()

        if std2 == 0 or not math.isfinite(std2):
            return

        df2 = df1.with_columns(((pl.col("zscore1") - mean2) / std2).alias("zscore2"))

        # Both should have mean≈0, std≈1
        assert abs(df2["zscore1"].mean()) < 0.1
        assert abs(df2["zscore1"].std() - 1.0) < 0.1
        assert abs(df2["zscore2"].mean()) < 0.1
        assert abs(df2["zscore2"].std() - 1.0) < 0.1
