"""Server-owned temporal context construction and cache identity."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from ditto_agent._canonical import canonical_sha256
from ditto_agent.contracts._validation import normalized_text
from ditto_agent.contracts.temporal import TemporalContextInput, TemporalToolContext


class TemporalContextError(ValueError):
    """Trusted temporal authority is incomplete or internally inconsistent."""

    def __init__(
        self,
        message: str,
        *,
        reason_code: str,
        details: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.reason_code = reason_code
        self.details = MappingProxyType(dict(details or {}))


class TemporalContextFactory:
    """Build complete contexts only from one server-resolved authority object."""

    @staticmethod
    def build(authority: object) -> TemporalToolContext:
        """Validate exact PIT authority without time, snapshot, or policy defaults."""
        if not isinstance(authority, TemporalContextInput):
            raise TemporalContextError(
                "Temporal authority must use the frozen host input contract",
                reason_code="temporal_context_invalid",
            )
        try:
            context = TemporalToolContext.from_host(authority)
        except (TypeError, ValueError) as exc:
            reason_code = (
                "temporal_cutoff_order_invalid"
                if "publication_cutoff must be" in str(exc)
                else "temporal_context_invalid"
            )
            raise TemporalContextError(
                "Temporal authority failed closed validation",
                reason_code=reason_code,
            ) from exc
        if (
            context.execution_eligible_at != "not_applicable"
            and context.execution_eligible_at < context.decision_time
        ):
            raise TemporalContextError(
                "Execution eligibility cannot precede the decision time",
                reason_code="temporal_execution_precedes_decision",
            )
        return context

    @staticmethod
    def cache_key(
        *,
        namespace: str,
        parameters: Mapping[str, object],
        context: object,
    ) -> str:
        """Hash request parameters with every trusted visibility input."""
        if not isinstance(context, TemporalToolContext):
            raise TemporalContextError(
                "Cache identity requires a trusted temporal context",
                reason_code="temporal_context_invalid",
            )
        return canonical_sha256(
            {
                "namespace": normalized_text(namespace, field="cache namespace"),
                "parameters": parameters,
                "temporal_context": context.canonical_payload(),
            }
        )


__all__ = ["TemporalContextError", "TemporalContextFactory"]
