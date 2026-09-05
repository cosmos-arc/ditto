"""Read-only composition for the exact Q5 live portfolio proposal."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Protocol, TypeVar, cast

import polars as pl
from ditto_application.processes.execution.strategy_run_process import (
    StrategyFacade,
    StrategyRunMode,
    StrategyRunServiceConfig,
)
from ditto_application.queries.source import SourceDataPort
from ditto_application.queries.strategy import StrategyQueryFacade
from ditto_backtest.data_feed import Slice
from ditto_data.services.metadata_service import MetadataService
from ditto_kernel.identity import InstrumentId
from ditto_kernel.trading import MarketSnapshot

from ditto_apps.operations.q4_live_account_acceptance import (
    SHANGHAI,
    canonical_text,
)
from ditto_apps.operations.q5_live_portfolio_acceptance import (
    LivePortfolioAcceptanceProposalInput,
    build_live_portfolio_acceptance_proposal,
)
from ditto_apps.registry.container import make_app_container
from ditto_apps.registry.infra.config import preload_runtime_secrets

__all__ = ["LivePortfolioProposalRequest", "build_live_portfolio_proposal"]

_STRATEGY_ID = "seed_etf_industry_rotation"
_STRATEGY_VERSION = 1
_SIGNAL_DATE = "2026-09-02"
_T = TypeVar("_T")


class _MarketSource(Protocol):
    def fetch_etf_daily(self, **kwargs: object) -> pl.DataFrame: ...


class _Container(Protocol):
    def get(self, dependency_type: type[_T]) -> _T: ...

    def close(self) -> None: ...


@dataclass(frozen=True, slots=True)
class LivePortfolioProposalRequest:
    """Composition inputs for the read-only live portfolio proposal."""

    data_root: Path
    trading_database: Path
    evidence_root: Path
    q3_evidence: Path
    account_evidence: Path
    observed_at: datetime


def _date_text(value: object, *, field: str) -> str:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return canonical_text(value, field=field)


def _provider_rows(
    frame: pl.DataFrame,
    *,
    metadata: MetadataService,
    universe: str,
) -> tuple[dict[str, object], ...]:
    universe_ids = tuple(metadata.get_universe(universe, asof=_SIGNAL_DATE))
    if not universe_ids:
        raise ValueError("published strategy universe is empty")
    id_by_ticker = {
        metadata.resolve_source_ticker(
            instrument_id=instrument_id,
            asset_class="etf",
            source="tushare",
            asof=_SIGNAL_DATE,
        ): instrument_id
        for instrument_id in universe_ids
    }
    by_ticker = {
        str(row["source_ticker"]): row
        for row in frame.to_dicts()
        if str(row.get("source_ticker")) in id_by_ticker
    }
    missing = tuple(sorted(set(id_by_ticker) - set(by_ticker)))
    if missing:
        raise ValueError(f"provider response lacks strategy universe rows: {missing}")
    return tuple(
        {
            "instrument_id": instrument_id,
            "source_ticker": ticker,
            "trade_date": _date_text(raw.get("trade_date"), field="trade_date"),
            "knowledge_date": _date_text(
                raw.get("knowledge_date"), field="knowledge_date"
            ),
            "open": raw.get("open"),
            "high": raw.get("high"),
            "low": raw.get("low"),
            "close": raw.get("close"),
            "pre_close": raw.get("pre_close"),
            "volume": raw.get("volume"),
            "amount": raw.get("amount"),
            "pct_change": raw.get("pct_change"),
        }
        for ticker, instrument_id in sorted(
            id_by_ticker.items(), key=lambda item: item[1]
        )
        for raw in (by_ticker[ticker],)
    )


def _strategy_slice(
    rows: Sequence[Mapping[str, object]], *, observed_at: datetime
) -> Slice:
    bars = {
        InstrumentId(cast(int, row["instrument_id"])): MarketSnapshot(
            trade_date=cast(str, row["trade_date"]),
            instrument_id=InstrumentId(cast(int, row["instrument_id"])),
            open=float(cast(float, row["open"])),
            high=float(cast(float, row["high"])),
            low=float(cast(float, row["low"])),
            close=float(cast(float, row["close"])),
            prev_close=float(cast(float, row["pre_close"])),
            volume=float(cast(float, row["volume"])),
            amount=float(cast(float, row["amount"])),
        )
        for row in rows
    }
    return Slice(
        trade_date=_SIGNAL_DATE,
        step_time=observed_at.astimezone(SHANGHAI),
        bars=bars,
        source_snapshot_ids=dict.fromkeys(bars, "proposal-preview-only"),
    )


def build_live_portfolio_proposal(
    request: LivePortfolioProposalRequest,
    *,
    container_factory: Callable[[], _Container] = cast(
        "Callable[[], _Container]", make_app_container
    ),
) -> dict[str, object]:
    """Compose a real-provider strategy preview and freeze its exact identity."""
    preload_runtime_secrets()
    container = container_factory()
    try:
        strategy_query = container.get(StrategyQueryFacade)
        active = strategy_query.get_active_published(_STRATEGY_ID)
        detail = strategy_query.get_version_detail(_STRATEGY_ID, _STRATEGY_VERSION)
        if (
            active is None
            or active.version != _STRATEGY_VERSION
            or detail is None
            or detail.state != "published"
        ):
            raise ValueError("exact published strategy version is not active")
        universe = cast(str, active.spec_json.get("universe"))
        if not universe:
            raise ValueError("active strategy universe is absent")
        provider = cast(_MarketSource, container.get(SourceDataPort))
        raw_frame = provider.fetch_etf_daily(trade_date=_SIGNAL_DATE)
        rows = _provider_rows(
            raw_frame,
            metadata=container.get(MetadataService),
            universe=universe,
        )
        preview = container.get(StrategyFacade).run_strategy_from_catalog(
            config=StrategyRunServiceConfig(
                strategy_id=_STRATEGY_ID,
                strategy_version=str(_STRATEGY_VERSION),
                run_id=f"preview-{_SIGNAL_DATE}-{_STRATEGY_ID}-{_STRATEGY_VERSION}",
                mode=StrategyRunMode.RESEARCH,
                manage_run_lifecycle=False,
            ),
            trade_date=_SIGNAL_DATE,
            slice_=_strategy_slice(rows, observed_at=request.observed_at),
            version=_STRATEGY_VERSION,
        )
        return build_live_portfolio_acceptance_proposal(
            LivePortfolioAcceptanceProposalInput(
                data_root=request.data_root,
                trading_database=request.trading_database,
                evidence_root=request.evidence_root,
                generated_at=request.observed_at,
                q3_evidence_path=request.q3_evidence,
                account_evidence_path=request.account_evidence,
                provider_rows=rows,
                raw_provider_row_count=len(raw_frame),
                strategy_spec_hash=detail.spec_hash,
                strategy_universe=universe,
                target_positions={
                    int(key): value for key, value in preview.target.positions.items()
                },
                factor_values=preview.factor_values,
                cash_target=preview.target.cash_target,
            )
        )
    finally:
        container.close()
