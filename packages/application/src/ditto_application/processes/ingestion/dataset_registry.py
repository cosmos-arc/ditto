"""Dataset registry for application ingestion routing."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from functools import cache
from typing import Literal

import polars as pl
from ditto_data.catalog import default_dataset_metadata
from ditto_data.models import (
    FX_CODE_TO_INSTRUMENT_ID,
    GLOBAL_INDEX_CODES,
    Dataset,
    DateScheduleType,
)
from ditto_kernel.instrument import InstrumentIngestParams

from ditto_application.exceptions import AppProcessError  # noqa: RUF100
from ditto_application.processes.ingestion.types import SourceFetchers

__all__ = [
    "GLOBAL_CONTEXT_INDEX_CODES",
    "DailyFetchContext",
    "DailyFetchFactory",
    "DailyFetchHandler",
    "DatasetRegistration",
    "DatasetRegistry",
    "InstrumentFetchContext",
    "InstrumentFetchFactory",
    "InstrumentFetchHandler",
    "WriteKind",
    "default_dataset_registry",
]


@dataclass(frozen=True)
class DailyFetchContext:
    """Runtime inputs for date-level fetch handlers."""

    fetchers: SourceFetchers
    trade_date: str
    fetch_commodity_daily: Callable[[str], pl.DataFrame]
    get_cached_index_codes: Callable[[], list[str]]
    source_name: str = "tushare"
    # 维护者确认的 ETF 参考事实声明读取（#408）；缺配置时 fail closed。
    fetch_etf_reference_config: Callable[[], pl.DataFrame] | None = None


@dataclass(frozen=True)
class InstrumentFetchContext:
    """Runtime inputs for instrument-level fetch handlers."""

    fetchers: SourceFetchers
    source_ticker: str
    params: InstrumentIngestParams


DailyFetchHandler = Callable[[], pl.DataFrame]
DailyFetchFactory = Callable[[DailyFetchContext], DailyFetchHandler]
InstrumentFetchHandler = Callable[[], pl.DataFrame]
InstrumentFetchFactory = Callable[[InstrumentFetchContext], InstrumentFetchHandler]


class WriteKind(StrEnum):
    """Supported ingestion writer routes."""

    UNSUPPORTED = "unsupported"
    TRADED_BARS = "traded_bars"
    INSTRUMENT_CODE_BARS = "instrument_code_bars"
    STOCK_STATUS = "stock_status"
    ADJ_FACTOR = "adj_factor"
    FUND_ADJ = "fund_adj"
    ETF_NAV = "etf_nav"
    STOCK_LIMIT = "stock_limit"
    # #518-#523 增补路由
    LIMIT_LIST = "limit_list"
    FUND_SHARE = "fund_share"
    INDEX_WEIGHT = "index_weight"
    FUNDAMENTAL = "fundamental"
    CAPITAL = "capital"
    MACRO = "macro"
    CALENDAR = "calendar"
    BASIC = "basic"
    GLOBAL_INDEX_BARS = "global_index_bars"
    INDUSTRY_CLASSIFICATION = "industry_classification"
    INDUSTRY_MAPPING = "industry_mapping"
    NAME_HISTORY = "name_history"
    ST_CHANGE_HISTORY = "st_change_history"
    ETF_REFERENCE = "etf_reference"
    ETF_REFERENCE_CONFIG = "etf_reference_config"
    FUTURES_BARS = "futures_bars"
    FUTURES_BASIC = "futures_basic"
    EARNINGS_EVENT = "earnings_event"
    INDEX_VALUATION = "index_valuation"


@dataclass(frozen=True)
class DatasetRegistration:
    """Operational route metadata for one Dataset value."""

    dataset: Dataset
    write_kind: WriteKind
    date_schedule: DateScheduleType = DateScheduleType.TRADING_DAYS
    write_dataset: str | None = None
    daily_fetch_factory: DailyFetchFactory | None = None
    instrument_fetch_factory: InstrumentFetchFactory | None = None
    metadata_dataset: bool = False
    basic_asset_class: Literal["stock", "etf", "index"] | None = None
    # 每日抓取的真实 request 区间（多数数据集按单日抓取，区间即交易日）；
    # 声明后摄取证据把该区间记入快照，而不是只记摄取日。
    request_bounds: Callable[[str], tuple[str, str]] | None = None

    def __post_init__(self) -> None:
        """Validate registration consistency."""
        if (
            self.write_kind
            in {
                WriteKind.TRADED_BARS,
                WriteKind.INSTRUMENT_CODE_BARS,
            }
            and self.write_dataset is None
        ):
            raise AppProcessError(
                f"write_dataset is required for {self.write_kind.value}",
                field="write_kind",
                value=self.write_kind.value,
            )
        if self.write_kind == WriteKind.BASIC and self.basic_asset_class is None:
            raise AppProcessError(
                "basic_asset_class is required for basic datasets",
                field="basic_asset_class",
                value=None,
            )
        # etf_reference 复用 basic 语义（etf_basic 帧），额外产出参考观察行。
        if (
            self.write_kind == WriteKind.ETF_REFERENCE
            and self.basic_asset_class != "etf"
        ):
            raise AppProcessError(
                "etf_reference routes require basic_asset_class='etf'",
                field="basic_asset_class",
                value=self.basic_asset_class,
            )

    @property
    def supports_instrument_ingestion(self) -> bool:
        """Return whether this dataset has an instrument-level fetch route."""
        return self.instrument_fetch_factory is not None

    @property
    def requires_year_partition(self) -> bool:
        """Return whether write routing needs a year from trade_date."""
        return not self.metadata_dataset


class DatasetRegistry:
    """Mutable registry used to declare ingestion routing once."""

    def __init__(
        self,
        registrations: tuple[DatasetRegistration, ...] = (),
    ) -> None:
        self._registrations: dict[Dataset, DatasetRegistration] = {}
        for registration in registrations:
            self.register(registration)

    def register(self, registration: DatasetRegistration) -> None:
        """Register one dataset route."""
        if registration.dataset in self._registrations:
            raise AppProcessError(
                f"Dataset already registered: {registration.dataset.value}",
                field="dataset",
                value=registration.dataset.value,
            )
        self._registrations[registration.dataset] = registration

    def validate_catalog_capabilities(self) -> None:
        """Validate all registered routes against data-owned catalog capabilities."""
        for registration in self._registrations.values():
            _validate_catalog_capability(registration)

    def require(self, dataset: Dataset) -> DatasetRegistration:
        """Return a registration or raise a clear error."""
        try:
            return self._registrations[dataset]
        except KeyError:
            raise AppProcessError(
                f"Dataset is not registered: {dataset.value}",
                field="dataset",
                value=dataset.value,
            ) from None

    def datasets(self) -> Iterator[Dataset]:
        """Yield registered dataset IDs in insertion order."""
        return iter(self._registrations)

    def registrations(self) -> tuple[DatasetRegistration, ...]:
        """Return all registrations in insertion order."""
        return tuple(self._registrations.values())

    def supported_instrument_datasets(self) -> frozenset[Dataset]:
        """Return datasets with instrument-level fetch routes."""
        return frozenset(
            registration.dataset
            for registration in self._registrations.values()
            if registration.supports_instrument_ingestion
        )

    def daily_fetch_handlers(
        self,
        ctx: DailyFetchContext,
    ) -> dict[Dataset, DailyFetchHandler]:
        """Build date-level fetch handlers from registrations."""
        handlers: dict[Dataset, DailyFetchHandler] = {}
        for registration in self._registrations.values():
            if registration.daily_fetch_factory is not None:
                handlers[registration.dataset] = registration.daily_fetch_factory(ctx)
        return handlers

    def instrument_fetch_handlers(
        self,
        ctx: InstrumentFetchContext,
    ) -> dict[Dataset, InstrumentFetchHandler]:
        """Build instrument-level fetch handlers from registrations."""
        handlers: dict[Dataset, InstrumentFetchHandler] = {}
        for registration in self._registrations.values():
            if registration.instrument_fetch_factory is not None:
                handlers[registration.dataset] = registration.instrument_fetch_factory(
                    ctx
                )
        return handlers


def _by_instrument(
    method: Callable[..., pl.DataFrame],
    ctx: InstrumentFetchContext,
) -> pl.DataFrame:
    return method(
        source_ticker=ctx.source_ticker,
        start_date=ctx.params.start_date,
        end_date=ctx.params.end_date,
    )


# ---------------------------------------------------------------------------
# Fetch-factory helpers — eliminate the double-lambda boilerplate
# ---------------------------------------------------------------------------


def _daily_fetch(group: str, method: str) -> DailyFetchFactory:
    """``ctx.fetchers.<group>.<method>(ctx.trade_date)``."""

    def factory(ctx: DailyFetchContext) -> DailyFetchHandler:
        fetcher = getattr(ctx.fetchers, group)
        fn = getattr(fetcher, method)
        return lambda: fn(ctx.trade_date)

    return factory


def _instrument_fetch(group: str, method: str) -> InstrumentFetchFactory:
    """Instrument route via ``_by_instrument``."""

    def factory(ctx: InstrumentFetchContext) -> InstrumentFetchHandler:
        fetcher = getattr(ctx.fetchers, group)
        return lambda: _by_instrument(getattr(fetcher, method), ctx)

    return factory


def _property_fetch(group: str, method: str) -> DailyFetchFactory:
    """``ctx.fetchers.<group>.<method>`` — no call, just a property ref."""

    def factory(ctx: DailyFetchContext) -> DailyFetchHandler:
        return getattr(getattr(ctx.fetchers, group), method)

    return factory


def _etf_reference_config_fetch(ctx: DailyFetchContext) -> DailyFetchHandler:
    """Read the maintainer-confirmed reference declaration, fail closed when absent."""

    def fetch() -> pl.DataFrame:
        if ctx.fetch_etf_reference_config is None:
            raise AppProcessError(
                "etf_reference config declaration is not configured: "
                + "config/default/etf_reference.json under DITTO_CONFIG_ROOT"
            )
        return ctx.fetch_etf_reference_config()

    return fetch


def _index_weight_fetch(ctx: DailyFetchContext) -> DailyFetchHandler:
    """Fetch every configured index for one effective date."""

    def fetch() -> pl.DataFrame:
        frames = [
            ctx.fetchers.capital.fetch_index_weight(
                index_code,
                trade_date=ctx.trade_date.replace("-", ""),
            )
            for index_code in ctx.get_cached_index_codes()
        ]
        non_empty = [frame for frame in frames if not frame.is_empty()]
        return (
            pl.concat(non_empty, how="diagonal_relaxed")
            if non_empty
            else pl.DataFrame()
        )

    return fetch


def _index_weight_instrument_fetch(
    ctx: InstrumentFetchContext,
) -> InstrumentFetchHandler:
    """Fetch one index's effective weights over a bounded provider interval."""
    return lambda: ctx.fetchers.capital.fetch_index_weight(
        ctx.source_ticker,
        start_date=ctx.params.start_date.replace("-", ""),
        end_date=ctx.params.end_date.replace("-", ""),
    )


