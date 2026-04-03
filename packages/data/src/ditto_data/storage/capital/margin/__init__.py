"""Capital domain margin trading subdomain."""

from ditto_data.storage.capital.margin.margin_trading_reader import (
    MarginTradingReader,
)
from ditto_data.storage.capital.margin.margin_trading_writer import (
    MarginTradingWriter,
)

__all__ = ["MarginTradingReader", "MarginTradingWriter"]
