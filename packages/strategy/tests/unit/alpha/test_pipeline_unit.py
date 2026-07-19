"""Tests for StrategyPipeline and StrategyInputBundle."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import FrozenInstanceError

import polars as pl
import pytest
from ditto_kernel.identity import InstrumentId
from ditto_strategy.alpha.context import StrategyContext
from ditto_strategy.alpha.models import TargetPortfolio
from ditto_strategy.alpha.pipeline import StrategyInputBundle, StrategyPipeline
from ditto_strategy.alpha.selection_evidence import SelectionEvidenceCollector
from ditto_strategy.errors import StrategySpecError

# ---------------------------------------------------------------------------
# Helpers: lightweight DecisionStage fakes for testing
# ---------------------------------------------------------------------------


class _RecordingStage:
    """记录调用次数和接收到的 context 的 Stage。"""

    def __init__(self) -> None:
        self.call_count: int = 0
        self.received_contexts: list[StrategyContext] = []

    def process(
        self,
        frame: pl.DataFrame,
        context: StrategyContext,
    ) -> pl.DataFrame:
        self.call_count += 1
        self.received_contexts.append(context)
        return frame


class _AddWeightStage:
    """给 frame 添加 weight 列，权重值固定为给定的 mapping。"""

    def __init__(self, weights: dict[int, float]) -> None:
        self._weights = weights

    def process(
        self,
        frame: pl.DataFrame,
        context: StrategyContext,
    ) -> pl.DataFrame:
        weights_expr = pl.col("instrument_id").replace(
            old=list(self._weights.keys()),
            new=list(self._weights.values()),
            default=0.0,
        )
        return frame.with_columns(weight=weights_expr)


class _DropInstrumentStage:
    """清空所有行（模拟 filter 全部移除）。"""

    def process(
        self,
        frame: pl.DataFrame,
        context: StrategyContext,
    ) -> pl.DataFrame:
        return frame.filter(pl.lit(False))


class _AddColumnStage:
    """给 frame 添加一个固定值的列。"""

    def __init__(self, column_name: str, value: float) -> None:
        self._column_name = column_name
        self._value = value

    def process(
        self,
        frame: pl.DataFrame,
        context: StrategyContext,
    ) -> pl.DataFrame:
        return frame.with_columns(pl.lit(self._value).alias(self._column_name))


class _CheckSignalStage:
    """检查 frame 是否包含 signal_value 列。"""

    def __init__(self) -> None:
        self.has_signal_column: bool = False

    def process(
        self,
        frame: pl.DataFrame,
        context: StrategyContext,
    ) -> pl.DataFrame:
        self.has_signal_column = "signal_value" in frame.columns
        return frame


class _ReplaceFrameStage:
    """返回指定 frame 的 Stage，用于验证 Pipeline 边界校验。"""

    def __init__(self, result: pl.DataFrame) -> None:
        self._result = result

    def process(
        self,
        frame: pl.DataFrame,
        context: StrategyContext,
    ) -> pl.DataFrame:
        return self._result


class _ObserveInitialEvidenceStage:
    """Capture whether initial-universe evidence exists before any stage runs."""

    def __init__(self, collector: SelectionEvidenceCollector) -> None:
        self._collector = collector
        self.observed_instrument_ids: tuple[int | str, ...] = ()

    def process(
        self,
        frame: pl.DataFrame,
        context: StrategyContext,
    ) -> pl.DataFrame:
        self.observed_instrument_ids = tuple(
            event.instrument_id for event in self._collector.snapshot().initial_universe
        )
        return frame


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def empty_context() -> StrategyContext:
    return StrategyContext()


@pytest.fixture
def sample_instruments() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "instrument_id": [1, 2, 3],
        }
    )


@pytest.fixture
def sample_market_data() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "instrument_id": [1, 2, 3],
            "close": [1.0, 2.0, 3.0],
        }
    )


@pytest.fixture
def sample_signal_values() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "instrument_id": [1, 2, 3],
            "signal_value": [0.85, 0.62, 0.41],
        }
    )


def _make_input_bundle(
    *,
    instruments: pl.DataFrame,
    market_data: pl.DataFrame,
    signal_values: pl.DataFrame | None = None,
    trade_date: str = "2026-01-15",
    strategy_id: str = "etf_momentum_rotation",
    run_id: str = "RUN-001",
    parameters: dict[str, object] | None = None,
    benchmark_close: float | None = None,
    instrument_id_map: Mapping[object, InstrumentId] | None = None,
    require_canonical_target_ids: bool = False,
) -> StrategyInputBundle:
    return StrategyInputBundle(
        trade_date=trade_date,
        strategy_id=strategy_id,
        run_id=run_id,
        instruments=instruments,
        market_data=market_data,
        signal_values=signal_values,
        parameters=parameters or {},
        benchmark_close=benchmark_close,
        instrument_id_map=instrument_id_map or {},
        require_canonical_target_ids=require_canonical_target_ids,
    )


# ---------------------------------------------------------------------------
# StrategyInputBundle tests
# ---------------------------------------------------------------------------


class TestStrategyInputBundle:
    def test_construction_with_all_fields(
        self,
        sample_instruments: pl.DataFrame,
        sample_market_data: pl.DataFrame,
        sample_signal_values: pl.DataFrame,
    ) -> None:
        bundle = _make_input_bundle(
            instruments=sample_instruments,
            market_data=sample_market_data,
            signal_values=sample_signal_values,
            parameters={"lookback": 252},
            benchmark_close=3200.0,
        )
        assert bundle.trade_date == "2026-01-15"
        assert bundle.strategy_id == "etf_momentum_rotation"
        assert bundle.run_id == "RUN-001"
        assert bundle.benchmark_close == 3200.0
        assert bundle.parameters["lookback"] == 252

    def test_construction_with_none_signal_values(
        self,
        sample_instruments: pl.DataFrame,
        sample_market_data: pl.DataFrame,
    ) -> None:
        bundle = _make_input_bundle(
            instruments=sample_instruments,
            market_data=sample_market_data,
            signal_values=None,
        )
        assert bundle.signal_values is None

    def test_frozen_immutability(
        self,
        sample_instruments: pl.DataFrame,
        sample_market_data: pl.DataFrame,
    ) -> None:
        bundle = _make_input_bundle(
            instruments=sample_instruments,
            market_data=sample_market_data,
        )
        with pytest.raises(FrozenInstanceError):
            bundle.trade_date = "2026-02-01"  # type: ignore[misc]

    def test_frozen_with_empty_parameters(
        self,
        sample_instruments: pl.DataFrame,
        sample_market_data: pl.DataFrame,
    ) -> None:
        bundle = _make_input_bundle(
            instruments=sample_instruments,
            market_data=sample_market_data,
        )
        assert bundle.parameters == {}
        assert bundle.benchmark_close is None


# ---------------------------------------------------------------------------
# StrategyPipeline tests
# ---------------------------------------------------------------------------


class TestStrategyPipeline:
    def test_initial_universe_evidence_is_emitted_before_join_and_stages(
        self,
        empty_context: StrategyContext,
        sample_instruments: pl.DataFrame,
        sample_market_data: pl.DataFrame,
        sample_signal_values: pl.DataFrame,
    ) -> None:
        collector = SelectionEvidenceCollector()
        observer = _ObserveInitialEvidenceStage(collector)
        pipeline = StrategyPipeline(stages=[observer], evidence_sink=collector)
        bundle = _make_input_bundle(
            instruments=sample_instruments,
            market_data=sample_market_data,
            signal_values=sample_signal_values,
        )

        target = pipeline.run(empty_context, bundle)

        assert observer.observed_instrument_ids == (1, 2, 3)
        assert [
            (event.instrument_id, event.ordinal)
            for event in collector.snapshot().initial_universe
        ] == [(1, 1), (2, 2), (3, 3)]
        assert target.positions == {1: 1 / 3, 2: 1 / 3, 3: 1 / 3}

    def test_empty_pipeline_returns_empty_target(
        self,
        empty_context: StrategyContext,
        sample_instruments: pl.DataFrame,
        sample_market_data: pl.DataFrame,
    ) -> None:
        pipeline = StrategyPipeline(stages=[])
        bundle = _make_input_bundle(
            instruments=sample_instruments,
            market_data=sample_market_data,
        )
        target = pipeline.run(empty_context, bundle)

        assert isinstance(target, TargetPortfolio)
        assert target.trade_date == "2026-01-15"
        assert target.strategy_id == "etf_momentum_rotation"
        assert target.run_id == "RUN-001"
        # No weight column from stages -> equal weight fallback
        assert len(target.positions) == 3
        for weight in target.positions.values():
            assert weight == pytest.approx(1.0 / 3.0)

    def test_empty_pipeline_with_no_instruments(
        self,
        empty_context: StrategyContext,
    ) -> None:
        pipeline = StrategyPipeline(stages=[])
        instruments = pl.DataFrame({"instrument_id": []})
        market_data = pl.DataFrame(
            {
                "instrument_id": [],
                "close": [],
            }
        )
        bundle = _make_input_bundle(
            instruments=instruments,
            market_data=market_data,
        )
        target = pipeline.run(empty_context, bundle)

        assert isinstance(target, TargetPortfolio)
        assert target.positions == {}

    def test_single_stage_forwarding(
        self,
        empty_context: StrategyContext,
        sample_instruments: pl.DataFrame,
        sample_market_data: pl.DataFrame,
    ) -> None:
        stage = _AddColumnStage("score", 1.0)
        pipeline = StrategyPipeline(stages=[stage])
        bundle = _make_input_bundle(
            instruments=sample_instruments,
            market_data=sample_market_data,
        )
        target = pipeline.run(empty_context, bundle)

        assert isinstance(target, TargetPortfolio)
        # No weight column -> equal weight fallback
        assert len(target.positions) == 3

    def test_multi_stage_sequential(
        self,
        empty_context: StrategyContext,
        sample_instruments: pl.DataFrame,
        sample_market_data: pl.DataFrame,
    ) -> None:
        stage1 = _AddColumnStage("signal_value", 0.5)
        stage2 = _AddColumnStage("score", 0.8)
        pipeline = StrategyPipeline(stages=[stage1, stage2])
        bundle = _make_input_bundle(
            instruments=sample_instruments,
            market_data=sample_market_data,
        )
        target = pipeline.run(empty_context, bundle)

        assert isinstance(target, TargetPortfolio)
        # Stages run in order; neither adds weight, so equal weight fallback
        assert len(target.positions) == 3

    def test_context_passed_to_all_stages(
        self,
        sample_instruments: pl.DataFrame,
        sample_market_data: pl.DataFrame,
    ) -> None:
        stage1 = _RecordingStage()
        stage2 = _RecordingStage()
        stage3 = _RecordingStage()
        pipeline = StrategyPipeline(stages=[stage1, stage2, stage3])

        ctx = StrategyContext()
        ctx.lock_instrument(1, "max_drawdown")
        bundle = _make_input_bundle(
            instruments=sample_instruments,
            market_data=sample_market_data,
        )
        pipeline.run(ctx, bundle)

        assert stage1.call_count == 1
        assert stage2.call_count == 1
        assert stage3.call_count == 1

        # Each stage received the same context object
        assert stage1.received_contexts[0] is ctx
        assert stage2.received_contexts[0] is ctx
        assert stage3.received_contexts[0] is ctx

        # Context mutation is visible to later stages
        assert stage1.received_contexts[0].is_locked(1)

    def test_target_portfolio_from_final_frame_with_weights(
        self,
        empty_context: StrategyContext,
        sample_instruments: pl.DataFrame,
        sample_market_data: pl.DataFrame,
    ) -> None:
        weights = {1: 0.4, 2: 0.35, 3: 0.25}
        stage = _AddWeightStage(weights)
        pipeline = StrategyPipeline(stages=[stage])
        bundle = _make_input_bundle(
            instruments=sample_instruments,
            market_data=sample_market_data,
        )
        target = pipeline.run(empty_context, bundle)

        assert isinstance(target, TargetPortfolio)
        assert target.positions[1] == pytest.approx(0.4)
        assert target.positions[2] == pytest.approx(0.35)
        assert target.positions[3] == pytest.approx(0.25)

    def test_target_portfolio_resolves_string_ids_with_input_bundle_identity_map(
        self,
        empty_context: StrategyContext,
    ) -> None:
        instruments = pl.DataFrame({"instrument_id": ["ETF001", "ETF002"]})
        market_data = pl.DataFrame(
            {
                "instrument_id": ["ETF001", "ETF002"],
                "close": [1.0, 2.0],
            },
        )
        stage = _ReplaceFrameStage(
            pl.DataFrame(
                {
                    "instrument_id": ["ETF001", "ETF002"],
                    "weight": [0.65, 0.35],
                },
            ),
        )
        pipeline = StrategyPipeline(stages=[stage])
        bundle = _make_input_bundle(
            instruments=instruments,
            market_data=market_data,
            instrument_id_map={
                "ETF001": InstrumentId(1001),
                "ETF002": InstrumentId(1002),
            },
            require_canonical_target_ids=True,
        )

        target = pipeline.run(empty_context, bundle)

        assert target.positions[InstrumentId(1001)] == pytest.approx(0.65)
        assert target.positions[InstrumentId(1002)] == pytest.approx(0.35)
        assert "ETF001" not in target.positions
        assert "ETF002" not in target.positions

    def test_target_portfolio_equal_weight_fallback(
        self,
        empty_context: StrategyContext,
        sample_instruments: pl.DataFrame,
        sample_market_data: pl.DataFrame,
    ) -> None:
        # Pipeline has a stage that does NOT add weight column
        stage = _AddColumnStage("signal_value", 0.5)
        pipeline = StrategyPipeline(stages=[stage])
        bundle = _make_input_bundle(
            instruments=sample_instruments,
            market_data=sample_market_data,
        )
        target = pipeline.run(empty_context, bundle)

        assert len(target.positions) == 3
        expected_weight = 1.0 / 3.0
        for weight in target.positions.values():
            assert weight == pytest.approx(expected_weight)

    def test_equal_weight_target_resolves_string_ids_with_identity_map(
        self,
        empty_context: StrategyContext,
    ) -> None:
        instruments = pl.DataFrame({"instrument_id": ["ETF001", "ETF002"]})
        market_data = pl.DataFrame(
            {
                "instrument_id": ["ETF001", "ETF002"],
                "close": [1.0, 2.0],
            },
        )
        pipeline = StrategyPipeline(stages=[])
        bundle = _make_input_bundle(
            instruments=instruments,
            market_data=market_data,
            instrument_id_map={
                "ETF001": InstrumentId(1001),
                "ETF002": InstrumentId(1002),
            },
            require_canonical_target_ids=True,
        )

        target = pipeline.run(empty_context, bundle)

        assert target.positions[InstrumentId(1001)] == pytest.approx(0.5)
        assert target.positions[InstrumentId(1002)] == pytest.approx(0.5)
        assert "ETF001" not in target.positions
        assert "ETF002" not in target.positions

    def test_strict_target_portfolio_rejects_unmapped_string_ids(
        self,
        empty_context: StrategyContext,
    ) -> None:
        instruments = pl.DataFrame({"instrument_id": ["ETF001"]})
        market_data = pl.DataFrame({"instrument_id": ["ETF001"], "close": [1.0]})
        pipeline = StrategyPipeline(stages=[])
        bundle = _make_input_bundle(
            instruments=instruments,
            market_data=market_data,
            require_canonical_target_ids=True,
        )

        with pytest.raises(
            StrategySpecError,
            match="TargetPortfolio contains non-canonical instrument IDs",
        ) as exc_info:
            pipeline.run(empty_context, bundle)

        assert exc_info.value.details["boundary"] == "target_portfolio"
        assert exc_info.value.details["non_canonical_instrument_ids"] == ("ETF001",)

    def test_target_portfolio_preserves_metadata(
        self,
        empty_context: StrategyContext,
        sample_instruments: pl.DataFrame,
        sample_market_data: pl.DataFrame,
    ) -> None:
        weights = {1: 0.5, 2: 0.3, 3: 0.2}
        stage = _AddWeightStage(weights)
        pipeline = StrategyPipeline(stages=[stage])
        bundle = _make_input_bundle(
            instruments=sample_instruments,
            market_data=sample_market_data,
            trade_date="2026-03-22",
            strategy_id="custom_strategy",
            run_id="RUN-CUSTOM-42",
        )
        target = pipeline.run(empty_context, bundle)

        assert target.trade_date == "2026-03-22"
        assert target.strategy_id == "custom_strategy"
        assert target.run_id == "RUN-CUSTOM-42"
        assert target.cash_target == 0.0

    def test_signal_values_joined_into_initial_frame(
        self,
        empty_context: StrategyContext,
        sample_instruments: pl.DataFrame,
        sample_market_data: pl.DataFrame,
        sample_signal_values: pl.DataFrame,
    ) -> None:
        stage = _CheckSignalStage()
        pipeline = StrategyPipeline(stages=[stage])
        bundle = _make_input_bundle(
            instruments=sample_instruments,
            market_data=sample_market_data,
            signal_values=sample_signal_values,
        )
        pipeline.run(empty_context, bundle)

        assert stage.has_signal_column

    def test_signal_values_none_skips_join(
        self,
        empty_context: StrategyContext,
        sample_instruments: pl.DataFrame,
        sample_market_data: pl.DataFrame,
    ) -> None:
        stage = _CheckSignalStage()
        pipeline = StrategyPipeline(stages=[stage])
        bundle = _make_input_bundle(
            instruments=sample_instruments,
            market_data=sample_market_data,
            signal_values=None,
        )
        pipeline.run(empty_context, bundle)

        assert not stage.has_signal_column

    def test_stages_are_stored_as_tuple(
        self,
        empty_context: StrategyContext,
        sample_instruments: pl.DataFrame,
        sample_market_data: pl.DataFrame,
    ) -> None:
        stages = [_RecordingStage(), _RecordingStage()]
        pipeline = StrategyPipeline(stages=stages)

        # stages should be stored as tuple, not list
        assert isinstance(pipeline._stages, tuple)
        assert len(pipeline._stages) == 2

    def test_all_instruments_filtered_out_returns_empty_positions(
        self,
        empty_context: StrategyContext,
        sample_instruments: pl.DataFrame,
        sample_market_data: pl.DataFrame,
    ) -> None:
        stage = _DropInstrumentStage()
        pipeline = StrategyPipeline(stages=[stage])
        bundle = _make_input_bundle(
            instruments=sample_instruments,
            market_data=sample_market_data,
        )
        target = pipeline.run(empty_context, bundle)

        assert isinstance(target, TargetPortfolio)
        assert target.positions == {}
        assert target.trade_date == "2026-01-15"

    def test_stage_output_missing_instrument_id_raises_strategy_spec_error(
        self,
        empty_context: StrategyContext,
        sample_instruments: pl.DataFrame,
        sample_market_data: pl.DataFrame,
    ) -> None:
        stage = _ReplaceFrameStage(pl.DataFrame({"weight": [1.0]}))
        pipeline = StrategyPipeline(stages=[stage])
        bundle = _make_input_bundle(
            instruments=sample_instruments,
            market_data=sample_market_data,
        )

        with pytest.raises(
            StrategySpecError,
            match="DecisionFrame missing required columns",
        ) as exc_info:
            pipeline.run(empty_context, bundle)

        assert exc_info.value.details["missing_columns"] == ("instrument_id",)
        assert exc_info.value.details["stage_name"] == "_ReplaceFrameStage"

    def test_stage_output_weight_must_be_numeric(
        self,
        empty_context: StrategyContext,
        sample_instruments: pl.DataFrame,
        sample_market_data: pl.DataFrame,
    ) -> None:
        stage = _ReplaceFrameStage(
            pl.DataFrame({"instrument_id": [1], "weight": ["full"]}),
        )
        pipeline = StrategyPipeline(stages=[stage])
        bundle = _make_input_bundle(
            instruments=sample_instruments,
            market_data=sample_market_data,
        )

        with pytest.raises(
            StrategySpecError,
            match="DecisionFrame column has invalid dtype",
        ) as exc_info:
            pipeline.run(empty_context, bundle)

        assert exc_info.value.details["column_name"] == "weight"
        assert exc_info.value.details["expected_dtype"] == "numeric"
        assert exc_info.value.details["actual_dtype"] == "String"
        assert exc_info.value.details["stage_name"] == "_ReplaceFrameStage"
