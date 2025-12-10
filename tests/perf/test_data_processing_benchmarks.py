"""Performance benchmarks for data processing operations."""

import polars as pl
import pytest
from pytest_benchmark.fixture import BenchmarkFixture


@pytest.mark.benchmark
def test_large_dataset_processing_performance(benchmark: BenchmarkFixture) -> None:
    """Benchmark processing of large financial datasets."""

    # Arrange - Create large dataset
    def setup_large_dataset() -> pl.DataFrame:
        """Create a large dataset for benchmarking."""
        n_rows = 1_000_000  # 1 million rows

        # Generate trade dates
        trade_dates = [
            f"2024-{(i % 12) + 1:02d}-{(i % 28) + 1:02d}" for i in range(n_rows)
        ]

        # Generate price data
        open_prices = [3.5 + (i % 100) * 0.01 for i in range(n_rows)]
        high_prices = [3.6 + (i % 100) * 0.01 for i in range(n_rows)]
        low_prices = [3.4 + (i % 100) * 0.01 for i in range(n_rows)]
        close_prices = [3.55 + (i % 100) * 0.01 for i in range(n_rows)]
        volumes = [1_000_000 + i * 100 for i in range(n_rows)]
        amounts = [3_550_000.0 + i * 355 for i in range(n_rows)]

        return pl.DataFrame(
            {
                "symbol": ["510300.SH"] * n_rows,
                "trade_date": trade_dates,
                "open_price": open_prices,
                "high_price": high_prices,
                "low_price": low_prices,
                "close_price": close_prices,
                "volume": volumes,
                "amount": amounts,
            }
        )

    # Act - Benchmark data processing
    large_data = setup_large_dataset()

    # Benchmark groupby operations (common in financial analysis)
    def process_data(data: pl.DataFrame) -> pl.DataFrame:
        """Process data with typical financial operations."""
        return (
            data.lazy()
            .with_columns(
                pl.col("trade_date").str.to_date(),
                daily_return=pl.col("close_price").pct_change(),
                high_low_ratio=pl.col("high_price") / pl.col("low_price"),
            )
            .filter(pl.col("daily_return").is_not_null())
            .group_by("symbol")
            .agg(
                [
                    pl.col("daily_return").mean().alias("avg_return"),
                    pl.col("daily_return").std().alias("return_volatility"),
                    pl.col("volume").sum().alias("total_volume"),
                ]
            )
            .collect()
        )

    # Benchmark the processing
    result = benchmark(process_data, large_data)

    # Assert - Verify results are correct
    assert len(result) == 1
    assert "avg_return" in result.columns
    assert "return_volatility" in result.columns


@pytest.mark.benchmark
def test_factor_calculation_performance(benchmark: BenchmarkFixture) -> None:
    """Benchmark factor calculation performance."""
    # Arrange
    n_dates = 252  # One year of trading days
    n_stocks = 500  # Number of stocks

    # Generate symbols and dates
    symbols = [f"STOCK_{i:03d}" for i in range(n_stocks) for _ in range(n_dates)]
    dates = [
        f"2024-{(d // 21) + 1:02d}-{(d % 21) + 1:02d}"
        for _ in range(n_stocks)
        for d in range(n_dates)
    ]
    closes = [
        100.0 + (i * 0.1) + (d * 0.01) for i in range(n_stocks) for d in range(n_dates)
    ]
    volumes = [1_000_000 for _ in range(n_stocks * n_dates)]

    price_data = pl.DataFrame(
        {
            "symbol": symbols,
            "date": dates,
            "close": closes,
            "volume": volumes,
        }
    )

    # Act - Benchmark factor calculation
    def calculate_factors(data: pl.DataFrame) -> pl.DataFrame:
        """Calculate various technical factors."""
        return (
            data.sort("symbol", "date")
            .group_by("symbol")
            .agg(
                [
                    # Momentum factor (12-month return)
                    (pl.col("close").last() / pl.col("close").first() - 1).alias(
                        "momentum_12m"
                    ),
                    # Volatility factor (annualized)
                    pl.col("close").pct_change().std() * (252**0.5).alias("volatility"),
                    # Volume ratio (recent vs historical average)
                    (pl.col("volume").tail(20).mean() / pl.col("volume").mean()).alias(
                        "volume_ratio"
                    ),
                ]
            )
        )

    # Benchmark
    result = benchmark(calculate_factors, price_data)

    # Assert
    assert len(result) == n_stocks
    assert "momentum_12m" in result.columns
    assert "volatility" in result.columns
    assert "volume_ratio" in result.columns
