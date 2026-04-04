"""
策略运行编排服务 — Process 模块.

合并自 ditto_interfaces.services.strategy 中的:
  - facade.py
  - backtest_service.py
  - strategy_run_service.py
  - lifecycle.py
  - artifact_writer.py
  - market_data_feed.py
  - input_assembler.py
"""

from __future__ import annotations

import dataclasses
import tempfile
import uuid
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from datetime import datetime as _dt_datetime
from enum import StrEnum
from pathlib import Path
from typing import Protocol, runtime_checkable

import orjson
import polars as pl
from ditto_data.models.strategy import ArtifactKind, StrategyArtifactRecord
from ditto_data.models.strategy_audit import (
    PreTradeDecisionPayload,
    RiskScanPayload,
)
from ditto_data.services.audit import ExecutionAuditService
from ditto_data.services.market_service import MarketService
from ditto_data.services.metadata_service import MetadataService
from ditto_data.services.strategy.strategy_artifact_service import (
    StrategyArtifactService,
)
from ditto_engine.alpha.context import StrategyContext
from ditto_engine.alpha.models import TargetPortfolio
from ditto_engine.alpha.pipeline import StrategyInputBundle, StrategyPipeline
from ditto_engine.alpha.specs import StrategySpec
from ditto_engine.alpha.validation import validate_spec_params
from ditto_engine.backtest.audit import ExecutionAuditCollector
from ditto_engine.backtest.data_feed import DataFeed, Slice
from ditto_engine.backtest.engine import (
    EngineConfig,
    EngineLoop,
    EngineMode,
    EngineOptions,
)
from ditto_engine.backtest.manifest import RunManifest, serialize_manifest
from ditto_engine.backtest.statistics import (
    BacktestReport,
    PreTradeDecisionRecord,
    RiskScanRecord,
    build_report,
)
from ditto_engine.execution.brokerage import Brokerage
from ditto_engine.execution.planner import ExecutionPlanner
from ditto_engine.execution.reality import FeeModel
from ditto_engine.execution.reality.market import MarketSnapshot
from ditto_engine.execution.rules import InstrumentRuleProvider
from ditto_engine.risk.post_trade import PostTradeRiskGuard
from ditto_engine.risk.pre_trade import CompositePreTradeCheck
from ditto_infra.foundation.util.io import atomic_bytes_write, atomic_write
from ditto_kernel.enums import AssetClass
from ditto_kernel.identity import InstrumentId

from ditto_app.process.backtest_serialization import serialize_report

__all__ = [
    "BacktestService",
    "BacktestServiceConfig",
    "BacktestServiceOptions",
    "MarketServiceDataFeed",
    "MarketServiceDataFeedConfig",
    "RunLifecycleService",
    "StrategyFacade",
    "StrategyInputAssembler",
    "StrategyRunMode",
    "StrategyRunResult",
    "StrategyRunService",
    "StrategyRunServiceConfig",
    "enrich_record_with_symbol",
    "write_backtest_artifacts",
]


# ===========================================================================
# lifecycle.py — 策略运行生命周期协议
# ===========================================================================


@runtime_checkable
class RunLifecycleService(Protocol):
    """策略运行生命周期协议。"""

    def create_run(
        self,
        run_id: str,
        strategy_id: str,
        strategy_version: str = "",
        mode: str = "backtest",
    ) -> None:
        """创建运行记录。"""
        ...

    def mark_running(self, run_id: str) -> bool:
        """标记运行为 running。"""
        ...

    def mark_completed(self, run_id: str) -> bool:
        """标记运行为 completed。"""
        ...

    def mark_failed(self, run_id: str, error_message: str = "") -> bool:
        """标记运行为 failed。"""
        ...


# ===========================================================================
# artifact_writer.py — 将回测产物序列化到磁盘
# ===========================================================================


_AuditRecord = RiskScanRecord | PreTradeDecisionRecord


def enrich_record_with_symbol(
    record: _AuditRecord,
    display_map: dict[InstrumentId, str],
) -> dict[str, object]:
    """
    将审计记录转为 dict 并注入 ``instrument_symbol`` 展示字段。

    如果 ``display_map`` 中无对应映射，则 ``instrument_symbol`` 值为空字符串。
    """
    d: dict[str, object] = dataclasses.asdict(record)
    iid = record.instrument_id
    d["instrument_symbol"] = display_map.get(iid, "") if iid is not None else ""
    return d


