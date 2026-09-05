"""PAP-08 controlled five-trading-day preacceptance evidence."""

from __future__ import annotations

import runpy
from collections.abc import Callable
from pathlib import Path
from typing import cast

import orjson


def test_paper_five_day_preacceptance_passes_without_duplicates() -> None:
    repository_root = Path(__file__).parents[4]
    namespace = runpy.run_path(
        str(repository_root / "scripts/evidence/paper_five_day_preacceptance.py"),
        run_name="paper_five_day_preacceptance_evidence",
    )
    build_evidence = cast(
        "Callable[[], dict[str, object]]", namespace["build_evidence"]
    )
    evidence = build_evidence()

    assert evidence["result"] == "PASS"
    assert evidence["run_mode"] == "controlled_deterministic_preacceptance"
    assert evidence["qualifies_as_real_soak"] is False
    assert evidence["real_trading_day_count"] == 0
    assert evidence["restart_count"] == 5

    days = cast("list[dict[str, object]]", evidence["days"])
    assert len(days) == 5
    assert {day["asset_class"] for day in days} == {"stock", "etf"}
    assert all(day["first_execution_status"] == "created" for day in days)
    assert all(day["replay_execution_status"] == "replayed" for day in days)
    assert all(day["execution_count"] == 1 for day in days)
    assert all(day["fill_count"] == 1 for day in days)
    assert all(day["ledger_fill_count"] == 1 for day in days)
    assert all(day["balanced"] is True for day in days)
    assert all(day["ledger_event_id"] for day in days)
    assert all(day["reconciliation_checksum"] for day in days)

    checks = cast("dict[str, bool]", evidence["checks"])
    assert all(checks.values())
    assert evidence["evidence_hash"] == (
        "sha256:7e4b823ba09f975c3dd37b96a89460e15ba069599d0e18b6c8b516227d314a6c"
    )

    artifact_path = (
        repository_root
        / "docs"
        / "evidence"
        / "personal-workstation"
        / "20260831-paper-five-day-preacceptance.json"
    )
    committed = cast(
        "dict[str, object]",
        orjson.loads(artifact_path.read_bytes()),
    )
    committed_deterministic = {
        key: value for key, value in committed.items() if key != "generated_at"
    }
    generated_deterministic = {
        key: value for key, value in evidence.items() if key != "generated_at"
    }
    assert committed_deterministic == generated_deterministic
