"""个股选股 Golden E2E — 合成数据全链路回测验证(因子桥接 + stock_selection).

验证 Phase 1 选股闭环:
  合成 OHLCV(40 日,前 30 日历史 + 后 10 日回测) + 基本面截面 →
  FactorBridge 编译因子(quality_roe / value_pe / momentum_1m) →
  build_factor_aware_bundle_builder 注入 EngineLoop →
  stock_selection pipeline(MultiFactor → TrendFilter → Scoring → Select)→
  回测 → NAV / 确定性断言。

短路 ingestion/materialize(合成 ProviderBackedDataFeed + fundamental 闭包),
聚焦验证:多因子打分选股策略端到端可跑 + 因子桥接在回测链路可用 + 结果确定性。

参考: test_golden_e2e.py(ETF rotation)+ test_factor_backtest_integration(因子桥接)。
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta

import polars as pl
import pytest
from ditto_application.processes.execution.factor_bridge import (
    FactorBridge,
    build_factor_aware_bundle_builder,
)
from ditto_backtest.audit import ExecutionAuditCollector
from ditto_backtest.brokerage import BacktestBrokerage
from ditto_backtest.data_feed import ProviderBackedDataFeed, SnapshotProviders
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
from ditto_strategy.alpha.templates.stock_selection_trend import (
    StockSelectionTrendConfig,
    build_stock_selection_trend_pipeline,
)

INITIAL_CASH = 1_000_000.0
STRATEGY_ID = "stock-selection-golden"

# 5 只个股(模拟 A 股个股)
INSTRUMENT_IDS = [1, 2, 3, 4, 5]
ID_MAP: dict[str, InstrumentId] = {str(i): InstrumentId(i) for i in INSTRUMENT_IDS}


def _gen_trading_days(n: int) -> list[str]:
    """生成 n 个工作日(跳周末)从 2026-01-05 起。"""
    days: list[str] = []
    d = date(2026, 1, 5)
    while len(days) < n:
        if d.weekday() < 5:  # Mon-Fri
            days.append(d.isoformat())
        d += timedelta(days=1)
    return days


# 40 个交易日:momentum_1m 约需 20 日 lookback,回测取后 10 日(前 30 日作历史窗口,
# 足够 ts_* 时序表达式回看)。data_feed 覆盖全 40 日,EngineLoop 从 BACKTEST_START 跑。
ALL_DATES = _gen_trading_days(40)
BACKTEST_START = ALL_DATES[30]
BACKTEST_END = ALL_DATES[39]
BACKTEST_DATES = ALL_DATES[30:40]


# ---------------------------------------------------------------------------
# Synthetic Parquet Provider
# ---------------------------------------------------------------------------


class _SyntheticParquetProvider:
    """内存合成数据 Provider — 从 polars DataFrame 直接读取(同 ETF golden 模式)。"""

    def __init__(
        self,
        data: dict[InstrumentId, pl.DataFrame],
        id_map: dict[str, InstrumentId],
    ) -> None:
        self._data = data
        self._id_map = id_map

    def get_bars(self, query: BarQuery) -> pl.DataFrame:
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
            (pl.col("trade_date") >= query.start) & (pl.col("trade_date") <= query.end),
        )

    def get_schedule(self, start: str, end: str) -> pl.DataFrame:
        all_dates: set[str] = set()
        for df in self._data.values():
            all_dates.update(df["trade_date"].cast(pl.String).to_list())
        filtered = sorted(d for d in all_dates if start <= d <= end)
        return pl.DataFrame({"trade_date": filtered})

    def get_instruments(self, query: InstrumentQuery) -> pl.DataFrame:
        return pl.DataFrame()

    def get_factor(
        self,
        name: str,
        instruments: tuple[str, ...],
        start: str,
        end: str,
        asof: str | None = None,
    ) -> pl.DataFrame:
        return pl.DataFrame()


# ---------------------------------------------------------------------------
# Synthetic data generation
# ---------------------------------------------------------------------------


def _make_ohlcv(instrument_id: int, dates: list[str]) -> pl.DataFrame:
    """单标的 N 日 OHLCV,带差异化上升趋势(让 momentum_1m 产生区分信号)。"""
    n = len(dates)
    base = 10.0 + instrument_id * 5.0
    growth = 0.003 * instrument_id  # 不同增长率 → momentum 排序有区分
    closes = [round(base * (1 + growth) ** i, 4) for i in range(n)]
    return pl.DataFrame(
        {
            "trade_date": dates,
            "open": closes,
            "high": [round(c * 1.005, 4) for c in closes],
            "low": [round(c * 0.995, 4) for c in closes],
            "close": closes,
            "prev_close": [closes[0], *closes[:-1]],
            "volume": [1_000_000.0] * n,
            "amount": [round(c * 1_000_000.0, 4) for c in closes],
            "is_suspended": [False] * n,
        },
    )


def _generate_data() -> dict[InstrumentId, pl.DataFrame]:
    return {InstrumentId(i): _make_ohlcv(i, ALL_DATES) for i in INSTRUMENT_IDS}


def _fundamental_snapshot(
    instrument_ids: Sequence[InstrumentId],
    as_of_date: date,
) -> pl.DataFrame:
    """合成基本面截面:差异化 roe / eps(让 quality_roe / value_pe 产生区分信号)。"""
    rows = [
        {
            "instrument_id": int(iid),
            "roe": round(0.05 + 0.02 * int(iid), 4),  # 越大越优质
            "net_margin": 0.1,
            "eps": round(0.5 + 0.2 * int(iid), 4),  # 影响 pe_ratio = close/eps
        }
        for iid in instrument_ids
    ]
    return pl.DataFrame(rows)


def _build_data_feed(
    data: dict[InstrumentId, pl.DataFrame],
) -> ProviderBackedDataFeed:
    """构建 ProviderBackedDataFeed — 数据覆盖全 40 日,注入 fundamental 闭包。"""
    provider = _SyntheticParquetProvider(data=data, id_map=ID_MAP)
    return ProviderBackedDataFeed(
        provider=provider,
        tickers=tuple(ID_MAP.keys()),
        start_date=ALL_DATES[0],
        end_date=ALL_DATES[-1],
        id_map=ID_MAP,
        snapshot_providers=SnapshotProviders(fundamental=_fundamental_snapshot),
    )


def _build_engine(
    data_feed: ProviderBackedDataFeed,
    audit: ExecutionAuditCollector,
) -> EngineLoop:
    """组装选股回测引擎 — FactorBridge + stock_selection pipeline。"""
    bridge = FactorBridge()
    compiled = bridge.compile_and_validate(
        ("quality_roe", "value_pe", "momentum_1m"),
        (0.4, 0.3, 0.3),
    )
    input_bundle_builder = build_factor_aware_bundle_builder(
        bridge=bridge,
        compiled=compiled,
        data_feed=data_feed,
        strategy_id=STRATEGY_ID,
        run_id=STRATEGY_ID,
    )
    config = StockSelectionTrendConfig(
        signal_factors=("signal_value",),
        signal_weights=(1.0,),
        top_k=3,
        trend_threshold=0.0,
    )
    pipeline = StrategyPipeline(build_stock_selection_trend_pipeline(config))

    account = Account(
        cash=CashBook(available=INITIAL_CASH, settled=INITIAL_CASH, frozen=0.0),
    )
    fee_model = SimpleFeeModel()
    brokerage = BacktestBrokerage(
        account=account,
        order_book=OrderBook(journal=InMemoryOrderEventJournal()),
        model=BrokerageModel(fee_model=fee_model),
    )
    engine_config = EngineConfig(
        start_date=BACKTEST_START,
        end_date=BACKTEST_END,
        initial_cash=INITIAL_CASH,
        mode=EngineMode.BACKTEST,
        strategy_id=STRATEGY_ID,
        strategy_run_id=STRATEGY_ID,
    )
    clock = SimulatedClock(
        initial=datetime(
            int(BACKTEST_START[:4]),
            int(BACKTEST_START[5:7]),
            int(BACKTEST_START[8:10]),
            tzinfo=UTC,
        ),
    )
    synchronizer = BacktestSynchronizer(
        data_feed=data_feed,
        clock=clock,
        start_date=BACKTEST_START,
    )
    return EngineLoop(
        config=engine_config,
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
            input_bundle_builder=input_bundle_builder,
        ),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.fixture
def synthetic_data() -> dict[InstrumentId, pl.DataFrame]:
    return _generate_data()


@pytest.fixture
def synthetic_data_feed(
    synthetic_data: dict[InstrumentId, pl.DataFrame],
) -> ProviderBackedDataFeed:
    return _build_data_feed(synthetic_data)


@pytest.mark.integration
class TestStockSelectionGoldenE2E:
    """个股选股 Golden E2E — 因子桥接 + stock_selection 全链路回测验证。"""

    def test_full_pipeline_produces_nav(
        self,
        synthetic_data_feed: ProviderBackedDataFeed,
    ) -> None:
        """选股闭环:因子桥接 → stock_selection → 回测 → NAV 为正 + 报告完整。"""
        audit = ExecutionAuditCollector()
        engine = _build_engine(synthetic_data_feed, audit)
        result = engine.run()

        # 引擎成功返回
        assert result.run_id == STRATEGY_ID
        assert result.period == (BACKTEST_START, BACKTEST_END)
        assert not result.cancelled
        # NAV 为正(资金未清零)
        assert result.final_nav > 0, (
            f"final_nav should be positive, got {result.final_nav}"
        )
        # 报告构建成功
        report = build_report(audit, run_id=result.run_id)
        assert isinstance(report, BacktestReport)
        assert len(report.nav_series) == len(BACKTEST_DATES), (
            f"NAV series length {len(report.nav_series)} "
            f"should match backtest days {len(BACKTEST_DATES)}"
        )
        for _date_str, nav in report.nav_series:
            assert nav > 0, f"NAV should be positive, got {nav}"
        # alpha 统计存在
        assert isinstance(report.alpha_stats.sharpe_ratio, float)
        assert isinstance(report.alpha_stats.max_drawdown, float)

    def test_engine_result_is_deterministic(
        self,
        synthetic_data: dict[InstrumentId, pl.DataFrame],
    ) -> None:
        """相同输入两次跑 final_nav 相等 — 确定性基线。"""
        results: list[float] = []
        for _ in range(2):
            data_feed = _build_data_feed(synthetic_data)
            audit = ExecutionAuditCollector()
            engine = _build_engine(data_feed, audit)
            result = engine.run()
            results.append(result.final_nav)

        assert results[0] == results[1], (
            f"Deterministic check failed: {results[0]} != {results[1]}"
        )
