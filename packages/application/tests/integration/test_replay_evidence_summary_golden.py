"""Synthetic restored-run replay evidence golden test.

This test uses real JSON artifact files with lightweight in-memory read models.
It proves the backend query surface can compose restored-run report provenance
with replay proof evidence without external market data, broker adapters or UI.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import orjson
from ditto_application.queries.backtest import BacktestQueryFacade
from ditto_strategy.models import ArtifactKind, StrategyArtifactRecord
from ditto_strategy.runs.models import StrategyRunRecord
from ditto_strategy.storage.sqlite.services.backtest_artifact_reader import (
    BacktestArtifactReader,
)


class _RunModel:
    """Minimal run read model for synthetic artifact composition."""

    def __init__(self, runs: dict[str, StrategyRunRecord]) -> None:
        self._runs = runs

    def get_run(self, run_id: str) -> StrategyRunRecord | None:
        return self._runs.get(run_id)

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
        _ = (strategy_id, status, start_date, end_date, limit, offset)
        return list(self._runs.values())


class _ArtifactService:
    """Minimal artifact service exposing the query-side list contract."""

    def __init__(self, artifacts: list[StrategyArtifactRecord]) -> None:
        self._artifacts = artifacts

    def list_artifacts(self) -> list[StrategyArtifactRecord]:
        return self._artifacts


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(orjson.dumps(payload, option=orjson.OPT_INDENT_2))


def test_restored_run_replay_evidence_summary_reads_real_artifacts(
    tmp_path: Path,
) -> None:
    """Synthetic golden: report provenance and proof provenance stay aligned."""
    restored_dir = tmp_path / "run-restored"
    replay_dir = tmp_path / "run-replay"
    resume_provenance: dict[str, object] = {
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

    _write_json(
        restored_dir / "backtest_report.json",
        {
            "run_id": "run-restored",
            "period": {"start": "2026-02-02", "end": "2026-03-31"},
            "initial_cash": 1_000_000.0,
            "final_nav": 1_080_000.0,
            "resume_provenance": resume_provenance,
        },
    )
    _write_json(
        replay_dir / "replay_proof.json",
        {
            "proof_version": 1,
            "original_run_id": "run-restored",
            "replay_run_id": "run-replay",
            "is_reproducible": True,
            "nav_correlation": 1.0,
            "max_nav_diff_bps": 0.0,
            "input_data_match": True,
            "manifest_diff": {"has_diff": False},
            "fill_match": True,
            "account_state_match": True,
            "original_resume_provenance": resume_provenance,
        },
    )

    runs = {
        run_id: StrategyRunRecord(
            run_id=run_id,
            strategy_id="momentum-etf",
            status="completed",
        )
        for run_id in ("run-restored", "run-replay")
    }
    artifact_service = _ArtifactService(
        [
            StrategyArtifactRecord(
                artifact_id="artifact-run-restored",
                strategy_id="momentum-etf",
                run_id="run-restored",
                artifact_type=ArtifactKind.BACKTEST_REPORT,
                file_path=str(restored_dir),
            ),
            StrategyArtifactRecord(
                artifact_id="replay-proof-run-replay",
                strategy_id="momentum-etf",
                run_id="run-replay",
                artifact_type=ArtifactKind.REPLAY_PROOF,
                file_path=str(replay_dir),
            ),
        ]
    )
    facade = BacktestQueryFacade(
        trade_facade=MagicMock(),
        run_model=_RunModel(runs),
        audit_service=MagicMock(),
        artifact_service=artifact_service,
        artifact_reader=BacktestArtifactReader(),
    )

    summary = facade.get_replay_evidence_summary("run-replay")

    assert summary is not None
    assert summary.original_run_id == "run-restored"
    assert summary.replay_run_id == "run-replay"
    assert summary.is_reproducible is True
    assert summary.input_data_match is True
    assert summary.fill_match is True
    assert summary.account_state_match is True
    assert summary.report_resume_provenance == resume_provenance
    assert summary.proof_resume_provenance == resume_provenance
    assert summary.resume_provenance_match is True
    assert summary.missing_sections == ()
