"""Shared fixtures for backtest integration tests.

提供 3 日和 5 日 parquet 测试数据、etf_rotation 策略 Pipeline、
EngineLoop 组装所需的全部组件。

Phase 3 新增:
- 涨跌停场景数据 (limit_up / limit_down)
- ST 场景数据 (5% 涨跌停)
- AShare BrokerageModel fixture
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import polars as pl
import pytest
from ditto_core.accounting.account import Account
from ditto_core.accounting.cash import CashBook
from ditto_core.backtest.data_feed import DataFeed, Slice
from ditto_core.backtest.engine import (
    EngineConfig,
    EngineLoop,
    EngineMode,
    EngineOptions,
)
from ditto_core.backtest.risk.pre_trade import (
    BuyingPowerCheck,
    CompositePreTradeCheck,
    LotSizeCheck,
)
from ditto_core.execution.brokerage import BacktestBrokerage
from ditto_core.execution.planner import SimpleExecutionPlanner
from ditto_core.execution.reality import (
    AShareFeeModel,
    AShareFillModel,
    AShareSettlementModel,
    BrokerageModel,
    FixedBpsSlippage,
    SimpleFeeModel,
)
from ditto_core.execution.reality.market import MarketSnapshot
from ditto_core.strategy.templates.etf_rotation import (
    ETFRotationConfig,
    build_etf_rotation_pipeline,
)
from ditto_kernel.identity import InstrumentId

# ---------------------------------------------------------------------------
# TestParquetDataFeed — 测试专用的 parquet 数据源
# ---------------------------------------------------------------------------


class TestParquetDataFeed:
    """测试专用的 Parquet-backed DataFeed — 从 parquet 文件读取市场数据。

    接受 ``list[int]`` 并内部转换为 ``InstrumentId``，方便测试使用。
    """

    def __init__(
        self,
        data_dir: str | Path,
        instrument_ids: list[Any],
        start_date: str,
        end_date: str,
    ) -> None:
        self._data_dir = Path(data_dir)
        self._instrument_ids = [InstrumentId(i) for i in instrument_ids]
        self._start_date = start_date
        self._end_date = end_date
        self._data: dict[InstrumentId, pl.DataFrame] | None = None

    def _load(self) -> dict[InstrumentId, pl.DataFrame]:
        """Lazy-load all parquet files into memory."""
        if self._data is not None:
            return self._data

        data: dict[InstrumentId, pl.DataFrame] = {}
        for iid in self._instrument_ids:
            path = self._data_dir / f"{iid}.parquet"
            if not path.exists():
                continue
            data[iid] = pl.read_parquet(path)
        self._data = data
        return data

    @staticmethod
    def _row_to_snapshot(
        date: str,
        iid: InstrumentId,
        row: dict[str, Any],
    ) -> MarketSnapshot:
        """Convert a polars row dict to a MarketSnapshot."""
        return MarketSnapshot(
            trade_date=date,
            instrument_id=iid,
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            prev_close=float(row["prev_close"]),
            volume=float(row["volume"]),
            amount=float(row["amount"]),
            is_suspended=bool(row["is_suspended"]),
            limit_up=(
                float(row["limit_up"]) if row.get("limit_up") is not None else None
            ),
            limit_down=(
                float(row["limit_down"]) if row.get("limit_down") is not None else None
            ),
            avg_volume_20d=(
                float(row["avg_volume_20d"])
                if row.get("avg_volume_20d") is not None
                else None
            ),
        )

    def trading_days(self) -> list[str]:
        """Return sorted list of unique trade dates in [start_date, end_date]."""
        data = self._load()
        all_dates: set[str] = set()
        for df in data.values():
            dates = df["trade_date"].cast(pl.String)
            all_dates.update(dates.to_list())

        filtered = {d for d in all_dates if self._start_date <= d <= self._end_date}
        return sorted(filtered)

    def get_slice(self, date: str) -> Slice:
        """Build Slice with all instruments' data for the given date."""
        data = self._load()
        date_obj = datetime.strptime(date, "%Y-%m-%d")
        step_time = date_obj.replace(hour=15, minute=0, second=0)

        bars: dict[InstrumentId, MarketSnapshot] = {}
        for iid, df in data.items():
            row = df.filter(pl.col("trade_date") == date)
            if row.height == 0:
                continue
            bars[iid] = self._row_to_snapshot(date, iid, row.to_dicts()[0])

        return Slice(trade_date=date, step_time=step_time, bars=bars)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

INITIAL_CASH = 1_000_000.0