# 官方 21 指数全量篮子（#435）；权威清单在 ditto_data.models.GLOBAL_INDEX_CODES
GLOBAL_CONTEXT_INDEX_CODES: list[str] = list(GLOBAL_INDEX_CODES)


def _global_index_fetch(ctx: DailyFetchContext) -> DailyFetchHandler:
    return lambda: ctx.fetchers.market.fetch_global_index_daily(
        GLOBAL_CONTEXT_INDEX_CODES,
        ctx.trade_date,
        ctx.trade_date,
    )


def _earnings_announcement_fetch(
    group: str,
    method: str,
) -> DailyFetchFactory:
    """``ctx.fetchers.<group>.<method>(ann_date=ctx.trade_date)`` — 公告日驱动."""

    def factory(ctx: DailyFetchContext) -> DailyFetchHandler:
        fetcher = getattr(ctx.fetchers, group)
        fn = getattr(fetcher, method)
        return lambda: fn(ann_date=ctx.trade_date)

    return factory


def _earnings_instrument_fetch(
    group: str,
    method: str,
) -> InstrumentFetchFactory:
    """公告回填：按标的+公告区间（参数即公告日区间）."""

    def factory(ctx: InstrumentFetchContext) -> InstrumentFetchHandler:
        fetcher = getattr(ctx.fetchers, group)
        fn = getattr(fetcher, method)
        return lambda: fn(
            source_ticker=ctx.source_ticker,
            start_date=ctx.params.start_date,
            end_date=ctx.params.end_date,
        )

    return factory


