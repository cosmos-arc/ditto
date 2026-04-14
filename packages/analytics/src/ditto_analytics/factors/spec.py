"""FactorSpec dataclass — lightweight declaration of a factor / feature."""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["FactorContext", "FactorSpec"]


@dataclass(frozen=True)
class FactorContext:
    """
    Immutable calendar context carried alongside a factor evaluation.

    Provides metadata about the trading day that factors may use to
    adjust their computation (e.g. different price-limit rules on
    special trading days such as IPO first day).

    Attributes
    ----------
    is_special:
        Whether the trading day is a special day (weekend trade,
        make-up day, IPO day, etc.).
    is_half_day:
        Whether the trading day is a half-day session.
    exchange:
        Exchange identifier (e.g. ``"SSE"``, ``"SZSE"``).

    """

    is_special: bool = False
    is_half_day: bool = False
    exchange: str | None = None


@dataclass(frozen=True)
class FactorSpec:
    """
    Immutable declaration of a derived factor or feature.

    Attributes
    ----------
    id:
        Unique identifier (e.g. ``"rsi_14"``).
    expression:
        DSL expression string compatible with the expression compiler.
        Empty for ``computation_type="python"`` factors.
    dependencies:
        Tuple of dependency names (other factor ids or ``market.*`` columns).
    description:
        Human-readable description of the factor.
    calendar_context:
        Optional calendar context (special day flags, exchange, etc.).
    computation_type:
        ``"expression"`` (default) for DSL-based factors,
        ``"python"`` for factors requiring Python computation.

    """

    id: str
    expression: str
    dependencies: tuple[str, ...] = ()
    description: str = ""
    calendar_context: FactorContext | None = None
    computation_type: str = "expression"
