"""Read-only OPS-10 release-candidate evidence aggregation."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import cast

import orjson

from ditto_apps.operations.evidence_manifest import (
    EvidenceManifestError,
    verify_gate_manifest,
)
from ditto_apps.operations.q4_live_account_acceptance import (
    canonical_hash,
    parse_timestamp,
    rfc3339,
)

__all__ = ["ReleaseCandidateArtifactPaths", "build_release_candidate_bundle"]

_ZERO_BROKER_SAFETY = {"broker_connections": 0, "real_orders": 0}
_ACCELERATED_DAY_COUNT = 20


@dataclass(frozen=True, slots=True)
class ReleaseCandidateArtifactPaths:
    """Exact evidence inputs required to close the OPS-10 launch bundle."""

    accelerated_proposal: Path
    accelerated_bootstrap: Path
    accelerated_progress: Path
    restore_evidence: Path
    q5_proposal: Path
    q5_acceptance: Path
    portfolio_diagnostic: Path
    ui08_final: Path
    backend_validation: Path
    frontend_validation: Path
    prerequisite_gates: tuple[Path, ...]


def _mapping(value: object, *, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(
        type(key) is str for key in cast("Mapping[object, object]", value)
    ):
        raise ValueError(f"{field} must be a string-keyed object")
    return cast("Mapping[str, object]", value)


def _sequence(value: object, *, field: str) -> tuple[object, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ValueError(f"{field} must be an array")
    return tuple(cast("Sequence[object]", value))


def _load(path: Path, *, field: str) -> dict[str, object]:
    resolved = path.expanduser().resolve(strict=True)
    value = orjson.loads(resolved.read_bytes())
    return dict(_mapping(value, field=field))


def _file_artifact(label: str, path: Path) -> dict[str, object]:
    resolved = path.expanduser().resolve(strict=True)
    payload = resolved.read_bytes()
    return {
        "label": label,
        "path": str(resolved),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "size": len(payload),
    }


def _status(value: object, *, field: str) -> None:
    mapping = _mapping(value, field=field)
    if mapping.get("status") != "passed":
        raise ValueError(f"{field} did not pass")


def _validate_accelerated(
    proposal: Mapping[str, object],
    bootstrap: Mapping[str, object],
    progress: Mapping[str, object],
) -> str:
    request = _mapping(
        proposal.get("exact_acceptance_request"), field="accelerated request"
    )
    arguments = _mapping(request.get("arguments"), field="accelerated arguments")
    approval_hash = request.get("approval_hash")
    acceptance = _mapping(arguments.get("acceptance"), field="accelerated acceptance")
    replay = _mapping(arguments.get("replay"), field="accelerated replay")
    approved_dates = _sequence(
        replay.get("trade_dates"), field="approved accelerated trade dates"
    )
    anchor = _mapping(arguments.get("live_day_anchor"), field="live day anchor")
    bootstrap_anchor = _mapping(
        bootstrap.get("live_day_anchor"), field="bootstrap live day anchor"
    )
    dates = _sequence(progress.get("trade_dates"), field="accelerated trade dates")
    hashes = _sequence(
        progress.get("day_evidence_hashes"), field="accelerated day hashes"
    )
    balanced = _sequence(
        progress.get("daily_reconciliations_balanced"),
        field="accelerated reconciliations",
    )
    if (
        proposal.get("schema") != "ditto.q4-accelerated-paper-acceptance-proposal.v1"
        or not isinstance(approval_hash, str)
        or approval_hash != canonical_hash(arguments)
        or acceptance.get("mode") != "accelerated_real_provider_replay"
        or acceptance.get("qualifies_as_wall_clock_soak") is not False
        or acceptance.get("qualifies_as_release_acceptance") is not True
        or acceptance.get("requires_current_live_day_anchor") is not True
        or bootstrap.get("schema")
        != "ditto.pap09-accelerated-provider-replay-bootstrap.v1"
        or bootstrap.get("status") != "passed"
        or bootstrap.get("request_hash") != approval_hash
        or bootstrap.get("acceptance_mode") != "accelerated_real_provider_replay"
        or bootstrap.get("qualifies_as_wall_clock_soak") is not False
        or bootstrap.get("qualifies_as_release_acceptance") is not True
        or bootstrap_anchor != anchor
        or progress.get("schema") != "ditto.pap09-accelerated-provider-replay.v1"
        or progress.get("status") != "passed"
        or progress.get("approval_hash") != approval_hash
        or progress.get("acceptance_mode") != "accelerated_real_provider_replay"
        or progress.get("qualifies_as_wall_clock_soak") is not False
        or progress.get("qualifies_as_release_acceptance") is not True
        or progress.get("accelerated_trading_day_count") != _ACCELERATED_DAY_COUNT
        or len(dates) != _ACCELERATED_DAY_COUNT
        or len(set(dates)) != _ACCELERATED_DAY_COUNT
        or tuple(sorted(cast("tuple[str, ...]", dates))) != dates
        or dates != approved_dates
        or len(hashes) != _ACCELERATED_DAY_COUNT
        or len(balanced) != _ACCELERATED_DAY_COUNT
        or not all(value is True for value in balanced)
        or progress.get("signature_chain_valid") is not True
        or progress.get("q4_five_day_ready") is not True
        or progress.get("pap09_twenty_day_release_ready") is not True
        or progress.get("remaining_accelerated_trading_days") != 0
        or _mapping(bootstrap.get("safety"), field="bootstrap safety").get(
            "broker_connections"
        )
        != 0
        or _mapping(bootstrap.get("safety"), field="bootstrap safety").get(
            "real_orders"
        )
        != 0
        or _mapping(progress.get("safety"), field="progress safety").get(
            "broker_connections"
        )
        != 0
        or _mapping(progress.get("safety"), field="progress safety").get("real_orders")
        != 0
    ):
        raise ValueError("accelerated acceptance is incomplete or inconsistent")
    return approval_hash


def _validate_restore(value: Mapping[str, object]) -> None:
    tree = _mapping(value.get("payload_tree"), field="restore payload tree")
    sqlite = _mapping(value.get("sqlite"), field="restore sqlite")
    verification = _mapping(value.get("verification"), field="restore verification")
    if (
        value.get("schema") != "ditto.q1-backup-restore.v2"
        or value.get("status") != "passed"
        or value.get("passed") is not True
        or tree.get("hashes_equal") is not True
        or sqlite.get("backup_integrity_check") != "ok"
        or sqlite.get("restore_integrity_check") != "ok"
        or sqlite.get("source_integrity_check") != "ok"
        or sqlite.get("logical_row_counts_equal") is not True
        or any(item is not True for item in verification.values())
    ):
        raise ValueError("restore evidence is incomplete")


def _validate_self_hash(
    value: Mapping[str, object], *, hash_field: str, field: str
) -> None:
    claimed = value.get(hash_field)
    body = {key: item for key, item in value.items() if key != hash_field}
    if claimed != canonical_hash(body):
        raise ValueError(f"{field} integrity hash is invalid")


def _validate_q5(proposal: Mapping[str, object], value: Mapping[str, object]) -> str:
    _validate_self_hash(value, hash_field="evidence_hash", field="Q5 acceptance")
    request = _mapping(
        proposal.get("exact_acceptance_request"), field="Q5 approval request"
    )
    arguments = _mapping(request.get("arguments"), field="Q5 approval arguments")
    approval_hash = request.get("approval_hash")
    proposal_provider = _mapping(arguments.get("provider"), field="Q5 provider")
    proposal_strategy = _mapping(arguments.get("strategy"), field="Q5 strategy")
    proposal_decision = _mapping(arguments.get("decision"), field="Q5 decision")
    receipt_provider = _mapping(value.get("provider"), field="Q5 receipt provider")
    receipt_strategy = _mapping(value.get("strategy_run"), field="Q5 receipt strategy")
    signal_package = _mapping(value.get("signal_package"), field="Q5 signal package")
    comparison = _mapping(
        value.get("comparison_request"), field="Q5 comparison request"
    )
    source_snapshots = _sequence(
        comparison.get("source_snapshot_ids"), field="Q5 source snapshots"
    )
    safety = _mapping(value.get("safety"), field="Q5 safety")
    if (
        proposal.get("schema") != "ditto.q5-live-portfolio-acceptance-proposal.v1"
        or proposal.get("status") != "pending_operator_approval"
        or request.get("requires_exact_approval") is not True
        or not isinstance(approval_hash, str)
        or approval_hash != canonical_hash(arguments)
        or arguments.get("operation") != "close-live-model-paper-manual-portfolio-v1"
        or value.get("request_hash") != approval_hash
        or receipt_provider.get("snapshot_id") != proposal_provider.get("snapshot_id")
        or receipt_provider.get("payload_checksum")
        != proposal_provider.get("payload_checksum")
        or receipt_strategy.get("strategy_id") != proposal_strategy.get("strategy_id")
        or receipt_strategy.get("strategy_version")
        != proposal_strategy.get("strategy_version")
        or receipt_strategy.get("spec_hash") != proposal_strategy.get("spec_hash")
        or comparison.get("strategy_id") != proposal_strategy.get("strategy_id")
        or comparison.get("model_portfolio_id") != signal_package.get("artifact_id")
        or comparison.get("paper_account_id")
        != proposal_decision.get("paper_account_id")
        or comparison.get("manual_account_id") != proposal_decision.get("account_id")
        or comparison.get("paper_session_id")
        != proposal_decision.get("paper_session_id")
        or comparison.get("as_of") != proposal_decision.get("signal_date")
        or source_snapshots != (proposal_provider.get("snapshot_id"),)
        or value.get("schema") != "ditto.q5-live-portfolio-acceptance.v1"
        or value.get("status") != "passed"
        or value.get("passed") is not True
        or safety.get("broker_connections") != 0
        or safety.get("real_orders") != 0
        or safety.get("paper_or_manual_journal_mutations") != 0
        or safety.get("strategy_governance_mutations") != 0
        or safety.get("agent_write_tools") != 0
    ):
        raise ValueError("Q5 approval binding or portfolio acceptance is incomplete")
    return approval_hash


def _validate_diagnostic(
    value: Mapping[str, object], *, q5: Mapping[str, object]
) -> None:
    _validate_self_hash(value, hash_field="report_hash", field="PortfolioDiagnostic")
    run = _mapping(value.get("run"), field="PortfolioDiagnostic run")
    usage = _mapping(run.get("usage"), field="PortfolioDiagnostic usage")
    egress = _mapping(value.get("egress"), field="PortfolioDiagnostic egress")
    safety = _mapping(value.get("safety"), field="PortfolioDiagnostic safety")
    if (
        value.get("schema") != "ditto.q5-live-portfolio-diagnostic.v1"
        or value.get("status") != "passed"
        or value.get("passed") is not True
        or value.get("provider") != "glm"
        or value.get("q5_acceptance_hash") != q5.get("evidence_hash")
        or run.get("status") != "completed"
        or run.get("guardrail_status") != "passed"
        or usage.get("tool_calls") != 1
        or run.get("episode_verified") is not True
        or egress.get("license_class") != "approved-research"
        or safety.get("broker_connections") != 0
        or safety.get("real_orders") != 0
        or safety.get("account_or_target_mutations") != 0
        or safety.get("agent_write_tools") != 0
    ):
        raise ValueError("PortfolioDiagnostic is incomplete")


def _validate_ui08(
    value: Mapping[str, object],
    *,
    q5: Mapping[str, object],
    diagnostic: Mapping[str, object],
) -> None:
    _validate_self_hash(value, hash_field="report_hash", field="UI-08")
    steps = tuple(
        _mapping(item, field="UI-08 step")
        for item in _sequence(value.get("steps"), field="UI-08 steps")
    )
    browser = _mapping(value.get("browser"), field="UI-08 browser")
    bindings = _mapping(value.get("evidence_bindings"), field="UI-08 evidence bindings")
    safety = _mapping(value.get("safety"), field="UI-08 safety")
    if (
        value.get("schema") != "ditto.personal-workstation.ui08-final.v1"
        or value.get("status") != "passed"
        or value.get("passed") is not True
        or tuple(item.get("step") for item in steps) != tuple(range(1, 11))
        or any(item.get("state") != "passed" for item in steps)
        or browser.get("mock_enabled") is not False
        or browser.get("live_backend") is not True
        or browser.get("console_error_count") != 0
        or bindings.get("q5_acceptance_hash") != q5.get("evidence_hash")
        or bindings.get("portfolio_diagnostic_hash") != diagnostic.get("report_hash")
        or safety != _ZERO_BROKER_SAFETY
    ):
        raise ValueError("UI-08 is incomplete")


def _validate_validation(
    value: Mapping[str, object],
    *,
    required: tuple[str, ...],
    field: str,
    not_before: datetime,
) -> datetime:
    if value.get("schema_version") != 1:
        raise ValueError(f"{field} schema is invalid")
    for name in required:
        _status(value.get(name), field=f"{field}.{name}")
    full_ci = _mapping(value.get("full_ci"), field=f"{field}.full_ci")
    completed_at = parse_timestamp(
        full_ci.get("completed_at"), field=f"{field}.full_ci.completed_at"
    )
    captured_at = parse_timestamp(
        value.get("captured_at"), field=f"{field}.captured_at"
    )
    if completed_at < not_before or captured_at < completed_at:
        raise ValueError(f"{field} did not run after final evidence was frozen")
    return captured_at


def _gate_evidence_relative_path(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("Gate evidence paths must be strings")
    relative = value.removeprefix("docs/evidence/")
    path = Path(relative)
    if not relative or path.is_absolute() or ".." in path.parts:
        raise ValueError("Gate evidence path is invalid")
    return path.as_posix()


def _validate_gates(
    values: tuple[Mapping[str, object], ...],
    paths: tuple[Path, ...],
) -> tuple[list[str], tuple[Path, ...]]:
    expected = tuple(f"Q{index}" for index in range(6))
    actual = tuple(value.get("gate") for value in values)
    if actual != expected:
        raise ValueError("prerequisite Gate sequence is invalid")
    manifest_paths: list[Path] = []
    for value, path in zip(values, paths, strict=True):
        blockers = _sequence(value.get("blockers"), field="Gate blockers")
        if (
            value.get("schema_version") != 1
            or value.get("gate_status") != "passed"
            or value.get("engineering_status") != "PROVEN"
            or blockers
        ):
            raise ValueError(f"prerequisite Gate {value.get('gate')} did not pass")
        resolved = path.expanduser().resolve(strict=True)
        workstation_root = resolved.parent.parent
        evidence_root = workstation_root.parent
        manifest_path = workstation_root / "manifests" / resolved.name
        try:
            manifest = verify_gate_manifest(evidence_root, manifest_path)
        except EvidenceManifestError as exc:
            raise ValueError(
                f"Gate manifest for {value.get('gate')} did not verify"
            ) from exc
        evidence_paths = {
            _gate_evidence_relative_path(item)
            for item in _sequence(value.get("evidence"), field="Gate evidence")
        }
        evidence_paths.add(resolved.relative_to(evidence_root).as_posix())
        manifested_paths = {artifact.relative_path for artifact in manifest.artifacts}
        if (
            manifest.gate != value.get("gate")
            or manifest.status != "passed"
            or manifest.blockers != blockers
            or manifested_paths != evidence_paths
        ):
            raise ValueError(
                f"Gate manifest for {value.get('gate')} is not bound to its decision"
            )
        manifest_paths.append(manifest_path)
    return list(expected), tuple(manifest_paths)


def build_release_candidate_bundle(
    paths: ReleaseCandidateArtifactPaths,
    *,
    generated_at: datetime,
) -> dict[str, object]:
    """Validate all Q6 prerequisites and return one content-addressed OPS-10 bundle."""
    proposal = _load(paths.accelerated_proposal, field="accelerated proposal")
    bootstrap = _load(paths.accelerated_bootstrap, field="accelerated bootstrap")
    progress = _load(paths.accelerated_progress, field="accelerated progress")
    restore = _load(paths.restore_evidence, field="restore evidence")
    q5_proposal = _load(paths.q5_proposal, field="Q5 proposal")
    q5 = _load(paths.q5_acceptance, field="Q5 acceptance")
    diagnostic = _load(paths.portfolio_diagnostic, field="PortfolioDiagnostic")
    ui08 = _load(paths.ui08_final, field="UI-08")
    backend = _load(paths.backend_validation, field="backend validation")
    frontend = _load(paths.frontend_validation, field="frontend validation")
    gates = tuple(
        _load(path, field="prerequisite Gate") for path in paths.prerequisite_gates
    )

    approval_hash = _validate_accelerated(proposal, bootstrap, progress)
    _validate_restore(restore)
    q5_approval_hash = _validate_q5(q5_proposal, q5)
    _validate_diagnostic(diagnostic, q5=q5)
    _validate_ui08(ui08, q5=q5, diagnostic=diagnostic)
    final_evidence_at = max(
        parse_timestamp(q5.get("generated_at"), field="Q5 generated_at"),
        parse_timestamp(
            diagnostic.get("generated_at"), field="PortfolioDiagnostic generated_at"
        ),
        parse_timestamp(ui08.get("generated_at"), field="UI-08 generated_at"),
    )
    backend_captured_at = _validate_validation(
        backend,
        required=("full_ci", "pit_gate", "post_pap09_changed_scope", "diff_check"),
        field="backend validation",
        not_before=final_evidence_at,
    )
    frontend_captured_at = _validate_validation(
        frontend,
        required=("full_ci", "openapi_zero_diff", "ui_07", "diff_check"),
        field="frontend validation",
        not_before=final_evidence_at,
    )
    gate_names, gate_manifest_paths = _validate_gates(gates, paths.prerequisite_gates)

    timestamp_text = rfc3339(generated_at)
    timestamp = parse_timestamp(timestamp_text, field="bundle generated_at")
    if timestamp < max(backend_captured_at, frontend_captured_at):
        raise ValueError("bundle generation preceded final validation capture")

    artifact_paths = (
        ("accelerated_proposal", paths.accelerated_proposal),
        ("accelerated_bootstrap", paths.accelerated_bootstrap),
        ("accelerated_progress", paths.accelerated_progress),
        ("restore_evidence", paths.restore_evidence),
        ("q5_proposal", paths.q5_proposal),
        ("q5_acceptance", paths.q5_acceptance),
        ("portfolio_diagnostic", paths.portfolio_diagnostic),
        ("ui08_final", paths.ui08_final),
        ("backend_validation", paths.backend_validation),
        ("frontend_validation", paths.frontend_validation),
        *tuple(
            (f"gate_{index}", path)
            for index, path in enumerate(paths.prerequisite_gates)
        ),
        *tuple(
            (f"gate_manifest_{index}", path)
            for index, path in enumerate(gate_manifest_paths)
        ),
    )
    result: dict[str, object] = {
        "schema": "ditto.personal-workstation.release-candidate.v1",
        "generated_at": timestamp_text,
        "status": "passed",
        "passed": True,
        "work_package": "OPS-10",
        "fresh_bootstrap": True,
        "restore_verified": True,
        "accelerated_acceptance_approval_hash": approval_hash,
        "q5_acceptance_approval_hash": q5_approval_hash,
        "accelerated_trading_day_count": _ACCELERATED_DAY_COUNT,
        "qualifies_as_wall_clock_soak": False,
        "live_day_anchor_bound": True,
        "portfolio_diagnostic_provider": "glm",
        "ui08_steps_passed": 10,
        "prerequisite_gates": gate_names,
        "artifacts": [_file_artifact(label, path) for label, path in artifact_paths],
        "safety": {
            "paper_only": True,
            "broker_connections": 0,
            "real_orders": 0,
            "strategy_publish_or_activation": 0,
        },
    }
    result["bundle_hash"] = canonical_hash(result)
    return result
