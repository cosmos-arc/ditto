"""观测系统全局状态注册表。"""

from __future__ import annotations

import contextvars
from dataclasses import dataclass

from .config import ObservabilityConfig


@dataclass(frozen=True)
class _RegistryState:
    """Immutable registry state stored in ContextVar."""

    initialized: bool = False
    config: ObservabilityConfig | None = None


_UNSET: object = object()

_var: contextvars.ContextVar[_RegistryState | object] = contextvars.ContextVar(
    "observability_registry",
    default=_UNSET,
)


def _get_state() -> _RegistryState:
    state = _var.get()
    if state is _UNSET:
        return _RegistryState()
    return state  # type: ignore[return-value]


def is_initialized() -> bool:
    return _get_state().initialized


def set_initialized(value: bool) -> None:
    state = _get_state()
    _var.set(_RegistryState(initialized=value, config=state.config))


def get_config() -> ObservabilityConfig | None:
    return _get_state().config


def set_config(config: ObservabilityConfig) -> None:
    state = _get_state()
    _var.set(_RegistryState(initialized=state.initialized, config=config))


def reset() -> None:
    _var.set(_RegistryState())
