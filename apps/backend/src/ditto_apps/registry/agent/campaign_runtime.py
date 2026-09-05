"""Apps composition adapter for durable governed Campaign public surfaces."""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping
from datetime import datetime
from types import MappingProxyType
from typing import Never, Protocol, cast

from ditto_agent.storage.sqlite.errors import (
    AgentConflictError,
    AgentPersistenceError,
)
from ditto_agent.storage.sqlite.records import (
    IdempotencyDisposition,
    IdempotencyRecord,
    IdempotencyReservation,
)
from ditto_analysis.errors import AnalysisError, ExperimentConflictError
from ditto_analysis.experiments.campaign_persistence import (
    CampaignEventRecord,
    CampaignManifestRecord,
    CampaignReaderProtocol,
)
from ditto_analysis.experiments.models import ExperimentId
from ditto_application.agent_campaign_runtime import (
    CampaignApproveCommand,
    CampaignBudgetView,
    CampaignCancelCommand,
    CampaignCreateCommand,
    CampaignEventView,
    CampaignGuardrailView,
    CampaignInvalidRequest,
    CampaignListView,
    CampaignRequestConflict,
    CampaignResourceNotFound,
    CampaignRuntimePort,
    CampaignRuntimeUnavailable,
    CampaignSandboxBudgetView,
    CampaignStatus,
    CampaignUsageView,
    CampaignValidationCommand,
    CampaignValidationView,
    CampaignView,
)
from ditto_application.commands.campaign_manifest import (
    build_research_campaign_manifest,
    validate_research_campaign_manifest_step,
)
from ditto_application.exceptions import AppCommandError, AppProcessError
from ditto_application.mutation_idempotency import canonical_request_hash
from ditto_application.processes.experiments._autonomous_campaign_contracts import (
    CampaignAuthorizationProof,
    datetime_from_epoch_us,
    decode_campaign_detail,
)
from ditto_application.processes.experiments.autonomous_campaign import (
    AutonomousCampaignCoordinator,
)

_CREATE_SCOPE = "agent.campaign.create"
_APPROVE_SCOPE = "agent.campaign.approve"
_CANCEL_SCOPE = "agent.campaign.cancel"
_MAX_PAGE_SIZE = 100


def _page_bounds(limit: int, offset: int) -> None:
    if type(limit) is not int or limit < 1 or limit > _MAX_PAGE_SIZE:
        raise CampaignInvalidRequest(
            "Campaign page limit is invalid",
            reason_code="campaign_pagination_invalid",
        )
    if type(offset) is not int or offset < 0:
        raise CampaignInvalidRequest(
            "Campaign page offset is invalid",
            reason_code="campaign_pagination_invalid",
        )


class _IdempotencyReader(Protocol):
    def get_idempotency(
        self,
        scope: str,
        idempotency_key: str,
    ) -> IdempotencyRecord | None: ...


class _IdempotencyWriter(Protocol):
    def reserve_idempotency(
        self,
        *,
        scope: str,
        idempotency_key: str,
        request_hash: str,
        occurred_at: datetime,
    ) -> IdempotencyReservation: ...

    def complete_idempotency(
        self,
        *,
        scope: str,
        idempotency_key: str,
        expected_request_hash: str,
        result_identity: str,
        occurred_at: datetime,
    ) -> IdempotencyRecord: ...


def _raise_agent_persistence(exc: AgentPersistenceError) -> Never:
    if isinstance(exc, AgentConflictError):
        raise CampaignRequestConflict(
            str(exc),
            reason_code=exc.reason_code,
        ) from exc
    raise CampaignRuntimeUnavailable(exc.reason_code) from exc


