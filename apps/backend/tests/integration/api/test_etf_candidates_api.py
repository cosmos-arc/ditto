"""ETF candidate comparison through the real HTTP and SQLite read path."""

from __future__ import annotations

from datetime import date, timedelta
from importlib.resources import files
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import setup_dishka
from ditto_application.queries.field_admission import (
    FieldAdmissionQuery,
    FieldAdmissionRequest,
)
from ditto_application.queries.metadata import MetadataQueryFacade
from ditto_apps.api.routes.metadata import router
from ditto_data.catalog.source_snapshot import ProviderSnapshotReader
from ditto_data.services.metadata_service import MetadataService
from ditto_data.storage.metadata.instrument.instrument_reader import InstrumentReader
from ditto_platform.foundation import SQLiteClient, SQLitePool
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _setup(
    tmp_path: Path,
    *,
    admission: FieldAdmissionQuery | None = None,
    snapshots: ProviderSnapshotReader | None = None,
) -> tuple[FastAPI, SQLitePool, str]:
    """Build an isolated recorded ETF source and its HTTP reader."""
    schema = Path(str(files("ditto_data.scripts") / "schema.sql"))
    pool = SQLitePool(str(tmp_path / "etf.sqlite"), schema_path=schema)
    pool.init_schema()
    client = SQLiteClient(pool)
    for instrument_id, ticker, name in (
        (2000001, "510300", "沪深300甲 ETF"),
        (2000002, "510310", "沪深300乙 ETF"),
        (2000003, "513100", "跨境 ETF"),
    ):
        client.execute(
            """INSERT INTO instrument
               (instrument_id, ticker, name, exchange, asset_class, list_date)
               VALUES (?, ?, ?, 'SSE', 'etf', '2020-01-01')""",
            [instrument_id, ticker, name],
        )
        client.execute(
            """INSERT INTO instrument_mapping
               (instrument_id, source, source_ticker, effective_from, is_primary)
               VALUES (?, 'recorded', ?, '2020-01-01', TRUE)""",
            [instrument_id, ticker + ".SH"],
        )

    snapshot = "snapshot:recorded:etf:one"

    def add(
        instrument_id: int,
        field: str,
        value: str,
        observed_on: str,
        published_at: str = "2026-09-29T18:00:00Z",
        unit: str = "text",
        effective_to: str | None = None,
    ) -> None:
        client.execute(
            """INSERT INTO etf_reference_observation
               (instrument_id, field, value, unit, observed_on, published_at,
                effective_from, effective_to, source, source_snapshot_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'recorded', ?)""",
            [
                instrument_id,
                field,
                value,
                unit,
                observed_on,
                published_at,
                observed_on,
                effective_to,
                snapshot,
            ],
        )

    for instrument_id in (2000001, 2000002):
        add(instrument_id, "tracking_index", "000300.SH", "2020-01-01")
        add(instrument_id, "asset_class", "A股宽基", "2020-01-01")
    add(2000003, "tracking_index", "NDX", "2020-01-01")
    add(2000003, "asset_class", "跨境股票", "2020-01-01")
    add(2000001, "management_fee", "0.5", "2026-01-01", unit="%/year")
    add(2000001, "custody_fee", "0.1", "2026-01-01", unit="%/year")
    add(2000002, "management_fee", "0.2", "2026-01-01", unit="%/year")
    client.execute(
        "UPDATE instrument SET is_active = 0 WHERE instrument_id = ?", [2000003]
    )
    add(2000003, "price_close", "1.2", "2026-09-29", unit="CNY")
    add(2000003, "nav", "1.1", "2026-09-27", unit="CNY")
    add(
        2000001,
        "tracking_index",
        "FUTURE",
        "2026-09-29",
        published_at="2026-10-01T09:00:00Z",
    )

    sessions: list[str] = []
    day = date(2026, 9, 1)
    while len(sessions) < 20:
        if day.weekday() < 5:
            sessions.append(day.isoformat())
        day += timedelta(days=1)
    for index, session in enumerate(sessions):
        add(
            2000001,
            "daily_amount",
            str(100 + index),
            session,
            unit="CNY",
            effective_to=(date.fromisoformat(session) + timedelta(days=1)).isoformat(),
        )
        add(
            2000003,
            "daily_amount",
            "NaN" if index == 3 else "100",
            session,
            unit="CNY",
        )
    client.commit()

    reader = InstrumentReader(client)
    service = cast(
        MetadataService,
        SimpleNamespace(
            instrument=reader,
            list_trading_days=lambda _start, _end: sessions,
        ),
    )

    class TestProvider(Provider):
        scope = Scope.APP

        @provide
        def metadata(self) -> MetadataQueryFacade:
            return MetadataQueryFacade(
                metadata_service=service, admission=admission, snapshots=snapshots
            )

    app = FastAPI()
    setup_dishka(container=make_async_container(TestProvider()), app=app)
    app.include_router(router, prefix="/api/v1")
    return app, pool, snapshot


