"""Typed application boundary for creating saved industry/selection runs."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime
from typing import Literal

from ditto_data.catalog.field_evidence import consumer_input_digest
from ditto_kernel.identity import InstrumentId
from ditto_strategy.errors import StrategySpecError
from ditto_strategy.industry_rotation.contracts import (
    IndustryRotationIndustryInput,
    IndustryRotationInputBundle,
)
from ditto_strategy.selection.contracts import (
    EtfSelectionSpec,
    SelectionFactorValue,
    SelectionFactorWeight,
    SelectionInputBundle,
    SelectionInstrumentInput,
    SelectionLimitState,
    StockSelectionSpec,
)

from ditto_application.exceptions import AppProcessError, AppQueryError
from ditto_application.processes.selection.admission import (
    assess_selection_fields,
    missing_field,
    observed_fields,
    selection_field_payload,
)
from ditto_application.processes.selection.run_industry_and_security_selection import (
    RunIndustryAndSecuritySelection,
    RunIndustryAndSecuritySelectionRequest,
)
from ditto_application.queries.field_admission import (
    FieldAdmissionQuery,
    FieldAdmissionReport,
    FieldAdmissionRequest,
    FieldRequirement,
)
from ditto_application.queries.selection_views import (
    SelectionWorkspaceReceiptView,
    to_selection_workspace_receipt_view,
)

__all__ = [
    "CreateSelectionRunRequest",
    "EtfSelectionSpecDraft",
    "IndustryRotationObservationDraft",
    "SelectionFactorValueDraft",
    "SelectionFactorWeightDraft",
    "SelectionInstrumentDraft",
    "SelectionWorkspaceFacade",
    "StockSelectionSpecDraft",
]

type LimitStateDraft = Literal["normal", "limit_up", "limit_down"]


@dataclass(frozen=True, slots=True)
class IndustryRotationObservationDraft:
    """Application-facing normalized facts for one industry."""

    industry_id: str
    industry_name: str
    relative_strength_5d: float | None
    relative_strength_20d: float | None
    relative_strength_60d: float | None
    advancing_count: int | None
    declining_count: int | None
    member_count: int | None
    trend_score: float | None
    fundamental_score: float | None
    regime_alignment_score: float | None


@dataclass(frozen=True, slots=True)
class SelectionFactorWeightDraft:
    """Application-facing additive factor weight."""

    name: str
    weight: float


@dataclass(frozen=True, slots=True)
class SelectionFactorValueDraft:
    """Application-facing normalized instrument factor value."""

    name: str
    value: float


@dataclass(frozen=True, slots=True)
class StockSelectionSpecDraft:
    """Public stock selection policy before strategy validation."""

    spec_id: str
    spec_version: str
    top_k: int
    min_average_turnover: float
    min_listing_days: int
    factor_weights: tuple[SelectionFactorWeightDraft, ...]
    excluded_limit_states: tuple[LimitStateDraft, ...] = ("limit_up", "limit_down")


@dataclass(frozen=True, slots=True)
class EtfSelectionSpecDraft:
    """Public ETF selection policy before strategy validation."""

    spec_id: str
    spec_version: str
    top_k: int
    min_average_turnover: float
    min_listing_days: int
    factor_weights: tuple[SelectionFactorWeightDraft, ...]
    max_tracking_error: float | None = None
    excluded_limit_states: tuple[LimitStateDraft, ...] = ("limit_up", "limit_down")


type SelectionSpecDraft = StockSelectionSpecDraft | EtfSelectionSpecDraft


@dataclass(frozen=True, slots=True)
class SelectionInstrumentDraft:
    """Public normalized factor and hard-filter facts for one instrument."""

    instrument_id: InstrumentId
    instrument_name: str
    industry_id: str | None
    factor_values: tuple[SelectionFactorValueDraft, ...]
    average_turnover: float | None
    is_st: bool | None
    is_suspended: bool | None
    listing_days: int | None
    limit_state: LimitStateDraft | None
    tracking_error: float | None
    declared_missing_inputs: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CreateSelectionRunRequest:
    """Single temporal identity for rotation plus stock/ETF selection."""

    as_of: datetime
    knowledge_cutoff: datetime
    publication_cutoff: datetime
    rotation_source_snapshot_ids: tuple[str, ...]
    market_context_feature_set_id: str | None
    membership_version: str
    rotation_algorithm_version: str
    industries: tuple[IndustryRotationObservationDraft, ...]
    universe_snapshot_id: str
    selection_source_snapshot_ids: tuple[str, ...]
    selection_spec: SelectionSpecDraft
    seed: int
    instruments: tuple[SelectionInstrumentDraft, ...]
    rotation_missing_inputs: tuple[str, ...] = ()
    data_fields: tuple[FieldRequirement, ...] = ()
    data_from: date | None = None
    data_to: date | None = None


def _factor_weights(
    values: tuple[SelectionFactorWeightDraft, ...],
) -> tuple[SelectionFactorWeight, ...]:
    return tuple(SelectionFactorWeight(item.name, item.weight) for item in values)


def _selection_spec(value: SelectionSpecDraft) -> StockSelectionSpec | EtfSelectionSpec:
    weights = _factor_weights(value.factor_weights)
    excluded_states = tuple(
        SelectionLimitState(item) for item in value.excluded_limit_states
    )
    if isinstance(value, StockSelectionSpecDraft):
        return StockSelectionSpec(
            spec_id=value.spec_id,
            spec_version=value.spec_version,
            top_k=value.top_k,
            min_average_turnover=value.min_average_turnover,
            min_listing_days=value.min_listing_days,
            factor_weights=weights,
            excluded_limit_states=excluded_states,
        )
    return EtfSelectionSpec(
        spec_id=value.spec_id,
        spec_version=value.spec_version,
        top_k=value.top_k,
        min_average_turnover=value.min_average_turnover,
        min_listing_days=value.min_listing_days,
        factor_weights=weights,
        excluded_limit_states=excluded_states,
        max_tracking_error=value.max_tracking_error,
    )


def _rotation_input(value: CreateSelectionRunRequest) -> IndustryRotationInputBundle:
    return IndustryRotationInputBundle(
        as_of=value.as_of,
        knowledge_cutoff=value.knowledge_cutoff,
        publication_cutoff=value.publication_cutoff,
        source_snapshot_ids=value.rotation_source_snapshot_ids,
        market_context_feature_set_id=value.market_context_feature_set_id,
        membership_version=value.membership_version,
        algorithm_version=value.rotation_algorithm_version,
        industries=tuple(
            IndustryRotationIndustryInput(
                industry_id=item.industry_id,
                industry_name=item.industry_name,
                relative_strength_5d=item.relative_strength_5d,
                relative_strength_20d=item.relative_strength_20d,
                relative_strength_60d=item.relative_strength_60d,
                advancing_count=item.advancing_count,
                declining_count=item.declining_count,
                member_count=item.member_count,
                trend_score=item.trend_score,
                fundamental_score=item.fundamental_score,
                regime_alignment_score=item.regime_alignment_score,
            )
            for item in value.industries
        ),
        declared_missing_inputs=value.rotation_missing_inputs,
    )


def _selection_input(value: CreateSelectionRunRequest) -> SelectionInputBundle:
    return SelectionInputBundle(
        as_of=value.as_of,
        knowledge_cutoff=value.knowledge_cutoff,
        publication_cutoff=value.publication_cutoff,
        universe_snapshot_id=value.universe_snapshot_id,
        industry_rotation_snapshot_id=None,
        source_snapshot_ids=value.selection_source_snapshot_ids,
        spec=_selection_spec(value.selection_spec),
        seed=value.seed,
        instruments=tuple(
            SelectionInstrumentInput(
                instrument_id=item.instrument_id,
                instrument_name=item.instrument_name,
                industry_id=item.industry_id,
                factor_values=tuple(
                    SelectionFactorValue(factor.name, factor.value)
                    for factor in item.factor_values
                ),
                average_turnover=item.average_turnover,
                is_st=item.is_st,
                is_suspended=item.is_suspended,
                listing_days=item.listing_days,
                limit_state=(
                    None
                    if item.limit_state is None
                    else SelectionLimitState(item.limit_state)
                ),
                tracking_error=item.tracking_error,
                declared_missing_inputs=item.declared_missing_inputs,
            )
            for item in value.instruments
        ),
    )


class SelectionWorkspaceFacade:
    """Validate public drafts through strategy contracts and execute the process."""

    def __init__(
        self,
        process: RunIndustryAndSecuritySelection,
        *,
        admission: FieldAdmissionQuery,
    ) -> None:
        self._process = process
        self._admission = admission

    def assess_admission(
        self, request: CreateSelectionRunRequest, *, instrument_id: int | None = None
    ) -> FieldAdmissionReport:
        """
        Preview the data gate for a declared or incomplete binding.

        Requests without a complete binding get the missing-binding verdict
        instead of a per-field assessment. During the /api/v1 deprecation
        window create enforces this verdict only for requests that declare
        a data binding.
        """
        if (
            not request.data_fields
            or request.data_from is None
            or request.data_to is None
        ):
            return FieldAdmissionReport(
                False,
                "formal_research",
                (missing_field("data_fields", "CONSUMER_BINDING_MISSING"),),
            )
        instrument_ids = tuple(int(item.instrument_id) for item in request.instruments)
        if instrument_id is not None:
            if instrument_id not in instrument_ids:
                raise AppProcessError(
                    "证券不在输入包中",
                    details={"reason": "invalid_admission_instrument"},
                )
            instrument_ids = (instrument_id,)
        try:
            return assess_selection_fields(
                self._admission,
                FieldAdmissionRequest(
                    fields=tuple(
                        replace(
                            item,
                            consumer_input_hash=consumer_input_digest(
                                selection_field_payload(request, item.consumer_field)
                            ),
                        )
                        for item in request.data_fields
                        if item.consumer_field in _consumed_fields(request)
                    ),
                    instrument_ids=instrument_ids,
                    required_from=request.data_from,
                    required_to=request.data_to,
                    knowledge_cutoff=request.knowledge_cutoff,
                    publication_cutoff=request.publication_cutoff,
                    purpose="formal_research",
                ),
                consumed_fields=_consumed_fields(request),
                instrument_ids=instrument_ids,
                snapshot_bindings=_snapshot_bindings(request),
            )
        except AppQueryError as exc:
            raise AppProcessError(
                str(exc), details={"reason": "invalid_data_admission_request"}
            ) from exc

    def create(
        self,
        request: CreateSelectionRunRequest,
    ) -> SelectionWorkspaceReceiptView:
        """Create an exact saved run or map domain validation to application."""
        try:
            process_request = RunIndustryAndSecuritySelectionRequest(
                rotation_input=_rotation_input(request),
                selection_input=_selection_input(request),
            )
        except (StrategySpecError, ValueError) as exc:
            details = getattr(exc, "details", {})
            raise AppProcessError(
                str(exc),
                details={"reason": "invalid_selection_request", **details},
            ) from exc
        if _declares_data_binding(request):
            admission = self.assess_admission(request)
            if not admission.allowed:
                reasons = sorted(
                    {
                        reason
                        for item in admission.fields
                        for reason in item.reason_codes
                    }
                )
                raise AppProcessError(
                    "数据准入未通过:" + ", ".join(reasons),
                    details={
                        "reason": "SELECTION_DATA_ADMISSION_BLOCKED",
                        "reason_codes": reasons,
                    },
                )
        try:
            receipt = self._process.execute(process_request)
        except StrategySpecError as exc:
            raise AppProcessError(
                str(exc),
                details={"reason": "invalid_selection_request", **exc.details},
            ) from exc
        return to_selection_workspace_receipt_view(
            receipt.industry_rotation,
            receipt.selection_run,
        )


def _declares_data_binding(request: CreateSelectionRunRequest) -> bool:
    """
    Pre-#256 v1 requests carry no binding and keep the ungated legacy path.

    Declaring any binding part opts the request into the admission gate.
    """
    return (
        bool(request.data_fields)
        or request.data_from is not None
        or request.data_to is not None
    )


def _snapshot_bindings(
    request: CreateSelectionRunRequest,
) -> dict[str, tuple[str, frozenset[str]]]:
    """Bind each consumed input to its stage identity and declared sources."""
    selection = ("selection", frozenset(request.selection_source_snapshot_ids))
    rotation = ("rotation", frozenset(request.rotation_source_snapshot_ids))
    return {
        name: (
            selection
            if name == "universe_snapshot_id" or name.startswith("instruments.")
            else rotation
        )
        for name in _consumed_fields(request)
    }


def _consumed_fields(request: CreateSelectionRunRequest) -> frozenset[str]:
    names: set[str] = {"universe_snapshot_id", "membership_version"}
    if request.market_context_feature_set_id is not None:
        names.add("market_context_feature_set_id")
    excluded = {"factor_values", "declared_missing_inputs"}
    if isinstance(request.selection_spec, EtfSelectionSpecDraft):
        excluded.add("is_st")
    if (
        not isinstance(request.selection_spec, EtfSelectionSpecDraft)
        or request.selection_spec.max_tracking_error is None
    ):
        excluded.add("tracking_error")
    weighted = {item.name for item in request.selection_spec.factor_weights}
    for instrument in request.instruments:
        names.update(
            observed_fields(
                instrument, prefix="instruments", exclude=frozenset(excluded)
            )
        )
        names.update(
            f"instruments.factor_values.{item.name}"
            for item in instrument.factor_values
            if item.name in weighted
        )
    for industry in request.industries:
        names.update(observed_fields(industry, prefix="industries"))
    return frozenset(names)