def _history_fetch(group: str, method: str) -> DailyFetchFactory:
    """``ctx.fetchers.<group>.<method>()`` — 全量事件历史，不随 trade_date 推进。"""

    def factory(ctx: DailyFetchContext) -> DailyFetchHandler:
        fetcher = getattr(ctx.fetchers, group)
        return getattr(fetcher, method)  # 已绑定方法即无参 handler

    return factory


def _industry_classification_fetch(ctx: DailyFetchContext) -> DailyFetchHandler:
    """SW L1 + 证监会分类两源拼接（#517）；级别统一 L 前缀，观察日=当天."""

    def fetch() -> pl.DataFrame:
        sw = (
            ctx.fetchers.metadata.fetch_sw_industry(level=1)
            .rename({"source_ticker": "industry_id"})
            .select(
                pl.col("industry_id"),
                pl.col("industry_name"),
                pl.concat_str(
                    pl.lit("L"), pl.col("industry_level").cast(pl.String)
                ).alias("industry_level"),
            )
            .with_columns(
                pl.lit(date.today()).alias("knowledge_date"),
                pl.lit("SW2021").alias("classification_version"),
                pl.lit("sw").alias("source"),
            )
        )
        # csrc_industrial 返回行业树（L1/L2），级别串已是 L 前缀、source=csrc
        csrc = ctx.fetchers.metadata.fetch_csrc_industry().select(
            pl.col("industry_id"),
            pl.col("industry_name"),
            pl.col("industry_level").cast(pl.String),
            pl.lit(date.today()).alias("knowledge_date"),
            pl.lit("CSRC2012").alias("classification_version"),
            pl.col("source"),
        )
        return pl.concat([sw, csrc], how="vertical_relaxed")

    return fetch


