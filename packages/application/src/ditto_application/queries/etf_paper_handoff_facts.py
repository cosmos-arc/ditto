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
)
from ditto_application.exceptions import AppProcessError
from ditto_application.queries.account_ledger import AccountLedgerQuery
from ditto_application.queries.etf_candidates import ETFCandidate, ETFField
from ditto_application.queries.etf_paper_reference import (
    ETFPaperReferenceQuery,
    paper_reference_candidates,
)
from ditto_application.queries.metadata import MetadataQueryFacade
from ditto_application.queries.retained_calendar import (
    RetainedCalendarAbsent,
    calendar_has_complete_authority,
    calendar_has_single_source,
    retained_trading_days,
)
from ditto_application.queries.snapshot_readiness import SnapshotReadinessQuery


def _next_trading_day(
    *,
    snapshots: ProviderSnapshotReader,
    payloads: ProviderPayloadReader,
    cutoff: datetime,
    signal_date: str,
) -> str:
    """Return the first open session after the signal day, cutoff-bound."""
    try:
        # Shared A-share schedule view: the paper flow serves instruments
        # across exchanges, so per-instrument exchange scoping waits until
        # per-exchange calendar ingestion registers scoped shards.
        calendar = retained_trading_days(
            snapshots=snapshots, payloads=payloads, cutoff=cutoff, first_day=signal_date
        )
    except RetainedCalendarAbsent as exc:
        raise AppProcessError("ETF Paper trading calendar is absent or future") from exc
    later = [day for day in calendar.days if day > signal_date]
    if not later:
        raise AppProcessError("ETF Paper trading calendar is incomplete")
    if not calendar_has_complete_authority(calendar, signal_date, later[0]):
        raise AppProcessError("ETF Paper trading calendar is incomplete")
    if not calendar_has_single_source(calendar, signal_date, later[0]):
        raise AppProcessError("ETF Paper trading calendar mixes provider sources")
    return later[0]


class LiveETFPaperHandoffFacts:
    """Require registered current reference fields and a valued PAPER ledger."""

    def __init__(
        self,
        *,
        metadata: MetadataQueryFacade,
        readiness: SnapshotReadinessQuery,
        snapshots: ProviderSnapshotReader,
        payloads: ProviderPayloadReader,
        ledger: AccountLedgerQuery,
    ) -> None:
        self._metadata = metadata
        self._readiness = readiness
        self._snapshots = snapshots
        self._payloads = payloads
        self._ledger = ledger

    def resolve(self, request: ETFPaperHandoffRequest) -> ETFPaperHandoffFacts:
        """Read only evidence visible under the selected execution-day cutoff."""
        candidates = paper_reference_candidates(
            metadata=self._metadata,
            readiness=self._readiness,
            snapshots=self._snapshots,
            payloads=self._payloads,
            query=ETFPaperReferenceQuery(
                asof=request.signal_date,
                cutoff=request.knowledge_cutoff,
                snapshot_id=request.source_snapshot_id,
                input_snapshot_ids=request.input_snapshot_ids,
            ),
        ).values()
        prices: dict[InstrumentId, Decimal] = {}
        investable: set[int] = set()
        candidates = list(candidates)
        unavailable = {
            candidate.instrument_id: self._unavailable(candidate, request)
            for candidate in candidates
        }
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
            unavailable_reasons=unavailable,
            next_trading_day=_next_trading_day(
                snapshots=self._snapshots,
                payloads=self._payloads,
                cutoff=request.knowledge_cutoff,
                signal_date=request.signal_date,
            ),
        )

    def _unavailable(
        self, candidate: ETFCandidate, request: ETFPaperHandoffRequest
    ) -> tuple[str, ...]:
        reasons: list[str] = []
        for name in (
            "price_close",
            "trading_restriction",
            "asset_class",
            "trading_currency",
        ):
            field = candidate.fields.get(name)
            if field is None or field.value is None:
                reasons.append(f"{name}:missing")
            elif not self._field_allowed(candidate, name, field, request):
                reasons.append(f"{name}:not_visible")
        price = candidate.fields.get("price_close")
        if (
            price is not None
            and price.value is not None
            and price.observed_on != request.signal_date
        ):
            reasons.append("price_close:not_signal_day")
        if not candidate.is_active:
            reasons.append("list_status:inactive")
        return tuple(reasons)

    def _field_allowed(
        self,
        candidate: ETFCandidate,
        field_name: str,
        field: ETFField,
        request: ETFPaperHandoffRequest,
    ) -> bool:
        return etf_field_visible(
            candidate,
            field_name,
            field,
            asof=request.signal_date,
            cutoff=request.knowledge_cutoff,
            snapshot_id=(
                request.source_snapshot_id,
                *request.input_snapshot_ids.values(),
            ),
        )


def etf_field_visible(
    candidate: ETFCandidate,
    field_name: str,
    field: ETFField,
    *,
    asof: str,
    cutoff: datetime,
    snapshot_id: str | tuple[str, ...],
) -> bool:
    """Apply the same temporal visibility rule at either Paper date."""
    if (
        field.value is None
        or field.observed_on is None
        or field.source_snapshot_id
        not in ((snapshot_id,) if isinstance(snapshot_id, str) else snapshot_id)
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
    return not (
        published.tzinfo is None
        or published > cutoff
        or observed > asof_day
        or (effective_from is not None and effective_from > asof_day)
        or (effective_to is not None and effective_to <= asof_day)
    )