# 3 个 ETF 标的
INSTRUMENT_IDS = [1, 2, 3]

# 3 个交易日
TRADE_DATES_3 = ["2026-01-05", "2026-01-06", "2026-01-07"]

# 5 个交易日
TRADE_DATES_5 = ["2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08", "2026-01-09"]


# ---------------------------------------------------------------------------
# Parquet data generation
# ---------------------------------------------------------------------------


def _make_market_df(
    dates: list[str],
    close_prices: list[float],
    open_prices: list[float] | None = None,
    high_prices: list[float] | None = None,
    low_prices: list[float] | None = None,
    volumes: list[float] | None = None,
) -> pl.DataFrame:
    """构建单个标的的市场数据 DataFrame。"""
    n = len(dates)
    return pl.DataFrame(
        {
            "trade_date": dates,
            "open": open_prices or close_prices,
            "high": high_prices or [c * 1.01 for c in close_prices],
            "low": low_prices or [c * 0.99 for c in close_prices],
            "close": close_prices,
            "prev_close": [close_prices[0], *close_prices[:-1]],
            "volume": volumes or [1_000_000.0] * n,
            "amount": [c * 1_000_000.0 for c in close_prices],
            "is_suspended": [False] * n,
        },
    )


def _make_market_df_with_limits(
    dates: list[str],
    close_prices: list[float],
    limit_ups: list[float | None],
    limit_downs: list[float | None],
    open_prices: list[float] | None = None,
    high_prices: list[float] | None = None,
    low_prices: list[float] | None = None,
    volumes: list[float] | None = None,
) -> pl.DataFrame:
    """构建带涨跌停限制的市场数据 DataFrame。"""
    n = len(dates)
    return pl.DataFrame(
        {
            "trade_date": dates,
            "open": open_prices or close_prices,
            "high": high_prices or [c * 1.01 for c in close_prices],
            "low": low_prices or [c * 0.99 for c in close_prices],
            "close": close_prices,
            "prev_close": [close_prices[0], *close_prices[:-1]],
            "volume": volumes or [1_000_000.0] * n,
            "amount": [c * 1_000_000.0 for c in close_prices],
            "is_suspended": [False] * n,
            "limit_up": limit_ups,
            "limit_down": limit_downs,
        },
    )


def generate_3day_data() -> dict[int, pl.DataFrame]:
    """3 日测试数据 — 价格稳定，方便确定性验证。"""
    return {
        1: _make_market_df(
            TRADE_DATES_3,
            [10.0, 10.2, 10.1],
        ),
        2: _make_market_df(
            TRADE_DATES_3,
            [20.0, 19.8, 20.1],
        ),
        3: _make_market_df(
            TRADE_DATES_3,
            [5.0, 5.1, 4.9],
        ),
    }


def generate_5day_data() -> dict[int, pl.DataFrame]:
    """5 日测试数据 — 包含价格波动。"""
    return {
        1: _make_market_df(
            TRADE_DATES_5,
            [10.0, 10.2, 10.1, 10.3, 10.5],
        ),
        2: _make_market_df(
            TRADE_DATES_5,
            [20.0, 19.8, 20.1, 20.5, 20.3],
        ),
        3: _make_market_df(
            TRADE_DATES_5,
            [5.0, 5.1, 4.9, 5.2, 5.3],
        ),
    }


def generate_limit_up_data() -> dict[int, pl.DataFrame]:
    """涨停场景 — Day 1 正常买入，Day 2 涨停（买入失败），Day 3 正常。

    ETF-001: Day 2 close=11.0 (涨停价=11.0, prev_close=10.0, +10%)
    ETF-002/003: 正常波动，不受涨跌停影响
    """
    return {
        1: _make_market_df_with_limits(
            TRADE_DATES_3,
            close_prices=[10.0, 11.0, 10.5],
            limit_ups=[11.0, 11.0, 11.55],
            limit_downs=[9.0, 9.9, 9.45],
            high_prices=[10.1, 11.0, 10.6],
            low_prices=[9.9, 10.8, 10.4],
        ),
        2: _make_market_df(
            TRADE_DATES_3,
            [20.0, 19.8, 20.1],
        ),
        3: _make_market_df(
            TRADE_DATES_3,
            [5.0, 5.1, 4.9],
        ),
    }


