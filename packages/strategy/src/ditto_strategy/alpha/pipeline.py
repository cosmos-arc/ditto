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

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from itertools import pairwise
from types import MappingProxyType
from typing import cast

import polars as pl
from ditto_kernel import traced
from ditto_kernel.identity import InstrumentId as _InstrumentId

from ditto_strategy.alpha.context import StrategyContext
from ditto_strategy.alpha.frame import FrameCol, validate_frame
from ditto_strategy.alpha.models import TargetPortfolio
from ditto_strategy.alpha.node_registry import NodeDescriptor, NodeRegistry
from ditto_strategy.alpha.nodes import NodeCategory, PipelineSpec
from ditto_strategy.alpha.protocols import DecisionStage
from ditto_strategy.alpha.selection_evidence import (
    InitialUniverseEvidence,
    SelectionEvidenceSink,
)
from ditto_strategy.alpha.specs import StrategyKind
from ditto_strategy.errors import StrategySpecError

__all__ = [
    "CompiledNode",
    "CompiledNodePipeline",
    "StrategyInputBundle",
    "StrategyPipeline",
    "compile_node_pipeline",
]

_REQUIRED_NODE_CATEGORIES = tuple(
    category for category in NodeCategory if category is not NodeCategory.FILTER
)


@dataclass(frozen=True)
class CompiledNode:
    """一个已完成 descriptor/config 解析的执行节点。"""

    node_id: str
    descriptor: NodeDescriptor
    config: Mapping[str, object]

    @property
    def category(self) -> NodeCategory:
        """返回 descriptor 唯一拥有的 category。"""
        return self.descriptor.category

    @property
    def implementation_key(self) -> str:
        """返回 application adapter 使用的稳定 key。"""
        return self.descriptor.implementation_key


@dataclass(frozen=True)
class CompiledNodePipeline:
    """受约束编译结果；不携带 callable 或第二套 runner。"""

    nodes: tuple[CompiledNode, ...]
    registry_manifest_hash: str
    required_datasets: tuple[str, ...]


def _compile_error(
    message: str,
    *,
    reason: str,
    **details: object,
) -> StrategySpecError:
    payload: dict[str, object] = {"reason": reason}
    payload.update(details)
    return StrategySpecError(message, details=payload)


def _validate_compiled_cardinality(nodes: tuple[CompiledNode, ...]) -> None:
    counts = Counter(node.category for node in nodes)
    invalid = {
        category.value: counts[category]
        for category in _REQUIRED_NODE_CATEGORIES
        if counts[category] != 1
    }
    if invalid:
        raise _compile_error(
            "Pipeline violates required node cardinality",
            reason="invalid_node_cardinality",
            category_counts=invalid,
        )


def _validate_compiled_ports(nodes: tuple[CompiledNode, ...]) -> None:
    for upstream, downstream in pairwise(nodes):
        if upstream.descriptor.output_contract != downstream.descriptor.input_contract:
            raise _compile_error(
                "Pipeline has an adjacent port contract mismatch",
                reason="node_port_mismatch",
                upstream_node_id=upstream.node_id,
                upstream_output=upstream.descriptor.output_contract,
                downstream_node_id=downstream.node_id,
                downstream_input=downstream.descriptor.input_contract,
            )


def _resolved_required_datasets(
    nodes: tuple[CompiledNode, ...],
) -> tuple[str, ...]:
    datasets: set[str] = set()
    for node in nodes:
        datasets.update(node.descriptor.required_datasets)
        configured = node.config.get("required_datasets")
        if isinstance(configured, tuple):
            items = cast("tuple[object, ...]", configured)
            if all(isinstance(item, str) for item in items):
                datasets.update(cast(str, item) for item in items)
    return tuple(sorted(datasets))


def _require_pipeline_spec(value: object) -> PipelineSpec:
    if not isinstance(value, PipelineSpec):
        raise _compile_error(
            "compile_node_pipeline requires PipelineSpec",
            reason="invalid_pipeline_spec",
        )
    return value


def _require_node_registry(value: object) -> NodeRegistry:
    if not isinstance(value, NodeRegistry):
        raise _compile_error(
            "compile_node_pipeline requires NodeRegistry",
            reason="invalid_node_registry",
        )
    return value


def _require_strategy_kind(value: object) -> StrategyKind:
    if not isinstance(value, StrategyKind):
        raise _compile_error(
            "compile_node_pipeline requires StrategyKind",
            reason="invalid_strategy_kind",
        )
    return value


