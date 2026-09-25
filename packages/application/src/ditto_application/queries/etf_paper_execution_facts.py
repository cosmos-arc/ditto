"""Admitted signal-day and execution-day facts for ETF Paper fills."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from math import isfinite

from ditto_data.catalog.provider_payload import ProviderPayloadReader
from ditto_data.catalog.source_snapshot import ProviderSnapshot, ProviderSnapshotReader
from ditto_data.query.contracts import DatasetSnapshot, PITQueryContext
from ditto_kernel.identity import InstrumentId
from ditto_portfolio.account_ledger import ledger_hash
from ditto_portfolio.account_projection import PortfolioPositionSnapshot

from ditto_application.etf_paper_contracts import (
    ETFPaperExecutionRequest,
    ETFPaperOrderFacts,
    canonical_cutoff,
)
from ditto_application.exceptions import AppProcessError
from ditto_application.paper_contracts import (
    PaperInstrumentRulesInput,
    PaperMarketSnapshotInput,
)
from ditto_application.queries.account_ledger import AccountLedgerQuery
from ditto_application.queries.etf_candidates import ETFCandidate
from ditto_application.queries.etf_paper_handoff_facts import admitted_etf_field
from ditto_application.queries.field_admission import (
    FieldAdmissionQuery,
    FieldAdmissionRequest,
    FieldRequirement,
)
from ditto_application.queries.metadata import MetadataQueryFacade
from ditto_application.queries.retained_calendar import (
    RetainedCalendarAbsent,
    calendar_has_single_source,
    retained_trading_days,
)
from ditto_application.queries.technical_analysis_source import (
    ProviderPayloadTechnicalAnalysisSource,
)

_RULE_FIELDS = (
    "lot_size",
    "tick_size",
    "settlement_cycle",
    "price_limit_pct",
    "commission_rate",
    "min_commission",
    "stamp_duty_rate",
    "transfer_fee_rate",
)
_BAR_FIELDS = (
    "open",
    "high",
    "low",
    "close",
    "pre_close",
    "volume",
    "amount",
)


class LiveETFPaperExecutionFacts:
    """Require retained market bars, admitted ETF rules and real PAPER balances."""

    def __init__(
        self,
        *,
        metadata: MetadataQueryFacade,
        admission: FieldAdmissionQuery,
        snapshots: ProviderSnapshotReader,
        payloads: ProviderPayloadReader,
        bars: ProviderPayloadTechnicalAnalysisSource,
        ledger: AccountLedgerQuery,
    ) -> None:
        self._metadata = metadata
        self._admission = admission
        self._snapshots = snapshots
        self._payloads = payloads
        self._bars = bars
        self._ledger = ledger

    def resolve(
        self,
        request: ETFPaperExecutionRequest,
        *,
        instrument_id: int,
        signal_snapshot_id: str,
        signal_cutoff: datetime,
        valuation_cutoff: datetime,
    ) -> ETFPaperOrderFacts:
        """
        Read exact D and D+1 inputs; no caller-supplied market or rule values.

        ``signal_cutoff`` (the saved version cutoff) bounds the ledger reads,
        matching the handoff's frozen ``paper_signal_ledger`` basis;
        ``valuation_cutoff`` (the handoff's declared cutoff) bounds the
        reference-data reads that reproduce the package's valuation basis.
        """
        signal = self._candidates(
            asof=request.signal_date,
            cutoff=valuation_cutoff,
            snapshot_id=signal_snapshot_id,
        )
        candidate = signal.get(instrument_id)
        if candidate is None:
            raise AppProcessError("ETF signal instrument is absent")
        signal_rules = self._rules(
            candidate,
            asof=request.signal_date,
            cutoff=valuation_cutoff,
            snapshot_id=signal_snapshot_id,
        )
        initial_account = self._ledger.get_paper(
            account_id=request.account_id,
            as_of=request.signal_date,
            recorded_through=signal_cutoff,
        )
        needed = {instrument_id} | {
            int(position.instrument_id)
            for position in initial_account.snapshot.positions
        }
        signal_prices = {
            InstrumentId(item_id): self._price(
                signal[item_id],
                asof=request.signal_date,
                cutoff=valuation_cutoff,
                snapshot_id=signal_snapshot_id,
            )
            for item_id in needed
            if item_id in signal
        }
        if len(signal_prices) != len(needed):
            raise AppProcessError("ETF signal account price coverage is incomplete")
        signal_account = self._ledger.get_paper(
            account_id=request.account_id,
            as_of=request.signal_date,
            valuation_prices=signal_prices,
            recorded_through=signal_cutoff,
        )
        if (
            not signal_account.snapshot.valuation_complete
            or signal_account.snapshot.total_value <= 0
        ):
            raise AppProcessError("ETF signal account valuation is incomplete")
        execution = self._candidates(
            asof=request.intended_trade_date,
            cutoff=request.execution_cutoff,
            snapshot_id=request.reference_snapshot_id,
        )
        execution_candidate = execution.get(instrument_id)
        if execution_candidate is None:
            raise AppProcessError("ETF execution instrument is absent")
        execution_rules = self._rules(
            execution_candidate,
            asof=request.intended_trade_date,
            cutoff=request.execution_cutoff,
            snapshot_id=request.reference_snapshot_id,
        )
        if not execution_candidate.is_active:
            raise AppProcessError("ETF execution instrument is inactive")
        restriction = self._value(
            execution_candidate,
            "trading_restriction",
            asof=request.intended_trade_date,
            cutoff=request.execution_cutoff,
            snapshot_id=request.reference_snapshot_id,
        )
        if restriction != "none":
            raise AppProcessError("ETF execution instrument is restricted")

        market_snapshot = self._snapshot(
            request.market_snapshot_id, "etf_daily", request.execution_cutoff
        )
        trade_day = date.fromisoformat(request.intended_trade_date)
        report = self._admission.assess(
            FieldAdmissionRequest(
                fields=tuple(
                    FieldRequirement(
                        dataset_id="etf_daily",
                        field=field,
                        snapshot_id=request.market_snapshot_id,
                    )
                    for field in _BAR_FIELDS
                ),
                instrument_ids=(instrument_id,),
                required_from=trade_day,
                required_to=trade_day,
                knowledge_cutoff=request.execution_cutoff,
                publication_cutoff=request.execution_cutoff,
                purpose="promotion_paper",
            )
        )
        if not report.allowed:
            raise AppProcessError("ETF execution bar fields are not admitted for Paper")
        source_ticker = self._source_ticker(
            request=request,
            instrument_id=instrument_id,
            market_snapshot=market_snapshot,
            execution_candidate=execution_candidate,
        )
        market = self._bars.load_paper_market(
            PITQueryContext(
                as_of=request.execution_cutoff,
                knowledge_cutoff=request.execution_cutoff,
                publication_cutoff=request.execution_cutoff,
                source_snapshots=(
                    DatasetSnapshot(
                        dataset_id="etf_daily",
                        dataset_version=market_snapshot.schema_version,
                        source_snapshot_ids=(market_snapshot.snapshot_id,),
                        created_at=market_snapshot.created_at,
                    ),
                ),
            ),
            instrument_id=InstrumentId(instrument_id),
            instrument_code=source_ticker,
            trade_date=request.intended_trade_date,
        )
        if market.is_suspended:
            raise AppProcessError("ETF execution instrument is suspended")
        market = _derived_price_limits(market, execution_rules)
        execution_account = self._ledger.get_paper(
            account_id=request.account_id,
            as_of=request.intended_trade_date,
            recorded_through=request.execution_cutoff,
        )
        signal_position = _position(signal_account.snapshot.positions, instrument_id)
        execution_position = _position(
            execution_account.snapshot.positions, instrument_id
        )
        return ETFPaperOrderFacts(
            signal_nav=float(signal_account.snapshot.total_value),
            signal_cash_available=float(signal_account.snapshot.cash.available),
            signal_current_quantity=_whole(signal_position[0]),
            signal_available_quantity=_whole(signal_position[1]),
            signal_reference_price=float(signal_prices[InstrumentId(instrument_id)]),
            signal_rules=signal_rules,
            signal_ledger_hash=ledger_hash(signal_account.events),
            execution_cash_available=float(execution_account.snapshot.cash.available),
            execution_position_quantity=_whole(execution_position[0]),
            execution_available_quantity=_whole(execution_position[1]),
            execution_rules=execution_rules,
            execution_market=market,
            settlement_date=self._settlement_date(
                request.intended_trade_date,
                execution_rules.settlement_cycle,
                request.execution_cutoff,
            ),
            execution_ledger_hash=execution_account.ledger_revision.ledger_hash,
        )

    def _source_ticker(
        self,
        *,
        request: ETFPaperExecutionRequest,
        instrument_id: int,
        market_snapshot: ProviderSnapshot,
        execution_candidate: ETFCandidate,
    ) -> str:
        """
        Resolve the bar alias, cross-checked against the reference identity.

        The live instrument mapping has no knowledge cutoff, so its answer
        must agree with the cutoff-bound candidate ticker; a retroactively
        corrected mapping fails closed instead of selecting another
        instrument's bars.
        """
        source_ticker = self._metadata.resolve_source_ticker(
            instrument_id=instrument_id,
            asset_class="etf",
            source=market_snapshot.source,
            asof=request.intended_trade_date,
        )
        if not source_ticker:
            raise AppProcessError("ETF execution source ticker is unavailable")
        if source_ticker.split(".", 1)[0] != execution_candidate.ticker:
            raise AppProcessError(
                "ETF execution source ticker conflicts with the reference identity"
            )
        return source_ticker

    def _snapshot(
        self, snapshot_id: str, dataset_id: str, cutoff: datetime
    ) -> ProviderSnapshot:
        snapshot = self._snapshots.get_snapshot(snapshot_id)
        if (
            snapshot is None
            or snapshot.snapshot_id != snapshot_id
            or snapshot.dataset_id != dataset_id
            or snapshot.created_at > cutoff
            or not snapshot.payload_retained
        ):
            raise AppProcessError("ETF Paper source snapshot is absent or future")
        return snapshot

    def _candidates(
        self, *, asof: str, cutoff: datetime, snapshot_id: str
    ) -> dict[int, ETFCandidate]:
        self._snapshot(snapshot_id, "etf_reference", cutoff)
        return {
            item.instrument_id: item
            for item in self._metadata.list_etf_candidates(
                asof=asof,
                cutoff=canonical_cutoff(cutoff),
                source_snapshot_id=snapshot_id,
            )
        }

    def _value(
        self,
        candidate: ETFCandidate,
        field_name: str,
        *,
        asof: str,
        cutoff: datetime,
        snapshot_id: str,
    ) -> str | float:
        field = candidate.fields.get(field_name)
        if field is None or not admitted_etf_field(
            candidate,
            field_name,
            field,
            asof=asof,
            cutoff=cutoff,
            snapshot_id=snapshot_id,
            admission=self._admission,
        ):
            raise AppProcessError(f"ETF Paper {field_name} is missing or not admitted")
        value = field.value
        if value is None:
            raise AppProcessError(f"ETF Paper {field_name} is missing")
        return value

    def _price(
        self,
        candidate: ETFCandidate,
        *,
        asof: str,
        cutoff: datetime,
        snapshot_id: str,
    ) -> Decimal:
        field = candidate.fields.get("price_close")
        if field is None:
            raise AppProcessError("ETF signal price is missing")
        if field.observed_on != asof:
            raise AppProcessError("ETF signal price is not from the signal day")
        value = Decimal(
            str(
                self._value(
                    candidate,
                    "price_close",
                    asof=asof,
                    cutoff=cutoff,
                    snapshot_id=snapshot_id,
                )
            )
        )
        if not value.is_finite() or value <= 0:
            raise AppProcessError("ETF signal price is invalid")
        return value

    def _rules(
        self,
        candidate: ETFCandidate,
        *,
        asof: str,
        cutoff: datetime,
        snapshot_id: str,
    ) -> PaperInstrumentRulesInput:
        asset_class = self._value(
            candidate, "asset_class", asof=asof, cutoff=cutoff, snapshot_id=snapshot_id
        )
        currency = self._value(
            candidate,
            "trading_currency",
            asof=asof,
            cutoff=cutoff,
            snapshot_id=snapshot_id,
        )
        if asset_class != "etf" or currency != "CNY":
            raise AppProcessError("ETF Paper only accepts CNY listed ETFs")
        values: dict[str, float] = {}
        for field in _RULE_FIELDS:
            raw = self._value(
                candidate, field, asof=asof, cutoff=cutoff, snapshot_id=snapshot_id
            )
            try:
                value = float(raw)
            except (TypeError, ValueError) as exc:
                raise AppProcessError(f"ETF Paper {field} is invalid") from exc
            if not isfinite(value) or value < 0:
                raise AppProcessError(f"ETF Paper {field} is invalid")
            values[field] = value
        lot_size = int(values["lot_size"])
        settlement_cycle = int(values["settlement_cycle"])
        if (
            lot_size <= 0
            or lot_size != values["lot_size"]
            or settlement_cycle != values["settlement_cycle"]
            or values["tick_size"] <= 0
            or values["price_limit_pct"] <= 0
        ):
            raise AppProcessError("ETF Paper trading rule is invalid")
        return PaperInstrumentRulesInput(
            asset_class="etf",
            exchange=candidate.exchange,
            currency="CNY",
            tick_size=values["tick_size"],
            lot_size=lot_size,
            board_segment="fund",
            settlement_cycle=settlement_cycle,
            commission_rate=values["commission_rate"],
            min_commission=values["min_commission"],
            stamp_duty_rate=values["stamp_duty_rate"],
            transfer_fee_rate=values["transfer_fee_rate"],
            price_limit_pct=values["price_limit_pct"],
        )

    def _settlement_date(self, trade_date: str, cycle: int, cutoff: datetime) -> str:
        """Derive the settlement date from calendar evidence visible at the cutoff."""
        start = date.fromisoformat(trade_date)
        horizon = (start + timedelta(days=30)).isoformat()
        try:
            calendar = retained_trading_days(
                snapshots=self._snapshots,
                payloads=self._payloads,
                cutoff=cutoff,
                first_day=trade_date,
            )
        except RetainedCalendarAbsent as exc:
            raise AppProcessError(
                "ETF Paper settlement calendar is absent or future"
            ) from exc
        days = [day for day in calendar.days if trade_date <= day <= horizon]
        if not days or days[0] != trade_date or len(days) <= cycle:
            raise AppProcessError("ETF Paper settlement calendar is incomplete")
        if not calendar_has_single_source(calendar, trade_date, days[cycle]):
            raise AppProcessError(
                "ETF Paper settlement calendar mixes provider sources"
            )
        return days[cycle]


def _derived_price_limits(
    market: PaperMarketSnapshotInput, rules: PaperInstrumentRulesInput
) -> PaperMarketSnapshotInput:
    """
    Fill absent exchange limits from pre_close and the admitted rule set.

    The canonical ETF daily producer carries no limit columns, so the limits
    follow the exchange rule: pre_close shifted by price_limit_pct and rounded
    half-up to the tick. Payload-provided limits win when both are present.
    """
    if market.limit_up is not None and market.limit_down is not None:
        return market
    base = Decimal(str(market.prev_close))
    tick = Decimal(str(rules.tick_size))
    ratio = Decimal(str(rules.price_limit_pct))

    def shifted(direction: Decimal) -> float:
        multiple = (base * (Decimal(1) + direction * ratio) / tick).quantize(
            Decimal(1), rounding=ROUND_HALF_UP
        )
        return float(multiple * tick)

    return replace(
        market,
        limit_up=shifted(Decimal(1)),
        limit_down=shifted(Decimal(-1)),
    )


def _position(
    positions: Sequence[PortfolioPositionSnapshot], instrument_id: int
) -> tuple[Decimal, Decimal]:
    for item in positions:
        if int(item.instrument_id) == instrument_id:
            return item.quantity, item.available_quantity
    return Decimal(0), Decimal(0)


def _whole(value: Decimal) -> int:
    result = int(value)
    if value != result or result < 0:
        raise AppProcessError("ETF Paper position quantity is invalid")
    return result
