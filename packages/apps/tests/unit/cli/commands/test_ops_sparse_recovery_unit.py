"""CLI contract for sparse PIT full-history recovery."""

from __future__ import annotations

from ditto_apps.cli.commands.ops import app
from typer.testing import CliRunner


def test_reattest_sparse_pit_outputs_application_result(mocker) -> None:
    recover = mocker.patch(
        "ditto_apps.cli.commands.ops.run_sparse_pit_reattestation",
        return_value={
            "dataset": "balance_sheet",
            "source": "tushare",
            "signal_date": "2026-07-16",
            "passed": True,
            "component_dates": ["2026-06-30"],
            "components": [{"trade_date": "2026-06-30", "passed": True}],
            "source_snapshot_id": "snapshot:aggregate",
            "source_snapshot_ids": ["snapshot:component"],
            "row_count": 12,
        },
    )

    result = CliRunner().invoke(
        app,
        [
            "reattest-sparse-pit",
            "--dataset",
            "balance_sheet",
            "--signal-date",
            "2026-07-16",
            "--source",
            "tushare",
        ],
    )

    assert result.exit_code == 0
    assert '"passed": true' in result.stdout
    assert '"source_snapshot_id": "snapshot:aggregate"' in result.stdout
    recover.assert_called_once_with(
        dataset="balance_sheet",
        signal_date="2026-07-16",
        source="tushare",
    )


def test_reattest_sparse_pit_returns_nonzero_for_failed_evidence(mocker) -> None:
    mocker.patch(
        "ditto_apps.cli.commands.ops.run_sparse_pit_reattestation",
        return_value={
            "dataset": "balance_sheet",
            "source": "tushare",
            "signal_date": "2026-07-16",
            "passed": False,
            "component_dates": ["2026-06-30"],
            "components": [
                {
                    "trade_date": "2026-06-30",
                    "passed": False,
                    "error": "SPARSE_REATTEST_COMPONENT_DURABLE_EVIDENCE_INVALID",
                }
            ],
            "error": "SPARSE_REATTEST_COMPONENT_FAILED",
        },
    )

    result = CliRunner().invoke(
        app,
        [
            "reattest-sparse-pit",
            "--dataset",
            "balance_sheet",
            "--signal-date",
            "2026-07-16",
        ],
    )

    assert result.exit_code == 1
    assert '"passed": false' in result.stdout
    assert "SPARSE_REATTEST_COMPONENT_FAILED" in result.stdout