def _industry_mapping_fetch(ctx: DailyFetchContext) -> DailyFetchHandler:
    return lambda: ctx.fetchers.metadata.fetch_sw_industry_concepts(
        asof_date=ctx.trade_date,
        level=1,
        knowledge_date=date.today(),
    )


_CHINA_MACRO_CODES = [
    "CN_GDP_YOY",
    "CN_CPI_YOY",
    "CN_PPI_YOY",
    "CN_M2_YOY",
    "CN_PMI_MFG",
    # #434 社融三系列（增量亿元×2/存量万亿元），共享 sf_month 月度窗口
    "CN_SF_FLOW_MONTH",
    "CN_SF_FLOW_CUM",
    "CN_SF_STOCK",
]


def _macro_fetch(ctx: DailyFetchContext) -> DailyFetchHandler:
    """Use the bounded China batch only for Tushare; preserve other providers."""
    if ctx.source_name == "tushare":
        return lambda: ctx.fetchers.macro.fetch_macro_indicators_by_codes(
            _CHINA_MACRO_CODES,
            "2015-01-01",
            ctx.trade_date,
            observed_on=date.today(),
        )
    return lambda: ctx.fetchers.macro.fetch_macro_indicators(ctx.trade_date)


# ---------------------------------------------------------------------------
# Domain-grouped registration sub-lists（模块级常量）
# ---------------------------------------------------------------------------

# fmt: off

def _calendar_request_bounds(trade_date: str) -> tuple[str, str]:
    """日历日更按自然年抓取：年初到次年一月末。"""
    year = int(trade_date[:4])
    return (f"{year}-01-01", f"{year + 1}-01-31")


_METADATA_REGISTRATIONS: tuple[DatasetRegistration, ...] = (
    DatasetRegistration(
        dataset=Dataset.CALENDAR,
        write_kind=WriteKind.CALENDAR,
        metadata_dataset=True,
        daily_fetch_factory=lambda ctx: (
            lambda: ctx.fetchers.metadata.fetch_calendar(
                *_calendar_request_bounds(ctx.trade_date)
            )
        ),
        request_bounds=_calendar_request_bounds,
    ),
    DatasetRegistration(
        dataset=Dataset.STOCK_BASIC,
        write_kind=WriteKind.BASIC,
        basic_asset_class="stock",
        metadata_dataset=True,
        daily_fetch_factory=_property_fetch("metadata", "fetch_stock_basic"),
    ),
    DatasetRegistration(
        dataset=Dataset.ETF_BASIC,
        write_kind=WriteKind.ETF_REFERENCE,
        basic_asset_class="etf",
        metadata_dataset=True,
        daily_fetch_factory=_property_fetch("metadata", "fetch_etf_basic"),
    ),
    # 维护者确认的 ETF 参考事实（#408）：声明文件经真实摄取链落快照/观察行。
    DatasetRegistration(
        dataset=Dataset.ETF_REFERENCE,
        write_kind=WriteKind.ETF_REFERENCE_CONFIG,
        date_schedule=DateScheduleType.SOURCE_DEFINED,
        metadata_dataset=True,
        daily_fetch_factory=_etf_reference_config_fetch,
    ),
    DatasetRegistration(
        dataset=Dataset.INDEX_BASIC,
        write_kind=WriteKind.BASIC,
        basic_asset_class="index",
        metadata_dataset=True,
        daily_fetch_factory=_property_fetch("metadata", "fetch_index_basic"),
    ),
)

