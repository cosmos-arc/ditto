"""MAN-08 fresh-journal rebuild acceptance evidence."""

from __future__ import annotations

import runpy
from collections.abc import Callable
from pathlib import Path
from typing import cast


def test_manual_account_rebuild_evidence_passes_all_checks() -> None:
    repository_root = Path(__file__).parents[4]
    namespace = runpy.run_path(
        str(repository_root / "scripts/evidence/manual_account_rebuild.py"),
        run_name="manual_account_rebuild_evidence",
    )
    build_evidence = cast(
        "Callable[[], dict[str, object]]", namespace["build_evidence"]
    )
    evidence = build_evidence()

    assert evidence["result"] == "PASS"
    assert evidence["expected"] == evidence["observed"]
    assert evidence["ledger_hash"] == (
        "account-ledger:sha256:"
        "e6426e90ff2fe63037d47786692e2e97f6413fc26e171bd04bb84bd73ea854c4"
    )
    assert evidence["evidence_hash"] == (
        "sha256:5c777bdaac99b2b9fbe611c820a2dfd8170d342964ed98e515c10d40f6faf4a5"
    )
