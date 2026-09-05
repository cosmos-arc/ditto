"""Unit contract for the redacted R2 live provider probe."""

from __future__ import annotations

from datetime import UTC, date, datetime

import orjson
import polars as pl
import pytest
from ditto_apps.scripts.r2_live_provider_probe import (
    LiveProviderProbeEvidence,
    build_live_provider_probe_evidence,
)


class _Source:
    def __init__(self, *, failing_method: str | None = None) -> None:
        self.failing_method = failing_method
        self.calls: list[str] = []

    def _fetch(self, name: str) -> pl.DataFrame:
        self.calls.append(name)
        if name == self.failing_method:
            raise RuntimeError("unsafe-provider-detail secret-value")
        return pl.DataFrame({"value": [1, 2]})

    def fetch_stock_basic(self) -> pl.DataFrame:
        return self._fetch("fetch_stock_basic")

    def fetch_etf_basic(self) -> pl.DataFrame:
        return self._fetch("fetch_etf_basic")

    def fetch_index_basic(self) -> pl.DataFrame:
        return self._fetch("fetch_index_basic")

    def fetch_calendar(self, start_date: str, end_date: str) -> pl.DataFrame:
        del start_date, end_date
        return self._fetch("fetch_calendar")

    def fetch_stock_daily(self, *, trade_date: str) -> pl.DataFrame:
        del trade_date
        return self._fetch("fetch_stock_daily")

    def fetch_etf_daily(self, *, trade_date: str) -> pl.DataFrame:
        del trade_date
        return self._fetch("fetch_etf_daily")

    def fetch_index_daily(
        self,
        *,
        source_ticker: str,
        start_date: str,
        end_date: str,
    ) -> pl.DataFrame:
        del source_ticker, start_date, end_date
        return self._fetch("fetch_index_daily")

    def fetch_global_index_daily(
        self,
        codes: list[str],
        start_date: str,
        end_date: str,
    ) -> pl.DataFrame:
        del codes, start_date, end_date
        return self._fetch("fetch_global_index_daily")

    def fetch_sw_industry(self, level: int = 1) -> pl.DataFrame:
        del level
        return self._fetch("fetch_sw_industry")

    def fetch_sw_industry_concepts(self, level: int = 1) -> pl.DataFrame:
        del level
        return self._fetch("fetch_sw_industry_concepts")

    def fetch_stock_status(self, trade_date: str) -> pl.DataFrame:
        del trade_date
        return self._fetch("fetch_stock_status")

    def fetch_adj_factor(self, trade_date: str) -> pl.DataFrame:
        del trade_date
        return self._fetch("fetch_adj_factor")

    def fetch_fund_adj(self, *, trade_date: str) -> pl.DataFrame:
        del trade_date
        return self._fetch("fetch_fund_adj")

    def fetch_balance_sheet(self, *, trade_date: str) -> pl.DataFrame:
        del trade_date
        return self._fetch("fetch_balance_sheet")

    def fetch_income_statement(self, *, trade_date: str) -> pl.DataFrame:
        del trade_date
        return self._fetch("fetch_income_statement")

    def fetch_cash_flow(self, *, trade_date: str) -> pl.DataFrame:
        del trade_date
        return self._fetch("fetch_cash_flow")

    def fetch_dividend(self, *, trade_date: str) -> pl.DataFrame:
        del trade_date
        return self._fetch("fetch_dividend")

    def fetch_valuation_metrics(self, *, trade_date: str) -> pl.DataFrame:
        del trade_date
        return self._fetch("fetch_valuation_metrics")

    def fetch_macro_indicators_by_codes(
        self,
        codes: list[str],
        start_date: str,
        end_date: str,
        *,
        observed_on: date | None = None,
    ) -> pl.DataFrame:
        del codes, start_date, end_date, observed_on
        return self._fetch("fetch_macro_indicators_by_codes")

    def fetch_metal_daily(
        self,
        codes: list[str],
        start_date: str,
        end_date: str,
    ) -> pl.DataFrame:
        del codes, start_date, end_date
        return self._fetch("fetch_metal_daily")

    def fetch_corporate_actions(self, trade_date: str) -> pl.DataFrame:
        del trade_date
        return self._fetch("fetch_corporate_actions")

    def fetch_index_weight(
        self,
        index_code: str,
        trade_date: str | None = None,
    ) -> pl.DataFrame:
        del index_code, trade_date
        return self._fetch("fetch_index_weight")


@pytest.mark.unit
def test_probe_covers_all_hard_products_and_four_benchmarks() -> None:
    source = _Source()

    evidence = build_live_provider_probe_evidence(
        source,
        evidence_uri="file:///acceptance/provider-probe.json",
        checked_at=datetime(2026, 8, 1, tzinfo=UTC),
    )

    assert isinstance(evidence, LiveProviderProbeEvidence)
    assert len(evidence.provider_access) == 23
    assert all(item.entitled for item in evidence.provider_access)
    assert {
        "tushare:cn_macro",
        "tushare:index_global",
        "tushare:index_classify",
        "tushare:index_member_all",
        "tushare:sw_daily",
    }.issubset({item.provider_dataset for item in evidence.provider_access})
    assert {item.dataset_id for item in evidence.benchmarks} == {
        "stock_daily",
        "index_daily",
        "adj_factor",
        "fund_adj",
    }
    assert len(source.calls) == 23
    assert "fetch_macro_indicators_by_codes" in source.calls
    assert "fetch_global_index_daily" in source.calls
    assert "fetch_sw_industry" in source.calls
    assert "fetch_sw_industry_concepts" in source.calls


@pytest.mark.unit
def test_probe_failure_is_redacted_and_fail_closed() -> None:
    source = _Source(failing_method="fetch_corporate_actions")

    evidence = build_live_provider_probe_evidence(
        source,
        evidence_uri="file:///acceptance/provider-probe.json",
        checked_at=datetime(2026, 8, 1, tzinfo=UTC),
    )
    payload = orjson.dumps(evidence)

    target = next(
        item
        for item in evidence.provider_access
        if item.provider_dataset == "tushare:corporate_actions"
    )
    assert target.entitled is False
    assert b"unsafe-provider-detail" not in payload
    assert b"secret-value" not in payload


@pytest.mark.unit
def test_probe_rejects_naive_timestamp() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        build_live_provider_probe_evidence(
            _Source(),
            evidence_uri="file:///acceptance/provider-probe.json",
            checked_at=datetime(2026, 8, 1),
        )
