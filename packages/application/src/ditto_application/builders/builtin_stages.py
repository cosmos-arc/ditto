"""Construction helpers for application-owned builtin decision stages."""

from collections.abc import Mapping

from ditto_strategy.alpha.builtins.filtering import TrendFilterStage
from ditto_strategy.alpha.protocols import DecisionStage
from ditto_strategy.alpha.selection_evidence import SelectionEvidenceSink

from ditto_application.builders._spec_deserializer import read_float, read_str_value

__all__ = ["build_trend_filter"]


def build_trend_filter(
    config: Mapping[str, object],
    *,
    evidence_sink: SelectionEvidenceSink | None,
) -> tuple[DecisionStage, ...]:
    """Build the frozen trend-filter builtin from validated node config."""
    return (
        TrendFilterStage(
            threshold=read_float(
                config["threshold"],
                field_name="node.config.threshold",
            ),
            direction=read_str_value(
                config["direction"],
                field_name="node.config.direction",
            ),
            signal_column=read_str_value(
                config["signal_column"],
                field_name="node.config.signal_column",
            ),
            evidence_sink=evidence_sink,
        ),
    )
