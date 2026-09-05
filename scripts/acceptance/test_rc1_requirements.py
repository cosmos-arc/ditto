from __future__ import annotations

import subprocess
import sys

from scripts.acceptance.rc1_real_data_acceptance import _commands
from scripts.acceptance.rc1_requirements import (
    LAUNCH_DATASETS,
    validate_maturity_status,
    validate_maturity_status_from_stdout,
)


def test_launch_dataset_list_contains_stock_etf_macro_requirements() -> None:
    assert "stock_daily" in LAUNCH_DATASETS
    assert "valuation_metrics" in LAUNCH_DATASETS
    assert "etf_daily" in LAUNCH_DATASETS
    assert "macro_indicators" in LAUNCH_DATASETS


def test_validate_maturity_status_rejects_blocked_dataset() -> None:
    payload = {
        "datasets": [
            {
                "dataset": "stock_daily",
                "dataset_maturity": "experimental",
                "dataset_promotion_status": "blocked",
                "catalog_storage_uri": "sqlite:///market.db",
                "catalog_schema_hash": "abc",
                "catalog_row_count": 10,
                "catalog_freshness_status": "fresh",
            }
        ]
    }

    result = validate_maturity_status(payload, required_datasets=("stock_daily",))

    assert not result.ok
    assert result.failures == (
        "stock_daily promotion status is blocked",
        "stock_daily maturity is experimental",
    )


def test_validate_maturity_status_accepts_promoted_fresh_dataset() -> None:
    payload = {
        "datasets": [
            {
                "dataset": "stock_daily",
                "dataset_maturity": "initial-focus",
                "dataset_promotion_status": "ready",
                "catalog_storage_uri": "sqlite:///market.db",
                "catalog_schema_hash": "abc",
                "catalog_row_count": 10,
                "catalog_freshness_status": "fresh",
            }
        ]
    }

    result = validate_maturity_status(payload, required_datasets=("stock_daily",))

    assert result.ok
    assert result.failures == ()


def test_validate_maturity_status_accepts_initial_focus_without_promotion_review() -> (
    None
):
    payload = {
        "datasets": [
            {
                "dataset": "etf_daily",
                "dataset_maturity": "initial-focus",
                "dataset_promotion_status": "not_applicable",
                "catalog_storage_uri": "sqlite:///market.db",
                "catalog_schema_hash": "abc",
                "catalog_row_count": 10,
                "catalog_freshness_status": "fresh",
            }
        ]
    }

    result = validate_maturity_status(payload, required_datasets=("etf_daily",))

    assert result.ok
    assert result.failures == ()


def test_validate_maturity_status_from_stdout_rejects_invalid_json() -> None:
    result = validate_maturity_status_from_stdout("not json")

    assert not result.ok
    assert result.failures == ("maturity status stdout is not valid JSON",)


def test_rc1_real_data_commands_include_full_real_data_coverage() -> None:
    commands = dict(_commands(real_data=True, require_promoted=True))

    assert "maturity-status" in commands
    real_data_command = " ".join(commands["real-data-e2e"])
    assert "apps/backend/tests/e2e/test_real_data_pipeline.py" in real_data_command
    assert (
        "apps/backend/tests/e2e/test_real_data_stock_selection_pipeline.py"
        in real_data_command
    )


def test_rc1_acceptance_script_help_runs_when_executed_directly() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/acceptance/rc1_real_data_acceptance.py",
            "--help",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "--require-promoted" in result.stdout
