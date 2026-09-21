"""Public CLI replay uses actual ingestion, approval and immutable payload services."""

from contextlib import ExitStack
from datetime import UTC, datetime
from types import SimpleNamespace

import orjson
import pytest
from ditto_application.processes.ingestion.post_ingest import process_fetched_data
from ditto_application.queries.field_admission import FieldAdmissionQuery
from ditto_application.queries.provider_snapshot import ProviderSnapshotQuery
from ditto_apps.cli.main import app
from ditto_data.catalog.certification_store import SQLiteCertificationStore
from ditto_data.catalog.provider_payload import FilesystemProviderPayloadStore
from ditto_data.catalog.snapshot_reader import SnapshotReadService
from ditto_platform.foundation import SQLiteClient, SQLitePool
from packages.application.tests.integration.test_ingestion_evidence_recovery import (
    _bars,
    _pipeline,
)
from packages.application.tests.integration.test_provider_snapshot_replay import (
    _certify,
)
from typer.testing import CliRunner


@pytest.mark.integration
@pytest.mark.pit
def test_cli_replay_checks_cutoff_and_revocation_without_losing_audit(
    tmp_path, monkeypatch
):
    with ExitStack() as stack:
        runtime = stack.enter_context(
            _pipeline(tmp_path, "stock_daily", display="allowed")
        )
        pool = SQLitePool(tmp_path / "reviews.sqlite")
        stack.callback(pool.close)
        reports = SQLiteCertificationStore(SQLiteClient(pool))
        ports = runtime.ports
        visible = datetime(2026, 7, 18, 9, tzinfo=UTC)
        result = process_fetched_data(
            _bars(),
            "stock_daily",
            "2026-07-16",
            False,
            ctx=runtime.context,
            request_end="2026-07-17",
            chunk_id="cli-replay",
        )
        assert result.status == "success"
        snapshot = ports.snapshot_reader.list_snapshots()[0]
        report = _certify(runtime, reports, snapshot, tmp_path, visible)
        query = ProviderSnapshotQuery(
            SnapshotReadService(
                ports.snapshot_reader,
                FilesystemProviderPayloadStore(tmp_path),
                ports.lifecycle_reader,
            ),
            FieldAdmissionQuery(
                ports.snapshot_reader,
                ports.license_reader,
                reports,
                ports.lifecycle_reader,
                now=lambda: visible,
            ),
        )
        container = SimpleNamespace(get=lambda _type: query, close=lambda: None)
        monkeypatch.setattr(
            "ditto_apps.cli.commands.data_products.make_app_container",
            lambda: container,
        )
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
            "knowledge_cutoff": "2026-07-18T08:59:00Z",
            "publication_cutoff": visible.isoformat(),
            "purpose": "formal_research",
        }
        path = tmp_path / "request.json"
        runner = CliRunner()
        path.write_bytes(orjson.dumps(request))
        early = runner.invoke(app, ["data-products", "replay-snapshots", str(path)])
        assert early.exit_code == 2, early.output
        request["knowledge_cutoff"] = visible.isoformat()
        path.write_bytes(orjson.dumps(request))
        allowed = runner.invoke(app, ["data-products", "replay-snapshots", str(path)])
        assert allowed.exit_code == 0, allowed.output
        payload = orjson.loads(allowed.output)
        assert payload["admission"]["rule_version"] == "field-admission-v2"
        assert [row["close"] for row in payload["snapshots"][snapshot.snapshot_id]] == [
            10.0,
            20.0,
        ]
        reports.revoke_report(
            report.report_id,
            revoked_by="reviewer",
            revoked_at=visible,
            reason="withdrawn",
        )
        assert (
            runner.invoke(
                app, ["data-products", "replay-snapshots", str(path)]
            ).exit_code
            == 2
        )
        assert (
            runner.invoke(
                app, ["data-products", "read-snapshot", snapshot.snapshot_id]
            ).exit_code
            == 0
        )
