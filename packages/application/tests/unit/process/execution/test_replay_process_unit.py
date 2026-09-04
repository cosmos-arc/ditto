"""
ReplayProcess 单元测试 — 回测重放编排.

覆盖：replay() 成功流程、FileNotFoundError、_load_manifest、
_build_config、_extract_nav、_load_report、_find_artifact_dir。
"""

from __future__ import annotations

import math
from datetime import datetime
from pathlib import Path
from types import MappingProxyType, SimpleNamespace
from unittest.mock import MagicMock, patch

import orjson
import polars as pl
import pytest
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.execution.backtest_process import (
    BacktestServiceConfig,
    BacktestServiceOptions,
)
from ditto_application.processes.execution.replay_process import (
    IndexedResearchReplayArtifactReader,
    ReplayProcess,
    VerifiedReplayBundle,
)
from ditto_backtest.manifest import RunManifest, serialize_manifest
from ditto_backtest.manifest_types import ReplayArtifactRef, ResearchReplayEvidence
from ditto_backtest.replay import ManifestDiff, ReplayValidationResult
from ditto_backtest.result import BacktestAccountStateSnapshot
from ditto_backtest.statistics import BacktestReport
from ditto_kernel.identity import InstrumentId
from ditto_kernel.order import OrderSide
from ditto_portfolio.accounting import AccountView, CashBook, Position
from ditto_portfolio.accounting.fills import FillEvent
from ditto_strategy.alpha.parameters import (
    CandidateParameter,
    EffectiveParameter,
    canonical_parameter_hash,
)
from ditto_strategy.models import ArtifactKind
from ditto_strategy.runs.models import StrategyRunRecord


