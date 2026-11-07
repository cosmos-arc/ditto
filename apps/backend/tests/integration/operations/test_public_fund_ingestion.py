"""Recorded provider responses through the real ingestion and query composition."""

import json
import sqlite3
from contextlib import closing
from dataclasses import replace
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

import httpx
import pytest
from ditto_apps.registry.container import make_app_container
from ditto_apps.registry.contexts import create_query_context
from ditto_apps.registry.contexts.ingestion import create_ingestion_bundle
from ditto_apps.registry.infra.init_providers import MetadataDbInitProvider
from ditto_data.ingestion.partition_state import (
    PartitionLifecycleStatus,
    PartitionLifecycleWriter,
)
from ditto_kernel.instrument import InstrumentIngestParams


def _configure_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    repo = Path(__file__).parents[5]
    root = tmp_path / "state"
    root.mkdir()
    monkeypatch.setenv("ENVIRONMENT", "testing")
    monkeypatch.setenv("DITTO_CONFIG_ROOT", str(repo))
    monkeypatch.setenv("DITTO_STATE_ROOT", str(root))
    monkeypatch.setenv("DITTO_CACHE_ROOT", str(tmp_path / "cache"))
    monkeypatch.setenv("TUSHARE_TOKEN", "recorded-provider-test")
    monkeypatch.setenv("SQLITE_PATH", str(root / "metadata" / "metadata.sqlite"))
    assert MetadataDbInitProvider().initialize(root).success

    return root