def write_backtest_artifacts(
    report: BacktestReport,
    output_dir: Path | None = None,
    manifest: RunManifest | None = None,
    display_map: dict[InstrumentId, str] | None = None,
) -> dict[str, Path]:
    """
    将 BacktestReport 序列化到磁盘，返回产物文件路径映射.

    Args:
        report: 回测报告.
        output_dir: 输出目录 (None = 使用系统临时目录).
        manifest: 运行清单（如提供则写出 manifest.json 并回填 artifacts）.
        display_map: InstrumentId → standard_ticker 映射，用于在审计日志中注入
            ``instrument_symbol`` 展示字段.

    Returns:
        产物类型 → 文件路径的映射，至少包含 ``backtest_report`` 条目.

    """
    if output_dir is None:
        output_dir = Path(tempfile.gettempdir()) / "ditto" / report.run_id

    output_dir.mkdir(parents=True, exist_ok=True)

    # 序列化报告（纯计算在 Engine）+ 文件写入（App 层职责）
    json_bytes, parquet_tables = serialize_report(report)
    atomic_bytes_write(json_bytes, output_dir / "backtest_report.json")
    for name, df in parquet_tables.items():
        atomic_write(df, output_dir / f"{name}.parquet")

    _write_audit_json(
        output_dir / "risk_log.json",
        report.risk_log,
        display_map,
    )
    _write_audit_json(
        output_dir / "pre_trade_log.json",
        report.pre_trade_log,
        display_map,
    )

    if manifest is not None:
        manifest_path = output_dir / "manifest.json"
        existing = tuple(
            sorted(child.name for child in output_dir.iterdir() if child.is_file())
        )
        artifact_refs = (*existing, "manifest.json")
        finalized_manifest = replace(
            manifest,
            artifacts=tuple(sorted(artifact_refs)),
        )
        atomic_bytes_write(
            serialize_manifest(finalized_manifest).encode("utf-8"),
            manifest_path,
        )

    return _collect_written_artifacts(output_dir)


def _write_audit_json(
    path: Path,
    records: tuple[_AuditRecord, ...],
    display_map: dict[InstrumentId, str] | None,
) -> None:
    """将非空审计记录写为 JSON artifact，可选注入 instrument_symbol。"""
    if not records:
        return
    if display_map is not None:
        payload = [enrich_record_with_symbol(r, display_map) for r in records]
    else:
        payload = [dataclasses.asdict(r) for r in records]
    atomic_bytes_write(
        orjson.dumps(payload, option=orjson.OPT_INDENT_2),
        path,
    )


def _collect_written_artifacts(output_dir: Path) -> dict[str, Path]:
    """收集输出目录中的 artifact 文件。"""
    return {child.stem: child for child in output_dir.iterdir() if child.is_file()}


# ===========================================================================
# input_assembler.py — 从 Slice 组装 StrategyInputBundle
# ===========================================================================


class StrategyInputAssembler:
    """
    从 Slice 组装 StrategyInputBundle.

    封装 strategy_id / run_id / parameters 等策略级别配置，
    ``assemble()`` 接收日期级别的 Slice 数据并产出完整的 bundle。

    可复用于 BACKTEST / RESEARCH / RECOMMENDATION 等模式。

    Parameters
    ----------
        strategy_id: 策略 ID
        run_id: 运行 ID
        parameters: 参数覆盖

    """

    def __init__(
        self,
        strategy_id: str = "default",
        run_id: str = "",
        parameters: dict[str, object] | None = None,
    ) -> None:
        self._strategy_id = strategy_id
        self._run_id = run_id
        self._parameters = parameters or {}

    @property
    def strategy_id(self) -> str:
        """策略 ID。"""
        return self._strategy_id

    @property
    def run_id(self) -> str:
        """运行 ID。"""
        return self._run_id

    @property
    def parameters(self) -> dict[str, object]:
        """参数覆盖。"""
        return dict(self._parameters)

    def assemble(
        self,
        trade_date: str,
        slice_: Slice,
        *,
        valid_until: str | None = None,
        run_id: str | None = None,
    ) -> StrategyInputBundle:
        """
        从 Slice 构建 StrategyInputBundle.

        从 bars 中提取 market_data (OHLCV) 和 signal_values
        (动量信号: close / prev_close - 1)。

        Args:
            trade_date: 交易日期 (YYYY-MM-DD)
            slice_: 当日市场数据切片
            valid_until: 信号有效期截止日期 (YYYY-MM-DD)，若早于
                trade_date 则视为过期，bundle 中 signal_values 为 None
            run_id: 覆盖默认 run_id，用于在运行前固化真实 run_id

        Returns:
            包含标的列表、市场数据、信号值的 StrategyInputBundle

        """
        instrument_ids = list(slice_.bars.keys())
        instruments = pl.DataFrame({"instrument_id": instrument_ids})

        market_rows: list[dict[str, object]] = []
        signal_rows: list[dict[str, object]] = []

        for iid, bar in slice_.bars.items():
            market_rows.append(
                {
                    "instrument_id": iid,
                    "open": bar.open,
                    "high": bar.high,
                    "low": bar.low,
                    "close": bar.close,
                    "volume": bar.volume,
                }
            )
            signal_rows.append(
                {
                    "instrument_id": iid,
                    "signal_value": (
                        (bar.close / bar.prev_close - 1.0) if bar.prev_close else 0.0
                    ),
                }
            )

        # 信号过期检查：valid_until < trade_date 时信号无效
        signals_expired = valid_until is not None and valid_until < trade_date

        return StrategyInputBundle(
            trade_date=trade_date,
            strategy_id=self._strategy_id,
            run_id=self._run_id if run_id is None else run_id,
            instruments=instruments,
            market_data=pl.DataFrame(market_rows),
            signal_values=None if signals_expired else pl.DataFrame(signal_rows),
            parameters=self._parameters,
            benchmark_close=slice_.benchmark_close,
        )