@pytest.fixture(autouse=True)
def _stable_replay_run_id(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep replay identity deterministic while production uses a fresh UUID."""
    monkeypatch.setattr(
        "ditto_application.processes.execution.replay_process.resolve_run_id",
        lambda configured_run_id: configured_run_id or "run-replay",
    )


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


def _make_manifest_raw(
    *,
    run_id: str = "run-original",
    strategy_id: str = "strat-1",
    strategy_version: str = "3",
    mode: str = "backtest",
    created_at: str = "2026-04-10T00:00:00Z",
    config_hash: str = "hash-abc",
    engine_version: str = "0.1.0",
    **overrides: object,
) -> dict[str, object]:
    """构建 manifest.json 的原始 dict."""
    raw: dict[str, object] = {
        "run_id": run_id,
        "strategy_id": strategy_id,
        "strategy_version": strategy_version,
        "mode": mode,
        "created_at": created_at,
        "input_refs": [],
        "input_ref_details": [],
        "parameter_overrides": [],
        "rule_refs": [],
        "artifacts": [],
        "config_hash": config_hash,
        "engine_version": engine_version,
        "rule_resolution_policy": "as_of_date",
        "universe_hash": "",
        "spec_hash": "a" * 64,
        "base_spec_hash": "b" * 64,
        "parameter_hash": (
            "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945"
        ),
        "effective_parameters": [],
        "research_snapshot_id": None,
        "research_snapshot_manifest_hash": None,
        "dependency_versions": [],
        "random_seed": None,
    }
    raw.update(overrides)
    return raw


def _make_report_dict(
    *,
    period_start: str = "2026-01-01",
    period_end: str = "2026-03-31",
    initial_cash: float = 1_000_000.0,
    final_nav: float = 1_050_000.0,
    rebalance_freq: str = "weekly",
    nav_series: list[float] | None = None,
) -> dict[str, object]:
    """构建 backtest_report.json 的原始 dict."""
    report: dict[str, object] = {
        "period": {"start": period_start, "end": period_end},
        "initial_cash": initial_cash,
        "final_nav": final_nav,
        "rebalance_freq": rebalance_freq,
    }
    if nav_series is not None:
        report["nav_series"] = nav_series
    return report


def _make_replay_evidence_raw(
    *,
    schema_version: int = 1,
    reproduction_fingerprint: str = "f" * 64,
    summary_hash: str = "1" * 64,
    nav_hash: str = "2" * 64,
    artifact_id_suffix: str = "",
) -> dict[str, object]:
    """Build canonical Schema v1 research replay evidence JSON."""
    return {
        "schema_version": schema_version,
        "reproduction_fingerprint": reproduction_fingerprint,
        "key_result_summary_artifact_id": f"artifact-summary{artifact_id_suffix}",
        "required_artifacts": [
            {
                "artifact_id": f"artifact-nav{artifact_id_suffix}",
                "artifact_kind": "nav",
                "artifact_format": "parquet",
                "content_hash": nav_hash,
                "schema_hash": "e" * 64,
                "row_count": 2,
                "byte_size": 128,
            },
            {
                "artifact_id": f"artifact-summary{artifact_id_suffix}",
                "artifact_kind": "summary",
                "artifact_format": "json",
                "content_hash": summary_hash,
                "schema_hash": "d" * 64,
                "row_count": 1,
                "byte_size": 64,
            },
        ],
    }


def _make_research_replay_metadata(
    *,
    artifact_id_suffix: str = "",
    fill_log_artifact_id: str | None = None,
) -> dict[str, object]:
    return {
        "research_replay_evidence_version": 1,
        "research_replay_bundle": {
            "schema_version": 1,
            "manifest_artifact_id": f"artifact-manifest{artifact_id_suffix}",
            "report_artifact_id": f"artifact-summary{artifact_id_suffix}",
            "required_artifact_ids": [
                f"artifact-nav{artifact_id_suffix}",
                f"artifact-summary{artifact_id_suffix}",
            ],
            "fill_log_artifact_id": fill_log_artifact_id,
        },
    }


def _make_verified_replay_bundle(
    *,
    run_id: str = "run-original",
    reproduction_fingerprint: str = "f" * 64,
    manifest_payload: dict[str, object] | None = None,
    report_payload: dict[str, object] | None = None,
    artifact_id_suffix: str = "",
) -> VerifiedReplayBundle:
    raw = manifest_payload or _make_manifest_raw(
        run_id=run_id,
        replay_evidence=_make_replay_evidence_raw(
            reproduction_fingerprint=reproduction_fingerprint,
            artifact_id_suffix=artifact_id_suffix,
        ),
    )
    return VerifiedReplayBundle(
        run_id=run_id,
        manifest_payload=raw,
        report_payload=report_payload or _make_report_dict(nav_series=[1.0, 1.01]),
        manifest_artifact=ReplayArtifactRef(
            artifact_id=f"artifact-manifest{artifact_id_suffix}",
            artifact_kind="run_manifest",
            artifact_format="json",
            content_hash="3" * 64,
            schema_hash="c" * 64,
            row_count=1,
            byte_size=512,
        ),
        reproduction_fingerprint=reproduction_fingerprint,
        report_artifact_id=f"artifact-summary{artifact_id_suffix}",
        verified_artifacts=(
            ReplayArtifactRef(
                artifact_id=f"artifact-nav{artifact_id_suffix}",
                artifact_kind="nav",
                artifact_format="parquet",
                content_hash="2" * 64,
                schema_hash="e" * 64,
                row_count=2,
                byte_size=128,
            ),
            ReplayArtifactRef(
                artifact_id=f"artifact-summary{artifact_id_suffix}",
                artifact_kind="summary",
                artifact_format="json",
                content_hash="1" * 64,
                schema_hash="d" * 64,
                row_count=1,
                byte_size=64,
            ),
        ),
    )


def _make_indexed_artifact_record(
    *,
    artifact_id: str,
    artifact_kind: str,
    artifact_format: str,
    run_id: str = "run-original",
    experiment_id: str = "experiment-1",
    candidate_id: str = "candidate-1",
    fold_id: str = "fold-1",
    attempt_id: str = "attempt-1",
) -> SimpleNamespace:
    return SimpleNamespace(
        artifact_id=artifact_id,
        artifact_kind=artifact_kind,
        experiment_id=experiment_id,
        candidate_id=candidate_id,
        fold_id=fold_id,
        attempt_id=attempt_id,
        content_hash="1" * 64,
        schema_hash="2" * 64,
        row_count=1,
        byte_size=128,
        reproduction_fingerprint="f" * 64,
        manifest={
            "format": artifact_format,
            "audit": {"run_id": run_id, "attempt_id": attempt_id},
        },
    )


def _make_replay_validation_result(
    *,
    is_reproducible: bool = True,
    nav_correlation: float = 1.0,
    max_nav_diff_bps: float = 0.0,
) -> ReplayValidationResult:
    """构建 ReplayValidationResult."""
    return ReplayValidationResult(
        is_reproducible=is_reproducible,
        nav_correlation=nav_correlation,
        max_nav_diff_bps=max_nav_diff_bps,
        manifest_diff=ManifestDiff(),
        input_data_match=True,
    )


def _make_backtest_report(
    *,
    run_id: str = "run-replay",
    final_nav: float = 1_050_000.0,
    nav_series: tuple[tuple[str, float], ...] | None = None,
    fill_log: tuple[FillEvent, ...] = (),
    final_account_state: AccountView | None = None,
) -> BacktestReport:
    """构建 BacktestReport mock 对象."""
    report = MagicMock(spec=BacktestReport)
    report.run_id = run_id
    report.final_nav = final_nav
    report.nav_series = nav_series or ()
    report.fill_log = fill_log
    report.final_account_state = final_account_state
    return report


def _configure_replay_execution(
    *,
    artifact_service: MagicMock,
    facade: MagicMock,
    original_record: MagicMock,
    replay_record: MagicMock,
    replay_dir: Path,
    replay_manifest_raw: dict[str, object],
    replay_report: BacktestReport,
) -> None:
    """Materialize the reserved replay target when the mocked facade executes."""
    artifact_service.list_artifacts.return_value = [original_record]

    def _execute(
        *,
        config: BacktestServiceConfig,
        version: int | None,
        options: BacktestServiceOptions,
    ) -> BacktestReport:
        assert version is None or isinstance(version, int)
        root = Path(str(options.artifact_dir))
        target = root / config.run_id
        assert target == replay_dir
        assert target.is_dir()
        (target / "manifest.json").write_bytes(orjson.dumps(replay_manifest_raw))
        artifact_service.list_artifacts.return_value = [
            replay_record,
            original_record,
        ]
        return replay_report

    facade.run_backtest_from_catalog.side_effect = _execute


def _make_account_view() -> AccountView:
    """构建稳定的 account-state proof 样本."""
    instrument_id = InstrumentId(510300)
    position = Position(
        instrument_id=instrument_id,
        quantity=1000,
        available_quantity=1000,
        average_cost=3.5,
        market_value=3500.0,
        unrealized_pnl=0.0,
        realized_pnl=125.0,
        total_fees=8.0,
    )
    return AccountView(
        positions=MappingProxyType({instrument_id: position}),
        cash=CashBook(available=1_046_500.0, settled=1_046_500.0, frozen=0.0),
        total_value=1_050_000.0,
        nav=1_050_000.0,
        exposure=3500.0,
    )


def _make_fill(
    *,
    fill_id: str = "fill-1",
    order_id: str = "order-1",
    instrument_id: int = 510300,
    direction: OrderSide = OrderSide.BUY,
    filled_quantity: int = 100,
    fill_price: float = 3.5,
    fee: float = 1.2,
    event_time: datetime | None = None,
) -> FillEvent:
    """构建稳定的 fill proof 样本."""
    return FillEvent(
        fill_id=fill_id,
        order_id=order_id,
        instrument_id=InstrumentId(instrument_id),
        direction=direction,
        filled_quantity=filled_quantity,
        fill_price=fill_price,
        fee=fee,
        slippage=0.0,
        event_time=event_time or datetime(2026, 1, 2, 15, 0),
        cumulative_quantity=filled_quantity,
        leaves_quantity=0,
        correlation_id=f"corr-{order_id}",
    )


def _write_fill_log(path: Path, fills: tuple[FillEvent, ...]) -> None:
    """写出与 BacktestReport artifact 兼容的 fill_log.parquet."""
    pl.DataFrame(
        [
            {
                "fill_id": fill.fill_id,
                "order_id": fill.order_id,
                "instrument_id": int(fill.instrument_id),
                "direction": fill.direction.value,
                "filled_quantity": fill.filled_quantity,
                "fill_price": fill.fill_price,
                "fee": fill.fee,
                "slippage": fill.slippage,
                "event_time": fill.event_time,
                "cumulative_quantity": fill.cumulative_quantity,
                "leaves_quantity": fill.leaves_quantity,
                "correlation_id": fill.correlation_id,
            }
            for fill in fills
        ],
    ).write_parquet(path)


# ---------------------------------------------------------------------------
# _load_manifest 测试
# ---------------------------------------------------------------------------


class TestLoadManifest:
    """ReplayProcess._load_manifest — 从 artifact 目录加载 manifest.json."""

    def test_load_manifest_success(self, tmp_path: Path) -> None:
        """正常加载 manifest.json."""
        from ditto_application.processes.execution.replay_process import ReplayProcess

        raw = _make_manifest_raw()
        raw["input_ref_details"] = [
            {
                "instrument_id": 510300,
                "data_hash": "sha256:aaa",
                "date_range": ["2026-01-01", "2026-01-31"],
                "source": "tushare",
                "source_snapshot_id": "snapshot-v1",
            }
        ]
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_bytes(orjson.dumps(raw))

        manifest = ReplayProcess._load_manifest(tmp_path)

        assert isinstance(manifest, RunManifest)
        assert manifest.run_id == "run-original"
        assert manifest.strategy_id == "strat-1"
        assert manifest.strategy_version == "3"
        assert manifest.input_ref_details[0].source_snapshot_id == "snapshot-v1"

    def test_load_manifest_preserves_all_deterministic_time_fields(
        self,
        tmp_path: Path,
    ) -> None:
        raw = _make_manifest_raw(
            pit_time_column="known_at",
            pit_policy="strict_as_of",
            unsafe_time_policy="explicit_unsafe_research",
            knowledge_lag_days=3,
        )
        (tmp_path / "manifest.json").write_bytes(orjson.dumps(raw))

        manifest = ReplayProcess._load_manifest(tmp_path)

        assert manifest.pit_time_column == "known_at"
        assert manifest.pit_policy == "strict_as_of"
        assert manifest.unsafe_time_policy == "explicit_unsafe_research"
        assert manifest.knowledge_lag_days == 3

    def test_load_manifest_decodes_complete_r3_evidence(self, tmp_path: Path) -> None:
        raw = _make_manifest_raw(replay_evidence=_make_replay_evidence_raw())
        (tmp_path / "manifest.json").write_bytes(orjson.dumps(raw))

        manifest = ReplayProcess._load_manifest(tmp_path)

        assert type(manifest.replay_evidence) is ResearchReplayEvidence
        assert manifest.replay_evidence.schema_version == 1
        assert manifest.replay_evidence.reproduction_fingerprint == "f" * 64
        assert manifest.replay_evidence.key_result_summary.content_hash == "1" * 64

    def test_load_manifest_rejects_unknown_r3_evidence_version(
        self,
        tmp_path: Path,
    ) -> None:
        raw = _make_manifest_raw(
            replay_evidence=_make_replay_evidence_raw(schema_version=2)
        )
        (tmp_path / "manifest.json").write_bytes(orjson.dumps(raw))

        with pytest.raises(AppProcessError, match="schema_version") as exc_info:
            ReplayProcess._load_manifest(tmp_path)

        assert exc_info.value.details["reason"] == "invalid_replay_evidence"

    def test_load_manifest_rejects_unknown_r3_evidence_field(
        self,
        tmp_path: Path,
    ) -> None:
        evidence = _make_replay_evidence_raw()
        evidence["unknown"] = "must-not-be-ignored"
        raw = _make_manifest_raw(replay_evidence=evidence)
        (tmp_path / "manifest.json").write_bytes(orjson.dumps(raw))

        with pytest.raises(AppProcessError, match="fields") as exc_info:
            ReplayProcess._load_manifest(tmp_path)

        assert exc_info.value.details["reason"] == "invalid_replay_evidence"

    def test_load_manifest_rejects_duplicate_required_artifact(
        self,
        tmp_path: Path,
    ) -> None:
        evidence = _make_replay_evidence_raw()
        artifacts = list(evidence["required_artifacts"])
        artifacts.append(dict(artifacts[0]))
        evidence["required_artifacts"] = artifacts
        raw = _make_manifest_raw(replay_evidence=evidence)
        (tmp_path / "manifest.json").write_bytes(orjson.dumps(raw))

        with pytest.raises(AppProcessError, match="unique") as exc_info:
            ReplayProcess._load_manifest(tmp_path)

        assert exc_info.value.details["reason"] == "invalid_replay_evidence"

    def test_load_manifest_file_not_found(self, tmp_path: Path) -> None:
        """manifest.json 不存在时抛出 FileNotFoundError."""
        from ditto_application.processes.execution.replay_process import ReplayProcess

        with pytest.raises(FileNotFoundError, match=r"manifest\.json not found"):
            ReplayProcess._load_manifest(tmp_path)

    @pytest.mark.parametrize(
        "field_name",
        [
            "spec_hash",
            "base_spec_hash",
            "parameter_hash",
            "effective_parameters",
            "research_snapshot_id",
            "research_snapshot_manifest_hash",
        ],
    )
    def test_load_manifest_rejects_missing_identity_field(
        self,
        tmp_path: Path,
        field_name: str,
    ) -> None:
        """历史 manifest 缺 identity 时必须明确 fail closed。"""
        from ditto_application.processes.execution.replay_process import ReplayProcess

        raw = _make_manifest_raw()
        raw.pop(field_name)
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_bytes(orjson.dumps(raw))

        with pytest.raises(AppProcessError, match=field_name) as exc_info:
            ReplayProcess._load_manifest(tmp_path)

        assert exc_info.value.details["field_name"] == field_name
        assert exc_info.value.details["reason"] == "missing_reproduction_identity"

    @pytest.mark.parametrize(
        "invalid_hash",
        [
            pytest.param("", id="empty"),
            pytest.param("a" * 16, id="short"),
            pytest.param("A" * 64, id="uppercase"),
            pytest.param("z" * 64, id="non-hex"),
        ],
    )
    def test_load_manifest_rejects_invalid_spec_hash(
        self,
        tmp_path: Path,
        invalid_hash: str,
    ) -> None:
        from ditto_application.processes.execution.replay_process import ReplayProcess

        raw = _make_manifest_raw(spec_hash=invalid_hash)
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_bytes(orjson.dumps(raw))

        with pytest.raises(AppProcessError, match="spec_hash") as exc_info:
            ReplayProcess._load_manifest(tmp_path)

        assert exc_info.value.details["field_name"] == "spec_hash"
        assert exc_info.value.details["reason"] == "invalid_canonical_identity"

    def test_signed_zero_manifest_replay_round_trip_has_one_identity(
        self,
        tmp_path: Path,
    ) -> None:
        """Persisted -0.0 loads and reserializes as canonical +0.0 with one hash."""
        from ditto_application.processes.execution.replay_process import ReplayProcess

        path = "/pipeline/nodes/legacy_factor_set/config/params/threshold"
        positive = (EffectiveParameter(path=path, value=0.0),)
        raw = _make_manifest_raw(
            parameter_hash=canonical_parameter_hash(positive),
            effective_parameters=[{"path": path, "value": -0.0}],
        )
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_bytes(orjson.dumps(raw))

        first = ReplayProcess._load_manifest(tmp_path)
        canonical_raw = orjson.loads(serialize_manifest(first))
        manifest_path.write_bytes(orjson.dumps(canonical_raw))
        second = ReplayProcess._load_manifest(tmp_path)

        first_value = first.effective_parameters[0].value
        assert isinstance(first_value, float)
        assert math.copysign(1.0, first_value) == 1.0
        assert canonical_raw["effective_parameters"][0]["value"] == 0.0
        assert first.effective_parameters == second.effective_parameters
        assert first.parameter_hash == second.parameter_hash


# ---------------------------------------------------------------------------
# _load_report 测试
# ---------------------------------------------------------------------------


class TestLoadReport:
    """ReplayProcess._load_report — 从 artifact 目录加载 backtest_report.json."""

    def test_load_report_success(self, tmp_path: Path) -> None:
        """正常加载 backtest_report.json."""
        from ditto_application.processes.execution.replay_process import ReplayProcess

        report_dict = _make_report_dict()
        report_path = tmp_path / "backtest_report.json"
        report_path.write_bytes(orjson.dumps(report_dict))

        report = ReplayProcess._load_report(tmp_path)

        assert report["initial_cash"] == 1_000_000.0
        assert report["period"]["start"] == "2026-01-01"

    def test_load_report_file_not_found(self, tmp_path: Path) -> None:
        """backtest_report.json 不存在时抛出 FileNotFoundError."""
        from ditto_application.processes.execution.replay_process import ReplayProcess

        with pytest.raises(FileNotFoundError, match=r"backtest_report\.json not found"):
            ReplayProcess._load_report(tmp_path)


class TestVerifiedReplayArtifactBoundary:
    """R3 artifacts must enter ReplayProcess only through the verified index port."""

    @staticmethod
    def _record(*, marker: object = 1, path: str = "/must-not-be-read") -> MagicMock:
        record = MagicMock()
        record.run_id = "run-original"
        record.artifact_type = ArtifactKind.BACKTEST_REPORT
        record.file_path = path
        record.metadata = _make_research_replay_metadata()
        record.metadata["research_replay_evidence_version"] = marker
        return record

    def test_r3_marker_requires_verified_reader(self) -> None:
        process = ReplayProcess(MagicMock(), MagicMock())

        with pytest.raises(AppProcessError, match="verified artifact reader") as exc:
            process._load_replay_inputs(self._record())

        assert exc.value.details["reason"] == "verified_artifact_reader_required"

    @pytest.mark.parametrize("marker", [0, 2, True, "1", None])
    def test_unknown_or_malformed_r3_marker_fails_closed(self, marker: object) -> None:
        reader = MagicMock()
        process = ReplayProcess(
            MagicMock(),
            MagicMock(),
            verified_artifact_reader=reader,
        )

        with pytest.raises(AppProcessError, match="version") as exc:
            process._load_replay_inputs(self._record(marker=marker))

        assert exc.value.details["reason"] == "unsupported_replay_evidence_version"
        reader.read_bundle.assert_not_called()

    def test_indexed_r3_bundle_never_reads_raw_artifact_directory(self) -> None:
        reader = MagicMock()
        reader.read_bundle.return_value = _make_verified_replay_bundle()
        process = ReplayProcess(
            MagicMock(),
            MagicMock(),
            verified_artifact_reader=reader,
        )

        with (
            patch.object(
                ReplayProcess,
                "_load_manifest",
                side_effect=AssertionError("raw manifest bypassed the index"),
            ),
            patch.object(
                ReplayProcess,
                "_load_report",
                side_effect=AssertionError("raw report bypassed the index"),
            ),
        ):
            loaded = process._load_replay_inputs(self._record())

        assert loaded.is_research_evidence is True
        assert loaded.manifest.replay_evidence is not None
        assert loaded.report["nav_series"] == [1.0, 1.01]
        reader.read_bundle.assert_called_once_with("run-original")

    def test_verified_bundle_fingerprint_must_match_manifest(self) -> None:
        reader = MagicMock()
        reader.read_bundle.return_value = _make_verified_replay_bundle(
            reproduction_fingerprint="0" * 64,
            manifest_payload=_make_manifest_raw(
                replay_evidence=_make_replay_evidence_raw(
                    reproduction_fingerprint="f" * 64,
                )
            ),
        )
        process = ReplayProcess(
            MagicMock(),
            MagicMock(),
            verified_artifact_reader=reader,
        )

        with pytest.raises(AppProcessError, match="fingerprint") as exc:
            process._load_replay_inputs(self._record())

        assert exc.value.details["reason"] == "verified_replay_evidence_mismatch"

    def test_verified_bundle_required_artifacts_must_be_exact(self) -> None:
        bundle = _make_verified_replay_bundle()
        reader = MagicMock()
        reader.read_bundle.return_value = VerifiedReplayBundle(
            run_id=bundle.run_id,
            manifest_payload=bundle.manifest_payload,
            report_payload=bundle.report_payload,
            manifest_artifact=bundle.manifest_artifact,
            reproduction_fingerprint=bundle.reproduction_fingerprint,
            report_artifact_id=bundle.report_artifact_id,
            verified_artifacts=(bundle.verified_artifacts[1],),
        )
        process = ReplayProcess(
            MagicMock(),
            MagicMock(),
            verified_artifact_reader=reader,
        )

        with pytest.raises(AppProcessError, match="required artifacts") as exc:
            process._load_replay_inputs(self._record())

        assert exc.value.details["reason"] == "verified_replay_evidence_mismatch"

    def test_manifest_r3_evidence_without_index_marker_cannot_fallback(
        self,
        tmp_path: Path,
    ) -> None:
        (tmp_path / "manifest.json").write_bytes(
            orjson.dumps(
                _make_manifest_raw(replay_evidence=_make_replay_evidence_raw())
            )
        )
        (tmp_path / "backtest_report.json").write_bytes(
            orjson.dumps(_make_report_dict())
        )
        record = self._record(path=str(tmp_path))
        record.metadata = {}
        process = ReplayProcess(MagicMock(), MagicMock())

        with pytest.raises(AppProcessError, match="index marker") as exc:
            process._load_replay_inputs(record)

        assert exc.value.details["reason"] == "r3_replay_index_marker_missing"

    def test_verified_reader_integrity_failure_propagates(self) -> None:
        reader = MagicMock()
        reader.read_bundle.side_effect = RuntimeError("artifact checksum mismatch")
        process = ReplayProcess(
            MagicMock(),
            MagicMock(),
            verified_artifact_reader=reader,
        )

        with pytest.raises(RuntimeError, match="checksum mismatch"):
            process._load_replay_inputs(self._record())

    @pytest.mark.parametrize(
        ("mutation", "expected_reason"),
        [
            ("missing_bundle", "invalid_replay_evidence_marker"),
            ("unknown_bundle_field", "invalid_replay_evidence_marker"),
            ("duplicate_required_id", "invalid_replay_evidence_marker"),
        ],
    )
    def test_marker_pointer_corruption_fails_before_verified_read(
        self,
        mutation: str,
        expected_reason: str,
    ) -> None:
        record = self._record()
        if mutation == "missing_bundle":
            del record.metadata["research_replay_bundle"]
        else:
            bundle = record.metadata["research_replay_bundle"]
            assert isinstance(bundle, dict)
            if mutation == "unknown_bundle_field":
                bundle["unexpected"] = "unsafe"
            else:
                bundle["required_artifact_ids"] = [
                    "artifact-summary",
                    "artifact-summary",
                ]
        reader = MagicMock()
        process = ReplayProcess(
            MagicMock(),
            MagicMock(),
            verified_artifact_reader=reader,
        )

        with pytest.raises(AppProcessError) as exc:
            process._load_replay_inputs(record)

        assert exc.value.details["reason"] == expected_reason
        reader.read_bundle.assert_not_called()

    @pytest.mark.parametrize(
        "mismatch",
        ["manifest", "report", "fill"],
    )
    def test_bundle_identity_must_exactly_match_persisted_pointer(
        self,
        mismatch: str,
    ) -> None:
        record = self._record()
        pointer = record.metadata["research_replay_bundle"]
        assert isinstance(pointer, dict)
        if mismatch == "manifest":
            pointer["manifest_artifact_id"] = "artifact-manifest-other"
        elif mismatch == "report":
            pointer["report_artifact_id"] = "artifact-nav"
        else:
            pointer["fill_log_artifact_id"] = "artifact-nav"
        reader = MagicMock()
        reader.read_bundle.return_value = _make_verified_replay_bundle()
        process = ReplayProcess(
            MagicMock(),
            MagicMock(),
            verified_artifact_reader=reader,
        )

        with pytest.raises(AppProcessError) as exc:
            process._load_replay_inputs(record)

        assert exc.value.details["reason"] == "verified_replay_evidence_mismatch"

    def test_report_must_be_the_manifest_key_result_summary(self) -> None:
        record = self._record()
        pointer = record.metadata["research_replay_bundle"]
        assert isinstance(pointer, dict)
        pointer["report_artifact_id"] = "artifact-nav"
        bundle = _make_verified_replay_bundle()
        reader = MagicMock()
        reader.read_bundle.return_value = VerifiedReplayBundle(
            run_id=bundle.run_id,
            manifest_payload=bundle.manifest_payload,
            report_payload=bundle.report_payload,
            manifest_artifact=bundle.manifest_artifact,
            reproduction_fingerprint=bundle.reproduction_fingerprint,
            report_artifact_id="artifact-nav",
            verified_artifacts=bundle.verified_artifacts,
        )
        process = ReplayProcess(
            MagicMock(),
            MagicMock(),
            verified_artifact_reader=reader,
        )

        with pytest.raises(AppProcessError) as exc:
            process._load_replay_inputs(record)

        assert exc.value.details["reason"] == "verified_replay_evidence_mismatch"


class TestIndexedResearchReplayArtifactReader:
    """The concrete adapter must assemble only one exact attempt lineage."""

    @staticmethod
    def _build(
        *,
        record_overrides: dict[str, dict[str, object]] | None = None,
        report_run_id: str | None = None,
    ) -> IndexedResearchReplayArtifactReader:
        strategy_record = MagicMock()
        strategy_record.run_id = "run-original"
        strategy_record.artifact_type = ArtifactKind.BACKTEST_REPORT
        strategy_record.metadata = _make_research_replay_metadata()
        strategy_service = MagicMock()
        strategy_service.list_artifacts.return_value = [strategy_record]

        records = {
            "artifact-manifest": _make_indexed_artifact_record(
                artifact_id="artifact-manifest",
                artifact_kind="run_manifest",
                artifact_format="json",
            ),
            "artifact-nav": _make_indexed_artifact_record(
                artifact_id="artifact-nav",
                artifact_kind="nav",
                artifact_format="parquet",
            ),
            "artifact-summary": _make_indexed_artifact_record(
                artifact_id="artifact-summary",
                artifact_kind="summary",
                artifact_format="json",
            ),
        }
        for artifact_id, overrides in (record_overrides or {}).items():
            record = records[artifact_id]
            for field_name, value in overrides.items():
                setattr(record, field_name, value)
        index_reader = MagicMock()
        index_reader.get_artifact.side_effect = records.get
        content_reader = MagicMock()
        report: dict[str, object] = {"nav_series": [1.0, 1.01]}
        if report_run_id is not None:
            report["run_id"] = report_run_id
        content_reader.read_indexed_json.side_effect = lambda artifact_id: {
            "artifact-manifest": {"run_id": "run-original"},
            "artifact-summary": report,
        }[artifact_id]
        content_reader.read_indexed_parquet.return_value = pl.DataFrame(
            {"nav": [1.0, 1.01]}
        )
        return IndexedResearchReplayArtifactReader(
            strategy_artifact_service=strategy_service,
            artifact_index_reader=index_reader,
            artifact_content_reader=content_reader,
        )

    def test_reads_one_exact_attempt_bundle(self) -> None:
        bundle = self._build(report_run_id="run-original").read_bundle("run-original")

        assert bundle.manifest_artifact.artifact_id == "artifact-manifest"
        assert bundle.report_artifact_id == "artifact-summary"
        assert tuple(item.artifact_id for item in bundle.verified_artifacts) == (
            "artifact-nav",
            "artifact-summary",
        )

    @pytest.mark.parametrize(
        ("artifact_id", "overrides"),
        [
            ("artifact-nav", {"attempt_id": "attempt-2"}),
            ("artifact-summary", {"experiment_id": "experiment-2"}),
        ],
    )
    def test_same_fingerprint_cannot_mix_cross_lineage_artifacts(
        self,
        artifact_id: str,
        overrides: dict[str, object],
    ) -> None:
        if "attempt_id" in overrides:
            overrides = {
                **overrides,
                "manifest": {
                    "format": "parquet",
                    "audit": {
                        "run_id": "run-original",
                        "attempt_id": "attempt-2",
                    },
                },
            }
        reader = self._build(record_overrides={artifact_id: overrides})

        with pytest.raises(AppProcessError, match="lineage") as exc:
            reader.read_bundle("run-original")

        assert exc.value.details["reason"] == "verified_replay_evidence_mismatch"

    def test_artifact_audit_must_match_typed_attempt(self) -> None:
        reader = self._build(
            record_overrides={
                "artifact-summary": {
                    "manifest": {
                        "format": "json",
                        "audit": {
                            "run_id": "run-original",
                            "attempt_id": "attempt-other",
                        },
                    }
                }
            }
        )

        with pytest.raises(AppProcessError, match="lineage") as exc:
            reader.read_bundle("run-original")

        assert exc.value.details["reason"] == "verified_replay_evidence_mismatch"

    def test_report_payload_run_id_must_match_request(self) -> None:
        reader = self._build(report_run_id="run-other")

        with pytest.raises(AppProcessError, match="different run") as exc:
            reader.read_bundle("run-original")

        assert exc.value.details["reason"] == "verified_replay_evidence_mismatch"


# ---------------------------------------------------------------------------
# _build_config 测试
# ---------------------------------------------------------------------------


class TestBuildConfig:
    """ReplayProcess._build_config — 从 manifest + report 恢复配置."""

    def test_build_config_defaults(self) -> None:
        """默认值 — period 为空时使用空字符串, initial_cash 默认 100 万."""
        from ditto_application.processes.execution.replay_process import ReplayProcess

        manifest = MagicMock(spec=RunManifest)
        manifest.strategy_id = "strat-1"
        manifest.strategy_version = "3"
        manifest.spec_hash = "a" * 64
        manifest.base_spec_hash = "b" * 64
        manifest.parameter_hash = (
            "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945"
        )
        manifest.effective_parameters = ()
        manifest.research_snapshot_id = None
        manifest.research_snapshot_manifest_hash = None
        manifest.context_input_refs = ()
        manifest.parameter_overrides = ()
        manifest.engine_version = "0.1.0"

        report = {"period": {}, "rebalance_freq": ""}

        config = ReplayProcess._build_config(
            manifest,
            report,
            parent_run_id="run-orig",
        )

        assert config.strategy_id == "strat-1"
        assert config.strategy_version == "3"
        assert config.spec_hash == "a" * 64
        assert config.parent_run_id == "run-orig"
        assert config.start_date == ""
        assert config.end_date == ""
        assert config.initial_cash == pytest.approx(1_000_000.0)
        assert config.rebalance_freq == "daily"  # 空字符串回退到 daily

    def test_build_config_with_values(self) -> None:
        """完整配置 — 从 report 恢复 period / cash / freq."""
        from ditto_application.processes.execution.replay_process import ReplayProcess

        manifest = MagicMock(spec=RunManifest)
        manifest.strategy_id = "strat-1"
        manifest.strategy_version = "3"
        manifest.spec_hash = "a" * 64
        manifest.base_spec_hash = "b" * 64
        manifest.parameter_hash = (
            "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945"
        )
        manifest.effective_parameters = ()
        manifest.research_snapshot_id = None
        manifest.research_snapshot_manifest_hash = None
        manifest.context_input_refs = ()
        manifest.parameter_overrides = ("--lookback=20",)
        manifest.engine_version = "0.2.0"

        report = _make_report_dict(
            period_start="2026-01-01",
            period_end="2026-06-30",
            initial_cash=500_000.0,
            rebalance_freq="monthly",
        )

        config = ReplayProcess._build_config(
            manifest,
            report,
            parent_run_id="run-orig",
        )

        assert config.start_date == "2026-01-01"
        assert config.end_date == "2026-06-30"
        assert config.initial_cash == pytest.approx(500_000.0)
        assert config.rebalance_freq == "monthly"
        assert config.parameter_overrides == ()
        assert config.engine_version == "0.2.0"

    def test_build_config_replays_effective_values_as_typed_candidates(self) -> None:
        """Complete manifest values rebuild the same resolved catalog runtime."""
        from ditto_application.processes.execution.replay_process import ReplayProcess

        effective_parameters = (
            EffectiveParameter(
                path="/pipeline/nodes/legacy_factor_set/config/params/top_k",
                value=2,
            ),
        )
        manifest = MagicMock(spec=RunManifest)
        manifest.strategy_id = "strat-1"
        manifest.strategy_version = "3"
        manifest.spec_hash = "a" * 64
        manifest.base_spec_hash = "b" * 64
        manifest.parameter_hash = canonical_parameter_hash(effective_parameters)
        manifest.effective_parameters = effective_parameters
        manifest.research_snapshot_id = None
        manifest.research_snapshot_manifest_hash = None
        manifest.context_input_refs = ()
        manifest.engine_version = "0.2.0"

        config = ReplayProcess._build_config(
            manifest,
            _make_report_dict(),
        )

        assert config.candidate_parameters == (
            CandidateParameter(
                path="/pipeline/nodes/legacy_factor_set/config/params/top_k",
                value=2,
            ),
        )


# ---------------------------------------------------------------------------
# _extract_nav 测试
# ---------------------------------------------------------------------------


class TestExtractNav:
    """ReplayProcess._extract_nav — 从 backtest_report dict 提取 NAV 序列."""

    def test_extract_nav_series(self) -> None:
        """有 nav_series 时直接返回."""
        from ditto_application.processes.execution.replay_process import ReplayProcess

        report = {"nav_series": [1.0, 1.01, 1.02, 1.015]}
        nav = ReplayProcess._extract_nav(report)
        assert nav == [1.0, 1.01, 1.02, 1.015]

    def test_extract_nav_final_only(self) -> None:
        """无 nav_series 时退而求其次用 final_nav."""
        from ditto_application.processes.execution.replay_process import ReplayProcess

        report = {"final_nav": 1.05}
        nav = ReplayProcess._extract_nav(report)
        assert nav == [1.05]

    def test_extract_nav_empty(self) -> None:
        """无 nav_series 也无 final_nav 时返回空列表."""
        from ditto_application.processes.execution.replay_process import ReplayProcess

        report: dict[str, object] = {}
        nav = ReplayProcess._extract_nav(report)
        assert nav == []

    def test_extract_nav_series_priority_over_final(self) -> None:
        """nav_series 优先级高于 final_nav."""
        from ditto_application.processes.execution.replay_process import ReplayProcess

        report = {"nav_series": [1.0, 1.1], "final_nav": 1.05}
        nav = ReplayProcess._extract_nav(report)
        assert nav == [1.0, 1.1]


# ---------------------------------------------------------------------------
# _extract_nav_from_report 测试
# ---------------------------------------------------------------------------


class TestExtractNavFromReport:
    """ReplayProcess._extract_nav_from_report — 从 BacktestReport 对象提取 NAV."""

    def test_extract_from_report_with_nav_series(self) -> None:
        """有 nav_series 时返回对应 NAV 值."""
        from ditto_application.processes.execution.replay_process import ReplayProcess

        report = _make_backtest_report(
            nav_series=(("2026-01-01", 1.0), ("2026-01-02", 1.02)),
        )

        nav = ReplayProcess._extract_nav_from_report(report)
        assert nav == [1.0, 1.02]

    def test_extract_from_report_final_nav_fallback(self) -> None:
        """无 nav_series 时用 final_nav."""
        from ditto_application.processes.execution.replay_process import ReplayProcess

        report = _make_backtest_report(
            final_nav=1.05,
            nav_series=(),
        )

        nav = ReplayProcess._extract_nav_from_report(report)
        assert nav == [1.05]

    def test_extract_from_report_empty(self) -> None:
        """无 nav_series 且无 final_nav 时返回空列表."""
        from ditto_application.processes.execution.replay_process import ReplayProcess

        report = _make_backtest_report(final_nav=0.0, nav_series=())

        nav = ReplayProcess._extract_nav_from_report(report)
        assert nav == []


# ---------------------------------------------------------------------------
# _find_artifact_dir 测试
# ---------------------------------------------------------------------------


class TestFindArtifactDir:
    """ReplayProcess._find_artifact_dir — 查找运行对应的 artifact 目录."""

    def test_find_success(self) -> None:
        """找到匹配的 artifact 记录."""
        from ditto_application.processes.execution.replay_process import ReplayProcess

        mock_artifact_service = MagicMock()
        mock_record = MagicMock()
        mock_record.run_id = "run-123"
        mock_record.artifact_type = ArtifactKind.BACKTEST_REPORT
        mock_record.file_path = "/data/artifacts/run-123"
        mock_artifact_service.list_artifacts.return_value = [mock_record]

        process = ReplayProcess(
            strategy_facade=MagicMock(),
            artifact_service=mock_artifact_service,
        )

        result = process._find_artifact_dir("run-123")

        assert result == Path("/data/artifacts/run-123")

    def test_find_not_found_raises(self) -> None:
        """找不到匹配的 artifact 时抛出 FileNotFoundError."""
        from ditto_application.processes.execution.replay_process import ReplayProcess

        mock_artifact_service = MagicMock()
        mock_artifact_service.list_artifacts.return_value = []

        process = ReplayProcess(
            strategy_facade=MagicMock(),
            artifact_service=mock_artifact_service,
        )

        with pytest.raises(FileNotFoundError, match="Artifact directory not found"):
            process._find_artifact_dir("run-unknown")


# ---------------------------------------------------------------------------
# replay() 完整流程测试
# ---------------------------------------------------------------------------


class TestReplaySuccess:
    """ReplayProcess.replay — 完整成功流程."""

    def test_replay_happy_path(self, tmp_path: Path) -> None:
        """端到端成功重放."""
        from ditto_application.processes.execution.replay_process import ReplayProcess

        # --- 准备 original artifact 目录 ---
        orig_dir = tmp_path / "artifacts" / "run-original"
        orig_dir.mkdir(parents=True)
        manifest_raw = _make_manifest_raw(run_id="run-original")
        report_raw = _make_report_dict(nav_series=[1.0, 1.01, 1.02])
        (orig_dir / "manifest.json").write_bytes(orjson.dumps(manifest_raw))
        (orig_dir / "backtest_report.json").write_bytes(orjson.dumps(report_raw))

        replay_dir = tmp_path / "artifacts" / "run-replay"
        replay_manifest_raw = _make_manifest_raw(
            run_id="run-replay",
            config_hash="hash-abc",  # 与 original 相同
        )

        # --- Mock ---
        mock_artifact_service = MagicMock()
        orig_record = MagicMock()
        orig_record.run_id = "run-original"
        orig_record.artifact_type = ArtifactKind.BACKTEST_REPORT
        orig_record.file_path = str(orig_dir)
        replay_record = MagicMock()
        replay_record.run_id = "run-replay"
        replay_record.artifact_type = ArtifactKind.BACKTEST_REPORT
        replay_record.file_path = str(replay_dir)
        replay_report = _make_backtest_report(
            run_id="run-replay",
            nav_series=(
                ("2026-01-01", 1.0),
                ("2026-01-02", 1.01),
                ("2026-01-03", 1.02),
            ),
        )

        mock_facade = MagicMock()
        _configure_replay_execution(
            artifact_service=mock_artifact_service,
            facade=mock_facade,
            original_record=orig_record,
            replay_record=replay_record,
            replay_dir=replay_dir,
            replay_manifest_raw=replay_manifest_raw,
            replay_report=replay_report,
        )

        process = ReplayProcess(
            strategy_facade=mock_facade,
            artifact_service=mock_artifact_service,
        )

        # --- 执行 ---
        result = process.replay("run-original")

        # --- 断言 ---
        assert result.new_run_id == "run-replay"
        assert isinstance(result.validation, ReplayValidationResult)
        assert isinstance(result.original_manifest, RunManifest)
        assert isinstance(result.replay_manifest, RunManifest)

        # facade 被正确调用
        mock_facade.run_backtest_from_catalog.assert_called_once()
        call_kwargs = mock_facade.run_backtest_from_catalog.call_args
        config = call_kwargs.kwargs.get("config") or call_kwargs[1].get("config")
        assert config is not None
        assert config.strategy_id == "strat-1"
        assert config.run_id == "run-replay"
        assert config.parent_run_id == "run-original"

        # version 参数正确
        version = call_kwargs.kwargs.get("version") or call_kwargs[1].get("version")
        assert version == 3  # "3" 被转为 int

    def test_r3_replay_uses_only_verified_bundles_and_accepts_new_artifact_ids(
        self,
        tmp_path: Path,
    ) -> None:
        artifacts_root = tmp_path / "artifacts"
        original_dir = artifacts_root / "run-original"
        replay_dir = artifacts_root / "run-replay"
        original_dir.mkdir(parents=True)

        original_record = MagicMock()
        original_record.run_id = "run-original"
        original_record.artifact_type = ArtifactKind.BACKTEST_REPORT
        original_record.file_path = str(original_dir)
        original_record.metadata = _make_research_replay_metadata(
            artifact_id_suffix="-attempt-1"
        )
        replay_record = MagicMock()
        replay_record.run_id = "run-replay"
        replay_record.artifact_type = ArtifactKind.BACKTEST_REPORT
        replay_record.file_path = str(replay_dir)
        replay_record.metadata = _make_research_replay_metadata(
            artifact_id_suffix="-attempt-2"
        )

        artifact_service = MagicMock()
        artifact_service.list_artifacts.return_value = [original_record]
        facade = MagicMock()

        def _execute(**_kwargs: object) -> BacktestReport:
            artifact_service.list_artifacts.return_value = [
                replay_record,
                original_record,
            ]
            return _make_backtest_report(
                run_id="run-replay",
                nav_series=(
                    ("2026-01-01", 9.0),
                    ("2026-01-02", 9.99),
                ),
            )

        facade.run_backtest_from_catalog.side_effect = _execute
        account_view = _make_account_view()
        verified_report = _make_report_dict(nav_series=[1.0, 1.01])
        verified_report["final_account_state"] = (
            BacktestAccountStateSnapshot.from_account_view(account_view).to_payload()
        )
        reader = MagicMock()
        reader.read_bundle.side_effect = lambda run_id: _make_verified_replay_bundle(
            run_id=run_id,
            artifact_id_suffix=(
                "-attempt-1" if run_id == "run-original" else "-attempt-2"
            ),
            report_payload=verified_report,
            manifest_payload=_make_manifest_raw(
                run_id=run_id,
                created_at=(
                    "2026-07-22T00:00:00Z"
                    if run_id == "run-original"
                    else "2026-07-23T00:00:00Z"
                ),
                replay_evidence=_make_replay_evidence_raw(
                    artifact_id_suffix=(
                        "-attempt-1" if run_id == "run-original" else "-attempt-2"
                    )
                ),
            ),
        )
        process = ReplayProcess(
            facade,
            artifact_service,
            verified_artifact_reader=reader,
        )

        with (
            patch.object(
                ReplayProcess,
                "_load_manifest",
                side_effect=AssertionError("raw manifest bypassed index"),
            ),
            patch.object(
                ReplayProcess,
                "_load_report",
                side_effect=AssertionError("raw report bypassed index"),
            ),
        ):
            result = process.replay("run-original")

        assert result.validation.is_reproducible is True
        assert result.validation.reproduction_fingerprint_match is True
        assert result.validation.key_result_summary_match is True
        assert result.validation.required_artifact_hashes_match is True
        assert result.validation.account_state_match is True
        assert [item.args for item in reader.read_bundle.call_args_list] == [
            ("run-original",),
            ("run-replay",),
        ]
        proof = orjson.loads((replay_dir / "replay_proof.json").read_bytes())
        assert proof["proof_version"] == 2

    def test_replay_persists_validation_proof_artifact(
        self,
        tmp_path: Path,
    ) -> None:
        """成功 replay 后持久化可审计的 replay proof 产物."""
        from ditto_application.processes.execution.replay_process import ReplayProcess
        from ditto_strategy.models import ArtifactKind

        orig_dir = tmp_path / "artifacts" / "run-original"
        orig_dir.mkdir(parents=True)
        (orig_dir / "manifest.json").write_bytes(
            orjson.dumps(_make_manifest_raw(run_id="run-original")),
        )
        (orig_dir / "backtest_report.json").write_bytes(
            orjson.dumps(_make_report_dict(nav_series=[1.0, 1.01, 1.02])),
        )

        replay_dir = tmp_path / "artifacts" / "run-replay"
        replay_manifest_raw = _make_manifest_raw(
            run_id="run-replay",
            config_hash="hash-abc",
        )

        orig_record = MagicMock()
        orig_record.run_id = "run-original"
        orig_record.artifact_type = ArtifactKind.BACKTEST_REPORT
        orig_record.file_path = str(orig_dir)
        replay_record = MagicMock()
        replay_record.run_id = "run-replay"
        replay_record.artifact_type = ArtifactKind.BACKTEST_REPORT
        replay_record.file_path = str(replay_dir)
        mock_artifact_service = MagicMock()

        mock_facade = MagicMock()
        replay_report = _make_backtest_report(
            run_id="run-replay",
            nav_series=(
                ("2026-01-01", 1.0),
                ("2026-01-02", 1.01),
                ("2026-01-03", 1.02),
            ),
        )
        _configure_replay_execution(
            artifact_service=mock_artifact_service,
            facade=mock_facade,
            original_record=orig_record,
            replay_record=replay_record,
            replay_dir=replay_dir,
            replay_manifest_raw=replay_manifest_raw,
            replay_report=replay_report,
        )

        process = ReplayProcess(
            strategy_facade=mock_facade,
            artifact_service=mock_artifact_service,
        )

        result = process.replay("run-original")

        proof_path = replay_dir / "replay_proof.json"
        assert proof_path.exists()
        payload = orjson.loads(proof_path.read_bytes())
        assert payload["original_run_id"] == "run-original"
        assert payload["replay_run_id"] == "run-replay"
        assert payload["is_reproducible"] is True
        assert payload["manifest_diff"]["has_diff"] is False
        assert payload["fill_match"] is None
        assert payload["account_state_match"] is None

        mock_artifact_service.save_artifact.assert_called_once()
        proof_record = mock_artifact_service.save_artifact.call_args.args[0]
        assert proof_record.artifact_id == "replay-proof-run-replay"
        assert proof_record.strategy_id == "strat-1"
        assert proof_record.run_id == result.new_run_id
        assert proof_record.artifact_type is ArtifactKind.REPLAY_PROOF
        assert proof_record.file_path == str(replay_dir)
        assert proof_record.metadata["original_run_id"] == "run-original"
        assert proof_record.metadata["is_reproducible"] is True
        assert proof_record.metadata["max_nav_diff_bps"] == 0.0

    def test_r3_replay_proof_freezes_exact_evidence_hashes(self) -> None:
        from ditto_application.processes.execution.replay_process import (
            _build_replay_proof_payload,
            _deserialize_manifest,
        )

        manifest = _deserialize_manifest(
            _make_manifest_raw(replay_evidence=_make_replay_evidence_raw())
        )
        evidence = manifest.replay_evidence
        assert evidence is not None
        replay_manifest = _deserialize_manifest(
            _make_manifest_raw(
                run_id="run-replay",
                replay_evidence=_make_replay_evidence_raw(artifact_id_suffix="-replay"),
            )
        )
        replay_evidence = replay_manifest.replay_evidence
        assert replay_evidence is not None
        validation = ReplayValidationResult(
            is_reproducible=True,
            nav_correlation=1.0,
            max_nav_diff_bps=0.0,
            manifest_diff=ManifestDiff(),
            input_data_match=True,
            reproduction_fingerprint_match=True,
            key_result_summary_match=True,
            required_artifact_hashes_match=True,
        )

        payload = _build_replay_proof_payload(
            original_run_id="run-original",
            replay_run_id="run-replay",
            validation=validation,
            original_replay_evidence=evidence,
            replay_replay_evidence=replay_evidence,
            created_at="2026-07-23T00:00:00Z",
        )

        assert payload["proof_version"] == 2
        assert payload["reproduction_fingerprint"] == "f" * 64
        assert payload["key_result_summary_hash"] == "1" * 64
        assert payload["reproduction_fingerprint_match"] is True
        assert payload["key_result_summary_match"] is True
        assert payload["required_artifact_hashes_match"] is True
        required = payload["required_artifacts"]
        assert isinstance(required, list)
        assert [item["content_hash"] for item in required] == ["2" * 64, "1" * 64]
        original = payload["original_replay_evidence"]
        replay = payload["replay_replay_evidence"]
        assert isinstance(original, dict)
        assert isinstance(replay, dict)
        assert original["key_result_summary_artifact_id"] == "artifact-summary"
        assert replay["key_result_summary_artifact_id"] == "artifact-summary-replay"

    def test_replay_proof_preserves_original_resume_provenance(
        self,
        tmp_path: Path,
    ) -> None:
        """重放 restored run 时，proof 应保留原始运行的 checkpoint 来源."""
        from ditto_application.processes.execution.replay_process import ReplayProcess

        resume_provenance = {
            "from_run_id": "run-root",
            "checkpoint_trade_date": "2026-01-31",
            "checkpoint_completed_days": 21,
            "checkpoint_total_days": 60,
            "checkpoint_nav": 1_020_000.0,
            "checkpoint_order_count": 4,
            "checkpoint_fill_count": 4,
            "account_state_hash": "sha256:account",
            "settlement_state_hash": "sha256:settlement",
            "runtime_state_hash": "sha256:runtime",
        }
        report_raw = _make_report_dict(nav_series=[1.0, 1.01, 1.02])
        report_raw["resume_provenance"] = resume_provenance

        orig_dir = tmp_path / "artifacts" / "run-original"
        orig_dir.mkdir(parents=True)
        (orig_dir / "manifest.json").write_bytes(
            orjson.dumps(_make_manifest_raw(run_id="run-original")),
        )
        (orig_dir / "backtest_report.json").write_bytes(orjson.dumps(report_raw))

        replay_dir = tmp_path / "artifacts" / "run-replay"
        replay_manifest_raw = _make_manifest_raw(
            run_id="run-replay",
            config_hash="hash-abc",
        )

        orig_record = MagicMock()
        orig_record.run_id = "run-original"
        orig_record.artifact_type = ArtifactKind.BACKTEST_REPORT
        orig_record.file_path = str(orig_dir)
        replay_record = MagicMock()
        replay_record.run_id = "run-replay"
        replay_record.artifact_type = ArtifactKind.BACKTEST_REPORT
        replay_record.file_path = str(replay_dir)
        mock_artifact_service = MagicMock()

        mock_facade = MagicMock()
        replay_report = _make_backtest_report(
            run_id="run-replay",
            nav_series=(
                ("2026-01-01", 1.0),
                ("2026-01-02", 1.01),
                ("2026-01-03", 1.02),
            ),
        )
        _configure_replay_execution(
            artifact_service=mock_artifact_service,
            facade=mock_facade,
            original_record=orig_record,
            replay_record=replay_record,
            replay_dir=replay_dir,
            replay_manifest_raw=replay_manifest_raw,
            replay_report=replay_report,
        )

        process = ReplayProcess(
            strategy_facade=mock_facade,
            artifact_service=mock_artifact_service,
        )

        process.replay("run-original")

        payload = orjson.loads((replay_dir / "replay_proof.json").read_bytes())
        assert payload["original_resume_provenance"] == resume_provenance

        proof_record = mock_artifact_service.save_artifact.call_args.args[0]
        assert proof_record.metadata["original_resume_from_run_id"] == "run-root"
        assert (
            proof_record.metadata["original_resume_checkpoint_trade_date"]
            == "2026-01-31"
        )
        assert (
            proof_record.metadata["original_resume_account_state_hash"]
            == "sha256:account"
        )

    def test_replay_restored_run_preserves_checkpoint_config_state(
        self,
        tmp_path: Path,
    ) -> None:
        """重放 restored run 时，应从原始 run config 带回 checkpoint 状态证据."""
        from ditto_application.processes.execution.replay_process import ReplayProcess

        orig_dir = tmp_path / "artifacts" / "run-restored"
        orig_dir.mkdir(parents=True)
        (orig_dir / "manifest.json").write_bytes(
            orjson.dumps(_make_manifest_raw(run_id="run-restored")),
        )
        report_raw = _make_report_dict(
            # Restored audit history expands report.period before the child's
            # actual execution boundary; replay must use the persisted config.
            period_start="2026-01-01",
            period_end="2026-03-31",
            initial_cash=1_011_111.0,
            nav_series=[1.0, 1.01, 1.02],
        )
        (orig_dir / "backtest_report.json").write_bytes(orjson.dumps(report_raw))

        replay_dir = tmp_path / "artifacts" / "run-replay"
        replay_manifest_raw = _make_manifest_raw(
            run_id="run-replay",
            config_hash="hash-abc",
        )

        orig_record = MagicMock()
        orig_record.run_id = "run-restored"
        orig_record.artifact_type = ArtifactKind.BACKTEST_REPORT
        orig_record.file_path = str(orig_dir)
        replay_record = MagicMock()
        replay_record.run_id = "run-replay"
        replay_record.artifact_type = ArtifactKind.BACKTEST_REPORT
        replay_record.file_path = str(replay_dir)
        mock_artifact_service = MagicMock()

        run_config = {
            "start_date": "2026-02-02",
            "end_date": "2026-03-31",
            "initial_cash": 1_000_000.0,
            "random_seed": 8675309,
            "execution_delay": 1,
            "knowledge_lag_days": 3,
            "resume_from_run_id": "run-root",
            "resume_checkpoint_trade_date": "2026-01-31",
            "resume_checkpoint_completed_days": 21,
            "resume_checkpoint_total_days": 60,
            "resume_checkpoint_nav": 1_020_000.0,
            "resume_checkpoint_order_count": 4,
            "resume_checkpoint_fill_count": 3,
            "resume_account_state_json": '{"cash_available":900000.0}',
            "resume_account_state_hash": "sha256:account",
            "resume_settlement_state_json": '{"frozen_quantities":[]}',
            "resume_settlement_state_hash": "sha256:settlement",
            "resume_runtime_state_json": '{"pending_orders":[],"delayed_signals":[]}',
            "resume_runtime_state_hash": "sha256:runtime",
            "allow_experimental_data": True,
        }
        mock_run_model = MagicMock()
        mock_run_model.get_run.return_value = StrategyRunRecord(
            run_id="run-restored",
            strategy_id="strat-1",
            status="completed",
            config_json=orjson.dumps(run_config).decode("utf-8"),
        )

        mock_facade = MagicMock()
        replay_report = _make_backtest_report(
            run_id="run-replay",
            nav_series=(
                ("2026-02-02", 1.0),
                ("2026-02-03", 1.01),
                ("2026-02-04", 1.02),
            ),
        )
        _configure_replay_execution(
            artifact_service=mock_artifact_service,
            facade=mock_facade,
            original_record=orig_record,
            replay_record=replay_record,
            replay_dir=replay_dir,
            replay_manifest_raw=replay_manifest_raw,
            replay_report=replay_report,
        )

        process = ReplayProcess(
            strategy_facade=mock_facade,
            artifact_service=mock_artifact_service,
            run_model=mock_run_model,
        )

        process.replay("run-restored")

        config = mock_facade.run_backtest_from_catalog.call_args.kwargs["config"]
        assert config.parent_run_id == "run-restored"
        assert config.start_date == "2026-02-02"
        assert config.end_date == "2026-03-31"
        assert config.initial_cash == pytest.approx(1_000_000.0)
        assert config.random_seed == 8675309
        assert config.execution_delay == 1
        assert config.knowledge_lag_days == 3
        assert config.resume_from_run_id == "run-root"
        assert config.resume_checkpoint_trade_date == "2026-01-31"
        assert config.resume_checkpoint_completed_days == 21
        assert config.resume_checkpoint_total_days == 60
        assert config.resume_checkpoint_nav == pytest.approx(1_020_000.0)
        assert config.resume_checkpoint_order_count == 4
        assert config.resume_checkpoint_fill_count == 3
        assert config.resume_account_state_json == '{"cash_available":900000.0}'
        assert config.resume_account_state_hash == "sha256:account"
        assert config.resume_settlement_state_json == '{"frozen_quantities":[]}'
        assert config.resume_settlement_state_hash == "sha256:settlement"
        assert (
            config.resume_runtime_state_json
            == '{"pending_orders":[],"delayed_signals":[]}'
        )
        assert config.resume_runtime_state_hash == "sha256:runtime"
        options = mock_facade.run_backtest_from_catalog.call_args.kwargs["options"]
        assert options.allow_experimental_data is True

    def test_replay_proof_uses_persisted_fill_log_state(
        self,
        tmp_path: Path,
    ) -> None:
        """存在 fill_log artifact 时，replay proof 应比较 fill 序列证据."""
        from ditto_application.processes.execution.replay_process import ReplayProcess

        fill = _make_fill()

        orig_dir = tmp_path / "artifacts" / "run-original"
        orig_dir.mkdir(parents=True)
        (orig_dir / "manifest.json").write_bytes(
            orjson.dumps(_make_manifest_raw(run_id="run-original")),
        )
        (orig_dir / "backtest_report.json").write_bytes(
            orjson.dumps(_make_report_dict(nav_series=[1.0, 1.01, 1.02])),
        )
        _write_fill_log(orig_dir / "fill_log.parquet", (fill,))

        replay_dir = tmp_path / "artifacts" / "run-replay"
        replay_manifest_raw = _make_manifest_raw(
            run_id="run-replay",
            config_hash="hash-abc",
        )

        orig_record = MagicMock()
        orig_record.run_id = "run-original"
        orig_record.artifact_type = ArtifactKind.BACKTEST_REPORT
        orig_record.file_path = str(orig_dir)
        replay_record = MagicMock()
        replay_record.run_id = "run-replay"
        replay_record.artifact_type = ArtifactKind.BACKTEST_REPORT
        replay_record.file_path = str(replay_dir)
        mock_artifact_service = MagicMock()

        mock_facade = MagicMock()
        replay_report = _make_backtest_report(
            run_id="run-replay",
            nav_series=(
                ("2026-01-01", 1.0),
                ("2026-01-02", 1.01),
                ("2026-01-03", 1.02),
            ),
            fill_log=(fill,),
        )
        _configure_replay_execution(
            artifact_service=mock_artifact_service,
            facade=mock_facade,
            original_record=orig_record,
            replay_record=replay_record,
            replay_dir=replay_dir,
            replay_manifest_raw=replay_manifest_raw,
            replay_report=replay_report,
        )

        process = ReplayProcess(
            strategy_facade=mock_facade,
            artifact_service=mock_artifact_service,
        )

        result = process.replay("run-original")

        assert result.validation.fill_match is True
        assert result.validation.fill_comparison is not None
        assert result.validation.fill_comparison.point_count == 1
        assert result.validation.is_reproducible is True

        payload = orjson.loads((replay_dir / "replay_proof.json").read_bytes())
        assert payload["fill_match"] is True
        assert payload["fill_comparison"]["identical"] is True
        assert payload["fill_comparison"]["point_count"] == 1

        proof_record = mock_artifact_service.save_artifact.call_args.args[0]
        assert proof_record.metadata["fill_match"] is True

    def test_replay_proof_uses_persisted_final_account_state(
        self,
        tmp_path: Path,
    ) -> None:
        """backtest_report 中的最终账户状态应作为 replay proof 证据源."""
        from ditto_application.processes.execution.replay_process import ReplayProcess

        account_view = _make_account_view()
        report_raw = _make_report_dict(nav_series=[1.0, 1.01, 1.02])
        report_raw["final_account_state"] = (
            BacktestAccountStateSnapshot.from_account_view(account_view).to_payload()
        )

        orig_dir = tmp_path / "artifacts" / "run-original"
        orig_dir.mkdir(parents=True)
        (orig_dir / "manifest.json").write_bytes(
            orjson.dumps(_make_manifest_raw(run_id="run-original")),
        )
        (orig_dir / "backtest_report.json").write_bytes(orjson.dumps(report_raw))

        replay_dir = tmp_path / "artifacts" / "run-replay"
        replay_manifest_raw = _make_manifest_raw(
            run_id="run-replay",
            config_hash="hash-abc",
        )

        orig_record = MagicMock()
        orig_record.run_id = "run-original"
        orig_record.artifact_type = ArtifactKind.BACKTEST_REPORT
        orig_record.file_path = str(orig_dir)
        replay_record = MagicMock()
        replay_record.run_id = "run-replay"
        replay_record.artifact_type = ArtifactKind.BACKTEST_REPORT
        replay_record.file_path = str(replay_dir)
        mock_artifact_service = MagicMock()

        mock_facade = MagicMock()
        replay_report = _make_backtest_report(
            run_id="run-replay",
            nav_series=(
                ("2026-01-01", 1.0),
                ("2026-01-02", 1.01),
                ("2026-01-03", 1.02),
            ),
            final_account_state=account_view,
        )
        _configure_replay_execution(
            artifact_service=mock_artifact_service,
            facade=mock_facade,
            original_record=orig_record,
            replay_record=replay_record,
            replay_dir=replay_dir,
            replay_manifest_raw=replay_manifest_raw,
            replay_report=replay_report,
        )

        process = ReplayProcess(
            strategy_facade=mock_facade,
            artifact_service=mock_artifact_service,
        )

        result = process.replay("run-original")

        assert result.validation.account_state_match is True
        assert result.validation.account_state_comparison is not None
        assert result.validation.account_state_comparison.identical is True
        assert result.validation.is_reproducible is True

        payload = orjson.loads((replay_dir / "replay_proof.json").read_bytes())
        assert payload["account_state_match"] is True
        assert payload["account_state_comparison"]["identical"] is True
        assert payload["account_state_comparison"]["nav_diff"] == 0.0

        proof_record = mock_artifact_service.save_artifact.call_args.args[0]
        assert proof_record.metadata["account_state_match"] is True

    def test_replay_non_numeric_version(self, tmp_path: Path) -> None:
        """strategy_version 非数字时 version 传 None."""
        from ditto_application.processes.execution.replay_process import ReplayProcess

        orig_dir = tmp_path / "artifacts" / "run-original"
        orig_dir.mkdir(parents=True)
        manifest_raw = _make_manifest_raw(strategy_version="v3-beta")
        report_raw = _make_report_dict()
        (orig_dir / "manifest.json").write_bytes(orjson.dumps(manifest_raw))
        (orig_dir / "backtest_report.json").write_bytes(orjson.dumps(report_raw))

        replay_dir = tmp_path / "artifacts" / "run-replay"
        replay_manifest_raw = _make_manifest_raw(run_id="run-replay")

        mock_artifact_service = MagicMock()
        orig_record = MagicMock()
        orig_record.run_id = "run-original"
        orig_record.artifact_type = ArtifactKind.BACKTEST_REPORT
        orig_record.file_path = str(orig_dir)
        replay_record = MagicMock()
        replay_record.run_id = "run-replay"
        replay_record.artifact_type = ArtifactKind.BACKTEST_REPORT
        replay_record.file_path = str(replay_dir)

        replay_report = _make_backtest_report(run_id="run-replay")
        mock_facade = MagicMock()
        _configure_replay_execution(
            artifact_service=mock_artifact_service,
            facade=mock_facade,
            original_record=orig_record,
            replay_record=replay_record,
            replay_dir=replay_dir,
            replay_manifest_raw=replay_manifest_raw,
            replay_report=replay_report,
        )

        process = ReplayProcess(
            strategy_facade=mock_facade,
            artifact_service=mock_artifact_service,
        )

        process.replay("run-original")

        call_kwargs = mock_facade.run_backtest_from_catalog.call_args
        version = call_kwargs.kwargs.get("version") or call_kwargs[1].get("version")
        assert version is None


# ---------------------------------------------------------------------------
# replay() 错误场景
# ---------------------------------------------------------------------------


class TestReplayErrors:
    """ReplayProcess.replay — 错误场景."""

    def test_replay_artifact_not_found(self) -> None:
        """原始运行的 artifact 不存在时抛出 FileNotFoundError."""
        from ditto_application.processes.execution.replay_process import ReplayProcess

        mock_artifact_service = MagicMock()
        mock_artifact_service.list_artifacts.return_value = []

        process = ReplayProcess(
            strategy_facade=MagicMock(),
            artifact_service=mock_artifact_service,
        )

        with pytest.raises(FileNotFoundError, match="Artifact directory not found"):
            process.replay("run-nonexistent")

    def test_replay_rejects_generated_original_run_id_before_facade_execution(
        self,
        tmp_path: Path,
    ) -> None:
        """A generated collision must fail before any execution can overwrite data."""
        from ditto_application.processes.execution.replay_process import ReplayProcess

        artifact_dir = tmp_path / "artifacts" / "run-original"
        artifact_dir.mkdir(parents=True)
        (artifact_dir / "manifest.json").write_bytes(
            orjson.dumps(_make_manifest_raw(run_id="run-original")),
        )
        (artifact_dir / "backtest_report.json").write_bytes(
            orjson.dumps(_make_report_dict(nav_series=[1.0, 1.01])),
        )
        proof_path = artifact_dir / "replay_proof.json"
        original_proof = b'{"owner":"original"}'
        proof_path.write_bytes(original_proof)

        original_record = MagicMock()
        original_record.run_id = "run-original"
        original_record.artifact_type = ArtifactKind.BACKTEST_REPORT
        original_record.file_path = str(artifact_dir)
        artifact_service = MagicMock()
        artifact_service.list_artifacts.return_value = [original_record]
        facade = MagicMock()
        process = ReplayProcess(facade, artifact_service)

        with (
            patch(
                "ditto_application.processes.execution.replay_process.resolve_run_id",
                return_value="run-original",
            ),
            patch(
                "ditto_application.processes.execution.replay_process.atomic_bytes_write"
            ) as atomic_write,
            pytest.raises(AppProcessError) as exc_info,
        ):
            process.replay("run-original")

        assert exc_info.value.details["reason"] == "replay_run_id_collision"
        facade.run_backtest_from_catalog.assert_not_called()
        atomic_write.assert_not_called()
        artifact_service.save_artifact.assert_not_called()
        assert proof_path.read_bytes() == original_proof

    def test_replay_rejects_facade_run_id_that_differs_from_requested_id(
        self,
        tmp_path: Path,
    ) -> None:
        """Facade output identity must match the collision-safe requested identity."""
        from ditto_application.processes.execution.replay_process import ReplayProcess

        artifact_dir = tmp_path / "artifacts" / "run-original"
        artifact_dir.mkdir(parents=True)
        (artifact_dir / "manifest.json").write_bytes(
            orjson.dumps(_make_manifest_raw(run_id="run-original")),
        )
        (artifact_dir / "backtest_report.json").write_bytes(
            orjson.dumps(_make_report_dict(nav_series=[1.0, 1.01])),
        )
        proof_path = artifact_dir / "replay_proof.json"
        original_proof = b'{"owner":"original"}'
        proof_path.write_bytes(original_proof)

        original_record = MagicMock()
        original_record.run_id = "run-original"
        original_record.artifact_type = ArtifactKind.BACKTEST_REPORT
        original_record.file_path = str(artifact_dir)
        artifact_service = MagicMock()
        artifact_service.list_artifacts.return_value = [original_record]
        facade = MagicMock()
        facade.run_backtest_from_catalog.return_value = _make_backtest_report(
            run_id="run-unrequested",
            nav_series=(("2026-01-01", 1.0), ("2026-01-02", 1.01)),
        )
        process = ReplayProcess(facade, artifact_service)

        with (
            patch(
                "ditto_application.processes.execution.replay_process.atomic_bytes_write"
            ) as atomic_write,
            pytest.raises(AppProcessError) as exc_info,
        ):
            process.replay("run-original")

        assert exc_info.value.details["reason"] == "replay_run_id_mismatch"
        assert exc_info.value.details["requested_run_id"] == "run-replay"
        assert exc_info.value.details["actual_run_id"] == "run-unrequested"
        requested_config = facade.run_backtest_from_catalog.call_args.kwargs["config"]
        assert requested_config.run_id == "run-replay"
        atomic_write.assert_not_called()
        artifact_service.save_artifact.assert_not_called()
        assert proof_path.read_bytes() == original_proof

    def test_replay_rejects_original_artifact_dir_without_writing_proof(
        self,
        tmp_path: Path,
    ) -> None:
        """An indexed path alias must fail before the facade can mutate originals."""
        from ditto_application.processes.execution.replay_process import ReplayProcess

        artifact_dir = tmp_path / "artifacts" / "run-original"
        artifact_dir.mkdir(parents=True)
        (artifact_dir / "manifest.json").write_bytes(
            orjson.dumps(_make_manifest_raw(run_id="run-original")),
        )
        (artifact_dir / "backtest_report.json").write_bytes(
            orjson.dumps(_make_report_dict(nav_series=[1.0, 1.01])),
        )
        proof_path = artifact_dir / "replay_proof.json"
        original_proof = b'{"owner":"original"}'
        proof_path.write_bytes(original_proof)
        (artifact_dir / "fill_log.parquet").write_bytes(b"original-fill-log")
        original_files = {
            path.relative_to(artifact_dir): path.read_bytes()
            for path in artifact_dir.rglob("*")
            if path.is_file()
        }

        original_record = MagicMock()
        original_record.run_id = "run-original"
        original_record.artifact_type = ArtifactKind.BACKTEST_REPORT
        original_record.file_path = str(artifact_dir)
        replay_record = MagicMock()
        replay_record.run_id = "run-replay"
        replay_record.artifact_type = ArtifactKind.BACKTEST_REPORT
        replay_record.file_path = str(artifact_dir)
        artifact_service = MagicMock()
        artifact_service.list_artifacts.return_value = [
            replay_record,
            original_record,
        ]
        facade = MagicMock()

        def _mutate_original_if_called(**_kwargs: object) -> BacktestReport:
            for path in artifact_dir.rglob("*"):
                if path.is_file():
                    path.write_bytes(b"overwritten")
            return _make_backtest_report(
                run_id="run-replay",
                nav_series=(("2026-01-01", 1.0), ("2026-01-02", 1.01)),
            )

        facade.run_backtest_from_catalog.side_effect = _mutate_original_if_called
        process = ReplayProcess(facade, artifact_service)

        with (
            patch(
                "ditto_application.processes.execution.replay_process.atomic_bytes_write"
            ) as atomic_write,
            pytest.raises(AppProcessError) as exc_info,
        ):
            process.replay("run-original")

        assert exc_info.value.details["reason"] == "replay_artifact_directory_collision"
        facade.run_backtest_from_catalog.assert_not_called()
        atomic_write.assert_not_called()
        artifact_service.save_artifact.assert_not_called()
        assert {
            path.relative_to(artifact_dir): path.read_bytes()
            for path in artifact_dir.rglob("*")
            if path.is_file()
        } == original_files

    def test_replay_rejects_existing_indexed_target_before_facade(
        self,
        tmp_path: Path,
    ) -> None:
        """A generated ID cannot reuse another run's indexed artifact target."""
        from ditto_application.processes.execution.replay_process import ReplayProcess

        root = tmp_path / "artifacts"
        original_dir = root / "run-original"
        target_dir = root / "run-replay"
        original_dir.mkdir(parents=True)
        target_dir.mkdir()
        (original_dir / "manifest.json").write_bytes(
            orjson.dumps(_make_manifest_raw(run_id="run-original")),
        )
        (original_dir / "backtest_report.json").write_bytes(
            orjson.dumps(_make_report_dict(nav_series=[1.0, 1.01])),
        )
        (original_dir / "immutable.bin").write_bytes(b"original")
        (target_dir / "manifest.json").write_bytes(
            orjson.dumps(_make_manifest_raw(run_id="run-replay")),
        )
        (target_dir / "immutable.bin").write_bytes(b"existing-target")
        before = {
            path.relative_to(root): path.read_bytes()
            for path in root.rglob("*")
            if path.is_file()
        }

        original_record = MagicMock(
            run_id="run-original",
            artifact_type=ArtifactKind.BACKTEST_REPORT,
            file_path=str(original_dir),
        )
        target_record = MagicMock(
            run_id="run-replay",
            artifact_type=ArtifactKind.BACKTEST_REPORT,
            file_path=str(target_dir),
        )
        artifact_service = MagicMock()
        artifact_service.list_artifacts.return_value = [target_record, original_record]
        facade = MagicMock()

        def _mutate_target_if_called(**_kwargs: object) -> BacktestReport:
            (target_dir / "immutable.bin").write_bytes(b"overwritten")
            return _make_backtest_report(
                run_id="run-replay",
                nav_series=(("2026-01-01", 1.0), ("2026-01-02", 1.01)),
            )

        facade.run_backtest_from_catalog.side_effect = _mutate_target_if_called
        process = ReplayProcess(facade, artifact_service)

        with pytest.raises(AppProcessError) as exc_info:
            process.replay("run-original")

        assert exc_info.value.details["reason"] == "replay_artifact_target_exists"
        facade.run_backtest_from_catalog.assert_not_called()
        artifact_service.save_artifact.assert_not_called()
        assert {
            path.relative_to(root): path.read_bytes()
            for path in root.rglob("*")
            if path.is_file()
        } == before

    def test_replay_rejects_existing_unindexed_target_before_facade(
        self,
        tmp_path: Path,
    ) -> None:
        """An orphan target directory is never treated as safe replay storage."""
        from ditto_application.processes.execution.replay_process import ReplayProcess

        root = tmp_path / "artifacts"
        original_dir = root / "run-original"
        target_dir = root / "run-replay"
        original_dir.mkdir(parents=True)
        target_dir.mkdir()
        (original_dir / "manifest.json").write_bytes(
            orjson.dumps(_make_manifest_raw(run_id="run-original")),
        )
        (original_dir / "backtest_report.json").write_bytes(
            orjson.dumps(_make_report_dict(nav_series=[1.0, 1.01])),
        )
        (original_dir / "immutable.bin").write_bytes(b"original")
        (target_dir / "orphan.bin").write_bytes(b"existing-target")
        before = {
            path.relative_to(root): path.read_bytes()
            for path in root.rglob("*")
            if path.is_file()
        }
        original_record = MagicMock(
            run_id="run-original",
            artifact_type=ArtifactKind.BACKTEST_REPORT,
            file_path=str(original_dir),
        )
        artifact_service = MagicMock()
        artifact_service.list_artifacts.return_value = [original_record]
        facade = MagicMock()

        def _mutate_if_called(**_kwargs: object) -> BacktestReport:
            (original_dir / "immutable.bin").write_bytes(b"overwritten")
            (target_dir / "orphan.bin").write_bytes(b"overwritten")
            return _make_backtest_report(run_id="run-replay")

        facade.run_backtest_from_catalog.side_effect = _mutate_if_called
        process = ReplayProcess(facade, artifact_service)

        with pytest.raises(AppProcessError) as exc_info:
            process.replay("run-original")

        assert exc_info.value.details["reason"] == "replay_artifact_target_exists"
        facade.run_backtest_from_catalog.assert_not_called()
        artifact_service.save_artifact.assert_not_called()
        assert {
            path.relative_to(root): path.read_bytes()
            for path in root.rglob("*")
            if path.is_file()
        } == before

    def test_replay_reservation_race_fails_before_facade(
        self,
        tmp_path: Path,
    ) -> None:
        """Losing exclusive target reservation cannot fall through to execution."""
        from ditto_application.processes.execution.replay_process import ReplayProcess

        original_dir = tmp_path / "artifacts" / "run-original"
        original_dir.mkdir(parents=True)
        (original_dir / "manifest.json").write_bytes(
            orjson.dumps(_make_manifest_raw(run_id="run-original")),
        )
        (original_dir / "backtest_report.json").write_bytes(
            orjson.dumps(_make_report_dict(nav_series=[1.0, 1.01])),
        )
        before = {
            path.relative_to(original_dir): path.read_bytes()
            for path in original_dir.rglob("*")
            if path.is_file()
        }
        original_record = MagicMock(
            run_id="run-original",
            artifact_type=ArtifactKind.BACKTEST_REPORT,
            file_path=str(original_dir),
        )
        artifact_service = MagicMock()
        artifact_service.list_artifacts.return_value = [original_record]
        facade = MagicMock()
        process = ReplayProcess(facade, artifact_service)

        with (
            patch.object(Path, "mkdir", side_effect=FileExistsError),
            pytest.raises(AppProcessError) as exc_info,
        ):
            process.replay("run-original")

        assert exc_info.value.details["reason"] == "replay_artifact_target_exists"
        facade.run_backtest_from_catalog.assert_not_called()
        assert {
            path.relative_to(original_dir): path.read_bytes()
            for path in original_dir.rglob("*")
            if path.is_file()
        } == before

    def test_replay_cleans_empty_reservation_when_facade_fails(
        self,
        tmp_path: Path,
    ) -> None:
        """A failed facade call must not strand its exclusively-created placeholder."""
        original_dir = tmp_path / "artifacts" / "run-original"
        original_dir.mkdir(parents=True)
        (original_dir / "manifest.json").write_bytes(
            orjson.dumps(_make_manifest_raw(run_id="run-original"))
        )
        (original_dir / "backtest_report.json").write_bytes(
            orjson.dumps(_make_report_dict(nav_series=[1.0]))
        )
        original_record = MagicMock(
            run_id="run-original",
            artifact_type=ArtifactKind.BACKTEST_REPORT,
            file_path=str(original_dir),
        )
        artifact_service = MagicMock()
        artifact_service.list_artifacts.return_value = [original_record]
        facade = MagicMock()
        facade.run_backtest_from_catalog.side_effect = RuntimeError("facade failed")

        with pytest.raises(RuntimeError, match="facade failed"):
            ReplayProcess(facade, artifact_service).replay("run-original")

        assert not (original_dir.parent / "run-replay").exists()

    def test_replay_requires_indexed_dir_to_equal_exclusive_reservation(
        self,
        tmp_path: Path,
    ) -> None:
        """A successful facade cannot redirect validation/proof to another directory."""
        root = tmp_path / "artifacts"
        original_dir = root / "run-original"
        other_dir = root / "other-existing-run"
        original_dir.mkdir(parents=True)
        other_dir.mkdir()
        (original_dir / "manifest.json").write_bytes(
            orjson.dumps(_make_manifest_raw(run_id="run-original"))
        )
        (original_dir / "backtest_report.json").write_bytes(
            orjson.dumps(_make_report_dict(nav_series=[1.0]))
        )
        (other_dir / "manifest.json").write_bytes(
            orjson.dumps(_make_manifest_raw(run_id="run-replay"))
        )
        existing_bytes = b"must-survive"
        (other_dir / "existing.bin").write_bytes(existing_bytes)
        original_record = MagicMock(
            run_id="run-original",
            artifact_type=ArtifactKind.BACKTEST_REPORT,
            file_path=str(original_dir),
        )
        redirected_record = MagicMock(
            run_id="run-replay",
            artifact_type=ArtifactKind.BACKTEST_REPORT,
            file_path=str(other_dir),
        )
        artifact_service = MagicMock()
        artifact_service.list_artifacts.return_value = [original_record]
        facade = MagicMock()

        def _execute(**kwargs: object) -> BacktestReport:
            options = kwargs["options"]
            config = kwargs["config"]
            assert isinstance(options, BacktestServiceOptions)
            assert isinstance(config, BacktestServiceConfig)
            reserved = Path(str(options.artifact_dir)) / config.run_id
            (reserved / "successful.bin").write_bytes(b"successful-artifact")
            artifact_service.list_artifacts.return_value = [
                redirected_record,
                original_record,
            ]
            return _make_backtest_report(run_id="run-replay", nav_series=(("d", 1.0),))

        facade.run_backtest_from_catalog.side_effect = _execute

        with pytest.raises(AppProcessError) as exc_info:
            ReplayProcess(facade, artifact_service).replay("run-original")

        assert exc_info.value.details["reason"] == "replay_artifact_target_mismatch"
        assert (root / "run-replay" / "successful.bin").read_bytes() == (
            b"successful-artifact"
        )
        assert (other_dir / "existing.bin").read_bytes() == existing_bytes
        artifact_service.save_artifact.assert_not_called()

    def test_replay_cleans_empty_reservation_on_run_id_mismatch(
        self,
        tmp_path: Path,
    ) -> None:
        """A rejected facade identity leaves no empty directory owned by replay."""
        original_dir = tmp_path / "artifacts" / "run-original"
        original_dir.mkdir(parents=True)
        (original_dir / "manifest.json").write_bytes(
            orjson.dumps(_make_manifest_raw(run_id="run-original"))
        )
        (original_dir / "backtest_report.json").write_bytes(
            orjson.dumps(_make_report_dict(nav_series=[1.0]))
        )
        original_record = MagicMock(
            run_id="run-original",
            artifact_type=ArtifactKind.BACKTEST_REPORT,
            file_path=str(original_dir),
        )
        artifact_service = MagicMock()
        artifact_service.list_artifacts.return_value = [original_record]
        facade = MagicMock()
        facade.run_backtest_from_catalog.return_value = _make_backtest_report(
            run_id="wrong-run"
        )

        with pytest.raises(AppProcessError, match="differs from the request"):
            ReplayProcess(facade, artifact_service).replay("run-original")

        assert not (original_dir.parent / "run-replay").exists()


# ---------------------------------------------------------------------------
# _extract_rebalance_freq 测试
# ---------------------------------------------------------------------------


class TestExtractRebalanceFreq:
    """_extract_rebalance_freq — 从 report 提取调仓频率."""

    def test_valid_string(self) -> None:
        from ditto_application.processes.execution.replay_process import (
            _extract_rebalance_freq,
        )

        assert _extract_rebalance_freq({"rebalance_freq": "weekly"}) == "weekly"

    def test_empty_string_defaults(self) -> None:
        from ditto_application.processes.execution.replay_process import (
            _extract_rebalance_freq,
        )

        assert _extract_rebalance_freq({"rebalance_freq": ""}) == "daily"

    def test_missing_key_defaults(self) -> None:
        from ditto_application.processes.execution.replay_process import (
            _extract_rebalance_freq,
        )

        assert _extract_rebalance_freq({}) == "daily"

    def test_non_string_type_defaults(self) -> None:
        from ditto_application.processes.execution.replay_process import (
            _extract_rebalance_freq,
        )

        assert _extract_rebalance_freq({"rebalance_freq": 42}) == "daily"
