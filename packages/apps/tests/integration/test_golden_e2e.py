"""Synthetic Golden E2E Test -- 全链路回测验证.

使用纯合成数据（无外部数据源）验证回测引擎主线:
  合成行情 -> 策略信号 -> 组合构建 -> 风控检查 -> 模拟执行 -> 绩效报告

设计原则:
  - 零外部依赖: 不依赖网络、数据库、本地文件
  - 确定性: 固定种子 + 固定价格序列 -> 可复现结果
  - 最小范围: 证明链路通畅，不测试边界条件

参考: packages/backtest/tests/integration/ 下的 golden baseline 模式.
"""

from __future__ import annotations

from datetime import UTC, datetime

import polars as pl
import pytest
from ditto_backtest.audit import ExecutionAuditCollector
from ditto_backtest.brokerage import BacktestBrokerage
from ditto_backtest.data_feed import ProviderBackedDataFeed
from ditto_backtest.engine import (
    EngineConfig,
    EngineLoop,
    EngineMode,
    EngineOptions,
)
from ditto_backtest.simulation import BrokerageModel
from ditto_backtest.statistics import BacktestReport, build_report
from ditto_backtest.synchronizer import BacktestSynchronizer
from ditto_data.provider import BarQuery, InstrumentQuery
from ditto_execution.orders.book import OrderBook
from ditto_execution.orders.journal import InMemoryOrderEventJournal
from ditto_execution.planner import SimpleExecutionPlanner
from ditto_execution.reality import SimpleFeeModel
from ditto_kernel.clock import SimulatedClock
from ditto_kernel.identity import InstrumentId
from ditto_portfolio.accounting import Account, CashBook
from ditto_risk.pre_trade import (
    BuyingPowerCheck,
    CompositePreTradeCheck,
    LotSizeCheck,
)
from ditto_strategy.alpha.pipeline import StrategyPipeline
from ditto_strategy.alpha.templates.etf_rotation import (
    ETFRotationConfig,
    build_etf_rotation_pipeline,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

INITIAL_CASH = 1_000_000.0

# 3 只 ETF 标的 (模拟 A 股 ETF)
#   1 -> 510300.SH (沪深 300ETF)
#   2 -> 510500.SH (中证 500ETF)
#   3 -> 159919.SZ (沪深 300ETF 深)
INSTRUMENT_IDS = [1, 2, 3]
ID_MAP: dict[str, InstrumentId] = {str(i): InstrumentId(i) for i in INSTRUMENT_IDS}

# 5 个交易日 (周一周五)
TRADE_DATES = [
    "2026-01-05",  # Monday
    "2026-01-06",  # Tuesday
    "2026-01-07",  # Wednesday
    "2026-01-08",  # Thursday
    "2026-01-09",  # Friday
]


# ---------------------------------------------------------------------------
# Synthetic Parquet Provider
# ---------------------------------------------------------------------------


class _SyntheticParquetProvider:
    """内存中的合成数据 Provider -- 从 polars DataFrame 直接读取."""

    def __init__(
        self,
        data: dict[InstrumentId, pl.DataFrame],
        id_map: dict[str, InstrumentId],
    ) -> None:
        self._data = data
        self._id_map = id_map

    def get_bars(self, query: BarQuery) -> pl.DataFrame:
        """拼接标的 bar 数据为含 instrument_id 列的 DataFrame."""
        frames: list[pl.DataFrame] = []
        for ticker in query.instruments:
            iid = self._id_map.get(ticker)
            if iid is None or iid not in self._data:
                continue
            df = self._data[iid].with_columns(instrument_id=pl.lit(int(iid)))
            frames.append(df)
        if not frames:
            return pl.DataFrame()
        result = pl.concat(frames, how="diagonal")
        return result.filter(
            (pl.col("trade_date") >= query.start) & (pl.col("trade_date") <= query.end)
        )

    def get_schedule(self, start: str, end: str) -> pl.DataFrame:
        """从已加载数据提取去重排序的 trade_date 列表."""
        all_dates: set[str] = set()
        for df in self._data.values():
            all_dates.update(df["trade_date"].cast(pl.String).to_list())
        filtered = sorted(d for d in all_dates if start <= d <= end)
        return pl.DataFrame({"trade_date": filtered})

    def get_instruments(self, query: InstrumentQuery) -> pl.DataFrame:
        """未使用 -- ProviderBackedDataFeed 不调用."""
        return pl.DataFrame()

    def get_factor(
        self,
        name: str,
        instruments: tuple[str, ...],
        start: str,
        end: str,
        asof: str | None = None,
    ) -> pl.DataFrame:
        """未使用 -- ProviderBackedDataFeed 不调用."""
        return pl.DataFrame()


# ---------------------------------------------------------------------------
# Synthetic data generation
# ---------------------------------------------------------------------------


def _make_bar_df(
    dates: list[str],
    close_prices: list[float],
    volumes: list[float] | None = None,
) -> pl.DataFrame:
    """构建单标的 OHLCV DataFrame -- 完整回测引擎所需的全部列."""
    n = len(dates)
    return pl.DataFrame(
        {
            "trade_date": dates,
            "open": close_prices,
            "high": [c * 1.01 for c in close_prices],
            "low": [c * 0.99 for c in close_prices],
            "close": close_prices,
            "prev_close": [close_prices[0], *close_prices[:-1]],
            "volume": volumes or [1_000_000.0] * n,
            "amount": [c * 1_000_000.0 for c in close_prices],
            "is_suspended": [False] * n,
        },
    )


def _generate_5day_data() -> dict[InstrumentId, pl.DataFrame]:
    """5 日合成行情 -- 价格有趋势方向，策略可产生有意义的信号.

    标的 1: 上升趋势 (10.0 -> 10.5)
    标的 2: 先降后升 (20.0 -> 20.3)
    标的 3: 稳定微升 (5.0 -> 5.3)
    """
    return {
        InstrumentId(1): _make_bar_df(
            TRADE_DATES,
            [10.0, 10.2, 10.1, 10.3, 10.5],
        ),
        InstrumentId(2): _make_bar_df(
            TRADE_DATES,
            [20.0, 19.8, 20.1, 20.5, 20.3],
        ),
        InstrumentId(3): _make_bar_df(
            TRADE_DATES,
            [5.0, 5.1, 4.9, 5.2, 5.3],
        ),
    }


def _build_data_feed(
    data: dict[InstrumentId, pl.DataFrame],
    start_date: str,
    end_date: str,
) -> ProviderBackedDataFeed:
    """从内存 DataFrame 构建 ProviderBackedDataFeed."""
    provider = _SyntheticParquetProvider(data=data, id_map=ID_MAP)
    return ProviderBackedDataFeed(
        provider=provider,
        tickers=tuple(ID_MAP.keys()),
        start_date=start_date,
        end_date=end_date,
        id_map=ID_MAP,
    )


def _build_engine(
    data_feed: ProviderBackedDataFeed,
    start_date: str,
    end_date: str,
    audit: ExecutionAuditCollector,
) -> EngineLoop:
    """组装完整回测引擎 -- 使用 etf_rotation 策略."""
    account = Account(
        cash=CashBook(
            available=INITIAL_CASH,
            settled=INITIAL_CASH,
            frozen=0.0,
        ),
    )
    fee_model = SimpleFeeModel()
    order_book = OrderBook(journal=InMemoryOrderEventJournal())
    brokerage = BacktestBrokerage(
        account=account,
        order_book=order_book,
        model=BrokerageModel(fee_model=fee_model),
    )
    pipeline = StrategyPipeline(
        build_etf_rotation_pipeline(
            ETFRotationConfig(top_k=3, cash_target=0.0),
        ),
    )
    config = EngineConfig(
        start_date=start_date,
        end_date=end_date,
        initial_cash=INITIAL_CASH,
        spec_hash="e" * 64,
        base_spec_hash="e" * 64,
        parameter_hash="4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
        effective_parameters=(),
        research_snapshot_id=None,
        research_snapshot_manifest_hash=None,
        mode=EngineMode.BACKTEST,
        strategy_id="synthetic-golden-e2e",
        strategy_run_id="synthetic-golden-e2e",
    )
    clock = SimulatedClock(
        initial=datetime(
            int(start_date[:4]),
            int(start_date[5:7]),
            int(start_date[8:10]),
            tzinfo=UTC,
        ),
    )
    synchronizer = BacktestSynchronizer(
        data_feed=data_feed,
        clock=clock,
        start_date=start_date,
    )
    return EngineLoop(
        config=config,
        pipeline=pipeline,
        planner=SimpleExecutionPlanner(),
        brokerage=brokerage,
        pre_trade_check=CompositePreTradeCheck(
            checks=(LotSizeCheck(), BuyingPowerCheck()),
        ),
        data_feed=data_feed,
        synchronizer=synchronizer,
        options=EngineOptions(
            fee_model=fee_model,
            audit_collector=audit,
        ),
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def synthetic_data() -> dict[InstrumentId, pl.DataFrame]:
    """5 日合成行情数据."""
    return _generate_5day_data()


@pytest.fixture
def synthetic_data_feed(
    synthetic_data: dict[InstrumentId, pl.DataFrame],
) -> ProviderBackedDataFeed:
    """合成数据 DataFeed."""
    return _build_data_feed(synthetic_data, "2026-01-05", "2026-01-09")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestSyntheticGoldenE2E:
    """Synthetic Golden E2E -- 全链路回测验证."""

    def test_full_pipeline_produces_results(
        self,
        synthetic_data: dict[InstrumentId, pl.DataFrame],
        synthetic_data_feed: ProviderBackedDataFeed,
    ) -> None:
        """验证: 合成数据 -> 策略信号 -> 执行 -> NAV 曲线存在.

        验收标准:
          1. EngineLoop.run() 成功返回 EngineResult
          2. final_nav 为正数（资金未清零）
          3. NAV 序列长度等于交易日数量
          4. 有成交记录（策略产生了交易）
          5. BacktestReport 构建成功
        """
        audit = ExecutionAuditCollector()
        engine = _build_engine(
            synthetic_data_feed,
            start_date="2026-01-05",
            end_date="2026-01-09",
            audit=audit,
        )

        # -- 执行回测 --
        result = engine.run()

        # -- 验收 1: 引擎成功返回 --
        assert result.run_id == "synthetic-golden-e2e"
        assert result.period == ("2026-01-05", "2026-01-09")
        assert not result.cancelled

        # -- 验收 2: NAV 为正 --
        assert result.final_nav > 0, (
            f"final_nav should be positive, got {result.final_nav}"
        )

        # -- 验收 3: 有成交记录 --
        assert result.total_trades > 0, "Strategy should produce at least some trades"

        # -- 验收 4: 无跳过日期 --
        assert result.skipped_dates == (), (
            f"No dates should be skipped, got {result.skipped_dates}"
        )

        # -- 构建报告 --
        report = build_report(audit, run_id=result.run_id)

        # -- 验收 5: 报告结构完整 --
        assert isinstance(report, BacktestReport)
        assert report.run_id == "synthetic-golden-e2e"
        # initial_cash 取首日 NAV（已扣首日交易费用），接近但不等于配置值
        assert report.initial_cash > 0, "Report initial_cash should be positive"
        assert report.initial_cash <= INITIAL_CASH, (
            f"Report initial_cash {report.initial_cash}"
            f" should not exceed config {INITIAL_CASH}"
        )

        # -- 验收 6: NAV 曲线存在且长度正确 --
        assert len(report.nav_series) == len(TRADE_DATES), (
            f"NAV series length {len(report.nav_series)} "
            f"should match trading days {len(TRADE_DATES)}"
        )

        # -- 验收 7: NAV 曲线单调合理 --
        for date_str, nav in report.nav_series:
            assert nav > 0, f"NAV on {date_str} should be positive, got {nav}"

        # -- 验收 8: 组合统计存在 --
        assert len(report.portfolio_stats) == len(TRADE_DATES), (
            f"Portfolio stats length {len(report.portfolio_stats)} "
            f"should match trading days {len(TRADE_DATES)}"
        )

        # -- 验收 9: 绩效统计存在且合理 --
        assert isinstance(report.alpha_stats.sharpe_ratio, float)
        assert isinstance(report.alpha_stats.max_drawdown, float)
        assert isinstance(report.aggregated_trade_stats.total_trades, int)
        assert report.aggregated_trade_stats.total_trades > 0

    def test_synthetic_data_shape_is_correct(
        self,
        synthetic_data: dict[InstrumentId, pl.DataFrame],
    ) -> None:
        """验证合成数据本身的形状和完整性."""
        assert len(synthetic_data) == 3, "Should have 3 instruments"

        for iid in (InstrumentId(1), InstrumentId(2), InstrumentId(3)):
            df = synthetic_data[iid]
            assert len(df) == 5, f"Instrument {iid} should have 5 rows"
            expected_cols = {
                "trade_date",
                "open",
                "high",
                "low",
                "close",
                "prev_close",
                "volume",
                "amount",
                "is_suspended",
            }
            assert set(df.columns) == expected_cols, (
                f"Instrument {iid} columns mismatch"
            )

    def test_data_feed_returns_trading_days(
        self,
        synthetic_data_feed: ProviderBackedDataFeed,
    ) -> None:
        """验证 DataFeed 返回正确的交易日历."""
        days = synthetic_data_feed.trading_days()
        assert days == TRADE_DATES, f"Expected {TRADE_DATES}, got {days}"

    def test_data_feed_returns_slices(
        self,
        synthetic_data_feed: ProviderBackedDataFeed,
    ) -> None:
        """验证 DataFeed 能逐日返回数据切片."""
        for date_str in TRADE_DATES:
            slice_ = synthetic_data_feed.get_slice(date_str)
            assert slice_.trade_date == date_str
            assert len(slice_.bars) == 3, f"Should have 3 instruments on {date_str}"
            for iid in (InstrumentId(1), InstrumentId(2), InstrumentId(3)):
                bar = slice_.bars[iid]
                assert bar.close > 0, f"Close should be positive on {date_str}"

    def test_engine_result_is_deterministic(
        self,
        synthetic_data: dict[InstrumentId, pl.DataFrame],
    ) -> None:
        """验证相同输入产生相同结果 -- 确定性基线."""
        results: list[float] = []
        for _ in range(2):
            data_feed = _build_data_feed(
                synthetic_data,
                "2026-01-05",
                "2026-01-09",
            )
            audit = ExecutionAuditCollector()
            engine = _build_engine(
                data_feed,
                start_date="2026-01-05",
                end_date="2026-01-09",
                audit=audit,
            )
            result = engine.run()
            results.append(result.final_nav)

        assert results[0] == results[1], (
            f"Deterministic check failed: {results[0]} != {results[1]}"
        )
