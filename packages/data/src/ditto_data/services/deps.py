"""
服务依赖聚合 - Service 依赖注入参数分组。

将 Service 的 Reader/Writer 依赖分组为结构化的依赖对象，
避免 __init__ 方法参数过多（PLR0913）。
"""

from __future__ import annotations

from dataclasses import dataclass

from ditto_data.storage.capital.index_composition.index_composition_reader import (
    IndexCompositionReader,
)
from ditto_data.storage.capital.index_composition.index_composition_writer import (
    IndexCompositionWriter,
)
from ditto_data.storage.capital.margin.margin_trading_reader import (
    MarginTradingReader,
)
from ditto_data.storage.capital.margin.margin_trading_writer import (
    MarginTradingWriter,
)
from ditto_data.storage.capital.pledge.pledge_ratio_reader import PledgeRatioReader
from ditto_data.storage.capital.pledge.pledge_ratio_writer import PledgeRatioWriter
from ditto_data.storage.capital.valuation.valuation_metrics_reader import (
    ValuationMetricsReader,
)
from ditto_data.storage.capital.valuation.valuation_metrics_writer import (
    ValuationMetricsWriter,
)
from ditto_data.storage.fundamental.corporate.corporate_actions_reader import (
    CorporateActionsReader,
)
from ditto_data.storage.fundamental.corporate.corporate_actions_writer import (
    CorporateActionsWriter,
)
from ditto_data.storage.fundamental.corporate.dividend_reader import DividendReader
from ditto_data.storage.fundamental.corporate.dividend_writer import DividendWriter
from ditto_data.storage.fundamental.financial.balance_sheet_reader import (
    BalanceSheetReader,
)
from ditto_data.storage.fundamental.financial.balance_sheet_writer import (
    BalanceSheetWriter,
)
from ditto_data.storage.fundamental.financial.cash_flow_reader import CashFlowReader
from ditto_data.storage.fundamental.financial.cash_flow_writer import CashFlowWriter
from ditto_data.storage.fundamental.financial.income_statement_reader import (
    IncomeStatementReader,
)
from ditto_data.storage.fundamental.financial.income_statement_writer import (
    IncomeStatementWriter,
)
from ditto_data.storage.fundamental.forecast.express_reader import ExpressReader
from ditto_data.storage.fundamental.forecast.express_writer import ExpressWriter
from ditto_data.storage.fundamental.forecast.forecast_reader import ForecastReader
from ditto_data.storage.fundamental.forecast.forecast_writer import ForecastWriter
from ditto_data.storage.market.commodity.bars import (
    CommodityBarsReader,
    CommodityBarsWriter,
)
from ditto_data.storage.market.etf.adj import EtfAdjFactorReader, EtfAdjFactorWriter
from ditto_data.storage.market.etf.bars import EtfBarsReader, EtfBarsWriter
from ditto_data.storage.market.etf.nav import EtfNavReader, EtfNavWriter
from ditto_data.storage.market.etf.status import EtfStatusReader, EtfStatusWriter
from ditto_data.storage.market.fx.bars import FxBarsReader, FxBarsWriter
from ditto_data.storage.market.index.bars import IndexBarsReader, IndexBarsWriter
from ditto_data.storage.market.index.constituent import (
    IndexConstituentReader,
    IndexConstituentWriter,
)
from ditto_data.storage.market.index.global_bars import (
    GlobalIndexBarsReader,
    GlobalIndexBarsWriter,
)
from ditto_data.storage.market.stock.adj import (
    StockAdjFactorReader,
    StockAdjFactorWriter,
)
from ditto_data.storage.market.stock.bars import StockBarsReader, StockBarsWriter
from ditto_data.storage.market.stock.status import (
    StockStatusReader,
    StockStatusWriter,
)
from ditto_data.storage.metadata.instrument import InstrumentReader


@dataclass(frozen=True)
class MarketReaders:
    """
    Market 域读取依赖。

    包含所有 Market 域的 Reader 依赖，用于 MarketService 的查询操作。

    Attributes:
        stock_bars: 股票 K线读取器（必需）.
        stock_status: 股票状态读取器（必需）.
        stock_adj: 股票复权因子读取器（必需）.
        etf_bars: ETF K线读取器（必需）.
        etf_status: ETF 状态读取器（必需）.
        instrument: 证券元数据读取器（必需）.
        etf_adj: ETF 复权因子读取器（可选）.
        etf_nav: ETF NAV 读取器（可选）.
        index_bars: 指数 K线读取器（可选）.
        index_constituent: 指数成分股读取器（可选）.
        fx_bars: 外汇 K线读取器（可选）.
        commodity_bars: 大宗商品 K线读取器（可选）.

    """

    # 必需依赖
    stock_bars: StockBarsReader
    stock_status: StockStatusReader
    stock_adj: StockAdjFactorReader
    etf_bars: EtfBarsReader
    etf_status: EtfStatusReader
    instrument: InstrumentReader

    # 可选依赖
    etf_adj: EtfAdjFactorReader | None = None
    etf_nav: EtfNavReader | None = None
    index_bars: IndexBarsReader | None = None
    global_index_bars: GlobalIndexBarsReader | None = None
    index_constituent: IndexConstituentReader | None = None
    fx_bars: FxBarsReader | None = None
    commodity_bars: CommodityBarsReader | None = None


