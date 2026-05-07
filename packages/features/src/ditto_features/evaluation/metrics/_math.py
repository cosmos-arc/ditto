"""Numerical helpers and shared constants for evaluation metrics."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from polars._typing import PythonLiteral

# ---------------------------------------------------------------------------
# Shared column-name configuration
# ---------------------------------------------------------------------------

__all__ = ["EvaluationColumns", "fit_ic_half_life"]


@dataclass(frozen=True)
class EvaluationColumns:
    """Shared column name configuration for evaluation metrics."""

    date: str = "trade_date"
    entity: str = "instrument_id"
    factor: str = "value"
    return_col: str = "forward_return"


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MIN_TRANSITIONS_FOR_MATRIX = 2
MIN_OBS_FOR_OLS = 30
MIN_TAIL_OBSERVATIONS = 2
MIN_CORR_PAIRS = 2
MIN_POINTS_FOR_HALF_LIFE_FIT = 2
IR_TE_EPSILON = 1e-12


# ---------------------------------------------------------------------------
# Scalar conversion
# ---------------------------------------------------------------------------


def scalar_to_float(
    value: PythonLiteral | None,
    default: float = 0.0,
) -> float:
    """
    Safely convert a polars scalar to float.

    Polars ``.mean()``, ``.std()``, ``.min()`` return ``PythonLiteral | None``
    which basedpyright cannot narrow.  This helper bridges that gap.
    """
    if value is None:
        return default
    if isinstance(value, (bool, int, float, Decimal)):
        return float(value)
    if isinstance(value, timedelta):
        return value.total_seconds()
    # date, datetime, time, str, bytes, list, np.ndarray — compute a float
    # representation, falling back to *default* on failure.
    result: float = default
    if isinstance(value, date) and not isinstance(value, datetime):
        result = float(value.toordinal())
    elif isinstance(value, datetime):
        result = float(value.timestamp())
    elif isinstance(value, time):
        result = float(value.hour * 3600 + value.minute * 60 + value.second)
    elif isinstance(value, (str, bytes)):
        try:
            result = float(value)
        except (TypeError, ValueError):
            pass
    # list / np.ndarray — not convertible to float; keep *default*.
    return result


# ---------------------------------------------------------------------------
# Statistics helpers
# ---------------------------------------------------------------------------


def two_sided_p_value(t: float, df: int) -> float:
    """
    Approximate two-sided p-value from the t-distribution.

    Uses the regularised incomplete beta function identity:

        p = I_x(a, b)  where x = df / (df + t^2), a = df/2, b = 1/2

    Args:
        t: t-statistic.
        df: Degrees of freedom.

    Returns:
        Two-sided p-value.

    """
    x = df / (df + t * t)
    return regularized_incomplete_beta(x, df / 2.0, 0.5)


def regularized_incomplete_beta(
    x: float,
    a: float,
    b: float,
    *,
    max_iter: int = 200,
    tol: float = 1e-12,
) -> float:
    """
    Compute the regularised incomplete beta function I_x(a, b).

    Uses the continued fraction expansion (Lentz's method) for numerical
    stability.  Falls back to the series expansion when the continued
    fraction does not converge.

    Args:
        x: Value in [0, 1].
        a: First shape parameter (> 0).
        b: Second shape parameter (> 0).
        max_iter: Maximum iterations for the continued fraction.
        tol: Convergence tolerance.

    Returns:
        I_x(a, b) in [0, 1].

    """
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0

    # Use log-gamma for numerical safety.
    log_prefix = (
        log_gamma(a + b)
        - log_gamma(a)
        - log_gamma(b)
        + a * math.log(x)
        + b * math.log(1 - x)
    )
    prefix = math.exp(log_prefix)

    if x < (a + 1) / (a + b + 2):
        result = prefix * _beta_cf(x, a, b, max_iter=max_iter, tol=tol) / a
        return result
    result = 1.0 - prefix * _beta_cf(1 - x, b, a, max_iter=max_iter, tol=tol) / b
    return result


def _beta_cf(
    x: float,
    a: float,
    b: float,
    *,
    max_iter: int = 200,
    tol: float = 1e-12,
) -> float:
    """
    Evaluate the continued fraction for the incomplete beta function.

    Implements the modified Lentz method for the continued fraction:

        1 + d_1/(1 + d_2/(1 + ...))

    Args:
        x: Value in (0, 1).
        a: First shape parameter.
        b: Second shape parameter.
        max_iter: Maximum iterations.
        tol: Convergence tolerance.

    Returns:
        The continued fraction value.

    """
    tiny = 1e-30
    f = 1.0
    c = 1.0
    d = 1.0 - (a + b) * x / (a + 1)
    if abs(d) < tiny:
        d = tiny
    d = 1.0 / d
    f = d

    for m in range(1, max_iter + 1):
        numerator_m = m * (b - m) * x / ((a + 2 * m - 1) * (a + 2 * m))
        d = 1.0 + numerator_m * d
        if abs(d) < tiny:
            d = tiny
        d = 1.0 / d
        c = 1.0 + numerator_m / c
        if abs(c) < tiny:
            c = tiny
        f *= c * d

        numerator_m2 = -(a + m) * (a + b + m) * x / ((a + 2 * m) * (a + 2 * m + 1))
        d = 1.0 + numerator_m2 * d
        if abs(d) < tiny:
            d = tiny
        d = 1.0 / d
        c = 1.0 + numerator_m2 / c
        if abs(c) < tiny:
            c = tiny
        delta = c * d
        f *= delta

        if abs(delta - 1.0) < tol:
            break

    return f


def log_gamma(x: float) -> float:
    """
    Lanczos approximation of log(Gamma(x)) for x > 0.

    Uses the coefficients from Numerical Recipes (Press et al.) with g = 7.

    Args:
        x: Positive real number.

    Returns:
        ``log(Gamma(x))``.

    """
    if x <= 0:
        msg = f"log_gamma requires x > 0, got {x}"
        raise ValueError(msg)

    coefs = [
        0.99999999999980993,
        676.5203681218851,
        -1259.1392167224028,
        771.32342877765313,
        -176.61502916214059,
        12.507343278686905,
        -0.13857109526572012,
        9.9843695780195716e-6,
        1.5056327351493116e-7,
    ]
    g = 7
    reflection_threshold = 0.5
    if x < reflection_threshold:
        # Reflection formula: Gamma(x) * Gamma(1-x) = pi / sin(pi*x)
        return math.log(math.pi / math.sin(math.pi * x)) - log_gamma(1 - x)

    x -= 1.0
    a = coefs[0]
    t = x + g + 0.5
    for i in range(1, len(coefs)):
        a += coefs[i] / (x + i)
    return 0.5 * math.log(2 * math.pi) + (x + 0.5) * math.log(t) - t + math.log(a)


# ---------------------------------------------------------------------------
# IC-specific helpers
# ---------------------------------------------------------------------------


def fit_ic_half_life(
    decay_results: list[tuple[int, float]],
) -> float | None:
    """
    Fit IC half-life via least-squares on log(IC^2) vs lag.

    Model: ``IC(lag) = A * exp(-lag / half_life)``
    Linearised: ``log(IC^2) = log(A^2) - 2*lag / half_life``

    Args:
        decay_results: ``[(lag, mean_ic), ...]`` with positive mean_ic.

    Returns:
        Estimated half-life in days, or ``None`` if the fit is not possible.

    """
    MIN_POINTS_FOR_FIT = MIN_POINTS_FOR_HALF_LIFE_FIT
    valid = [(lag, ic) for lag, ic in decay_results if ic > 0]
    if len(valid) < MIN_POINTS_FOR_FIT:
        return None

    lags = [float(lag) for lag, _ in valid]
    log_ic2 = [math.log(ic * ic) for _, ic in valid]
    n = len(lags)
    sum_x = sum(lags)
    sum_y = sum(log_ic2)
    sum_xy = sum(x * y for x, y in zip(lags, log_ic2, strict=True))
    sum_x2 = sum(x * x for x in lags)

    denom = n * sum_x2 - sum_x * sum_x
    if denom == 0:
        return None

    slope = (n * sum_xy - sum_x * sum_y) / denom
    # slope = -2 / half_life  =>  half_life = -2 / slope
    if slope >= 0:
        return None  # IC should decay, not grow.

    half_life = -2.0 / slope
    return half_life if half_life > 0 else None
