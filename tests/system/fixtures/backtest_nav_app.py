"""Real engine backtest NAV fixture over a seeded isolated market store.

The chart page under test reads everything through the production API:
- NAV/trade/audit artifacts come from a real EngineLoop run (the same
  synthetic-provider golden E2E assembly), persisted through the production
  ``persist_audit``/``persist_artifact`` path into the fixture state.
- The benchmark NAV series is derived server-side from the run's
  ``config_json`` benchmark_id over the seeded benchmark bars (with a
  deliberate 5-day hole to exercise the honest gap path).
"""

from __future__ import annotations

import importlib
import os
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import orjson
import polars as pl
from ditto_application.processes.execution.backtest_audit import (
    ArtifactPersistConfig,
    ArtifactPersistContext,
    persist_artifact,
    persist_audit,
)
from ditto_application.processes.execution.strategy_input import (
    write_backtest_artifacts,
)
from ditto_apps.registry.container import make_app_container
from ditto_apps.registry.fresh_runtime import create_fresh_runtime
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
from ditto_backtest.statistics import build_report
from ditto_backtest.synchronizer import BacktestSynchronizer
from ditto_data.models.metadata import InstrumentRegistration
from ditto_data.provider import BarQuery
from ditto_data.storage.metadata.instrument.instrument_writer import InstrumentWriter
from ditto_execution.audit.execution_audit_service import ExecutionAuditService
from ditto_execution.orders.book import OrderBook
from ditto_execution.orders.journal import InMemoryOrderEventJournal
from ditto_execution.planner import SimpleExecutionPlanner
from ditto_execution.reality import SimpleFeeModel
from ditto_kernel.clock import SimulatedClock
from ditto_kernel.identity import InstrumentId
from ditto_platform.foundation import (
    OnDuplicate,
    ParquetStore,
    SQLiteClient,
    SQLitePool,
)
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
from ditto_strategy.storage.sqlite.services.strategy_artifact_service import (
    StrategyArtifactService,
)
from ditto_strategy.storage.sqlite.services.strategy_run_service import (
    StrategyRunLifecycleStore,
)

if os.environ.get("DITTO_ENVIRONMENT") != "testing":
    raise RuntimeError("backtest nav fixture requires testing mode")
_root = Path(os.environ["DITTO_ACCEPTANCE_DATA_ROOT"]).resolve()
if not _root.is_relative_to(Path("/tmp").resolve()):
    raise RuntimeError("backtest nav fixture requires isolated /tmp state")
_state = _root / "state"
os.environ.update(
    {
        "DITTO_STATE_ROOT": str(_state),
        "SQLITE_PATH": str(_state / "metadata/metadata.sqlite"),
        "ENVIRONMENT": "testing",
    }
)

RUN_WITH_BENCHMARK = "sys-fx-nav-001"
RUN_NO_BENCHMARK = "sys-fx-nav-002"
BENCH_ID = 2_001_003
UNIVERSE_IDS = [2_001_001, 2_001_002]
INITIAL_CASH = 1_000_000.0

# 固定日历：2026-01-05 起 60 个交易日（跳过周末）。
TRADING_DAYS: list[date] = []
_cursor = date(2026, 1, 5)
while len(TRADING_DAYS) < 60:
    if _cursor.weekday() < 5:
        TRADING_DAYS.append(_cursor)
    _cursor += timedelta(days=1)
START_DATE = TRADING_DAYS[0].isoformat()
END_DATE = TRADING_DAYS[-1].isoformat()
# 基准行情挖空 5 个交易日（索引 30–34）→ benchmark-partial 断口路径。
BENCHMARK_HOLE = set(range(30, 35))


def _close_series(base: float, *, hump: bool) -> list[float]:
    """确定性收盘价：先扬后抑再修复，保证策略净值出现真实回撤区间."""
    closes: list[float] = []
    for index in range(len(TRADING_DAYS)):
        if hump and index >= 24 and index <= 38:
            # 回撤段：−12% 水下，之后修复
            drift = -0.005 * (index - 24)
        else:
            drift = 0.004 if index % 3 else 0.001
        previous = closes[-1] if closes else base
        closes.append(round(previous * (1 + drift), 4))
    return closes


def _bars_frame(instrument_id: int, closes: list[float]) -> pl.DataFrame:
    rows = []
    previous_close = closes[0]
    for index, day in enumerate(TRADING_DAYS):
        close = closes[index]
        open_ = round(previous_close + (close - previous_close) * 0.3, 4)
        rows.append(
            {
                "instrument_id": instrument_id,
                "trade_date": day.isoformat(),
                "open": open_,
                "high": round(max(open_, close) * 1.01, 4),
                "low": round(min(open_, close) * 0.99, 4),
                "close": close,
                "pre_close": previous_close,
                "volume": 1_200_000 + (index % 7) * 35_000,
                "amount": round(close * 1_200_000, 2),
                "turnover_rate": 0.83,
            }
        )
        previous_close = close
    return pl.DataFrame(rows)


