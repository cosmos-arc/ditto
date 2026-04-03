"""AlphaOutput / PortfolioOutput Stage 数据合约单元测试."""

from __future__ import annotations

import polars as pl
import pytest
from ditto_engine.orchestrator.contracts import AlphaOutput, PortfolioOutput

# ---------------------------------------------------------------------------
# AlphaOutput
# ---------------------------------------------------------------------------


class TestAlphaOutput:
    """AlphaOutput frozen dataclass 测试."""

    def test_valid_signals(self) -> None:
        """正常构造 — 包含 instrument_id, score, rank 列."""
        df = pl.DataFrame(
            {
                "instrument_id": [1, 2, 3],
                "score": [0.8, 0.6, 0.4],
                "rank": [1, 2, 3],
            },
        )
        output = AlphaOutput(signals=df)
        assert len(output.signals) == 3
        assert set(output.signals.columns) >= {"instrument_id", "score", "rank"}

    def test_frozen(self) -> None:
        """AlphaOutput 是 frozen — 禁止修改属性."""
        df = pl.DataFrame(
            {"instrument_id": [1], "score": [0.5], "rank": [1]},
        )
        output = AlphaOutput(signals=df)
        with pytest.raises(AttributeError):
            output.signals = pl.DataFrame()  # type: ignore[misc]

    def test_missing_columns_raises(self) -> None:
        """缺少必需列 → ValueError."""
        df = pl.DataFrame({"instrument_id": [1], "score": [0.5]})
        with pytest.raises(ValueError, match="缺少必需列"):
            AlphaOutput(signals=df)

    def test_extra_columns_allowed(self) -> None:
        """额外列允许 — 只要包含必需列."""
        df = pl.DataFrame(
            {
                "instrument_id": [1],
                "score": [0.5],
                "rank": [1],
                "extra_col": ["hello"],
            },
        )
        output = AlphaOutput(signals=df)
        assert "extra_col" in output.signals.columns

    def test_empty_signals_allowed(self) -> None:
        """空 DataFrame 允许 — 只要有正确的列."""
        df = pl.DataFrame(
            {"instrument_id": pl.Series([], dtype=pl.Int64)},
        )
        # 只有一列，缺少 score 和 rank
        with pytest.raises(ValueError):
            AlphaOutput(signals=df)


# ---------------------------------------------------------------------------
# PortfolioOutput
# ---------------------------------------------------------------------------


class TestPortfolioOutput:
    """PortfolioOutput frozen dataclass 测试."""

    def test_valid_targets(self) -> None:
        """正常构造 — 包含 instrument_id, target_weight 列."""
        df = pl.DataFrame(
            {
                "instrument_id": [1, 2],
                "target_weight": [0.6, 0.4],
            },
        )
        output = PortfolioOutput(targets=df)
        assert len(output.targets) == 2
        assert set(output.targets.columns) >= {"instrument_id", "target_weight"}

    def test_frozen(self) -> None:
        """PortfolioOutput 是 frozen — 禁止修改属性."""
        df = pl.DataFrame(
            {"instrument_id": [1], "target_weight": [1.0]},
        )
        output = PortfolioOutput(targets=df)
        with pytest.raises(AttributeError):
            output.targets = pl.DataFrame()  # type: ignore[misc]

    def test_missing_columns_raises(self) -> None:
        """缺少 target_weight 列 → ValueError."""
        df = pl.DataFrame({"instrument_id": [1]})
        with pytest.raises(ValueError, match="target_weight"):
            PortfolioOutput(targets=df)

    def test_extra_columns_allowed(self) -> None:
        """额外列允许 — 只要有必需列."""
        df = pl.DataFrame(
            {
                "instrument_id": [1],
                "target_weight": [1.0],
                "sector": ["etf"],
            },
        )
        output = PortfolioOutput(targets=df)
        assert "sector" in output.targets.columns
