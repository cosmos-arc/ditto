"""Generate realistic mock CSV data for testing."""

import random
from datetime import datetime, timedelta
from pathlib import Path

import polars as pl

# Constants
START_DATE = datetime(2020, 1, 1)
END_DATE = datetime(2024, 12, 31)
SYMBOLS: dict[str, dict[str, str | float]] = {
    "510300.SH": {
        "name": "CSI300ETF",
        "initial_price": 3.5,
        "volatility": 0.015,
        "trend": 0.0002,
        "market": "SSE",
        "list_date": "2012-05-04",
    },
    "516010.SH": {
        "name": "CSI300ETFEFund",
        "initial_price": 1.8,
        "volatility": 0.018,
        "trend": 0.0003,
        "market": "SSE",
        "list_date": "2019-10-14",
    },
    "513100.SH": {
        "name": "NASDAQETF",
        "initial_price": 4.2,
        "volatility": 0.022,
        "trend": 0.0004,
        "market": "SSE",
        "list_date": "2013-04-25",
    },
    "000300.SH": {
        "name": "CSI300Index",
        "initial_price": 3500,
        "volatility": 0.015,
        "trend": 0.0002,
        "market": "SZSE",
        "list_date": "2005-04-08",
    },
}


# Skip weekends
WEEKDAY = 5  # Trading days are 0-4 (Monday-Friday)


def is_trading_day(date: datetime) -> bool:
    """Check if date is a weekday (trading day)."""
    return date.weekday() < WEEKDAY


def generate_price_data(
    symbol: str,
    info: dict[str, str | float],
    start_date: datetime,
    end_date: datetime,
) -> pl.DataFrame:
    """Generate realistic price data for a symbol."""
    data = []
    current_date = start_date
    current_price = float(info["initial_price"])

    # Skip to list_date if after start_date
    list_date = datetime.strptime(str(info["list_date"]), "%Y-%m-%d")
    if list_date > start_date:
        current_date = list_date

    while current_date <= end_date:
        if is_trading_day(current_date):
            # Generate OHLC with random walk
            daily_return = random.gauss(float(info["trend"]), float(info["volatility"]))

            # High volatility days (2% of days)
            HIGH_VOLATILITY_PROBABILITY = 0.02
            NEGATIVE_PROBABILITY = 0.5
            if random.random() < HIGH_VOLATILITY_PROBABILITY:
                daily_return *= random.uniform(2, 4)
                if random.random() < NEGATIVE_PROBABILITY:
                    daily_return *= -1  # Make it negative

            new_price = current_price * (1 + daily_return)

            # Generate OHLC
            high = max(current_price, new_price) * random.uniform(1.0, 1.02)
            low = min(current_price, new_price) * random.uniform(0.98, 1.0)
            open_price = current_price * random.uniform(0.995, 1.005)
            close_price = new_price

            # Generate volume (in millions)
            base_volume = random.randint(1000000, 5000000)
            if info["market"] == "SSE":
                volume = base_volume * random.randint(1, 10)
            else:  # Index has different volume pattern
                volume = base_volume * 100

            # Calculate amount = volume * avg price
            avg_price = (high + low + open_price + close_price) / 4
            amount = volume * avg_price

            data.append(
                {
                    "symbol": symbol,
                    "date": current_date.strftime("%Y-%m-%d"),
                    "open": round(open_price, 3),
                    "high": round(high, 3),
                    "low": round(low, 3),
                    "close": round(close_price, 3),
                    "volume": int(volume),
                    "amount": round(amount, 2),
                }
            )

            current_price = close_price

        current_date += timedelta(days=1)

    return pl.DataFrame(data)


def main() -> None:
    """Generate test data files."""
    output_dir = Path("data/test")
    output_dir.mkdir(parents=True, exist_ok=True)
    daily_dir = output_dir / "daily"
    daily_dir.mkdir(parents=True, exist_ok=True)

    # Generate ETF list
    etf_list = []
    for symbol, info in SYMBOLS.items():
        etf_list.append(
            {
                "symbol": symbol,
                "name": info["name"],
                "market": info["market"],
                "list_date": info["list_date"],
            }
        )

        # Generate daily data
        df = generate_price_data(symbol, info, START_DATE, END_DATE)
        output_file = daily_dir / f"{symbol}.csv"
        df.write_csv(output_file)
        print(f"Generated {len(df)} rows for {symbol} -> {output_file}")

    # Save ETF list
    etf_df = pl.DataFrame(etf_list)
    etf_list_file = output_dir / "etf_list.csv"
    etf_df.write_csv(etf_list_file)
    print(f"Generated ETF list -> {etf_list_file}")

    print("\nTest data generation complete!")
    print(f"Output directory: {output_dir.absolute()}")


if __name__ == "__main__":
    main()
