"""Replay proof payload and persisted state evidence helpers."""

from __future__ import annotations

from pathlib import Path
from types import MappingProxyType
from typing import Any, cast

import polars as pl
from ditto_backtest.manifest_types import ReplayArtifactRef, ResearchReplayEvidence
from ditto_backtest.replay import (
    AccountStateComparison,
    FillComparison,
    ManifestDiff,
    ReplayStateProof,
    ReplayValidationResult,
)
from ditto_backtest.result import BacktestAccountStateSnapshot
from ditto_portfolio.accounting import AccountView, CashBook, Position
from ditto_portfolio.accounting.fills import FillEvent

from ditto_application.exceptions import AppProcessError
from ditto_application.processes.execution._research_replay_artifacts import (
    fill_from_indexed_row,
)


def build_replay_proof_payload(
    *,
    original_run_id: str,
    replay_run_id: str,
    validation: ReplayValidationResult,
    original_replay_evidence: ResearchReplayEvidence | None = None,
    replay_replay_evidence: ResearchReplayEvidence | None = None,
    original_resume_provenance: dict[str, object] | None = None,
    created_at: str,
) -> dict[str, object]:
    """Build one stable, persistable replay proof payload."""
    payload: dict[str, object] = {
        "proof_version": 2 if original_replay_evidence is not None else 1,
        "created_at": created_at,
        "original_run_id": original_run_id,
        "replay_run_id": replay_run_id,
        "is_reproducible": validation.is_reproducible,
        "nav_correlation": validation.nav_correlation,
        "max_nav_diff_bps": validation.max_nav_diff_bps,
        "input_data_match": validation.input_data_match,
        "manifest_diff": _manifest_diff_to_payload(validation.manifest_diff),
        "fill_match": validation.fill_match,
        "account_state_match": validation.account_state_match,
        "fill_comparison": _fill_comparison_to_payload(validation.fill_comparison),
        "account_state_comparison": _account_comparison_to_payload(
            validation.account_state_comparison
        ),
    }
    if original_resume_provenance is not None:
        payload["original_resume_provenance"] = original_resume_provenance
    if original_replay_evidence is not None:
        payload.update(
            _strict_evidence_payload(
                original=original_replay_evidence,
                replay=replay_replay_evidence,
                validation=validation,
            )
        )
    return payload


def _strict_evidence_payload(
    *,
    original: ResearchReplayEvidence,
    replay: ResearchReplayEvidence | None,
    validation: ReplayValidationResult,
) -> dict[str, object]:
    if replay is None or any(
        value is None
        for value in (
            validation.reproduction_fingerprint_match,
            validation.key_result_summary_match,
            validation.required_artifact_hashes_match,
        )
    ):
        raise AppProcessError(
            "R3 replay proof is missing strict two-sided evidence",
            reason="incomplete_replay_evidence_proof",
        )
    return {
        "replay_evidence_schema_version": original.schema_version,
        "reproduction_fingerprint": original.reproduction_fingerprint,
        "key_result_summary_hash": original.key_result_summary.content_hash,
        "required_artifacts": [
            _replay_artifact_ref_payload(item) for item in original.required_artifacts
        ],
        "reproduction_fingerprint_match": validation.reproduction_fingerprint_match,
        "key_result_summary_match": validation.key_result_summary_match,
        "required_artifact_hashes_match": validation.required_artifact_hashes_match,
        "original_replay_evidence": _replay_evidence_payload(original),
        "replay_replay_evidence": _replay_evidence_payload(replay),
    }


def _replay_artifact_ref_payload(item: ReplayArtifactRef) -> dict[str, object]:
    return {
        "artifact_id": item.artifact_id,
        "artifact_kind": item.artifact_kind,
        "artifact_format": item.artifact_format,
        "content_hash": item.content_hash,
        "schema_hash": item.schema_hash,
        "row_count": item.row_count,
        "byte_size": item.byte_size,
    }


def _replay_evidence_payload(
    evidence: ResearchReplayEvidence,
) -> dict[str, object]:
    return {
        "schema_version": evidence.schema_version,
        "reproduction_fingerprint": evidence.reproduction_fingerprint,
        "key_result_summary_artifact_id": evidence.key_result_summary_artifact_id,
        "key_result_summary_hash": evidence.key_result_summary.content_hash,
        "required_artifacts": [
            _replay_artifact_ref_payload(item) for item in evidence.required_artifacts
        ],
    }


def load_resume_provenance(report: dict[str, Any]) -> dict[str, object] | None:
    """Load restored-run provenance from a verified report."""
    payload = report.get("resume_provenance")
    if payload is None:
        return None
    if not isinstance(payload, dict):
        raise AppProcessError(
            "Invalid resume_provenance payload in backtest_report.json"
        )
    raw = cast(dict[object, object], payload)
    return {str(key): value for key, value in raw.items()}


