"""Selection workspace DI provider."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime
from typing import Literal
from zoneinfo import ZoneInfo

from dishka import Provider, Scope, provide
from ditto_data.catalog.certification import CertificationReader
from ditto_data.catalog.license import DatasetLicenseReader
from ditto_data.catalog.provider_payload import ProviderPayloadReader
from ditto_data.catalog.snapshot_reader import SnapshotReadService, SourceTickerResolver
from ditto_data.catalog.source_snapshot import ProviderSnapshotReader
from ditto_data.ingestion.partition_state import PartitionLifecycleReader
from ditto_data.services.metadata.instrument import SecurityQuery
from ditto_data.services.metadata_service import MetadataService
from ditto_features.factors.factor_specs import ALL_FACTOR_SPECS
from ditto_features.factors.spec import FactorSpec
from ditto_strategy.industry_rotation.service import IndustryRotationService
from ditto_strategy.industry_rotation.store import (
    IndustryRotationReader,
    IndustryRotationWriter,
)
from ditto_strategy.selection.pipeline import SelectionPipeline
from ditto_strategy.selection.store import SelectionRunReader, SelectionRunWriter

from ditto_application.builders.data_provider import ServiceBackedDataProvider
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.selection.assemble_facts import (
    AssembleSelectionFacts,
    CertifiedSnapshotIndex,
    CertifiedSnapshotWindow,
    InstrumentIdentityReader,
    UniverseSourcesDiscovery,
)
from ditto_application.processes.selection.create_research_case import (
    CreateResearchCaseFromSelection,
)
from ditto_application.processes.selection.facade import SelectionWorkspaceFacade
from ditto_application.processes.selection.run_industry_and_security_selection import (
    RunIndustryAndSecuritySelection,
)
from ditto_application.queries.field_admission import FieldAdmissionQuery
from ditto_application.queries.historical_universe import (
    HistoricalUniverseQuery,
    HistoricalUniverseSources,
)
from ditto_application.queries.industry_rotations import IndustryRotationQueryService
from ditto_application.queries.provider_snapshot import ProviderSnapshotQuery
from ditto_application.queries.selection_evidence import (
    IndustryRotationEvidenceQueryFacade,
    SelectionRunEvidenceQueryFacade,
)
from ditto_application.queries.selection_runs import SelectionRunQueryService
from ditto_application.research_case_contracts import ResearchCaseFactory

__all__ = ["AppSelectionProvider"]

# Mirrors the FieldAdmissionRequest profile default; admission and discovery
# must qualify the same certification lane.
_SELECTION_FIELDS_PROFILE = "selection-fields-v1"


def _metadata_ticker_resolver(metadata: MetadataService) -> SourceTickerResolver:
    """Resolve replay scopes through the durable PIT source-ticker mapping."""

    def resolve(
        instrument_ids: Sequence[int],
        *,
        source: str,
        asofs: Sequence[date],
        cutoff: datetime,
    ) -> Mapping[str, Mapping[int, str]]:
        cutoff_text = cutoff.isoformat()
        resolved_by_date: dict[str, dict[int, str]] = {
            asof.isoformat(): {} for asof in asofs
        }
        for instrument_id in instrument_ids:
            tickers = metadata.instrument.get_source_tickers(
                instrument_id,
                source=source,
                asofs=[asof.isoformat() for asof in asofs],
                cutoff=cutoff_text,
            )
            for asof in asofs:
                ticker = tickers.get(asof.isoformat())
                if ticker is not None:
                    resolved_by_date[asof.isoformat()][instrument_id] = ticker
        return resolved_by_date

    return resolve


def _metadata_identities(metadata: MetadataService) -> InstrumentIdentityReader:
    """Serve registry names and PIT source tickers from durable metadata."""

    class _MetadataIdentities:
        def names(
            self, instrument_ids: Sequence[int], *, asof: date
        ) -> Mapping[int, str]:
            # PIT name history first; the live registry is the documented
            # fallback while the history table is not ingested.
            resolved: dict[int, str] = {}
            frame = metadata.instrument.find_securities(
                SecurityQuery(asset_class="stock", is_active=None)
            )
            known = {
                int(row["instrument_id"]): str(row["name"])
                for row in frame.unique(subset=["instrument_id"]).to_dicts()
            }
            for instrument_id in instrument_ids:
                name = metadata.instrument.get_stock_name(
                    instrument_id, asof.isoformat()
                )
                resolved[instrument_id] = name or known.get(
                    instrument_id, str(instrument_id)
                )
            return resolved

        def source_tickers(
            self, instrument_ids: Sequence[int], *, asof: date
        ) -> Mapping[int, str]:
            resolved: dict[int, str] = {}
            for instrument_id in instrument_ids:
                ticker = metadata.instrument.get_source_ticker(
                    instrument_id, "tushare", asof.isoformat()
                )
                if ticker is not None:
                    resolved[instrument_id] = ticker
            return resolved

    return _MetadataIdentities()


def _certified_snapshot_index(
    certifications: CertificationReader, snapshots: ProviderSnapshotReader
) -> CertifiedSnapshotIndex:
    """Qualify snapshots through the active selection-fields certification."""

    class _CertifiedIndex:
        def snapshot_ids(self, dataset_id: str) -> tuple[str, ...]:
            report = certifications.get_active_report(
                dataset_id, _SELECTION_FIELDS_PROFILE
            )
            return report.evidence.snapshot_ids if report else ()

        def covering(
            self, *, dataset_id: str, day: date
        ) -> tuple[CertifiedSnapshotWindow, ...]:
            windows: list[CertifiedSnapshotWindow] = []
            for snapshot_id in self.snapshot_ids(dataset_id):
                snapshot = snapshots.get_snapshot(snapshot_id)
                if snapshot is None:
                    continue
                request_start = date.fromisoformat(snapshot.request_start)
                request_end = date.fromisoformat(snapshot.request_end)
                if request_start <= day <= request_end:
                    windows.append(
                        CertifiedSnapshotWindow(snapshot_id, request_start, request_end)
                    )
            return tuple(windows)

    return _CertifiedIndex()


class _GovernedFactorRegistry:
    """Serve the governed factor table through the assembly port."""

    def __init__(self, specs: Mapping[str, FactorSpec]) -> None:
        self._specs = specs

    def get(self, factor_id: str) -> FactorSpec | None:
        return self._specs.get(factor_id)


def _index_universe_discovery(
    index: CertifiedSnapshotIndex,
    metadata: MetadataService,
) -> UniverseSourcesDiscovery:
    """
    Retain the certified registry chains for one universe at a cutoff.

    The v1 roster lane projects the whole certified market through the
    master/status chains; it cannot express a narrower pool (that needs
    membership snapshots inside ``HistoricalUniverseSources``). Discovery
    therefore fails closed unless the requested universe covers exactly
    the registered stock lane, so a custom pool can never silently select
    outside its declared membership.
    """

    def discover(
        *,
        universe_id: str,
        asset_kind: Literal["stock", "etf"],
        knowledge_cutoff: datetime,
    ) -> HistoricalUniverseSources:
        if asset_kind == "stock":
            asof = knowledge_cutoff.astimezone(ZoneInfo("Asia/Shanghai"))
            members = set(
                metadata.universe.get_universe(universe_id, asof.date().isoformat())
            )
            if not members:
                raise AppProcessError(
                    f"unknown universe: {universe_id}",
                    details={
                        "reason": "ASSEMBLY_UNIVERSE_UNKNOWN",
                        "universe_id": universe_id,
                    },
                )
            registered = set(
                metadata.instrument.list_instrument_ids(
                    asset_class="stock", is_active=None
                )
            )
            if members != registered:
                raise AppProcessError(
                    "universe membership is narrower than the certified roster "
                    + "lane; pool rosters need membership snapshots",
                    details={
                        "reason": "ASSEMBLY_UNIVERSE_SCOPE_UNSUPPORTED",
                        "universe_id": universe_id,
                        "member_count": len(members),
                        "roster_count": len(registered),
                    },
                )
        return HistoricalUniverseSources(
            universe_id=universe_id,
            asset_kind=asset_kind,
            master_snapshot_ids=index.snapshot_ids(f"{asset_kind}_basic"),
            status_snapshot_ids=index.snapshot_ids(
                "stock_status" if asset_kind == "stock" else "etf_daily",
            ),
        )

    return discover


class AppSelectionProvider(Provider):
    """Compose the selection capability behind application-owned contracts."""

    scope = Scope.APP

    @provide
    def run_industry_and_security_selection(
        self,
        rotation_service: IndustryRotationService,
        selection_pipeline: SelectionPipeline,
        rotation_writer: IndustryRotationWriter,
        run_writer: SelectionRunWriter,
    ) -> RunIndustryAndSecuritySelection:
        """Bind the cross-plane selection process to strategy ports."""
        return RunIndustryAndSecuritySelection(
            rotation_service=rotation_service,
            selection_pipeline=selection_pipeline,
            rotation_writer=rotation_writer,
            run_writer=run_writer,
        )

    @provide
    def selection_workspace_facade(
        self,
        process: RunIndustryAndSecuritySelection,
        admission: FieldAdmissionQuery,
        historical_universe: HistoricalUniverseQuery,
    ) -> SelectionWorkspaceFacade:
        """Expose typed create-selection requests to transport adapters."""
        return SelectionWorkspaceFacade(
            process, admission=admission, historical_universe=historical_universe
        )

    @provide
    def assemble_selection_facts(
        self,
        data_provider: ServiceBackedDataProvider,
        historical_universe: HistoricalUniverseQuery,
        metadata: MetadataService,
        certifications: CertificationReader,
        snapshots: ProviderSnapshotReader,
    ) -> AssembleSelectionFacts:
        """Assemble policy-only selection requests from certified evidence."""
        index = _certified_snapshot_index(certifications, snapshots)
        return AssembleSelectionFacts(
            provider=data_provider,
            history=historical_universe,
            discover_sources=_index_universe_discovery(index, metadata),
            identities=_metadata_identities(metadata),
            factors=_GovernedFactorRegistry(ALL_FACTOR_SPECS),
            snapshots=index,
        )

    @provide
    def create_research_case_from_selection(
        self,
        reader: SelectionRunReader,
        factory: ResearchCaseFactory,
    ) -> CreateResearchCaseFromSelection:
        """Bind Analysis Research Cases to exact persisted SelectionRuns."""
        return CreateResearchCaseFromSelection(reader, factory)

    @provide
    def selection_run_query_service(
        self,
        reader: SelectionRunReader,
    ) -> SelectionRunQueryService:
        """Expose exact saved SelectionRun reads and comparisons."""
        return SelectionRunQueryService(reader)

    @provide
    def industry_rotation_query_service(
        self,
        reader: IndustryRotationReader,
    ) -> IndustryRotationQueryService:
        """Expose exact persisted rotation snapshots to UI transports."""
        return IndustryRotationQueryService(reader)

    @provide
    def industry_rotation_evidence_query(
        self,
        reader: IndustryRotationReader,
    ) -> IndustryRotationEvidenceQueryFacade:
        """Bind exact persisted rankings to the Agent-facing application port."""
        return IndustryRotationEvidenceQueryFacade(reader)

    @provide
    def selection_run_evidence_query(
        self,
        reader: SelectionRunReader,
    ) -> SelectionRunEvidenceQueryFacade:
        """Bind exact saved runs to the Agent-facing application port."""
        return SelectionRunEvidenceQueryFacade(reader)

    @provide
    def field_admission_query(
        self,
        snapshots: ProviderSnapshotReader,
        licenses: DatasetLicenseReader,
        certifications: CertificationReader,
        lifecycle: PartitionLifecycleReader,
    ) -> FieldAdmissionQuery:
        """Reuse durable data evidence for both selection checks and previews."""
        return FieldAdmissionQuery(snapshots, licenses, certifications, lifecycle)

    @provide
    def provider_snapshot_query(
        self,
        snapshots: ProviderSnapshotReader,
        payloads: ProviderPayloadReader,
        lifecycle: PartitionLifecycleReader,
        admission: FieldAdmissionQuery,
        metadata: MetadataService,
    ) -> ProviderSnapshotQuery:
        """Bind exact replay to data-owned immutable reads and current qualification."""
        return ProviderSnapshotQuery(
            SnapshotReadService(snapshots, payloads, lifecycle),
            admission,
            ticker_resolver=_metadata_ticker_resolver(metadata),
        )

    @provide
    def historical_universe_query(
        self,
        snapshots: ProviderSnapshotReader,
        payloads: ProviderPayloadReader,
        lifecycle: PartitionLifecycleReader,
        admission: FieldAdmissionQuery,
    ) -> HistoricalUniverseQuery:
        """Resolve qualified historical scopes from completed retained evidence."""
        return HistoricalUniverseQuery(
            SnapshotReadService(snapshots, payloads, lifecycle), admission
        )
