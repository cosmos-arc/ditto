"""Deterministic, fail-closed budgets for governed Agent runs."""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal

from ditto_agent.models.port import ModelUsage

_MILLION = Decimal(1_000_000)


def _positive_int(value: int, *, field: str) -> int:
    if isinstance(value, bool) or value <= 0:
        raise ValueError(f"{field} must be a positive integer")
    return value


def _nonnegative_int(value: int, *, field: str) -> int:
    if isinstance(value, bool) or value < 0:
        raise ValueError(f"{field} must be a non-negative integer")
    return value


def _finite_nonnegative_decimal(value: Decimal, *, field: str) -> Decimal:
    if not value.is_finite() or value < 0:
        raise ValueError(f"{field} must be a finite non-negative Decimal")
    return value


@dataclass(frozen=True, slots=True)
class BudgetLimits:
    """Hard limits selected by the host before a run starts."""

    max_turns: int
    max_model_tokens: int
    max_model_spend_usd: Decimal
    max_wall_time_seconds: float
    max_retries: int

    def __post_init__(self) -> None:
        """Reject disabled, invalid, or unbounded controls."""
        _positive_int(self.max_turns, field="max_turns")
        _positive_int(self.max_model_tokens, field="max_model_tokens")
        _finite_nonnegative_decimal(
            self.max_model_spend_usd,
            field="max_model_spend_usd",
        )
        if (
            isinstance(self.max_wall_time_seconds, bool)
            or not math.isfinite(self.max_wall_time_seconds)
            or self.max_wall_time_seconds <= 0
        ):
            raise ValueError("max_wall_time_seconds must be finite and positive")
        _nonnegative_int(self.max_retries, field="max_retries")


@dataclass(frozen=True, slots=True)
class ModelPricing:
    """Pinned model prices used for local cost accounting."""

    input_usd_per_million: Decimal
    output_usd_per_million: Decimal

    def __post_init__(self) -> None:
        """Require finite non-negative prices."""
        _finite_nonnegative_decimal(
            self.input_usd_per_million,
            field="input_usd_per_million",
        )
        _finite_nonnegative_decimal(
            self.output_usd_per_million,
            field="output_usd_per_million",
        )


@dataclass(frozen=True, slots=True)
class BudgetSnapshot:
    """Auditable point-in-time view of all consumed resources."""

    model_attempts: int
    model_turns: int
    tool_calls: int
    retries: int
    total_tokens: int
    model_spend_usd: Decimal
    elapsed_seconds: float
    exhausted_reason: str | None


class BudgetExceeded(PermissionError):
    """A sticky hard limit prevents any further run activity."""

    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


class BudgetLedger:
    """Account model, tool, retry, token, cost, and wall-time consumption."""

    def __init__(
        self,
        *,
        limits: BudgetLimits,
        pricing: ModelPricing,
        monotonic: Callable[[], float],
    ) -> None:
        self._limits = limits
        self._pricing = pricing
        self._monotonic = monotonic
        self._started_at = monotonic()
        self._model_attempts = 0
        self._model_turns = 0
        self._tool_calls = 0
        self._retries = 0
        self._total_tokens = 0
        self._model_spend_usd = Decimal(0)
        self._exhausted_reason: str | None = None

    @property
    def limits(self) -> BudgetLimits:
        """Return the immutable limits bound to this ledger."""
        return self._limits

    @property
    def pricing(self) -> ModelPricing:
        """Return the immutable price identity bound to this ledger."""
        return self._pricing

    def _fail(self, reason_code: str) -> None:
        if self._exhausted_reason is None:
            self._exhausted_reason = reason_code
        raise BudgetExceeded(self._exhausted_reason)

    def _check_available(self) -> None:
        if self._exhausted_reason is not None:
            raise BudgetExceeded(self._exhausted_reason)
        if self._monotonic() - self._started_at > self._limits.max_wall_time_seconds:
            self._fail("max_wall_time_exceeded")

    def before_model_attempt(self) -> None:
        """Admit and account one provider request attempt."""
        self._check_available()
        self._model_attempts += 1

    def record_model_usage(self, usage: ModelUsage) -> None:
        """Record provider-reported usage and immediately enforce every limit."""
        self._check_available()
        self._model_turns += usage.requests
        self._total_tokens += usage.total_tokens
        self._model_spend_usd += (
            Decimal(usage.input_tokens) * self._pricing.input_usd_per_million
            + Decimal(usage.output_tokens) * self._pricing.output_usd_per_million
        ) / _MILLION
        if self._model_turns > self._limits.max_turns:
            self._fail("max_turns_exceeded")
        if self._total_tokens > self._limits.max_model_tokens:
            self._fail("max_model_tokens_exceeded")
        if self._model_spend_usd > self._limits.max_model_spend_usd:
            self._fail("max_model_spend_exceeded")

    def before_tool_call(self) -> None:
        """Admit and account one host tool invocation."""
        self._check_available()
        if self._tool_calls >= self._limits.max_turns:
            self._fail("max_turns_exceeded")
        self._tool_calls += 1

    def register_retry(self) -> None:
        """Admit a bounded transient-provider retry."""
        self._check_available()
        if self._retries >= self._limits.max_retries:
            self._fail("max_retries_exceeded")
        self._retries += 1

    def snapshot(self) -> BudgetSnapshot:
        """Return counters without introducing an implicit clock dependency."""
        elapsed = self._monotonic() - self._started_at
        return BudgetSnapshot(
            model_attempts=self._model_attempts,
            model_turns=self._model_turns,
            tool_calls=self._tool_calls,
            retries=self._retries,
            total_tokens=self._total_tokens,
            model_spend_usd=self._model_spend_usd,
            elapsed_seconds=elapsed,
            exhausted_reason=self._exhausted_reason,
        )


__all__ = [
    "BudgetExceeded",
    "BudgetLedger",
    "BudgetLimits",
    "BudgetSnapshot",
    "ModelPricing",
]
