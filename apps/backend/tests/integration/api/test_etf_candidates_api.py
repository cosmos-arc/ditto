"""ETF candidate comparison through the real HTTP and SQLite read path."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from importlib.resources import files
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import setup_dishka
from ditto_application.queries.field_admission import (
    FieldAdmissionQuery,
    FieldAdmissionRequest,
)
from ditto_application.queries.metadata import MetadataQueryFacade
from ditto_apps.api.routes.metadata import router
from ditto_apps.middleware import configure_exception_handlers
from ditto_data.catalog.provider_payload import ProviderPayloadReader
from ditto_data.catalog.source_snapshot import ProviderSnapshotReader
from ditto_data.services.metadata_service import MetadataService
from ditto_data.storage.metadata.instrument.instrument_reader import InstrumentReader
from ditto_platform.foundation import SQLiteClient, SQLitePool
from fastapi import FastAPI
from fastapi.testclient import TestClient


class _CalendarFrame(dict):
    """Minimal frame double exposing the trade_date/is_open columns."""

    columns = ("trade_date", "is_open")


def _calendar_shards(
    calendar_days: list[str],
    overrides: list[tuple[str, str, str, str, list[str], list[bool]]] | None,
    omit: frozenset[str],
) -> tuple[list[Any], dict[str, list[str]], dict[str, list[bool]]]:
    """Split fixture calendar days into per-year shards plus later revisions.

    与生产 trade_cal 一致，每个分片 payload 覆盖其区间内的每个自然日
    （周末/节假日为 is_open=false 行）；``omit`` 模拟残缺 payload 缺日。
    """
    open_days = frozenset(calendar_days)
    shard_days: dict[str, list[str]] = {}
    shard_flags: dict[str, list[bool]] = {}
    shards = []
    for index, year in enumerate(sorted({day[:4] for day in calendar_days})):
        sessions = [day for day in calendar_days if day.startswith(year)]
        full_days: list[str] = []
        flags: list[bool] = []
        cursor = date.fromisoformat(sessions[0])
        final = date.fromisoformat(sessions[-1])
        while cursor <= final:
            iso = cursor.isoformat()
            if iso not in omit:
                full_days.append(iso)
                flags.append(iso in open_days)
            cursor += timedelta(days=1)
        checksum = f"{index:032x}"
        shard_days[checksum] = full_days
        shard_flags[checksum] = flags
        shards.append(
            SimpleNamespace(
                dataset_id="calendar",
                source="recorded",
                snapshot_id=f"snapshot:recorded:calendar:{year}",
                created_at=datetime(2026, 9, 30, tzinfo=UTC),
                last_observed_at=None,
                payload_retained=True,
                payload_uri=(f"provider_payloads/recorded/calendar/{checksum}.parquet"),
                checksum=checksum,
                row_count=len(full_days),
                request_start=full_days[0],
                request_end=full_days[-1],
            )
        )
    # (snapshot_id, source, request_start, request_end, days, flags)：request
    # 边界显式给出，模拟生产日摄取把 request 边界记成摄取日的形态。
    for index, (identifier, source, start, end, days, flags) in enumerate(
        overrides or [], start=90
    ):
        checksum = f"{index:032x}"
        shard_days[checksum] = days
        shard_flags[checksum] = flags
        shards.append(
            SimpleNamespace(
                dataset_id="calendar",
                source=source,
                snapshot_id=identifier,
                created_at=datetime(2026, 9, 30, 1, tzinfo=UTC),
                last_observed_at=None,
                payload_retained=True,
                payload_uri=(f"provider_payloads/{source}/calendar/{checksum}.parquet"),
                checksum=checksum,
                row_count=len(days),
                request_start=start,
                request_end=end,
            )
        )
    return shards, shard_days, shard_flags


def _full_date_payload(
    open_days: list[str], closed: frozenset[str] = frozenset()
) -> tuple[list[str], list[bool]]:
    """Expand weekday sessions into a full trade_cal-shaped payload."""
    days: list[str] = []
    flags: list[bool] = []
    open_set = set(open_days)
    cursor = date.fromisoformat(open_days[0])
    end = date.fromisoformat(open_days[-1])
    while cursor <= end:
        iso = cursor.isoformat()
        days.append(iso)
        flags.append(iso in open_set and iso not in closed)
        cursor += timedelta(days=1)
    return days, flags


def _setup(
    tmp_path: Path,
    *,
    admission: FieldAdmissionQuery | None = None,
    snapshots: ProviderSnapshotReader | None = None,
    source: str = "recorded",
    tracking_sessions: list[str] | None = None,
    calendar_overrides: list[tuple[str, str, str, str, list[str], list[bool]]]
    | None = None,
    calendar_omit: frozenset[str] = frozenset(),
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
        (2000004, "510900", "改指 ETF"),
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

    snapshot = f"snapshot:{source}:etf:one"

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
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                instrument_id,
                field,
                value,
                unit,
                observed_on,
                published_at,
                observed_on,
                effective_to,
                source,
                snapshot,
            ],
        )

    for instrument_id in (2000001, 2000002):
        add(instrument_id, "tracking_index", "000300.SH", "2020-01-01")
        add(instrument_id, "asset_class", "A股宽基", "2020-01-01")
    add(2000003, "tracking_index", "NDX", "2020-01-01")
    add(2000004, "tracking_index", "OLD", "2020-01-01", effective_to="2026-09-29")
    add(2000004, "tracking_index", "NEW", "2026-09-29")
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
    while len(sessions) < 22:
        if day.weekday() < 5:
            sessions.append(day.isoformat())
        day += timedelta(days=1)
    # The evaluation windows derive from the retained cutoff calendar, so the
    # fixture calendar defines both the 20-session liquidity days and the
    # tracking sessions.
    calendar_days = tracking_sessions if tracking_sessions is not None else sessions
    for index, session in enumerate(calendar_days[-20:]):
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
    # 生产日历按年度分片摄取：fixture 把日历天按年拆成多个 retained 分片，
    # 每个分片携带独立身份，窗口必须由全部分片合并而成；overrides 提供更晚
    # 创建的修订分片（逐日覆盖，后写胜出）。
    calendar_snapshots, shard_days, shard_flags = _calendar_shards(
        calendar_days, calendar_overrides, calendar_omit
    )
    snapshots_reader = SimpleNamespace(
        get_snapshot=(
            snapshots.get_snapshot if snapshots is not None else (lambda _id: None)
        ),
        list_snapshots=lambda dataset_id: (
            calendar_snapshots if dataset_id == "calendar" else []
        ),
    )
    payloads_reader = SimpleNamespace(
        read_payload=lambda artifact: _CalendarFrame(
            trade_date=list(shard_days[artifact.checksum]),
            is_open=list(shard_flags[artifact.checksum]),
        )
    )
    service = cast(MetadataService, SimpleNamespace(instrument=reader))

    class TestProvider(Provider):
        scope = Scope.APP

        @provide
        def metadata(self) -> MetadataQueryFacade:
            return MetadataQueryFacade(
                metadata_service=service,
                admission=admission,
                snapshots=cast(ProviderSnapshotReader, snapshots_reader),
                payloads=cast(ProviderPayloadReader, payloads_reader),
            )

    app = FastAPI()
    configure_exception_handlers(app)
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
        old_relation = web.get(
            "/api/v1/metadata/etf-candidates",
            params={
                "asof": "2026-09-28",
                "cutoff": "2026-09-30T18:00:00Z",
                "source_snapshot_id": snapshot,
                "exposure": "OLD",
            },
        )
        new_relation = web.get(
            "/api/v1/metadata/etf-candidates",
            params={
                "asof": "2026-09-30",
                "cutoff": "2026-09-30T18:00:00Z",
                "source_snapshot_id": snapshot,
                "exposure": "NEW",
            },
        )
        assert [item["instrument_id"] for item in old_relation.json()["data"]] == [
            2000004
        ]
        assert [item["instrument_id"] for item in new_relation.json()["data"]] == [
            2000004
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
@pytest.mark.pit
def test_etf_candidates_fail_closed_without_retained_calendar(
    tmp_path: Path,
) -> None:
    """Comparisons reject instead of reading an unversioned current calendar."""
    app, pool, snapshot = _setup(tmp_path)
    with TestClient(app) as web:
        response = web.get(
            "/api/v1/metadata/etf-candidates",
            params={
                "asof": "2026-09-28",
                "cutoff": "2026-09-29T18:00:00Z",
                "source_snapshot_id": snapshot,
            },
        )
        assert response.status_code == 200, response.text
        tracking = response.json()["data"][0]["tracking"]
        assert tracking["status"] == "unavailable"
        assert tracking["reason"] == "evaluation_calendar_absent"
        assert tracking["calendar_snapshot_ids"] == []
        stale = web.get(
            "/api/v1/metadata/etf-candidates",
            params={
                "asof": "2026-10-20",
                "cutoff": "2026-10-20T18:00:00Z",
                "source_snapshot_id": snapshot,
            },
        )
        assert stale.status_code == 200, stale.text
        tracking = stale.json()["data"][0]["tracking"]
        assert tracking["reason"] == "evaluation_calendar_stale"
    pool.close()


@pytest.mark.integration
@pytest.mark.pit
def test_etf_candidates_reject_calendar_stale_gap_before_asof(tmp_path: Path) -> None:
    """Future scheduled sessions cannot mask a stale gap before the as-of date."""
    gapped: list[str] = []
    for month in (1, 12):
        day = date(2026, month, 1)
        while day.month == month:
            if day.weekday() < 5:
                gapped.append(day.isoformat())
            day += timedelta(days=1)
    app, pool, snapshot = _setup(tmp_path, tracking_sessions=gapped)
    with TestClient(app) as web:
        response = web.get(
            "/api/v1/metadata/etf-candidates",
            params={
                "asof": "2026-06-15",
                "cutoff": "2026-09-30T18:00:00Z",
                "source_snapshot_id": snapshot,
            },
        )
        assert response.status_code == 200, response.text
        tracking = response.json()["data"][0]["tracking"]
        assert tracking["reason"] == "evaluation_calendar_stale"
    pool.close()


@pytest.mark.integration
@pytest.mark.pit
def test_newer_calendar_revision_closes_previously_open_session(
    tmp_path: Path,
) -> None:
    """A cutoff-visible correction overrides the older shard date by date."""
    days = []
    day = date(2026, 9, 30)
    while len(days) < 253:
        if day.weekday() < 5:
            days.append(day.isoformat())
        day -= timedelta(days=1)
    days.reverse()
    revision_days, revision_flags = _full_date_payload(days, frozenset({days[100]}))
    app, pool, snapshot = _setup(
        tmp_path,
        tracking_sessions=days,
        calendar_overrides=[
            (
                "snapshot:recorded:calendar:revision",
                "recorded",
                revision_days[0],
                revision_days[-1],
                revision_days,
                revision_flags,
            )
        ],
    )
    with TestClient(app) as web:
        response = web.get(
            "/api/v1/metadata/etf-candidates",
            params={
                "asof": "2026-09-30",
                "cutoff": "2026-09-30T18:00:00Z",
                "source_snapshot_id": snapshot,
                "exposure": "000300.SH",
            },
        )
        assert response.status_code == 200, response.text
        tracking = response.json()["data"][0]["tracking"]
        assert tracking["reason"] == "insufficient_trading_sessions"
        assert tracking["calendar_snapshot_ids"] == [
            "snapshot:recorded:calendar:revision"
        ]
    pool.close()


@pytest.mark.integration
@pytest.mark.pit
def test_daily_calendar_revision_beyond_asof_still_overlays_history(
    tmp_path: Path,
) -> None:
    """Daily shards record only their ingestion day but cover a full year."""
    days = []
    day = date(2026, 9, 30)
    while len(days) < 253:
        if day.weekday() < 5:
            days.append(day.isoformat())
        day -= timedelta(days=1)
    days.reverse()
    revision_days, revision_flags = _full_date_payload(days, frozenset({days[100]}))
    app, pool, snapshot = _setup(
        tmp_path,
        tracking_sessions=days,
        calendar_overrides=[
            (
                "snapshot:recorded:calendar:daily-revision",
                "recorded",
                "2026-10-01",
                "2026-10-01",
                revision_days,
                revision_flags,
            )
        ],
    )
    with TestClient(app) as web:
        response = web.get(
            "/api/v1/metadata/etf-candidates",
            params={
                "asof": "2026-09-30",
                "cutoff": "2026-10-02T00:00:00Z",
                "source_snapshot_id": snapshot,
                "exposure": "000300.SH",
            },
        )
        assert response.status_code == 200, response.text
        tracking = response.json()["data"][0]["tracking"]
        assert tracking["reason"] == "insufficient_trading_sessions"
        assert tracking["calendar_snapshot_ids"] == [
            "snapshot:recorded:calendar:daily-revision"
        ]
    pool.close()


@pytest.mark.integration
@pytest.mark.pit
def test_etf_candidates_fail_closed_on_mixed_calendar_sources(
    tmp_path: Path,
) -> None:
    """A secondary-provider calendar cannot silently replace sessions."""
    days = []
    day = date(2026, 9, 30)
    while len(days) < 253:
        if day.weekday() < 5:
            days.append(day.isoformat())
        day -= timedelta(days=1)
    days.reverse()
    # 只接手 2026 年日期：2025 年仍由 recorded 分片决定，窗口真正混合来源。
    partial = [day for day in days if day.startswith("2026")]
    app, pool, snapshot = _setup(
        tmp_path,
        tracking_sessions=days,
        calendar_overrides=[
            (
                "snapshot:secondary:calendar:one",
                "secondary",
                partial[0],
                partial[-1],
                partial,
                [True] * len(partial),
            )
        ],
    )
    with TestClient(app) as web:
        response = web.get(
            "/api/v1/metadata/etf-candidates",
            params={
                "asof": "2026-09-30",
                "cutoff": "2026-09-30T18:00:00Z",
                "source_snapshot_id": snapshot,
            },
        )
        assert response.status_code == 200, response.text
        tracking = response.json()["data"][0]["tracking"]
        assert tracking["reason"] == "evaluation_calendar_mixed_sources"
    pool.close()


@pytest.mark.integration
@pytest.mark.pit
def test_tracking_comparison_requires_complete_visible_total_return_series(
    tmp_path: Path,
) -> None:
    """The HTTP query computes only aligned 252-return evidence at one cutoff."""
    days = []
    day = date(2026, 9, 30)
    while len(days) < 253:
        if day.weekday() < 5:
            days.append(day.isoformat())
        day -= timedelta(days=1)
    days.reverse()
    app, pool, snapshot = _setup(tmp_path, tracking_sessions=days)
    client = SQLiteClient(pool)
    for instrument_id, daily_excess in ((2000001, 0.0), (2000002, 0.001)):
        for index, observed_on in enumerate(days):
            for field, value in (
                ("nav_total_return", 100 * (1.01 + daily_excess) ** index),
                ("benchmark_total_return", 100 * 1.01**index),
            ):
                client.execute(
                    """INSERT INTO etf_reference_observation
                    (instrument_id, field, value, unit, observed_on, published_at,
                     effective_from, source, source_snapshot_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'recorded', ?)""",
                    [
                        instrument_id,
                        field,
                        str(value),
                        "CNY:nav_total_return"
                        if field == "nav_total_return"
                        else "CNY:index_total_return:000300.SH",
                        observed_on,
                        "2026-10-01T00:00:00Z"
                        if instrument_id == 2000002 and index == 90
                        else "2026-09-30T18:00:00Z",
                        observed_on,
                        snapshot,
                    ],
                )
    client.commit()
    params = {
        "asof": "2026-09-30",
        "cutoff": "2026-09-30T19:00:00Z",
        "source_snapshot_id": snapshot,
        "exposure": "000300.SH",
    }
    with TestClient(app) as web:
        response = web.get("/api/v1/metadata/etf-candidates", params=params)
        assert response.status_code == 200, response.text
        first, second = response.json()["data"]
        assert first["tracking"]["status"] == "reference_only"
        assert first["tracking"]["sample_count"] == 252
        assert first["tracking"]["calendar_snapshot_ids"] == [
            "snapshot:recorded:calendar:2025",
            "snapshot:recorded:calendar:2026",
        ]
        assert first["tracking"]["tracking_deviation_pct"] == pytest.approx(0)
        assert first["tracking"]["tracking_error_pct"] == pytest.approx(0)
        assert second["tracking"]["status"] == "unavailable"
        assert second["tracking"]["reason"] == "fund_and_benchmark_total_return_missing"
        assert second["tracking"]["sample_count"] == 250
        assert second["tracking"]["start"] == days[1]
        client.execute(
            """UPDATE etf_reference_observation
               SET published_at = '2026-09-30T18:00:00Z'
               WHERE instrument_id = 2000002
                 AND field = 'benchmark_total_return' AND observed_on = ?""",
            [days[90]],
        )
        client.commit()
        missing_fund = web.get("/api/v1/metadata/etf-candidates", params=params)
        assert (
            missing_fund.json()["data"][1]["tracking"]["reason"]
            == "fund_nav_total_return_missing"
        )
        later = web.get(
            "/api/v1/metadata/etf-candidates",
            params={**params, "cutoff": "2026-10-02T00:00:00Z"},
        )
        assert later.status_code == 200, later.text
        result = next(
            item["tracking"]
            for item in later.json()["data"]
            if item["instrument_id"] == 2000002
        )
        assert result["status"] == "reference_only"
        assert result["tracking_error_pct"] == pytest.approx(0, abs=1e-10)
        assert result["tracking_deviation_pct"] > 0
    pool.close()


def _assert_shard_scoped_admission(requests: list[FieldAdmissionRequest]) -> None:
    """Calendar shards are admitted per their own authoritative interval."""
    calendar_requests = {
        request.fields[0].snapshot_id: request
        for request in requests
        if request.purpose == "formal_research"
        and request.fields[0].dataset_id == "calendar"
    }
    assert set(calendar_requests) == {
        "snapshot:recorded:calendar:2025",
        "snapshot:recorded:calendar:2026",
    }
    assert calendar_requests["snapshot:recorded:calendar:2025"].required_to.year == 2025
    assert (
        calendar_requests["snapshot:recorded:calendar:2026"].required_from.year == 2026
    )


@pytest.mark.integration
def test_tracking_formal_result_requires_field_admission_and_matching_benchmark(
    tmp_path: Path,
) -> None:
    """Display permission alone cannot produce a formal comparison."""
    days = []
    day = date(2026, 9, 30)
    while len(days) < 253:
        if day.weekday() < 5:
            days.append(day.isoformat())
        day -= timedelta(days=1)
    days.reverse()
    formal_allowed = [False]
    requests: list[FieldAdmissionRequest] = []

    def assess(request: FieldAdmissionRequest) -> SimpleNamespace:
        requests.append(request)
        return SimpleNamespace(
            allowed=request.purpose == "display" or formal_allowed[0],
            fields=(SimpleNamespace(reason_codes=("LICENSE_RESTRICTED",)),),
        )

    admission = cast(FieldAdmissionQuery, SimpleNamespace(assess=assess))
    snapshots = cast(
        ProviderSnapshotReader,
        SimpleNamespace(
            get_snapshot=lambda _id: SimpleNamespace(
                dataset_id="etf_reference", source="provider"
            )
        ),
    )
    app, pool, snapshot = _setup(
        tmp_path,
        admission=admission,
        snapshots=snapshots,
        source="provider",
        tracking_sessions=days,
    )
    client = SQLiteClient(pool)
    for index, observed_on in enumerate(days):
        for field, unit in (
            ("nav_total_return", "CNY:nav_total_return"),
            ("benchmark_total_return", "CNY:index_total_return:000300.SH"),
        ):
            client.execute(
                """INSERT INTO etf_reference_observation
                (instrument_id, field, value, unit, observed_on, published_at,
                 effective_from, source, source_snapshot_id)
                VALUES (2000001, ?, ?, ?, ?,
                        '2026-09-30T18:00:00Z', ?, 'provider', ?)""",
                [
                    field,
                    str(100 * 1.01**index),
                    unit,
                    observed_on,
                    observed_on,
                    snapshot,
                ],
            )
    client.commit()
    params = {
        "asof": "2026-09-30",
        "cutoff": "2026-09-30T19:00:00Z",
        "source_snapshot_id": snapshot,
        "search": "510300",
    }
    with TestClient(app) as web:
        denied = web.get("/api/v1/metadata/etf-candidates", params=params)
        assert denied.status_code == 200, denied.text
        tracking = denied.json()["data"][0]["tracking"]
        assert tracking["status"] == "unavailable"
        assert tracking["tracking_error_pct"] is None
        assert any(
            request.purpose == "formal_research"
            and request.required_from == date.fromisoformat(days[0])
            for request in requests
        )
        _assert_shard_scoped_admission(requests)
        formal_allowed[0] = True
        unaligned = web.get("/api/v1/metadata/etf-candidates", params=params)
        _assert_rejection_evidence(
            unaligned.json()["data"][0]["tracking"],
            "valuation_time_not_aligned",
            days,
            snapshot,
        )
        for field in ("nav_total_return", "benchmark_total_return"):
            client.execute(
                """UPDATE etf_reference_observation
                   SET unit = unit || ':valuation=07:00Z'
                   WHERE instrument_id = 2000001 AND field = ?""",
                [field],
            )
        client.commit()
        allowed = web.get("/api/v1/metadata/etf-candidates", params=params)
        assert allowed.status_code == 200, allowed.text
        tracking = allowed.json()["data"][0]["tracking"]
        assert tracking["status"] == "comparable"
        assert tracking["tracking_error_pct"] == pytest.approx(0)
        ranked = web.get(
            "/api/v1/metadata/etf-candidates",
            params={**params, "search": "", "sort_field": "tracking_error"},
        )
        assert ranked.status_code == 200, ranked.text
        assert ranked.json()["data"][0]["instrument_id"] == 2000001
        assert all(
            item["tracking"]["status"] != "comparable"
            for item in ranked.json()["data"][1:]
        )
        client.execute(
            """UPDATE etf_reference_observation
               SET unit = 'CNY:index_total_return:000300.SH:valuation=08:00Z'
               WHERE instrument_id = 2000001
                 AND field = 'benchmark_total_return' AND observed_on = ?""",
            [days[50]],
        )
        client.commit()
        asynchronous = web.get("/api/v1/metadata/etf-candidates", params=params)
        assert (
            asynchronous.json()["data"][0]["tracking"]["reason"]
            == "valuation_time_not_aligned"
        )
        client.execute(
            """UPDATE etf_reference_observation
               SET unit = 'USD:index_total_return:000300.SH'
               WHERE instrument_id = 2000001
                 AND field = 'benchmark_total_return' AND observed_on = ?""",
            [days[50]],
        )
        client.commit()
        mismatch = web.get("/api/v1/metadata/etf-candidates", params=params)
        _assert_rejection_evidence(
            mismatch.json()["data"][0]["tracking"],
            "currency_or_benchmark_mismatch",
            days,
            snapshot,
        )
    pool.close()


@pytest.mark.integration
def test_tracking_relation_source_mismatch_blocks_formal_result(
    tmp_path: Path,
) -> None:
    """A cross-source tracking relation can never reach formal comparison."""
    days = []
    day = date(2026, 9, 30)
    while len(days) < 253:
        if day.weekday() < 5:
            days.append(day.isoformat())
        day -= timedelta(days=1)
    days.reverse()
    admission = cast(
        FieldAdmissionQuery,
        SimpleNamespace(
            assess=lambda _request: SimpleNamespace(
                allowed=True, fields=(SimpleNamespace(reason_codes=()),)
            )
        ),
    )
    snapshots = cast(
        ProviderSnapshotReader,
        SimpleNamespace(
            get_snapshot=lambda _id: SimpleNamespace(
                dataset_id="etf_reference", source="provider"
            )
        ),
    )
    app, pool, snapshot = _setup(
        tmp_path,
        admission=admission,
        snapshots=snapshots,
        source="provider",
        tracking_sessions=days,
    )
    client = SQLiteClient(pool)
    for index, observed_on in enumerate(days):
        for field, unit in (
            ("nav_total_return", "CNY:nav_total_return:valuation=07:00Z"),
            (
                "benchmark_total_return",
                "CNY:index_total_return:000300.SH:valuation=07:00Z",
            ),
        ):
            client.execute(
                """INSERT INTO etf_reference_observation
                (instrument_id, field, value, unit, observed_on, published_at,
                 effective_from, source, source_snapshot_id)
                VALUES (2000001, ?, ?, ?, ?,
                        '2026-09-30T18:00:00Z', ?, 'provider', ?)""",
                [
                    field,
                    str(100 * 1.01**index),
                    unit,
                    observed_on,
                    observed_on,
                    snapshot,
                ],
            )
    client.execute(
        "UPDATE etf_reference_observation SET source = 'cross-source'"
        " WHERE instrument_id = 2000001 AND field = 'tracking_index'"
    )
    client.commit()
    with TestClient(app) as web:
        response = web.get(
            "/api/v1/metadata/etf-candidates",
            params={
                "asof": "2026-09-30",
                "cutoff": "2026-09-30T19:00:00Z",
                "source_snapshot_id": snapshot,
                "search": "510300",
            },
        )
        assert response.status_code == 200, response.text
        tracking = response.json()["data"][0]["tracking"]
        assert tracking["status"] == "unavailable"
        assert tracking["reason"] == "source_or_display_admission_denied"
    pool.close()


def _assert_rejection_evidence(
    tracking: dict[str, Any], reason: str, days: list[str], snapshot: str
) -> None:
    """A rejected aligned series still exposes its window and snapshot identity."""
    assert tracking["reason"] == reason
    assert tracking["sample_count"] == 252
    assert tracking["start"] == days[1]
    assert tracking["end"] == days[-1]
    assert tracking["currency"] is None
    assert tracking["benchmark_id"] == "000300.SH"
    assert tracking["source_snapshot_id"] == snapshot
    assert tracking["calendar_snapshot_ids"] == [
        "snapshot:recorded:calendar:2025",
        "snapshot:recorded:calendar:2026",
    ]


@pytest.mark.integration
@pytest.mark.pit
def test_find_etf_reference_bounds_time_series_to_evaluation_window(
    tmp_path: Path,
) -> None:
    """History before the tracking window stays out; effective fields stay in."""
    days = []
    day = date(2026, 9, 30)
    while len(days) < 253:
        if day.weekday() < 5:
            days.append(day.isoformat())
        day -= timedelta(days=1)
    days.reverse()
    _, pool, snapshot = _setup(tmp_path, tracking_sessions=days)
    client = SQLiteClient(pool)
    for field, unit in (
        ("nav_total_return", "CNY:nav_total_return"),
        ("benchmark_total_return", "CNY:index_total_return:000300.SH"),
    ):
        client.execute(
            """INSERT INTO etf_reference_observation
               (instrument_id, field, value, unit, observed_on, published_at,
                effective_from, source, source_snapshot_id)
               VALUES (2000001, ?, '100', ?, '2024-01-01',
                       '2026-09-30T18:00:00Z', '2024-01-01', 'recorded', ?)""",
            [field, unit, snapshot],
        )
    client.commit()
    reader = InstrumentReader(client)
    _, observations = reader.find_etf_reference(
        asof="2026-09-30",
        cutoff="2026-09-30T19:00:00Z",
        source_snapshot_id=snapshot,
        observed_since=days[0],
    )
    observed = {(str(row["field"]), str(row["observed_on"])) for row in observations}
    assert ("nav_total_return", "2024-01-01") not in observed
    assert ("benchmark_total_return", "2024-01-01") not in observed
    assert ("daily_amount", days[-1]) in observed
    assert ("tracking_index", "2020-01-01") in observed
    pool.close()


@pytest.mark.integration
@pytest.mark.pit
def test_tracking_lineage_excludes_shards_outside_selected_window(
    tmp_path: Path,
) -> None:
    """Shards loaded for the 550-day lookback but outside the final 253
    sessions neither enter the lineage nor require formal admission."""
    stale_year: list[str] = []
    day = date(2024, 9, 2)
    while day <= date(2024, 12, 31):
        if day.weekday() < 5:
            stale_year.append(day.isoformat())
        day += timedelta(days=1)
    days: list[str] = []
    day = date(2026, 1, 30)
    while len(days) < 253:
        if day.weekday() < 5:
            days.append(day.isoformat())
        day -= timedelta(days=1)
    days.reverse()
    app, pool, snapshot = _setup(tmp_path, tracking_sessions=stale_year + days)
    with TestClient(app) as web:
        response = web.get(
            "/api/v1/metadata/etf-candidates",
            params={
                "asof": "2026-01-30",
                "cutoff": "2026-09-30T18:00:00Z",
                "source_snapshot_id": snapshot,
                "exposure": "000300.SH",
            },
        )
        assert response.status_code == 200, response.text
        tracking = response.json()["data"][0]["tracking"]
        assert tracking["reason"] == "fund_and_benchmark_total_return_missing"
        assert tracking["calendar_snapshot_ids"] == [
            "snapshot:recorded:calendar:2025",
            "snapshot:recorded:calendar:2026",
        ]
    pool.close()


@pytest.mark.integration
@pytest.mark.pit
def test_foreign_calendar_shard_outside_window_does_not_block(
    tmp_path: Path,
) -> None:
    """A foreign-source shard contributing no window date is not ambiguity."""
    days = []
    day = date(2026, 9, 30)
    while len(days) < 253:
        if day.weekday() < 5:
            days.append(day.isoformat())
        day -= timedelta(days=1)
    days.reverse()
    future: list[str] = []
    day = date(2026, 12, 1)
    while day.month == 12:
        if day.weekday() < 5:
            future.append(day.isoformat())
        day += timedelta(days=1)
    app, pool, snapshot = _setup(
        tmp_path,
        tracking_sessions=days,
        calendar_overrides=[
            (
                "snapshot:secondary:calendar:future",
                "secondary",
                future[0],
                future[-1],
                future,
                [True] * len(future),
            )
        ],
    )
    with TestClient(app) as web:
        response = web.get(
            "/api/v1/metadata/etf-candidates",
            params={
                "asof": "2026-09-30",
                "cutoff": "2026-09-30T18:00:00Z",
                "source_snapshot_id": snapshot,
                "exposure": "000300.SH",
            },
        )
        assert response.status_code == 200, response.text
        tracking = response.json()["data"][0]["tracking"]
        assert tracking["calendar_snapshot_ids"] == [
            "snapshot:recorded:calendar:2025",
            "snapshot:recorded:calendar:2026",
        ]
    pool.close()


@pytest.mark.integration
@pytest.mark.pit
def test_narrow_closure_shard_stays_in_tracking_lineage(tmp_path: Path) -> None:
    """A correction that only closes a date still shaped the window."""
    days = []
    day = date(2026, 9, 30)
    while len(days) < 253:
        if day.weekday() < 5:
            days.append(day.isoformat())
        day -= timedelta(days=1)
    days.reverse()
    correction = days[200]
    app, pool, snapshot = _setup(
        tmp_path,
        tracking_sessions=days,
        calendar_overrides=[
            (
                "snapshot:recorded:calendar:closure",
                "recorded",
                correction,
                correction,
                [correction],
                [False],
            )
        ],
    )
    with TestClient(app) as web:
        response = web.get(
            "/api/v1/metadata/etf-candidates",
            params={
                "asof": "2026-09-30",
                "cutoff": "2026-09-30T18:00:00Z",
                "source_snapshot_id": snapshot,
                "exposure": "000300.SH",
            },
        )
        assert response.status_code == 200, response.text
        tracking = response.json()["data"][0]["tracking"]
        assert tracking["reason"] == "insufficient_trading_sessions"
        assert "snapshot:recorded:calendar:closure" in tracking["calendar_snapshot_ids"]
    pool.close()


@pytest.mark.integration
@pytest.mark.pit
def test_foreign_calendar_shard_before_window_does_not_block(
    tmp_path: Path,
) -> None:
    """A foreign shard owning only pre-window dates is not consumed."""
    stale_year: list[str] = []
    day = date(2024, 9, 2)
    while day <= date(2024, 12, 31):
        if day.weekday() < 5:
            stale_year.append(day.isoformat())
        day += timedelta(days=1)
    days: list[str] = []
    day = date(2026, 1, 30)
    while len(days) < 253:
        if day.weekday() < 5:
            days.append(day.isoformat())
        day -= timedelta(days=1)
    days.reverse()
    app, pool, snapshot = _setup(
        tmp_path,
        tracking_sessions=stale_year + days,
        calendar_overrides=[
            (
                "snapshot:secondary:calendar:past",
                "secondary",
                stale_year[0],
                stale_year[-1],
                stale_year,
                [True] * len(stale_year),
            )
        ],
    )
    with TestClient(app) as web:
        response = web.get(
            "/api/v1/metadata/etf-candidates",
            params={
                "asof": "2026-01-30",
                "cutoff": "2026-09-30T18:00:00Z",
                "source_snapshot_id": snapshot,
                "exposure": "000300.SH",
            },
        )
        assert response.status_code == 200, response.text
        tracking = response.json()["data"][0]["tracking"]
        assert tracking["calendar_snapshot_ids"] == [
            "snapshot:recorded:calendar:2025",
            "snapshot:recorded:calendar:2026",
        ]
    pool.close()


@pytest.mark.integration
@pytest.mark.pit
def test_partial_calendar_payload_with_hole_fails_closed(tmp_path: Path) -> None:
    """A payload missing a mid-range chunk must not read as extra closures."""
    days = []
    day = date(2026, 9, 30)
    while len(days) < 293:
        if day.weekday() < 5:
            days.append(day.isoformat())
        day -= timedelta(days=1)
    days.reverse()
    omitted = {days[100]}
    cursor = date.fromisoformat(days[100])
    while cursor <= date.fromisoformat(days[139]):
        omitted.add(cursor.isoformat())
        cursor += timedelta(days=1)
    app, pool, snapshot = _setup(
        tmp_path, tracking_sessions=days, calendar_omit=frozenset(omitted)
    )
    with TestClient(app) as web:
        response = web.get(
            "/api/v1/metadata/etf-candidates",
            params={
                "asof": "2026-09-30",
                "cutoff": "2026-09-30T18:00:00Z",
                "source_snapshot_id": snapshot,
            },
        )
        assert response.status_code == 200, response.text
        tracking = response.json()["data"][0]["tracking"]
        assert tracking["reason"] == "evaluation_calendar_gap"
    pool.close()


@pytest.mark.integration
def test_unregistered_provider_snapshot_hides_reference_values(tmp_path: Path) -> None:
    """Only isolated recorded fixtures can be inspected without catalog evidence."""
    app, pool, snapshot = _setup(tmp_path, source="provider")
    with TestClient(app) as web:
        response = web.get(
            "/api/v1/metadata/etf-candidates",
            params={
                "asof": "2026-09-30",
                "cutoff": "2026-09-30T18:00:00Z",
                "source_snapshot_id": snapshot,
            },
        )
        assert response.status_code == 200, response.text
        field = response.json()["data"][0]["fields"]["tracking_index"]
        assert field["value"] is None
        assert field["eligibility"] == "display_denied"
        assert field["eligibility_reasons"] == ["ADMISSION_UNAVAILABLE"]
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
