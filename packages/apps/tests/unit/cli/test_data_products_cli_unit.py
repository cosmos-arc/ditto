"""Unit contract for guarded R2 data-product operations."""

from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock

import orjson
import pytest
from ditto_apps.cli.commands.data_products import (
    DataProductOperationOptions,
    execute_data_product_operation,
)
from ditto_apps.cli.main import app
from typer.testing import CliRunner


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.mark.unit
@pytest.mark.parametrize(
    ("operation", "extra_args"),
    [
        ("bootstrap", ["--start-date", "2020-01-01", "--end-date", "2020-01-31"]),
        ("repair", []),
        ("certify", ["--report-id", "report-1", "--actor", "owner"]),
        (
            "license",
            [
                "--source",
                "tushare",
                "--terms-version",
                "terms-2026-08",
                "--effective-from",
                "2026-08-01",
                "--actor",
                "owner",
                "--notes",
                "Reviewed provider terms for local research use.",
            ],
        ),
        ("build-certification", []),
        (
            "promotion",
            [
                "--criterion",
                "coverage",
                "--evidence-uri",
                "evidence://coverage",
                "--actor",
                "owner",
            ],
        ),
        (
            "revoke",
            [
                "--report-id",
                "report-1",
                "--actor",
                "owner",
                "--reason",
                "evidence_invalidated",
            ],
        ),
    ],
)
def test_dangerous_command_previews_without_execution(
    runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
    extra_args: list[str],
) -> None:
    """Every dangerous operation defaults to a side-effect-free preview."""
    execute = MagicMock()
    monkeypatch.setattr(
        "ditto_apps.cli.commands.data_products.execute_data_product_operation",
        execute,
    )
    result = runner.invoke(
        app,
        ["data-products", operation, "stock_daily", *extra_args],
    )
    assert result.exit_code == 0
    payload = orjson.loads(result.output)
    assert payload["mode"] == "preview"
    assert payload["confirmation_phrase"] == (
        f"data-product:{operation}:stock_daily:confirm"
    )
    execute.assert_not_called()


@pytest.mark.unit
@pytest.mark.parametrize(
    "operation",
    [
        "bootstrap",
        "repair",
        "license",
        "build-certification",
        "certify",
        "promotion",
        "revoke",
    ],
)
def test_dangerous_command_rejects_wrong_confirmation(
    runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
) -> None:
    """A truthy flag is insufficient; the exact preview phrase is required."""
    execute = MagicMock()
    monkeypatch.setattr(
        "ditto_apps.cli.commands.data_products.execute_data_product_operation",
        execute,
    )
    result = runner.invoke(
        app,
        [
            "data-products",
            operation,
            "stock_daily",
            "--confirm",
            "yes",
        ],
    )
    assert result.exit_code == 2
    assert "confirmation does not match preview" in result.output
    execute.assert_not_called()


@pytest.mark.unit
@pytest.mark.parametrize(
    "operation",
    [
        "bootstrap",
        "repair",
        "license",
        "build-certification",
        "certify",
        "promotion",
        "revoke",
    ],
)
def test_exact_confirmation_executes_selected_operation_once(
    runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
) -> None:
    """An exact confirmation crosses the guard and invokes one operation."""
    execute = MagicMock(return_value={"status": "completed"})
    monkeypatch.setattr(
        "ditto_apps.cli.commands.data_products.execute_data_product_operation",
        execute,
    )
    result = runner.invoke(
        app,
        [
            "data-products",
            operation,
            "stock_daily",
            "--confirm",
            f"data-product:{operation}:stock_daily:confirm",
        ],
    )
    assert result.exit_code == 0
    assert orjson.loads(result.output)["status"] == "completed"
    assert execute.call_count == 1


@pytest.mark.unit
@pytest.mark.parametrize("operation", ["bootstrap", "repair"])
def test_ingestion_operation_exits_nonzero_when_any_chunk_failed(
    runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
) -> None:
    """Automation must not mistake a rendered partial result for success."""
    execute = MagicMock(
        return_value={
            "status": "completed",
            "success_count": 2,
            "skipped_count": 0,
            "failed_count": 1,
        }
    )
    monkeypatch.setattr(
        "ditto_apps.cli.commands.data_products.execute_data_product_operation",
        execute,
    )

    result = runner.invoke(
        app,
        [
            "data-products",
            operation,
            "stock_daily",
            "--confirm",
            f"data-product:{operation}:stock_daily:confirm",
        ],
    )

    assert result.exit_code == 1
    assert orjson.loads(result.output)["failed_count"] == 1


@pytest.mark.unit
def test_bootstrap_binds_explicit_reviewed_license_to_ingestion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = MagicMock()
    manager.backfill_range.return_value = SimpleNamespace(status="completed")

    @contextmanager
    def bundle(*, source: str, license_record_id: str | None = None):
        assert source == "tushare"
        assert license_record_id == "license:tushare:stock_daily:sha256:reviewed"
        yield SimpleNamespace(backfill_manager=manager)

    monkeypatch.setattr(
        "ditto_apps.cli.commands.data_products.create_ingestion_bundle",
        bundle,
    )

    execute_data_product_operation(
        "bootstrap",
        "stock_daily",
        DataProductOperationOptions(
            start_date="2026-07-01",
            end_date="2026-07-02",
            license_record_id="license:tushare:stock_daily:sha256:reviewed",
        ),
    )

    manager.backfill_range.assert_called_once_with(
        dataset="stock_daily",
        start_date="2026-07-01",
        end_date="2026-07-02",
        parallel=1,
        instrument_ids=(),
    )


@pytest.mark.unit
def test_bootstrap_forwards_repeatable_instrument_ids(
    runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    execute = MagicMock(return_value={"status": "completed"})
    monkeypatch.setattr(
        "ditto_apps.cli.commands.data_products.execute_data_product_operation",
        execute,
    )

    result = runner.invoke(
        app,
        [
            "data-products",
            "bootstrap",
            "index_daily",
            "--instrument-id",
            "3",
            "--instrument-id",
            "9",
            "--confirm",
            "data-product:bootstrap:index_daily:confirm",
        ],
    )

    assert result.exit_code == 0
    options = execute.call_args.args[2]
    assert options.instrument_ids == (3, 9)


@pytest.mark.unit
def test_build_certification_forwards_explicit_bounded_window(
    runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    execute = MagicMock(return_value={"status": "completed"})
    monkeypatch.setattr(
        "ditto_apps.cli.commands.data_products.execute_data_product_operation",
        execute,
    )

    result = runner.invoke(
        app,
        [
            "data-products",
            "build-certification",
            "index_daily",
            "--target-from",
            "2024-02-01",
            "--target-to",
            "2024-03-29",
            "--confirm",
            "data-product:build-certification:index_daily:confirm",
        ],
    )

    assert result.exit_code == 0
    options = execute.call_args.args[2]
    assert options.target_from == "2024-02-01"
    assert options.target_to == "2024-03-29"
