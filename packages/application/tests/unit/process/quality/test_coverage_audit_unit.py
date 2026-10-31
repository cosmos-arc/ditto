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
from ditto_application.exceptions import AppError
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

    def get_stock_status_date_range(self) -> tuple[date, date] | None:
        # 状态数据集物理覆盖起点 = TUE（与状态帧首行一致）。
        return TUE, FRI

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
    """名册桩：find_securities 以 kwargs 形态挂在 MetadataService 门面层."""

    def __init__(self, asset_class: str) -> None:
        self.asset_class = asset_class
        self.seen_kwargs: dict[str, Any] = {}

    def find_securities(self, **kwargs: Any) -> pl.DataFrame:
        self.seen_kwargs = kwargs
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
        self._instrument = _InstrumentStub(asset_class)

    def find_securities(self, **kwargs: Any) -> pl.DataFrame:
        return self._instrument.find_securities(**kwargs)

    @property
    def instrument(self) -> _InstrumentStub:
        return self._instrument


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
        assert instrument.seen_kwargs == {"asset_class": "stock", "is_active": None}
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
        assert instrument.seen_kwargs == {"asset_class": "etf", "is_active": None}
        assert "etf_bars:2024-01-01:2024-01-05" in market.calls
        assert "fund_adj:2024-01-01:2024-01-05" in market.calls
        # WED 缺日线且无状态数据集 → 证据边界；fund_adj 缺证券 2 的 TUE → 缺口 1。
        assert report.session.gap_counts == {"no_status_dataset": 1}
        assert report.session.adj_factor_missing == 1
        assert not report.passed

    def test_report_dict_shape(self) -> None:
        service, _, _ = _service("stock")
        report = service.run(
            PriceCoverageAuditRequest("2024-01-01", "2024-01-05", "stock", "daily", 5)
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

            def get_stock_status_date_range(self) -> tuple[date, date] | None:
                return date(2024, 2, 1), date(2024, 2, 28)  # 状态期在窗口之后

        market = _NoStatusMarket()
        metadata = _MetadataStub(_days(), "stock")
        service = PriceCoverageAuditService(
            market=market,  # type: ignore[arg-type]
            metadata=metadata,  # type: ignore[arg-type]
        )
        report = service.run(
            PriceCoverageAuditRequest("2024-01-01", "2024-01-05", "stock")
        )
        # 状态数据集存在但覆盖在窗口之后 → 全部缺失归 pre_status_era 证据边界。
        assert report.session.gap_counts == {"pre_status_era": 1}
        assert report.session.limitation_gaps == 1
        assert report.session.passed

    def test_leading_status_hole_inside_window_fails_closed(self) -> None:
        """F1 回归：窗口内状态前导摄取空洞不得借 pre_status_era 豁免.

        数据集真实起点 MON（早于窗口内状态首行 WED）；MON 缺日线且缺
        状态行 → status_row_missing 失败，而非证据边界。
        """

        class _LeadingHoleMarket(_MarketStub):
            def get_stock_status(self, start: str, end: str) -> pl.DataFrame:
                rows = [
                    (1, WED, True),
                    (1, THU, False),
                    (1, FRI, False),
                    (2, WED, False),
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

            def get_stock_status_date_range(self) -> tuple[date, date] | None:
                return MON, FRI

            def _bars(self) -> pl.DataFrame:
                # 证券 1 缺 MON/TUE（状态洞）与 WED（停牌）；证券 2 完整。
                rows = [(1, THU), (1, FRI), (2, MON), (2, TUE)]
                return pl.DataFrame(
                    {
                        "instrument_id": [r[0] for r in rows],
                        "trade_date": [r[1] for r in rows],
                    },
                    schema={"instrument_id": pl.Int64, "trade_date": pl.Date},
                )

            def get_adj_factors(self, start: str, end: str) -> pl.DataFrame:
                return pl.DataFrame(
                    {
                        "instrument_id": [1, 1, 2, 2],
                        "trade_date": [THU, FRI, MON, TUE],
                    },
                    schema={"instrument_id": pl.Int64, "trade_date": pl.Date},
                )

        market = _LeadingHoleMarket()
        metadata = _MetadataStub(_days(), "stock")
        service = PriceCoverageAuditService(
            market=market,  # type: ignore[arg-type]
            metadata=metadata,  # type: ignore[arg-type]
        )
        report = service.run(
            PriceCoverageAuditRequest("2024-01-01", "2024-01-05", "stock")
        )
        # MON/TUE 早于窗口内状态首行 WED，但数据集起点是 MON → 状态洞失败；
        # WED 有停牌行 → suspended。
        assert report.session.gap_counts == {
            "status_row_missing": 2,
            "suspended": 1,
        }
        assert report.session.failure_gaps == 2
        assert not report.passed

    def test_schemaless_empty_frames_produce_report_not_crash(self) -> None:
        """F2 回归：空窗读取的无列空帧（bars/status/adj）补 schema 产出归因报告.

        数据集物理存在（覆盖在窗口之后）→ 全部期望会话缺失归 pre_status_era，
        而非在纯函数 select 上抛 ColumnNotFoundError。
        """

        class _SchemalessAllMarket(_NoStatusMarketSchemaless):
            def _bars(self) -> pl.DataFrame:
                return pl.DataFrame()

            def get_adj_factors(self, start: str, end: str) -> pl.DataFrame:
                return pl.DataFrame()

            def get_stock_status_date_range(self) -> tuple[date, date] | None:
                return date(2024, 2, 1), date(2024, 2, 28)

        market = _SchemalessAllMarket()
        metadata = _MetadataStub(_days(), "stock")
        service = PriceCoverageAuditService(
            market=market,  # type: ignore[arg-type]
            metadata=metadata,  # type: ignore[arg-type]
        )
        report = service.run(
            PriceCoverageAuditRequest("2024-01-01", "2024-01-05", "stock")
        )
        # 两名册成员全部期望会话缺失（7 会话），数据集在窗口之后 → 证据边界。
        assert report.session.expected_sessions == 7
        assert report.session.gap_counts == {"pre_status_era": 7}
        assert report.session.present_sessions == 0
        assert report.passed

    def test_rejects_unknown_asset_class_and_bad_window(self) -> None:
        service, _, _ = _service("stock")
        with pytest.raises(AppError, match="未知资产类"):
            service.run(PriceCoverageAuditRequest("2024-01-01", "2024-01-05", "index"))
        with pytest.raises(AppError, match="end_date"):
            service.run(PriceCoverageAuditRequest("2024-01-05", "2024-01-01", "stock"))


class _CapitalStub:
    """CapitalStore 桩：moneyflow 业务键帧（#625）."""

    def __init__(self, rows: list[tuple[int, date]] | None = None) -> None:
        self.calls: list[str] = []
        self._rows = rows

    def get_moneyflows(self, start: str, end: str) -> pl.DataFrame:
        self.calls.append(f"moneyflow:{start}:{end}")
        rows = (
            self._rows
            if self._rows is not None
            else [
                (1, MON),
                (1, THU),
                (1, FRI),
                (2, MON),
                (2, TUE),
            ]
        )
        return pl.DataFrame(
            {
                "instrument_id": [r[0] for r in rows],
                "trade_date": [r[1] for r in rows],
            },
            schema={"instrument_id": pl.Int64, "trade_date": pl.Date},
        )


class _FundShareMarketStub(_MarketStub):
    """fund_share 读口桩：ETF 份额业务键帧."""

    def __init__(self, frame: pl.DataFrame | None = None) -> None:
        super().__init__(asset_class="etf")
        self._frame = frame
        self.fund_share_calls: list[str] = []

    def get_fund_share(self, start: str, end: str) -> pl.DataFrame | None:
        self.fund_share_calls.append(f"fund_share:{start}:{end}")
        if self._frame is None:
            return pl.DataFrame(
                {
                    "instrument_id": [1, 2, 2],
                    "trade_date": [MON, MON, TUE],
                },
                schema={"instrument_id": pl.Int64, "trade_date": pl.Date},
            )
        return self._frame


class TestCapitalDatasetAudit:
    """#625 资金面数据集档位：moneyflow 复用 stock 网格，fund_share 落证据边界."""

    def test_moneyflow_reuses_stock_grid_and_status_attribution(self) -> None:
        market = _MarketStub(asset_class="stock")
        metadata = _MetadataStub(_days(), "stock")
        capital = _CapitalStub()
        service = PriceCoverageAuditService(
            market=market,  # type: ignore[arg-type]
            metadata=metadata,  # type: ignore[arg-type]
            capital=capital,  # type: ignore[arg-type]
        )

        report = service.run(
            PriceCoverageAuditRequest(
                "2024-01-01", "2024-01-05", "stock", dataset="moneyflow"
            )
        )

        # 证券 1 缺 TUE（未停牌 → 失败缺口）与 WED（停牌 → 正常缺席）
        assert report.session.gap_counts == {
            "status_trading_no_bar": 1,
            "suspended": 1,
        }
        # 资金流档位不做复权因子在场核验
        assert report.session.adj_factor_checked is False
        assert report.dataset == "moneyflow"
        assert capital.calls == ["moneyflow:2024-01-01:2024-01-05"]
        # 复用价格档位的读口不被触碰
        assert "stock_bars:2024-01-01:2024-01-05" not in market.calls

    def test_moneyflow_without_capital_service_fails_loud(self) -> None:
        service, _, _ = _service("stock")
        with pytest.raises(AppError, match="capital"):
            service.run(
                PriceCoverageAuditRequest(
                    "2024-01-01", "2024-01-05", "stock", dataset="moneyflow"
                )
            )

    def test_fund_share_gaps_land_in_no_status_limitation(self) -> None:
        market = _FundShareMarketStub()
        metadata = _MetadataStub(_days(), "etf")
        service = PriceCoverageAuditService(
            market=market,  # type: ignore[arg-type]
            metadata=metadata,  # type: ignore[arg-type]
        )

        report = service.run(
            PriceCoverageAuditRequest(
                "2024-01-01", "2024-01-05", "etf", dataset="fund_share"
            )
        )

        # 证券 1（未退市）期望 5 会话仅 1 在场；ETF 无状态数据集 → 全部
        # 落 no_status_dataset 证据边界（受限非失败）。
        assert report.session.expected_sessions == 7
        assert report.session.gap_counts == {"no_status_dataset": 4}
        assert report.session.limitation_gaps == 4
        assert report.session.failure_gaps == 0
        assert report.passed
        assert market.fund_share_calls == ["fund_share:2024-01-01:2024-01-05"]

    def test_fund_share_port_not_assembled_fails_loud(self) -> None:
        class _NoFundShareMarket(_MarketStub):
            def get_fund_share(self, start: str, end: str) -> pl.DataFrame | None:
                return None

        market = _NoFundShareMarket(asset_class="etf")
        metadata = _MetadataStub(_days(), "etf")
        service = PriceCoverageAuditService(
            market=market,  # type: ignore[arg-type]
            metadata=metadata,  # type: ignore[arg-type]
        )
        with pytest.raises(AppError, match="fund_share 读取端口未装配"):
            service.run(
                PriceCoverageAuditRequest(
                    "2024-01-01", "2024-01-05", "etf", dataset="fund_share"
                )
            )

    def test_dataset_asset_class_combination_rejected(self) -> None:
        service, _, _ = _service("stock")
        with pytest.raises(AppError, match="不支持资产类"):
            service.run(
                PriceCoverageAuditRequest(
                    "2024-01-01", "2024-01-05", "etf", dataset="moneyflow"
                )
            )
        with pytest.raises(AppError, match="未知数据集档位"):
            service.run(
                PriceCoverageAuditRequest(
                    "2024-01-01", "2024-01-05", "stock", dataset="margin_trading"
                )
            )

    def test_daily_dataset_default_unchanged(self) -> None:
        market = _MarketStub(asset_class="stock")
        metadata = _MetadataStub(_days(), "stock")
        service = PriceCoverageAuditService(
            market=market,  # type: ignore[arg-type]
            metadata=metadata,  # type: ignore[arg-type]
        )
        report = service.run(
            PriceCoverageAuditRequest("2024-01-01", "2024-01-05", "stock")
        )
        assert report.dataset == "daily"
        assert report.to_dict()["dataset"] == "daily"
        # 价格档位保持复权因子核验
        assert report.session.adj_factor_checked is True
