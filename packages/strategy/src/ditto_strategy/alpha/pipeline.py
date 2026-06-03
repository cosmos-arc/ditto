"""
StrategyPipeline + StrategyInputBundle — Pipeline 编排与数据容器.

DecisionFrame schema 约定
========================
DecisionFrame 是 Pipeline 各阶段间流转的 ``pl.DataFrame``，通过列名约定
传递信息，并在 Pipeline 输入、join、stage 输出和最终组合边界做运行时
schema 校验。

必选列:
  instrument_id: InstrumentId-compatible identifier — 标的 ID（生产路径优先 int；
    实验模板仍允许字符串标识符）

可选列（由各 Stage 按需添加）:
  signal_value: float   — 信号值（SignalStage）
  score: float          — 评分（ScoringStage）
  weight: float         — 权重（AllocationStage）
  reason_codes: list[str] — 约束调整原因（ConstraintStage）

数据流转:
  input_bundle.instruments  (初始 DecisionFrame)
    -> [signal_values left join]   (可选)
    -> SignalStage.process()       (添加 signal_value)
    -> ScoringStage.process()      (添加 score)
    -> AllocationStage.process()   (添加 weight)
    -> ConstraintStage.process()   (添加 reason_codes, 调整 weight)
    -> 提取 TargetPortfolio        (instrument_id + weight -> positions)

实验模板若仍使用字符串 ``instrument_id``，可通过
``StrategyInputBundle.instrument_id_map`` 在 TargetPortfolio 边界解析到 canonical
``InstrumentId(int)``。未提供映射时保留字符串兼容路径，仅限实验模板继续运行；
promotion / golden fixture 可启用 ``require_canonical_target_ids`` 让输出边界
fail closed。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import cast

import polars as pl
from ditto_kernel import traced
from ditto_kernel.identity import InstrumentId as _InstrumentId

from ditto_strategy.alpha.context import StrategyContext
from ditto_strategy.alpha.frame import FrameCol, validate_frame
from ditto_strategy.alpha.models import TargetPortfolio
from ditto_strategy.alpha.protocols import DecisionStage
from ditto_strategy.errors import StrategySpecError

__all__ = ["StrategyInputBundle", "StrategyPipeline"]


def _empty_instrument_id_map() -> dict[object, _InstrumentId]:
    return {}


def _resolve_target_instrument_id(
    raw_id: object,
    instrument_id_map: Mapping[object, _InstrumentId],
) -> _InstrumentId:
    mapped_id = instrument_id_map.get(raw_id)
    if mapped_id is not None:
        return mapped_id
    if isinstance(raw_id, int) and not isinstance(raw_id, bool):
        return _InstrumentId(raw_id)
    return cast(_InstrumentId, raw_id)


def _validate_canonical_target_ids(
    positions: Mapping[_InstrumentId, float],
    *,
    boundary: str,
) -> None:
    non_canonical_ids = tuple(
        str(instrument_id)
        for instrument_id in positions
        if not _is_canonical_instrument_id(instrument_id)
    )
    if non_canonical_ids:
        raise StrategySpecError(
            "TargetPortfolio contains non-canonical instrument IDs",
            details={
                "boundary": boundary,
                "non_canonical_instrument_ids": non_canonical_ids,
            },
        )


def _is_canonical_instrument_id(instrument_id: object) -> bool:
    return isinstance(instrument_id, int) and not isinstance(instrument_id, bool)


@dataclass(frozen=True)
class StrategyInputBundle:
    """
    Pipeline 输入数据容器 — 由 Port 层组装。

    封装一次 Pipeline 运行所需的全部输入数据，包括标的列表、
    市场数据、预计算信号值和参数覆盖。

    Attributes:
        trade_date: 交易日期 (YYYY-MM-DD)
        strategy_id: 策略 ID
        run_id: 运行 ID
        instruments: 标的 DataFrame，至少包含 ``instrument_id`` 列
        market_data: 市场数据 DataFrame（OHLCV 等）
        signal_values: 预计算信号值（可选），包含 ``instrument_id`` +
            ``signal_value`` 列
        parameters: 参数覆盖
        benchmark_close: 基准收盘价（可选）
        instrument_id_map: 实验模板字符串 ID 到 canonical ``InstrumentId`` 的映射
        require_canonical_target_ids: 是否要求 TargetPortfolio 输出只包含
            canonical ``InstrumentId(int)`` key

    """

    trade_date: str
    strategy_id: str
    run_id: str
    instruments: pl.DataFrame
    market_data: pl.DataFrame
    signal_values: pl.DataFrame | None = None
    parameters: dict[str, object] = field(default_factory=dict)
    benchmark_close: float | None = None
    instrument_id_map: Mapping[object, _InstrumentId] = field(
        default_factory=_empty_instrument_id_map,
    )
    require_canonical_target_ids: bool = False


class StrategyPipeline:
    """
    策略决策 Pipeline — 顺序编排 DecisionStage.

    Pipeline 是无状态的：相同 ``(context, input_bundle)`` 输入总是
    产生相同的 ``TargetPortfolio`` 输出。

    Parameters
    ----------
        stages: DecisionStage 序列，按顺序执行

    """

    def __init__(self, stages: Sequence[DecisionStage]) -> None:
        self._stages = tuple(stages)

    @traced("engine.alpha.pipeline.process")
    def run(
        self,
        context: StrategyContext,
        input_bundle: StrategyInputBundle,
    ) -> TargetPortfolio:
        """
        执行完整 Pipeline，返回 TargetPortfolio.

        流程:
          1. 从 ``input_bundle.instruments`` 构建初始 DecisionFrame
          2. 若有 ``signal_values``，left join 到 frame
          3. 顺序执行每个 ``stage.process(frame, context)``
          4. 从最终 frame 提取 ``TargetPortfolio``
             - 若有 ``weight`` 列，直接提取
             - 若无 ``weight`` 列，使用 equal_weight 兜底

        """
        # Step 1: 初始 DecisionFrame
        frame = input_bundle.instruments.clone()
        validate_frame(
            frame,
            (FrameCol.INSTRUMENT_ID,),
            boundary="input_bundle.instruments",
        )

        # Step 2: 可选 signal_values join
        if input_bundle.signal_values is not None:
            validate_frame(
                input_bundle.signal_values,
                (FrameCol.INSTRUMENT_ID,),
                boundary="input_bundle.signal_values",
            )
            frame = frame.join(
                input_bundle.signal_values,
                on=FrameCol.INSTRUMENT_ID,
                how="left",
            )
            validate_frame(frame, (FrameCol.INSTRUMENT_ID,), boundary="initial_join")

        # Step 3: 顺序执行 stages
        for stage in self._stages:
            frame = stage.process(frame, context)
            validate_frame(
                frame,
                (FrameCol.INSTRUMENT_ID,),
                boundary="stage_output",
                stage_name=stage.__class__.__name__,
            )

        # Step 4: 从最终 frame 提取 TargetPortfolio
        return self._build_target_portfolio(frame, input_bundle)

    def _build_target_portfolio(
        self,
        frame: pl.DataFrame,
        input_bundle: StrategyInputBundle,
    ) -> TargetPortfolio:
        """
        从最终 DecisionFrame 构建 TargetPortfolio.

        若 frame 包含 ``weight`` 列，直接提取；否则使用 equal_weight 兜底。
        """
        n_rows = frame.height
        if n_rows == 0:
            return TargetPortfolio(
                trade_date=input_bundle.trade_date,
                strategy_id=input_bundle.strategy_id,
                run_id=input_bundle.run_id,
                positions={},
            )

        validate_frame(frame, (FrameCol.INSTRUMENT_ID,), boundary="target_portfolio")

        if FrameCol.WEIGHT in frame.columns:
            rows = frame.select(FrameCol.INSTRUMENT_ID, FrameCol.WEIGHT).rows()
            positions: dict[_InstrumentId, float] = {
                _resolve_target_instrument_id(
                    row[0],
                    input_bundle.instrument_id_map,
                ): float(row[1])
                for row in rows
            }
        else:
            # Equal weight fallback
            equal_weight = 1.0 / n_rows
            ids = frame.get_column(FrameCol.INSTRUMENT_ID).to_list()
            positions = {
                _resolve_target_instrument_id(
                    instrument_id,
                    input_bundle.instrument_id_map,
                ): equal_weight
                for instrument_id in ids
            }

        if input_bundle.require_canonical_target_ids:
            _validate_canonical_target_ids(
                positions,
                boundary="target_portfolio",
            )

        return TargetPortfolio(
            trade_date=input_bundle.trade_date,
            strategy_id=input_bundle.strategy_id,
            run_id=input_bundle.run_id,
            positions=positions,
        )
