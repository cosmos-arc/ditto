"""Board-aware A-share close limit classification (single authority)."""

from __future__ import annotations

import math
from typing import Literal

__all__ = ["derive_limit_state"]

type LimitState = Literal["normal", "limit_up", "limit_down"]


def derive_limit_state(
    *,
    source_ticker: str,
    pct_change: float,
    close: float,
    high: float,
    low: float,
    is_st: bool,
) -> LimitState:
    """
    Derive a conservative A-share close limit using board/ST thresholds.

    ST names use the ±4.8% band; ChiNext/STAR use ±19.5%; Beijing-exchange
    codes use ±29.5%; the main boards use ±9.5%. A limit additionally
    requires the close to sit at the session extreme, so an intraday touch
    that faded is not a close limit.
    """
    ticker = source_ticker.partition(".")[0]
    if is_st:
        threshold = 4.8
    elif ticker.startswith(("300", "301", "688", "689")):
        threshold = 19.5
    elif ticker.startswith(("4", "8", "92")):
        threshold = 29.5
    else:
        threshold = 9.5
    tolerance = max(abs(close), 1.0) * 1e-8
    if pct_change >= threshold and math.isclose(close, high, abs_tol=tolerance):
        return "limit_up"
    if pct_change <= -threshold and math.isclose(close, low, abs_tol=tolerance):
        return "limit_down"
    return "normal"