_TRADED_BARS_REGISTRATIONS: tuple[DatasetRegistration, ...] = (
    DatasetRegistration(
        dataset=Dataset.STOCK_DAILY,
        write_kind=WriteKind.TRADED_BARS,
        write_dataset="stock_daily",
        daily_fetch_factory=_daily_fetch("market", "fetch_stock_daily"),
        instrument_fetch_factory=_instrument_fetch("market", "fetch_stock_daily"),
    ),
    DatasetRegistration(
        dataset=Dataset.ETF_DAILY,
        write_kind=WriteKind.TRADED_BARS,
        write_dataset="etf_daily",
        daily_fetch_factory=_daily_fetch("market", "fetch_etf_daily"),
        instrument_fetch_factory=_instrument_fetch("market", "fetch_etf_daily"),
    ),
    DatasetRegistration(
        dataset=Dataset.INDEX_DAILY,
        write_kind=WriteKind.TRADED_BARS,
        write_dataset="index_daily",
        daily_fetch_factory=lambda ctx: (
            lambda: ctx.fetchers.market.fetch_index_daily(
                ctx.trade_date,
                ts_codes=ctx.get_cached_index_codes(),
            )
        ),
        instrument_fetch_factory=_instrument_fetch("market", "fetch_index_daily"),
    ),
    DatasetRegistration(
        dataset=Dataset.GLOBAL_INDEX_DAILY,
        write_kind=WriteKind.GLOBAL_INDEX_BARS,
        date_schedule=DateScheduleType.SOURCE_DEFINED,
        daily_fetch_factory=_global_index_fetch,
    ),
)

_INDUSTRY_REGISTRATIONS: tuple[DatasetRegistration, ...] = (
    DatasetRegistration(
        dataset=Dataset.INDUSTRY_CLASSIFICATION,
        write_kind=WriteKind.INDUSTRY_CLASSIFICATION,
        date_schedule=DateScheduleType.SOURCE_DEFINED,
        metadata_dataset=True,
        daily_fetch_factory=_industry_classification_fetch,
    ),
    DatasetRegistration(
        dataset=Dataset.INDUSTRY_MAPPING,
        write_kind=WriteKind.INDUSTRY_MAPPING,
        date_schedule=DateScheduleType.SOURCE_DEFINED,
        metadata_dataset=True,
        daily_fetch_factory=_industry_mapping_fetch,
    ),
)

# #395 可信历史：namechange / st_history（tushare namechange 全量事件流，
# 写入行带 生效时间 + 可知时间(published_at→observed) + 来源三元组）。
_HISTORY_REGISTRATIONS: tuple[DatasetRegistration, ...] = (
    DatasetRegistration(
        dataset=Dataset.NAME_CHANGE,
        write_kind=WriteKind.NAME_HISTORY,
        date_schedule=DateScheduleType.SOURCE_DEFINED,
        metadata_dataset=True,
        daily_fetch_factory=_history_fetch("market", "fetch_name_history"),
    ),
    DatasetRegistration(
        dataset=Dataset.ST_HISTORY,
        write_kind=WriteKind.ST_CHANGE_HISTORY,
        date_schedule=DateScheduleType.SOURCE_DEFINED,
        metadata_dataset=True,
        daily_fetch_factory=_history_fetch("market", "fetch_st_history"),
    ),
)

_MARKET_REGISTRATIONS: tuple[DatasetRegistration, ...] = (
    DatasetRegistration(
        dataset=Dataset.STOCK_STATUS,
        write_kind=WriteKind.STOCK_STATUS,
        daily_fetch_factory=_daily_fetch("market", "fetch_stock_status"),
    ),
    # #519 涨跌停/炸板名单（事件型）
    DatasetRegistration(
        dataset=Dataset.LIMIT_LIST,
        write_kind=WriteKind.LIMIT_LIST,
        daily_fetch_factory=_daily_fetch("market", "fetch_limit_list"),
    ),
    # #522 基金份额（ETF 逐日申报）
    DatasetRegistration(
        dataset=Dataset.FUND_SHARE,
        write_kind=WriteKind.FUND_SHARE,
        daily_fetch_factory=_daily_fetch("market", "fetch_fund_share"),
        instrument_fetch_factory=_instrument_fetch("market", "fetch_fund_share"),
    ),
)

