"""Current PIT ETF reference and PAPER ledger facts for fixed-target handoff."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from ditto_data.catalog.provider_payload import ProviderPayloadReader
from ditto_data.catalog.source_snapshot import ProviderSnapshotReader
from ditto_kernel.identity import InstrumentId
from ditto_portfolio.account_ledger import ledger_hash

from ditto_application.etf_paper_contracts import (
    ETFPaperHandoffFacts,
    ETFPaperHandoffRequest,
    canonical_cutoff,
)
from ditto_application.exceptions import AppProcessError
from ditto_application.queries.account_ledger import AccountLedgerQuery
from ditto_application.queries.etf_candidates import ETFCandidate, ETFField
from ditto_application.queries.field_admission import (
    FieldAdmissionQuery,
    FieldAdmissionRequest,
    FieldRequirement,
)
from ditto_application.queries.metadata import MetadataQueryFacade
from ditto_application.queries.retained_calendar import (
    RetainedCalendarAbsent,
    retained_trading_days,
)


def _next_trading_day(
    *,
    snapshots: ProviderSnapshotReader,
    payloads: ProviderPayloadReader,
    cutoff: datetime,
    signal_date: str,
) -> str:
    """Return the first open session after the signal day, cutoff-bound."""
    try:
        calendar = retained_trading_days(
            snapshots=snapshots, payloads=payloads, cutoff=cutoff
        )
    except RetainedCalendarAbsent as exc:
        raise AppProcessError("ETF Paper trading calendar is absent or future") from exc
    later = [day for day in calendar.days if day > signal_date]
    if not later:
        raise AppProcessError("ETF Paper trading calendar is incomplete")
    return later[0]


class LiveETFPaperHandoffFacts:
    """Require registered current reference fields and a valued PAPER ledger."""

    def __init__(
        self,
        *,
        metadata: MetadataQueryFacade,
        admission: FieldAdmissionQuery,
        snapshots: ProviderSnapshotReader,
        payloads: ProviderPayloadReader,
        ledger: AccountLedgerQuery,
    ) -> None:
        self._metadata = metadata
        self._admission = admission
        self._snapshots = snapshots
        self._payloads = payloads
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
            cutoff=canonical_cutoff(request.knowledge_cutoff),
            source_snapshot_id=request.source_snapshot_id,
        )
        prices: dict[InstrumentId, Decimal] = {}
        investable: set[int] = set()
        for candidate in candidates:
            price = candidate.fields.get("price_close")
            if price is None:
                continue
            if (
                not self._field_allowed(candidate, "price_close", price, request)
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
            recorded_through=request.ledger_cutoff or request.knowledge_cutoff,
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
            signal_ledger_hash=ledger_hash(account.events),
            next_trading_day=_next_trading_day(
                snapshots=self._snapshots,
                payloads=self._payloads,
                cutoff=request.knowledge_cutoff,
                signal_date=request.signal_date,
            ),
        )

    def _field_allowed(
        self,
        candidate: ETFCandidate,
        field_name: str,
        field: ETFField,
        request: ETFPaperHandoffRequest,
    ) -> bool:
        return admitted_etf_field(
            candidate,
            field_name,
            field,
            asof=request.signal_date,
            cutoff=request.knowledge_cutoff,
            snapshot_id=request.source_snapshot_id,
            admission=self._admission,
        )


def admitted_etf_field(
    candidate: ETFCandidate,
    field_name: str,
    field: ETFField,
    *,
    asof: str,
    cutoff: datetime,
    snapshot_id: str,
    admission: FieldAdmissionQuery,
) -> bool:
    """Apply the same temporal and promotion admission rule at either Paper date."""
    if (
        field.value is None
        or field.observed_on is None
        or field.source_snapshot_id != snapshot_id
    ):
        return False
    try:
        observed = date.fromisoformat(field.observed_on)
        published = datetime.fromisoformat(
            (field.published_at or "").replace("Z", "+00:00")
        )
        asof_day = date.fromisoformat(asof)
        effective_from = (
            date.fromisoformat(field.effective_from) if field.effective_from else None
        )
        effective_to = (
            date.fromisoformat(field.effective_to) if field.effective_to else None
        )
    except ValueError:
        return False
    if (
        published.tzinfo is None
        or published > cutoff
        or observed > asof_day
        or (effective_from is not None and effective_from > asof_day)
        or (effective_to is not None and effective_to <= asof_day)
    ):
        return False
    report = admission.assess(
        FieldAdmissionRequest(
            fields=(
                FieldRequirement(
                    dataset_id="etf_reference",
                    field=field_name,
                    snapshot_id=snapshot_id,
                ),
            ),
            instrument_ids=(candidate.instrument_id,),
            required_from=observed,
            required_to=observed,
            knowledge_cutoff=cutoff,
            publication_cutoff=cutoff,
            purpose="promotion_paper",
        )
    )
    return report.allowed