def _benchmark_frame() -> pl.DataFrame:
    closes = _close_series(4.0, hump=False)
    rows = [
        {
            "instrument_id": BENCH_ID,
            "trade_date": day.isoformat(),
            "open": close,
            "high": round(close * 1.01, 4),
            "low": round(close * 0.99, 4),
            "close": close,
            "pre_close": closes[index - 1] if index else close,
            "volume": 9_000_000,
            "amount": round(close * 9_000_000, 2),
            "turnover_rate": 0.5,
        }
        for index, (day, close) in enumerate(zip(TRADING_DAYS, closes, strict=True))
        # 挖空洞内交易日：基准缺失区间必须以断口呈现，不得插值。
        if index not in BENCHMARK_HOLE
    ]
    return pl.DataFrame(rows)


class _SeededStoreProvider:
    """从已播种 parquet 读回 bar 数据的 Provider（引擎与 API 读同一份真相）."""

    def __init__(self, frames: dict[InstrumentId, pl.DataFrame]) -> None:
        self._frames = frames

    def get_bars(self, query: BarQuery) -> pl.DataFrame:
        frames = [
            frame.with_columns(instrument_id=pl.lit(int(instrument_id)))
            for ticker, instrument_id in _ID_MAP.items()
            if ticker in query.instruments
            and (frame := self._frames.get(instrument_id)) is not None
        ]
        if not frames:
            return pl.DataFrame()
        merged = pl.concat(frames, how="diagonal")
        return merged.filter(
            (pl.col("trade_date") >= query.start) & (pl.col("trade_date") <= query.end),
        )

    def get_schedule(self, start: str, end: str) -> pl.DataFrame:
        dates = sorted(
            {
                trade_date
                for frame in self._frames.values()
                for trade_date in frame["trade_date"].cast(pl.String).to_list()
                if start <= trade_date <= end
            },
        )
        return pl.DataFrame({"trade_date": dates})


_ID_MAP: dict[str, InstrumentId] = {
    str(instrument_id): InstrumentId(instrument_id) for instrument_id in UNIVERSE_IDS
}


def _run_engine(run_id: str, provider: _SeededStoreProvider) -> object:
    """跑一次真实回测引擎（golden E2E 同款装配），返回 BacktestReport."""
    account = Account(
        cash=CashBook(available=INITIAL_CASH, settled=INITIAL_CASH, frozen=0.0),
    )
    fee_model = SimpleFeeModel()
    audit = ExecutionAuditCollector()
    data_feed = ProviderBackedDataFeed(
        provider=provider,
        tickers=tuple(_ID_MAP.keys()),
        start_date=START_DATE,
        end_date=END_DATE,
        id_map=_ID_MAP,
    )
    config = EngineConfig(
        start_date=START_DATE,
        end_date=END_DATE,
        initial_cash=INITIAL_CASH,
        spec_hash="e" * 64,
        base_spec_hash="e" * 64,
        parameter_hash="4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
        effective_parameters=(),
        research_snapshot_id=None,
        research_snapshot_manifest_hash=None,
        mode=EngineMode.BACKTEST,
        strategy_id="sys-fx-etf-rotation",
        strategy_run_id=run_id,
    )
    engine = EngineLoop(
        config=config,
        pipeline=StrategyPipeline(
            build_etf_rotation_pipeline(ETFRotationConfig(top_k=2, cash_target=0.0)),
        ),
        planner=SimpleExecutionPlanner(),
        brokerage=BacktestBrokerage(
            account=account,
            order_book=OrderBook(journal=InMemoryOrderEventJournal()),
            model=BrokerageModel(fee_model=fee_model),
        ),
        pre_trade_check=CompositePreTradeCheck(
            checks=(LotSizeCheck(), BuyingPowerCheck()),
        ),
        data_feed=data_feed,
        synchronizer=BacktestSynchronizer(
            data_feed=data_feed,
            clock=SimulatedClock(
                initial=datetime(
                    int(START_DATE[:4]),
                    int(START_DATE[5:7]),
                    int(START_DATE[8:10]),
                    tzinfo=UTC,
                ),
            ),
            start_date=START_DATE,
        ),
        options=EngineOptions(fee_model=fee_model, audit_collector=audit),
    )
    result = engine.run()
    if result.cancelled or len(result.skipped_dates) > 0:
        raise RuntimeError("fixture engine run did not complete every session")
    report = build_report(audit, run_id=run_id)
    if not report.nav_series or report.final_nav <= 0:
        raise RuntimeError("fixture engine run produced no usable NAV series")
    return report