@pytest.mark.integration
@pytest.mark.pit
def test_etf_candidate_snapshot_and_20_session_comparison(tmp_path: Path) -> None:
    """Late revisions stay invisible and missing liquidity never wins a sort."""
    app, pool, snapshot = _setup(tmp_path)
    with TestClient(app) as web:
        response = web.get(
            "/api/v1/metadata/etf-candidates",
            params={
                "asof": "2026-09-30",
                "cutoff": "2026-09-30T18:00:00Z",
                "source_snapshot_id": snapshot,
                "exposure": "000300.SH",
                "sort_field": "daily_amount",
            },
        )
        assert response.status_code == 200, response.text
        first, second = response.json()["data"]
        assert first["instrument_id"] == 2000001
        assert first["fields"]["daily_amount"]["value"] == 109.5
        assert first["fields"]["daily_amount"]["sample_count"] == 20
        assert first["fields"]["tracking_index"]["value"] == "000300.SH"
        assert first["fields"]["tracking_index"]["eligibility"] == "unverified"
        assert first["fields"]["custody_fee"]["value"] == 0.1
        assert second["fields"]["custody_fee"]["value"] is None
        assert second["fields"]["daily_amount"]["value"] is None
        assert (
            second["fields"]["daily_amount"]["missing_reason"]
            == "incomplete_20_session_window"
        )

        cross_border = web.get(
            "/api/v1/metadata/etf-candidates",
            params={
                "asof": "2026-09-30",
                "cutoff": "2026-09-30T18:00:00Z",
                "source_snapshot_id": snapshot,
                "exposure": "NDX",
            },
        )
        assert cross_border.status_code == 200, cross_border.text
        fields = cross_border.json()["data"][0]["fields"]
        assert cross_border.json()["data"][0]["is_active"] is False
        assert fields["price_close"]["observed_on"] == "2026-09-29"
        assert fields["nav"]["observed_on"] == "2026-09-27"
        assert fields["iopv"]["missing_reason"] == "no_observation"
        assert fields["daily_amount"]["missing_reason"] == "invalid_amount_observation"
        later = web.get(
            "/api/v1/metadata/etf-candidates",
            params={
                "asof": "2026-09-30",
                "cutoff": "2026-10-02T00:00:00Z",
                "source_snapshot_id": snapshot,
                "exposure": "FUTURE",
            },
        )
        assert later.status_code == 200, later.text
        assert later.json()["data"][0]["instrument_id"] == 2000001
        historical = web.get(
            "/api/v1/metadata/etf-candidates",
            params={
                "asof": "2026-09-28",
                "cutoff": "2026-10-02T00:00:00Z",
                "source_snapshot_id": snapshot,
                "exposure": "000300.SH",
            },
        )
        assert historical.status_code == 200, historical.text
        assert [item["instrument_id"] for item in historical.json()["data"]] == [
            2000001,
            2000002,
        ]
        searched = web.get(
            "/api/v1/metadata/etf-candidates",
            params={
                "asof": "2026-09-30",
                "cutoff": "2026-09-30T18:00:00Z",
                "source_snapshot_id": snapshot,
                "search": "510310",
            },
        )
        assert searched.status_code == 200, searched.text
        assert [item["instrument_id"] for item in searched.json()["data"]] == [2000002]
        by_asset = web.get(
            "/api/v1/metadata/etf-candidates",
            params={
                "asof": "2026-09-30",
                "cutoff": "2026-09-30T18:00:00Z",
                "source_snapshot_id": snapshot,
                "asset_exposure": "跨境股票",
            },
        )
        assert by_asset.status_code == 200, by_asset.text
        assert [item["instrument_id"] for item in by_asset.json()["data"]] == [2000003]
    pool.close()


@pytest.mark.integration
def test_registered_snapshot_requires_field_display_admission(tmp_path: Path) -> None:
    """A registered but denied field cannot be displayed or sorted by value."""
    allowed = {"value": False}
    requests: list[FieldAdmissionRequest] = []

    def assess(request: FieldAdmissionRequest) -> SimpleNamespace:
        requests.append(request)
        return SimpleNamespace(
            allowed=allowed["value"],
            fields=(SimpleNamespace(reason_codes=("LICENSE_RESTRICTED",)),),
        )

    admission = cast(FieldAdmissionQuery, SimpleNamespace(assess=assess))
    snapshots = cast(
        ProviderSnapshotReader,
        SimpleNamespace(
            get_snapshot=lambda _id: SimpleNamespace(dataset_id="etf_reference")
        ),
    )
    app, pool, snapshot = _setup(tmp_path, admission=admission, snapshots=snapshots)
    params = {
        "asof": "2026-09-30",
        "cutoff": "2026-09-30T18:00:00Z",
        "source_snapshot_id": snapshot,
    }
    with TestClient(app) as web:
        blocked = web.get("/api/v1/metadata/etf-candidates", params=params)
        assert blocked.status_code == 200, blocked.text
        field = blocked.json()["data"][0]["fields"]["tracking_index"]
        assert field["value"] is None
        assert field["eligibility"] == "display_denied"
        assert field["eligibility_reasons"] == ["LICENSE_RESTRICTED"]
        assert field["missing_reason"] == "display_admission_denied"
        assert requests
        assert all(request.purpose == "display" for request in requests)
        allowed["value"] = True
        admitted = web.get("/api/v1/metadata/etf-candidates", params=params)
        assert admitted.status_code == 200, admitted.text
        field = admitted.json()["data"][0]["fields"]["tracking_index"]
        assert field["value"] == "000300.SH"
        assert field["eligibility"] == "display_allowed"
    pool.close()