# ===========================================================================
# market_data_feed.py — 基于 Data Metadata/MarketService 的 DataFeed 适配器
# ===========================================================================


@dataclass(frozen=True)
class MarketServiceDataFeedConfig:
    """市场服务 DataFeed 的静态装配参数。"""

    universe_id: str
    asset_class: str
    start_date: str
    end_date: str
    benchmark_id: InstrumentId | None = None
    source: str = "tushare"


class MarketServiceDataFeed:
    """将 Data 市场数据服务适配为 Core ``DataFeed``。"""

    def __init__(
        self,
        *,
        metadata_service: MetadataService,
        market_service: MarketService,
        config: MarketServiceDataFeedConfig,
    ) -> None:
        self._metadata_service = metadata_service
        self._market_service = market_service
        self._config = config
        self._asset_class = AssetClass(config.asset_class)
        self._trading_days: list[str] | None = None
        self._bars_by_date: dict[str, dict[InstrumentId, MarketSnapshot]] | None = None
        self._benchmark_close_by_date: dict[str, float] | None = None
        self._display_map: dict[InstrumentId, str] = {}

    def trading_days(self) -> list[str]:
        """返回回测区间内交易日列表。"""
        self._ensure_loaded()
        return list(self._trading_days or [])

    @property
    def display_map(self) -> dict[InstrumentId, str]:
        """返回 InstrumentId → standard_ticker 映射。"""
        self._ensure_loaded()
        return dict(self._display_map)

    def get_slice(self, date: str) -> Slice:
        """返回指定日期的市场切片。"""
        self._ensure_loaded()
        step_time = _dt_datetime.strptime(date, "%Y-%m-%d").replace(
            hour=15,
            minute=0,
            second=0,
        )
        bars = dict((self._bars_by_date or {}).get(date, {}))
        benchmark_close = (self._benchmark_close_by_date or {}).get(date)
        return Slice(
            trade_date=date,
            step_time=step_time,
            bars=bars,
            benchmark_close=benchmark_close,
        )

    def _ensure_loaded(self) -> None:
        if self._trading_days is not None:
            return

        calendar_df = self._metadata_service.list_calendar_range(
            self._config.start_date,
            self._config.end_date,
            only_open=True,
        )
        trading_days = self._extract_trading_days(calendar_df)
        query_start = self._resolve_query_start(calendar_df)

        universe_ids = self._metadata_service.get_universe(
            self._config.universe_id,
            asof=self._config.start_date,
        )
        display_map = self._build_display_map(universe_ids)
        bars_df = self._load_universe_bars(universe_ids, query_start)

        if not trading_days:
            trading_days = self._extract_trading_days_from_bars(bars_df)

        self._trading_days = trading_days
        self._display_map = display_map
        self._bars_by_date = self._build_bars_by_date(
            bars_df,
            trading_days=set(trading_days),
        )
        self._benchmark_close_by_date = self._load_benchmark_close_map(
            query_start,
            trading_days=set(trading_days),
        )

    def _resolve_query_start(self, calendar_df: pl.DataFrame) -> str:
        if "prev_trade_date" not in calendar_df.columns or calendar_df.is_empty():
            return self._config.start_date
        prev_trade_dates = [
            value
            for value in calendar_df.select(pl.col("prev_trade_date").cast(pl.String))
            .to_series()
            .to_list()
            if value is not None
        ]
        if not prev_trade_dates:
            return self._config.start_date
        return prev_trade_dates[0]

    def _extract_trading_days(self, calendar_df: pl.DataFrame) -> list[str]:
        if "trade_date" not in calendar_df.columns or calendar_df.is_empty():
            return []
        dates = [
            value
            for value in calendar_df.select(pl.col("trade_date").cast(pl.String))
            .to_series()
            .to_list()
            if value is not None
        ]
        return sorted(dates)

    def _extract_trading_days_from_bars(self, bars_df: pl.DataFrame) -> list[str]:
        if bars_df.is_empty() or "trade_date" not in bars_df.columns:
            return []
        dates = [
            value
            for value in bars_df.select(pl.col("trade_date").cast(pl.String).unique())
            .to_series()
            .to_list()
            if value is not None
            and self._config.start_date <= value <= self._config.end_date
        ]
        return sorted(dates)

    def _build_display_map(self, instrument_ids: list[int]) -> dict[InstrumentId, str]:
        """构建 InstrumentId → standard_ticker 映射。"""
        display_map: dict[InstrumentId, str] = {}
        for iid in instrument_ids:
            instrument_id = InstrumentId(iid)
            instrument = self._metadata_service.get_instrument(iid)
            if instrument is not None:
                ticker = instrument.get("ticker", str(iid))
                exchange = instrument.get("exchange", "")
                key = f"{ticker}.{exchange}" if exchange else str(iid)
                display_map[instrument_id] = key
            else:
                display_map[instrument_id] = str(iid)
        return display_map

    def _load_universe_bars(
        self,
        instrument_ids: list[int],
        start_date: str,
    ) -> pl.DataFrame:
        if not instrument_ids:
            return pl.DataFrame()
        return self._market_service.list_bars(
            instrument_ids,
            start=start_date,
            end=self._config.end_date,
            asset_class=self._asset_class.value,
        )

    def _build_bars_by_date(
        self,
        bars_df: pl.DataFrame,
        *,
        trading_days: set[str],
    ) -> dict[str, dict[InstrumentId, MarketSnapshot]]:
        if bars_df.is_empty():
            return {}

        prepared = self._prepare_bars_frame(bars_df)
        bars_by_date: dict[str, dict[InstrumentId, MarketSnapshot]] = {}
        for row in prepared.to_dicts():
            trade_date = self._read_str(row, "trade_date")
            if trade_date not in trading_days:
                continue
            instrument_id = InstrumentId(self._read_int(row, "instrument_id"))
            date_bucket = bars_by_date.setdefault(trade_date, {})
            date_bucket[instrument_id] = self._row_to_snapshot(instrument_id, row)
        return bars_by_date

    def _load_benchmark_close_map(
        self,
        start_date: str,
        *,
        trading_days: set[str],
    ) -> dict[str, float]:
        if self._config.benchmark_id is None:
            return {}

        benchmark_instrument_id = int(self._config.benchmark_id)
        benchmark_asset_class = self._resolve_benchmark_asset_class(
            benchmark_instrument_id,
        )
        benchmark_df = self._market_service.list_bars(
            [benchmark_instrument_id],
            start=start_date,
            end=self._config.end_date,
            asset_class=benchmark_asset_class.value,
        )
        if benchmark_df.is_empty():
            return {}

        prepared = self._prepare_bars_frame(benchmark_df)
        close_map: dict[str, float] = {}
        for row in prepared.to_dicts():
            trade_date = self._read_str(row, "trade_date")
            if trade_date not in trading_days:
                continue
            close_map[trade_date] = self._read_float(row.get("close"))
        return close_map

    def _resolve_benchmark_asset_class(self, instrument_id: int) -> AssetClass:
        instrument = self._metadata_service.get_instrument(instrument_id)
        if instrument is None:
            return AssetClass.INDEX
        asset_class = instrument.get("asset_class")
        if not isinstance(asset_class, str):
            return AssetClass.INDEX
        try:
            return AssetClass(asset_class)
        except ValueError:
            return AssetClass.INDEX

    def _prepare_bars_frame(self, bars_df: pl.DataFrame) -> pl.DataFrame:
        prepared = bars_df.with_columns(pl.col("trade_date").cast(pl.String)).sort(
            ["instrument_id", "trade_date"],
        )
        return prepared.with_columns(
            pl.col("close").shift(1).over("instrument_id").alias("prev_close"),
        ).with_columns(
            pl.col("prev_close").fill_null(pl.col("close")),
        )

    def _row_to_snapshot(
        self,
        instrument_id: InstrumentId,
        row: dict[str, object],
    ) -> MarketSnapshot:
        close = self._read_float(row.get("close"))
        amount = row.get("amount")
        if amount is None:
            amount_value = close * self._read_float(row.get("volume"))
        else:
            amount_value = self._read_float(amount)
        return MarketSnapshot(
            trade_date=self._read_str(row, "trade_date"),
            instrument_id=instrument_id,
            open=self._read_float(row.get("open")),
            high=self._read_float(row.get("high")),
            low=self._read_float(row.get("low")),
            close=close,
            prev_close=self._read_float(row.get("prev_close"), default=close),
            volume=self._read_float(row.get("volume")),
            amount=amount_value,
            is_suspended=bool(row.get("is_suspended", False)),
            limit_up=self._read_optional_float(row.get("limit_up")),
            limit_down=self._read_optional_float(row.get("limit_down")),
            avg_volume_20d=self._read_optional_float(row.get("avg_volume_20d")),
        )

    @staticmethod
    def _read_str(row: dict[str, object], key: str) -> str:
        value = row.get(key)
        if isinstance(value, str):
            return value
        if value is None:
            msg = f"缺失字段: {key}"
            raise ValueError(msg)
        return str(value)

    @staticmethod
    def _read_int(row: dict[str, object], key: str) -> int:
        value = row.get(key)
        if isinstance(value, int):
            return value
        if value is None:
            msg = f"缺失字段: {key}"
            raise ValueError(msg)
        return int(str(value))

    @staticmethod
    def _read_float(value: object, *, default: float = 0.0) -> float:
        if value is None:
            return default
        if isinstance(value, bool):
            return float(value)
        if isinstance(value, int | float):
            return float(value)
        return float(str(value))

    @staticmethod
    def _read_optional_float(value: object) -> float | None:
        if value is None:
            return None
        return MarketServiceDataFeed._read_float(value)