@dataclass(frozen=True)
class MarketWriters:
    """
    Market 域写入依赖。

    包含所有 Market 域的 Writer 依赖，用于 MarketService 的写入操作。

    Attributes:
        stock_bars: 股票 K线写入器（必需）.
        stock_status: 股票状态写入器（必需）.
        stock_adj: 股票复权因子写入器（必需）.
        etf_bars: ETF K线写入器（必需）.
        etf_status: ETF 状态写入器（必需）.
        etf_adj: ETF 复权因子写入器（可选）.
        etf_nav: ETF NAV 写入器（可选）.
        index_bars: 指数 K线写入器（可选）.
        index_constituent: 指数成分股写入器（可选）.
        fx_bars: 外汇 K线写入器（可选）.
        commodity_bars: 大宗商品 K线写入器（可选）.

    """

    # 必需依赖
    stock_bars: StockBarsWriter
    stock_status: StockStatusWriter
    stock_adj: StockAdjFactorWriter
    etf_bars: EtfBarsWriter
    etf_status: EtfStatusWriter

    # 可选依赖
    etf_adj: EtfAdjFactorWriter | None = None
    etf_nav: EtfNavWriter | None = None
    index_bars: IndexBarsWriter | None = None
    global_index_bars: GlobalIndexBarsWriter | None = None
    index_constituent: IndexConstituentWriter | None = None
    fx_bars: FxBarsWriter | None = None
    commodity_bars: CommodityBarsWriter | None = None


@dataclass(frozen=True)
class FundamentalReaders:
    """
    Fundamental 域读取依赖。

    包含所有 Fundamental 域的 Reader 依赖，用于 FundamentalStore 的查询操作。

    Attributes:
        balance_sheet: 资产负债表读取器.
        income_statement: 利润表读取器.
        cash_flow: 现金流量表读取器.
        dividend: 股息读取器.
        corporate_actions: 公司行动读取器.
        forecast: 业绩预告读取器.
        express: 业绩快报读取器.

    """

    balance_sheet: BalanceSheetReader
    income_statement: IncomeStatementReader
    cash_flow: CashFlowReader
    dividend: DividendReader
    corporate_actions: CorporateActionsReader
    forecast: ForecastReader
    express: ExpressReader


@dataclass(frozen=True)
class FundamentalWriters:
    """
    Fundamental 域写入依赖。

    包含所有 Fundamental 域的 Writer 依赖，用于 FundamentalStore 的写入操作。

    Attributes:
        balance_sheet: 资产负债表写入器.
        income_statement: 利润表写入器.
        cash_flow: 现金流量表写入器.
        dividend: 股息写入器.
        corporate_actions: 公司行动写入器.
        forecast: 业绩预告写入器.
        express: 业绩快报写入器.

    """

    balance_sheet: BalanceSheetWriter
    income_statement: IncomeStatementWriter
    cash_flow: CashFlowWriter
    dividend: DividendWriter
    corporate_actions: CorporateActionsWriter
    forecast: ForecastWriter
    express: ExpressWriter


@dataclass(frozen=True)
class CapitalReaders:
    """
    Capital 域读取依赖。

    包含所有 Capital 域的 Reader 依赖，用于 CapitalStore 的查询操作。

    Attributes:
        margin_trading: 融资融券读取器.
        pledge_ratio: 质押比例读取器.
        valuation_metrics: 估值指标读取器.
        index_composition: 指数成分读取器.

    """

    margin_trading: MarginTradingReader
    pledge_ratio: PledgeRatioReader
    valuation_metrics: ValuationMetricsReader
    index_composition: IndexCompositionReader


@dataclass(frozen=True)
class CapitalWriters:
    """
    Capital 域写入依赖。

    包含所有 Capital 域的 Writer 依赖，用于 CapitalStore 的写入操作。

    Attributes:
        margin_trading: 融资融券写入器.
        pledge_ratio: 质押比例写入器.
        valuation_metrics: 估值指标写入器.
        index_composition: 指数成分写入器.

    """

    margin_trading: MarginTradingWriter
    pledge_ratio: PledgeRatioWriter
    valuation_metrics: ValuationMetricsWriter
    index_composition: IndexCompositionWriter


__all__ = [
    "CapitalReaders",
    "CapitalWriters",
    "FundamentalReaders",
    "FundamentalWriters",
    "MarketReaders",
    "MarketWriters",
]
