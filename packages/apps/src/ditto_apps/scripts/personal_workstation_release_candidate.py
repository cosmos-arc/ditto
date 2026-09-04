"""Build the read-only OPS-10 personal-workstation release-candidate bundle."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from ditto_apps.operations.personal_workstation_release_candidate import (
    ReleaseCandidateArtifactPaths,
    build_release_candidate_bundle,
)
from ditto_apps.operations.q4_accelerated_paper_acceptance import (
    approved_accelerated_acceptance_request,
)
from ditto_apps.operations.q4_live_account_acceptance import (
    atomic_write_json,
    canonical_hash,
    load_json,
)
from ditto_apps.registry.live.q4_accelerated_paper_acceptance_runtime import (
    verify_accelerated_acceptance,
)

_PREREQUISITE_GATE_COUNT = 6


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--accelerated-proposal", type=Path, required=True)
    parser.add_argument("--accelerated-bootstrap", type=Path, required=True)
    parser.add_argument("--accelerated-progress", type=Path, required=True)
    parser.add_argument("--restore-evidence", type=Path, required=True)
    parser.add_argument("--q5-proposal", type=Path, required=True)
    parser.add_argument("--q5-acceptance", type=Path, required=True)
    parser.add_argument("--portfolio-diagnostic", type=Path, required=True)
    parser.add_argument("--ui08-final", type=Path, required=True)
    parser.add_argument("--backend-validation", type=Path, required=True)
    parser.add_argument("--frontend-validation", type=Path, required=True)
    parser.add_argument("--gate", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Validate every input before atomically writing the OPS-10 bundle."""
    arguments = _parser().parse_args(argv)
    gates = tuple(arguments.gate)
    if len(gates) != _PREREQUISITE_GATE_COUNT:
        raise ValueError("exactly six --gate inputs (Q0 through Q5) are required")
    paths = ReleaseCandidateArtifactPaths(
        accelerated_proposal=arguments.accelerated_proposal,
        accelerated_bootstrap=arguments.accelerated_bootstrap,
        accelerated_progress=arguments.accelerated_progress,
        restore_evidence=arguments.restore_evidence,
        q5_proposal=arguments.q5_proposal,
        q5_acceptance=arguments.q5_acceptance,
        portfolio_diagnostic=arguments.portfolio_diagnostic,
        ui08_final=arguments.ui08_final,
        backend_validation=arguments.backend_validation,
        frontend_validation=arguments.frontend_validation,
        prerequisite_gates=gates,
    )
    proposal = load_json(
        paths.accelerated_proposal.resolve(strict=True), field="proposal"
    )
    request = proposal.get("exact_acceptance_request")
    if not isinstance(request, Mapping):
        raise ValueError("accelerated proposal request is invalid")
    approval_hash = cast("Mapping[str, object]", request).get("approval_hash")
    if not isinstance(approval_hash, str):
        raise ValueError("accelerated proposal approval hash is invalid")
    approved = approved_accelerated_acceptance_request(
        proposal,
        approved_request_hash=approval_hash,
    )
    rebuilt_progress = verify_accelerated_acceptance(
        data_root=approved.data_root,
        evidence_root=approved.evidence_root,
        expected_approval_hash=approved.request_hash,
    )
    published_progress = load_json(
        paths.accelerated_progress.resolve(strict=True), field="accelerated progress"
    )
    if canonical_hash(rebuilt_progress) != canonical_hash(published_progress):
        raise ValueError("public progress differs from the signed accelerated runtime")
    payload = build_release_candidate_bundle(paths, generated_at=datetime.now(UTC))
    atomic_write_json(arguments.output.expanduser().resolve(), payload)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
