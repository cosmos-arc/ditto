"""Optional platform metrics bridge for backtest step execution."""

from __future__ import annotations

from collections.abc import Callable

__all__ = ["build_step_metrics_callback"]


def build_step_metrics_callback() -> Callable[[str, float, bool], None] | None:
    """Build the callback only when the host metrics runtime is available."""
    try:
        from ditto_platform.foundation import Metrics  # noqa: PLC0415
    except Exception:
        return None

    def _on_step_complete(
        step_name: str,
        duration: float,
        success: bool,
    ) -> None:
        try:
            Metrics.backtest_step_duration.record(duration, {"step": step_name})
            if not success:
                Metrics.backtest_step_failures.add(1, {"step": step_name})
        except AttributeError:
            return

    return _on_step_complete
