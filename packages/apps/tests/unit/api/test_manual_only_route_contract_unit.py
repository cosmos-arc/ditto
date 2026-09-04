"""Public execution routes must name the Manual boundary explicitly."""

from __future__ import annotations

from ditto_apps.main import app


def test_openapi_has_no_ambiguous_trade_or_broker_routes() -> None:
    paths = set(app.openapi()["paths"])

    assert not any(path.startswith("/api/v1/trade") for path in paths)
    assert not any("broker" in path.lower() for path in paths)
    assert {
        "/api/v1/manual/account-baseline",
        "/api/v1/manual/intents/{intent_id}/status",
        "/api/v1/manual/fills",
        "/api/v1/manual/fills/{fill_id}/void",
        "/api/v1/manual/fills/{fill_id}/replace",
    } <= paths


def test_manual_route_operations_are_labeled_manual() -> None:
    schema = app.openapi()
    operations = [
        operation
        for path, path_item in schema["paths"].items()
        if path.startswith("/api/v1/manual")
        for operation in path_item.values()
        if isinstance(operation, dict) and "operationId" in operation
    ]

    assert operations
    assert all(operation["tags"] == ["manual"] for operation in operations)
