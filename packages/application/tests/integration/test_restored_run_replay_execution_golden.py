"""Restored-run replay execution golden.

This golden keeps external systems out of scope: no real broker adapter, no
external data source, no product UI. It proves the backend resume/replay chain
can preserve checkpoint config state through real service execution and artifact
query surfaces.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, replace
from pathlib import Path
from typing import cast

import orjson
import polars as pl
import pytest
from ditto_application.builders import (
    BacktestRuntimeBuilder,
    PublishedStrategyRuntime,
    StrategyServiceFactory,
)
from ditto_application.commands.backtest import ResumeRunCommand, ResumeRunHandler
from ditto_application.processes.execution.backtest_process import (
    BacktestCatalogRequestConfig,
    BacktestServiceConfig,
    BacktestServiceOptions,
)
from ditto_application.processes.execution.replay_process import ReplayProcess
from ditto_application.processes.execution.strategy_run_process import StrategyFacade
from ditto_application.queries.backtest import BacktestQueryFacade
from ditto_application.queries.run import RunReadModel
from ditto_data.provider import BarQuery, DataProvider, InstrumentQuery
from ditto_data.services.metadata_service import MetadataService
from ditto_execution.audit import ExecutionAuditService
from ditto_kernel.identity import InstrumentId
from ditto_kernel.strategy import RunStatus
from ditto_strategy.alpha.context import StrategyContext
from ditto_strategy.alpha.parameters import canonical_parameter_hash
from ditto_strategy.alpha.pipeline import StrategyPipeline
from ditto_strategy.alpha.specs import StrategySpec
from ditto_strategy.models import (
    StrategyArtifactRecord,
    StrategySpecRecord,
)
from ditto_strategy.runs.models import StrategyRunCheckpointRecord, StrategyRunRecord
from ditto_strategy.storage.sqlite.services.backtest_artifact_reader import (
    BacktestArtifactReader,
)
from ditto_strategy.storage.sqlite.services.strategy_artifact_service import (
    StrategyArtifactService,
)

INITIAL_CASH = 1_000_000.0
STRATEGY_ID = "restored-replay-golden"
TRADE_DATES = ("2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08")
ID_MAP = {
    "510300.XSHG": InstrumentId(2_000_001),
    "510500.XSHG": InstrumentId(2_000_002),
}


class _AllCashStage:
    """Decision stage that keeps the portfolio entirely in cash."""

    def process(self, frame: pl.DataFrame, context: StrategyContext) -> pl.DataFrame:
        _ = context
        return frame.with_columns(pl.lit(0.0).alias("weight"))


class _SyntheticDataProvider:
    """In-memory synthetic data provider for the golden lane."""

    def __init__(self, data: dict[InstrumentId, pl.DataFrame]) -> None:
        self._data = data

    def get_bars(self, query: BarQuery) -> pl.DataFrame:
        frames: list[pl.DataFrame] = []
        for ticker in query.instruments:
            instrument_id = ID_MAP.get(ticker)
            if instrument_id is None:
                continue
            frame = self._data[instrument_id].with_columns(
                instrument_id=pl.lit(int(instrument_id)),
            )
            frames.append(frame)
        if not frames:
            return pl.DataFrame()
        bars = pl.concat(frames, how="diagonal")
        return bars.filter(
            (pl.col("trade_date") >= query.start) & (pl.col("trade_date") <= query.end)
        )

    def get_schedule(self, start: str, end: str) -> pl.DataFrame:
        dates = [trade_date for trade_date in TRADE_DATES if start <= trade_date <= end]
        return pl.DataFrame({"trade_date": dates})

    def get_instruments(self, query: InstrumentQuery) -> pl.DataFrame:
        _ = query
        return pl.DataFrame()

    def get_factor(
        self,
        name: str,
        instruments: tuple[str, ...],
        start: str,
        end: str,
        asof: str | None = None,
    ) -> pl.DataFrame:
        _ = (name, instruments, start, end, asof)
        return pl.DataFrame()


class _InMemoryRunControl:
    """In-memory lifecycle plus latest-checkpoint store."""

    def __init__(self, *, auto_cancel_run_ids: Iterable[str] = ()) -> None:
        self._runs: dict[str, StrategyRunRecord] = {}
        self._checkpoints: dict[str, StrategyRunCheckpointRecord] = {}
        self._auto_cancel_run_ids = set(auto_cancel_run_ids)

    def create_run(
        self,
        run_id: str,
        strategy_id: str,
        strategy_version: str = "",
        mode: str = "backtest",
        *,
        parent_run_id: str = "",
        config_json: str = "",
    ) -> None:
        self._runs[run_id] = StrategyRunRecord(
            run_id=run_id,
            strategy_id=strategy_id,
            strategy_version=strategy_version,
            mode=mode,
            status=RunStatus.PENDING,
            parent_run_id=parent_run_id,
            config_json=config_json,
        )

    def mark_running(self, run_id: str) -> bool:
        return self._update(run_id, status=RunStatus.RUNNING)

    def mark_completed(self, run_id: str) -> bool:
        return self._update(run_id, status=RunStatus.COMPLETED)

    def mark_failed(self, run_id: str, error_message: str = "") -> bool:
        return self._update(
            run_id,
            status=RunStatus.FAILED,
            error_message=error_message,
        )

    def mark_cancelled(self, run_id: str) -> bool:
        return self._update(run_id, status=RunStatus.CANCELLED)

    def get_run(self, run_id: str) -> StrategyRunRecord | None:
        return self._runs.get(run_id)

    def is_cancelled(self, run_id: str) -> bool:
        record = self.get_run(run_id)
        return record is not None and record.status == RunStatus.CANCELLED

    def update_progress(
        self,
        run_id: str,
        *,
        progress_pct: float = 0.0,
        current_step: str = "",
        completed_days: int = 0,
        total_days: int = 0,
    ) -> bool:
        status = (
            RunStatus.CANCELLED
            if run_id in self._auto_cancel_run_ids and completed_days >= 1
            else None
        )
        return self._update(
            run_id,
            status=status,
            progress_pct=progress_pct,
            current_step=current_step,
            completed_days=completed_days,
            total_days=total_days,
        )

    def list_runs(
        self,
        *,
        strategy_id: str | None = None,
        status: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[StrategyRunRecord]:
        _ = (start_date, end_date)
        records = list(self._runs.values())
        if strategy_id is not None:
            records = [
                record for record in records if record.strategy_id == strategy_id
            ]
        if status is not None:
            records = [record for record in records if record.status == status]
        start = offset or 0
        end = None if limit is None else start + limit
        return records[start:end]

    def list_by_strategy(self, strategy_id: str) -> list[StrategyRunRecord]:
        return [
            record
            for record in self._runs.values()
            if record.strategy_id == strategy_id
        ]

    def list_by_parent(self, parent_run_id: str) -> list[StrategyRunRecord]:
        return [
            record
            for record in self._runs.values()
            if record.parent_run_id == parent_run_id
        ]

    def save_checkpoint(self, record: StrategyRunCheckpointRecord) -> None:
        self._checkpoints[record.run_id] = record

    def get_latest_checkpoint(
        self,
        run_id: str,
    ) -> StrategyRunCheckpointRecord | None:
        return self._checkpoints.get(run_id)

    def list_checkpoints_by_strategy(
        self,
        strategy_id: str,
    ) -> list[StrategyRunCheckpointRecord]:
        return [
            record
            for record in self._checkpoints.values()
            if record.strategy_id == strategy_id
        ]

    def _update(self, run_id: str, **changes: object) -> bool:
        record = self._runs.get(run_id)
        if record is None:
            return False
        updates = {key: value for key, value in changes.items() if value is not None}
        self._runs[run_id] = replace(record, **updates)
        return True


class _InMemoryArtifactService:
    """In-memory artifact service with real file paths."""

    def __init__(self) -> None:
        self._artifacts: list[StrategyArtifactRecord] = []

    def save_artifact(self, record: StrategyArtifactRecord) -> None:
        self._artifacts = [
            artifact
            for artifact in self._artifacts
            if artifact.artifact_id != record.artifact_id
        ]
        self._artifacts.append(record)

    def get_artifact(self, artifact_id: str) -> StrategyArtifactRecord | None:
        for artifact in self._artifacts:
            if artifact.artifact_id == artifact_id:
                return artifact
        return None

    def list_artifacts(self) -> list[StrategyArtifactRecord]:
        return list(self._artifacts)

    def list_by_strategy(self, strategy_id: str) -> list[StrategyArtifactRecord]:
        return [
            artifact
            for artifact in self._artifacts
            if artifact.strategy_id == strategy_id
        ]


class _NoopAuditService:
    """No-op execution audit port for this artifact-focused golden."""

    def save_risk_log(self, run_id: str, payloads: object) -> None:
        _ = (run_id, payloads)

    def save_pre_trade_log(self, run_id: str, payloads: object) -> None:
        _ = (run_id, payloads)

    def query(
        self,
        run_id: str,
        *,
        record_type: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict[str, object]]:
        _ = (run_id, record_type, start_date, end_date)
        return []


def _make_data() -> dict[InstrumentId, pl.DataFrame]:
    return {
        InstrumentId(2_000_001): _bar_frame([10.0, 10.1, 10.2, 10.3]),
        InstrumentId(2_000_002): _bar_frame([20.0, 20.1, 20.2, 20.3]),
    }


def _bar_frame(close_prices: list[float]) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "trade_date": list(TRADE_DATES),
            "open": close_prices,
            "high": [value * 1.01 for value in close_prices],
            "low": [value * 0.99 for value in close_prices],
            "close": close_prices,
            "prev_close": [close_prices[0], *close_prices[:-1]],
            "volume": [1_000_000.0] * len(close_prices),
            "amount": [value * 1_000_000.0 for value in close_prices],
            "is_suspended": [False] * len(close_prices),
        }
    )


def _build_factory(
    *,
    run_control: _InMemoryRunControl,
    artifact_service: _InMemoryArtifactService,
    artifact_dir: Path,
) -> StrategyServiceFactory:
    spec = StrategySpec(
        strategy_id=STRATEGY_ID,
        name="Restored Replay Golden",
        template="etf_rotation",
        universe="golden-etf",
        asset_class="etf",
        benchmark=None,
        tags=("golden",),
    )
    strategy_runtime_builder = cast(object, _RuntimeBuilderStub(spec))
    metadata_service = cast(MetadataService, _MetadataServiceStub())
    data_provider = cast(DataProvider, _SyntheticDataProvider(_make_data()))
    runtime_builder = BacktestRuntimeBuilder(
        strategy_runtime_builder=cast(object, strategy_runtime_builder),
        metadata_service=metadata_service,
        data_provider=data_provider,
    )
    return StrategyServiceFactory(
        audit_service=cast(ExecutionAuditService, _NoopAuditService()),
        artifact_service=cast(StrategyArtifactService, artifact_service),
        run_service=run_control,
        backtest_runtime_builder=runtime_builder,
        checkpoint_writer=run_control,
    )


class _RuntimeBuilderStub:
    def __init__(self, spec: StrategySpec) -> None:
        self._spec = spec

    def build_published_runtime(
        self,
        strategy_id: str,
        version: int | None = None,
        *,
        candidate_parameters: tuple[object, ...] = (),
    ) -> PublishedStrategyRuntime:
        _ = (strategy_id, version, candidate_parameters)
        return PublishedStrategyRuntime(
            record=StrategySpecRecord(
                strategy_id=self._spec.strategy_id,
                name=self._spec.name,
                spec_json=asdict(self._spec),
                version=1,
                tags=self._spec.tags,
            ),
            spec=self._spec,
            base_spec=self._spec,
            resolved_spec=self._spec,
            pipeline=StrategyPipeline((_AllCashStage(),)),
            base_spec_hash="a" * 64,
            spec_hash="b" * 64,
            parameter_hash=canonical_parameter_hash(()),
            effective_parameters=(),
        )


class _InstrumentLookup:
    def get_instrument(self, instrument_id: int) -> dict[str, str] | None:
        if instrument_id == 2_000_001:
            return {"ticker": "510300", "exchange": "XSHG"}
        if instrument_id == 2_000_002:
            return {"ticker": "510500", "exchange": "XSHG"}
        return None

    def get_source_ticker(
        self,
        instrument_id: int,
        source: str,
        as_of: str | None = None,
    ) -> str | None:
        _ = (source, as_of)
        return {
            2_000_001: "510300.XSHG",
            2_000_002: "510500.XSHG",
        }.get(instrument_id)


class _MetadataServiceStub:
    instrument = _InstrumentLookup()

    def resolve_instrument_id(
        self,
        ticker: str,
        source: str,
        as_of: str,
    ) -> int | None:
        _ = (ticker, source, as_of)
        return None

    def get_universe(self, universe_id: str, asof: str) -> list[int]:
        _ = (universe_id, asof)
        return [2_000_001, 2_000_002]


class _ReplayFacade:
    def __init__(
        self,
        factory: StrategyServiceFactory,
        artifact_dir: Path,
    ) -> None:
        self._factory = factory
        self._artifact_dir = artifact_dir

    def run_backtest_from_catalog(
        self,
        *,
        config: BacktestServiceConfig,
        version: int | None = None,
        options: BacktestServiceOptions | None = None,
        source: str = "tushare",
    ):
        resolved_options = options or BacktestServiceOptions(
            artifact_dir=str(self._artifact_dir),
        )
        service = self._factory.build_backtest_service_from_catalog(
            config=config,
            version=version,
            options=resolved_options,
            source=source,
        )
        return service.run()


def _config_from_record(record: StrategyRunRecord) -> BacktestCatalogRequestConfig:
    raw = orjson.loads(record.config_json)
    assert isinstance(raw, dict)
    data = cast(dict[str, object], raw)
    return BacktestCatalogRequestConfig(
        strategy_id=record.strategy_id,
        strategy_version=record.strategy_version,
        run_id=record.run_id,
        parent_run_id=record.parent_run_id,
        start_date=cast(str, data["start_date"]),
        end_date=cast(str, data["end_date"]),
        initial_cash=float(data["initial_cash"]),
        parameter_overrides=tuple(cast(list[str], data.get("parameter_overrides", []))),
        resume_from_run_id=cast(str, data.get("resume_from_run_id", "")),
        resume_checkpoint_trade_date=cast(
            str,
            data.get("resume_checkpoint_trade_date", ""),
        ),
        resume_checkpoint_completed_days=int(
            data.get("resume_checkpoint_completed_days", 0),
        ),
        resume_checkpoint_total_days=int(data.get("resume_checkpoint_total_days", 0)),
        resume_checkpoint_nav=float(data.get("resume_checkpoint_nav", 0.0)),
        resume_checkpoint_order_count=int(data.get("resume_checkpoint_order_count", 0)),
        resume_checkpoint_fill_count=int(data.get("resume_checkpoint_fill_count", 0)),
        resume_account_state_json=cast(str, data.get("resume_account_state_json", "")),
        resume_account_state_hash=cast(str, data.get("resume_account_state_hash", "")),
        resume_settlement_state_json=cast(
            str,
            data.get("resume_settlement_state_json", ""),
        ),
        resume_settlement_state_hash=cast(
            str,
            data.get("resume_settlement_state_hash", ""),
        ),
        resume_runtime_state_json=cast(str, data.get("resume_runtime_state_json", "")),
        resume_runtime_state_hash=cast(str, data.get("resume_runtime_state_hash", "")),
    )


@pytest.mark.integration
def test_restored_run_replay_execution_golden(tmp_path: Path) -> None:
    """Root checkpoint -> resume child -> replay proof -> evidence summary."""
    artifact_dir = tmp_path / "artifacts"
    run_control = _InMemoryRunControl(auto_cancel_run_ids={"run-root"})
    artifact_service = _InMemoryArtifactService()
    factory = _build_factory(
        run_control=run_control,
        artifact_service=artifact_service,
        artifact_dir=artifact_dir,
    )

    root_service = factory.build_backtest_service_from_catalog(
        config=BacktestCatalogRequestConfig(
            strategy_id=STRATEGY_ID,
            run_id="run-root",
            start_date=TRADE_DATES[0],
            end_date=TRADE_DATES[-1],
            initial_cash=INITIAL_CASH,
        ),
        version=1,
        options=BacktestServiceOptions(artifact_dir=str(artifact_dir)),
    )
    root_service.run()

    checkpoint = run_control.get_latest_checkpoint("run-root")
    assert checkpoint is not None
    assert checkpoint.can_resume is True
    assert checkpoint.resume_from == TRADE_DATES[1]
    assert checkpoint.account_state_json
    assert checkpoint.runtime_state_json

    child_run_id = ResumeRunHandler(
        run_service=run_control,
        checkpoint_reader=run_control,
    ).handle(ResumeRunCommand(run_id="run-root"))
    child_record = run_control.get_run(child_run_id)
    assert child_record is not None

    child_service = factory.build_backtest_service_from_catalog(
        config=_config_from_record(child_record),
        version=1,
        options=BacktestServiceOptions(artifact_dir=str(artifact_dir)),
    )
    child_report = child_service.run()

    replay_process = ReplayProcess(
        strategy_facade=cast(
            StrategyFacade,
            _ReplayFacade(factory=factory, artifact_dir=artifact_dir),
        ),
        artifact_service=cast(StrategyArtifactService, artifact_service),
        run_model=run_control,
    )
    replay_result = replay_process.replay(child_report.run_id)

    facade = BacktestQueryFacade(
        trade_facade=cast(object, object()),
        run_model=cast(RunReadModel, run_control),
        audit_service=cast(ExecutionAuditService, _NoopAuditService()),
        artifact_service=cast(StrategyArtifactService, artifact_service),
        artifact_reader=BacktestArtifactReader(),
    )
    summary = facade.get_replay_evidence_summary(replay_result.new_run_id)

    assert summary is not None
    assert summary.original_run_id == child_report.run_id
    assert summary.replay_run_id == replay_result.new_run_id
    assert summary.is_reproducible is True
    assert summary.input_data_match is True
    assert summary.account_state_match is True
    assert summary.report_resume_provenance == summary.proof_resume_provenance
    assert summary.resume_provenance_match is True
    assert summary.missing_sections == ()
    assert summary.report_resume_provenance is not None
    assert summary.report_resume_provenance["from_run_id"] == "run-root"
    assert summary.report_resume_provenance["runtime_state_hash"] == (
        checkpoint.runtime_state_hash
    )
