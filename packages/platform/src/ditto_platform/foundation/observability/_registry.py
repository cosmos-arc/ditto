"""观测系统全局状态注册表。"""

from __future__ import annotations

from dataclasses import dataclass

from .config import ObservabilityConfig


@dataclass(frozen=True)
class _RegistryState:
    """Immutable registry state."""

    initialized: bool = False
    config: ObservabilityConfig | None = None


_state: list[_RegistryState] = [_RegistryState()]


def is_initialized() -> bool:
    return _state[0].initialized


def set_initialized(value: bool) -> None:
    _state[0] = _RegistryState(initialized=value, config=_state[0].config)


def get_config() -> ObservabilityConfig | None:
    return _state[0].config


def set_config(config: ObservabilityConfig) -> None:
    _state[0] = _RegistryState(initialized=_state[0].initialized, config=config)


def reset() -> None:
    _state[0] = _RegistryState()
