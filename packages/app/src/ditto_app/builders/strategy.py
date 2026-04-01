"""
策略服务工厂与运行时装配 — Builders 模块.

合并自 ditto_port.services.strategy 中的:
  - factory.py
  - runtime_builder.py
  - backtest_runtime_builder.py
  - slice_builder.py

注意: 本模块依赖 process.strategy 中的类型（BacktestService,
BacktestServiceConfig, BacktestServiceOptions, StrategyInputAssembler,
RunLifecycleService, StrategyRunService, StrategyRunServiceConfig,
StrategyRunResult, MarketServiceDataFeed, MarketServiceDataFeedConfig），
通过延迟导入或类型注解引用避免循环依赖。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import cast

from ditto_datahub.models.strategy import StrategySpecRecord
from ditto_datahub.services.audit import ExecutionAuditService
from ditto_datahub.services.market_service import MarketService
from ditto_datahub.services.metadata_service import MetadataService
from ditto_datahub.services.strategy.strategy_artifact_service import (
    StrategyArtifactService,
)
from ditto_datahub.services.strategy.strategy_catalog_service import (
    StrategyCatalogService,
)
from ditto_engine.accounting.account import Account
from ditto_engine.accounting.cash import CashBook
from ditto_engine.backtest.data_feed import DataFeed, Slice
from ditto_engine.backtest.risk.pre_trade import (
    BuyingPowerCheck,
    CompositePreTradeCheck,
    LotSizeCheck,
)
from ditto_engine.execution.brokerage import BacktestBrokerage, Brokerage
from ditto_engine.execution.planner import ExecutionPlanner, SimpleExecutionPlanner
from ditto_engine.execution.reality import BrokerageModel, FeeModel, SimpleFeeModel
from ditto_engine.strategy.builtins.scoring import ScoringMethod
from ditto_engine.strategy.pipeline import StrategyPipeline
from ditto_engine.strategy.specs import (
    ConstraintSpec,
    CostModelSpec,
    ExecutionSpec,
    ParamConstraint,
    ScorerSpec,
    SelectorSpec,
    StrategySpec,
)
from ditto_engine.strategy.templates import (
    ETFRotationConfig,
    ETFTrendSwingConfig,
    StockSectorRotationConfig,
    StockSelectionTrendConfig,
    build_etf_rotation_pipeline,
    build_etf_trend_swing_pipeline,
    build_stock_sector_rotation_pipeline,
    build_stock_selection_trend_pipeline,
    get_sector_rotation_param_constraints,
    validate_sector_rotation_config,
)
from ditto_engine.strategy.templates import (
    get_param_constraints as get_stock_selection_param_constraints,
)
from ditto_engine.strategy.templates import (
    validate_config as validate_stock_selection_config,
)
from ditto_kernel.identity import InstrumentId

from ditto_app.process.strategy import (
    BacktestService,
    BacktestServiceConfig,
    BacktestServiceOptions,
    MarketServiceDataFeed,
    MarketServiceDataFeedConfig,
    RunLifecycleService,
    StrategyInputAssembler,
    StrategyRunService,
    StrategyRunServiceConfig,
)

__all__ = [
    "BacktestRuntimeBuilder",
    "PublishedBacktestRuntime",
    "PublishedStrategyRuntime",
    "StrategyRuntimeBuilder",
    "StrategyServiceFactory",
    "StrategySliceBuilder",
]


# ===========================================================================
# runtime_builder.py — 已发布策略 Spec 的运行时装配器
# ===========================================================================


@dataclass(frozen=True)
class PublishedStrategyRuntime:
    """已发布策略的运行时定义。"""

    record: StrategySpecRecord
    spec: StrategySpec
    pipeline: StrategyPipeline


class StrategyRuntimeBuilder:
    """从 published StrategySpecRecord 组装 Core runtime 对象。"""

    def __init__(self, *, catalog_service: StrategyCatalogService) -> None:
        self._catalog_service = catalog_service

    def build_published_runtime(
        self,
        strategy_id: str,
        version: int | None = None,
    ) -> PublishedStrategyRuntime:
        """读取 published spec 并构造 ``StrategySpec + StrategyPipeline``。"""
        record = self._catalog_service.get_spec(strategy_id, version)
        if record is None:
            msg = (
                f"未找到策略定义: strategy_id={strategy_id}, "
                f"version={version if version is not None else 'latest'}"
            )
            raise LookupError(msg)
        if record.status != "published":
            msg = (
                f"策略定义尚未发布为 published: strategy_id={strategy_id}, "
                f"version={record.version}, status={record.status}"
            )
            raise ValueError(msg)

        spec = self._deserialize_strategy_spec(record)
        pipeline = self._build_pipeline(spec)
        return PublishedStrategyRuntime(record=record, spec=spec, pipeline=pipeline)

    def _deserialize_strategy_spec(self, record: StrategySpecRecord) -> StrategySpec:
        """将 catalog 中的 ``spec_json`` 恢复为 ``StrategySpec``。"""
        payload = self._as_object_dict(record.spec_json, field_name="spec_json")
        spec = StrategySpec(
            strategy_id=self._read_optional_str(payload.get("strategy_id"))
            or record.strategy_id,
            name=self._read_optional_str(payload.get("name")) or record.name,
            template=self._read_required_str(payload, "template"),
            universe=self._read_required_str(payload, "universe"),
            asset_class=self._read_required_str(payload, "asset_class"),
            scorer=self._deserialize_scorer(payload.get("scorer")),
            selector=self._deserialize_selector(payload.get("selector")),
            execution=self._deserialize_execution(payload.get("execution")),
            constraints=tuple(
                self._deserialize_constraint(item, index=index)
                for index, item in enumerate(
                    self._as_sequence(
                        payload.get("constraints"),
                        field_name="constraints",
                    )
                )
            ),
            benchmark=self._read_optional_str(payload.get("benchmark")),
            params=self._as_object_dict(payload.get("params"), field_name="params"),
            param_constraints=tuple(
                self._deserialize_param_constraint(item, index=index)
                for index, item in enumerate(
                    self._as_sequence(
                        payload.get("param_constraints"),
                        field_name="param_constraints",
                    )
                )
            ),
            tags=self._as_str_tuple(payload.get("tags"), field_name="tags")
            or record.tags,
        )
        return self._inject_template_constraints(spec)

    def _deserialize_scorer(self, raw_value: object) -> ScorerSpec:
        """恢复评分器配置。"""
        payload = self._as_object_dict(raw_value, field_name="scorer")
        return ScorerSpec(
            method=self._read_optional_str(payload.get("method")) or "equal_weight",
            params=self._as_object_dict(
                payload.get("params"),
                field_name="scorer.params",
            ),
        )

    def _deserialize_selector(self, raw_value: object) -> SelectorSpec:
        """恢复选择器配置。"""
        payload = self._as_object_dict(raw_value, field_name="selector")
        return SelectorSpec(
            method=self._read_optional_str(payload.get("method")) or "top_k",
            params=self._as_object_dict(
                payload.get("params"),
                field_name="selector.params",
            ),
        )

    def _deserialize_execution(self, raw_value: object) -> ExecutionSpec:
        """恢复执行层配置。"""
        payload = self._as_object_dict(raw_value, field_name="execution")
        return ExecutionSpec(
            frequency=self._read_optional_str(payload.get("frequency")) or "M",
            method=self._read_optional_str(payload.get("method")) or "calendar",
            cost_model=self._deserialize_cost_model(payload.get("cost_model")),
        )

    def _deserialize_cost_model(self, raw_value: object) -> CostModelSpec:
        """恢复成本模型配置。"""
        payload = self._as_object_dict(raw_value, field_name="execution.cost_model")
        return CostModelSpec(
            commission_rate=self._read_float(
                payload.get("commission_rate", 0.0003),
                field_name="execution.cost_model.commission_rate",
            ),
            slippage_bps=self._read_float(
                payload.get("slippage_bps", 5.0),
                field_name="execution.cost_model.slippage_bps",
            ),
            impact_model=(
                self._read_optional_str(payload.get("impact_model")) or "linear"
            ),
        )

    def _deserialize_constraint(
        self,
        raw_value: object,
        *,
        index: int,
    ) -> ConstraintSpec:
        """恢复单条约束配置。"""
        payload = self._as_object_dict(raw_value, field_name=f"constraints[{index}]")
        return ConstraintSpec(
            type=self._read_required_str(payload, "type"),
            params=self._as_object_dict(
                payload.get("params"),
                field_name=f"constraints[{index}].params",
            ),
            priority=self._read_int(
                payload.get("priority", 100),
                field_name=f"constraints[{index}].priority",
            ),
        )

    def _deserialize_param_constraint(
        self,
        raw_value: object,
        *,
        index: int,
    ) -> ParamConstraint:
        """恢复参数约束元数据。"""
        payload = self._as_object_dict(
            raw_value,
            field_name=f"param_constraints[{index}]",
        )
        return ParamConstraint(
            name=self._read_required_str(payload, "name"),
            dtype=self._read_required_str(payload, "dtype"),
            min_value=self._read_optional_float(
                payload.get("min_value"),
                field_name=f"param_constraints[{index}].min_value",
            ),
            max_value=self._read_optional_float(
                payload.get("max_value"),
                field_name=f"param_constraints[{index}].max_value",
            ),
            step=self._read_optional_float(
                payload.get("step"),
                field_name=f"param_constraints[{index}].step",
            ),
            allowed_values=self._as_str_tuple(
                payload.get("allowed_values"),
                field_name=f"param_constraints[{index}].allowed_values",
            ),
        )

    def _inject_template_constraints(self, spec: StrategySpec) -> StrategySpec:
        """为模板型策略补齐缺失的参数约束元数据。"""
        if spec.param_constraints:
            return spec
        if spec.template == "stock_selection_trend":
            return replace(
                spec,
                param_constraints=get_stock_selection_param_constraints(),
            )
        if spec.template == "stock_sector_rotation":
            return replace(
                spec,
                param_constraints=get_sector_rotation_param_constraints(),
            )
        return spec

    def _build_pipeline(self, spec: StrategySpec) -> StrategyPipeline:
        """根据模板类型构造对应的 ``StrategyPipeline``。"""
        if spec.template == "etf_rotation":
            return build_etf_rotation_pipeline(self._build_etf_rotation_config(spec))
        if spec.template == "etf_trend_swing":
            return build_etf_trend_swing_pipeline(
                self._build_etf_trend_swing_config(spec),
            )
        if spec.template == "stock_selection_trend":
            config = self._build_stock_selection_trend_config(spec)
            validate_stock_selection_config(config)
            return build_stock_selection_trend_pipeline(config)
        if spec.template == "stock_sector_rotation":
            config = self._build_stock_sector_rotation_config(spec)
            validate_sector_rotation_config(config)
            return build_stock_sector_rotation_pipeline(config)

        msg = f"不支持的策略模板: {spec.template}"
        raise ValueError(msg)

    def _build_etf_rotation_config(self, spec: StrategySpec) -> ETFRotationConfig:
        params = spec.params
        return ETFRotationConfig(
            top_k=self._resolve_top_k(spec, default=10),
            scoring_method=self._resolve_scoring_method(spec, default="rank"),
            scoring_ascending=self._read_bool(
                params.get("scoring_ascending", True),
                field_name="params.scoring_ascending",
            ),
            allocation_method=self._read_optional_str(
                params.get("allocation_method"),
            )
            or "equal_weight",
            cash_target=self._read_float(
                params.get("cash_target", 0.0),
                field_name="params.cash_target",
            ),
            signal_column=self._read_optional_str(params.get("signal_column"))
            or "signal_value",
            max_weight=self._read_optional_float(
                params.get("max_weight"),
                field_name="params.max_weight",
            ),
            max_positions=self._read_optional_int(
                params.get("max_positions"),
                field_name="params.max_positions",
            ),
        )

    def _build_etf_trend_swing_config(
        self,
        spec: StrategySpec,
    ) -> ETFTrendSwingConfig:
        params = spec.params
        return ETFTrendSwingConfig(
            lookback_window=self._read_int(
                params.get("lookback_window", 20),
                field_name="params.lookback_window",
            ),
            trend_threshold=self._read_float(
                params.get("trend_threshold", 0.0),
                field_name="params.trend_threshold",
            ),
            trailing_stop_pct=self._read_float(
                params.get("trailing_stop_pct", 0.08),
                field_name="params.trailing_stop_pct",
            ),
            max_positions=self._read_int(
                params.get("max_positions", self._resolve_top_k(spec, default=10)),
                field_name="params.max_positions",
            ),
            scoring_method=self._resolve_scoring_method(spec, default="rank"),
            scoring_ascending=self._read_bool(
                params.get("scoring_ascending", True),
                field_name="params.scoring_ascending",
            ),
            allocation_method=self._read_optional_str(
                params.get("allocation_method"),
            )
            or "equal_weight",
            cash_target=self._read_float(
                params.get("cash_target", 0.0),
                field_name="params.cash_target",
            ),
            signal_column=self._read_optional_str(params.get("signal_column"))
            or "signal_value",
        )

    def _build_stock_selection_trend_config(
        self,
        spec: StrategySpec,
    ) -> StockSelectionTrendConfig:
        params = spec.params
        return StockSelectionTrendConfig(
            universe_filter=(
                self._read_optional_str(params.get("universe_filter")) or ""
            ),
            signal_factors=self._as_str_tuple(
                params.get("signal_factors"),
                field_name="params.signal_factors",
            )
            or ("signal_value",),
            signal_weights=self._as_float_tuple(
                params.get("signal_weights"),
                field_name="params.signal_weights",
            )
            or (1.0,),
            top_k=self._resolve_top_k(spec, default=10),
            max_weight=self._read_float(
                params.get("max_weight", 0.15),
                field_name="params.max_weight",
            ),
            allocation_method=self._read_optional_str(
                params.get("allocation_method"),
            )
            or "equal_weight",
            cash_target=self._read_float(
                params.get("cash_target", 0.0),
                field_name="params.cash_target",
            ),
            trend_threshold=self._read_float(
                params.get("trend_threshold", 0.0),
                field_name="params.trend_threshold",
            ),
            rebalance_freq=self._read_optional_str(params.get("rebalance_freq"))
            or self._resolve_rebalance_frequency(spec.execution.frequency),
        )

    def _build_stock_sector_rotation_config(
        self,
        spec: StrategySpec,
    ) -> StockSectorRotationConfig:
        params = spec.params
        return StockSectorRotationConfig(
            sector_signal=self._read_optional_str(params.get("sector_signal"))
            or "signal_value",
            stock_signal=self._read_optional_str(params.get("stock_signal"))
            or "signal_value",
            top_sectors=self._read_int(
                params.get("top_sectors", 3),
                field_name="params.top_sectors",
            ),
            stocks_per_sector=self._read_int(
                params.get("stocks_per_sector", 3),
                field_name="params.stocks_per_sector",
            ),
            sector_weight_method=self._read_optional_str(
                params.get("sector_weight_method"),
            )
            or "equal_weight",
            stock_weight_method=self._read_optional_str(
                params.get("stock_weight_method"),
            )
            or "equal_weight",
            max_weight=self._read_float(
                params.get("max_weight", 0.15),
                field_name="params.max_weight",
            ),
            cash_target=self._read_float(
                params.get("cash_target", 0.0),
                field_name="params.cash_target",
            ),
            rebalance_freq=self._read_optional_str(params.get("rebalance_freq"))
            or self._resolve_rebalance_frequency(spec.execution.frequency),
        )

    @staticmethod
    def _resolve_top_k(spec: StrategySpec, *, default: int) -> int:
        """优先使用 params.top_k，否则回落到 selector.params.k。"""
        params = spec.params
        if "top_k" in params:
            return StrategyRuntimeBuilder._read_int(
                params["top_k"],
                field_name="params.top_k",
            )
        selector_k = spec.selector.params.get("k")
        if selector_k is None:
            return default
        return StrategyRuntimeBuilder._read_int(
            selector_k,
            field_name="selector.params.k",
        )

    @staticmethod
    def _resolve_scoring_method(
        spec: StrategySpec,
        *,
        default: str,
    ) -> ScoringMethod:
        """优先使用 params.scoring_method，否则回落到 scorer.method。"""
        raw_method = spec.params.get("scoring_method")
        if raw_method is None:
            raw_method = spec.scorer.method or default
        method = StrategyRuntimeBuilder._read_str_value(
            raw_method,
            field_name="scoring_method",
        )
        try:
            return ScoringMethod(method)
        except ValueError as exc:
            msg = f"不支持的 scoring_method: {method}"
            raise ValueError(msg) from exc

    @staticmethod
    def _resolve_rebalance_frequency(frequency: str) -> str:
        """将执行层频率映射为模板 rebalance_freq。"""
        mapping = {
            "D": "daily",
            "W": "weekly",
            "M": "monthly",
        }
        return mapping.get(frequency, "daily")

    @staticmethod
    def _as_object_dict(
        raw_value: object,
        *,
        field_name: str,
    ) -> dict[str, object]:
        """校验对象形态并返回 ``dict[str, object]``。"""
        if raw_value is None:
            return {}
        if not isinstance(raw_value, dict):
            msg = f"{field_name} 必须是 object/dict"
            raise ValueError(msg)
        raw_dict = cast("dict[object, object]", raw_value)
        result: dict[str, object] = {}
        for key, value in raw_dict.items():
            if not isinstance(key, str):
                msg = f"{field_name} 的 key 必须是 str"
                raise ValueError(msg)
            result[key] = value
        return result

    @staticmethod
    def _as_sequence(
        raw_value: object,
        *,
        field_name: str,
    ) -> tuple[object, ...]:
        """校验序列形态并返回 tuple。"""
        if raw_value is None:
            return ()
        if isinstance(raw_value, tuple):
            return cast("tuple[object, ...]", raw_value)
        if isinstance(raw_value, list):
            return tuple(cast("list[object]", raw_value))
        msg = f"{field_name} 必须是 list/tuple"
        raise ValueError(msg)

    @staticmethod
    def _as_str_tuple(
        raw_value: object,
        *,
        field_name: str,
    ) -> tuple[str, ...]:
        """将字符串序列标准化为 tuple。"""
        items = StrategyRuntimeBuilder._as_sequence(raw_value, field_name=field_name)
        result: list[str] = []
        for item in items:
            if not isinstance(item, str):
                msg = f"{field_name} 的元素必须是 str"
                raise ValueError(msg)
            result.append(item)
        return tuple(result)

    @staticmethod
    def _as_float_tuple(
        raw_value: object,
        *,
        field_name: str,
    ) -> tuple[float, ...]:
        """将数值序列标准化为 tuple[float, ...]。"""
        items = StrategyRuntimeBuilder._as_sequence(raw_value, field_name=field_name)
        result: list[float] = []
        for item in items:
            if not isinstance(item, (int, float)) or isinstance(item, bool):
                msg = f"{field_name} 的元素必须是数字"
                raise ValueError(msg)
            result.append(float(item))
        return tuple(result)

    @staticmethod
    def _read_required_str(payload: dict[str, object], field_name: str) -> str:
        """读取必填字符串字段。"""
        value = payload.get(field_name)
        if not isinstance(value, str) or value == "":
            msg = f"{field_name} 必须是非空字符串"
            raise ValueError(msg)
        return value

    @staticmethod
    def _read_optional_str(raw_value: object) -> str | None:
        """读取可选字符串字段。"""
        if raw_value is None:
            return None
        if not isinstance(raw_value, str):
            msg = "字段值必须是字符串"
            raise ValueError(msg)
        return raw_value

    @staticmethod
    def _read_str_value(raw_value: object, *, field_name: str) -> str:
        """读取字符串值。"""
        if not isinstance(raw_value, str) or raw_value == "":
            msg = f"{field_name} 必须是非空字符串"
            raise ValueError(msg)
        return raw_value

    @staticmethod
    def _read_int(raw_value: object, *, field_name: str) -> int:
        """读取整数值。"""
        if not isinstance(raw_value, int) or isinstance(raw_value, bool):
            msg = f"{field_name} 必须是 int"
            raise ValueError(msg)
        return raw_value

    @staticmethod
    def _read_optional_int(raw_value: object, *, field_name: str) -> int | None:
        """读取可选整数值。"""
        if raw_value is None:
            return None
        return StrategyRuntimeBuilder._read_int(raw_value, field_name=field_name)

    @staticmethod
    def _read_float(raw_value: object, *, field_name: str) -> float:
        """读取浮点值，允许 int 自动提升。"""
        if not isinstance(raw_value, (int, float)) or isinstance(raw_value, bool):
            msg = f"{field_name} 必须是数字"
            raise ValueError(msg)
        return float(raw_value)

    @staticmethod
    def _read_optional_float(
        raw_value: object,
        *,
        field_name: str,
    ) -> float | None:
        """读取可选浮点值。"""
        if raw_value is None:
            return None
        return StrategyRuntimeBuilder._read_float(raw_value, field_name=field_name)

    @staticmethod
    def _read_bool(raw_value: object, *, field_name: str) -> bool:
        """读取布尔值。"""
        if not isinstance(raw_value, bool):
            msg = f"{field_name} 必须是 bool"
            raise ValueError(msg)
        return raw_value


# ===========================================================================
# backtest_runtime_builder.py — published strategy 到 backtest runtime 的装配器
# ===========================================================================


@dataclass(frozen=True)
class PublishedBacktestRuntime:
    """从 published strategy 派生出的完整回测运行时。"""

    record: StrategySpecRecord
    spec: StrategySpec
    pipeline: StrategyPipeline
    planner: SimpleExecutionPlanner
    brokerage: BacktestBrokerage
    pre_trade_check: CompositePreTradeCheck
    data_feed: MarketServiceDataFeed
    fee_model: FeeModel
    config: BacktestServiceConfig


class BacktestRuntimeBuilder:
    """为 published strategy 组装最小可运行回测依赖。"""

    def __init__(
        self,
        *,
        strategy_runtime_builder: StrategyRuntimeBuilder,
        metadata_service: MetadataService,
        market_service: MarketService,
    ) -> None:
        self._strategy_runtime_builder = strategy_runtime_builder
        self._metadata_service = metadata_service
        self._market_service = market_service

    def build_published_runtime(
        self,
        *,
        config: BacktestServiceConfig,
        version: int | None = None,
        source: str = "tushare",
    ) -> PublishedBacktestRuntime:
        """从 published strategy catalog 构造回测运行时。"""
        runtime = self._strategy_runtime_builder.build_published_runtime(
            config.strategy_id,
            version,
        )
        fee_model = SimpleFeeModel()
        brokerage = BacktestBrokerage(
            account=Account(
                cash=CashBook(
                    available=config.initial_cash,
                    settled=config.initial_cash,
                    frozen=0.0,
                )
            ),
            model=BrokerageModel(fee_model=fee_model),
        )
        benchmark_id = self._resolve_benchmark(
            config.benchmark_id,
            runtime.spec.benchmark,
            source,
            config.start_date,
        )
        resolved_config = replace(
            config,
            strategy_version=str(runtime.record.version),
            benchmark_id=benchmark_id,
        )
        return PublishedBacktestRuntime(
            record=runtime.record,
            spec=runtime.spec,
            pipeline=runtime.pipeline,
            planner=SimpleExecutionPlanner(),
            brokerage=brokerage,
            pre_trade_check=CompositePreTradeCheck(
                checks=(LotSizeCheck(), BuyingPowerCheck()),
            ),
            data_feed=MarketServiceDataFeed(
                metadata_service=self._metadata_service,
                market_service=self._market_service,
                config=MarketServiceDataFeedConfig(
                    universe_id=runtime.spec.universe,
                    asset_class=runtime.spec.asset_class,
                    start_date=config.start_date,
                    end_date=config.end_date,
                    benchmark_id=resolved_config.benchmark_id,
                    source=source,
                ),
            ),
            fee_model=fee_model,
            config=resolved_config,
        )

    def _resolve_benchmark(
        self,
        config_benchmark: InstrumentId | None,
        spec_benchmark: str | None,
        source: str,
        as_of: str,
    ) -> InstrumentId | None:
        """解析 benchmark：优先使用 config 中的 InstrumentId，否则从 spec 解析。"""
        if config_benchmark is not None:
            return config_benchmark
        if spec_benchmark is None:
            return None
        iid = self._metadata_service.resolve_instrument_id(
            spec_benchmark,
            source,
            as_of,
        )
        return InstrumentId(iid) if iid is not None else None


# ===========================================================================
# slice_builder.py — published strategy 到单日 Slice 的组装器
# ===========================================================================


class StrategySliceBuilder:
    """为 published strategy 组装 research/recommendation 所需单日 Slice。"""

    def __init__(
        self,
        *,
        strategy_runtime_builder: StrategyRuntimeBuilder,
        metadata_service: MetadataService,
        market_service: MarketService,
    ) -> None:
        self._strategy_runtime_builder = strategy_runtime_builder
        self._metadata_service = metadata_service
        self._market_service = market_service

    def build_published_slice(
        self,
        strategy_id: str,
        *,
        trade_date: str,
        version: int | None = None,
        source: str = "tushare",
    ) -> Slice:
        """从 published strategy catalog 构造指定日期的市场切片。"""
        runtime = self._strategy_runtime_builder.build_published_runtime(
            strategy_id,
            version,
        )
        benchmark_id = self._resolve_benchmark(
            runtime.spec.benchmark,
            source,
            trade_date,
        )
        data_feed = MarketServiceDataFeed(
            metadata_service=self._metadata_service,
            market_service=self._market_service,
            config=MarketServiceDataFeedConfig(
                universe_id=runtime.spec.universe,
                asset_class=runtime.spec.asset_class,
                start_date=trade_date,
                end_date=trade_date,
                benchmark_id=benchmark_id,
                source=source,
            ),
        )
        if trade_date not in data_feed.trading_days():
            msg = f"trade_date 不在可用交易日内: {trade_date}"
            raise ValueError(msg)
        return data_feed.get_slice(trade_date)

    def _resolve_benchmark(
        self,
        benchmark: str | None,
        source: str,
        as_of: str,
    ) -> InstrumentId | None:
        """将 benchmark ticker 解析为 InstrumentId。"""
        if benchmark is None:
            return None
        iid = self._metadata_service.resolve_instrument_id(benchmark, source, as_of)
        return InstrumentId(iid) if iid is not None else None


# ===========================================================================
# factory.py — Port 策略服务工厂
# ===========================================================================


class StrategyServiceFactory:
    """为 Port 层策略服务预接控制面依赖的工厂。"""

    def __init__(
        self,
        *,
        audit_service: ExecutionAuditService,
        artifact_service: StrategyArtifactService,
        run_service: RunLifecycleService,
        runtime_builder: StrategyRuntimeBuilder | None = None,
        backtest_runtime_builder: BacktestRuntimeBuilder | None = None,
    ) -> None:
        self._audit_service = audit_service
        self._artifact_service = artifact_service
        self._run_service = run_service
        self._runtime_builder = runtime_builder
        self._backtest_runtime_builder = backtest_runtime_builder

    def build_strategy_run_service(
        self,
        *,
        config: StrategyRunServiceConfig,
        pipeline: StrategyPipeline,
        assembler: StrategyInputAssembler | None = None,
    ) -> StrategyRunService:
        """构造带控制面依赖的 StrategyRunService。"""
        resolved_assembler = assembler or self._build_input_assembler(config)
        return StrategyRunService(
            config=config,
            pipeline=pipeline,
            assembler=resolved_assembler,
            artifact_service=self._artifact_service,
            run_service=self._run_service,
        )

    def build_strategy_run_service_from_catalog(
        self,
        *,
        config: StrategyRunServiceConfig,
        version: int | None = None,
        assembler: StrategyInputAssembler | None = None,
    ) -> StrategyRunService:
        """从 published strategy catalog 直接构造 ``StrategyRunService``。"""
        if self._runtime_builder is None:
            msg = "StrategyRuntimeBuilder 未配置, 无法从 catalog 构造运行服务"
            raise ValueError(msg)
        resolved_version = version
        if resolved_version is None:
            resolved_version = self._parse_catalog_version(config.strategy_version)
        runtime = self._runtime_builder.build_published_runtime(
            config.strategy_id,
            resolved_version,
        )
        resolved_config = replace(
            config,
            strategy_version=str(runtime.record.version),
            spec=runtime.spec,
        )
        return self.build_strategy_run_service(
            config=resolved_config,
            pipeline=runtime.pipeline,
            assembler=assembler,
        )

    def build_backtest_service(
        self,
        *,
        config: BacktestServiceConfig,
        pipeline: StrategyPipeline,
        planner: ExecutionPlanner,
        brokerage: Brokerage,
        pre_trade_check: CompositePreTradeCheck,
        data_feed: DataFeed,
        options: BacktestServiceOptions | None = None,
    ) -> BacktestService:
        """构造带控制面依赖的 BacktestService。"""
        resolved_options = self._build_backtest_options(options)
        return BacktestService(
            config=config,
            pipeline=pipeline,
            planner=planner,
            brokerage=brokerage,
            pre_trade_check=pre_trade_check,
            data_feed=data_feed,
            options=resolved_options,
        )

    def build_backtest_service_from_catalog(
        self,
        *,
        config: BacktestServiceConfig,
        version: int | None = None,
        options: BacktestServiceOptions | None = None,
        source: str = "tushare",
    ) -> BacktestService:
        """从 published strategy catalog 直接构造 ``BacktestService``。"""
        if self._backtest_runtime_builder is None:
            msg = "BacktestRuntimeBuilder 未配置, 无法从 catalog 构造回测服务"
            raise ValueError(msg)
        resolved_version = version
        if resolved_version is None:
            resolved_version = self._parse_catalog_version(config.strategy_version)
        runtime = self._backtest_runtime_builder.build_published_runtime(
            config=config,
            version=resolved_version,
            source=source,
        )
        resolved_options = options or BacktestServiceOptions()
        if resolved_options.fee_model is None:
            resolved_options = replace(
                resolved_options,
                fee_model=runtime.fee_model,
            )
        if resolved_options.display_map is None:
            resolved_options = replace(
                resolved_options,
                display_map=runtime.data_feed.display_map,
            )
        return self.build_backtest_service(
            config=runtime.config,
            pipeline=runtime.pipeline,
            planner=runtime.planner,
            brokerage=runtime.brokerage,
            pre_trade_check=runtime.pre_trade_check,
            data_feed=runtime.data_feed,
            options=resolved_options,
        )

    def _build_input_assembler(
        self,
        config: StrategyRunServiceConfig,
    ) -> StrategyInputAssembler:
        """按运行配置创建默认输入组装器。"""
        parameters: dict[str, object] | None = None
        if config.spec is not None:
            parameters = dict(config.spec.params)
        return StrategyInputAssembler(
            strategy_id=config.strategy_id,
            run_id=config.run_id,
            parameters=parameters,
        )

    def _build_backtest_options(
        self,
        options: BacktestServiceOptions | None,
    ) -> BacktestServiceOptions:
        """将容器内控制面服务并入 BacktestServiceOptions。"""
        if options is None:
            return BacktestServiceOptions(
                audit_service=self._audit_service,
                artifact_service=self._artifact_service,
                run_service=self._run_service,
            )
        return BacktestServiceOptions(
            fee_model=options.fee_model,
            rule_provider=options.rule_provider,
            post_trade_guard=options.post_trade_guard,
            audit_service=options.audit_service or self._audit_service,
            artifact_service=options.artifact_service or self._artifact_service,
            artifact_dir=options.artifact_dir,
            display_map=options.display_map,
            run_service=options.run_service or self._run_service,
        )

    @staticmethod
    def _parse_catalog_version(strategy_version: str) -> int | None:
        """将 run lifecycle 中的版本字符串尽量解析成 catalog version。"""
        if strategy_version == "":
            return None
        try:
            return int(strategy_version)
        except ValueError:
            return None