_ADJ_FACTOR_REGISTRATIONS: tuple[DatasetRegistration, ...] = (
    DatasetRegistration(
        dataset=Dataset.ADJ_FACTOR,
        write_kind=WriteKind.ADJ_FACTOR,
        daily_fetch_factory=_daily_fetch("market", "fetch_adj_factor"),
        instrument_fetch_factory=lambda ctx: (
            lambda: ctx.fetchers.market.fetch_adj_factor_by_ticker(
                ts_code=ctx.source_ticker,
                start_date=ctx.params.start_date.replace("-", ""),
                end_date=ctx.params.end_date.replace("-", ""),
            )
        ),
    ),
    DatasetRegistration(
        dataset=Dataset.FUND_ADJ,
        write_kind=WriteKind.FUND_ADJ,
        daily_fetch_factory=_daily_fetch("market", "fetch_fund_adj"),
        instrument_fetch_factory=_instrument_fetch("market", "fetch_fund_adj"),
    ),
    DatasetRegistration(
        dataset=Dataset.ETF_NAV,
        write_kind=WriteKind.ETF_NAV,
        daily_fetch_factory=_daily_fetch("market", "fetch_fund_nav"),
        instrument_fetch_factory=_instrument_fetch("market", "fetch_fund_nav"),
    ),
    # #517 涨跌停价格：stk_limit 单日全市场抓取
    DatasetRegistration(
        dataset=Dataset.STOCK_LIMIT,
        write_kind=WriteKind.STOCK_LIMIT,
        daily_fetch_factory=_daily_fetch("market", "fetch_stock_limit"),
    ),
)

_FUNDAMENTAL_REGISTRATIONS: tuple[DatasetRegistration, ...] = (
    DatasetRegistration(
        dataset=Dataset.BALANCE_SHEET,
        write_kind=WriteKind.FUNDAMENTAL,
        daily_fetch_factory=_daily_fetch("fundamental", "fetch_balance_sheet"),
        instrument_fetch_factory=_instrument_fetch(
            "fundamental", "fetch_balance_sheet"
        ),
    ),
    DatasetRegistration(
        dataset=Dataset.INCOME_STATEMENT,
        write_kind=WriteKind.FUNDAMENTAL,
        daily_fetch_factory=_daily_fetch("fundamental", "fetch_income_statement"),
        instrument_fetch_factory=_instrument_fetch(
            "fundamental", "fetch_income_statement"
        ),
    ),
    DatasetRegistration(
        dataset=Dataset.CASH_FLOW,
        write_kind=WriteKind.FUNDAMENTAL,
        daily_fetch_factory=_daily_fetch("fundamental", "fetch_cash_flow"),
        instrument_fetch_factory=_instrument_fetch(
            "fundamental", "fetch_cash_flow"
        ),
    ),
    DatasetRegistration(
        dataset=Dataset.DIVIDEND,
        write_kind=WriteKind.FUNDAMENTAL,
        date_schedule=DateScheduleType.NATURAL_DAYS,
        daily_fetch_factory=_daily_fetch("fundamental", "fetch_dividend"),
        instrument_fetch_factory=_instrument_fetch(
            "fundamental", "fetch_dividend"
        ),
    ),
    DatasetRegistration(
        dataset=Dataset.CORPORATE_ACTIONS,
        write_kind=WriteKind.FUNDAMENTAL,
        date_schedule=DateScheduleType.NATURAL_DAYS,
        daily_fetch_factory=_daily_fetch("fundamental", "fetch_corporate_actions"),
    ),
    # #521 官方口径财务指标（披露增量，对齐三表）
    DatasetRegistration(
        dataset=Dataset.FINA_INDICATOR,
        write_kind=WriteKind.FUNDAMENTAL,
        daily_fetch_factory=_daily_fetch("fundamental", "fetch_fina_indicator"),
        instrument_fetch_factory=_instrument_fetch(
            "fundamental", "fetch_fina_indicator"
        ),
    ),
    # #522 基金季度持仓（公告日驱动，NATURAL_DAYS 对齐 dividend/corporate_actions）
    DatasetRegistration(
        dataset=Dataset.FUND_PORTFOLIO,
        write_kind=WriteKind.FUNDAMENTAL,
        date_schedule=DateScheduleType.NATURAL_DAYS,
        daily_fetch_factory=_daily_fetch("fundamental", "fetch_fund_portfolio"),
        instrument_fetch_factory=_instrument_fetch(
            "fundamental", "fetch_fund_portfolio"
        ),
    ),
)

