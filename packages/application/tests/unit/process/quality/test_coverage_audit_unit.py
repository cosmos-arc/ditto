"""PriceCoverageAuditService 编排单测（#624 / #621 P2）.

stub MarketService/MetadataService 注入合成物理帧，验证：
- 名册取 is_active=None 全量（退市保留，幸存者偏差防护）；
- 状态期起点由窗口内状态帧推导；
- ETF 路径无状态数据集（no_status_dataset 证据边界）+ fund_adj 检查接线；
- 报告 to_dict 形状与 top-N 明细。
"""

from datetime import date
from typing import Any

import polars as pl
import pytest
from ditto_application.processes.quality.coverage_audit import (
    PriceCoverageAuditRequest,
    PriceCoverageAuditService,
)

MON, TUE, WED, THU, FRI = (
    date(2024, 1, 1),
    date(2024, 1, 2),
    date(2024, 1, 3),
    date(2024, 1, 4),
    date(2024, 1, 5),
)


class _MarketStub:
    def __init__(self, *, asset_class: str = "stock") -> None:
        self.asset_class = asset_class
        self.calls: list[str] = []

    def _bars(self) -> pl.DataFrame:
        # 证券 1 活跃（缺 WED）；证券 2 于 TUE 退市（生命周期仅 MON/TUE）。
        rows = [
            (1, MON),
            (1, TUE),
            (1, THU),
            (1, FRI),
            (2, MON),
            (2, TUE),
        ]
        return pl.DataFrame(
            {
                "instrument_id": [r[0] for r in rows],
                "trade_date": [r[1] for r in rows],
            },
            schema={"instrument_id": pl.Int64, "trade_date": pl.Date},
        )

    def get_stock_bars(self, start: str, end: str) -> pl.DataFrame:
        self.calls.append(f"stock_bars:{start}:{end}")
        return self._bars()

    def get_etf_bars(self, start: str, end: str, adj: str = "none") -> pl.DataFrame:
        assert adj == "none"
        self.calls.append(f"etf_bars:{start}:{end}")
        return self._bars()

    def get_stock_status(self, start: str, end: str) -> pl.DataFrame:
        # 状态自 TUE 起（era 推导 = TUE）；证券 1 的 WED 停牌。
        self.calls.append(f"stock_status:{start}:{end}")
        rows = [
            (1, TUE, False),
            (1, WED, True),
            (1, THU, False),
            (1, FRI, False),
            (2, TUE, False),
        ]
        return pl.DataFrame(
            {
                "instrument_id": [r[0] for r in rows],
                "trade_date": [r[1] for r in rows],
                "is_suspended": [r[2] for r in rows],
            },
            schema={
                "instrument_id": pl.Int64,
                "trade_date": pl.Date,
                "is_suspended": pl.Boolean,
            },
        )

    def get_adj_factors(self, start: str, end: str) -> pl.DataFrame:
        # 覆盖全部 6 个日线会话。
        return pl.DataFrame(
            {
                "instrument_id": [1, 1, 1, 1, 2, 2],
                "trade_date": [MON, TUE, THU, FRI, MON, TUE],
            },
            schema={"instrument_id": pl.Int64, "trade_date": pl.Date},
        )

    def get_fund_adj(self, start: str, end: str) -> pl.DataFrame | None:
        self.calls.append(f"fund_adj:{start}:{end}")
        # 故意缺证券 2 的 TUE → adj_factor_missing = 1。
        return pl.DataFrame(
            {
                "instrument_id": [1, 1, 1, 1, 2],
                "trade_date": [MON, TUE, THU, FRI, MON],
            },
            schema={"instrument_id": pl.Int64, "trade_date": pl.Date},
        )


class _InstrumentStub:
    def __init__(self, asset_class: str) -> None:
        self.asset_class = asset_class
        self.seen_query: Any = None

    def find_securities(self, query: Any) -> pl.DataFrame:
        self.seen_query = query
        return pl.DataFrame(
            {
                "instrument_id": [1, 2],
                "source_ticker": ["000001.SZ", "000002.SZ"],
                "list_date": ["2023-06-01", "2023-06-01"],
                "delist_date": [None, "2024-01-02"],
            },
            schema={
                "instrument_id": pl.Int64,
                "source_ticker": pl.String,
                "list_date": pl.String,
                "delist_date": pl.String,
            },
        )


class _CalendarStub:
    def __init__(self, days: list[str]) -> None:
        self.days = days

    def list_trading_days(
        self, start: str, end: str, only_open: bool = True
    ) -> list[str]:
        return self.days


class _NoStatusMarketSchemaless(_MarketStub):
    def get_stock_status(self, start: str, end: str) -> pl.DataFrame:
        return pl.DataFrame()


class _MetadataStub:
    def __init__(self, days: list[str], asset_class: str) -> None:
        self.calendar = _CalendarStub(days)
        self.instrument = _InstrumentStub(asset_class)


def _days() -> list[str]:
    return [d.isoformat() for d in (MON, TUE, WED, THU, FRI)]


def _service(
    asset_class: str = "stock",
) -> tuple[PriceCoverageAuditService, _MarketStub, _InstrumentStub]:
    market = _MarketStub(asset_class=asset_class)
    metadata = _MetadataStub(_days(), asset_class)
    service = PriceCoverageAuditService(
        market=market,  # type: ignore[arg-type]
        metadata=metadata,  # type: ignore[arg-type]
    )
    return service, market, metadata.instrument


