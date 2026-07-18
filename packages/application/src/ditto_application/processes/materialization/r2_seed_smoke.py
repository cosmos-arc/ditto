"""Deterministic certified-snapshot smoke for the designated R1 stock seed."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from hashlib import sha256

from ditto_data.catalog.certification import CertificationReader
from ditto_data.catalog.contracts import DataCatalogReader
from ditto_features.factors.production_guard import (
    CertifiedSeedFactorContract,
    validate_certified_seed_factor_contract,
)

from ditto_application.exceptions import AppProcessError
from ditto_application.processes.materialization.catalog_dependency_validation import (
    CertifiedCatalogDependencySelection,
    validate_certified_catalog_dependencies,
)

__all__ = [
    "R2SeedDatasetSnapshots",
    "R2SeedSmokeReport",
    "R2SeedSmokeRequest",
    "R2SeedSmokeRunner",
]

type _MaterializeSeed = Callable[["R2SeedSmokeRequest"], object]


@dataclass(frozen=True, slots=True)
class R2SeedDatasetSnapshots:
    """Exact source snapshots selected for one fixed-seed input dataset."""

    dataset_id: str
    snapshot_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        """Reject ambiguous dataset and snapshot evidence."""
        if not self.dataset_id or self.dataset_id.strip() != self.dataset_id:
            raise AppProcessError(f"invalid seed smoke dataset_id: {self.dataset_id!r}")
        if not self.snapshot_ids or len(set(self.snapshot_ids)) != len(
            self.snapshot_ids
        ):
            raise AppProcessError(
                "seed smoke snapshot IDs must be non-empty and unique"
            )


@dataclass(frozen=True, slots=True)
class R2SeedSmokeRequest:
    """All immutable inputs needed to replay the fixed seed factor slice."""

    factor_ids: tuple[str, ...]
    input_dataset_ids: tuple[str, ...]
    max_lookback: int
    knowledge_date: date
    certification_profile: str
    dataset_snapshots: tuple[R2SeedDatasetSnapshots, ...]

    def __post_init__(self) -> None:
        """Require one uniquely identified snapshot selection per input dataset."""
        snapshot_datasets = tuple(item.dataset_id for item in self.dataset_snapshots)
        if len(set(snapshot_datasets)) != len(snapshot_datasets):
            raise AppProcessError(
                "seed smoke dataset snapshot selections must be unique"
            )


@dataclass(frozen=True, slots=True)
class R2SeedSmokeReport:
    """Evidence that identical certified inputs materialize identically twice."""

    status: str
    factor_ids: tuple[str, ...]
    input_dataset_ids: tuple[str, ...]
    max_lookback: int
    knowledge_date: date
    certification_profile: str
    certification_report_ids: tuple[str, ...]
    source_snapshot_ids: tuple[str, ...]
    first_checksum: str
    replay_checksum: str


class R2SeedSmokeRunner:
    """Fail closed on contract drift, missing evidence, or replay divergence."""

    def __init__(
        self,
        *,
        catalog_reader: DataCatalogReader,
        certification_reader: CertificationReader,
        materialize: _MaterializeSeed,
    ) -> None:
        self._catalog_reader = catalog_reader
        self._certification_reader = certification_reader
        self._materialize = materialize

    def run(self, request: R2SeedSmokeRequest) -> R2SeedSmokeReport:
        """Validate evidence, materialize twice, and compare canonical checksums."""
        contract = CertifiedSeedFactorContract(
            factor_ids=request.factor_ids,
            input_dataset_ids=request.input_dataset_ids,
            max_lookback=request.max_lookback,
            knowledge_date_required=True,
            certification_profile=request.certification_profile,
        )
        validate_certified_seed_factor_contract(contract)
        snapshots_by_dataset = {
            selection.dataset_id: selection.snapshot_ids
            for selection in request.dataset_snapshots
        }
        if tuple(snapshots_by_dataset) != request.input_dataset_ids:
            raise AppProcessError(
                "seed smoke dataset snapshot inputs do not match fixed input datasets"
            )

        catalog_report = validate_certified_catalog_dependencies(
            selections=tuple(
                CertifiedCatalogDependencySelection(
                    dataset_id=dataset_id,
                    source_snapshot_ids=snapshots_by_dataset[dataset_id],
                )
                for dataset_id in request.input_dataset_ids
            ),
            catalog_reader=self._catalog_reader,
        )
        certification_report_ids = self._validate_certifications(
            request,
            snapshots_by_dataset=snapshots_by_dataset,
        )
        first_checksum = _payload_checksum(self._materialize(request))
        replay_checksum = _payload_checksum(self._materialize(request))
        if first_checksum != replay_checksum:
            mismatch = f"{first_checksum} != {replay_checksum}"
            raise AppProcessError(
                f"R2 seed deterministic materialization checksum mismatch: {mismatch}"
            )
        return R2SeedSmokeReport(
            status="passed",
            factor_ids=request.factor_ids,
            input_dataset_ids=request.input_dataset_ids,
            max_lookback=request.max_lookback,
            knowledge_date=request.knowledge_date,
            certification_profile=request.certification_profile,
            certification_report_ids=certification_report_ids,
            source_snapshot_ids=catalog_report.source_snapshot_ids,
            first_checksum=first_checksum,
            replay_checksum=replay_checksum,
        )

    def _validate_certifications(
        self,
        request: R2SeedSmokeRequest,
        *,
        snapshots_by_dataset: dict[str, tuple[str, ...]],
    ) -> tuple[str, ...]:
        report_ids: list[str] = []
        for dataset_id in request.input_dataset_ids:
            report = self._certification_reader.get_active_report(
                dataset_id,
                request.certification_profile,
            )
            if report is None:
                product = f"{dataset_id}/{request.certification_profile}"
                raise AppProcessError(f"R2 seed certification missing: {product}")
            complete_from = report.coverage.complete_from
            if (
                complete_from is None
                or request.knowledge_date < complete_from
                or request.knowledge_date > report.coverage.target_to
            ):
                point = f"{dataset_id}@{request.knowledge_date.isoformat()}"
                raise AppProcessError(
                    f"R2 seed certification does not cover knowledge date: {point}"
                )
            if not set(snapshots_by_dataset[dataset_id]).issubset(
                report.evidence.snapshot_ids
            ):
                raise AppProcessError(
                    f"R2 seed certification snapshot mismatch: {dataset_id}"
                )
            report_ids.append(report.report_id)
        return tuple(report_ids)


def _payload_checksum(payload: object) -> str:
    if not isinstance(payload, bytes):
        raise AppProcessError("R2 seed materialization must return canonical bytes")
    return f"sha256:{sha256(payload).hexdigest()}"