def _raise_application(exc: AppCommandError | AppProcessError) -> Never:
    reason = str(exc.details.get("reason", "campaign_runtime_failed"))
    if reason == "campaign_not_found":
        raise CampaignResourceNotFound(str(exc), reason_code=reason) from exc
    if reason in {
        "campaign_authority_mismatch",
        "campaign_manifest_hash_drift",
        "campaign_authorization_replay_conflict",
        "campaign_terminal",
        "campaign_candidate_budget_exhausted",
        "campaign_fold_budget_exhausted",
        "campaign_generation_budget_exhausted",
        "campaign_lease_lost",
    }:
        raise CampaignRequestConflict(str(exc), reason_code=reason) from exc
    raise CampaignInvalidRequest(str(exc), reason_code=reason) from exc


def _root(record_payload: bytes) -> Mapping[str, object]:
    return decode_campaign_detail(record_payload)


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise CampaignRuntimeUnavailable(f"campaign_{field}_projection_invalid")
    return cast("Mapping[str, object]", value)


def _integer(value: object, field: str) -> int:
    if type(value) is not int or value <= 0:
        raise CampaignRuntimeUnavailable(f"campaign_{field}_projection_invalid")
    return value


def _string(value: object, field: str) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise CampaignRuntimeUnavailable(f"campaign_{field}_projection_invalid")
    return value


def _validated_campaign_event_views(
    events: tuple[CampaignEventRecord, ...],
    *,
    campaign_id: str,
) -> tuple[CampaignEventView, ...]:
    """Validate the complete persisted status chain before slicing a replay."""
    views: list[CampaignEventView] = []
    previous_status: str | None = None
    try:
        for expected_ordinal, event in enumerate(events):
            if (
                str(event.campaign_id) != campaign_id
                or event.ordinal != expected_ordinal
                or event.previous_status != previous_status
            ):
                raise CampaignRuntimeUnavailable("campaign_event_stream_invalid")
            view = CampaignEventView(
                event_id=event.ordinal + 1,
                durable_event_id=event.event_id,
                campaign_id=campaign_id,
                event_type=event.event_type,
                previous_status=event.previous_status,
                status=CampaignStatus(event.status),
                payload_hash=hashlib.sha256(event.detail_payload).hexdigest(),
                occurred_at=datetime_from_epoch_us(event.occurred_at_epoch_us),
            )
            views.append(view)
            previous_status = event.status
    except CampaignRuntimeUnavailable:
        raise
    except (TypeError, ValueError) as exc:
        raise CampaignRuntimeUnavailable("campaign_event_stream_invalid") from exc
    return tuple(views)


def _validate_campaign(command: CampaignValidationCommand) -> CampaignValidationView:
    if type(command) is not CampaignValidationCommand:
        raise CampaignInvalidRequest(
            "Campaign validation command is invalid",
            reason_code="campaign_manifest_invalid",
        )
    try:
        manifest = validate_research_campaign_manifest_step(
            command.step,
            command.document,
        )
    except (AppCommandError, AnalysisError, ValueError) as exc:
        raise CampaignInvalidRequest(
            str(exc),
            reason_code="campaign_manifest_invalid",
        ) from exc
    if manifest is None:
        return CampaignValidationView(
            step=command.step,
            canonical_manifest=None,
            manifest_hash=None,
        )
    canonical = decode_campaign_detail(manifest.canonical_payload.json_bytes)
    return CampaignValidationView(
        step=command.step,
        canonical_manifest=MappingProxyType(dict(canonical)),
        manifest_hash=str(manifest.manifest_hash),
    )


