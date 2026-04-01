"""Tests for stock_sector_rotation strategy template.

Covers StockSectorRotationConfig, validate_config, get_param_constraints,
SectorSignalStage, SectorScoreAndSelectStage, IntraSectorSelectStage,
SectorWeightStage, FinalStockFilterStage, build_stock_sector_rotation_pipeline,
and E2E pipeline execution.
"""

from __future__ import annotations

import polars as pl
import pytest
from ditto_engine.portfolio.constraints import (
    ConstraintChecker,
    ConstraintStage,
    MaxWeightConstraint,
)
from ditto_engine.strategy.builtins.filtering import RiskLockFilter
from ditto_engine.strategy.context import StrategyContext
from ditto_engine.strategy.pipeline import StrategyInputBundle
from ditto_engine.strategy.specs import ParamConstraint
from ditto_engine.strategy.templates.stock_sector_rotation import (
    FinalStockFilterStage,
    IntraSectorSelectStage,
    SectorScoreAndSelectStage,
    SectorSignalStage,
    SectorWeightStage,
    StockSectorRotationConfig,
    build_stock_sector_rotation_pipeline,
    get_param_constraints,
    validate_config,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SECTOR_ETFS = ["SECTOR-FIN", "SECTOR-TECH", "SECTOR-HEA"]
STOCKS = [
    ("STOCK-FIN-001", "SECTOR-FIN"),
    ("STOCK-FIN-002", "SECTOR-FIN"),
    ("STOCK-FIN-003", "SECTOR-FIN"),
    ("STOCK-TECH-001", "SECTOR-TECH"),
    ("STOCK-TECH-002", "SECTOR-TECH"),
    ("STOCK-TECH-003", "SECTOR-TECH"),
    ("STOCK-HEA-001", "SECTOR-HEA"),
    ("STOCK-HEA-002", "SECTOR-HEA"),
    ("STOCK-HEA-003", "SECTOR-HEA"),
]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def empty_context() -> StrategyContext:
    return StrategyContext()


@pytest.fixture
def sector_rotation_frame() -> pl.DataFrame:
    """
    12-row frame: 3 sector ETFs + 9 stocks.

    signal_value:
      SECTOR-FIN=0.05, SECTOR-TECH=0.08, SECTOR-HEA=0.03
      STOCK-FIN-001=0.04, STOCK-FIN-002=0.06, STOCK-FIN-003=0.01
      STOCK-TECH-001=0.07, STOCK-TECH-002=0.09, STOCK-TECH-003=0.02
      STOCK-HEA-001=0.03, STOCK-HEA-002=0.01, STOCK-HEA-003=0.02
    """
    instrument_ids = SECTOR_ETFS + [s[0] for s in STOCKS]
    sector_ids = SECTOR_ETFS + [s[1] for s in STOCKS]
    is_sectors = [True] * 3 + [False] * 9
    signals = [
        # Sector ETFs
        0.05,  # SECTOR-FIN
        0.08,  # SECTOR-TECH (highest)
        0.03,  # SECTOR-HEA
        # FIN stocks
        0.04,
        0.06,
        0.01,
        # TECH stocks
        0.07,
        0.09,
        0.02,
        # HEA stocks
        0.03,
        0.01,
        0.02,
    ]
    return pl.DataFrame(
        {
            "instrument_id": instrument_ids,
            "sector_id": sector_ids,
            "is_sector": is_sectors,
            "signal_value": signals,
        },
    )


@pytest.fixture
def sector_rotation_bundle(sector_rotation_frame: pl.DataFrame) -> StrategyInputBundle:
    """Build StrategyInputBundle with sector ETFs + stocks."""
    instruments = sector_rotation_frame.select("instrument_id")
    signal_values = sector_rotation_frame.select(
        "instrument_id",
        "sector_id",
        "is_sector",
        "signal_value",
    )
    market_data = sector_rotation_frame.select(
        "instrument_id",
        pl.lit(10.0).alias("close"),
        pl.lit(10.0).alias("open"),
        pl.lit(10.5).alias("high"),
        pl.lit(9.5).alias("low"),
        pl.lit(1_000_000.0).alias("volume"),
    )
    return StrategyInputBundle(
        trade_date="2026-03-23",
        strategy_id="test_sector_rotation",
        run_id="run_001",
        instruments=instruments,
        market_data=market_data,
        signal_values=signal_values,
    )


# ---------------------------------------------------------------------------
# StockSectorRotationConfig
# ---------------------------------------------------------------------------


class TestStockSectorRotationConfig:
    def test_default_values(self) -> None:
        """默认配置值正确。"""
        config = StockSectorRotationConfig()
        assert config.sector_signal == "signal_value"
        assert config.stock_signal == "signal_value"
        assert config.top_sectors == 3
        assert config.stocks_per_sector == 3
        assert config.sector_weight_method == "equal_weight"
        assert config.stock_weight_method == "equal_weight"
        assert config.max_weight == 0.15
        assert config.cash_target == 0.0
        assert config.rebalance_freq == "daily"

    def test_frozen(self) -> None:
        """Config 是 frozen dataclass，不可变。"""
        config = StockSectorRotationConfig()
        with pytest.raises(AttributeError):
            config.top_sectors = 5  # type: ignore[misc]


# ---------------------------------------------------------------------------
# validate_config
# ---------------------------------------------------------------------------


class TestValidateConfig:
    def test_valid_config_passes(self) -> None:
        """合法配置不抛异常。"""
        config = StockSectorRotationConfig()
        validate_config(config)  # Should not raise

    def test_invalid_top_sectors_raises(self) -> None:
        """top_sectors < 1 时抛异常。"""
        config = StockSectorRotationConfig(top_sectors=0)
        with pytest.raises(ValueError, match="top_sectors"):
            validate_config(config)

    def test_invalid_stocks_per_sector_raises(self) -> None:
        """stocks_per_sector < 1 时抛异常。"""
        config = StockSectorRotationConfig(stocks_per_sector=0)
        with pytest.raises(ValueError, match="stocks_per_sector"):
            validate_config(config)

    def test_invalid_max_weight_zero_raises(self) -> None:
        """max_weight <= 0 时抛异常。"""
        config = StockSectorRotationConfig(max_weight=0.0)
        with pytest.raises(ValueError, match="max_weight"):
            validate_config(config)

    def test_invalid_max_weight_over_one_raises(self) -> None:
        """max_weight > 1 时抛异常。"""
        config = StockSectorRotationConfig(max_weight=1.5)
        with pytest.raises(ValueError, match="max_weight"):
            validate_config(config)

    def test_invalid_cash_target_raises(self) -> None:
        """cash_target >= 1 时抛异常。"""
        config = StockSectorRotationConfig(cash_target=1.0)
        with pytest.raises(ValueError, match="cash_target"):
            validate_config(config)

    def test_invalid_sector_weight_method_raises(self) -> None:
        """非法 sector_weight_method 抛异常。"""
        config = StockSectorRotationConfig(sector_weight_method="inverse_vol")
        with pytest.raises(ValueError, match="sector_weight_method"):
            validate_config(config)

    def test_invalid_stock_weight_method_raises(self) -> None:
        """非法 stock_weight_method 抛异常。"""
        config = StockSectorRotationConfig(stock_weight_method="score_weight")
        with pytest.raises(ValueError, match="stock_weight_method"):
            validate_config(config)

    def test_invalid_rebalance_freq_raises(self) -> None:
        """非法 rebalance_freq 抛异常。"""
        config = StockSectorRotationConfig(rebalance_freq="quarterly")
        with pytest.raises(ValueError, match="rebalance_freq"):
            validate_config(config)


# ---------------------------------------------------------------------------
# get_param_constraints
# ---------------------------------------------------------------------------


class TestGetParamConstraints:
    def test_returns_constraints(self) -> None:
        """返回非空的 ParamConstraint 元组。"""
        constraints = get_param_constraints()
        assert isinstance(constraints, tuple)
        assert len(constraints) >= 5
        for c in constraints:
            assert isinstance(c, ParamConstraint)


# ---------------------------------------------------------------------------
# SectorSignalStage
# ---------------------------------------------------------------------------


class TestSectorSignalStage:
    def test_extracts_sector_signals(
        self,
        empty_context: StrategyContext,
        sector_rotation_frame: pl.DataFrame,
    ) -> None:
        """行业 ETF 行的 sector_signal = signal_value，个股行为 null。"""
        stage = SectorSignalStage()
        result = stage.process(sector_rotation_frame, empty_context)

        # Sector ETFs should have sector_signal = their signal_value
        sector_rows = result.filter(pl.col("is_sector")).sort("instrument_id")
        # Sorted alphabetically: FIN(0.05), HEA(0.03), TECH(0.08)
        expected = pytest.approx([0.05, 0.03, 0.08])
        assert sector_rows["sector_signal"].to_list() == expected

        # Stock rows should have null sector_signal
        stock_rows = result.filter(~pl.col("is_sector"))
        assert stock_rows["sector_signal"].null_count() == 9

    def test_custom_signal_column(
        self,
        empty_context: StrategyContext,
    ) -> None:
        """使用自定义信号列名。"""
        frame = pl.DataFrame(
            {
                "instrument_id": ["SECTOR-A", "STOCK-1"],
                "sector_id": ["SECTOR-A", "SECTOR-A"],
                "is_sector": [True, False],
                "momentum": [0.10, 0.05],
            },
        )
        stage = SectorSignalStage(signal_column="momentum")
        result = stage.process(frame, empty_context)
        assert result["sector_signal"][0] == 0.10
        assert result["sector_signal"][1] is None

    def test_empty_frame(
        self,
        empty_context: StrategyContext,
    ) -> None:
        """空 frame 返回空 frame + sector_signal 列。"""
        frame = pl.DataFrame(
            {
                "instrument_id": [],
                "sector_id": [],
                "is_sector": [],
            },
            schema={
                "instrument_id": pl.Utf8,
                "sector_id": pl.Utf8,
                "is_sector": pl.Boolean,
            },
        )
        stage = SectorSignalStage()
        result = stage.process(frame, empty_context)
        assert result.is_empty()
        assert "sector_signal" in result.columns

    def test_missing_signal_column(
        self,
        empty_context: StrategyContext,
    ) -> None:
        """signal_column 不存在时 sector_signal 全 null。"""
        frame = pl.DataFrame(
            {
                "instrument_id": ["SECTOR-A"],
                "sector_id": ["SECTOR-A"],
                "is_sector": [True],
            },
        )
        stage = SectorSignalStage(signal_column="nonexistent")
        result = stage.process(frame, empty_context)
        assert result["sector_signal"][0] is None

    def test_frozen(self) -> None:
        """SectorSignalStage 是 frozen dataclass。"""
        stage = SectorSignalStage()
        with pytest.raises(AttributeError):
            stage.signal_column = "x"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# SectorScoreAndSelectStage
# ---------------------------------------------------------------------------


class TestSectorScoreAndSelectStage:
    def _make_frame_with_sector_signal(
        self,
        sector_signals: dict[str, float],
    ) -> pl.DataFrame:
        """构建带 sector_signal 列的测试 frame。"""
        rows = []
        # Add sector ETF rows
        for sid, sig in sector_signals.items():
            rows.append(
                {
                    "instrument_id": sid,
                    "sector_id": sid,
                    "is_sector": True,
                    "sector_signal": sig,
                }
            )
        # Add 2 dummy stocks per sector
        for sid in sector_signals:
            for j in range(1, 3):
                rows.append(
                    {
                        "instrument_id": f"STOCK-{sid}-{j}",
                        "sector_id": sid,
                        "is_sector": False,
                        "sector_signal": None,
                    }
                )
        return pl.DataFrame(rows)

    def test_selects_top_k_sectors(
        self,
        empty_context: StrategyContext,
    ) -> None:
        """选取 Top K 行业并标记关联个股。"""
        frame = self._make_frame_with_sector_signal(
            {
                "SECTOR-FIN": 0.05,
                "SECTOR-TECH": 0.08,
                "SECTOR-HEA": 0.03,
            }
        )
        stage = SectorScoreAndSelectStage(top_k=2)
        result = stage.process(frame, empty_context)

        # TECH (0.08) and FIN (0.05) should be selected
        selected_sector_ids = (
            result.filter(pl.col("selected_sector") & pl.col("is_sector"))
            .select("instrument_id")
            .to_series()
            .to_list()
        )
        assert "SECTOR-TECH" in selected_sector_ids
        assert "SECTOR-FIN" in selected_sector_ids
        assert "SECTOR-HEA" not in selected_sector_ids

        # Stocks in TECH and FIN should be selected
        selected_stocks = (
            result.filter(pl.col("selected_sector") & (~pl.col("is_sector")))
            .select("instrument_id")
            .to_series()
            .to_list()
        )
        assert "STOCK-SECTOR-TECH-1" in selected_stocks
        assert "STOCK-SECTOR-FIN-1" in selected_stocks
        assert "STOCK-SECTOR-HEA-1" not in selected_stocks

    def test_top_k_exceeds_sector_count(
        self,
        empty_context: StrategyContext,
    ) -> None:
        """top_k >= 行业数量时全部选中。"""
        frame = self._make_frame_with_sector_signal(
            {
                "SECTOR-FIN": 0.05,
                "SECTOR-TECH": 0.08,
            }
        )
        stage = SectorScoreAndSelectStage(top_k=10)
        result = stage.process(frame, empty_context)

        # All sectors and all stocks should be selected
        assert result.filter(pl.col("selected_sector")).height == frame.height

    def test_empty_frame(self, empty_context: StrategyContext) -> None:
        """空 frame 返回空 frame + selected_sector 列。"""
        frame = pl.DataFrame(
            {
                "instrument_id": [],
                "sector_id": [],
                "is_sector": [],
                "sector_signal": [],
            },
            schema={
                "instrument_id": pl.Utf8,
                "sector_id": pl.Utf8,
                "is_sector": pl.Boolean,
                "sector_signal": pl.Float64,
            },
        )
        stage = SectorScoreAndSelectStage(top_k=2)
        result = stage.process(frame, empty_context)
        assert result.is_empty()
        assert "selected_sector" in result.columns

    def test_no_sector_rows(self, empty_context: StrategyContext) -> None:
        """无行业 ETF 行时 selected_sector 全 False。"""
        frame = pl.DataFrame(
            {
                "instrument_id": ["STOCK-1", "STOCK-2"],
                "sector_id": ["SECTOR-A", "SECTOR-A"],
                "is_sector": [False, False],
                "sector_signal": [None, None],
            },
        )
        stage = SectorScoreAndSelectStage(top_k=2)
        result = stage.process(frame, empty_context)
        assert result["selected_sector"].to_list() == [False, False]

    def test_frozen(self) -> None:
        """SectorScoreAndSelectStage 是 frozen dataclass。"""
        stage = SectorScoreAndSelectStage()
        with pytest.raises(AttributeError):
            stage.top_k = 5  # type: ignore[misc]


# ---------------------------------------------------------------------------
# IntraSectorSelectStage
# ---------------------------------------------------------------------------


class TestIntraSectorSelectStage:
    def _make_frame_with_selection(
        self,
        stocks_per_sector: dict[str, list[tuple[str, float]]],
    ) -> pl.DataFrame:
        """构建带 selected_sector 和 signal_value 列的测试 frame。"""
        rows = []
        for sector_id, stocks in stocks_per_sector.items():
            # Sector ETF row
            rows.append(
                {
                    "instrument_id": sector_id,
                    "sector_id": sector_id,
                    "is_sector": True,
                    "selected_sector": True,
                    "signal_value": 0.0,
                }
            )
            # Stock rows
            for stock_id, sig in stocks:
                rows.append(
                    {
                        "instrument_id": stock_id,
                        "sector_id": sector_id,
                        "is_sector": False,
                        "selected_sector": True,
                        "signal_value": sig,
                    }
                )
        return pl.DataFrame(rows)

    def test_selects_top_k_per_sector(
        self,
        empty_context: StrategyContext,
    ) -> None:
        """每个选中行业内选 Top K 个股。"""
        frame = self._make_frame_with_selection(
            {
                "SECTOR-FIN": [
                    ("FIN-001", 0.06),
                    ("FIN-002", 0.04),
                    ("FIN-003", 0.01),
                ],
                "SECTOR-TECH": [
                    ("TECH-001", 0.09),
                    ("TECH-002", 0.07),
                    ("TECH-003", 0.02),
                ],
            }
        )
        stage = IntraSectorSelectStage(stocks_per_sector=2)
        result = stage.process(frame, empty_context)

        selected_stocks = (
            result.filter(pl.col("intra_selected"))
            .select("instrument_id")
            .to_series()
            .to_list()
        )

        # FIN: top 2 by signal → FIN-001 (0.06), FIN-002 (0.04)
        assert "FIN-001" in selected_stocks
        assert "FIN-002" in selected_stocks
        assert "FIN-003" not in selected_stocks

        # TECH: top 2 by signal → TECH-001 (0.09), TECH-002 (0.07)
        assert "TECH-001" in selected_stocks
        assert "TECH-002" in selected_stocks
        assert "TECH-003" not in selected_stocks

    def test_sector_etf_not_selected(
        self,
        empty_context: StrategyContext,
    ) -> None:
        """行业 ETF 行不会被标记为 intra_selected。"""
        frame = self._make_frame_with_selection(
            {
                "SECTOR-FIN": [("FIN-001", 0.06)],
            }
        )
        stage = IntraSectorSelectStage(stocks_per_sector=1)
        result = stage.process(frame, empty_context)
        assert result.filter(pl.col("is_sector") & pl.col("intra_selected")).is_empty()

    def test_unselected_sector_stocks_not_selected(
        self,
        empty_context: StrategyContext,
    ) -> None:
        """未选中行业内的个股不会被标记。"""
        frame = pl.DataFrame(
            {
                "instrument_id": ["STOCK-1"],
                "sector_id": ["SECTOR-A"],
                "is_sector": [False],
                "selected_sector": [False],
                "signal_value": [0.99],
            },
        )
        stage = IntraSectorSelectStage(stocks_per_sector=1)
        result = stage.process(frame, empty_context)
        assert result["intra_selected"].to_list() == [False]

    def test_empty_frame(self, empty_context: StrategyContext) -> None:
        """空 frame 返回空 frame + intra_selected 列。"""
        frame = pl.DataFrame(
            {
                "instrument_id": [],
                "sector_id": [],
                "is_sector": [],
                "selected_sector": [],
                "signal_value": [],
            },
            schema={
                "instrument_id": pl.Utf8,
                "sector_id": pl.Utf8,
                "is_sector": pl.Boolean,
                "selected_sector": pl.Boolean,
                "signal_value": pl.Float64,
            },
        )
        stage = IntraSectorSelectStage(stocks_per_sector=1)
        result = stage.process(frame, empty_context)
        assert result.is_empty()
        assert "intra_selected" in result.columns

    def test_missing_signal_column(self, empty_context: StrategyContext) -> None:
        """signal_column 不存在时 intra_selected 全 False。"""
        frame = pl.DataFrame(
            {
                "instrument_id": ["STOCK-1"],
                "sector_id": ["SECTOR-A"],
                "is_sector": [False],
                "selected_sector": [True],
            },
        )
        stage = IntraSectorSelectStage(stocks_per_sector=1)
        result = stage.process(frame, empty_context)
        assert result["intra_selected"].to_list() == [False]

    def test_stocks_per_sector_greater_than_available(
        self,
        empty_context: StrategyContext,
    ) -> None:
        """stocks_per_sector > 行业内个股数时全部选中。"""
        frame = self._make_frame_with_selection(
            {
                "SECTOR-FIN": [("FIN-001", 0.06)],
            }
        )
        stage = IntraSectorSelectStage(stocks_per_sector=5)
        result = stage.process(frame, empty_context)
        assert result.filter(pl.col("intra_selected")).height == 1

    def test_frozen(self) -> None:
        """IntraSectorSelectStage 是 frozen dataclass。"""
        stage = IntraSectorSelectStage()
        with pytest.raises(AttributeError):
            stage.stocks_per_sector = 5  # type: ignore[misc]


# ---------------------------------------------------------------------------
# SectorWeightStage
# ---------------------------------------------------------------------------


class TestSectorWeightStage:
    def _make_weighted_frame(
        self,
        sectors: list[str],
        stocks_per_sector: int = 3,
        signal_values: list[float] | None = None,
    ) -> pl.DataFrame:
        """构建带 intra_selected 列的测试 frame。"""
        rows = []
        for sector in sectors:
            rows.append(
                {
                    "instrument_id": sector,
                    "sector_id": sector,
                    "is_sector": True,
                    "intra_selected": False,
                }
            )
            for j in range(stocks_per_sector):
                rows.append(
                    {
                        "instrument_id": f"STOCK-{sector}-{j}",
                        "sector_id": sector,
                        "is_sector": False,
                        "intra_selected": True,
                    }
                )
        return pl.DataFrame(rows)

    def test_equal_sector_weight_equal_stock_weight(
        self,
        empty_context: StrategyContext,
    ) -> None:
        """2 行业各 3 股 → 行业权重 0.5，个股权重 0.5/3。"""
        frame = self._make_weighted_frame(
            sectors=["SECTOR-A", "SECTOR-B"],
            stocks_per_sector=3,
        )
        stage = SectorWeightStage(cash_target=0.0)
        result = stage.process(frame, empty_context)

        # Selected stocks should have weight = 0.5/3 ≈ 0.1667
        stock_weights = (
            result.filter(pl.col("intra_selected"))
            .select("weight")
            .to_series()
            .to_list()
        )
        for w in stock_weights:
            assert w == pytest.approx(1.0 / 6.0)

        # Sector ETFs should have weight = 0
        sector_weights = (
            result.filter(pl.col("is_sector")).select("weight").to_series().to_list()
        )
        assert all(w == 0.0 for w in sector_weights)

    def test_cash_target_reduces_weight(
        self,
        empty_context: StrategyContext,
    ) -> None:
        """cash_target=0.1 时总可投资 = 0.9。"""
        frame = self._make_weighted_frame(
            sectors=["SECTOR-A", "SECTOR-B"],
            stocks_per_sector=3,
        )
        stage = SectorWeightStage(cash_target=0.1)
        result = stage.process(frame, empty_context)

        stock_weights = (
            result.filter(pl.col("intra_selected"))
            .select("weight")
            .to_series()
            .to_list()
        )
        # Each sector: 0.9/2 = 0.45, each stock: 0.45/3 = 0.15
        for w in stock_weights:
            assert w == pytest.approx(0.15)

    def test_uneven_stocks_per_sector(
        self,
        empty_context: StrategyContext,
    ) -> None:
        """行业内个股数不均时权重不同。"""
        rows = [
            # Sector A: 2 stocks
            {
                "instrument_id": "SECTOR-A",
                "sector_id": "SECTOR-A",
                "is_sector": True,
                "intra_selected": False,
            },
            {
                "instrument_id": "STOCK-A1",
                "sector_id": "SECTOR-A",
                "is_sector": False,
                "intra_selected": True,
            },
            {
                "instrument_id": "STOCK-A2",
                "sector_id": "SECTOR-A",
                "is_sector": False,
                "intra_selected": True,
            },
            # Sector B: 1 stock
            {
                "instrument_id": "SECTOR-B",
                "sector_id": "SECTOR-B",
                "is_sector": True,
                "intra_selected": False,
            },
            {
                "instrument_id": "STOCK-B1",
                "sector_id": "SECTOR-B",
                "is_sector": False,
                "intra_selected": True,
            },
        ]
        frame = pl.DataFrame(rows)
        stage = SectorWeightStage(cash_target=0.0)
        result = stage.process(frame, empty_context)

        weights = dict(
            zip(
                result["instrument_id"].to_list(),
                result["weight"].to_list(),
                strict=True,
            ),
        )
        # Sector weight = 0.5 each
        # A: 0.5/2 = 0.25, B: 0.5/1 = 0.5
        assert weights["STOCK-A1"] == pytest.approx(0.25)
        assert weights["STOCK-A2"] == pytest.approx(0.25)
        assert weights["STOCK-B1"] == pytest.approx(0.5)
        assert weights["SECTOR-A"] == 0.0
        assert weights["SECTOR-B"] == 0.0

    def test_no_selected_stocks(self, empty_context: StrategyContext) -> None:
        """无选中个股时 weight 全 0。"""
        frame = pl.DataFrame(
            {
                "instrument_id": ["SECTOR-A", "STOCK-A1"],
                "sector_id": ["SECTOR-A", "SECTOR-A"],
                "is_sector": [True, False],
                "intra_selected": [False, False],
            },
        )
        stage = SectorWeightStage(cash_target=0.0)
        result = stage.process(frame, empty_context)
        assert result["weight"].to_list() == [0.0, 0.0]

    def test_empty_frame(self, empty_context: StrategyContext) -> None:
        """空 frame 返回空 frame + weight 列。"""
        frame = pl.DataFrame(
            {
                "instrument_id": [],
                "sector_id": [],
                "is_sector": [],
                "intra_selected": [],
            },
            schema={
                "instrument_id": pl.Utf8,
                "sector_id": pl.Utf8,
                "is_sector": pl.Boolean,
                "intra_selected": pl.Boolean,
            },
        )
        stage = SectorWeightStage()
        result = stage.process(frame, empty_context)
        assert result.is_empty()
        assert "weight" in result.columns

    def test_cash_target_at_one(self, empty_context: StrategyContext) -> None:
        """cash_target=1.0 时 weight 全 0。"""
        frame = self._make_weighted_frame(sectors=["SECTOR-A"], stocks_per_sector=2)
        stage = SectorWeightStage(cash_target=1.0)
        result = stage.process(frame, empty_context)
        assert result["weight"].to_list() == [0.0, 0.0, 0.0]

    def test_total_weight_sum(self, empty_context: StrategyContext) -> None:
        """所有选中个股权重之和 = 1 - cash_target。"""
        frame = self._make_weighted_frame(
            sectors=["SECTOR-A", "SECTOR-B", "SECTOR-C"],
            stocks_per_sector=2,
        )
        stage = SectorWeightStage(cash_target=0.1)
        result = stage.process(frame, empty_context)
        total = result.select(pl.col("weight").sum()).item()
        assert total == pytest.approx(0.9)

    def test_frozen(self) -> None:
        """SectorWeightStage 是 frozen dataclass。"""
        stage = SectorWeightStage()
        with pytest.raises(AttributeError):
            stage.cash_target = 0.1  # type: ignore[misc]


# ---------------------------------------------------------------------------
# FinalStockFilterStage
# ---------------------------------------------------------------------------


class TestFinalStockFilterStage:
    def test_filters_sector_etfs(
        self,
        empty_context: StrategyContext,
        sector_rotation_frame: pl.DataFrame,
    ) -> None:
        """过滤后仅保留个股行。"""
        stage = FinalStockFilterStage()
        result = stage.process(sector_rotation_frame, empty_context)
        assert result.height == 9
        assert result.filter(pl.col("is_sector")).is_empty()

    def test_preserves_stock_data(
        self,
        empty_context: StrategyContext,
    ) -> None:
        """过滤后个股数据不变。"""
        frame = pl.DataFrame(
            {
                "instrument_id": ["SECTOR-A", "STOCK-1"],
                "sector_id": ["SECTOR-A", "SECTOR-A"],
                "is_sector": [True, False],
                "weight": [0.0, 0.5],
            },
        )
        stage = FinalStockFilterStage()
        result = stage.process(frame, empty_context)
        assert result.height == 1
        assert result["instrument_id"][0] == "STOCK-1"
        assert result["weight"][0] == 0.5

    def test_all_sectors_returns_empty(
        self,
        empty_context: StrategyContext,
    ) -> None:
        """全为行业 ETF 时返回空 frame。"""
        frame = pl.DataFrame(
            {
                "instrument_id": ["SECTOR-A", "SECTOR-B"],
                "sector_id": ["SECTOR-A", "SECTOR-B"],
                "is_sector": [True, True],
            },
        )
        stage = FinalStockFilterStage()
        result = stage.process(frame, empty_context)
        assert result.is_empty()

    def test_frozen(self) -> None:
        """FinalStockFilterStage 是 frozen dataclass。"""
        stage = FinalStockFilterStage()
        with pytest.raises(AttributeError):
            stage.is_sector_column = "x"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# build_stock_sector_rotation_pipeline
# ---------------------------------------------------------------------------


class TestBuildPipeline:
    def test_default_config_builds_pipeline(self) -> None:
        """默认配置构建合法 Pipeline。"""
        config = StockSectorRotationConfig()
        pipeline = build_stock_sector_rotation_pipeline(config)
        assert pipeline is not None
        # SectorSignal + SectorScoreAndSelect + IntraSectorSelect +
        # RiskLockFilter + SectorWeight + Constraint + FinalStockFilter = 7
        assert len(pipeline._stages) == 7

    def test_pipeline_stage_order(self) -> None:
        """Pipeline 阶段顺序正确。"""
        config = StockSectorRotationConfig()
        pipeline = build_stock_sector_rotation_pipeline(config)
        stages = pipeline._stages
        assert isinstance(stages[0], SectorSignalStage)
        assert isinstance(stages[1], SectorScoreAndSelectStage)
        assert isinstance(stages[2], IntraSectorSelectStage)
        assert isinstance(stages[3], RiskLockFilter)
        assert isinstance(stages[4], SectorWeightStage)
        assert isinstance(stages[5], ConstraintStage)
        assert isinstance(stages[6], FinalStockFilterStage)

    def test_max_weight_constraint_present(self) -> None:
        """ConstraintStage 中包含 MaxWeightConstraint。"""
        config = StockSectorRotationConfig(max_weight=0.20)
        pipeline = build_stock_sector_rotation_pipeline(config)
        constraint_stage = pipeline._stages[5]
        assert isinstance(constraint_stage, ConstraintStage)
        assert isinstance(constraint_stage.checker, ConstraintChecker)
        has_max_weight = any(
            isinstance(c, MaxWeightConstraint)
            for c in constraint_stage.checker._constraints
        )
        assert has_max_weight

    def test_cash_target_propagated(self) -> None:
        """cash_target 正确传递到 SectorWeightStage。"""
        config = StockSectorRotationConfig(cash_target=0.1)
        pipeline = build_stock_sector_rotation_pipeline(config)
        weight_stage = pipeline._stages[4]
        assert isinstance(weight_stage, SectorWeightStage)
        assert weight_stage.cash_target == 0.1


# ---------------------------------------------------------------------------
# E2E Pipeline
# ---------------------------------------------------------------------------


class TestPipelineE2E:
    def test_e2e_basic(
        self,
        empty_context: StrategyContext,
        sector_rotation_bundle: StrategyInputBundle,
    ) -> None:
        """
        基本端到端: 3 行业各 3 股，top_sectors=2, stocks_per_sector=2.

        行业信号: TECH(0.08) > FIN(0.05) > HEA(0.03) → 选中 TECH, FIN
        TECH 个股信号: TECH-002(0.09) > TECH-001(0.07) → 选 2
        FIN 个股信号: FIN-002(0.06) > FIN-001(0.04) → 选 2
        最终: 4 个持仓, 无行业 ETF
        """
        config = StockSectorRotationConfig(
            top_sectors=2,
            stocks_per_sector=2,
            max_weight=1.0,  # No max weight constraint effectively
        )
        pipeline = build_stock_sector_rotation_pipeline(config)
        target = pipeline.run(empty_context, sector_rotation_bundle)

        # No sector ETFs in final portfolio
        for iid in target.positions:
            assert not iid.startswith("SECTOR-")

        # TECH and FIN stocks, 2 per sector = 4 total
        assert len(target.positions) == 4
        assert "STOCK-TECH-001" in target.positions
        assert "STOCK-TECH-002" in target.positions
        assert "STOCK-FIN-001" in target.positions
        assert "STOCK-FIN-002" in target.positions

        # HEA stocks should not be selected
        assert "STOCK-HEA-001" not in target.positions
        assert "STOCK-HEA-002" not in target.positions
        assert "STOCK-HEA-003" not in target.positions

    def test_e2e_weight_sum(
        self,
        empty_context: StrategyContext,
        sector_rotation_bundle: StrategyInputBundle,
    ) -> None:
        """所有持仓权重之和 = 1.0 (cash_target=0)。"""
        config = StockSectorRotationConfig(
            top_sectors=2,
            stocks_per_sector=2,
            max_weight=1.0,
        )
        pipeline = build_stock_sector_rotation_pipeline(config)
        target = pipeline.run(empty_context, sector_rotation_bundle)

        total_weight = sum(target.positions.values())
        assert total_weight == pytest.approx(1.0)

    def test_e2e_weight_sum_with_cash_target(
        self,
        empty_context: StrategyContext,
        sector_rotation_bundle: StrategyInputBundle,
    ) -> None:
        """cash_target=0.1 时所有持仓权重之和 = 0.9。"""
        config = StockSectorRotationConfig(
            top_sectors=2,
            stocks_per_sector=2,
            max_weight=1.0,
            cash_target=0.1,
        )
        pipeline = build_stock_sector_rotation_pipeline(config)
        target = pipeline.run(empty_context, sector_rotation_bundle)

        total_weight = sum(target.positions.values())
        assert total_weight == pytest.approx(0.9)

    def test_e2e_equal_weight_within_sectors(
        self,
        empty_context: StrategyContext,
        sector_rotation_bundle: StrategyInputBundle,
    ) -> None:
        """同一行业内所有选中个股权重相同。"""
        config = StockSectorRotationConfig(
            top_sectors=3,
            stocks_per_sector=3,
            max_weight=1.0,
        )
        pipeline = build_stock_sector_rotation_pipeline(config)
        target = pipeline.run(empty_context, sector_rotation_bundle)

        # All 9 stocks selected, 3 sectors x 3 stocks
        assert len(target.positions) == 9

        # All weights should be equal: 1.0 / 9 ≈ 0.1111
        weights = list(target.positions.values())
        assert all(w == pytest.approx(weights[0]) for w in weights)
        assert weights[0] == pytest.approx(1.0 / 9.0)

    def test_e2e_max_weight_constraint(
        self,
        empty_context: StrategyContext,
        sector_rotation_bundle: StrategyInputBundle,
    ) -> None:
        """max_weight 约束生效。"""
        config = StockSectorRotationConfig(
            top_sectors=1,
            stocks_per_sector=1,
            max_weight=0.05,
        )
        pipeline = build_stock_sector_rotation_pipeline(config)
        target = pipeline.run(empty_context, sector_rotation_bundle)

        # With 1 sector and 1 stock, weight would be 1.0
        # MaxWeightConstraint should cap it at 0.05
        for weight in target.positions.values():
            assert weight <= 0.05

    def test_e2e_risk_lock_filter(
        self,
        sector_rotation_bundle: StrategyInputBundle,
    ) -> None:
        """RiskLockFilter 排除被锁定标的。"""
        context = StrategyContext()
        context.lock_instrument("STOCK-TECH-002", "test lock")

        config = StockSectorRotationConfig(
            top_sectors=2,
            stocks_per_sector=2,
            max_weight=1.0,
        )
        pipeline = build_stock_sector_rotation_pipeline(config)
        target = pipeline.run(context, sector_rotation_bundle)

        # Locked stock should not be in portfolio
        assert "STOCK-TECH-002" not in target.positions

        # Other TECH stocks should still be selected (TECH-001, TECH-003 if top 2)
        # TECH-002 was filtered out, so TECH-001 and TECH-003 fill top 2
        assert "STOCK-TECH-001" in target.positions

    def test_e2e_top_sectors_one(
        self,
        empty_context: StrategyContext,
        sector_rotation_bundle: StrategyInputBundle,
    ) -> None:
        """top_sectors=1 → 只选 1 个行业。"""
        config = StockSectorRotationConfig(
            top_sectors=1,
            stocks_per_sector=2,
            max_weight=1.0,
        )
        pipeline = build_stock_sector_rotation_pipeline(config)
        target = pipeline.run(empty_context, sector_rotation_bundle)

        # Only TECH sector selected (highest signal 0.08)
        for iid in target.positions:
            assert "TECH" in iid or "SECTOR" in iid

        # No FIN or HEA stocks
        assert not any("FIN" in iid for iid in target.positions)
        assert not any("HEA" in iid for iid in target.positions)

    def test_e2e_stocks_per_sector_one(
        self,
        empty_context: StrategyContext,
        sector_rotation_bundle: StrategyInputBundle,
    ) -> None:
        """stocks_per_sector=1 → 每行业只选 1 股。"""
        config = StockSectorRotationConfig(
            top_sectors=3,
            stocks_per_sector=1,
            max_weight=1.0,
        )
        pipeline = build_stock_sector_rotation_pipeline(config)
        target = pipeline.run(empty_context, sector_rotation_bundle)

        assert len(target.positions) == 3

        # Each sector's top stock:
        # FIN: FIN-002 (0.06), TECH: TECH-002 (0.09), HEA: HEA-001 (0.03)
        assert "STOCK-FIN-002" in target.positions
        assert "STOCK-TECH-002" in target.positions
        assert "STOCK-HEA-001" in target.positions

    def test_e2e_empty_positions(
        self,
        empty_context: StrategyContext,
    ) -> None:
        """无标的时返回空 TargetPortfolio。"""
        bundle = StrategyInputBundle(
            trade_date="2026-03-23",
            strategy_id="test",
            run_id="run_001",
            instruments=pl.DataFrame({"instrument_id": []}),
            market_data=pl.DataFrame(
                {
                    "instrument_id": [],
                    "close": [],
                    "open": [],
                    "high": [],
                    "low": [],
                    "volume": [],
                },
            ),
        )
        config = StockSectorRotationConfig()
        pipeline = build_stock_sector_rotation_pipeline(config)
        target = pipeline.run(empty_context, bundle)
        assert len(target.positions) == 0

    def test_e2e_custom_signal_columns(
        self,
        empty_context: StrategyContext,
    ) -> None:
        """使用自定义行业/个股信号列名。"""
        instrument_ids = SECTOR_ETFS + [s[0] for s in STOCKS]
        sector_ids = SECTOR_ETFS + [s[1] for s in STOCKS]
        is_sectors = [True] * 3 + [False] * 9
        sector_sigs = [0.05, 0.08, 0.03] + [None] * 9
        stock_sigs = [
            0.0,
            0.0,
            0.0,
            0.04,
            0.06,
            0.01,
            0.07,
            0.09,
            0.02,
            0.03,
            0.01,
            0.02,
        ]
        signal_values = pl.DataFrame(
            {
                "instrument_id": instrument_ids,
                "sector_id": sector_ids,
                "is_sector": is_sectors,
                "sector_momentum": sector_sigs,
                "stock_momentum": stock_sigs,
            },
        )
        bundle = StrategyInputBundle(
            trade_date="2026-03-23",
            strategy_id="test",
            run_id="run_001",
            instruments=pl.DataFrame({"instrument_id": instrument_ids}),
            market_data=pl.DataFrame(
                {
                    "instrument_id": instrument_ids,
                    "close": [10.0] * 12,
                    "open": [10.0] * 12,
                    "high": [10.5] * 12,
                    "low": [9.5] * 12,
                    "volume": [1_000_000.0] * 12,
                },
            ),
            signal_values=signal_values,
        )

        config = StockSectorRotationConfig(
            sector_signal="sector_momentum",
            stock_signal="stock_momentum",
            top_sectors=2,
            stocks_per_sector=2,
            max_weight=1.0,
        )
        pipeline = build_stock_sector_rotation_pipeline(config)
        target = pipeline.run(empty_context, bundle)

        assert len(target.positions) == 4
        assert "STOCK-TECH-001" in target.positions
        assert "STOCK-TECH-002" in target.positions
        assert "STOCK-FIN-001" in target.positions
        assert "STOCK-FIN-002" in target.positions
