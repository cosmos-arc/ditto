"""已发布策略 Spec 的运行时装配器."""

from __future__ import annotations

from dataclasses import dataclass, replace

from ditto_data.models.strategy import StrategySpecRecord
from ditto_data.services.strategy.strategy_catalog_service import (
    StrategyCatalogService,
)
from ditto_engine.alpha.builtins.scoring import ScoringMethod
from ditto_engine.alpha.pipeline import StrategyPipeline
from ditto_engine.alpha.specs import (
    ConstraintSpec,
    CostModelSpec,
    ExecutionSpec,
    ParamConstraint,
    ScorerSpec,
    SelectorSpec,
    StrategySpec,
)
from ditto_engine.alpha.templates import (
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
from ditto_engine.alpha.templates import (
    get_param_constraints as get_stock_selection_param_constraints,
)
from ditto_engine.alpha.templates import (
    validate_config as validate_stock_selection_config,
)

from ditto_app.builders._spec_deserializer import (
    as_float_tuple,
    as_object_dict,
    as_sequence,
    as_str_tuple,
    read_bool,
    read_float,
    read_int,
    read_optional_float,
    read_optional_int,
    read_optional_str,
    read_required_str,
    read_str_value,
)

__all__ = [
    "PublishedStrategyRuntime",
    "StrategyRuntimeBuilder",
]


# ===========================================================================
# PublishedStrategyRuntime
# ===========================================================================


@dataclass(frozen=True)
class PublishedStrategyRuntime:
    """已发布策略的运行时定义。"""

    record: StrategySpecRecord
    spec: StrategySpec
    pipeline: StrategyPipeline


# ===========================================================================
# StrategyRuntimeBuilder
# ===========================================================================


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

    # ------------------------------------------------------------------
    # Deserialization
    # ------------------------------------------------------------------

    def _deserialize_strategy_spec(self, record: StrategySpecRecord) -> StrategySpec:
        """将 catalog 中的 ``spec_json`` 恢复为 ``StrategySpec``。"""
        payload = as_object_dict(record.spec_json, field_name="spec_json")
        spec = StrategySpec(
            strategy_id=read_optional_str(payload.get("strategy_id"))
            or record.strategy_id,
            name=read_optional_str(payload.get("name")) or record.name,
            template=read_required_str(payload, "template"),
            universe=read_required_str(payload, "universe"),
            asset_class=read_required_str(payload, "asset_class"),
            scorer=self._deserialize_scorer(payload.get("scorer")),
            selector=self._deserialize_selector(payload.get("selector")),
            execution=self._deserialize_execution(payload.get("execution")),
            constraints=tuple(
                self._deserialize_constraint(item, index=index)
                for index, item in enumerate(
                    as_sequence(
                        payload.get("constraints"),
                        field_name="constraints",
                    )
                )
            ),
            benchmark=read_optional_str(payload.get("benchmark")),
            params=as_object_dict(payload.get("params"), field_name="params"),
            param_constraints=tuple(
                self._deserialize_param_constraint(item, index=index)
                for index, item in enumerate(
                    as_sequence(
                        payload.get("param_constraints"),
                        field_name="param_constraints",
                    )
                )
            ),
            tags=as_str_tuple(payload.get("tags"), field_name="tags") or record.tags,
        )
        return self._inject_template_constraints(spec)

    def _deserialize_scorer(self, raw_value: object) -> ScorerSpec:
        """恢复评分器配置。"""
        payload = as_object_dict(raw_value, field_name="scorer")
        return ScorerSpec(
            method=read_optional_str(payload.get("method")) or "equal_weight",
            params=as_object_dict(
                payload.get("params"),
                field_name="scorer.params",
            ),
        )

    def _deserialize_selector(self, raw_value: object) -> SelectorSpec:
        """恢复选择器配置。"""
        payload = as_object_dict(raw_value, field_name="selector")
        return SelectorSpec(
            method=read_optional_str(payload.get("method")) or "top_k",
            params=as_object_dict(
                payload.get("params"),
                field_name="selector.params",
            ),
        )

    def _deserialize_execution(self, raw_value: object) -> ExecutionSpec:
        """恢复执行层配置。"""
        payload = as_object_dict(raw_value, field_name="execution")
        return ExecutionSpec(
            frequency=read_optional_str(payload.get("frequency")) or "M",
            method=read_optional_str(payload.get("method")) or "calendar",
            cost_model=self._deserialize_cost_model(payload.get("cost_model")),
        )

    def _deserialize_cost_model(self, raw_value: object) -> CostModelSpec:
        """恢复成本模型配置。"""
        payload = as_object_dict(raw_value, field_name="execution.cost_model")
        return CostModelSpec(
            commission_rate=read_float(
                payload.get("commission_rate", 0.0003),
                field_name="execution.cost_model.commission_rate",
            ),
            slippage_bps=read_float(
                payload.get("slippage_bps", 5.0),
                field_name="execution.cost_model.slippage_bps",
            ),
            impact_model=(read_optional_str(payload.get("impact_model")) or "linear"),
        )

    def _deserialize_constraint(
        self,
        raw_value: object,
        *,
        index: int,
    ) -> ConstraintSpec:
        """恢复单条约束配置。"""
        payload = as_object_dict(raw_value, field_name=f"constraints[{index}]")
        return ConstraintSpec(
            type=read_required_str(payload, "type"),
            params=as_object_dict(
                payload.get("params"),
                field_name=f"constraints[{index}].params",
            ),
            priority=read_int(
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
        payload = as_object_dict(
            raw_value,
            field_name=f"param_constraints[{index}]",
        )
        return ParamConstraint(
            name=read_required_str(payload, "name"),
            dtype=read_required_str(payload, "dtype"),
            min_value=read_optional_float(
                payload.get("min_value"),
                field_name=f"param_constraints[{index}].min_value",
            ),
            max_value=read_optional_float(
                payload.get("max_value"),
                field_name=f"param_constraints[{index}].max_value",
            ),
            step=read_optional_float(
                payload.get("step"),
                field_name=f"param_constraints[{index}].step",
            ),
            allowed_values=as_str_tuple(
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

    # ------------------------------------------------------------------
    # Pipeline construction
    # ------------------------------------------------------------------

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
            scoring_ascending=read_bool(
                params.get("scoring_ascending", True),
                field_name="params.scoring_ascending",
            ),
            allocation_method=read_optional_str(
                params.get("allocation_method"),
            )
            or "equal_weight",
            cash_target=read_float(
                params.get("cash_target", 0.0),
                field_name="params.cash_target",
            ),
            signal_column=read_optional_str(params.get("signal_column"))
            or "signal_value",
            max_weight=read_optional_float(
                params.get("max_weight"),
                field_name="params.max_weight",
            ),
            max_positions=read_optional_int(
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
            lookback_window=read_int(
                params.get("lookback_window", 20),
                field_name="params.lookback_window",
            ),
            trend_threshold=read_float(
                params.get("trend_threshold", 0.0),
                field_name="params.trend_threshold",
            ),
            trailing_stop_pct=read_float(
                params.get("trailing_stop_pct", 0.08),
                field_name="params.trailing_stop_pct",
            ),
            max_positions=read_int(
                params.get("max_positions", self._resolve_top_k(spec, default=10)),
                field_name="params.max_positions",
            ),
            scoring_method=self._resolve_scoring_method(spec, default="rank"),
            scoring_ascending=read_bool(
                params.get("scoring_ascending", True),
                field_name="params.scoring_ascending",
            ),
            allocation_method=read_optional_str(
                params.get("allocation_method"),
            )
            or "equal_weight",
            cash_target=read_float(
                params.get("cash_target", 0.0),
                field_name="params.cash_target",
            ),
            signal_column=read_optional_str(params.get("signal_column"))
            or "signal_value",
        )

    def _build_stock_selection_trend_config(
        self,
        spec: StrategySpec,
    ) -> StockSelectionTrendConfig:
        params = spec.params
        return StockSelectionTrendConfig(
            universe_filter=(read_optional_str(params.get("universe_filter")) or ""),
            signal_factors=as_str_tuple(
                params.get("signal_factors"),
                field_name="params.signal_factors",
            )
            or ("signal_value",),
            signal_weights=as_float_tuple(
                params.get("signal_weights"),
                field_name="params.signal_weights",
            )
            or (1.0,),
            top_k=self._resolve_top_k(spec, default=10),
            max_weight=read_float(
                params.get("max_weight", 0.15),
                field_name="params.max_weight",
            ),
            allocation_method=read_optional_str(
                params.get("allocation_method"),
            )
            or "equal_weight",
            cash_target=read_float(
                params.get("cash_target", 0.0),
                field_name="params.cash_target",
            ),
            trend_threshold=read_float(
                params.get("trend_threshold", 0.0),
                field_name="params.trend_threshold",
            ),
            rebalance_freq=read_optional_str(params.get("rebalance_freq"))
            or self._resolve_rebalance_frequency(spec.execution.frequency),
        )

    def _build_stock_sector_rotation_config(
        self,
        spec: StrategySpec,
    ) -> StockSectorRotationConfig:
        params = spec.params
        return StockSectorRotationConfig(
            sector_signal=read_optional_str(params.get("sector_signal"))
            or "signal_value",
            stock_signal=read_optional_str(params.get("stock_signal"))
            or "signal_value",
            top_sectors=read_int(
                params.get("top_sectors", 3),
                field_name="params.top_sectors",
            ),
            stocks_per_sector=read_int(
                params.get("stocks_per_sector", 3),
                field_name="params.stocks_per_sector",
            ),
            sector_weight_method=read_optional_str(
                params.get("sector_weight_method"),
            )
            or "equal_weight",
            stock_weight_method=read_optional_str(
                params.get("stock_weight_method"),
            )
            or "equal_weight",
            max_weight=read_float(
                params.get("max_weight", 0.15),
                field_name="params.max_weight",
            ),
            cash_target=read_float(
                params.get("cash_target", 0.0),
                field_name="params.cash_target",
            ),
            rebalance_freq=read_optional_str(params.get("rebalance_freq"))
            or self._resolve_rebalance_frequency(spec.execution.frequency),
        )

    # ------------------------------------------------------------------
    # Resolution helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_top_k(spec: StrategySpec, *, default: int) -> int:
        """优先使用 params.top_k，否则回落到 selector.params.k。"""
        params = spec.params
        if "top_k" in params:
            return read_int(
                params["top_k"],
                field_name="params.top_k",
            )
        selector_k = spec.selector.params.get("k")
        if selector_k is None:
            return default
        return read_int(
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
        method = read_str_value(
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
