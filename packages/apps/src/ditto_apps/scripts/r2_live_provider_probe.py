"""Redacted, bounded provider-entitlement and throughput probe for R2 live G2."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Protocol, cast

import orjson
import polars as pl
from ditto_application.queries.source import SourceDataPort

from ditto_apps.registry.container import make_app_container

__all__ = [
    "LiveProviderProbeEvidence",
    "build_live_provider_probe_evidence",
]

_PROBE_DATE = "2024-03-29"
_TARGET_PARTITIONS = 3_000
_REPRESENTATIVE_DATASETS = frozenset(
    {"stock_daily", "index_daily", "adj_factor", "fund_adj"}
)


class _TushareProbeSource(Protocol):
    """Small public-method surface used by the live provider probe."""

    def fetch_stock_basic(self) -> pl.DataFrame: ...

    def fetch_etf_basic(self) -> pl.DataFrame: ...

    def fetch_index_basic(self) -> pl.DataFrame: ...

    def fetch_calendar(self, start_date: str, end_date: str) -> pl.DataFrame: ...

    def fetch_stock_daily(self, *, trade_date: str) -> pl.DataFrame: ...

    def fetch_etf_daily(self, *, trade_date: str) -> pl.DataFrame: ...

    def fetch_index_daily(
        self,
        *,
        source_ticker: str,
        start_date: str,
        end_date: str,
    ) -> pl.DataFrame: ...

    def fetch_stock_status(self, trade_date: str) -> pl.DataFrame: ...

    def fetch_adj_factor(self, trade_date: str) -> pl.DataFrame: ...

    def fetch_fund_adj(self, *, trade_date: str) -> pl.DataFrame: ...

    def fetch_balance_sheet(self, *, trade_date: str) -> pl.DataFrame: ...

    def fetch_income_statement(self, *, trade_date: str) -> pl.DataFrame: ...

    def fetch_cash_flow(self, *, trade_date: str) -> pl.DataFrame: ...

    def fetch_dividend(self, *, trade_date: str) -> pl.DataFrame: ...

    def fetch_valuation_metrics(self, *, trade_date: str) -> pl.DataFrame: ...

    def fetch_macro_indicators(self, trade_date: str) -> pl.DataFrame: ...

    def fetch_metal_daily(
        self,
        codes: list[str],
        start_date: str,
        end_date: str,
    ) -> pl.DataFrame: ...

    def fetch_corporate_actions(self, trade_date: str) -> pl.DataFrame: ...

    def fetch_index_weight(
        self,
        index_code: str,
        trade_date: str | None = None,
    ) -> pl.DataFrame: ...


@dataclass(frozen=True, slots=True)
class _ProbeSpec:
    dataset_id: str
    provider_dataset: str
    fetch: Callable[[_TushareProbeSource], pl.DataFrame]


@dataclass(frozen=True, slots=True)
class ProviderAccessProbe:
    """Secret-free entitlement observation consumed by R2 acceptance."""

    provider_dataset: str
    entitled: bool
    evidence_uri: str
    checked_at: datetime


@dataclass(frozen=True, slots=True)
class ProviderBenchmarkProbe:
    """Measured one-partition throughput sample consumed by R2 acceptance."""

    dataset_id: str
    sample_partitions: int
    sample_rows: int
    elapsed_seconds: float
    target_partitions: int
    observed_at: datetime
    evidence_uri: str


@dataclass(frozen=True, slots=True)
class LiveProviderProbeEvidence:
    """Exact partial input for the R2 live acceptance runner."""

    provider_access: tuple[ProviderAccessProbe, ...]
    benchmarks: tuple[ProviderBenchmarkProbe, ...]
    incremental_elapsed_seconds: None = None
    workbench_query_seconds: None = None
    first_run: None = None
    second_run: None = None


def _specs() -> tuple[_ProbeSpec, ...]:
    date_value = _PROBE_DATE
    return (
        _ProbeSpec(
            "stock_basic",
            "tushare:stock_basic",
            lambda s: s.fetch_stock_basic(),
        ),
        _ProbeSpec("etf_basic", "tushare:fund_basic", lambda s: s.fetch_etf_basic()),
        _ProbeSpec(
            "index_basic",
            "tushare:index_basic",
            lambda s: s.fetch_index_basic(),
        ),
        _ProbeSpec(
            "calendar",
            "tushare:trade_cal",
            lambda s: s.fetch_calendar(date_value, date_value),
        ),
        _ProbeSpec(
            "stock_daily",
            "tushare:daily",
            lambda s: s.fetch_stock_daily(trade_date=date_value),
        ),
        _ProbeSpec(
            "etf_daily",
            "tushare:fund_daily",
            lambda s: s.fetch_etf_daily(trade_date=date_value),
        ),
        _ProbeSpec(
            "index_daily",
            "tushare:index_daily",
            lambda s: s.fetch_index_daily(
                source_ticker="000300.SH",
                start_date=date_value,
                end_date=date_value,
            ),
        ),
        _ProbeSpec(
            "stock_status",
            "tushare:stock_st",
            lambda s: s.fetch_stock_status(date_value),
        ),
        _ProbeSpec(
            "adj_factor",
            "tushare:adj_factor",
            lambda s: s.fetch_adj_factor(date_value),
        ),
        _ProbeSpec(
            "fund_adj",
            "tushare:fund_adj",
            lambda s: s.fetch_fund_adj(trade_date=date_value),
        ),
        _ProbeSpec(
            "balance_sheet",
            "tushare:balancesheet",
            lambda s: s.fetch_balance_sheet(trade_date=date_value),
        ),
        _ProbeSpec(
            "income_statement",
            "tushare:income",
            lambda s: s.fetch_income_statement(trade_date=date_value),
        ),
        _ProbeSpec(
            "cash_flow",
            "tushare:cashflow",
            lambda s: s.fetch_cash_flow(trade_date=date_value),
        ),
        _ProbeSpec(
            "dividend",
            "tushare:dividend",
            lambda s: s.fetch_dividend(trade_date=date_value),
        ),
        _ProbeSpec(
            "valuation_metrics",
            "tushare:daily_basic",
            lambda s: s.fetch_valuation_metrics(trade_date=date_value),
        ),
        _ProbeSpec(
            "macro_indicators",
            "tushare:cn_macro",
            lambda s: s.fetch_macro_indicators(date_value),
        ),
        _ProbeSpec(
            "commodity_daily",
            "tushare:commodity_reference",
            lambda s: s.fetch_metal_daily(
                ["XAUUSD.FXCM", "XAGUSD.FXCM"],
                date_value,
                date_value,
            ),
        ),
        _ProbeSpec(
            "corporate_actions",
            "tushare:corporate_actions",
            lambda s: s.fetch_corporate_actions(date_value),
        ),
        _ProbeSpec(
            "index_weight",
            "tushare:index_weight",
            lambda s: s.fetch_index_weight("000300.SH", trade_date=date_value),
        ),
    )


def build_live_provider_probe_evidence(
    source: _TushareProbeSource,
    *,
    evidence_uri: str,
    checked_at: datetime | None = None,
) -> LiveProviderProbeEvidence:
    """Call every hard-scope Tushare surface without serializing failures or secrets."""
    now = checked_at or datetime.now(UTC)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("provider probe checked_at must be timezone-aware")
    if not evidence_uri.strip():
        raise ValueError("provider probe evidence_uri cannot be blank")
    access: list[ProviderAccessProbe] = []
    benchmarks: list[ProviderBenchmarkProbe] = []
    for spec in _specs():
        started = perf_counter()
        try:
            frame = spec.fetch(source)
        except Exception:
            entitled = False
            row_count = 0
        else:
            entitled = True
            row_count = frame.height
        elapsed = max(perf_counter() - started, 1e-9)
        item_uri = f"{evidence_uri}#{spec.provider_dataset}"
        access.append(
            ProviderAccessProbe(
                provider_dataset=spec.provider_dataset,
                entitled=entitled,
                evidence_uri=item_uri,
                checked_at=now,
            )
        )
        if entitled and row_count > 0 and spec.dataset_id in _REPRESENTATIVE_DATASETS:
            benchmarks.append(
                ProviderBenchmarkProbe(
                    dataset_id=spec.dataset_id,
                    sample_partitions=1,
                    sample_rows=row_count,
                    elapsed_seconds=elapsed,
                    target_partitions=_TARGET_PARTITIONS,
                    observed_at=now,
                    evidence_uri=item_uri,
                )
            )
    return LiveProviderProbeEvidence(tuple(access), tuple(benchmarks))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Write one redacted provider probe artifact and fail if any access is denied."""
    args = _parser().parse_args(argv)
    output = args.output.expanduser().resolve(strict=False)
    container = make_app_container()
    try:
        source = cast("_TushareProbeSource", container.get(SourceDataPort))
        evidence = build_live_provider_probe_evidence(
            source,
            evidence_uri=output.as_uri(),
        )
    finally:
        container.close()
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = (
        orjson.dumps(
            asdict(evidence),
            option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS,
        )
        + b"\n"
    )
    output.write_bytes(payload)
    sys.stdout.write(
        orjson.dumps(
            {
                "benchmark_count": len(evidence.benchmarks),
                "entitled_count": sum(
                    item.entitled for item in evidence.provider_access
                ),
                "provider_count": len(evidence.provider_access),
            },
            option=orjson.OPT_SORT_KEYS,
        ).decode()
        + "\n"
    )
    complete = (
        all(item.entitled for item in evidence.provider_access)
        and frozenset(item.dataset_id for item in evidence.benchmarks)
        == _REPRESENTATIVE_DATASETS
    )
    return 0 if complete else 2


if __name__ == "__main__":
    raise SystemExit(main())