_CAPITAL_REGISTRATIONS: tuple[DatasetRegistration, ...] = (
    DatasetRegistration(
        dataset=Dataset.VALUATION_METRICS,
        write_kind=WriteKind.CAPITAL,
        daily_fetch_factory=_daily_fetch("capital", "fetch_valuation_metrics"),
        instrument_fetch_factory=_instrument_fetch(
            "capital", "fetch_valuation_metrics"
        ),
    ),
    DatasetRegistration(
        dataset=Dataset.MARGIN_TRADING,
        write_kind=WriteKind.CAPITAL,
        daily_fetch_factory=_daily_fetch("capital", "fetch_margin_trading"),
        instrument_fetch_factory=_instrument_fetch(
            "capital", "fetch_margin_trading"
        ),
    ),
    DatasetRegistration(
        dataset=Dataset.PLEDGE_RATIO,
        write_kind=WriteKind.CAPITAL,
        daily_fetch_factory=_daily_fetch("capital", "fetch_pledge_ratio"),
        instrument_fetch_factory=_instrument_fetch("capital", "fetch_pledge_ratio"),
    ),
    # #518/#523 日频资金面/筹码（全市场单日 + 按标的回填）
    DatasetRegistration(
        dataset=Dataset.MONEYFLOW,
        write_kind=WriteKind.CAPITAL,
        daily_fetch_factory=_daily_fetch("capital", "fetch_moneyflow"),
        instrument_fetch_factory=_instrument_fetch("capital", "fetch_moneyflow"),
    ),
    DatasetRegistration(
        dataset=Dataset.CYQ_PERF,
        write_kind=WriteKind.CAPITAL,
        daily_fetch_factory=_daily_fetch("capital", "fetch_cyq_perf"),
    ),
    # #519 龙虎榜（事件型，无按标的回填路由）
    DatasetRegistration(
        dataset=Dataset.TOP_LIST,
        write_kind=WriteKind.CAPITAL,
        daily_fetch_factory=_daily_fetch("capital", "fetch_top_list"),
    ),
    DatasetRegistration(
        dataset=Dataset.TOP_INST,
        write_kind=WriteKind.CAPITAL,
        daily_fetch_factory=_daily_fetch("capital", "fetch_top_inst"),
    ),
    # #520 北向两接口（hk_hold 改制后北向季度末节奏）
    DatasetRegistration(
        dataset=Dataset.HK_HOLD,
        write_kind=WriteKind.CAPITAL,
        daily_fetch_factory=_daily_fetch("capital", "fetch_hk_hold"),
        instrument_fetch_factory=_instrument_fetch("capital", "fetch_hk_hold"),
    ),
    DatasetRegistration(
        dataset=Dataset.HSGT_TOP10,
        write_kind=WriteKind.CAPITAL,
        daily_fetch_factory=_daily_fetch("capital", "fetch_hsgt_top10"),
    ),
)

_MACRO_REGISTRATIONS: tuple[DatasetRegistration, ...] = (
    DatasetRegistration(
        dataset=Dataset.MACRO_INDICATORS,
        write_kind=WriteKind.MACRO,
        date_schedule=DateScheduleType.SOURCE_DEFINED,
        daily_fetch_factory=_macro_fetch,
    ),
)

_FX_COMMODITY_REGISTRATIONS: tuple[DatasetRegistration, ...] = (
    DatasetRegistration(
        dataset=Dataset.FX_DAILY,
        write_kind=WriteKind.INSTRUMENT_CODE_BARS,
        write_dataset="fx_daily",
        date_schedule=DateScheduleType.NATURAL_DAYS,
        daily_fetch_factory=lambda ctx: (
            lambda: ctx.fetchers.macro.fetch_fx_daily(
                ts_codes=list(FX_CODE_TO_INSTRUMENT_ID.keys()),
                start_date=ctx.trade_date,
                end_date=ctx.trade_date,
            )
        ),
    ),
    DatasetRegistration(
        dataset=Dataset.COMMODITY_DAILY,
        write_kind=WriteKind.INSTRUMENT_CODE_BARS,
        write_dataset="commodity_daily",
        date_schedule=DateScheduleType.SOURCE_DEFINED,
        daily_fetch_factory=lambda ctx: (
            lambda: ctx.fetch_commodity_daily(ctx.trade_date)
        ),
    ),
)

# #434 四组增补：期货/业绩预告快报/指数估值
_FUTURES_REGISTRATIONS: tuple[DatasetRegistration, ...] = (
    DatasetRegistration(
        dataset=Dataset.FUTURES_DAILY,
        write_kind=WriteKind.FUTURES_BARS,
        daily_fetch_factory=_daily_fetch("market", "fetch_futures_daily"),
        instrument_fetch_factory=_instrument_fetch("market", "fetch_futures_daily"),
    ),
    DatasetRegistration(
        dataset=Dataset.FUTURES_BASIC,
        write_kind=WriteKind.FUTURES_BASIC,
        date_schedule=DateScheduleType.SOURCE_DEFINED,
        daily_fetch_factory=_property_fetch("market", "fetch_futures_basic"),
    ),
)

