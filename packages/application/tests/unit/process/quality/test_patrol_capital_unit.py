"""#518/#523：L3 巡检 capital 域日频帧读取分支."""

from __future__ import annotations

from typing import Any, Literal, cast

import polars as pl
import pytest
from ditto_application.processes.quality.patrol import QualityPatrolService
from ditto_application.queries.market import MarketQueryFacade
from ditto_application.queries.metadata import MetadataQueryFacade
from ditto_data.quality.checkers.cross_source import CrossSourceComparison
from ditto_data.quality.quality_types import DQResult


def _service(capital_facade):
    # MarketQueryFacade/MetadataQueryFacade 为具体类（非协议），无法以轻量
    # stub 结构化满足；capital 分支不读取它们，按测试 mock 边界单点收窄。
    return QualityPatrolService(
        engine=_EngineStub(),
        market_facade=cast("MarketQueryFacade", _MarketStub()),
        metadata_facade=cast("MetadataQueryFacade", _MetadataStub()),
        capital_facade=capital_facade,
    )


class _EngineStub:
    def has_statistical_rules(self, dataset: str) -> bool:
        return dataset in {"moneyflow", "cyq_perf"}

    def check_statistical(
        self,
        dataset: str,
        current: pl.DataFrame,
        historical: pl.DataFrame | None = None,
        calendar: pl.DataFrame | None = None,
        reference: pl.DataFrame | None = None,
    ) -> DQResult:
        return DQResult(dataset=dataset, passed=True, issues=[])

    def check(
        self,
        df: pl.DataFrame,
        dataset: str,
        levels: list[Literal["l1", "l2"]] | None = None,
        context: dict[str, Any] | None = None,
    ) -> DQResult:
        raise AssertionError(f"capital 分支不得触发写入时 DQ 检查: {dataset}")

    def check_cross_source(
        self,
        primary: pl.DataFrame,
        secondary: pl.DataFrame,
        dataset: str,
        context: dict[str, Any] | None = None,
    ) -> DQResult:
        raise AssertionError(f"capital 分支不得触发跨源对比: {dataset}")

    def compare_cross_source(
        self,
        primary: pl.DataFrame,
        secondary: pl.DataFrame,
        dataset: str,
        context: dict[str, Any] | None = None,
    ) -> CrossSourceComparison:
        raise AssertionError(f"capital 分支不得触发跨源对比报告: {dataset}")


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
