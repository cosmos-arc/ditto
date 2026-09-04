"""Fail-closed edge evidence for Q3 live-discovery normalization helpers."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path
from typing import cast

import polars as pl
import pytest
from ditto_agent.contracts.evidence import EvidenceEnvelope
from ditto_application.commands.data_product_certification import (
    DataProductCertificationCommands,
)
from ditto_application.commands.data_product_certification_builder import (
    DataProductCertificationBuilder,
)
from ditto_apps.scripts import q3_live_discovery_support as subject
from ditto_data.catalog.certification import CertificationGovernanceStore
from ditto_data.catalog.contracts import DataAssetRef
from ditto_data.catalog.provider_payload import (
    ProviderPayloadArtifact,
    ProviderPayloadReader,
)
from ditto_data.catalog.source_snapshot import (
    ProviderSnapshot,
    ProviderSnapshotReader,
)


def _snapshot(
    *,
    snapshot_id: str = "snapshot-1",
    dataset_id: str = "stock_daily",
    request_start: str = "2024-03-29",
    request_end: str = "2024-03-29",
    payload_uri: str | None = (
        "provider_payloads/tushare/stock_daily/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.parquet"
    ),
    payload_retained: bool = True,
    partition_keys: tuple[str, ...] = (),
) -> ProviderSnapshot:
    return ProviderSnapshot(
        snapshot_id=snapshot_id,
        dataset_id=dataset_id,
        source="tushare",
        request_start=request_start,
        request_end=request_end,
        schema_version="1",
        checksum="a" * 32,
        canonical_asset=DataAssetRef(
            dataset_id=dataset_id,
            namespace="market/daily",
            partition_keys=partition_keys,
        ),
        request_parameters_hash=f"request:{snapshot_id}",
        response_metadata=(),
        license_record_id="license:tushare",
        row_count=1,
        payload_uri=payload_uri,
        payload_retained=payload_retained,
        created_at=datetime(2024, 3, 29, tzinfo=UTC),
    )


class _SnapshotReader:
    def __init__(self, snapshots: tuple[ProviderSnapshot, ...]) -> None:
        self.snapshots = snapshots

    def get_snapshot(self, snapshot_id: str) -> ProviderSnapshot | None:
        return next(
            (item for item in self.snapshots if item.snapshot_id == snapshot_id),
            None,
        )

    def list_snapshots(
        self,
        *,
        dataset_id: str | None = None,
        source: str | None = None,
        canonical_asset: DataAssetRef | None = None,
    ) -> tuple[ProviderSnapshot, ...]:
        del source, canonical_asset
        return tuple(
            item
            for item in self.snapshots
            if dataset_id is None or item.dataset_id == dataset_id
        )


class _PayloadReader:
    def __init__(self, frame: pl.DataFrame) -> None:
        self.frame = frame
        self.uri: str | None = None

    def read_payload(self, artifact: ProviderPayloadArtifact) -> pl.DataFrame:
        self.uri = artifact.uri
        return self.frame


def _daily_frame(count: int = 8) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "source_ticker": [f"6000{index:02d}.SH" for index in range(count)],
            "trade_date": [date(2024, 3, 29)] * count,
            "pct_change": [float(index) for index in range(count)],
            "close": [10.0] * count,
            "high": [10.0] * count,
            "low": [9.0] * count,
            "amount": [float(index + 1) * 1_000.0 for index in range(count)],
        }
    )


def _basic_frame(count: int = 8) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "source_ticker": [f"6000{index:02d}.SH" for index in range(count)],
            "name": [f"Asset {index}" for index in range(count)],
            "list_date": [date(2020, 1, 1)] * count,
        }
    )


def _metadata_frame(count: int = 8) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "instrument_id": [index + 1 for index in range(count)],
            "source_ticker": [f"6000{index:02d}.SH" for index in range(count)],
        }
    )


def test_rank_normalization_rejects_missing_empty_and_null_inputs() -> None:
    for frame, column in (
        (pl.DataFrame(), "score"),
        (pl.DataFrame({"other": [1.0]}), "score"),
        (pl.DataFrame({"score": [1.0, None]}), "score"),
    ):
        with pytest.raises(ValueError, match="Q3 rank input"):
            subject.normalized_rank_values(
                frame,
                value_column=column,
                output_column="rank",
            )

    single = subject.normalized_rank_values(
        pl.DataFrame({"score": [7.0]}),
        value_column="score",
        output_column="rank",
    )
    assert single["rank"].to_list() == [0.0]


@pytest.mark.parametrize(
    ("ticker", "change", "close", "high", "low", "is_st", "expected"),
    [
        ("600000.SH", 9.5, 10.0, 10.0, 9.0, False, "limit_up"),
        ("300001.SZ", 19.5, 10.0, 10.0, 9.0, False, "limit_up"),
        ("830001.BJ", 29.5, 10.0, 10.0, 9.0, False, "limit_up"),
        ("600001.SH", -4.8, 9.0, 10.0, 9.0, True, "limit_down"),
        ("600002.SH", 20.0, 9.5, 10.0, 9.0, False, "normal"),
    ],
)
def test_limit_state_respects_each_board_and_close_location(
    ticker: str,
    change: float,
    close: float,
    high: float,
    low: float,
    is_st: bool,
    expected: str,
) -> None:
    assert (
        subject.derive_limit_state(
            source_ticker=ticker,
            pct_change=change,
            close=close,
            high=high,
            low=low,
            is_st=is_st,
        )
        == expected
    )


def test_addressed_evidence_is_idempotent_and_rejects_collision(
    tmp_path: Path,
) -> None:
    path, digest = subject._write_addressed(tmp_path, "evidence", {"value": 1})
    repeated, repeated_digest = subject._write_addressed(
        tmp_path, "evidence", {"value": 1}
    )
    assert repeated == path
    assert repeated_digest == digest

    path.write_text("corrupt", encoding="utf-8")
    with pytest.raises(ValueError, match="content-addressed evidence conflict"):
        subject._write_addressed(tmp_path, "evidence", {"value": 1})


def test_snapshot_requires_one_retained_exact_partition() -> None:
    valid = _snapshot(partition_keys=("source_ticker=600000.SH",))
    wrong_partition = _snapshot(
        snapshot_id="snapshot-wrong",
        partition_keys=("source_ticker=600001.SH",),
    )
    discarded = _snapshot(
        snapshot_id="snapshot-discarded",
        payload_uri=None,
        payload_retained=False,
        partition_keys=("source_ticker=600000.SH",),
    )
    reader = cast(
        ProviderSnapshotReader,
        _SnapshotReader((valid, wrong_partition, discarded)),
    )

    selected = subject._snapshot(
        reader,
        dataset_id="stock_daily",
        request_start=date(2024, 3, 29),
        request_end=date(2024, 3, 29),
        required_partition_key="source_ticker=600000.SH",
    )
    assert selected == valid

    with pytest.raises(ValueError, match="found=0"):
        subject._snapshot(
            reader,
            dataset_id="stock_daily",
            request_start=date(2024, 3, 28),
            request_end=date(2024, 3, 29),
        )

    with pytest.raises(ValueError, match="found=2"):
        subject._snapshot(
            cast(ProviderSnapshotReader, _SnapshotReader((valid, valid))),
            dataset_id="stock_daily",
            request_start=date(2024, 3, 29),
            request_end=date(2024, 3, 29),
        )


def test_payload_requires_uri_and_preserves_artifact_identity() -> None:
    frame = pl.DataFrame({"value": [1]})
    reader = _PayloadReader(frame)
    loaded = subject._payload(
        _snapshot(),
        cast(ProviderPayloadReader, reader),
    )
    assert loaded.equals(frame)
    assert reader.uri == (
        "provider_payloads/tushare/stock_daily/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.parquet"
    )

    with pytest.raises(ValueError, match="retained payload missing"):
        subject._payload(
            _snapshot(payload_uri=None, payload_retained=False),
            cast(ProviderPayloadReader, reader),
        )


def test_bounded_universe_rejects_invalid_inputs_and_keeps_edge_cases() -> None:
    with pytest.raises(ValueError, match="bounded universe is invalid"):
        subject._bounded_universe(pl.DataFrame(), limit=8)
    with pytest.raises(ValueError, match="bounded universe is invalid"):
        subject._bounded_universe(pl.DataFrame({"source_ticker": ["A"]}), limit=7)

    frame = pl.DataFrame(
        {
            "source_ticker": [f"T{index:02d}" for index in range(12)],
            "is_st": [True, *([False] * 11)],
            "is_suspended": [False, True, *([False] * 10)],
            "limit_state": ["normal", "normal", "limit_up", *(["normal"] * 9)],
            "listing_days": [500, 500, 500, 10, *([500] * 8)],
            "amount": [float(index) for index in range(12)],
        }
    )
    bounded = subject._bounded_universe(frame, limit=8)

    assert len(bounded) == 8
    assert {"T00", "T01", "T02", "T03"} <= set(bounded["source_ticker"].to_list())


def test_selection_frame_requires_stock_facts_and_builds_etf_defaults() -> None:
    with pytest.raises(ValueError, match="requires industry and status facts"):
        subject._selection_frame(
            asset_kind="stock",
            daily=_daily_frame(),
            basic=_basic_frame(),
            metadata=_metadata_frame(),
            industry_mapping=None,
            stock_status=None,
            limit=8,
        )

    frame = subject._selection_frame(
        asset_kind="etf",
        daily=_daily_frame(),
        basic=_basic_frame(),
        metadata=_metadata_frame(),
        industry_mapping=None,
        stock_status=None,
        limit=8,
    )
    assert len(frame) == 8
    assert frame["industry_id"].null_count() == 8
    assert frame["is_st"].to_list() == [False] * 8

    tickers = _daily_frame()["source_ticker"].to_list()
    stock = subject._selection_frame(
        asset_kind="stock",
        daily=_daily_frame(),
        basic=_basic_frame(),
        metadata=_metadata_frame(),
        industry_mapping=pl.DataFrame(
            {
                "instrument_id": tickers,
                "industry_id": ["industry-1"] * 8,
            }
        ),
        stock_status=pl.DataFrame(
            {
                "source_ticker": tickers,
                "is_st": [False] * 8,
                "is_suspended": [False] * 8,
            }
        ),
        limit=8,
    )
    assert stock["industry_id"].to_list() == ["industry-1"] * 8


def test_selection_instruments_preserve_optional_industry() -> None:
    frame = pl.DataFrame(
        {
            "instrument_id": [1, 2],
            "name": ["Stock", "ETF"],
            "industry_id": ["industry-1", None],
            "liquidity_score": [1.0, -1.0],
            "momentum_score": [0.5, -0.5],
            "amount": [100.0, 50.0],
            "is_st": [False, False],
            "is_suspended": [False, False],
            "listing_days": [500, 500],
            "limit_state": ["normal", "normal"],
        }
    )

    instruments = subject._selection_instruments(frame)

    assert instruments[0].industry_id == "industry-1"
    assert instruments[1].industry_id is None


def test_rotation_skips_unobserved_industries_and_rejects_empty_output() -> None:
    classification = pl.DataFrame(
        {
            "industry_id": ["industry-1", "industry-2"],
            "industry_name": ["One", "Two"],
        }
    )
    mapping = pl.DataFrame(
        {"instrument_id": ["600000.SH"], "industry_id": ["industry-2"]}
    )
    daily = pl.DataFrame({"source_ticker": ["600000.SH"], "pct_change": [2.0]})

    observations = subject._rotation_observations(
        classification=classification,
        mapping=mapping,
        stock_daily=daily,
        regime_score=0.25,
    )
    assert tuple(item.industry_id for item in observations) == ("industry-2",)

    with pytest.raises(ValueError, match="no real mapped observations"):
        subject._rotation_observations(
            classification=classification,
            mapping=pl.DataFrame(
                {"instrument_id": ["other"], "industry_id": ["industry-3"]}
            ),
            stock_daily=daily,
            regime_score=0.25,
        )


def test_universe_identity_and_temporal_context_require_lineage() -> None:
    instruments = subject._selection_instruments(
        pl.DataFrame(
            {
                "instrument_id": [1],
                "name": ["Stock"],
                "industry_id": [None],
                "liquidity_score": [0.0],
                "momentum_score": [0.0],
                "amount": [100.0],
                "is_st": [False],
                "is_suspended": [False],
                "listing_days": [500],
                "limit_state": ["normal"],
            }
        )
    )
    identity = subject._universe_snapshot_id(
        asset_kind="stock",
        source_snapshot_ids=("snapshot-1",),
        instruments=instruments,
    )
    assert identity.startswith("universe:sha256:")

    with pytest.raises(ValueError, match="requires source snapshots"):
        subject._context(
            decision_at=datetime(2024, 3, 29, tzinfo=UTC),
            source_snapshot_ids=(),
            allowed_universe=(),
        )


def test_envelope_summary_rejects_tampering_and_replay_drift() -> None:
    temporal = subject._context(
        decision_at=datetime(2024, 3, 29, tzinfo=UTC),
        source_snapshot_ids=("snapshot-1",),
        allowed_universe=("600000.SH",),
    )
    left = EvidenceEnvelope.seal(
        evidence_id="evidence-1",
        tool_name="market-context",
        result={"value": 1},
        artifact_refs=("artifact-1",),
        temporal_context=temporal,
        lineage=("snapshot-1",),
    )
    tampered = replace(left, integrity_hash="0" * 64)
    with pytest.raises(ValueError, match="integrity failed"):
        subject._envelope_summary(tampered, left)

    right = EvidenceEnvelope.seal(
        evidence_id="evidence-1",
        tool_name="market-context",
        result={"value": 2},
        artifact_refs=("artifact-1",),
        temporal_context=temporal,
        lineage=("snapshot-1",),
    )
    with pytest.raises(ValueError, match="non-deterministic"):
        subject._envelope_summary(left, right)

    summary = subject._envelope_summary(left, left)
    assert summary["deterministic"] is True
    assert summary["integrity_hash"] == left.integrity_hash


def test_technical_certification_rejects_invalid_product_before_io(
    tmp_path: Path,
) -> None:
    context = subject._TechnicalCertificationContext(
        evidence_root=tmp_path,
        recovery_evidence=tmp_path / "missing",
        generated_at=datetime(2024, 3, 29, tzinfo=UTC),
        actor="tester",
        data_root=tmp_path,
        builder=cast(DataProductCertificationBuilder, object()),
        commands=cast(DataProductCertificationCommands, object()),
        store=cast(CertificationGovernanceStore, object()),
    )
    payload = pl.DataFrame({"trade_date": [date(2024, 3, 29)]})

    with pytest.raises(ValueError, match="daily market product"):
        subject._technical_certification(
            dataset_id="fundamental",
            instrument_code="600000.SH",
            snapshot=_snapshot(),
            payload=payload,
            context=context,
        )
    with pytest.raises(ValueError, match="snapshot dataset drift"):
        subject._technical_certification(
            dataset_id="etf_daily",
            instrument_code="518880.SH",
            snapshot=_snapshot(dataset_id="stock_daily"),
            payload=payload,
            context=context,
        )