class TestPriceCoverageAuditService:
    def test_stock_audit_attributes_suspension_and_passes(self) -> None:
        service, market, instrument = _service("stock")
        report = service.run(
            PriceCoverageAuditRequest("2024-01-01", "2024-01-05", "stock")
        )
        # 名册必须取全量（is_active=None）——退市证券保留。
        assert instrument.seen_query.asset_class == "stock"
        assert instrument.seen_query.is_active is None
        # 状态期起点由窗口内状态帧最早会话推导（TUE）。
        assert "stock_status:2024-01-01:2024-01-05" in market.calls
        assert report.session.gap_counts == {"suspended": 1}
        assert report.session.adj_factor_missing == 0
        assert report.passed

    def test_pre_era_monday_gap_lands_in_limitation(self) -> None:
        """MON 早于状态期起点（TUE）→ 缺日线时归因 pre_status_era 而非失败."""

        class _PreEraMarket(_MarketStub):
            def _bars(self) -> pl.DataFrame:
                # 证券 1 缺 MON（期前）与 WED（停牌）；证券 2 生命周期完整。
                rows = [(1, TUE), (1, THU), (1, FRI), (2, MON), (2, TUE)]
                return pl.DataFrame(
                    {
                        "instrument_id": [r[0] for r in rows],
                        "trade_date": [r[1] for r in rows],
                    },
                    schema={"instrument_id": pl.Int64, "trade_date": pl.Date},
                )

        market = _PreEraMarket()
        metadata = _MetadataStub(_days(), "stock")
        service = PriceCoverageAuditService(
            market=market,  # type: ignore[arg-type]
            metadata=metadata,  # type: ignore[arg-type]
        )
        report = service.run(
            PriceCoverageAuditRequest("2024-01-01", "2024-01-05", "stock")
        )
        # WED（状态期后，停牌行）归因 suspended；MON（状态期前）归因 pre_status_era。
        assert report.session.gap_counts == {"suspended": 1, "pre_status_era": 1}
        assert report.passed

    def test_etf_path_uses_no_status_dataset_and_checks_fund_adj(self) -> None:
        service, market, instrument = _service("etf")
        report = service.run(
            PriceCoverageAuditRequest("2024-01-01", "2024-01-05", "etf")
        )
        assert instrument.seen_query.asset_class == "etf"
        assert instrument.seen_query.is_active is None
        assert "etf_bars:2024-01-01:2024-01-05" in market.calls
        assert "fund_adj:2024-01-01:2024-01-05" in market.calls
        # WED 缺日线且无状态数据集 → 证据边界；fund_adj 缺证券 2 的 TUE → 缺口 1。
        assert report.session.gap_counts == {"no_status_dataset": 1}
        assert report.session.adj_factor_missing == 1
        assert not report.passed

    def test_report_dict_shape(self) -> None:
        service, _, _ = _service("stock")
        report = service.run(
            PriceCoverageAuditRequest("2024-01-01", "2024-01-05", "stock", 5)
        )
        payload = report.to_dict()
        assert payload["asset_class"] == "stock"
        assert payload["window"] == ["2024-01-01", "2024-01-05"]
        assert payload["session"]["expected_sessions"] == 7
        assert payload["calendar"]["trading_days"] == 5
        assert payload["gap_counts"] == {"suspended": 1}
        assert payload["passed"] is True
        # 样本含 ticker 映射。
        assert payload["gap_samples"][0]["ticker"] == "000001.SZ"
        assert payload["gap_samples"][0]["kind"] == "suspended"

    def test_pre_era_stock_window_attributed_to_pre_status_era(self) -> None:
        """窗口完全早于状态期（股票）→ pre_status_era，不得误标 no_status_dataset."""

        class _NoStatusMarket(_MarketStub):
            def get_stock_status(self, start: str, end: str) -> pl.DataFrame:
                return pl.DataFrame(
                    schema={
                        "instrument_id": pl.Int64,
                        "trade_date": pl.Date,
                        "is_suspended": pl.Boolean,
                    }
                )

        market = _NoStatusMarket()
        metadata = _MetadataStub(_days(), "stock")
        service = PriceCoverageAuditService(
            market=market,  # type: ignore[arg-type]
            metadata=metadata,  # type: ignore[arg-type]
        )
        report = service.run(
            PriceCoverageAuditRequest("2024-01-01", "2024-01-05", "stock")
        )
        # 状态数据集存在但窗口内零行 → 全部缺失归 pre_status_era 证据边界。
        assert report.session.gap_counts == {"pre_status_era": 1}
        assert report.session.limitation_gaps == 1
        assert report.session.passed

    def test_statusless_window_handles_schemaless_empty_frame(self) -> None:
        """空窗读取返回无列空帧时服务补 schema，不因 select 失败."""

        market = _NoStatusMarketSchemaless()
        metadata = _MetadataStub(_days(), "stock")
        service = PriceCoverageAuditService(
            market=market,  # type: ignore[arg-type]
            metadata=metadata,  # type: ignore[arg-type]
        )
        report = service.run(
            PriceCoverageAuditRequest("2024-01-01", "2024-01-05", "stock")
        )
        assert report.session.gap_counts == {"pre_status_era": 1}

    def test_rejects_unknown_asset_class_and_bad_window(self) -> None:
        service, _, _ = _service("stock")
        with pytest.raises(ValueError, match="未知资产类"):
            service.run(PriceCoverageAuditRequest("2024-01-01", "2024-01-05", "index"))
        with pytest.raises(ValueError, match="end_date"):
            service.run(PriceCoverageAuditRequest("2024-01-05", "2024-01-01", "stock"))
