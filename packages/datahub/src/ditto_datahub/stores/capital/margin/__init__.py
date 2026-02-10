"""Capital domain margin trading subdomain."""

from ditto_datahub.stores.capital.margin.margin_trading_reader import (
    MarginTradingReader,
)
from ditto_datahub.stores.capital.margin.margin_trading_writer import (
    MarginTradingWriter,
)

__all__ = ["MarginTradingReader", "MarginTradingWriter"]
