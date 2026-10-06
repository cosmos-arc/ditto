"""#518/#523：L3 巡检 capital 域日频帧读取分支."""

from __future__ import annotations

import polars as pl
import pytest
from ditto_application.processes.quality.patrol import QualityPatrolService


def _service(capital_facade):
    return QualityPatrolService(
        engine=_EngineStub(),
        market_facade=_MarketStub(),
        metadata_facade=_MetadataStub(),
        capital_facade=capital_facade,
    )


class _EngineStub:
    def has_statistical_rules(self, dataset: str) -> bool:
        return dataset in {"moneyflow", "cyq_perf"}

    def check_statistical(self, dataset: str, **_kwargs: object):
        from ditto_data.quality.quality_types import DQResult

        return DQResult(dataset=dataset, passed=True, issues=[])


class _MarketStub:
    pass


class _MetadataStub:
    def list_calendar_range(self, **kwargs):
        return pl.DataFrame({"trade_date": []})


class _CapitalStub:
    def __init__(self):
        self.calls: list[tuple[str, str, str]] = []

    def get_moneyflows(self, start: str, end: str, **_kwargs: object) -> pl.DataFrame:
        self.calls.append(("moneyflow", start, end))
        return pl.DataFrame()

    def get_cyq_perfs(self, start: str, end: str, **_kwargs: object) -> pl.DataFrame:
        self.calls.append(("cyq_perf", start, end))
        return pl.DataFrame()


@pytest.mark.unit
def test_moneyflow_l3_reads_via_capital_facade() -> None:
    capital = _CapitalStub()
    result = _service(capital).check_dataset("moneyflow", "2026-09-30")
    assert result.passed
    assert ("moneyflow", "2026-09-30", "2026-09-30") in capital.calls


@pytest.mark.unit
def test_capital_dataset_without_facade_fails_explicitly() -> None:
    result = _service(None).check_dataset("cyq_perf", "2026-09-30")
    assert not result.passed
    assert result.error == "L3_CAPITAL_FACADE_UNAVAILABLE"