def resume_provenance_metadata(
    provenance: dict[str, object] | None,
) -> dict[str, object]:
    """Flatten original restored-run provenance into artifact metadata."""
    if provenance is None:
        return {}
    return {
        "original_resume_from_run_id": provenance.get("from_run_id", ""),
        "original_resume_checkpoint_trade_date": provenance.get(
            "checkpoint_trade_date", ""
        ),
        "original_resume_checkpoint_completed_days": provenance.get(
            "checkpoint_completed_days", 0
        ),
        "original_resume_checkpoint_total_days": provenance.get(
            "checkpoint_total_days", 0
        ),
        "original_resume_checkpoint_nav": provenance.get("checkpoint_nav", 0.0),
        "original_resume_checkpoint_order_count": provenance.get(
            "checkpoint_order_count", 0
        ),
        "original_resume_checkpoint_fill_count": provenance.get(
            "checkpoint_fill_count", 0
        ),
        "original_resume_account_state_hash": provenance.get("account_state_hash", ""),
        "original_resume_settlement_state_hash": provenance.get(
            "settlement_state_hash", ""
        ),
        "original_resume_runtime_state_hash": provenance.get("runtime_state_hash", ""),
    }


def build_state_proof(
    *,
    original_fills: tuple[FillEvent, ...] | None,
    original_account: AccountView | None,
    replay_fills: tuple[FillEvent, ...] | None,
    replay_account: AccountView | None,
) -> ReplayStateProof | None:
    """Build state proof only when the original persisted evidence exists."""
    if original_fills is None and original_account is None:
        return None
    return ReplayStateProof(
        original_fills=original_fills,
        replay_fills=replay_fills if original_fills is not None else None,
        original_account=original_account,
        replay_account=replay_account if original_account is not None else None,
    )


def load_final_account_state(report: dict[str, Any]) -> AccountView | None:
    """Load a persisted final account state from a verified report."""
    payload = report.get("final_account_state")
    if payload is None:
        return None
    try:
        snapshot = BacktestAccountStateSnapshot.from_payload(payload)
    except ValueError as exc:
        raise AppProcessError(
            "Invalid final_account_state payload in backtest_report.json"
        ) from exc
    positions = {
        position.instrument_id: Position(
            instrument_id=position.instrument_id,
            quantity=position.quantity,
            available_quantity=position.available_quantity,
            average_cost=position.average_cost,
            market_value=position.market_value,
            unrealized_pnl=position.unrealized_pnl,
            realized_pnl=position.realized_pnl,
            total_fees=position.total_fees,
        )
        for position in snapshot.positions
    }
    return AccountView(
        positions=MappingProxyType(positions),
        cash=CashBook(
            available=snapshot.cash_available,
            settled=snapshot.cash_settled,
            frozen=snapshot.cash_frozen,
        ),
        total_value=snapshot.total_value,
        nav=snapshot.nav,
        exposure=snapshot.exposure,
    )


def load_fill_log(artifact_dir: Path) -> tuple[FillEvent, ...] | None:
    """Load a legacy persisted fill log when one exists."""
    fill_log_path = artifact_dir / "fill_log.parquet"
    if not fill_log_path.exists():
        return None
    return tuple(
        fill_from_indexed_row(cast(dict[str, object], row))
        for row in pl.read_parquet(fill_log_path).to_dicts()
    )


def _manifest_diff_to_payload(diff: ManifestDiff) -> dict[str, object]:
    return {
        "config_diffs": list(diff.config_diffs),
        "data_diffs": list(diff.data_diffs),
        "version_diffs": list(diff.version_diffs),
        "seed_diffs": list(diff.seed_diffs),
        "evidence_diffs": list(diff.evidence_diffs),
        "has_diff": diff.has_diff,
    }


def _fill_comparison_to_payload(
    comparison: FillComparison | None,
) -> dict[str, object] | None:
    if comparison is None:
        return None
    return {
        "identical": comparison.identical,
        "mismatch_count": comparison.mismatch_count,
        "length_mismatch": comparison.length_mismatch,
        "point_count": comparison.point_count,
    }


def _account_comparison_to_payload(
    comparison: AccountStateComparison | None,
) -> dict[str, object] | None:
    if comparison is None:
        return None
    return {
        "identical": comparison.identical,
        "nav_diff": comparison.nav_diff,
        "available_cash_diff": comparison.available_cash_diff,
        "settled_cash_diff": comparison.settled_cash_diff,
        "frozen_cash_diff": comparison.frozen_cash_diff,
        "position_count_diff": comparison.position_count_diff,
    }
