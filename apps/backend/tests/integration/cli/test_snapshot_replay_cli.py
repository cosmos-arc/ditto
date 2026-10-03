"""Public CLI replay uses actual ingestion, readiness and immutable payload services."""

from contextlib import ExitStack
from datetime import UTC, datetime
from types import SimpleNamespace

import orjson
import pytest
from ditto_application.processes.ingestion.post_ingest import (
    RequestWindow,
    process_fetched_data,
)
from ditto_application.queries.provider_snapshot import ProviderSnapshotQuery
from ditto_application.queries.snapshot_readiness import SnapshotReadinessQuery
from ditto_apps.cli.main import app
from ditto_data.catalog.provider_payload import FilesystemProviderPayloadStore
from ditto_data.catalog.snapshot_reader import SnapshotReadService
from packages.application.tests.integration.test_ingestion_evidence_recovery import (
    _bars,
    _pipeline,
)
from typer.testing import CliRunner


@pytest.mark.integration
@pytest.mark.pit
def test_cli_replay_reads_ready_snapshots_and_fails_closed_without_losing_audit(
    tmp_path, monkeypatch
):
    with ExitStack() as stack:
        runtime = stack.enter_context(
            _pipeline(
                tmp_path,
                "stock_daily",
                display="allowed",
                snapshot_now=lambda: datetime(2026, 7, 17, 10, tzinfo=UTC),
            )
        )
        ports = runtime.ports
        result = process_fetched_data(
            _bars(),
            "stock_daily",
            "2026-07-16",
            False,
            ctx=runtime.context,
            request_window=RequestWindow(None, "2026-07-17"),
            chunk_id="cli-replay",
        )
        assert result.status == "success"
        snapshot = ports.snapshot_reader.list_snapshots()[0]
        query = ProviderSnapshotQuery(
            SnapshotReadService(
                ports.snapshot_reader,
                FilesystemProviderPayloadStore(tmp_path),
                ports.lifecycle_reader,
            ),
            SnapshotReadinessQuery(ports.snapshot_reader, ports.lifecycle_reader),
        )
        container = SimpleNamespace(get=lambda _type: query, close=lambda: None)
        monkeypatch.setattr(
            "ditto_apps.cli.commands.data_products.make_app_container",
            lambda: container,
        )
        runner = CliRunner()
        request = {
            "fields": [
                {
                    "dataset_id": "stock_daily",
                    "field": "close",
                    "snapshot_id": snapshot.snapshot_id,
                }
            ],
            "instrument_ids": [1000001],
            "required_from": "2026-07-16",
            "required_to": "2026-07-17",
            "knowledge_cutoff": "2026-07-18T09:00:00Z",
        }
        path = tmp_path / "request.json"
        path.write_bytes(orjson.dumps(request))
        allowed = runner.invoke(app, ["data-products", "replay-snapshots", str(path)])
        assert allowed.exit_code == 0, allowed.output
        payload = orjson.loads(allowed.output)
        assert payload["readiness"]["rule_version"] == "snapshot-readiness-v1"
        assert [row["close"] for row in payload["snapshots"][snapshot.snapshot_id]] == [
            10.0,
            20.0,
        ]

        # An identity the ledger never registered is never replayed.
        unregistered = dict(request)
        unregistered["fields"] = [
            {**request["fields"][0], "snapshot_id": "snapshot:absent"}
        ]
        path.write_bytes(orjson.dumps(unregistered))
        rejected = runner.invoke(app, ["data-products", "replay-snapshots", str(path)])
        assert rejected.exit_code == 2, rejected.output
        assert "snapshot replay data is incomplete" in rejected.output

        # A window the snapshot never covered fails closed the same way.
        uncovered = {**request, "required_from": "2026-07-01"}
        path.write_bytes(orjson.dumps(uncovered))
        wide = runner.invoke(app, ["data-products", "replay-snapshots", str(path)])
        assert wide.exit_code == 2, wide.output
        assert "snapshot replay data is incomplete" in wide.output

        # A pinned replay never accepts an ambiguous naive knowledge cutoff.
        naive = {**request, "knowledge_cutoff": "2026-07-18T09:00:00"}
        path.write_bytes(orjson.dumps(naive))
        ambiguous = runner.invoke(app, ["data-products", "replay-snapshots", str(path)])
        assert ambiguous.exit_code == 2, ambiguous.output

        # Immutable audit access is never lost when replay refuses.
        audited = runner.invoke(
            app, ["data-products", "read-snapshot", snapshot.snapshot_id]
        )
        assert audited.exit_code == 0, audited.output
        payload = orjson.loads(audited.output)
        assert [row["close"] for row in payload["rows"]] == [10.0, 20.0]
