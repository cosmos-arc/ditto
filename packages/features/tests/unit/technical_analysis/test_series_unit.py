"""叠加序列计算的单测：与 registry 标量读数同口径。"""

from __future__ import annotations

import polars as pl
import pytest
from ditto_features.technical_analysis import service as registry_service
from ditto_features.technical_analysis.series import (
    atr_series,
    compute_overlay_series,
    donchian_series,
    macd_series,
    rsi_series,
    series_alignment,
    sma_series,
)


def _frame(closes: list[float]) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "trade_date": [f"2026-01-{index + 1:02d}" for index in range(len(closes))],
            "close": closes,
            "high": [value + 1.0 for value in closes],
            "low": [value - 1.0 for value in closes],
        }
    )


def test_sma_series_matches_registry_scalar_on_tail() -> None:
    closes = [float(index + 1) for index in range(30)]
    series = sma_series(closes, 5)
    assert series[:4] == [None] * 4
    assert series[4] == pytest.approx(3.0)
    assert series[-1] == pytest.approx(sum(closes[-5:]) / 5)


def test_macd_series_tail_matches_registry_formula() -> None:
    closes = [10.0 + (index % 7) * 0.5 for index in range(60)]
    macd, signal, histogram = macd_series(closes, fast=12, slow=26, signal=9)
    first_valid = 26 + 9 - 2
    assert macd[first_valid - 1] is None
    fast_ema = registry_service._ema(closes, 12)
    slow_ema = registry_service._ema(closes, 26)
    expected_macd = fast_ema[-1] - slow_ema[-1]
    assert macd[-1] == pytest.approx(expected_macd)
    assert histogram[-1] == pytest.approx(macd[-1] - signal[-1])  # type: ignore[operator]


def test_rsi_series_matches_registry_scalar() -> None:
    closes = [100.0 + (index % 3) - 1.0 for index in range(40)]
    series = rsi_series(closes, 14)
    assert series[13] is None
    assert series[14] is not None
    assert series[-1] == pytest.approx(registry_service._rsi(closes, 14))


def test_atr_series_matches_registry_scalar() -> None:
    closes = [float(index + 1) for index in range(30)]
    highs = [value + 2.0 for value in closes]
    lows = [value - 2.0 for value in closes]
    series = atr_series(closes, highs, lows, 14)
    assert series[13] is None
    assert series[14] is not None
    assert series[-1] == pytest.approx(registry_service._atr(closes, highs, lows, 14))


def test_donchian_series_excludes_current_bar() -> None:
    highs = [10.0, 11.0, 12.0, 13.0, 14.0, 15.0]
    lows = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
    upper, lower = donchian_series(highs, lows, 3)
    # 首个有效索引 = window(需要 window 根前序 bar)
    assert upper[:3] == [None, None, None]
    # index 3: 取 index 0..2(不含当根)——registry 口径 highs[-(w+1):-1]
    assert upper[3] == 12.0
    assert lower[3] == 1.0
    # index 5: 取 index 2..4
    assert upper[5] == 14.0
    assert lower[5] == 3.0


def test_compute_overlay_series_keys_and_alignment() -> None:
    closes = [float(index + 1) for index in range(80)]
    frame = _frame(closes)
    output = compute_overlay_series(
        frame,
        ma_windows=(5, 20),
        include=frozenset({"ma", "rsi", "macd", "atr", "donchian"}),
    )
    assert set(output) == {
        "ma_5",
        "ma_20",
        "rsi",
        "macd",
        "macd_signal",
        "macd_histogram",
        "atr",
        "donchian_high",
        "donchian_low",
    }
    for values in output.values():
        assert len(values) == len(closes)
    assert series_alignment(frame)[0] == "2026-01-01"


def test_compute_overlay_series_rejects_unknown() -> None:
    with pytest.raises(ValueError, match="unsupported overlays"):
        compute_overlay_series(_frame([1.0, 2.0]), include=frozenset({"boll"}))