def generate_limit_down_data() -> dict[int, pl.DataFrame]:
    """跌停场景 — Day 1 正常买入，Day 2 跌停（卖出失败），Day 3 正常。

    ETF-001: Day 2 close=9.0 (跌停价=9.0, prev_close=10.0, -10%)
    ETF-002/003: 正常波动，不受涨跌停影响
    """
    return {
        1: _make_market_df_with_limits(
            TRADE_DATES_3,
            close_prices=[10.0, 9.0, 9.5],
            limit_ups=[11.0, 9.9, 10.45],
            limit_downs=[9.0, 9.0, 8.55],
            high_prices=[10.1, 9.1, 9.6],
            low_prices=[9.9, 9.0, 9.4],
        ),
        2: _make_market_df(
            TRADE_DATES_3,
            [20.0, 19.8, 20.1],
        ),
        3: _make_market_df(
            TRADE_DATES_3,
            [5.0, 5.1, 4.9],
        ),
    }


def generate_st_data() -> dict[int, pl.DataFrame]:
    """ST 场景 — ETF-001 为 ST 标的（5% 涨跌停），ETF-002/003 正常。

    ETF-001: limit_up=10.5, limit_down=9.5 (prev_close=10.0, ±5%)
    Day 2: close=10.5 (涨停)
    """
    return {
        1: _make_market_df_with_limits(
            TRADE_DATES_3,
            close_prices=[10.0, 10.5, 10.3],
            limit_ups=[10.5, 10.5, 11.025],
            limit_downs=[9.5, 9.975, 9.8],
            high_prices=[10.1, 10.5, 10.4],
            low_prices=[9.9, 10.4, 10.2],
        ),
        2: _make_market_df(
            TRADE_DATES_3,
            [20.0, 19.8, 20.1],
        ),
        3: _make_market_df(
            TRADE_DATES_3,
            [5.0, 5.1, 4.9],
        ),
    }


def write_parquet_data(
    tmp_path: Path,
    data: dict[int, pl.DataFrame],
) -> Path:
    """将测试数据写入 parquet 文件，返回数据目录。"""
    data_dir = tmp_path / "market_data"
    data_dir.mkdir()
    for iid, df in data.items():
        df.write_parquet(data_dir / f"{iid}.parquet")
    return data_dir


# ---------------------------------------------------------------------------
# Fixtures: 3-day backtest
# ---------------------------------------------------------------------------


@pytest.fixture
def three_day_data() -> dict[int, pl.DataFrame]:
    """3 日市场数据。"""
    return generate_3day_data()


@pytest.fixture
def three_day_parquet_dir(
    tmp_path: Path,
    three_day_data: dict[int, pl.DataFrame],
) -> Path:
    """3 日 parquet 数据目录。"""
    return write_parquet_data(tmp_path, three_day_data)


@pytest.fixture
def three_day_data_feed(three_day_parquet_dir: Path) -> DataFeed:
    """3 日 TestParquetDataFeed。"""
    return TestParquetDataFeed(
        data_dir=three_day_parquet_dir,
        instrument_ids=INSTRUMENT_IDS,
        start_date="2026-01-05",
        end_date="2026-01-07",
    )


@pytest.fixture
def three_day_engine_config() -> EngineConfig:
    """3 日回测引擎配置。"""
    return EngineConfig(
        start_date="2026-01-05",
        end_date="2026-01-07",
        initial_cash=INITIAL_CASH,
        mode=EngineMode.BACKTEST,
        strategy_id="test-etf-rotation",
        strategy_run_id="run-3day",
    )


@pytest.fixture
def etf_rotation_pipeline() -> Any:
    """etf_rotation 策略 Pipeline — top_k=3, equal_weight。"""
    config = ETFRotationConfig(top_k=3, cash_target=0.0)
    return build_etf_rotation_pipeline(config)


@pytest.fixture
def fee_model() -> SimpleFeeModel:
    """统一手续费模型。"""
    return SimpleFeeModel()


@pytest.fixture
def backtest_account() -> Account:
    """初始资金 100 万的可变账户。"""
    return Account(
        cash=CashBook(
            available=INITIAL_CASH,
            settled=INITIAL_CASH,
            frozen=0.0,
        ),
    )


@pytest.fixture
def pre_trade_check() -> CompositePreTradeCheck:
    """组合 PreTrade 校验。"""
    return CompositePreTradeCheck(
        checks=(LotSizeCheck(), BuyingPowerCheck()),
    )


