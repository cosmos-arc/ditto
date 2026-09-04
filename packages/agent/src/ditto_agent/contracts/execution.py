"""Immutable host authority for one governed read-only Agent execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import cast

from ditto_agent._canonical import canonical_sha256
from ditto_agent.contracts._validation import (
    normalized_unique_tuple,
    positive_int,
)
from ditto_agent.contracts.temporal import TemporalToolContext


@dataclass(frozen=True, slots=True)
class AgentRunExecutionPlan:
    """Persistable PIT, egress, tool and output scope selected by the host."""

    temporal_context: TemporalToolContext
    allowed_tools: tuple[str, ...]
    max_output_tokens: int
    authority_hash: str = field(init=False)

    def __post_init__(self) -> None:
        """Normalize the closed scope and derive its immutable authority hash."""
        if not isinstance(cast(object, self.temporal_context), TemporalToolContext):
            raise TypeError("temporal_context must be a TemporalToolContext")
        object.__setattr__(
            self,
            "allowed_tools",
            normalized_unique_tuple(self.allowed_tools, field="allowed_tools"),
        )
        positive_int(self.max_output_tokens, field="max_output_tokens")
        object.__setattr__(
            self,
            "authority_hash",
            canonical_sha256(self.canonical_payload()),
        )

    def canonical_payload(self) -> dict[str, object]:
        """Return every trusted execution field used by the authority fence."""
        return {
            "temporal_context": self.temporal_context.canonical_payload(),
            "allowed_tools": self.allowed_tools,
            "max_output_tokens": self.max_output_tokens,
        }


__all__ = ["AgentRunExecutionPlan"]
