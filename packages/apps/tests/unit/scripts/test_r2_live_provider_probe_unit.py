"""Unit contract for the redacted R2 live provider probe."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

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

    def __getattr__(self, name: str):
        def fetch(*args: object, **kwargs: object) -> pl.DataFrame:
            del args, kwargs
            self.calls.append(name)
            if name == self.failing_method:
                raise RuntimeError("unsafe-provider-detail secret-value")
            return pl.DataFrame({"value": [1, 2]})

        return fetch


@pytest.mark.unit
def test_probe_covers_all_hard_products_and_four_benchmarks() -> None:
    source = _Source()

    evidence = build_live_provider_probe_evidence(
        cast("object", source),
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
        cast("object", source),
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
            cast("object", _Source()),
            evidence_uri="file:///acceptance/provider-probe.json",
            checked_at=datetime(2026, 8, 1),
        )
