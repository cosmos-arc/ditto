"""Deterministic signal package generation for manual trading."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, replace
from datetime import UTC, datetime

from ditto_execution.contracts import FillDataPort, IntentDataPort
from ditto_execution.models import SignalRecord
from ditto_strategy.models import ArtifactKind, StrategyArtifactRecord
from ditto_strategy.storage.sqlite.services.strategy_artifact_service import (
    StrategyArtifactService,
)

from ditto_application.exceptions import AppProcessError
from ditto_application.execution_dto import intent_to_record
from ditto_application.processes.execution.manual_sizing import AShareTradeDateResolver
from ditto_application.processes.execution.signal_package_models import (
    SelectionReason,
    SignalPackage,
    SignalPackagePublishRequest,
)
from ditto_application.processes.execution.signal_package_payload import (
    artifact_business_payload as _artifact_business_payload,
)
from ditto_application.processes.execution.signal_package_payload import (
    artifact_intent_ids as _artifact_intent_ids,
)
from ditto_application.processes.execution.signal_package_payload import (
    conflict_artifact_id as _conflict_artifact_id,
)
from ditto_application.processes.execution.signal_package_payload import (
    intent_payload as _intent_payload,
)
from ditto_application.processes.execution.signal_package_payload import (
    intent_sort_key as _intent_sort_key,
)
from ditto_application.processes.execution.signal_package_payload import (
    normalize_dataset_states as _normalize_dataset_states,
)
from ditto_application.processes.execution.signal_package_payload import (
    package_from_artifact as _package_from_artifact,
)
from ditto_application.processes.execution.signal_package_payload import (
    same_intent_payload as _same_intent_payload,
)
from ditto_application.processes.execution.signal_package_payload import (
    selection_reason_payload as _selection_reason_payload,
)
from ditto_application.processes.execution.signal_package_payload import (
    selection_reasons as _selection_reasons,
)
from ditto_application.processes.execution.signal_package_payload import (
    stable_intent_id as _stable_intent_id,
)
from ditto_application.processes.execution.signal_package_payload import (
    target_str as _target_str,
)
from ditto_application.processes.execution.signal_package_payload import (
    validate_factor_values as _validate_factor_values,
)
from ditto_application.processes.execution.signal_package_payload import (
    validate_intent_numbers as _validate_intent_numbers,
)
from ditto_application.processes.execution.signal_package_payload import (
    validate_target_numbers as _validate_target_numbers,
)
from ditto_application.processes.execution.signal_snapshot import SignalSnapshotProcess
from ditto_application.signal_package_contract import (
    compute_signal_package_checksum,
    verify_signal_package_metadata,
)

__all__ = [
    "SelectionReason",
    "SignalPackage",
    "SignalPackagePublishRequest",
    "SignalPackagePublisher",
]


class SignalPackagePublisher:
    """Build deterministic packages and persist their trade intents."""

    def __init__(
        self,
        *,
        snapshot_process: SignalSnapshotProcess,
        intent_port: IntentDataPort,
        fill_port: FillDataPort,
        date_resolver: AShareTradeDateResolver,
        artifact_service: StrategyArtifactService,
    ) -> None:
        self._snapshot = snapshot_process
        self._intent_port = intent_port
        self._fill_port = fill_port
        self._date_resolver = date_resolver
        self._artifact_service = artifact_service

    def publish(self, request: SignalPackagePublishRequest) -> SignalPackage:
        """Publish a deterministic manual-trading signal package."""
        target = request.target
        strategy_version = request.strategy_version
        account_id = request.account_id
        sleeve_id = request.sleeve_id
        decision_date = request.decision_date
        intended_trade_date = request.intended_trade_date
        threshold = request.threshold
        strategy_id = _target_str(target, "strategy_id")
        signal_date = _target_str(target, "trade_date")
        run_id = _target_str(target, "run_id")
        if not strategy_version:
            raise AppProcessError(
                "strategy_version is required for signal package identity"
            )
        if not account_id:
            raise AppProcessError("account_id is required for signal package identity")
        if not sleeve_id:
            raise AppProcessError("sleeve_id is required for signal package identity")
        expected_sleeve_id = f"manual-{account_id}-{strategy_id}"
        if sleeve_id != expected_sleeve_id:
            raise AppProcessError(
                f"sleeve_id must be {expected_sleeve_id} for R1 manual execution"
            )
        expected_batch_key = f"eod-{signal_date}-{strategy_id}-{strategy_version}"
        if run_id != expected_batch_key:
            raise AppProcessError(
                f"batch key must be {expected_batch_key} for R1 EOD package identity"
            )
        factors = request.factor_values
        cash_target = _validate_target_numbers(target, threshold=threshold)
        _validate_factor_values(factors)
        self._date_resolver.validate(
            signal_date=signal_date,
            decision_date=decision_date,
            intended_trade_date=intended_trade_date,
        )
        raw_intents = self._snapshot.generate_intents(
            strategy_id=strategy_id,
            signal_date=signal_date,
            target=target,
            threshold=threshold,
            sizing_contexts=request.sizing_contexts,
        )
        _validate_intent_numbers(raw_intents)
        snapshots = dict(sorted(request.dataset_snapshot_ids.items()))
        datasets = tuple(sorted(set(request.required_datasets)))
        dataset_states = _normalize_dataset_states(request.required_dataset_states)
        factors_used = tuple(sorted(set(request.factor_ids)))
        normalized_risk_flags = tuple(sorted(set(request.risk_flags)))
        sorted_factor_values = {
            instrument_id: dict(sorted(values.items()))
            for instrument_id, values in sorted(factors.items())
        }
        selection_reasons = _selection_reasons(
            target=target,
            factor_ids=factors_used,
            factor_values=sorted_factor_values,
            industry_by_instrument=dict(request.industry_by_instrument),
        )
        business_payload = {
            "account_id": account_id,
            "cash_target": cash_target,
            "dataset_snapshot_ids": snapshots,
            "factor_ids": list(factors_used),
            "factor_values": {
                str(instrument_id): values
                for instrument_id, values in sorted_factor_values.items()
            },
            "intents": [
                _intent_payload(intent)
                for intent in sorted(raw_intents, key=_intent_sort_key)
            ],
            "risk_flags": list(normalized_risk_flags),
            "required_datasets": list(datasets),
            "required_dataset_states": dataset_states,
            "selection_reasons": {
                str(instrument_id): _selection_reason_payload(reason)
                for instrument_id, reason in sorted(selection_reasons.items())
            },
            "signal_date": signal_date,
            "sleeve_id": sleeve_id,
            "decision_date": decision_date,
            "intended_trade_date": intended_trade_date,
            "strategy_id": strategy_id,
            "strategy_version": strategy_version,
        }
        checksum = compute_signal_package_checksum(business_payload)
        checksum_revision = checksum.removeprefix("sha256:")[:12]
        intents = tuple(
            sorted(
                (
                    replace(
                        intent,
                        intent_id=_stable_intent_id(
                            run_id, signal_date, checksum_revision, intent
                        ),
                    )
                    for intent in raw_intents
                ),
                key=lambda item: item.instrument_id,
            )
        )
        artifact_id = (
            f"signal-package-{strategy_id}-v{strategy_version}-"
            f"{signal_date}-{run_id}-{checksum_revision}"
        )
        package = SignalPackage(
            run_id=run_id,
            strategy_id=strategy_id,
            signal_date=signal_date,
            intents=intents,
            dataset_snapshot_ids=snapshots,
            factor_ids=factors_used,
            risk_flags=normalized_risk_flags,
            factor_values=sorted_factor_values,
            selection_reasons=selection_reasons,
            checksum=checksum,
            artifact_id=artifact_id,
            outcome="no_rebalance" if not intents else "completed",
            no_rebalance=not intents,
        )
        return self._publish_candidate(package, business_payload)

    def finalize(self, package: SignalPackage) -> SignalPackage:
        """Atomically expose a staged package after its run is durably completed."""
        candidate = self._artifact_service.get_artifact(package.artifact_id)
        if candidate is None:
            raise AppProcessError("staged signal package disappeared")
        self._validate_candidate(package, candidate)
        if candidate.status == "conflict" and package.outcome == "rerun_conflict":
            return package

        business_payload = _artifact_business_payload(candidate)
        active = self._active_artifacts(package)
        if candidate.status == "active":
            if [item.artifact_id for item in active] == [candidate.artifact_id]:
                return package
            return self._persist_conflict(
                package,
                business_payload,
                active[0] if active else candidate,
                "MULTIPLE_ACTIVE_PACKAGES",
            )

        supersedes = candidate.metadata.get("supersedes_artifact_id")
        if candidate.status == "staged" and supersedes is None:
            return self._activate_initial(package, business_payload, candidate)
        if candidate.status in {"staged", "replacing"} and isinstance(supersedes, str):
            existing = self._artifact_service.get_artifact(supersedes)
            if existing is not None:
                return self._replace_active(package, business_payload, existing)
        return self._abort_candidate(
            package,
            business_payload,
            active[0] if active else candidate,
            "CANDIDATE_STATE_CONFLICT",
        )

    def find_staged(
        self,
        *,
        strategy_id: str,
        run_id: str,
        signal_date: str,
    ) -> SignalPackage | None:
        """Find staged recovery work, or the unique active package for a retry."""
        candidates = sorted(
            (
                artifact
                for artifact in self._artifact_service.list_by_strategy(strategy_id)
                if artifact.artifact_type == ArtifactKind.SIGNAL_PACKAGE
                and artifact.run_id == run_id
                and artifact.status in {"active", "staged", "replacing"}
            ),
            key=lambda artifact: artifact.artifact_id,
        )
        if not candidates:
            return None
        if any(
            artifact.metadata.get("signal_date") != signal_date
            or not verify_signal_package_metadata(artifact.metadata)
            for artifact in candidates
        ):
            raise AppProcessError("recoverable signal package evidence is invalid")
        staged = [item for item in candidates if item.status in {"staged", "replacing"}]
        replacing = [item for item in staged if item.status == "replacing"]
        if len(replacing) > 1 or (not replacing and len(staged) > 1):
            raise AppProcessError("multiple staged signal packages require review")
        if staged:
            return _package_from_artifact(replacing[0] if replacing else staged[0])
        active = [item for item in candidates if item.status == "active"]
        if len(active) > 1:
            raise AppProcessError("multiple active signal packages require review")
        return _package_from_artifact(active[0]) if active else None

    def _publish_candidate(
        self,
        package: SignalPackage,
        business_payload: Mapping[str, object],
    ) -> SignalPackage:
        persisted_conflict = self._find_conflict(
            package.strategy_id,
            package.signal_date,
            package.run_id,
            package.checksum,
        )
        if persisted_conflict is not None:
            return replace(
                package,
                artifact_id=persisted_conflict.artifact_id,
                outcome="rerun_conflict",
            )
        candidate = self._artifact_service.get_artifact(package.artifact_id)
        active = self._active_artifacts(package)
        staged = self._staged_artifacts(package)
        if candidate is not None:
            return self._resume_candidate(package, business_payload, candidate, active)
        return self._stage_new_candidate(
            package,
            business_payload,
            active=active,
            staged=staged,
        )

    def _stage_new_candidate(
        self,
        package: SignalPackage,
        business_payload: Mapping[str, object],
        *,
        active: Sequence[StrategyArtifactRecord],
        staged: Sequence[StrategyArtifactRecord],
    ) -> SignalPackage:
        """Stage a candidate only when no durable candidate with its ID exists."""
        if staged:
            self._save_artifact(
                package,
                business_payload,
                status="archived",
                extra_metadata={
                    "blocked_by_staged_artifact_id": staged[0].artifact_id,
                },
            )
            self._save_intents(package)
            self._supersede_candidate_intents(package)
            return self._persist_conflict(
                package,
                business_payload,
                staged[0],
                "CONCURRENT_STAGED_PACKAGE",
            )
        if len(active) > 1:
            return self._persist_conflict(
                package, business_payload, active[0], "MULTIPLE_ACTIVE_PACKAGES"
            )
        if not active:
            return self._stage_initial(package, business_payload)
        return self._stage_replacement(package, business_payload, active[0])

    def _stage_replacement(
        self,
        package: SignalPackage,
        business_payload: Mapping[str, object],
        existing: StrategyArtifactRecord,
    ) -> SignalPackage:
        """Validate the currently active package before staging its replacement."""
        if existing.metadata.get("checksum") == package.checksum:
            if (
                existing.artifact_id == package.artifact_id
                and verify_signal_package_metadata(existing.metadata)
            ):
                return package
            return self._persist_conflict(
                package, business_payload, existing, "CHECKSUM_MISMATCH"
            )
        if not verify_signal_package_metadata(existing.metadata):
            return self._persist_conflict(
                package, business_payload, existing, "CHECKSUM_MISMATCH"
            )
        if self._replacement_intents(existing, ("pending",)) is None:
            return self._persist_conflict(
                package, business_payload, existing, "UNSAFE_TO_SUPERSEDE"
            )
        self._save_artifact(
            package,
            business_payload,
            status="staged",
            extra_metadata={"supersedes_artifact_id": existing.artifact_id},
        )
        self._save_intents(package)
        return package

    def _active_artifacts(
        self,
        package: SignalPackage,
    ) -> list[StrategyArtifactRecord]:
        return sorted(
            (
                artifact
                for artifact in self._artifact_service.list_by_strategy(
                    package.strategy_id
                )
                if artifact.artifact_type == ArtifactKind.SIGNAL_PACKAGE
                and artifact.status == "active"
                and artifact.metadata.get("signal_date") == package.signal_date
                and artifact.metadata.get("batch_key") == package.run_id
            ),
            key=lambda artifact: artifact.artifact_id,
        )

    def _staged_artifacts(
        self,
        package: SignalPackage,
    ) -> list[StrategyArtifactRecord]:
        return sorted(
            (
                artifact
                for artifact in self._artifact_service.list_by_strategy(
                    package.strategy_id
                )
                if artifact.artifact_type == ArtifactKind.SIGNAL_PACKAGE
                and artifact.status in {"staged", "replacing"}
                and artifact.metadata.get("signal_date") == package.signal_date
                and artifact.metadata.get("batch_key") == package.run_id
            ),
            key=lambda artifact: artifact.artifact_id,
        )

    def _find_conflict(
        self,
        strategy_id: str,
        signal_date: str,
        run_id: str,
        checksum: str,
    ) -> StrategyArtifactRecord | None:
        matches = [
            artifact
            for artifact in self._artifact_service.list_by_strategy(strategy_id)
            if artifact.artifact_type == ArtifactKind.SIGNAL_PACKAGE
            and artifact.status == "conflict"
            and artifact.metadata.get("signal_date") == signal_date
            and artifact.metadata.get("batch_key") == run_id
            and artifact.metadata.get("checksum") == checksum
            and artifact.metadata.get("outcome") == "rerun_conflict"
            and verify_signal_package_metadata(artifact.metadata)
        ]
        return (
            max(
                matches,
                key=lambda artifact: (artifact.created_at, artifact.artifact_id),
            )
            if matches
            else None
        )

    def _resume_candidate(
        self,
        package: SignalPackage,
        business_payload: Mapping[str, object],
        candidate: StrategyArtifactRecord,
        active: Sequence[StrategyArtifactRecord],
    ) -> SignalPackage:
        conflicting = active[0] if active else candidate
        if not verify_signal_package_metadata(candidate.metadata):
            return self._persist_conflict(
                package, business_payload, conflicting, "CHECKSUM_MISMATCH"
            )
        if candidate.status == "active":
            if [item.artifact_id for item in active] == [candidate.artifact_id]:
                return package
            return self._persist_conflict(
                package, business_payload, conflicting, "MULTIPLE_ACTIVE_PACKAGES"
            )
        supersedes = candidate.metadata.get("supersedes_artifact_id")
        if candidate.status == "staged" and supersedes is None:
            self._save_intents(package)
            return package
        if candidate.status in {"staged", "replacing"} and isinstance(supersedes, str):
            existing = self._artifact_service.get_artifact(supersedes)
            if existing is not None:
                self._save_intents(package)
                return package
        return self._persist_conflict(
            package, business_payload, conflicting, "CANDIDATE_STATE_CONFLICT"
        )

    def _stage_initial(
        self,
        package: SignalPackage,
        business_payload: Mapping[str, object],
    ) -> SignalPackage:
        self._save_artifact(package, business_payload, status="staged")
        self._save_intents(package)
        return package

    def _activate_initial(
        self,
        package: SignalPackage,
        business_payload: Mapping[str, object],
        candidate: StrategyArtifactRecord,
    ) -> SignalPackage:
        if self._artifact_service.activate_candidate(package.artifact_id):
            return package
        active = self._active_artifacts(package)
        refreshed = self._artifact_service.get_artifact(package.artifact_id)
        if refreshed is not None and refreshed.status == "active":
            return package
        return self._abort_candidate(
            package,
            business_payload,
            active[0] if active else candidate,
            "CONCURRENT_BATCH_PUBLICATION",
        )

    def _validate_candidate(
        self,
        package: SignalPackage,
        candidate: StrategyArtifactRecord,
    ) -> None:
        if (
            candidate.artifact_type != ArtifactKind.SIGNAL_PACKAGE
            or candidate.strategy_id != package.strategy_id
            or candidate.run_id != package.run_id
            or candidate.metadata.get("signal_date") != package.signal_date
            or candidate.metadata.get("checksum") != package.checksum
            or not verify_signal_package_metadata(candidate.metadata)
        ):
            raise AppProcessError("signal package candidate evidence is invalid")

    def _replace_active(
        self,
        package: SignalPackage,
        business_payload: Mapping[str, object],
        existing: StrategyArtifactRecord,
    ) -> SignalPackage:
        candidate = self._artifact_service.get_artifact(package.artifact_id)
        if candidate is None:
            raise AppProcessError("staged signal package disappeared")
        if (
            candidate.status == "staged"
            and not self._artifact_service.claim_replacement(
                candidate.artifact_id,
                existing.artifact_id,
            )
        ):
            candidate = self._artifact_service.get_artifact(candidate.artifact_id)
            if candidate is None or candidate.status != "replacing":
                return self._abort_replacement(
                    package, business_payload, existing, "CONCURRENT_BATCH_PUBLICATION"
                )
        old_intents = self._replacement_intents(
            existing,
            ("pending", "superseded"),
        )
        if old_intents is None:
            return self._abort_replacement(
                package, business_payload, existing, "UNSAFE_TO_SUPERSEDE"
            )
        for intent in old_intents:
            if intent.status == "pending" and not self._supersede_intent(
                intent.intent_id
            ):
                return self._abort_replacement(
                    package, business_payload, existing, "INTENT_TRANSITION_CONFLICT"
                )
        if self._has_fills(existing, {intent.intent_id for intent in old_intents}):
            return self._abort_replacement(
                package, business_payload, existing, "FILL_APPEARED_DURING_REPLACEMENT"
            )
        return self._activate_replacement(package, business_payload, existing)

    def _activate_replacement(
        self,
        package: SignalPackage,
        business_payload: Mapping[str, object],
        existing: StrategyArtifactRecord,
    ) -> SignalPackage:
        """Commit the artifact swap after the old pending intents are superseded."""
        if self._artifact_service.activate_candidate(
            package.artifact_id,
            replaced_artifact_id=existing.artifact_id,
        ):
            return package
        refreshed = self._artifact_service.get_artifact(package.artifact_id)
        old = self._artifact_service.get_artifact(existing.artifact_id)
        if (
            refreshed is not None
            and refreshed.status == "active"
            and old is not None
            and old.status == "archived"
        ):
            return package
        return self._abort_replacement(
            package, business_payload, existing, "ARTIFACT_TRANSITION_CONFLICT"
        )

    def _replacement_intents(
        self,
        existing: StrategyArtifactRecord,
        allowed_statuses: tuple[str, ...],
    ) -> list[SignalRecord] | None:
        artifact_intent_ids = _artifact_intent_ids(existing)
        if artifact_intent_ids is None:
            return None
        old_intents = [
            intent
            for intent in self._intent_port.list_intents(
                existing.strategy_id,
                signal_date=str(existing.metadata.get("signal_date", "")),
            )
            if intent.intent_id in artifact_intent_ids
        ]
        if {intent.intent_id for intent in old_intents} != artifact_intent_ids:
            return None
        if any(intent.status not in allowed_statuses for intent in old_intents):
            return None
        if self._has_fills(existing, artifact_intent_ids):
            return None
        return old_intents

    def _has_fills(
        self,
        existing: StrategyArtifactRecord,
        intent_ids: set[str],
    ) -> bool:
        return any(
            self._fill_port.list_fills(existing.strategy_id, intent_id=intent_id)
            for intent_id in sorted(intent_ids)
        )

    def _supersede_intent(self, intent_id: str) -> bool:
        if self._intent_port.update_intent_status(
            intent_id,
            "superseded",
            expected_current=("pending",),
        ):
            return True
        current = self._intent_port.get_intent(intent_id)
        return current is not None and current.status == "superseded"

    def _abort_replacement(
        self,
        package: SignalPackage,
        business_payload: Mapping[str, object],
        existing: StrategyArtifactRecord,
        reason: str,
    ) -> SignalPackage:
        current_existing = self._artifact_service.get_artifact(existing.artifact_id)
        if current_existing is not None and current_existing.status == "active":
            self._restore_pending(tuple(_artifact_intent_ids(existing) or ()))
        self._supersede_candidate_intents(package)
        self._artifact_service.transition_artifact(
            package.artifact_id,
            "archived",
            expected_current=("staged", "replacing"),
        )
        return self._persist_conflict(package, business_payload, existing, reason)

    def _abort_candidate(
        self,
        package: SignalPackage,
        business_payload: Mapping[str, object],
        conflicting: StrategyArtifactRecord,
        reason: str,
    ) -> SignalPackage:
        self._supersede_candidate_intents(package)
        self._artifact_service.transition_artifact(
            package.artifact_id,
            "archived",
            expected_current=("staged", "replacing"),
        )
        return self._persist_conflict(
            package,
            business_payload,
            conflicting,
            reason,
        )

    def _supersede_candidate_intents(self, package: SignalPackage) -> None:
        for intent in package.intents:
            self._intent_port.update_intent_status(
                intent.intent_id,
                "superseded",
                expected_current=("pending",),
            )

    def _persist_conflict(
        self,
        package: SignalPackage,
        business_payload: Mapping[str, object],
        existing: StrategyArtifactRecord | None,
        reason: str,
    ) -> SignalPackage:
        if existing is None:
            raise AppProcessError(
                "signal package transition lost all durable artifacts"
            )
        conflict = replace(
            package,
            artifact_id=_conflict_artifact_id(package, existing, reason),
            outcome="rerun_conflict",
        )
        self._save_artifact(
            conflict,
            business_payload,
            status="conflict",
            extra_metadata={
                "candidate_artifact_id": package.artifact_id,
                "conflicting_artifact_id": existing.artifact_id,
                "conflict_reason": reason,
            },
        )
        return conflict

    def _save_intents(self, package: SignalPackage) -> None:
        for intent in package.intents:
            record = intent_to_record(intent)
            existing = self._intent_port.get_intent(intent.intent_id)
            if existing is None:
                self._intent_port.save_intent(record)
            elif not _same_intent_payload(existing, record):
                raise AppProcessError(
                    "signal intent identity conflicts with stored payload"
                )

    def _restore_pending(self, intent_ids: Sequence[str]) -> None:
        for intent_id in sorted(intent_ids, reverse=True):
            self._intent_port.update_intent_status(
                intent_id,
                "pending",
                expected_current=("superseded",),
            )

    def _save_artifact(
        self,
        package: SignalPackage,
        business_payload: Mapping[str, object],
        *,
        status: str,
        extra_metadata: Mapping[str, object] | None = None,
    ) -> StrategyArtifactRecord:
        metadata = {
            **business_payload,
            "schema_version": "1.0",
            "business_payload": dict(business_payload),
            "batch_key": package.run_id,
            "checksum": package.checksum,
            "no_rebalance": package.no_rebalance,
            "outcome": package.outcome,
            "intents": [asdict(intent) for intent in package.intents],
            **(extra_metadata or {}),
        }
        return self._artifact_service.save_artifact(
            StrategyArtifactRecord(
                artifact_id=package.artifact_id,
                strategy_id=package.strategy_id,
                run_id=package.run_id,
                artifact_type=ArtifactKind.SIGNAL_PACKAGE,
                file_path=f"inline://signal-packages/{package.artifact_id}",
                metadata=metadata,
                status=status,
                created_at=datetime.now(UTC).isoformat(),
            )
        )
