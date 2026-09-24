"""Current PIT ETF reference and PAPER ledger facts for fixed-target handoff."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from ditto_data.catalog.source_snapshot import ProviderSnapshotReader
from ditto_kernel.identity import InstrumentId

from ditto_application.exceptions import AppProcessError
from ditto_application.processes.portfolio.etf_paper_handoff import (
    ETFPaperHandoffFacts,
    ETFPaperHandoffRequest,
)
from ditto_application.queries.account_ledger import AccountLedgerQuery
from ditto_application.queries.etf_candidates import ETFCandidate, ETFField
from ditto_application.queries.field_admission import (
    FieldAdmissionQuery,
    FieldAdmissionRequest,
    FieldRequirement,
)
from ditto_application.queries.metadata import MetadataQueryFacade


class LiveETFPaperHandoffFacts:
    """Require registered current reference fields and a valued PAPER ledger."""

    def __init__(
        self,
        *,
        metadata: MetadataQueryFacade,
        admission: FieldAdmissionQuery,
        snapshots: ProviderSnapshotReader,
        ledger: AccountLedgerQuery,
    ) -> None:
        self._metadata = metadata
        self._admission = admission
        self._snapshots = snapshots
        self._ledger = ledger

    def resolve(self, request: ETFPaperHandoffRequest) -> ETFPaperHandoffFacts:
        """Read only evidence visible under the selected execution-day cutoff."""
        snapshot = self._snapshots.get_snapshot(request.source_snapshot_id)
        if (
            snapshot is None
            or snapshot.snapshot_id != request.source_snapshot_id
            or snapshot.dataset_id != "etf_reference"
            or snapshot.created_at > request.knowledge_cutoff
        ):
            raise AppProcessError("Paper source snapshot is absent or future")
        candidates = self._metadata.list_etf_candidates(
            asof=request.signal_date,
            cutoff=request.knowledge_cutoff.isoformat(),
            source_snapshot_id=request.source_snapshot_id,
        )
        prices: dict[InstrumentId, Decimal] = {}
        investable: set[int] = set()
        for candidate in candidates:
            price = candidate.fields.get("price_close")
            if price is None:
                continue
            if (
                not self._field_allowed(
                    candidate, "price_close", price, request, snapshot.dataset_id
                )
                or price.observed_on != request.signal_date
            ):
                continue
            try:
                value = Decimal(str(price.value))
            except (ValueError, TypeError):
                continue
            if not value.is_finite() or value <= 0:
                continue
            prices[InstrumentId(candidate.instrument_id)] = value
            if not candidate.is_active:
                continue
            restriction = candidate.fields.get("trading_restriction")
            asset_class = candidate.fields.get("asset_class")
            currency = candidate.fields.get("trading_currency")
            if (
                restriction is not None
                and asset_class is not None
                and currency is not None
                and restriction.value == "none"
                and asset_class.value == "etf"
                and currency.value == "CNY"
                and all(
                    self._field_allowed(
                        candidate,
                        field,
                        candidate.fields[field],
                        request,
                        snapshot.dataset_id,
                    )
                    for field in (
                        "trading_restriction",
                        "asset_class",
                        "trading_currency",
                    )
                )
            ):
                investable.add(candidate.instrument_id)
        account = self._ledger.get_paper(
            account_id=request.account_id,
            as_of=request.signal_date,
            valuation_prices=prices,
        )
        if not account.snapshot.valuation_complete or account.snapshot.total_value <= 0:
            raise AppProcessError("Paper account valuation is incomplete")
        weights = {
            int(position.instrument_id): float(
                position.market_value / account.snapshot.total_value
            )
            for position in account.snapshot.positions
        }
        return ETFPaperHandoffFacts(
            signal_date=request.signal_date,
            knowledge_cutoff=request.knowledge_cutoff,
            source_snapshot_id=request.source_snapshot_id,
            current_positions=weights,
            investable_instrument_ids=frozenset(investable),
        )

    def _field_allowed(
        self,
        candidate: ETFCandidate,
        field_name: str,
        field: ETFField,
        request: ETFPaperHandoffRequest,
        dataset_id: str,
    ) -> bool:
        if (
            field.value is None
            or field.observed_on is None
            or field.source_snapshot_id != request.source_snapshot_id
        ):
            return False
        try:
            observed = date.fromisoformat(field.observed_on)
            published = datetime.fromisoformat(
                (field.published_at or "").replace("Z", "+00:00")
            )
            asof = date.fromisoformat(request.signal_date)
            effective_from = (
                date.fromisoformat(field.effective_from)
                if field.effective_from
                else None
            )
            effective_to = (
                date.fromisoformat(field.effective_to) if field.effective_to else None
            )
        except ValueError:
            return False
        if (
            published.tzinfo is None
            or published > request.knowledge_cutoff
            or observed > asof
            or (effective_from is not None and effective_from > asof)
            or (effective_to is not None and effective_to <= asof)
        ):
            return False
        report = self._admission.assess(
            FieldAdmissionRequest(
                fields=(
                    FieldRequirement(
                        dataset_id=dataset_id,
                        field=field_name,
                        snapshot_id=request.source_snapshot_id,
                    ),
                ),
                instrument_ids=(candidate.instrument_id,),
                required_from=observed,
                required_to=observed,
                knowledge_cutoff=request.knowledge_cutoff,
                publication_cutoff=request.knowledge_cutoff,
                purpose="promotion_paper",
            )
        )
        return report.allowed
