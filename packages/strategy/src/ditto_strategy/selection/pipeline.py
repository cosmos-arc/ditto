"""Deterministic stock/ETF selection pipeline with fail-closed filters."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from ditto_strategy.selection.contracts import (
    EtfSelectionSpec,
    SelectionCandidate,
    SelectionExclusion,
    SelectionExclusionReason,
    SelectionFactorContribution,
    SelectionInputBundle,
    SelectionInstrumentInput,
    SelectionRun,
    SelectionRunStatus,
    SelectionSpec,
    StockSelectionSpec,
)

__all__ = ["SelectionPipeline"]


@dataclass(frozen=True, slots=True)
class _ScoredInstrument:
    source: SelectionInstrumentInput
    score: float
    contributions: tuple[SelectionFactorContribution, ...]
    tie_breaker: str


def _required_missing(
    value: SelectionInstrumentInput,
    spec: SelectionSpec,
) -> tuple[str, ...]:
    missing = set(value.declared_missing_inputs)
    prefix = f"instrument:{value.instrument_id}:"
    required_fields = {
        "average_turnover": value.average_turnover,
        "is_suspended": value.is_suspended,
        "listing_days": value.listing_days,
        "limit_state": value.limit_state,
    }
    if isinstance(spec, StockSelectionSpec):
        required_fields["is_st"] = value.is_st
    if isinstance(spec, EtfSelectionSpec) and spec.max_tracking_error is not None:
        required_fields["tracking_error"] = value.tracking_error
    for field_name, field_value in required_fields.items():
        if field_value is None:
            missing.add(f"{prefix}{field_name}")
    observed_factors = {item.name for item in value.factor_values}
    for factor in spec.factor_weights:
        if factor.name not in observed_factors:
            missing.add(f"{prefix}factor:{factor.name}")
    return tuple(sorted(missing))


def _hard_filter(
    value: SelectionInstrumentInput,
    spec: SelectionSpec,
) -> tuple[SelectionExclusionReason, str] | None:
    missing = _required_missing(value, spec)
    if missing:
        return SelectionExclusionReason.MISSING_DATA, ",".join(missing)
    if value.average_turnover is not None and (
        value.average_turnover < spec.min_average_turnover
    ):
        return (
            SelectionExclusionReason.INSUFFICIENT_LIQUIDITY,
            "average_turnover_below_minimum",
        )
    if isinstance(spec, StockSelectionSpec) and value.is_st:
        return SelectionExclusionReason.ST_STATUS, "stock_is_st"
    return _tradability_filter(value, spec)


def _tradability_filter(
    value: SelectionInstrumentInput,
    spec: SelectionSpec,
) -> tuple[SelectionExclusionReason, str] | None:
    if value.is_suspended:
        return SelectionExclusionReason.SUSPENDED, "instrument_is_suspended"
    if value.listing_days is not None and value.listing_days < spec.min_listing_days:
        return (
            SelectionExclusionReason.INSUFFICIENT_LISTING_DAYS,
            "listing_days_below_minimum",
        )
    limit_state = value.limit_state
    if limit_state is not None and limit_state in spec.excluded_limit_states:
        return SelectionExclusionReason.PRICE_LIMITED, limit_state.value
    if (
        isinstance(spec, EtfSelectionSpec)
        and spec.max_tracking_error is not None
        and value.tracking_error is not None
        and value.tracking_error > spec.max_tracking_error
    ):
        return (
            SelectionExclusionReason.EXCESSIVE_TRACKING_ERROR,
            "tracking_error_above_maximum",
        )
    return None


def _score(
    value: SelectionInstrumentInput,
    spec: SelectionSpec,
    *,
    seed: int,
) -> _ScoredInstrument:
    factor_values = {item.name: item.value for item in value.factor_values}
    contributions = tuple(
        SelectionFactorContribution(
            factor_name=factor.name,
            value=factor_values[factor.name],
            weight=factor.weight,
            contribution=factor_values[factor.name] * factor.weight,
        )
        for factor in spec.factor_weights
    )
    score = sum(item.contribution for item in contributions)
    tie_breaker = hashlib.sha256(f"{seed}:{value.instrument_id}".encode()).hexdigest()
    return _ScoredInstrument(
        source=value,
        score=0.0 if score == 0.0 else score,
        contributions=contributions,
        tie_breaker=tie_breaker,
    )


def _exclusion(
    value: SelectionInstrumentInput,
    *,
    reason: SelectionExclusionReason,
    detail: str,
    stage: str,
) -> SelectionExclusion:
    return SelectionExclusion(
        instrument_id=value.instrument_id,
        instrument_name=value.instrument_name,
        reason_code=reason,
        stage=stage,
        detail=detail,
    )


class SelectionPipeline:
    """Apply exact hard filters, rank scores, and save every in/out reason."""

    def run(self, value: SelectionInputBundle) -> SelectionRun:
        """Execute one deterministic selection run."""
        if not value.instruments:
            return self._run(
                value,
                status=SelectionRunStatus.BLOCKED,
                candidates=(),
                exclusions=(),
                missing_inputs=("instruments",),
            )

        missing_inputs: set[str] = set()
        exclusions: list[SelectionExclusion] = []
        eligible: list[_ScoredInstrument] = []
        for instrument in value.instruments:
            missing = _required_missing(instrument, value.spec)
            filter_result = _hard_filter(instrument, value.spec)
            if filter_result is not None:
                reason, detail = filter_result
                exclusions.append(
                    _exclusion(
                        instrument,
                        reason=reason,
                        detail=detail,
                        stage="hard_filter",
                    )
                )
                missing_inputs.update(missing)
                continue
            eligible.append(_score(instrument, value.spec, seed=value.seed))

        eligible.sort(
            key=lambda item: (-item.score, item.tie_breaker, item.source.instrument_id)
        )
        selected = eligible[: value.spec.top_k]
        below_top_k = eligible[value.spec.top_k :]
        candidates = tuple(
            SelectionCandidate(
                instrument_id=item.source.instrument_id,
                instrument_name=item.source.instrument_name,
                industry_id=item.source.industry_id,
                rank=rank,
                score=item.score,
                factor_contributions=item.contributions,
            )
            for rank, item in enumerate(selected, start=1)
        )
        exclusions.extend(
            _exclusion(
                item.source,
                reason=SelectionExclusionReason.BELOW_TOP_K,
                detail="eligible_score_below_top_k",
                stage="ranking",
            )
            for item in below_top_k
        )
        status = (
            SelectionRunStatus.DEGRADED if missing_inputs else SelectionRunStatus.READY
        )
        return self._run(
            value,
            status=status,
            candidates=candidates,
            exclusions=tuple(sorted(exclusions, key=lambda item: item.instrument_id)),
            missing_inputs=tuple(sorted(missing_inputs)),
        )

    @staticmethod
    def _run(
        value: SelectionInputBundle,
        *,
        status: SelectionRunStatus,
        candidates: tuple[SelectionCandidate, ...],
        exclusions: tuple[SelectionExclusion, ...],
        missing_inputs: tuple[str, ...],
    ) -> SelectionRun:
        return SelectionRun(
            input_hash=value.input_hash,
            spec_hash=value.spec_hash,
            asset_kind=value.spec.asset_kind,
            spec_id=value.spec.spec_id,
            spec_version=value.spec.spec_version,
            seed=value.seed,
            as_of=value.as_of,
            knowledge_cutoff=value.knowledge_cutoff,
            publication_cutoff=value.publication_cutoff,
            universe_snapshot_id=value.universe_snapshot_id,
            industry_rotation_snapshot_id=value.industry_rotation_snapshot_id,
            source_snapshot_ids=value.source_snapshot_ids,
            status=status,
            candidates=candidates,
            exclusions=exclusions,
            missing_inputs=missing_inputs,
        )