@pytest.fixture
def assembled_engine_loop(
    three_day_engine_config: EngineConfig,
    etf_rotation_pipeline: Any,
    backtest_account: Account,
    pre_trade_check: CompositePreTradeCheck,
    three_day_data_feed: DataFeed,
    fee_model: SimpleFeeModel,
) -> EngineLoop:
    """完整组装的 3 日回测引擎 — 所有组件均为真实实现。"""
    brokerage = BacktestBrokerage(
        account=backtest_account,
        model=BrokerageModel(fee_model=fee_model),
    )
    planner = SimpleExecutionPlanner()

    return EngineLoop(
        config=three_day_engine_config,
        pipeline=etf_rotation_pipeline,
        planner=planner,
        brokerage=brokerage,
        pre_trade_check=pre_trade_check,
        data_feed=three_day_data_feed,
        options=EngineOptions(fee_model=fee_model),
    )


# ---------------------------------------------------------------------------
# Fixtures: 5-day backtest
# ---------------------------------------------------------------------------


@pytest.fixture
def five_day_data() -> dict[int, pl.DataFrame]:
    """5 日市场数据。"""
    return generate_5day_data()


@pytest.fixture
def five_day_parquet_dir(
    tmp_path: Path,
    five_day_data: dict[int, pl.DataFrame],
) -> Path:
    """5 日 parquet 数据目录。"""
    return write_parquet_data(tmp_path, five_day_data)


@pytest.fixture
def five_day_data_feed(five_day_parquet_dir: Path) -> DataFeed:
    """5 日 TestParquetDataFeed。"""
    return TestParquetDataFeed(
        data_dir=five_day_parquet_dir,
        instrument_ids=INSTRUMENT_IDS,
        start_date="2026-01-05",
        end_date="2026-01-09",
    )


@pytest.fixture
def five_day_engine_config() -> EngineConfig:
    """5 日回测引擎配置。"""
    return EngineConfig(
        start_date="2026-01-05",
        end_date="2026-01-09",
        initial_cash=INITIAL_CASH,
        mode=EngineMode.BACKTEST,
        strategy_id="test-etf-rotation",
        strategy_run_id="run-5day",
    )


@pytest.fixture
def five_day_engine_loop(
    five_day_engine_config: EngineConfig,
    etf_rotation_pipeline: Any,
    five_day_data_feed: DataFeed,
    pre_trade_check: CompositePreTradeCheck,
    fee_model: SimpleFeeModel,
) -> EngineLoop:
    """完整组装的 5 日回测引擎。"""
    account = Account(
        cash=CashBook(
            available=INITIAL_CASH,
            settled=INITIAL_CASH,
            frozen=0.0,
        ),
    )
    brokerage = BacktestBrokerage(
        account=account,
        model=BrokerageModel(fee_model=fee_model),
    )
    planner = SimpleExecutionPlanner()

    return EngineLoop(
        config=five_day_engine_config,
        pipeline=etf_rotation_pipeline,
        planner=planner,
        brokerage=brokerage,
        pre_trade_check=pre_trade_check,
        data_feed=five_day_data_feed,
        options=EngineOptions(fee_model=fee_model),
    )


# ---------------------------------------------------------------------------
# Fixtures: A-Share reality model scenarios (Phase 3)
# ---------------------------------------------------------------------------


@pytest.fixture
def ashare_brokerage_model() -> BrokerageModel:
    """A 股完整 BrokerageModel — AShareFillModel + AShareSettlementModel。"""
    return BrokerageModel(
        fill_model=AShareFillModel(),
        slippage_model=FixedBpsSlippage(),
        fee_model=AShareFeeModel(),
        settlement_model=AShareSettlementModel(),
    )


@pytest.fixture
def ashare_fee_model() -> AShareFeeModel:
    """A 股费用模型。"""
    return AShareFeeModel()


@pytest.fixture
def limit_up_data() -> dict[int, pl.DataFrame]:
    """涨停场景市场数据。"""
    return generate_limit_up_data()


@pytest.fixture
def limit_up_parquet_dir(
    tmp_path: Path,
    limit_up_data: dict[int, pl.DataFrame],
) -> Path:
    """涨停场景 parquet 数据目录。"""
    return write_parquet_data(tmp_path, limit_up_data)


@pytest.fixture
def limit_up_data_feed(limit_up_parquet_dir: Path) -> DataFeed:
    """涨停场景 TestParquetDataFeed。"""
    return TestParquetDataFeed(
        data_dir=limit_up_parquet_dir,
        instrument_ids=INSTRUMENT_IDS,
        start_date="2026-01-05",
        end_date="2026-01-07",
    )