_EARNINGS_REGISTRATIONS: tuple[DatasetRegistration, ...] = (
    DatasetRegistration(
        dataset=Dataset.EARNINGS_FORECAST,
        write_kind=WriteKind.EARNINGS_EVENT,
        date_schedule=DateScheduleType.NATURAL_DAYS,
        daily_fetch_factory=_earnings_announcement_fetch(
            "fundamental", "fetch_earnings_forecast"
        ),
        instrument_fetch_factory=_earnings_instrument_fetch(
            "fundamental", "fetch_earnings_forecast"
        ),
    ),
    DatasetRegistration(
        dataset=Dataset.EARNINGS_EXPRESS,
        write_kind=WriteKind.EARNINGS_EVENT,
        date_schedule=DateScheduleType.NATURAL_DAYS,
        daily_fetch_factory=_earnings_announcement_fetch(
            "fundamental", "fetch_earnings_express"
        ),
        instrument_fetch_factory=_earnings_instrument_fetch(
            "fundamental", "fetch_earnings_express"
        ),
    ),
)

_INDEX_VALUATION_REGISTRATIONS: tuple[DatasetRegistration, ...] = (
    DatasetRegistration(
        dataset=Dataset.INDEX_VALUATION,
        write_kind=WriteKind.INDEX_VALUATION,
        daily_fetch_factory=_daily_fetch("capital", "fetch_index_valuation"),
        instrument_fetch_factory=_instrument_fetch("capital", "fetch_index_valuation"),
    ),
)

_PLACEHOLDER_REGISTRATIONS: tuple[DatasetRegistration, ...] = (
    DatasetRegistration(
        dataset=Dataset.INDEX_WEIGHT,
        write_kind=WriteKind.INDEX_WEIGHT,
        daily_fetch_factory=_index_weight_fetch,
        instrument_fetch_factory=_index_weight_instrument_fetch,
    ),
)

# fmt: on

_ALL_REGISTRATIONS: tuple[DatasetRegistration, ...] = (
    _METADATA_REGISTRATIONS
    + _TRADED_BARS_REGISTRATIONS
    + _INDUSTRY_REGISTRATIONS
    + _HISTORY_REGISTRATIONS
    + _MARKET_REGISTRATIONS
    + _ADJ_FACTOR_REGISTRATIONS
    + _FUNDAMENTAL_REGISTRATIONS
    + _CAPITAL_REGISTRATIONS
    + _MACRO_REGISTRATIONS
    + _FX_COMMODITY_REGISTRATIONS
    + _FUTURES_REGISTRATIONS
    + _EARNINGS_REGISTRATIONS
    + _INDEX_VALUATION_REGISTRATIONS
    + _PLACEHOLDER_REGISTRATIONS
)


@cache
def default_dataset_registry() -> DatasetRegistry:
    """Build (once) and return the default application ingestion registry."""
    registry = DatasetRegistry()
    for registration in _ALL_REGISTRATIONS:
        registry.register(registration)
    registry.validate_catalog_capabilities()
    return registry


def _validate_catalog_capability(registration: DatasetRegistration) -> None:
    """Validate app routing against data-owned catalog capabilities."""
    metadata = default_dataset_metadata()[registration.dataset.value]
    if registration.date_schedule.value != metadata.schedule:
        raise AppProcessError(
            "Dataset route schedule does not match catalog metadata",
            field="dataset",
            value=registration.dataset.value,
            route_schedule=registration.date_schedule.value,
            catalog_schedule=metadata.schedule,
        )
    has_date_route = registration.daily_fetch_factory is not None
    if has_date_route != metadata.supports_date_ingestion:
        raise AppProcessError(
            "Dataset date route does not match catalog metadata",
            field="dataset",
            value=registration.dataset.value,
            route_supports_date=has_date_route,
            catalog_supports_date=metadata.supports_date_ingestion,
        )
    has_instrument_route = registration.instrument_fetch_factory is not None
    if has_instrument_route != metadata.supports_instrument_ingestion:
        raise AppProcessError(
            "Dataset instrument route does not match catalog metadata",
            field="dataset",
            value=registration.dataset.value,
            route_supports_instrument=has_instrument_route,
            catalog_supports_instrument=metadata.supports_instrument_ingestion,
        )