def _seed_market() -> dict[InstrumentId, pl.DataFrame]:
    create_fresh_runtime(_state)
    pool = SQLitePool(str(_state / "metadata/metadata.sqlite"))
    client = SQLiteClient(pool)
    writer = InstrumentWriter(client=client, cache=None)
    registrations = [
        (UNIVERSE_IDS[0], "510300.SH", "510300", "沪深300ETF-回测验收", "etf"),
        (UNIVERSE_IDS[1], "510500.SH", "510500", "中证500ETF-回测验收", "etf"),
        (BENCH_ID, "159919.SZ", "159919", "沪深300ETF-基准验收", "etf"),
    ]
    for instrument_id, source_ticker, ticker, name, asset_class in registrations:
        writer.register(
            instrument_id,
            InstrumentRegistration(
                source_ticker=source_ticker,
                ticker=ticker,
                name=name,
                exchange="SSE" if source_ticker.endswith(".SH") else "SZSE",
                asset_class=asset_class,
                list_date="2012-05-28",
            ),
        )
    frames = {
        InstrumentId(UNIVERSE_IDS[0]): _bars_frame(
            UNIVERSE_IDS[0],
            _close_series(4.0, hump=True),
        ),
        InstrumentId(UNIVERSE_IDS[1]): _bars_frame(
            UNIVERSE_IDS[1],
            _close_series(6.0, hump=False),
        ),
    }
    store = ParquetStore(
        _state,
        key_columns=("instrument_id", "trade_date"),
        date_column="trade_date",
        instrument_column="instrument_id",
    )
    store.write(
        "market/etf/bars",
        pl.concat([*frames.values(), _benchmark_frame()]),
        OnDuplicate.ERROR.value,
        year=2026,
    )
    # 从已写入的 parquet 读回，保证引擎与 API 查询看到同一份数据；
    # trade_date 统一转回字符串（引擎 Provider 与 golden E2E 同一口径）。
    seeded = store.read("market/etf/bars").with_columns(
        pl.col("trade_date").cast(pl.String),
    )
    return {
        instrument_id: seeded.filter(
            pl.col("instrument_id") == int(instrument_id),
        ).drop("instrument_id")
        for instrument_id in frames
    }


def _persist_run(
    *,
    run_id: str,
    report: object,
    benchmark_id: int | None,
    run_service: StrategyRunLifecycleStore,
    audit_service: ExecutionAuditService,
    artifact_service: StrategyArtifactService,
) -> None:
    config_json = orjson.dumps(
        {
            "start_date": START_DATE,
            "end_date": END_DATE,
            "initial_cash": INITIAL_CASH,
            "benchmark_id": benchmark_id,
            "strategy_version": "1",
        },
    ).decode()
    run_service.create_run(
        run_id=run_id,
        strategy_id="sys-fx-etf-rotation",
        strategy_version="1",
        mode="backtest",
        parent_run_id="",
        config_json=config_json,
    )
    run_service.mark_running(run_id)
    run_service.mark_completed(run_id)
    persist_audit(run_id, report, audit_service)
    persist_artifact(
        ArtifactPersistContext(run_id=run_id, report=report),
        ArtifactPersistConfig(
            strategy_id="sys-fx-etf-rotation",
            strategy_version="1",
            initial_cash=INITIAL_CASH,
            rebalance_freq="daily",
            artifact_service=artifact_service,
            write_fn=write_backtest_artifacts,
            base_spec_hash="e" * 64,
            spec_hash="e" * 64,
            parameter_hash="4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
            effective_parameters=(),
            research_snapshot_id=None,
            research_snapshot_manifest_hash=None,
            artifact_dir=str(_root / "artifacts"),
            benchmark_id=InstrumentId(benchmark_id) if benchmark_id else None,
        ),
    )


def _seed() -> None:
    frames = _seed_market()
    provider = _SeededStoreProvider(frames)
    container = make_app_container()
    try:
        run_service = container.get(StrategyRunLifecycleStore)
        audit_service = container.get(ExecutionAuditService)
        artifact_service = container.get(StrategyArtifactService)
        report_with_bench = _run_engine(RUN_WITH_BENCHMARK, provider)
        _persist_run(
            run_id=RUN_WITH_BENCHMARK,
            report=report_with_bench,
            benchmark_id=BENCH_ID,
            run_service=run_service,
            audit_service=audit_service,
            artifact_service=artifact_service,
        )
        report_without_bench = _run_engine(RUN_NO_BENCHMARK, provider)
        _persist_run(
            run_id=RUN_NO_BENCHMARK,
            report=report_without_bench,
            benchmark_id=None,
            run_service=run_service,
            audit_service=audit_service,
            artifact_service=artifact_service,
        )
    finally:
        container.close()


_seed()

app = importlib.import_module("ditto_apps.main").app
