"""PIT（Point-in-Time）策略配置."""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum


class WindowClosed(str, Enum):
    """
    Rolling window closed side strategy.

    Determines whether the window is closed on the left, right, or both sides.
    This is critical for PIT safety to prevent data leakage.

    Attributes:
        LEFT: Window includes [T-window, T-1] (PIT-safe, no data leakage)
        RIGHT: Window includes [T-window+1, T] (NOT PIT-safe, data leakage)
        BOTH: Window includes [T-window, T] (NOT PIT-safe, data leakage)
        NONE: Window includes [T-window+1, T-1] (PIT-safe)

    Examples:
        - rolling_mean(20, closed="left") → Use data up to T-1 (safe)
        - rolling_mean(20, closed="right") → Use data up to T (leakage)

    """

    LEFT = "left"  # PIT-safe: window [T-window, T-1]
    RIGHT = "right"  # NOT PIT-safe: window [T-window+1, T]
    BOTH = "both"  # NOT PIT-safe: window [T-window, T]
    NONE = "none"  # PIT-safe: window [T-window+1, T-1]


class PitStrategy(str, Enum):
    """
    PIT strategy for point-in-time data queries.

    Defines how to handle time-sensitive data to ensure data consistency
    and prevent look-ahead bias.

    Attributes:
        STRICT: Enforce PIT with version checking (default, safest)
        LOOSE: Allow late-arriving data without version checks
        LATEST: Use latest data regardless of timestamp (not recommended)

    Examples:
        - STRICT: Use only data available as_of_date (safest)
        - LOOSE: Allow data with knowledge_date <= as_of_date + tolerance
        - LATEST: Use latest data regardless of timestamp (not PIT-safe)

    """

    STRICT = "strict"  # Enforce PIT with effective_from/effective_to
    LOOSE = "loose"  # Allow late-arriving data within tolerance
    LATEST = "latest"  # Use latest data (not recommended for production)


@dataclass(frozen=True)
class PitConfig:
    """
    PIT (Point-in-Time) configuration.

    Centralized configuration for PIT strategy across the system.
    This ensures consistent PIT behavior and prevents data leakage.

    Attributes:
        strategy: PIT strategy for time-sensitive queries
        window_closed: Rolling window closed side (default: LEFT for PIT safety)
        knowledge_date_tolerance_days: Tolerance days for LOOSE strategy (default: 0)
        enforce_effective_dates: Whether to enforce effective_from/effective_to checks

    Examples:
        >>> config = PitConfig()
        >>> assert config.window_closed == WindowClosed.LEFT
        >>> assert config.strategy == PitStrategy.STRICT

    """

    strategy: PitStrategy = PitStrategy.STRICT
    window_closed: WindowClosed = WindowClosed.LEFT
    knowledge_date_tolerance_days: int = 0
    enforce_effective_dates: bool = True

    @classmethod
    def from_env(cls) -> PitConfig:
        """
        Create PitConfig from environment variables.

        Environment Variables:
            DITTO_PIT_STRATEGY: PIT strategy (strict/loose/latest)
            DITTO_PIT_WINDOW_CLOSED: Window closed side (left/right/both/none)
            DITTO_PIT_TOLERANCE_DAYS: Tolerance days for LOOSE strategy

        Returns:
            PitConfig instance

        Examples:
            >>> import os
            >>> os.environ["DITTO_PIT_STRATEGY"] = "loose"
            >>> os.environ["DITTO_PIT_TOLERANCE_DAYS"] = "3"
            >>> config = PitConfig.from_env()
            >>> assert config.strategy == PitStrategy.LOOSE
            >>> assert config.knowledge_date_tolerance_days == 3

        """
        strategy_str = os.getenv("DITTO_PIT_STRATEGY", "strict")
        window_closed_str = os.getenv("DITTO_PIT_WINDOW_CLOSED", "left")
        tolerance_days_str = os.getenv("DITTO_PIT_TOLERANCE_DAYS", "0")
        tolerance_days_str = os.getenv("DITTO_PIT_TOLERANCE_DAYS", "0")

        try:
            strategy = PitStrategy(strategy_str)
        except ValueError:
            strategy = PitStrategy.STRICT

        try:
            window_closed = WindowClosed(window_closed_str)
        except ValueError:
            window_closed = WindowClosed.LEFT

        try:
            tolerance_days = int(tolerance_days_str)
        except ValueError:
            tolerance_days = 0

        return cls(
            strategy=strategy,
            window_closed=window_closed,
            knowledge_date_tolerance_days=tolerance_days,
        )

    def validate_for_safety(self) -> None:
        """
        Validate PIT configuration for safety.

        Raises:
            ValueError: If configuration is not PIT-safe

        Examples:
            >>> config = PitConfig()
            >>> config.validate_for_safety()  # OK

            >>> unsafe_config = PitConfig(window_closed=WindowClosed.RIGHT)
            >>> unsafe_config.validate_for_safety()  # Raises ValueError

        """
        # LEFT: [T-window, T-1] - 包含左端点，不包含当前点
        # NONE: [T-window+1, T-1] - 不包含两个端点，最保守策略
        if self.window_closed not in (WindowClosed.LEFT, WindowClosed.NONE):
            raise ValueError(
                "Unsafe PIT configuration: "
                + f"window_closed={self.window_closed.value}. "
                + "Use WindowClosed.LEFT or WindowClosed.NONE to prevent data leakage."
            )

        if self.strategy == PitStrategy.LATEST:
            raise ValueError(
                "Unsafe PIT configuration: strategy=latest. "
                + "Use PitStrategy.STRICT or PitStrategy.LOOSE for production."
            )