@pytest.fixture
def limit_up_engine_loop(
    three_day_engine_config: EngineConfig,
    etf_rotation_pipeline: Any,
    limit_up_data_feed: DataFeed,
    pre_trade_check: CompositePreTradeCheck,
    ashare_brokerage_model: BrokerageModel,
    ashare_fee_model: AShareFeeModel,
) -> EngineLoop:
    """涨停场景回测引擎 — 使用 AShareFillModel。"""
    account = Account(
        cash=CashBook(
            available=INITIAL_CASH,
            settled=INITIAL_CASH,
            frozen=0.0,
        ),
    )
    brokerage = BacktestBrokerage(
        account=account,
        model=ashare_brokerage_model,
    )
    planner = SimpleExecutionPlanner()

    return EngineLoop(
        config=three_day_engine_config,
        pipeline=etf_rotation_pipeline,
        planner=planner,
        brokerage=brokerage,
        pre_trade_check=pre_trade_check,
        data_feed=limit_up_data_feed,
        options=EngineOptions(fee_model=ashare_fee_model),
    )


@pytest.fixture
def limit_down_data() -> dict[int, pl.DataFrame]:
    """跌停场景市场数据。"""
    return generate_limit_down_data()


@pytest.fixture
def limit_down_parquet_dir(
    tmp_path: Path,
    limit_down_data: dict[int, pl.DataFrame],
) -> Path:
    """跌停场景 parquet 数据目录。"""
    return write_parquet_data(tmp_path, limit_down_data)


@pytest.fixture
def limit_down_data_feed(limit_down_parquet_dir: Path) -> DataFeed:
    """跌停场景 TestParquetDataFeed。"""
    return TestParquetDataFeed(
        data_dir=limit_down_parquet_dir,
        instrument_ids=INSTRUMENT_IDS,
        start_date="2026-01-05",
        end_date="2026-01-07",
    )


@pytest.fixture
def limit_down_engine_loop(
    three_day_engine_config: EngineConfig,
    etf_rotation_pipeline: Any,
    limit_down_data_feed: DataFeed,
    pre_trade_check: CompositePreTradeCheck,
    ashare_brokerage_model: BrokerageModel,
    ashare_fee_model: AShareFeeModel,
) -> EngineLoop:
    """跌停场景回测引擎 — 使用 AShareFillModel。"""
    account = Account(
        cash=CashBook(
            available=INITIAL_CASH,
            settled=INITIAL_CASH,
            frozen=0.0,
        ),
    )
    brokerage = BacktestBrokerage(
        account=account,
        model=ashare_brokerage_model,
    )
    planner = SimpleExecutionPlanner()

    return EngineLoop(
        config=three_day_engine_config,
        pipeline=etf_rotation_pipeline,
        planner=planner,
        brokerage=brokerage,
        pre_trade_check=pre_trade_check,
        data_feed=limit_down_data_feed,
        options=EngineOptions(fee_model=ashare_fee_model),
    )


@pytest.fixture
def st_data() -> dict[int, pl.DataFrame]:
    """ST 场景市场数据 — 5% 涨跌停。"""
    return generate_st_data()


@pytest.fixture
def st_parquet_dir(
    tmp_path: Path,
    st_data: dict[int, pl.DataFrame],
) -> Path:
    """ST 场景 parquet 数据目录。"""
    return write_parquet_data(tmp_path, st_data)


@pytest.fixture
def st_data_feed(st_parquet_dir: Path) -> DataFeed:
    """ST 场景 TestParquetDataFeed。"""
    return TestParquetDataFeed(
        data_dir=st_parquet_dir,
        instrument_ids=INSTRUMENT_IDS,
        start_date="2026-01-05",
        end_date="2026-01-07",
    )


@pytest.fixture
def st_engine_loop(
    three_day_engine_config: EngineConfig,
    etf_rotation_pipeline: Any,
    st_data_feed: DataFeed,
    pre_trade_check: CompositePreTradeCheck,
    ashare_brokerage_model: BrokerageModel,
    ashare_fee_model: AShareFeeModel,
) -> EngineLoop:
    """ST 场景回测引擎 — 标的 1 为 ST 标的（5% 涨跌停）。"""
    account = Account(
        cash=CashBook(
            available=INITIAL_CASH,
            settled=INITIAL_CASH,
            frozen=0.0,
        ),
    )
    brokerage = BacktestBrokerage(
        account=account,
        model=ashare_brokerage_model,
    )
    planner = SimpleExecutionPlanner()

    return EngineLoop(
        config=three_day_engine_config,
        pipeline=etf_rotation_pipeline,
        planner=planner,
        brokerage=brokerage,
        pre_trade_check=pre_trade_check,
        data_feed=st_data_feed,
        options=EngineOptions(fee_model=ashare_fee_model),
    )
