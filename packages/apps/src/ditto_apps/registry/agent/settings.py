"""Fail-closed Apps settings for the five fixed R5 Agent feature flags."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_FALSE_VALUES = frozenset({"0", "false", "no", "off"})


def _flag(environ: Mapping[str, str], name: str) -> bool:
    value = environ.get(name)
    if value is None:
        return False
    normalized = value.casefold()
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False
    raise ValueError(f"{name} must be an explicit boolean")


@dataclass(frozen=True, slots=True)
class AgentFeatureSettings:
    """Closed flag set; subfeatures cannot bypass the master Agent switch."""

    agent_enabled: bool = False
    author_enabled: bool = False
    campaign_enabled: bool = False
    decision_shadow_enabled: bool = False
    model_calls_enabled: bool = False

    def __post_init__(self) -> None:
        """Reject integer or string truthiness in direct construction."""
        for name in (
            "agent_enabled",
            "author_enabled",
            "campaign_enabled",
            "decision_shadow_enabled",
            "model_calls_enabled",
        ):
            if type(getattr(self, name)) is not bool:
                raise ValueError(f"{name} must be boolean")

    @classmethod
    def from_environment(
        cls,
        environ: Mapping[str, str] | None = None,
    ) -> AgentFeatureSettings:
        """Read only the five documented environment names."""
        source = os.environ if environ is None else environ
        return cls(
            agent_enabled=_flag(source, "DITTO_AGENT_ENABLED"),
            author_enabled=_flag(source, "DITTO_AGENT_AUTHOR_ENABLED"),
            campaign_enabled=_flag(source, "DITTO_AGENT_CAMPAIGN_ENABLED"),
            decision_shadow_enabled=_flag(
                source,
                "DITTO_AGENT_DECISION_SHADOW_ENABLED",
            ),
            model_calls_enabled=_flag(source, "DITTO_AGENT_MODEL_CALLS_ENABLED"),
        )

    @property
    def any_enabled(self) -> bool:
        """Return whether any Agent surface can be effective."""
        return self.agent_enabled

    @property
    def author_available(self) -> bool:
        """Return the effective Author capability gate."""
        return self.agent_enabled and self.author_enabled

    @property
    def campaign_available(self) -> bool:
        """Return the effective Campaign capability gate."""
        return self.agent_enabled and self.campaign_enabled

    @property
    def decision_shadow_available(self) -> bool:
        """Return the effective Decision shadow capability gate."""
        return self.agent_enabled and self.decision_shadow_enabled

    @property
    def model_calls_available(self) -> bool:
        """Return the effective live-model egress gate."""
        return self.agent_enabled and self.model_calls_enabled


__all__ = ["AgentFeatureSettings"]