# ===========================================================================
# backtest_service.py — Port 层回测编排服务
# ===========================================================================


@dataclass(frozen=True)
class BacktestServiceConfig:
    """
    BacktestService 配置 — frozen, 运行前确定.

    Attributes:
        strategy_id: 策略 ID
        strategy_version: 策略版本
        run_id: 运行 ID (空字符串时由服务预生成并传给引擎)
        start_date: 起始日期 (YYYY-MM-DD)
        end_date: 结束日期 (YYYY-MM-DD)
        initial_cash: 初始资金
        benchmark_id: 基准标的 ID (None = 无基准)
        parameter_overrides: 参数覆盖列表
        rebalance_freq: 调仓频率 (daily / weekly / monthly)
        engine_version: 引擎版本号

    """

    strategy_id: str = "default"
    strategy_version: str = ""
    run_id: str = ""
    start_date: str = ""
    end_date: str = ""
    initial_cash: float = 1_000_000.0
    benchmark_id: InstrumentId | None = None
    parameter_overrides: tuple[str, ...] = ()
    rebalance_freq: str = "daily"
    engine_version: str = "0.1.0"


@dataclass(frozen=True)
class BacktestServiceOptions:
    """
    BacktestService 可选组件 — 将可选依赖打包以减少构造参数数量.

    Attributes:
        fee_model: 手续费模型 (用于 PreTrade 估算)
        rule_provider: 三层规则提供者 (用于 Planner 涨跌停/lot_size 检查)
        post_trade_guard: PostTrade 风控扫描器
        audit_service: 审计日志持久化服务
        artifact_service: 策略产物持久化服务
        artifact_dir: 回测产物序列化输出目录 (None = 使用默认临时目录)
        run_service: 策略运行生命周期服务 (None = 跳过生命周期管理)

    """

    fee_model: FeeModel | None = None
    rule_provider: InstrumentRuleProvider | None = None
    post_trade_guard: PostTradeRiskGuard | None = None
    audit_service: ExecutionAuditService | None = None
    artifact_service: StrategyArtifactService | None = None
    artifact_dir: str | None = None
    display_map: dict[InstrumentId, str] | None = None
    run_service: RunLifecycleService | None = None


