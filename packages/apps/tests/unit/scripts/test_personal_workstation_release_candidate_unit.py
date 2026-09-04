"""OPS-10 entrypoint must reverify private accelerated evidence."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import orjson
import pytest
from ditto_apps.scripts import personal_workstation_release_candidate as release_script


def test_release_candidate_cli_rejects_public_progress_that_differs_from_hmac_rebuild(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposal = tmp_path / "proposal.json"
    proposal.write_bytes(
        orjson.dumps(
            {
                "schema": "proposal",
                "exact_acceptance_request": {"approval_hash": "a" * 64},
            }
        )
    )
    progress = tmp_path / "progress.json"
    progress.write_bytes(orjson.dumps({"status": "tampered"}))
    approved = SimpleNamespace(
        request_hash="a" * 64,
        data_root=tmp_path / "private",
        evidence_root=tmp_path / "public",
    )
    monkeypatch.setattr(
        release_script,
        "approved_accelerated_acceptance_request",
        lambda proposal, *, approved_request_hash: approved,
        raising=False,
    )
    monkeypatch.setattr(
        release_script,
        "verify_accelerated_acceptance",
        lambda **kwargs: {"status": "passed"},
        raising=False,
    )
    monkeypatch.setattr(
        release_script,
        "build_release_candidate_bundle",
        lambda paths, *, generated_at: {"status": "passed"},
    )

    gates = [
        item
        for index in range(6)
        for item in ("--gate", str(tmp_path / f"Q{index}.json"))
    ]
    argv = [
        "--accelerated-proposal",
        str(proposal),
        "--accelerated-bootstrap",
        str(tmp_path / "bootstrap.json"),
        "--accelerated-progress",
        str(progress),
        "--restore-evidence",
        str(tmp_path / "restore.json"),
        "--q5-proposal",
        str(tmp_path / "q5-proposal.json"),
        "--q5-acceptance",
        str(tmp_path / "q5.json"),
        "--portfolio-diagnostic",
        str(tmp_path / "diagnostic.json"),
        "--ui08-final",
        str(tmp_path / "ui08.json"),
        "--backend-validation",
        str(tmp_path / "backend.json"),
        "--frontend-validation",
        str(tmp_path / "frontend.json"),
        *gates,
        "--output",
        str(tmp_path / "release-candidate.json"),
    ]

    with pytest.raises(ValueError, match="signed accelerated runtime"):
        release_script.main(argv)
