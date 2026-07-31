"""
因子桥接 — 字符串表达式 → 编译 → 信号计算 + 回测因子 bundle 构建.

FactorBridge 将声明式因子表达式字符串桥接到回测引擎的信号流中：
  1. 字符串表达式 → DerivedSpec → ExpressionCompiler → pl.Expr
  2. 多因子 rank 归一化 + 加权合成 → signal_value 列

同时提供模块级函数用于构建因子感知的 StrategyInputBundle。
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass, fields
from datetime import date
from math import isfinite
from typing import Any, cast

import orjson
import polars as pl
from ditto_backtest.data_feed import DataFeed
from ditto_backtest.steps import StepContext
from ditto_features.derived_types import (
    DerivedRole,
    DerivedSpec,
    MaterializationProfile,
)
from ditto_features.expression.compiler import ExpressionCompiler
from ditto_features.expression.contracts import (
    Analysis,
    AnalysisWarning,
    CompiledDerivedExpression,
    CompileIdentity,
)
from ditto_features.expression.diagnostics import ExpressionCompileError
from ditto_features.factors.factor_specs import ALL_FACTOR_SPECS
from ditto_features.factors.spec import FactorSpec
from ditto_kernel.identity import InstrumentId
from ditto_kernel.strategy import ExecutionPolicy
from ditto_strategy.alpha.pipeline import StrategyInputBundle

from ditto_application.contracts import REGIME_DEFAULT_LOOKBACK
from ditto_application.exceptions import AppProcessError

__all__ = [
    "CompiledExpressions",
    "FactorBridge",
    "build_factor_aware_bundle_builder",
    "build_factor_bundle",
    "build_signal_spec",
    "compiled_expressions_actual_max_lookback",
    "compiled_expressions_execution_hash",
    "factor_normalized_column",
    "factor_value_column",
]


def factor_value_column(index: int) -> str:
    """Return the stable materialized value column for one compiled factor."""
    return f"factor_{index}"


def factor_normalized_column(index: int) -> str:
    """Return the stable rank-normalized column for one compiled factor."""
    return f"rank_{factor_value_column(index)}"


def _validate_factor_weight(value: object, *, index: int) -> None:
    """Reject booleans, non-numbers, and non-finite values at the typed seam."""
    if (
        isinstance(value, bool)
        or not isinstance(value, int | float)
        or not isfinite(value)
    ):
        raise AppProcessError(
            f"factor weight must be a finite number: weights[{index}]",
            details={
                "code": "SPEC_INVALID",
                "reason": "invalid_factor_weight",
                "weight_index": index,
            },
        )


def build_signal_spec(
    expr_str: str,
    index: int,
    *,
    derived_id: str | None = None,
    version: int = 1,
) -> DerivedSpec:
    """
    从表达式字符串构建信号 DerivedSpec.

    统一默认值: role=SIGNAL, materialization_profile=SERIES,
    entity_keys=("instrument_id",), grain="1d", calendar="cn_stock".

    Args:
        expr_str: 因子表达式字符串（如 ``"ts_mean(close, 20)"``）。
        index: 因子序号，用于生成 ``signal_{index}`` 形式的 id。
        derived_id: 可选的精确注册因子 ID；普通 legacy 路径保持 ``signal_{index}``。
        version: ``derived_id`` 对应的精确注册版本。

    Returns:
        配置好默认值的 ``DerivedSpec``。

    """
    return DerivedSpec(
        id=derived_id if derived_id is not None else f"signal_{index}",
        version=version,
        role=DerivedRole.SIGNAL,
        materialization_profile=MaterializationProfile.SERIES,
        expression=expr_str,
        entity_keys=("instrument_id",),
        grain="1d",
        calendar="cn_stock",
        execution_policy=ExecutionPolicy(),
    )


@dataclass(frozen=True)
class CompiledExpressions:
    """编译后的因子表达式集合."""

    expressions: tuple[CompiledDerivedExpression, ...]
    weights: tuple[float, ...]


def _require_exact_dataclass_state(value: object, *, reason: str) -> None:
    try:
        actual = set(vars(value))
    except TypeError:
        raise AppProcessError(
            "compiled factor execution state is invalid",
            details={"code": "REPRODUCIBILITY_FAILED", "reason": reason},
        ) from None
    expected = {item.name for item in fields(cast("Any", value))}
    if actual != expected:
        raise AppProcessError(
            "compiled factor execution state is invalid",
            details={"code": "REPRODUCIBILITY_FAILED", "reason": reason},
        )


def _require_exact_polars_expression_state(expression: object) -> pl.Expr:
    if type(expression) is not pl.Expr:
        raise AppProcessError(
            "compiled factor execution state is invalid",
            details={
                "code": "REPRODUCIBILITY_FAILED",
                "reason": "compiled_factor_expression_state_drift",
            },
        )
    actual: set[str]
    try:
        actual = set(vars(expression))
    except TypeError:
        actual = set()
    if actual != {"_pyexpr"}:
        raise AppProcessError(
            "compiled factor execution state is invalid",
            details={
                "code": "REPRODUCIBILITY_FAILED",
                "reason": "compiled_factor_expression_state_drift",
            },
        )
    return expression


def _analysis_execution_payload(analysis: Analysis) -> dict[str, object]:
    _require_exact_dataclass_state(
        analysis,
        reason="compiled_factor_analysis_state_drift",
    )
    if type(analysis.warnings) is not tuple or any(
        type(item) is not AnalysisWarning for item in analysis.warnings
    ):
        raise AppProcessError(
            "compiled factor execution state is invalid",
            details={
                "code": "REPRODUCIBILITY_FAILED",
                "reason": "compiled_factor_analysis_state_drift",
            },
        )
    warnings: list[dict[str, str]] = []
    for warning in analysis.warnings:
        _require_exact_dataclass_state(
            warning,
            reason="compiled_factor_analysis_state_drift",
        )
        warnings.append({"error_code": warning.error_code, "message": warning.message})
    return {
        "dependencies": list(analysis.dependencies),
        "lookback": analysis.lookback,
        "operator_names": list(analysis.operator_names),
        "output_schema": list(analysis.output_schema),
        "requires_full_day": analysis.requires_full_day,
        "scope": analysis.scope,
        "warnings": warnings,
    }


def _compile_identity_execution_payload(
    identity: CompileIdentity,
) -> dict[str, object]:
    _require_exact_dataclass_state(
        identity,
        reason="compiled_factor_identity_state_drift",
    )
    return {
        "analysis_version": identity.analysis_version,
        "cache_key": identity.cache_key,
        "compile_input_hash": identity.compile_input_hash,
        "compiler_fingerprint": identity.compiler_fingerprint,
        "engine_codegen_version": identity.engine_codegen_version,
        "expr_serialization_format": identity.expr_serialization_format,
        "global_compile_flags": list(identity.global_compile_flags),
        "operator_fingerprint": identity.operator_fingerprint,
        "operator_versions": [list(item) for item in identity.operator_versions],
        "polars_version": identity.polars_version,
    }


def compiled_expressions_execution_hash(
    compiled: CompiledExpressions | None,
) -> str:
    """Hash the exact expressions and weights consumed by numerical execution."""
    payload: dict[str, object] = {
        "schema": "ditto.compiled-factor-execution.v1",
        "compiled": None,
    }
    if compiled is not None:
        if type(compiled) is not CompiledExpressions:
            raise AppProcessError(
                "compiled factor execution state is invalid",
                details={
                    "code": "REPRODUCIBILITY_FAILED",
                    "reason": "compiled_factor_set_state_drift",
                },
            )
        _require_exact_dataclass_state(
            compiled,
            reason="compiled_factor_set_state_drift",
        )
        if (
            type(compiled.expressions) is not tuple
            or type(compiled.weights) is not tuple
            or len(compiled.expressions) != len(compiled.weights)
            or any(
                type(weight) is not float or not isfinite(weight)
                for weight in compiled.weights
            )
        ):
            raise AppProcessError(
                "compiled factor execution state is invalid",
                details={
                    "code": "REPRODUCIBILITY_FAILED",
                    "reason": "compiled_factor_set_state_drift",
                },
            )
        expressions: list[dict[str, object]] = []
        for expression in compiled.expressions:
            if type(expression) is not CompiledDerivedExpression:
                raise AppProcessError(
                    "compiled factor execution state is invalid",
                    details={
                        "code": "REPRODUCIBILITY_FAILED",
                        "reason": "compiled_factor_expression_state_drift",
                    },
                )
            _require_exact_dataclass_state(
                expression,
                reason="compiled_factor_expression_state_drift",
            )
            if (
                type(expression.analysis) is not Analysis
                or type(expression.compile_identity) is not CompileIdentity
            ):
                raise AppProcessError(
                    "compiled factor execution state is invalid",
                    details={
                        "code": "REPRODUCIBILITY_FAILED",
                        "reason": "compiled_factor_expression_state_drift",
                    },
                )
            polars_expression = _require_exact_polars_expression_state(expression.expr)
            try:
                serialized = polars_expression.meta.serialize()
            except (AttributeError, TypeError, ValueError, pl.exceptions.PolarsError):
                raise AppProcessError(
                    "compiled factor expression cannot be serialized",
                    details={
                        "code": "REPRODUCIBILITY_FAILED",
                        "reason": "compiled_factor_serialization_unavailable",
                    },
                ) from None
            if type(serialized) is not bytes:
                raise AppProcessError(
                    "compiled factor expression cannot be serialized",
                    details={
                        "code": "REPRODUCIBILITY_FAILED",
                        "reason": "compiled_factor_serialization_unavailable",
                    },
                )
            expressions.append(
                {
                    "analysis": _analysis_execution_payload(expression.analysis),
                    "compile_identity": _compile_identity_execution_payload(
                        expression.compile_identity
                    ),
                    "derived_id": expression.derived_id,
                    "expression_sha256": hashlib.sha256(serialized).hexdigest(),
                    "version": expression.version,
                }
            )
        payload["compiled"] = {
            "expressions": expressions,
            "weights_hex": [weight.hex() for weight in compiled.weights],
        }
    return hashlib.sha256(
        orjson.dumps(payload, option=orjson.OPT_SORT_KEYS)
    ).hexdigest()


def compiled_expressions_actual_max_lookback(
    compiled: CompiledExpressions | None,
) -> int:
    """Return the maximum lookback from one strictly validated compiled set."""
    compiled_expressions_execution_hash(compiled)
    if compiled is None:
        return 0
    lookbacks = tuple(
        expression.analysis.lookback for expression in compiled.expressions
    )
    if any(type(lookback) is not int or lookback < 0 for lookback in lookbacks):
        raise AppProcessError(
            "compiled factor lookback state is invalid",
            details={
                "code": "REPRODUCIBILITY_FAILED",
                "reason": "compiled_factor_lookback_state_drift",
            },
        )
    return max(lookbacks, default=0)


class FactorBridge:
    """因子桥接 — 字符串表达式 → 编译 → 信号计算."""

    def __init__(
        self,
        compiler: ExpressionCompiler | None = None,
        *,
        factor_registry: Mapping[str, FactorSpec] | None = None,
        factor_versions: Mapping[str, int] | None = None,
        require_registered_factor_ids: bool = False,
    ) -> None:
        self._compiler = compiler if compiler is not None else ExpressionCompiler()
        # 因子 ID → 真实表达式的解析 registry。默认用 ALL_FACTOR_SPECS，
        # 使 seed 的 signal_expressions（如 quality_roe）解析为底层表达式（如 roe）。
        # 未命中项原样返回，兼容直接传表达式字符串（如 "close"）。
        self._registry: Mapping[str, FactorSpec] = (
            factor_registry if factor_registry is not None else ALL_FACTOR_SPECS
        )
        self._factor_versions: Mapping[str, int] = (
            factor_versions
            if factor_versions is not None
            else dict.fromkeys(self._registry, 1)
        )
        self._require_registered_factor_ids = require_registered_factor_ids

    def _resolve_expression(self, expr_or_id: str) -> str:
        """Resolve a factor ID while preserving legacy raw-expression behavior."""
        spec = self._registry.get(expr_or_id)
        if spec is None:
            if self._require_registered_factor_ids:
                raise AppProcessError(
                    f"unknown registered factor: {expr_or_id}",
                    details={
                        "code": "SPEC_INVALID",
                        "reason": "unknown_registered_factor",
                        "factor_id": expr_or_id,
                    },
                )
            return expr_or_id
        if not self._require_registered_factor_ids:
            return spec.expression
        if spec.computation_type != "expression":
            raise AppProcessError(
                f"research factor executor is unavailable: {expr_or_id}",
                details={
                    "code": "EXECUTOR_UNAVAILABLE",
                    "reason": "research_factor_executor_unavailable",
                    "factor_id": expr_or_id,
                    "computation_type": spec.computation_type,
                },
            )
        return spec.expression

    def _resolve_compilation_identity(
        self,
        expr_or_id: str,
    ) -> tuple[str | None, int]:
        if not self._require_registered_factor_ids:
            return None, 1
        version = self._factor_versions.get(expr_or_id)
        if type(version) is not int or version <= 0:
            raise AppProcessError(
                f"registered factor version is invalid: {expr_or_id}",
                details={
                    "code": "SPEC_INVALID",
                    "reason": "invalid_registered_factor_version",
                    "factor_id": expr_or_id,
                },
            )
        return expr_or_id, version

    def compile_and_validate(
        self,
        expressions: tuple[str, ...],
        weights: tuple[float, ...],
    ) -> CompiledExpressions:
        """
        编译并验证因子表达式.

        Args:
            expressions: 因子表达式字符串元组。
            weights: 对应权重元组。

        Returns:
            ``CompiledExpressions`` 包含编译后的 ``pl.Expr``。

        Raises:
            ValueError: 表达式为空、权重不匹配、权重非负、编译失败。

        """
        if not expressions:
            msg = "表达式不能为空"
            raise AppProcessError(msg)

        if len(expressions) != len(weights):
            msg = f"权重数量 ({len(weights)}) 与表达式数量 ({len(expressions)}) 不匹配"
            raise AppProcessError(msg)

        if self._require_registered_factor_ids and len(expressions) != len(
            set(expressions)
        ):
            raise AppProcessError(
                "registered factor IDs cannot be duplicated",
                details={
                    "code": "SPEC_INVALID",
                    "reason": "duplicate_registered_factor",
                    "factor_ids": expressions,
                },
            )

        for i, w in enumerate(weights):
            _validate_factor_weight(w, index=i)
            if w < 0:
                msg = f"权重不能为负: weights[{i}] = {w}"
                raise AppProcessError(msg)

        compiled: list[CompiledDerivedExpression] = []
        for i, expr_str in enumerate(expressions):
            resolved = self._resolve_expression(expr_str)
            derived_id, version = self._resolve_compilation_identity(expr_str)
            spec = build_signal_spec(
                resolved,
                index=i,
                derived_id=derived_id,
                version=version,
            )
            try:
                result = self._compiler.compile(spec)
            except ExpressionCompileError as exc:
                msg = f"编译失败 (signal_{i}): {exc}"
                raise AppProcessError(msg) from exc
            compiled.append(result)

        return CompiledExpressions(
            expressions=tuple(compiled),
            weights=weights,
        )

    def compute_signals(
        self,
        df: pl.DataFrame,
        compiled: CompiledExpressions,
    ) -> pl.DataFrame:
        """
        在 DataFrame 上计算因子值并合成 signal_value.

        步骤:
          1. ``df.with_columns([expr.alias(f"factor_{i}") for each compiled expr])``
          2. 各因子列 ``cs_rank()`` 归一化
          3. ``signal_value = sum(rank_f_i * w_i) / sum(w_i)``

        Args:
            df: 包含 ``instrument_id`` + 底层列的 DataFrame。
            compiled: 编译后的表达式集合。

        Returns:
            包含 ``instrument_id``、编译后 factor/rank 列与 ``signal_value``
            的 DataFrame；factor/rank 列供 strategy scoring 原路径审计。

        """
        compiled_expressions_execution_hash(compiled)
        if df.height == 0:
            evidence_columns = tuple(
                column
                for index in range(len(compiled.expressions))
                for column in (
                    factor_value_column(index),
                    factor_normalized_column(index),
                )
            )
            schema = pl.Schema(
                (
                    ("instrument_id", df["instrument_id"].dtype),
                    *((column, pl.Float64) for column in evidence_columns),
                    ("signal_value", pl.Float64),
                )
            )
            return pl.DataFrame(schema=schema)

        # Step 1: 计算各因子列
        factor_columns: list[str] = []
        factor_exprs: list[pl.Expr] = []
        for i, compiled_expr in enumerate(compiled.expressions):
            col_name = factor_value_column(i)
            factor_columns.append(col_name)
            factor_exprs.append(pl.Expr.alias(compiled_expr.expr, col_name))

        enriched = df.with_columns(factor_exprs)

        # Step 2: rank 归一化各因子列
        # 当包含 trade_date 列（历史窗口）时，rank 只在最后一天截面上操作
        has_trade_date = "trade_date" in enriched.columns
        if has_trade_date:
            # 因子表达式可能产生 null（如历史不足），取每个标的最后一天的非 null 值
            last_day = enriched.group_by("instrument_id").last()
            enriched = last_day
            # 重新获取 factor_columns dtype
            enriched = enriched.with_columns(
                [
                    pl.col(c).cast(pl.Float64)
                    for c in factor_columns
                    if enriched[c].dtype != pl.Float64
                ],
            )

        rank_exprs: list[pl.Expr] = []
        for index, col_name in enumerate(factor_columns):
            rank_exprs.append(
                (
                    pl.col(col_name).rank(method="average").cast(pl.Float64)
                    / pl.len().cast(pl.Float64)
                ).alias(factor_normalized_column(index)),
            )

        enriched = enriched.with_columns(rank_exprs)

        # Step 3: 加权合成 signal_value
        weight_sum = sum(compiled.weights)
        if weight_sum == 0:
            # 所有权重为零时，signal_value 全部为零
            return enriched.select(
                "instrument_id",
                *factor_columns,
                *(factor_normalized_column(i) for i in range(len(factor_columns))),
                pl.lit(0.0).alias("signal_value"),
            )

        weighted_sum = pl.lit(0.0)
        for i, w in enumerate(compiled.weights):
            if w == 0:
                continue
            rank_col = factor_normalized_column(i)
            weighted_sum = weighted_sum + pl.col(rank_col) * w

        return enriched.select(
            "instrument_id",
            *factor_columns,
            *(factor_normalized_column(i) for i in range(len(factor_columns))),
            (weighted_sum / weight_sum).alias("signal_value"),
        )


# ---------------------------------------------------------------------------
# Module-level functions for backtest factor bundle building
# ---------------------------------------------------------------------------


def build_factor_aware_bundle_builder(
    *,
    bridge: FactorBridge,
    compiled: CompiledExpressions,
    data_feed: DataFeed,
    strategy_id: str,
    run_id: str,
) -> Callable[[StepContext], StrategyInputBundle]:
    """
    构建含因子信号注入的 input_bundle_builder.

    当 data_feed 可用时，会在 market_data 中包含历史窗口，
    使 ts_* 时间序列表达式（如 ts_mean, shift）能正确计算。

    Args:
        bridge: 因子桥接器实例。
        compiled: 编译后的因子表达式。
        data_feed: 市场数据源。
        strategy_id: 策略标识。
        run_id: 由 run() 统一生成的运行标识，确保 bundle.run_id 与 run record 一致。

    Returns:
        接收 StepContext、返回 StrategyInputBundle 的可调用对象。

    """
    lookback_days = max(
        (expr.analysis.lookback for expr in compiled.expressions),
        default=REGIME_DEFAULT_LOOKBACK,
    )

    def _build(ctx: StepContext) -> StrategyInputBundle:
        return build_factor_bundle(
            ctx=ctx,
            strategy_id=strategy_id,
            run_id=run_id,
            bridge=bridge,
            compiled=compiled,
            data_feed=data_feed,
            lookback_days=lookback_days,
        )

    return _build


def build_factor_bundle(
    *,
    ctx: StepContext,
    strategy_id: str,
    run_id: str,
    bridge: FactorBridge,
    compiled: CompiledExpressions,
    data_feed: DataFeed,
    lookback_days: int,
) -> StrategyInputBundle:
    """
    构建单日因子感知的 StrategyInputBundle.

    从 StepContext 提取当日行情，可选追加历史窗口数据，
    通过 FactorBridge 计算信号值并组装完整的输入包。

    Args:
        ctx: 引擎步骤上下文（含 date 和 slice_）。
        strategy_id: 策略标识。
        run_id: 运行标识。
        bridge: 因子桥接器。
        compiled: 编译后的因子表达式。
        data_feed: 市场数据源（需支持 get_history）。
        lookback_days: 历史回溯天数。

    """
    slice_ = ctx.slice_
    if slice_ is None:
        msg = "slice_ required"
        raise AppProcessError(msg)
    bars = slice_.bars
    instrument_ids = list(bars.keys())

    instruments = pl.DataFrame({"instrument_id": instrument_ids})

    # 构建当日 OHLCV
    market_rows: list[dict[str, object]] = []
    for iid, bar in bars.items():
        market_rows.append(
            {
                "instrument_id": int(iid),
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume,
                "trade_date": ctx.time_context.trade_date,
            },
        )

    # 追加历史窗口 — 支持 ts_* 时间序列表达式。
    # PIT: history uses knowledge_date as the strict as_of boundary; current
    # trade_date bars are already supplied by the slice above.
    history_df = data_feed.get_history(
        instrument_ids,
        ctx.time_context.knowledge_date.isoformat(),
        lookback_days,
    )
    if not history_df.is_empty():
        hist_rows = history_df.select(
            "instrument_id",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "trade_date",
        ).to_dicts()
        for row in hist_rows:
            market_rows.append(row)

    market_data = pl.DataFrame(market_rows)
    if "trade_date" in market_data.columns:
        market_data = market_data.sort("trade_date")

    # 注入基本面截面（PIT as_of = knowledge_date），供 quality_roe / value_pe 等
    # 基本面因子引用底层列（roe / pe_ratio）。截面只 merge 到当日行。
    market_data = _enrich_with_fundamentals(
        market_data,
        data_feed=data_feed,
        instrument_ids=instrument_ids,
        knowledge_date=ctx.time_context.knowledge_date,
        trade_date=ctx.time_context.trade_date,
    )
    # 注入行业分类截面(sector_id),供 stock_sector_rotation 结构列校验与
    # 因子中性化(neutralize_by="sector_id")使用。PIT as_of = knowledge_date。
    market_data = _enrich_with_classification(
        market_data,
        data_feed=data_feed,
        instrument_ids=instrument_ids,
        knowledge_date=ctx.time_context.knowledge_date,
        trade_date=ctx.time_context.trade_date,
    )

    signal_values = bridge.compute_signals(market_data, compiled)

    return StrategyInputBundle(
        trade_date=ctx.time_context.trade_date,
        strategy_id=strategy_id,
        run_id=run_id,
        instruments=instruments,
        market_data=market_data,
        signal_values=signal_values,
        benchmark_close=getattr(slice_, "benchmark_close", None),
    )


def _enrich_with_fundamentals(
    market_data: pl.DataFrame,
    *,
    data_feed: DataFeed,
    instrument_ids: list[InstrumentId],
    knowledge_date: date,
    trade_date: str,
) -> pl.DataFrame:
    """
    注入基本面截面到当日行并补算 pe_ratio.

    基本面是截面快照（1 行/instrument），仅 merge 到当日行（trade_date 匹配），
    历史行补 null。pe_ratio 依赖当日 close + 基本面 eps，在 merge 后补算。
    PIT as_of = knowledge_date（严格，非 trade_date），由 data_feed 透传。

    无基本面数据或无当日行时原样返回。
    """
    if market_data.is_empty() or not instrument_ids:
        return market_data

    fundamental_df = data_feed.get_fundamental_snapshot(instrument_ids, knowledge_date)
    if fundamental_df.is_empty():
        return market_data

    today_mask = market_data["trade_date"] == trade_date
    today_rows = market_data.filter(today_mask)
    if today_rows.is_empty():
        return market_data

    history_rows = market_data.filter(~today_mask)
    today_rows = today_rows.join(fundamental_df, on="instrument_id", how="left")

    # 补算 pe_ratio（当日 close / 基本面 eps）；pb_ratio 暂无数据源（无 total_shares）。
    if "eps" in today_rows.columns and "close" in today_rows.columns:
        today_rows = today_rows.with_columns(
            pl.when(pl.col("eps") != 0)
            .then(pl.col("close") / pl.col("eps"))
            .otherwise(None)
            .cast(pl.Float64)
            .alias("pe_ratio"),
        )

    enriched = pl.concat([today_rows, history_rows], how="diagonal_relaxed")
    if "trade_date" in enriched.columns:
        enriched = enriched.sort("trade_date")
    return enriched


def _enrich_with_classification(
    market_data: pl.DataFrame,
    *,
    data_feed: DataFeed,
    instrument_ids: list[InstrumentId],
    knowledge_date: date,
    trade_date: str,
) -> pl.DataFrame:
    """
    注入行业分类截面(sector_id)到当日行.

    分类是截面快照(1 行/instrument),仅 merge 到当日行(trade_date 匹配),
    历史行补 null。PIT as_of = knowledge_date(严格,非 trade_date),由 data_feed 透传。

    无分类数据或无当日行时原样返回。
    """
    if market_data.is_empty() or not instrument_ids:
        return market_data

    classification_df = data_feed.get_classification_snapshot(
        instrument_ids,
        knowledge_date,
    )
    if classification_df.is_empty():
        return market_data

    today_mask = market_data["trade_date"] == trade_date
    today_rows = market_data.filter(today_mask)
    if today_rows.is_empty():
        return market_data

    history_rows = market_data.filter(~today_mask)
    today_rows = today_rows.join(classification_df, on="instrument_id", how="left")

    enriched = pl.concat([today_rows, history_rows], how="diagonal_relaxed")
    if "trade_date" in enriched.columns:
        enriched = enriched.sort("trade_date")
    return enriched
