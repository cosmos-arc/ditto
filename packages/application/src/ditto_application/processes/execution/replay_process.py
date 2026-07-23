"""ReplayProcess — deterministic backtest replay orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol, cast

import orjson
from ditto_backtest.manifest import RunManifest
from ditto_backtest.replay import ReplayValidationResult, ReplayValidator
from ditto_backtest.statistics import BacktestReport
from ditto_platform.foundation import atomic_bytes_write
from ditto_portfolio.accounting.fills import FillEvent
from ditto_strategy.alpha.parameters import CandidateParameter
from ditto_strategy.models import ArtifactKind, StrategyArtifactRecord
from ditto_strategy.runs.models import StrategyRunRecord
from ditto_strategy.storage.sqlite.services.strategy_artifact_service import (
    StrategyArtifactService,
)

from ditto_application.config import DEFAULT_INITIAL_CASH
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.execution._replay_artifact_reservation import (
    ReplayArtifactReservation,
)
from ditto_application.processes.execution._replay_proof import (
    build_replay_proof_payload as _build_replay_proof_payload,
)
from ditto_application.processes.execution._replay_proof import (
    build_state_proof as _build_state_proof,
)
from ditto_application.processes.execution._replay_proof import (
    load_fill_log as _load_fill_log,
)
from ditto_application.processes.execution._replay_proof import (
    load_final_account_state as _load_final_account_state,
)
from ditto_application.processes.execution._replay_proof import (
    load_resume_provenance as _load_resume_provenance,
)
from ditto_application.processes.execution._replay_proof import (
    resume_provenance_metadata as _resume_provenance_metadata,
)
from ditto_application.processes.execution._research_replay_artifacts import (
    IndexedResearchReplayArtifactReader,
    VerifiedReplayArtifactReader,
    VerifiedReplayBundle,
)
from ditto_application.processes.execution._research_replay_codec import (
    build_research_replay_metadata,
)
from ditto_application.processes.execution._research_replay_codec import (
    deserialize_manifest as _deserialize_manifest,
)
from ditto_application.processes.execution._research_replay_codec import (
    research_replay_pointer as _research_replay_pointer,
)
from ditto_application.processes.execution.backtest_audit import resolve_run_id
from ditto_application.processes.execution.backtest_process import (
    BacktestServiceConfig,
    BacktestServiceOptions,
)
from ditto_application.processes.execution.strategy_run_process import StrategyFacade
from ditto_application.queries.artifact_utils import find_artifact

__all__ = [
    "IndexedResearchReplayArtifactReader",
    "ReplayProcess",
    "ReplayResult",
    "VerifiedReplayArtifactReader",
    "VerifiedReplayBundle",
    "build_research_replay_metadata",
]


class ReplayRunConfigReader(Protocol):
    """Narrow read port for original run-control config during replay."""

    def get_run(self, run_id: str) -> StrategyRunRecord | None:
        """Return a run record by ID."""
        ...


@dataclass(frozen=True, slots=True)
class _ReplayInputs:
    manifest: RunManifest
    report: dict[str, Any]
    fill_log: tuple[FillEvent, ...] | None
    is_research_evidence: bool


@dataclass(frozen=True)
class ReplayResult:
    """Replay result and immutable original/replayed manifests."""

    new_run_id: str
    validation: ReplayValidationResult
    original_manifest: RunManifest
    replay_manifest: RunManifest


class ReplayProcess:
    """Replay a persisted backtest and validate deterministic equivalence."""

    def __init__(
        self,
        strategy_facade: StrategyFacade,
        artifact_service: StrategyArtifactService,
        run_model: ReplayRunConfigReader | None = None,
        *,
        verified_artifact_reader: VerifiedReplayArtifactReader | None = None,
    ) -> None:
        self._facade = strategy_facade
        self._artifact_service = artifact_service
        self._run_model = run_model
        self._verified_artifact_reader = verified_artifact_reader

    def replay(self, original_run_id: str) -> ReplayResult:
        """Replay ``original_run_id`` without mutating its artifacts."""
        original_record = self._find_artifact_record(original_run_id)
        artifact_dir = Path(original_record.file_path)
        original_inputs = self._load_replay_inputs(original_record)
        original_manifest = original_inputs.manifest
        report = original_inputs.report
        original_run_config = self._load_run_config(original_run_id)
        requested_run_id = resolve_run_id("")
        if requested_run_id == original_run_id:
            raise AppProcessError(
                "Replay run ID must differ from the original run ID",
                reason="replay_run_id_collision",
                original_run_id=original_run_id,
                replay_run_id=requested_run_id,
            )
        indexed_target = find_artifact(
            self._artifact_service,
            requested_run_id,
            ArtifactKind.BACKTEST_REPORT,
        )
        if indexed_target is not None:
            indexed_dir = Path(indexed_target.file_path)
            same_dir = indexed_dir.resolve() == artifact_dir.resolve()
            raise AppProcessError(
                "Replay artifact target is already indexed",
                reason=(
                    "replay_artifact_directory_collision"
                    if same_dir
                    else "replay_artifact_target_exists"
                ),
                original_artifact_dir=str(artifact_dir),
                replay_artifact_dir=str(indexed_dir),
            )
        target_dir = artifact_dir.parent / requested_run_id
        config = self._build_config(
            original_manifest,
            report,
            run_id=requested_run_id,
            parent_run_id=original_run_id,
            run_config=original_run_config,
        )
        reservation = ReplayArtifactReservation.acquire(
            target_dir,
            original=artifact_dir,
        )
        try:
            replay_report = self._facade.run_backtest_from_catalog(
                config=config,
                options=BacktestServiceOptions(artifact_dir=str(artifact_dir.parent)),
                version=int(original_manifest.strategy_version)
                if original_manifest.strategy_version.isdigit()
                else None,
            )
            new_run_id = replay_report.run_id
            if new_run_id != requested_run_id:
                raise AppProcessError(
                    "Replay facade returned a run ID that differs from the request",
                    reason="replay_run_id_mismatch",
                    original_run_id=original_run_id,
                    requested_run_id=requested_run_id,
                    actual_run_id=new_run_id,
                )
            replay_record = self._find_artifact_record(new_run_id)
            replay_artifact_dir = Path(replay_record.file_path)
            if not reservation.matches(replay_artifact_dir):
                raise AppProcessError(
                    "Replay artifact directory differs from its reserved target",
                    reason="replay_artifact_target_mismatch",
                    requested_artifact_dir=str(target_dir),
                    replay_artifact_dir=str(replay_artifact_dir),
                )
            replay_inputs = self._load_replay_inputs(
                replay_record,
                load_report=False,
            )
            replay_manifest = replay_inputs.manifest
            state_proof = _build_state_proof(
                original_fills=(
                    original_inputs.fill_log
                    if original_inputs.is_research_evidence
                    else _load_fill_log(artifact_dir)
                ),
                original_account=_load_final_account_state(report),
                replay_fills=(
                    replay_inputs.fill_log
                    if replay_inputs.is_research_evidence
                    else tuple(replay_report.fill_log)
                ),
                replay_account=(
                    _load_final_account_state(replay_inputs.report)
                    if replay_inputs.is_research_evidence
                    else replay_report.final_account_state
                ),
            )
            replay_nav = (
                self._extract_nav(replay_inputs.report)
                if replay_inputs.is_research_evidence
                else self._extract_nav_from_report(replay_report)
            )
            validation = ReplayValidator.validate(
                original_manifest,
                replay_manifest,
                self._extract_nav(report),
                replay_nav,
                state_proof=state_proof,
                require_research_evidence=(
                    original_inputs.is_research_evidence
                    or replay_inputs.is_research_evidence
                ),
            )
            self._persist_replay_proof(
                original_run_id=original_run_id,
                replay_run_id=new_run_id,
                original_manifest=original_manifest,
                replay_manifest=replay_manifest,
                validation=validation,
                original_resume_provenance=_load_resume_provenance(report),
                replay_artifact_dir=replay_artifact_dir,
            )
            return ReplayResult(
                new_run_id=new_run_id,
                validation=validation,
                original_manifest=original_manifest,
                replay_manifest=replay_manifest,
            )
        finally:
            reservation.cleanup_empty()

    def _find_artifact_dir(self, run_id: str) -> Path:
        """查找运行对应的 artifact 目录."""
        return Path(self._find_artifact_record(run_id).file_path)

    def _find_artifact_record(self, run_id: str) -> StrategyArtifactRecord:
        """Return the indexed strategy artifact record for one run."""
        record = find_artifact(
            self._artifact_service,
            run_id,
            ArtifactKind.BACKTEST_REPORT,
        )
        if record is None:
            msg = f"Artifact directory not found for run: {run_id}"
            raise FileNotFoundError(msg)
        return record

    def _load_replay_inputs(
        self,
        record: StrategyArtifactRecord,
        *,
        load_report: bool = True,
    ) -> _ReplayInputs:
        """Load a genuine legacy v1 run or an index-verified R3 bundle."""
        pointer = _research_replay_pointer(record)
        if pointer is None:
            artifact_dir = Path(record.file_path)
            manifest = self._load_manifest(artifact_dir)
            if manifest.replay_evidence is not None:
                raise AppProcessError(
                    "R3 replay manifest is missing its persisted index marker",
                    reason="r3_replay_index_marker_missing",
                    run_id=record.run_id,
                )
            return _ReplayInputs(
                manifest=manifest,
                report=self._load_report(artifact_dir) if load_report else {},
                fill_log=None,
                is_research_evidence=False,
            )

        reader = self._verified_artifact_reader
        if reader is None:
            raise AppProcessError(
                "R3 replay requires an injected verified artifact reader",
                reason="verified_artifact_reader_required",
                run_id=record.run_id,
            )
        bundle = reader.read_bundle(record.run_id)
        if type(bundle) is not VerifiedReplayBundle:
            raise AppProcessError(
                "verified artifact reader returned an invalid bundle",
                reason="invalid_verified_replay_bundle",
                run_id=record.run_id,
            )
        manifest = _deserialize_manifest(dict(bundle.manifest_payload))
        evidence = manifest.replay_evidence
        if (
            bundle.schema_version != pointer.schema_version
            or bundle.run_id != record.run_id
            or manifest.run_id != record.run_id
            or evidence is None
            or evidence.schema_version != pointer.schema_version
            or evidence.reproduction_fingerprint != bundle.reproduction_fingerprint
            or evidence.required_artifacts != bundle.verified_artifacts
            or bundle.manifest_artifact.artifact_id != pointer.manifest_artifact_id
            or bundle.report_artifact_id != pointer.report_artifact_id
            or tuple(item.artifact_id for item in bundle.verified_artifacts)
            != pointer.required_artifact_ids
            or bundle.fill_log_artifact_id != pointer.fill_log_artifact_id
            or bundle.report_artifact_id != evidence.key_result_summary_artifact_id
        ):
            raise AppProcessError(
                "verified bundle fingerprint or required artifacts mismatch",
                reason="verified_replay_evidence_mismatch",
                run_id=record.run_id,
            )
        artifacts_by_id = {item.artifact_id: item for item in bundle.verified_artifacts}
        report_ref = artifacts_by_id.get(bundle.report_artifact_id)
        if report_ref is None or report_ref.artifact_format != "json":
            raise AppProcessError(
                "verified report is not one of the required JSON artifacts",
                reason="verified_replay_evidence_mismatch",
                run_id=record.run_id,
            )
        if bundle.fill_log_artifact_id is not None:
            fill_ref = artifacts_by_id.get(bundle.fill_log_artifact_id)
            if fill_ref is None or fill_ref.artifact_format != "parquet":
                raise AppProcessError(
                    "verified fill log is not one of the required Parquet artifacts",
                    reason="verified_replay_evidence_mismatch",
                    run_id=record.run_id,
                )
        return _ReplayInputs(
            manifest=manifest,
            report={str(key): value for key, value in bundle.report_payload.items()},
            fill_log=bundle.fill_log,
            is_research_evidence=True,
        )

    @staticmethod
    def _load_manifest(artifact_dir: Path) -> RunManifest:
        """从 artifact 目录加载 manifest.json."""
        manifest_path = artifact_dir / "manifest.json"
        if not manifest_path.exists():
            msg = f"manifest.json not found: {manifest_path}"
            raise FileNotFoundError(msg)
        raw: dict[str, Any] = orjson.loads(manifest_path.read_bytes())
        return _deserialize_manifest(raw)

    @staticmethod
    def _load_report(artifact_dir: Path) -> dict[str, Any]:
        """从 artifact 目录加载 backtest_report.json."""
        report_path = artifact_dir / "backtest_report.json"
        if not report_path.exists():
            msg = f"backtest_report.json not found: {report_path}"
            raise FileNotFoundError(msg)
        return orjson.loads(report_path.read_bytes())

    @staticmethod
    def _build_config(
        manifest: RunManifest,
        report: dict[str, Any],
        *,
        run_id: str = "",
        parent_run_id: str = "",
        run_config: dict[str, object] | None = None,
    ) -> BacktestServiceConfig:
        """从 manifest + report 恢复 BacktestServiceConfig."""
        period = report.get("period", {})
        return BacktestServiceConfig(
            strategy_id=manifest.strategy_id,
            strategy_version=manifest.strategy_version,
            run_id=run_id,
            spec_hash=manifest.spec_hash,
            base_spec_hash=manifest.base_spec_hash,
            parameter_hash=manifest.parameter_hash,
            effective_parameters=manifest.effective_parameters,
            research_snapshot_id=manifest.research_snapshot_id,
            research_snapshot_manifest_hash=(manifest.research_snapshot_manifest_hash),
            parent_run_id=parent_run_id,
            start_date=(
                _str_config_field(run_config, "start_date") or period.get("start", "")
            ),
            end_date=(
                _str_config_field(run_config, "end_date") or period.get("end", "")
            ),
            initial_cash=_initial_cash_from_config_or_report(run_config, report),
            parameter_overrides=(),
            candidate_parameters=tuple(
                CandidateParameter(path=item.path, value=item.value)
                for item in manifest.effective_parameters
            ),
            rebalance_freq=_extract_rebalance_freq(report),
            engine_version=manifest.engine_version,
            random_seed=_int_config_field(run_config, "random_seed", default=42),
            execution_delay=_int_config_field(run_config, "execution_delay"),
            knowledge_lag_days=_int_config_field(
                run_config,
                "knowledge_lag_days",
                default=1,
            ),
            resume_from_run_id=_str_config_field(run_config, "resume_from_run_id"),
            resume_checkpoint_trade_date=_str_config_field(
                run_config,
                "resume_checkpoint_trade_date",
            ),
            resume_checkpoint_completed_days=_int_config_field(
                run_config,
                "resume_checkpoint_completed_days",
            ),
            resume_checkpoint_total_days=_int_config_field(
                run_config,
                "resume_checkpoint_total_days",
            ),
            resume_checkpoint_nav=_float_config_field(
                run_config,
                "resume_checkpoint_nav",
            ),
            resume_checkpoint_order_count=_int_config_field(
                run_config,
                "resume_checkpoint_order_count",
            ),
            resume_checkpoint_fill_count=_int_config_field(
                run_config,
                "resume_checkpoint_fill_count",
            ),
            resume_account_state_json=_str_config_field(
                run_config,
                "resume_account_state_json",
            ),
            resume_account_state_hash=_str_config_field(
                run_config,
                "resume_account_state_hash",
            ),
            resume_settlement_state_json=_str_config_field(
                run_config,
                "resume_settlement_state_json",
            ),
            resume_settlement_state_hash=_str_config_field(
                run_config,
                "resume_settlement_state_hash",
            ),
            resume_runtime_state_json=_str_config_field(
                run_config,
                "resume_runtime_state_json",
            ),
            resume_runtime_state_hash=_str_config_field(
                run_config,
                "resume_runtime_state_hash",
            ),
        )

    @staticmethod
    def _extract_nav(report: dict[str, Any]) -> list[float]:
        """从 backtest_report 提取 NAV 序列."""
        nav_data = report.get("nav_series")
        if nav_data is not None:
            return [float(v) for v in nav_data]
        final_nav = report.get("final_nav")
        if final_nav is not None:
            return [float(final_nav)]
        return []

    @staticmethod
    def _extract_nav_from_report(report: BacktestReport) -> list[float]:
        """从 BacktestReport 对象提取 NAV 序列."""
        if report.nav_series:
            return [float(v) for _, v in report.nav_series]
        if report.final_nav:
            return [float(report.final_nav)]
        return []

    def _load_run_config(self, run_id: str) -> dict[str, object] | None:
        """Load original run-control config JSON when a run model is available."""
        if self._run_model is None:
            return None
        record = self._run_model.get_run(run_id)
        if record is None or not record.config_json:
            return None
        try:
            raw = orjson.loads(record.config_json)
        except orjson.JSONDecodeError as exc:
            msg = f"Invalid config_json for replay run: {run_id}"
            raise AppProcessError(msg) from exc
        if not isinstance(raw, dict):
            msg = f"config_json for replay run must be an object: {run_id}"
            raise AppProcessError(msg)
        data = cast(dict[object, object], raw)
        return {str(key): value for key, value in data.items()}

    def _persist_replay_proof(
        self,
        *,
        original_run_id: str,
        replay_run_id: str,
        original_manifest: RunManifest,
        replay_manifest: RunManifest,
        validation: ReplayValidationResult,
        original_resume_provenance: dict[str, object] | None,
        replay_artifact_dir: Path,
    ) -> None:
        """写出 replay proof JSON 并登记 strategy artifact 记录."""
        replay_artifact_dir.mkdir(parents=True, exist_ok=True)
        proof_path = replay_artifact_dir / "replay_proof.json"
        created_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        payload = _build_replay_proof_payload(
            original_run_id=original_run_id,
            replay_run_id=replay_run_id,
            validation=validation,
            original_replay_evidence=original_manifest.replay_evidence,
            replay_replay_evidence=replay_manifest.replay_evidence,
            original_resume_provenance=original_resume_provenance,
            created_at=created_at,
        )
        atomic_bytes_write(
            orjson.dumps(payload, option=orjson.OPT_INDENT_2),
            proof_path,
        )

        metadata: dict[str, object] = {
            "original_run_id": original_run_id,
            "replay_run_id": replay_run_id,
            "is_reproducible": validation.is_reproducible,
            "nav_correlation": validation.nav_correlation,
            "max_nav_diff_bps": validation.max_nav_diff_bps,
            "input_data_match": validation.input_data_match,
            "manifest_has_diff": validation.manifest_diff.has_diff,
            "fill_match": validation.fill_match,
            "account_state_match": validation.account_state_match,
            "proof_path": str(proof_path),
        }
        if original_manifest.replay_evidence is not None:
            metadata.update(
                {
                    "replay_evidence_schema_version": (
                        original_manifest.replay_evidence.schema_version
                    ),
                    "reproduction_fingerprint": (
                        original_manifest.replay_evidence.reproduction_fingerprint
                    ),
                    "reproduction_fingerprint_match": (
                        validation.reproduction_fingerprint_match
                    ),
                    "key_result_summary_match": validation.key_result_summary_match,
                    "required_artifact_hashes_match": (
                        validation.required_artifact_hashes_match
                    ),
                }
            )
        metadata.update(_resume_provenance_metadata(original_resume_provenance))

        self._artifact_service.save_artifact(
            StrategyArtifactRecord(
                artifact_id=f"replay-proof-{replay_run_id}",
                strategy_id=original_manifest.strategy_id,
                run_id=replay_run_id,
                artifact_type=ArtifactKind.REPLAY_PROOF,
                file_path=str(replay_artifact_dir),
                metadata=metadata,
                created_at=created_at,
            ),
        )


def _extract_rebalance_freq(report: dict[str, Any]) -> str:
    """从报告中提取调仓频率."""
    freq = report.get("rebalance_freq")
    if isinstance(freq, str) and freq:
        return freq
    return "daily"


def _str_config_field(config: dict[str, object] | None, key: str) -> str:
    """Read an optional run-config string field."""
    if config is None:
        return ""
    value = config.get(key)
    return value if isinstance(value, str) else ""


def _int_config_field(
    config: dict[str, object] | None,
    key: str,
    *,
    default: int = 0,
) -> int:
    """Read an optional run-config int field without treating bool as int."""
    if config is None:
        return default
    value = config.get(key)
    if isinstance(value, bool):
        return default
    return value if isinstance(value, int) else default


def _float_config_field(config: dict[str, object] | None, key: str) -> float:
    """Read an optional run-config numeric field."""
    value = _optional_float_config_field(config, key)
    return value if value is not None else 0.0


def _optional_float_config_field(
    config: dict[str, object] | None,
    key: str,
) -> float | None:
    """Read an optional run-config numeric field as a nullable value."""
    if config is None:
        return None
    value = config.get(key)
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _initial_cash_from_config_or_report(
    run_config: dict[str, object] | None,
    report: dict[str, Any],
) -> float:
    """Use original run config cash when available, falling back to report cash."""
    config_cash = _optional_float_config_field(run_config, "initial_cash")
    if config_cash is not None:
        return config_cash
    return float(report.get("initial_cash", DEFAULT_INITIAL_CASH))