class DisabledCampaignRuntime(CampaignRuntimePort):
    """Fail-closed surface used until Campaign execution is explicitly enabled."""

    @staticmethod
    def _unavailable() -> Never:
        raise CampaignRuntimeUnavailable("agent_campaign_feature_disabled")

    def create_campaign(self, command: CampaignCreateCommand) -> CampaignView:
        """Reject Campaign creation while disabled."""
        self._unavailable()

    def validate_campaign(
        self,
        command: CampaignValidationCommand,
    ) -> CampaignValidationView:
        """Validate immutable inputs independently of runtime availability."""
        return _validate_campaign(command)

    def approve_campaign(self, command: CampaignApproveCommand) -> CampaignView:
        """Reject Campaign approval while disabled."""
        self._unavailable()

    def get_campaign(self, campaign_id: str) -> CampaignView:
        """Reject Campaign reads while disabled."""
        self._unavailable()

    def list_campaigns(
        self,
        *,
        status: CampaignStatus | None,
        limit: int,
        offset: int,
    ) -> CampaignListView:
        """Return a stable empty history when no Campaign store is configured."""
        _page_bounds(limit, offset)
        return CampaignListView(items=(), total=0, limit=limit, offset=offset)

    def list_campaign_events(
        self,
        campaign_id: str,
        *,
        after_event_id: int | None = None,
    ) -> tuple[CampaignEventView, ...]:
        """Reject Campaign event replay while disabled."""
        self._unavailable()

    def cancel_campaign(self, command: CampaignCancelCommand) -> CampaignView:
        """Reject Campaign cancellation while disabled."""
        self._unavailable()