class BacktestService:
    """
    Port 层回测编排服务.

    接收 EngineLoop 的构造参数 + 可选持久化服务，内部管理
    ExecutionAuditCollector 生命周期，编排完整回测流程:

    1. (可选) 创建策略运行记录
    2. 创建 ExecutionAuditCollector
    3. 构建 EngineConfig + EngineOptions
    4. 构造 EngineLoop 并运行
    5. 从 collector 构建 BacktestReport
    6. 持久化审计日志 + 策略产物
    7. (可选) 更新运行状态 (completed / failed)

    Parameters
    ----------
        config: 服务配置
        pipeline: 策略 Pipeline
        planner: 执行计划器
        brokerage: 经纪商
        pre_trade_check: 组合 PreTrade 校验
        data_feed: 市场数据源
        options: 可选组件 (费率模型、规则提供者、风控、持久化服务)

    """

    def __init__(
        self,
        config: BacktestServiceConfig,
        pipeline: StrategyPipeline,
        planner: ExecutionPlanner,
        brokerage: Brokerage,
        pre_trade_check: CompositePreTradeCheck,
        data_feed: DataFeed,
        options: BacktestServiceOptions = BacktestServiceOptions(),
    ) -> None:
        self._config = config
        self._pipeline = pipeline
        self._planner = planner
        self._brokerage = brokerage
        self._pre_trade_check = pre_trade_check
        self._data_feed = data_feed
        self._options = options

    def run(self) -> BacktestReport:
        """
        执行完整回测流程: 运行引擎 → 生成报告 → 持久化结果.

        Returns:
            BacktestReport 回测报告。

        """
        run_id = self._resolve_run_id()
        run_svc = self._options.run_service

        # 1. (可选) 创建运行记录
        if run_svc is not None:
            run_svc.create_run(
                run_id=run_id,
                strategy_id=self._config.strategy_id,
                strategy_version=self._config.strategy_version,
                mode="backtest",
            )
            run_svc.mark_running(run_id)

        try:
            return self._execute_backtest(run_id)
        except Exception as exc:
            if run_svc is not None:
                run_svc.mark_failed(run_id, str(exc))
            raise

    def _execute_backtest(self, run_id: str) -> BacktestReport:
        """执行回测核心逻辑。"""
        # 创建审计收集器
        collector = ExecutionAuditCollector()

        # 构建 EngineConfig
        engine_config = EngineConfig(
            start_date=self._config.start_date,
            end_date=self._config.end_date,
            initial_cash=self._config.initial_cash,
            benchmark_id=self._config.benchmark_id,
            mode=EngineMode.BACKTEST,
            strategy_id=self._config.strategy_id,
            strategy_version=self._config.strategy_version,
            strategy_run_id=run_id,
            parameter_overrides=self._config.parameter_overrides,
            rebalance_freq=self._config.rebalance_freq,
            engine_version=self._config.engine_version,
        )

        # 构建 EngineOptions (注入 audit_collector)
        options = EngineOptions(
            fee_model=self._options.fee_model,
            rule_provider=self._options.rule_provider,
            post_trade_guard=self._options.post_trade_guard,
            audit_collector=collector,
        )

        # 构造并运行 EngineLoop
        engine_loop = EngineLoop(
            config=engine_config,
            pipeline=self._pipeline,
            planner=self._planner,
            brokerage=self._brokerage,
            pre_trade_check=self._pre_trade_check,
            data_feed=self._data_feed,
            options=options,
        )
        engine_result = engine_loop.run()

        # 构建 BacktestReport
        report = build_report(collector, run_id=run_id)

        # 持久化审计日志
        self._persist_audit(run_id, report)

        # 持久化策略产物
        self._persist_artifact(run_id, report, manifest=engine_result.manifest)

        # 更新运行状态
        run_svc = self._options.run_service
        if run_svc is not None:
            run_svc.mark_completed(run_id)

        return report

    def _resolve_run_id(self) -> str:
        """在进入生命周期编排前固化 run_id。"""
        configured_run_id = self._config.run_id
        if configured_run_id:
            return configured_run_id
        return uuid.uuid4().hex[:8]

    # -- internal persistence ------------------------------------------------

    def _persist_audit(self, run_id: str, report: BacktestReport) -> None:
        """
        持久化审计日志到 ExecutionAuditService。

        Port 层负责将 Core record 转换为 Data 本地 DTO。
        """
        if self._options.audit_service is None:
            return
        risk_payloads = tuple(
            RiskScanPayload(
                trade_date=r.trade_date,
                rule_id=r.rule_id,
                instrument_id=(
                    int(r.instrument_id) if r.instrument_id is not None else None
                ),
                scope=r.scope,
                severity=str(r.severity),
                action_taken=str(r.action_taken),
                detail=r.detail,
                current_value=r.current_value,
                threshold=r.threshold,
            )
            for r in report.risk_log
        )
        pre_trade_payloads = tuple(
            PreTradeDecisionPayload(
                trade_date=r.trade_date,
                order_id=r.order_id,
                instrument_id=int(r.instrument_id),
                direction=r.direction,
                original_quantity=r.original_quantity,
                final_quantity=r.final_quantity,
                decision=r.decision,
                reason=r.reason,
                check_sequence=r.check_sequence,
            )
            for r in report.pre_trade_log
        )
        self._options.audit_service.save_risk_log(run_id, risk_payloads)
        self._options.audit_service.save_pre_trade_log(run_id, pre_trade_payloads)

    def _persist_artifact(
        self,
        run_id: str,
        report: BacktestReport,
        manifest: RunManifest | None = None,
    ) -> None:
        """持久化回测报告到磁盘 + StrategyArtifactService。"""
        if self._options.artifact_service is None:
            return

        # 始终将产物序列化到磁盘
        output_dir: Path | None = None
        if self._options.artifact_dir is not None:
            output_dir = Path(self._options.artifact_dir) / run_id

        written = write_backtest_artifacts(
            report,
            output_dir=output_dir,
            manifest=manifest,
            display_map=self._options.display_map,
        )
        file_path = str(written.get("backtest_report", ""))

        artifact = StrategyArtifactRecord(
            artifact_id=f"artifact-{run_id}",
            strategy_id=self._config.strategy_id,
            run_id=run_id,
            artifact_type=ArtifactKind.BACKTEST_REPORT,
            file_path=file_path,
            metadata={
                "initial_cash": self._config.initial_cash,
                "final_nav": report.final_nav,
                "total_trades": report.aggregated_trade_stats.total_trades,
                "sharpe_ratio": report.alpha_stats.sharpe_ratio,
                "max_drawdown": report.alpha_stats.max_drawdown,
                "period_start": report.period[0],
                "period_end": report.period[1],
            },
            created_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
        self._options.artifact_service.save_artifact(artifact)


# ===========================================================================
# strategy_run_service.py — Port 层策略运行编排服务
# ===========================================================================


class StrategyRunMode(StrEnum):
    """策略运行模式。"""

    RESEARCH = "research"
    RECOMMENDATION = "recommendation"


# ---------------------------------------------------------------------------
# StrategyRunServiceConfig
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StrategyRunServiceConfig:
    """
    StrategyRunService 配置 — frozen, 运行前确定.

    Attributes:
        strategy_id: 策略 ID
        strategy_version: 策略版本
        run_id: 运行 ID (空字符串时自动生成)
        mode: 运行模式 (research / recommendation)
        spec: 策略定义（可选，设置后 run() 会先校验参数）

    """

    strategy_id: str = "default"
    strategy_version: str = ""
    run_id: str = ""
    mode: StrategyRunMode = StrategyRunMode.RESEARCH
    spec: StrategySpec | None = None


# ---------------------------------------------------------------------------
# StrategyRunResult
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StrategyRunResult:
    """
    策略运行结果.

    Attributes:
        run_id: 运行 ID
        trade_date: 交易日期
        strategy_id: 策略 ID
        target: 目标持仓
        mode: 运行模式

    """

    run_id: str
    trade_date: str
    strategy_id: str
    target: TargetPortfolio
    mode: StrategyRunMode


# ---------------------------------------------------------------------------
# StrategyRunService
# ---------------------------------------------------------------------------


class StrategyRunService:
    """
    Port 层策略运行编排服务.

    对给定交易日运行策略 Pipeline，产出 TargetPortfolio。
    RESEARCH 模式仅返回结果，RECOMMENDATION 模式额外持久化信号。

    Parameters
    ----------
        config: 服务配置
        pipeline: 策略 Pipeline
        assembler: 输入组装器
        artifact_service: 策略产物持久化服务 (RECOMMENDATION 模式使用)
        run_service: 策略运行生命周期服务

    """

    def __init__(
        self,
        config: StrategyRunServiceConfig,
        pipeline: StrategyPipeline,
        assembler: StrategyInputAssembler,
        *,
        artifact_service: StrategyArtifactService | None = None,
        run_service: RunLifecycleService | None = None,
    ) -> None:
        self._config = config
        self._pipeline = pipeline
        self._assembler = assembler
        self._artifact_service = artifact_service
        self._run_service = run_service

    @property
    def mode(self) -> StrategyRunMode:
        """当前运行模式。"""
        return self._config.mode

    def run(self, trade_date: str, slice_: Slice) -> StrategyRunResult:
        """
        执行单日策略运行.

        Args:
            trade_date: 交易日期
            slice_: 市场数据切片

        Returns:
            StrategyRunResult 包含 TargetPortfolio。

        """
        run_id = self._resolve_run_id()
        run_svc = self._run_service
        if run_svc is not None:
            run_svc.create_run(
                run_id=run_id,
                strategy_id=self._config.strategy_id,
                strategy_version=self._config.strategy_version,
                mode=str(self._config.mode),
            )
            run_svc.mark_running(run_id)

        try:
            return self._execute_run(trade_date, slice_, run_id=run_id)
        except Exception as exc:
            if run_svc is not None:
                run_svc.mark_failed(run_id, str(exc))
            raise

    def _execute_run(
        self,
        trade_date: str,
        slice_: Slice,
        *,
        run_id: str,
    ) -> StrategyRunResult:
        """执行策略核心运行逻辑。"""
        if self._config.spec is not None:
            self._validate_params(self._config.spec)

        input_bundle = self._assembler.assemble(trade_date, slice_, run_id=run_id)

        context = StrategyContext()
        target = self._pipeline.run(context, input_bundle)

        result = StrategyRunResult(
            run_id=run_id,
            trade_date=trade_date,
            strategy_id=self._config.strategy_id,
            target=target,
            mode=self._config.mode,
        )

        if self._config.mode == StrategyRunMode.RECOMMENDATION:
            self._persist_signal(run_id, trade_date, target)

        run_svc = self._run_service
        if run_svc is not None:
            run_svc.mark_completed(run_id)

        return result

    def _resolve_run_id(self) -> str:
        """在运行前固化真实 run_id。"""
        configured_run_id = self._config.run_id
        if configured_run_id:
            return configured_run_id
        return uuid.uuid4().hex[:8]

    # -- internal validation -------------------------------------------------

    @staticmethod
    def _validate_params(spec: StrategySpec) -> None:
        """校验 spec 参数，不合法时抛出 ValueError。"""
        errors = validate_spec_params(spec)
        if errors:
            raise ValueError(
                f"策略参数校验失败 [{spec.strategy_id}]: {'; '.join(errors)}"
            )

    # -- internal persistence ------------------------------------------------

    def _persist_signal(
        self,
        run_id: str,
        trade_date: str,
        target: TargetPortfolio,
    ) -> None:
        """持久化信号到 StrategyArtifactService。"""
        if self._artifact_service is None:
            return
        artifact = StrategyArtifactRecord(
            artifact_id=f"signal-{run_id}-{trade_date}",
            strategy_id=self._config.strategy_id,
            run_id=run_id,
            artifact_type=ArtifactKind.SIGNAL_SNAPSHOT,
            file_path="",
            metadata={
                "trade_date": trade_date,
                "positions": dict(target.positions),
                "cash_target": target.cash_target,
            },
            created_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
        self._artifact_service.save_artifact(artifact)


# ===========================================================================
# facade.py — 策略运行 facade
# ===========================================================================


class _StrategyServiceFactoryProto(Protocol):
    """StrategyFacade 所需的工厂协议（避免循环导入 builders）。"""

    def build_strategy_run_service_from_catalog(
        self,
        *,
        config: StrategyRunServiceConfig,
        version: int | None = None,
        assembler: StrategyInputAssembler | None = None,
    ) -> StrategyRunService: ...

    def build_backtest_service_from_catalog(
        self,
        *,
        config: BacktestServiceConfig,
        version: int | None = None,
        options: BacktestServiceOptions | None = None,
        source: str = "tushare",
    ) -> BacktestService: ...


class _StrategySliceBuilderProto(Protocol):
    """StrategyFacade 所需的 Slice 构建协议。"""

    def build_published_slice(
        self,
        strategy_id: str,
        *,
        trade_date: str,
        version: int | None = None,
        source: str = "tushare",
    ) -> Slice: ...


class StrategyFacade:
    """对外暴露 catalog-backed 策略执行入口。"""

    def __init__(
        self,
        *,
        factory: _StrategyServiceFactoryProto,
        slice_builder: _StrategySliceBuilderProto | None = None,
    ) -> None:
        self._factory = factory
        self._slice_builder = slice_builder

    def run_strategy_from_catalog(
        self,
        *,
        config: StrategyRunServiceConfig,
        trade_date: str,
        slice_: Slice,
        version: int | None = None,
    ) -> StrategyRunResult:
        """从 published catalog 构造并执行 research/recommendation。"""
        service = self._factory.build_strategy_run_service_from_catalog(
            config=config,
            version=version,
        )
        return service.run(trade_date, slice_)

    def run_strategy_for_date_from_catalog(
        self,
        *,
        config: StrategyRunServiceConfig,
        trade_date: str,
        version: int | None = None,
        source: str = "tushare",
    ) -> StrategyRunResult:
        """从 published catalog 自动组装单日 Slice 并执行 research/recommendation。"""
        if self._slice_builder is None:
            msg = "StrategySliceBuilder 未配置, 无法自动组装单日 Slice"
            raise ValueError(msg)
        slice_ = self._slice_builder.build_published_slice(
            config.strategy_id,
            trade_date=trade_date,
            version=version,
            source=source,
        )
        return self.run_strategy_from_catalog(
            config=config,
            trade_date=trade_date,
            slice_=slice_,
            version=version,
        )

    def run_backtest_from_catalog(
        self,
        *,
        config: BacktestServiceConfig,
        version: int | None = None,
        options: BacktestServiceOptions | None = None,
        source: str = "tushare",
    ) -> BacktestReport:
        """从 published catalog 构造并执行完整回测。"""
        service = self._factory.build_backtest_service_from_catalog(
            config=config,
            version=version,
            options=options,
            source=source,
        )
        return service.run()