def compile_node_pipeline(
    pipeline: PipelineSpec,
    *,
    registry: NodeRegistry,
    strategy_kind: StrategyKind,
) -> CompiledNodePipeline:
    """按 fixed grammar 解析 descriptor、配置、lane、cardinality 和 ports。"""
    pipeline_value = _require_pipeline_spec(pipeline)
    registry_value = _require_node_registry(registry)
    strategy_kind_value = _require_strategy_kind(strategy_kind)

    nodes_by_id = {node.node_id: node for node in pipeline_value.nodes}
    compiled: list[CompiledNode] = []
    for node_id in pipeline_value.sequence:
        node = nodes_by_id[node_id]
        descriptor = registry_value.lookup(node.ref)
        if descriptor.category is not node.category:
            raise _compile_error(
                "Node instance category does not match its descriptor category",
                reason="node_category_mismatch",
                node_id=node.node_id,
                instance_category=node.category.value,
                descriptor_category=descriptor.category.value,
            )
        if strategy_kind_value not in descriptor.supported_strategy_kinds:
            raise _compile_error(
                "Node descriptor does not support this strategy kind",
                reason="unsupported_strategy_kind",
                node_id=node.node_id,
                strategy_kind=strategy_kind_value.value,
            )
        resolved_config = descriptor.resolve_config(node.config)
        if node.enabled:
            compiled.append(
                CompiledNode(
                    node_id=node.node_id,
                    descriptor=descriptor,
                    config=MappingProxyType(dict(resolved_config)),
                ),
            )

    result_nodes = tuple(compiled)
    _validate_compiled_cardinality(result_nodes)
    _validate_compiled_ports(result_nodes)
    return CompiledNodePipeline(
        nodes=result_nodes,
        registry_manifest_hash=registry_value.manifest_hash,
        required_datasets=_resolved_required_datasets(result_nodes),
    )


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

    def __init__(
        self,
        stages: Sequence[DecisionStage],
        *,
        evidence_sink: SelectionEvidenceSink | None = None,
    ) -> None:
        self._stages = tuple(stages)
        self._evidence_sink = evidence_sink

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
        if self._evidence_sink is not None:
            self._evidence_sink.begin_rebalance(input_bundle.trade_date)

        # Step 1: 初始 DecisionFrame
        frame = input_bundle.instruments.clone()
        validate_frame(
            frame,
            (FrameCol.INSTRUMENT_ID,),
            boundary="input_bundle.instruments",
        )
        self._validate_unique_evidence_instruments(
            frame,
            trade_date=input_bundle.trade_date,
            boundary="input_bundle.instruments",
        )
        self._emit_initial_universe(frame, trade_date=input_bundle.trade_date)

        # Step 2: 可选 signal_values join
        if input_bundle.signal_values is not None:
            validate_frame(
                input_bundle.signal_values,
                (FrameCol.INSTRUMENT_ID,),
                boundary="input_bundle.signal_values",
            )
            self._validate_unique_evidence_instruments(
                input_bundle.signal_values,
                trade_date=input_bundle.trade_date,
                boundary="input_bundle.signal_values",
            )
            frame = frame.join(
                input_bundle.signal_values,
                on=FrameCol.INSTRUMENT_ID,
                how="left",
            )
            validate_frame(frame, (FrameCol.INSTRUMENT_ID,), boundary="initial_join")
            self._validate_unique_evidence_instruments(
                frame,
                trade_date=input_bundle.trade_date,
                boundary="initial_join",
            )

        # Step 3: 顺序执行 stages
        for stage in self._stages:
            frame = stage.process(frame, context)
            validate_frame(
                frame,
                (FrameCol.INSTRUMENT_ID,),
                boundary="stage_output",
                stage_name=stage.__class__.__name__,
            )
            self._validate_unique_evidence_instruments(
                frame,
                trade_date=input_bundle.trade_date,
                boundary="stage_output",
                stage_name=stage.__class__.__name__,
            )

        # Step 4: 从最终 frame 提取 TargetPortfolio
        return self._build_target_portfolio(frame, input_bundle)

    def _emit_initial_universe(
        self,
        frame: pl.DataFrame,
        *,
        trade_date: str,
    ) -> None:
        """Emit the candidate pool before joins or stage transformations."""
        if self._evidence_sink is None:
            return
        instrument_ids = frame.get_column(FrameCol.INSTRUMENT_ID).to_list()
        for ordinal, instrument_id in enumerate(instrument_ids, start=1):
            self._evidence_sink.emit(
                InitialUniverseEvidence(
                    trade_date=trade_date,
                    instrument_id=instrument_id,
                    ordinal=ordinal,
                ),
            )

    def _validate_unique_evidence_instruments(
        self,
        frame: pl.DataFrame,
        *,
        trade_date: str,
        boundary: str,
        stage_name: str | None = None,
    ) -> None:
        """Keep date-keyed evidence unambiguous without changing plain runs."""
        if self._evidence_sink is None or frame.is_empty():
            return
        instrument_ids = frame.get_column(FrameCol.INSTRUMENT_ID)
        duplicate_ids = (
            frame.filter(instrument_ids.is_duplicated())
            .get_column(FrameCol.INSTRUMENT_ID)
            .unique(maintain_order=True)
            .to_list()
        )
        if not duplicate_ids:
            return
        details: dict[str, object] = {
            "reason": "duplicate_evidence_instrument_id",
            "boundary": boundary,
            "trade_date": trade_date,
            "duplicate_instrument_ids": tuple(duplicate_ids),
        }
        if stage_name is not None:
            details["stage_name"] = stage_name
        raise StrategySpecError(
            "evidence-enabled pipeline has duplicate instrument_id rows",
            details=details,
        )

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