class PersistedCampaignRuntime(CampaignRuntimePort):
    """Idempotent public runtime over Application coordination and durable stores."""

    def __init__(
        self,
        *,
        coordinator: AutonomousCampaignCoordinator,
        reader: CampaignReaderProtocol,
        idempotency_reader: _IdempotencyReader,
        idempotency_writer: _IdempotencyWriter,
        clock: Callable[[], datetime],
    ) -> None:
        self._coordinator = coordinator
        self._reader = reader
        self._idempotency_reader = idempotency_reader
        self._idempotency_writer = idempotency_writer
        self._clock = clock

    def _idempotent(
        self,
        *,
        scope: str,
        key: str,
        request_hash: str,
        result_identity: str,
        operation: Callable[[datetime], object],
    ) -> CampaignView:
        try:
            reservation = self._idempotency_writer.reserve_idempotency(
                scope=scope,
                idempotency_key=key,
                request_hash=request_hash,
                occurred_at=self._clock(),
            )
            durable_identity = reservation.record.result_identity
            if (
                reservation.disposition is IdempotencyDisposition.REPLAY
                and durable_identity is not None
            ):
                if durable_identity != result_identity:
                    raise CampaignRequestConflict(
                        "Campaign idempotency result identity drifted",
                        reason_code="agent_idempotency_result_conflict",
                    )
                return self.get_campaign(durable_identity)
            operation(reservation.record.created_at)
            self._idempotency_writer.complete_idempotency(
                scope=scope,
                idempotency_key=key,
                expected_request_hash=request_hash,
                result_identity=result_identity,
                occurred_at=self._clock(),
            )
            durable = self._idempotency_reader.get_idempotency(scope, key)
            if durable is None or durable.result_identity != result_identity:
                raise CampaignRuntimeUnavailable(
                    "agent_campaign_idempotency_result_missing"
                )
            return self.get_campaign(result_identity)
        except CampaignRequestConflict:
            raise
        except AgentPersistenceError as exc:
            _raise_agent_persistence(exc)

    def create_campaign(self, command: CampaignCreateCommand) -> CampaignView:
        """Create or recover a DRAFT from the complete immutable document."""
        if type(command) is not CampaignCreateCommand:
            raise CampaignInvalidRequest(
                "Campaign create command is invalid",
                reason_code="campaign_request_invalid",
            )
        try:
            manifest = build_research_campaign_manifest(command.manifest_document)
            return self._idempotent(
                scope=_CREATE_SCOPE,
                key=command.idempotency_key,
                request_hash=command.request_hash,
                result_identity=str(manifest.campaign_id),
                operation=lambda occurred_at: self._coordinator.create(
                    manifest,
                    occurred_at=occurred_at,
                ),
            )
        except (AppCommandError, AppProcessError) as exc:
            _raise_application(exc)
        except AnalysisError as exc:
            raise CampaignInvalidRequest(
                str(exc),
                reason_code=str(
                    exc.details.get("reason_code", "campaign_manifest_invalid")
                ),
            ) from exc
        except ValueError as exc:
            raise CampaignInvalidRequest(
                "Campaign create command is invalid",
                reason_code="campaign_request_invalid",
            ) from exc

    def validate_campaign(
        self,
        command: CampaignValidationCommand,
    ) -> CampaignValidationView:
        """Validate immutable inputs without reserving or writing durable state."""
        return _validate_campaign(command)

    def _approval_material(
        self,
        campaign_id: str,
    ) -> tuple[
        CampaignManifestRecord,
        Mapping[str, object],
        Mapping[str, object],
        list[str],
    ]:
        try:
            record = self._reader.get_campaign(ExperimentId(campaign_id))
            if record is None:
                raise CampaignResourceNotFound(
                    "Campaign does not exist",
                    reason_code="campaign_not_found",
                )
            root = _root(record.manifest_payload)
            budget = _mapping(root.get("budget"), "budget")
            tools = root.get("allowed_tools")
            if not isinstance(tools, list):
                raise CampaignRuntimeUnavailable(
                    "campaign_allowed_tools_projection_invalid"
                )
            raw_tools = cast("list[object]", tools)
            if any(type(item) is not str for item in raw_tools):
                raise CampaignRuntimeUnavailable(
                    "campaign_allowed_tools_projection_invalid"
                )
            return record, root, budget, cast("list[str]", raw_tools)
        except (CampaignResourceNotFound, CampaignRuntimeUnavailable):
            raise
        except AnalysisError as exc:
            raise CampaignRuntimeUnavailable(
                str(exc.details.get("reason_code", "campaign_persistence_failed"))
            ) from exc
        except (AppProcessError, KeyError, TypeError, ValueError) as exc:
            raise CampaignRuntimeUnavailable("campaign_projection_invalid") from exc

    def approve_campaign(self, command: CampaignApproveCommand) -> CampaignView:
        """Issue and persist exact finite authority after a human decision."""
        if type(command) is not CampaignApproveCommand:
            raise CampaignInvalidRequest(
                "Campaign approval command is invalid",
                reason_code="campaign_request_invalid",
            )
        record, root, budget, tools = self._approval_material(command.campaign_id)

        def approve(occurred_at: datetime) -> None:
            if command.expires_at <= occurred_at:
                raise CampaignInvalidRequest(
                    "Campaign approval expiry must be in the future",
                    reason_code="campaign_approval_expired",
                )
            authority_payload = {
                "campaign_manifest_hash": str(record.manifest_hash),
                "search_axis": root.get("search_axis"),
                "allowed_tools": tools,
                "source_snapshot_id": _mapping(
                    root.get("experiment_plan"), "experiment_plan"
                ).get("snapshot_id"),
                "budget": budget,
            }
            authority_hash = canonical_request_hash(authority_payload)
            authorization_hash = canonical_request_hash(
                {
                    "authority_hash": authority_hash,
                    "authorized_by": command.operator_id,
                    "authorized_at": occurred_at.isoformat(
                        timespec="microseconds"
                    ).replace("+00:00", "Z"),
                    "expires_at": command.expires_at.isoformat(
                        timespec="microseconds"
                    ).replace("+00:00", "Z"),
                }
            )
            proof = CampaignAuthorizationProof.issue(
                authorization_id=f"campaign-auth-{authorization_hash[:24]}",
                authorization_hash=authorization_hash,
                authority_hash=authority_hash,
                authorized_by=command.operator_id,
                authorized_at=occurred_at,
                expires_at=command.expires_at,
                campaign_manifest_hash=str(record.manifest_hash),
                search_axis=cast("str", root["search_axis"]),
                allowed_tools=tools,
                source_snapshot_id=cast(
                    "str",
                    _mapping(root["experiment_plan"], "experiment_plan")["snapshot_id"],
                ),
                candidate_limit=_integer(
                    budget.get("candidate_limit"), "candidate_limit"
                ),
                fold_run_limit=_integer(budget.get("fold_run_limit"), "fold_run_limit"),
                generation_limit=_integer(
                    budget.get("generation_limit"), "generation_limit"
                ),
                concurrent_sandbox_limit=_integer(
                    budget.get("concurrent_sandbox_limit"),
                    "concurrent_sandbox_limit",
                ),
                wall_time_limit_seconds=_integer(
                    budget.get("wall_time_limit_seconds"),
                    "wall_time_limit_seconds",
                ),
                temporary_storage_limit_bytes=_integer(
                    budget.get("temporary_storage_limit_bytes"),
                    "temporary_storage_limit_bytes",
                ),
                model_spend_limit_usd_micros=_integer(
                    budget.get("model_spend_limit_usd_micros"),
                    "model_spend_limit_usd_micros",
                ),
            )
            exact_durable_replay = any(
                decode_campaign_detail(event.detail_payload).get("verification_hash")
                == proof.verification_hash
                for event in self._reader.list_campaign_events(
                    ExperimentId(command.campaign_id)
                )
                if event.event_type == "campaign_authorized"
            )
            if command.expires_at <= self._clock() and not exact_durable_replay:
                raise CampaignInvalidRequest(
                    "Campaign approval expiry has elapsed",
                    reason_code="campaign_approval_expired",
                )
            self._coordinator.approve(
                ExperimentId(command.campaign_id),
                proof,
                expected_manifest_hash=command.expected_manifest_hash,
                occurred_at=occurred_at,
            )

        try:
            return self._idempotent(
                scope=_APPROVE_SCOPE,
                key=command.idempotency_key,
                request_hash=command.request_hash,
                result_identity=command.campaign_id,
                operation=approve,
            )
        except (AppCommandError, AppProcessError) as exc:
            _raise_application(exc)
        except AnalysisError as exc:
            raise CampaignRuntimeUnavailable(
                str(exc.details.get("reason_code", "campaign_persistence_failed"))
            ) from exc

    def get_campaign(self, campaign_id: str) -> CampaignView:
        """Project immutable manifest, authority, budget, and durable counters."""
        try:
            identity = ExperimentId(campaign_id)
            record = self._reader.get_campaign(identity)
            if record is None:
                raise CampaignResourceNotFound(
                    "Campaign does not exist",
                    reason_code="campaign_not_found",
                )
            state = self._coordinator.get_state(identity)
            root = _root(record.manifest_payload)
            plan = _mapping(root.get("experiment_plan"), "experiment_plan")
            budget = _mapping(root.get("budget"), "budget")
            sandbox = _mapping(
                budget.get("sandbox_resource_limits"),
                "sandbox_resource_limits",
            )
            events = self._reader.list_campaign_events(identity)
            authorization = next(
                (
                    decode_campaign_detail(event.detail_payload)
                    for event in events
                    if event.event_type == "campaign_authorized"
                ),
                None,
            )
            proof = (
                None
                if authorization is None
                else _mapping(authorization.get("proof"), "authorization")
            )
            tools = root.get("allowed_tools")
            if not isinstance(tools, list):
                raise CampaignRuntimeUnavailable(
                    "campaign_allowed_tools_projection_invalid"
                )
            raw_tools = cast("list[object]", tools)
            if any(type(item) is not str for item in raw_tools):
                raise CampaignRuntimeUnavailable(
                    "campaign_allowed_tools_projection_invalid"
                )
            expires = None if proof is None else proof.get("expires_at")
            last_event = None if not events else events[-1]
            exhausted_reason = (
                "campaign_budget_exhausted"
                if state.status.value == "paused_budget"
                else None
            )
            return CampaignView(
                campaign_id=campaign_id,
                status=CampaignStatus(state.status.value),
                manifest_hash=str(record.manifest_hash),
                authorization_hash=state.authorization_hash,
                authorized_by=(
                    None if proof is None else cast("str", proof.get("authorized_by"))
                ),
                authorization_expires_at=(
                    None
                    if type(expires) is not str
                    else datetime.fromisoformat(expires.replace("Z", "+00:00"))
                ),
                search_axis=cast("str", root["search_axis"]),
                source_snapshot_id=cast("str", plan["snapshot_id"]),
                allowed_tools=tuple(cast("list[str]", raw_tools)),
                budget=CampaignBudgetView(
                    candidate_limit=_integer(
                        budget.get("candidate_limit"), "candidate_limit"
                    ),
                    fold_run_limit=_integer(
                        budget.get("fold_run_limit"), "fold_run_limit"
                    ),
                    generation_limit=_integer(
                        budget.get("generation_limit"), "generation_limit"
                    ),
                    concurrent_sandbox_limit=_integer(
                        budget.get("concurrent_sandbox_limit"),
                        "concurrent_sandbox_limit",
                    ),
                    wall_time_limit_seconds=_integer(
                        budget.get("wall_time_limit_seconds"),
                        "wall_time_limit_seconds",
                    ),
                    temporary_storage_limit_bytes=_integer(
                        budget.get("temporary_storage_limit_bytes"),
                        "temporary_storage_limit_bytes",
                    ),
                    model_spend_limit_usd_micros=_integer(
                        budget.get("model_spend_limit_usd_micros"),
                        "model_spend_limit_usd_micros",
                    ),
                    sandbox_resource_limits=CampaignSandboxBudgetView(
                        cpu_count=_integer(sandbox.get("cpu_count"), "cpu_count"),
                        memory_bytes=_integer(
                            sandbox.get("memory_bytes"), "memory_bytes"
                        ),
                        process_limit=_integer(
                            sandbox.get("process_limit"), "process_limit"
                        ),
                        temporary_storage_bytes=_integer(
                            sandbox.get("temporary_storage_bytes"),
                            "temporary_storage_bytes",
                        ),
                        wall_time_seconds=_integer(
                            sandbox.get("wall_time_seconds"), "wall_time_seconds"
                        ),
                        output_bytes=_integer(
                            sandbox.get("output_bytes"), "output_bytes"
                        ),
                    ),
                ),
                best_primary_metric_value=state.best_primary_metric_value,
                no_improvement_generations=state.no_improvement_generations,
                statistical_trial_count=state.statistical_trial_count,
                operational_attempt_count=state.operational_attempt_count,
                revision=state.revision,
                canonical_manifest=MappingProxyType(dict(root)),
                objective=_string(root.get("objective"), "objective"),
                output_summary=None,
                tool_records=(),
                evidence_refs=(),
                artifact_refs=(),
                guardrail=CampaignGuardrailView(
                    status="unknown",
                    reason_code="campaign_guardrail_projection_unavailable",
                ),
                usage=CampaignUsageView(
                    statistical_trial_count=state.statistical_trial_count,
                    operational_attempt_count=state.operational_attempt_count,
                    no_improvement_generations=state.no_improvement_generations,
                    model_spend_usd_micros=None,
                    exhausted_reason=exhausted_reason,
                ),
                event_cursor=(1 if last_event is None else last_event.ordinal + 1),
                projection_state="partial",
                projection_reason="campaign_result_projection_unavailable",
                projection_version=(
                    1 if last_event is None else last_event.ordinal + 1
                ),
                projection_updated_at=(
                    datetime_from_epoch_us(record.created_at_epoch_us)
                    if last_event is None
                    else datetime_from_epoch_us(last_event.occurred_at_epoch_us)
                ),
            )
        except CampaignResourceNotFound:
            raise
        except AppProcessError as exc:
            _raise_application(exc)
        except ExperimentConflictError as exc:
            raise CampaignRequestConflict(
                str(exc),
                reason_code=str(exc.details.get("reason_code", "campaign_conflict")),
            ) from exc
        except AnalysisError as exc:
            raise CampaignRuntimeUnavailable(
                str(exc.details.get("reason_code", "campaign_persistence_failed"))
            ) from exc
        except (KeyError, TypeError, ValueError) as exc:
            raise CampaignRuntimeUnavailable("campaign_projection_invalid") from exc

    def list_campaigns(
        self,
        *,
        status: CampaignStatus | None,
        limit: int,
        offset: int,
    ) -> CampaignListView:
        """Recover durable Campaign projections without caller-held IDs."""
        _page_bounds(limit, offset)
        try:
            records = self._reader.list_campaigns()
        except AnalysisError as exc:
            raise CampaignRuntimeUnavailable(
                str(exc.details.get("reason_code", "campaign_persistence_failed"))
            ) from exc
        projected = tuple(
            self.get_campaign(str(record.campaign_id)) for record in records
        )
        filtered = tuple(
            campaign
            for campaign in projected
            if status is None or campaign.status is status
        )
        return CampaignListView(
            items=filtered[offset : offset + limit],
            total=len(filtered),
            limit=limit,
            offset=offset,
        )

    def list_campaign_events(
        self,
        campaign_id: str,
        *,
        after_event_id: int | None = None,
    ) -> tuple[CampaignEventView, ...]:
        """Replay persisted event rows without executing Campaign work."""
        if after_event_id is not None and (
            type(after_event_id) is not int or after_event_id < 0
        ):
            raise CampaignInvalidRequest(
                "Last-Event-ID must be a non-negative integer",
                reason_code="campaign_event_cursor_invalid",
            )
        try:
            identity = ExperimentId(campaign_id)
            if self._reader.get_campaign(identity) is None:
                raise CampaignResourceNotFound(
                    "Campaign does not exist",
                    reason_code="campaign_not_found",
                )
            events = self._reader.list_campaign_events(identity)
        except CampaignResourceNotFound:
            raise
        except AnalysisError as exc:
            raise CampaignRuntimeUnavailable(
                str(exc.details.get("reason_code", "campaign_persistence_failed"))
            ) from exc
        views = _validated_campaign_event_views(events, campaign_id=campaign_id)
        if after_event_id not in (None, 0) and all(
            event.event_id != after_event_id for event in views
        ):
            raise CampaignInvalidRequest(
                "Last-Event-ID is not retained by this Campaign",
                reason_code="campaign_event_cursor_expired",
            )
        return tuple(
            event
            for event in views
            if after_event_id is None or event.event_id > after_event_id
        )

    def cancel_campaign(self, command: CampaignCancelCommand) -> CampaignView:
        """Cancel or recover cancellation without duplicate scheduler calls."""
        if type(command) is not CampaignCancelCommand:
            raise CampaignInvalidRequest(
                "Campaign cancellation command is invalid",
                reason_code="campaign_request_invalid",
            )
        try:
            return self._idempotent(
                scope=_CANCEL_SCOPE,
                key=command.idempotency_key,
                request_hash=command.request_hash,
                result_identity=command.campaign_id,
                operation=lambda occurred_at: self._coordinator.cancel(
                    ExperimentId(command.campaign_id),
                    authorization_hash=command.expected_authorization_hash,
                    occurred_at=occurred_at,
                ),
            )
        except (AppCommandError, AppProcessError) as exc:
            _raise_application(exc)
        except AnalysisError as exc:
            raise CampaignRuntimeUnavailable(
                str(exc.details.get("reason_code", "campaign_persistence_failed"))
            ) from exc


__all__ = ["DisabledCampaignRuntime", "PersistedCampaignRuntime"]