@pytest.mark.integration
@pytest.mark.pit
def test_otc_fund_reaches_query_without_tradable_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, respx_mock
) -> None:
    root = _configure_state(tmp_path, monkeypatch)

    calls: list[dict] = []

    def response(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        calls.append(body)
        params = body["params"]
        assert params["ts_code"] in {"000001.OF", "999999.OF"}
        fields = body["fields"].split(",")
        if body["api_name"] == "fund_basic":
            row = {
                "ts_code": "000001.OF",
                "name": "华夏成长",
                "market": "O",
                "status": "L",
                "found_date": "20011218",
            }
            rows = (
                [row]
                if (
                    params["market"] == "O"
                    and params["status"] == "L"
                    and params["ts_code"] == "000001.OF"
                )
                else []
            )
        elif body["api_name"] == "fund_portfolio":
            rows = [
                {
                    "ts_code": "000001.OF",
                    "ann_date": "20260721",
                    "end_date": "20260630",
                    "symbol": "600519.SH",
                    "mkv": 1000.0,
                    "amount": None,
                    "stk_mkv_ratio": 1.0,
                    "stk_float_ratio": None,
                }
            ]
        else:
            raise AssertionError(body["api_name"])
        if params.get("offset", 0) or params.get("end_date") == "20141231":
            rows = []
        return httpx.Response(
            200,
            json={
                "code": 0,
                "data": {
                    "fields": fields,
                    "items": [[row.get(f) for f in fields] for row in rows],
                },
            },
        )

    respx_mock.post("http://api.tushare.pro").mock(side_effect=response)
    with create_ingestion_bundle("tushare") as bundle:
        params = InstrumentIngestParams(
            ticker="000001.OF", start_date="2026-01-01", end_date="2026-09-30"
        )
        for _ in range(2):
            result = bundle.coordinator.ingest_by_instrument("fund_portfolio", params)
            assert result.status == "success", result
        _assert_per_fund_empty_replay(bundle.coordinator, root)
        snapshots = bundle.snapshot_reader.list_snapshots(dataset_id="fund_portfolio")
        assert snapshots
        assert all(
            dict(snapshot.response_metadata)["source_ticker"] == "000001.OF"
            for snapshot in snapshots
        )
        with pytest.raises(
            ValueError, match="fund_basic returned no holder identities"
        ):
            bundle.coordinator.ingest_by_instrument(
                "fund_portfolio",
                InstrumentIngestParams(
                    ticker="999999.OF", start_date="2026-01-01", end_date="2026-09-30"
                ),
            )
        assert not any(
            call["api_name"] == "fund_portfolio"
            and call["params"]["ts_code"] == "999999.OF"
            for call in calls
        )
    with create_query_context() as query:
        frame = query.fundamental.get_fund_portfolio(
            "000001.OF",
            "2026-01-01",
            "2026-09-30",
            "2026-07-21",
            allow_experimental_data=True,
        )
        assert frame.height == 1
        assert frame["instrument_id"].to_list() == [None]
        assert frame["holding_shares"].to_list() == [None]
        assert frame["report_type"].to_list() == ["unknown"]
        observations = query.fundamental.list_fund_portfolio_observations("000001.OF")
        assert observations
        assert {row["payload_retained"] for row in observations} == {True, False}
        assert observations[0]["snapshot_id"] in {s.snapshot_id for s in snapshots}
        assert query.fundamental.list_fund_portfolio_observations("999999.OF") == []
    _assert_report_round_trip(frame["holdings_sha256"][0])
    assert any(call["params"].get("offset", 0) > 0 for call in calls)


def _assert_per_fund_empty_replay(coordinator, root: Path) -> None:
    empty_params = InstrumentIngestParams(
        ticker="000001.OF", start_date="2014-01-01", end_date="2014-12-31"
    )
    for _ in range(2):
        empty = coordinator.ingest_by_instrument("fund_portfolio", empty_params)
        assert empty.status == "success", empty
        assert empty.row_count == 0
    # Positive/zero observations and COMPLETE replay stay per fund.
    with sqlite3.connect(root / "metadata" / "metadata.sqlite") as database:
        assert (
            database.execute(
                "SELECT COUNT(*) FROM ingestion_log "
                "WHERE dataset='fund_portfolio' AND status='SUCCESS'"
            ).fetchone()[0]
            == 0
        )


def _assert_report_round_trip(holdings_sha256: str) -> None:
    document = b"recorded quarterly original"
    document_hash = sha256(document).hexdigest()
    evidence = json.dumps(
        {
            "source_ticker": "000001.OF",
            "report_date": "2026-06-30",
            "announcement_date": "2026-07-21",
            "report_type": "quarterly",
            "document_form": "body",
            "document_sha256": document_hash,
            "source_url": "https://example.test/quarterly.pdf",
            "title": "Quarterly fixture",
            "holdings_sha256": holdings_sha256,
            "evidence_note": "Reviewed recorded fixture",
        }
    ).encode()
    with create_ingestion_bundle("tushare") as bundle:
        assert bundle.coordinator.register_fund_report(evidence, document) == {
            "fund_code": "000001.OF",
            "report_id": document_hash,
        }
    with create_query_context() as query:
        annotated = query.fundamental.get_fund_portfolio(
            "000001.OF",
            "2026-01-01",
            "2026-09-30",
            "2026-07-21",
            allow_experimental_data=True,
        )
        assert annotated["report_type"].to_list() == ["quarterly"]


@pytest.mark.integration
@pytest.mark.pit
@pytest.mark.parametrize("returned_day", ["20261026", "20261025", "20261027", None])
def test_market_fund_disclosures_register_holders_and_expose_market_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    respx_mock,
    returned_day: str | None,
) -> None:
    root = _configure_state(tmp_path, monkeypatch)
    calls: list[dict] = []
    codes = ["000001.OF", "510300.SH"]
    empty = False
    market_value = 1000.0

    def response(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        calls.append(body)
        params = body["params"]
        fields = body["fields"].split(",")
        if body["api_name"] == "fund_basic":
            rows = [
                {
                    "ts_code": code,
                    "name": code,
                    "market": market,
                    "status": "L",
                    "found_date": "20010101",
                }
                for code, market in zip(codes, ["O", "E"], strict=True)
                if params["market"] == market and params["status"] == "L"
            ]
        else:
            assert body["api_name"] == "fund_portfolio"
            assert params["ann_date"] == "20261026"
            assert not params.get("ts_code")
            rows = [
                {
                    "ts_code": code,
                    "ann_date": returned_day,
                    "end_date": "20260930",
                    "symbol": "600519.SH",
                    "mkv": market_value,
                    "amount": None,
                    "stk_mkv_ratio": 1.0,
                    "stk_float_ratio": None,
                }
                for code in codes
            ]
        if params.get("offset", 0) or (empty and body["api_name"] == "fund_portfolio"):
            rows = []
        return httpx.Response(
            200,
            json={
                "code": 0,
                "data": {
                    "fields": fields,
                    "items": [[row.get(f) for f in fields] for row in rows],
                },
            },
        )

    respx_mock.post("http://api.tushare.pro").mock(side_effect=response)
    with create_ingestion_bundle("tushare") as bundle:
        if returned_day == "20261026":
            empty = True
            first = bundle.coordinator.ingest_date("fund_portfolio", "2026-10-26")
            assert (first.status, first.row_count) == ("success", 0)
            _mark_fund_day_for_recheck(bundle, "old-zero")
            empty = False
        result = bundle.coordinator.ingest_date("fund_portfolio", "2026-10-26")
        if returned_day != "20261026":
            assert result.status == "failed", result
            assert any(call["api_name"] == "fund_portfolio" for call in calls)
            assert not list((root / "fundamental" / "fund_portfolio").glob("*.parquet"))
            return
        assert result.status == "success", result
        assert result.row_count == 2
        assert (
            bundle.coordinator.ingest_date("fund_portfolio", "2026-10-26").status
            == "skipped"
        )
        _mark_fund_day_for_recheck(bundle, "changed-values")
        market_value = 2000.0
        assert (
            bundle.coordinator.ingest_date("fund_portfolio", "2026-10-26").status
            == "failed"
        )
    with create_query_context() as query:
        for code in codes:
            frame = query.fundamental.get_fund_portfolio(
                code,
                "2026-01-01",
                "2026-11-05",
                "2026-10-26",
                allow_experimental_data=True,
            )
            assert frame.height == 1
            assert frame["instrument_id"].to_list() == [None]
            assert frame["holding_shares"].to_list() == [None]
            assert frame["market_value"].to_list() == [1000.0]
            observations = query.fundamental.list_fund_portfolio_observations(code)
            assert len(observations) == 2
            assert {row["scope"] for row in observations} == {"market"}
            assert {row["source_ticker"] for row in observations} == {None}
            assert {row["rows"] for row in observations} == {0, 2}
    assert any(call["params"].get("offset", 0) for call in calls)


def _mark_fund_day_for_recheck(bundle, suffix: str) -> None:
    checkpoint = bundle.lifecycle_reader.get_latest_checkpoint(
        "partition:tushare:fund_portfolio:2026-10-26:2026-10-26"
    )
    assert checkpoint is not None
    with closing(make_app_container()) as container:
        container.get(PartitionLifecycleWriter).plan_partition(
            replace(
                checkpoint,
                chunk_id=checkpoint.chunk_id + ":revision:" + suffix,
                status=PartitionLifecycleStatus.PLANNED,
                payload_id=None,
                complete_evidence_id=None,
                error_code=None,
                updated_at=datetime.now(UTC),
            )
        )


@pytest.mark.integration
def test_fred_commodity_legs_keep_source_identity_and_single_value_shape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, respx_mock
) -> None:
    """FRED commodity ingestion must never call its nonexistent metal interface."""
    repo = Path(__file__).parents[5]
    root = tmp_path / "state"
    root.mkdir()
    monkeypatch.setenv("ENVIRONMENT", "testing")
    monkeypatch.setenv("DITTO_CONFIG_ROOT", str(repo))
    monkeypatch.setenv("DITTO_STATE_ROOT", str(root))
    monkeypatch.setenv("DITTO_CACHE_ROOT", str(tmp_path / "cache"))
    monkeypatch.setenv("TUSHARE_TOKEN", "recorded-provider-test")
    monkeypatch.setenv("FRED_API_KEY", "recorded-fred-test")
    assert MetadataDbInitProvider().initialize(root).success
    series: list[str] = []

    def response(request: httpx.Request) -> httpx.Response:
        series.append(request.url.params["series_id"])
        return httpx.Response(
            200,
            json={
                "observations": [
                    {
                        "date": "2026-11-02",
                        "value": ".",
                        "realtime_start": "2026-11-06",
                        "realtime_end": "2026-11-06",
                    },
                    {
                        "date": "2026-11-03",
                        "value": "20.0",
                        "realtime_start": "2026-11-06",
                        "realtime_end": "2026-11-06",
                    },
                ]
            },
        )

    respx_mock.get("https://api.stlouisfed.org/fred/series/observations").mock(
        side_effect=response
    )
    with create_ingestion_bundle("fred") as bundle:
        result = bundle.coordinator.ingest_date("commodity_daily", "2026-11-05")
        assert result.status == "success", result
        snapshots = bundle.snapshot_reader.list_snapshots(dataset_id="commodity_daily")
        assert {snapshot.source for snapshot in snapshots} == {"fred"}
    assert set(series) == {"DCOILWTICO", "DCOILBRENTEU", "VIXCLS"}
    with create_query_context() as query:
        frame = query.market.find_bars(
            instrument_ids=[5_000_001, 5_000_002, 5_100_001],
            asset_class="commodity",
            start="2026-11-03",
            end="2026-11-03",
            allow_experimental_data=True,
        )
        assert frame.height == 3
        assert frame["close"].to_list() == [20.0] * 3
        assert frame["open"].null_count() == 3
