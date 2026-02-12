"""Capital Domain - 资金与资本市场数据域."""

from ditto_datahub.stores.capital.futures.futures_reader import FuturesReader
from ditto_datahub.stores.capital.futures.futures_writer import FuturesWriter
from ditto_datahub.stores.capital.index_composition.index_composition_reader import (
    IndexCompositionReader,
)
from ditto_datahub.stores.capital.index_composition.index_composition_writer import (
    IndexCompositionWriter,
)
from ditto_datahub.stores.capital.margin.margin_trading_reader import (
    MarginTradingReader,
)
from ditto_datahub.stores.capital.margin.margin_trading_writer import (
    MarginTradingWriter,
)
from ditto_datahub.stores.capital.pledge.pledge_ratio_reader import (
    PledgeRatioReader,
)
from ditto_datahub.stores.capital.pledge.pledge_ratio_writer import (
    PledgeRatioWriter,
)
from ditto_datahub.stores.capital.valuation.valuation_metrics_reader import (
    ValuationMetricsReader,
)
from ditto_datahub.stores.capital.valuation.valuation_metrics_writer import (
    ValuationMetricsWriter,
)

__all__ = [
    "FuturesReader",
    "FuturesWriter",
    "IndexCompositionReader",
    "IndexCompositionWriter",
    "MarginTradingReader",
    "MarginTradingWriter",
    "PledgeRatioReader",
    "PledgeRatioWriter",
    "ValuationMetricsReader",
    "ValuationMetricsWriter",
]
