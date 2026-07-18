"""Unit contract for guarded R2 data-product operations."""

from __future__ import annotations

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
        ("certify", ["--report-id", "report-1", "--actor", "owner"]),
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
    ["bootstrap", "repair", "certify", "promotion", "revoke"],
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
    ["bootstrap", "repair", "certify", "promotion", "revoke"],
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
