"""Unit contract for guarded R2 data-product operations."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import orjson
import pytest
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


def test_read_snapshot_outputs_audit_content_and_closes_container(runner, monkeypatch):
    from dataclasses import dataclass

    import polars as pl
    from ditto_application.queries.provider_snapshot import ProviderSnapshotQuery

    @dataclass
    class Snapshot:
        snapshot_id: str

    query = MagicMock(spec=ProviderSnapshotQuery)
    query.read_for_audit.return_value = SimpleNamespace(
        snapshot=Snapshot("pinned-id"),
        previous_snapshot_id="prior-id",
        observed_at=None,
        frame=pl.DataFrame({"close": [10.0]}),
    )
    container = MagicMock()
    container.get.return_value = query
    monkeypatch.setattr(
        "ditto_apps.cli.commands.data_products.make_app_container", lambda: container
    )
    result = runner.invoke(app, ["data-products", "read-snapshot", "pinned-id"])
    assert result.exit_code == 0, result.output
    assert orjson.loads(result.output) == {
        "use": "audit",
        "snapshot": {"snapshot_id": "pinned-id"},
        "previous_snapshot_id": "prior-id",
        "observed_at": None,
        "rows": [{"close": 10.0}],
    }
    query.read_for_audit.assert_called_once_with("pinned-id")
    container.get.assert_called_once_with(ProviderSnapshotQuery)
    container.close.assert_called_once()
