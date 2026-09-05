"""Composition-owned Manual and Paper runtime for Q4/PAP-09 acceptance."""

from __future__ import annotations

from collections.abc import Generator, Mapping, Sequence
from contextlib import contextmanager
from datetime import UTC, date, datetime, time
from decimal import Decimal
from pathlib import Path

from ditto_application.commands.account_ledger import (
    CorrectManualEventCommand,
    CreateAccountCommand,
    CreateAccountHandler,
    ManualAccountCommandHandler,
    ManualEventInput,
    RecordManualEventCommand,
)
from ditto_application.commands.paper_account import (
    CreatePaperAccountCommand,
    CreatePaperAccountHandler,
)
from ditto_application.commands.paper_session import (
    CreatePaperSessionCommand,
    PaperSessionCommandHandler,
    PausePaperSessionCommand,
    ReconcilePaperSessionCommand,
    StartPaperSessionCommand,
)
from ditto_application.paper_contracts import (
    PaperFillAssumptionInput,
    PaperInstrumentRulesInput,
    PaperMarketSnapshotInput,
)
from ditto_application.processes.execution.operate_paper_session import (
    OperatePaperOrderCommand,
    OperatePaperSession,
)
from ditto_application.processes.execution.reconcile_paper_account import (
    ReconcilePaperAccount,
)
from ditto_execution.paper.session import PaperExecutionRecord, PaperSessionStatus
from ditto_execution.paper.sqlite_store import SqlitePaperSessionStore
from ditto_execution.storage.sqlite.account_journal import SqliteAccountEventJournal
from ditto_kernel.identity import InstrumentId
from ditto_portfolio.account_ledger import AccountEventJournalPort, AccountEventType
from ditto_portfolio.account_projection import AccountLedgerRebuilder

from ditto_apps.operations.q4_live_account_acceptance import (
    BOOTSTRAP_SCHEMA,
    DAY_SCHEMA,
    SHANGHAI,
    AcceptanceDayRequest,
    AcceptanceMarketSource,
    ApprovedAcceptance,
    acceptance_state_paths,
    approved_acceptance_request,
    atomic_write_json,
    canonical_hash,
    canonical_text,
    load_json,
    load_signing_key,
    parse_timestamp,
    positive_number,
    reconcile_completed_dates,
    restore_public_evidence_mirrors,
    rfc3339,
    select_next_eligible_trade_date,
    sign_payload,
    verify_soak_progress,
)
from ditto_apps.registry.live.q4_live_account_acceptance_state import (
    bootstrap_receipt as _bootstrap_receipt,
)
from ditto_apps.registry.live.q4_live_account_acceptance_state import (
    eligibility_calendar_context as _eligibility_calendar_context,
)
from ditto_apps.registry.live.q4_live_account_acceptance_state import (
    frame_bar as _frame_bar,
)
from ditto_apps.registry.live.q4_live_account_acceptance_state import (
    previous_day_signature as _previous_day_signature,
)
from ditto_apps.registry.live.q4_live_account_acceptance_store import (
    acceptance_opened_at,
    count_acceptance_rows,
)


def _bootstrap_manual(
    approved: ApprovedAcceptance,
    *,
    database: Path,
    approved_at: datetime,
    operator_id: str,
) -> dict[str, object]:
    approval_day = approved_at.astimezone(SHANGHAI).date().isoformat()
    instrument = InstrumentId(approved.instrument_id)
    price = Decimal(approved.manual_opening_position_price)
    quantity = Decimal(approved.manual_opening_position_quantity)
    with SqliteAccountEventJournal(str(database)) as journal:
        account_receipt = CreateAccountHandler(journal=journal).handle(
            CreateAccountCommand.manual(
                account_id=approved.manual_account_id,
                name="Q4 Owner Manual Acceptance",
                opened_at=approved_at,
            )
        )
        handler = ManualAccountCommandHandler(
            journal=journal,
            clock=lambda: approved_at,
        )
        event_specs = (
            ManualEventInput.cash(
                event_type="opening_cash",
                trade_date=approval_day,
                settlement_date=approval_day,
                idempotency_key="q4-manual-opening-cash-v1",
                actor=operator_id,
                amount=Decimal(approved.manual_opening_cash),
            ),
            ManualEventInput(
                event_type=AccountEventType.OPENING_POSITION,
                trade_date=approved.manual_opening_trade_date,
                settlement_date=approved.manual_opening_trade_date,
                idempotency_key="q4-manual-opening-position-v1",
                actor=operator_id,
                instrument_id=instrument,
                quantity=quantity,
                price=price,
                gross_amount=price * quantity,
                note="Synthetic owner acceptance opening position",
                external_reference=f"approval:{approved.request_hash}",
            ),
            ManualEventInput.cash(
                event_type="deposit",
                trade_date=approval_day,
                settlement_date=approval_day,
                idempotency_key="q4-manual-deposit-original-v1",
                actor=operator_id,
                amount=Decimal(approved.manual_original_deposit),
            ),
        )
        receipts = [
            handler.record(
                RecordManualEventCommand(
                    account_id=approved.manual_account_id,
                    event=event,
                )
            )
            for event in event_specs
        ]
        original = receipts[-1].event
        if original is None:
            raise RuntimeError("manual original deposit did not produce an event")
        correction = handler.correct(
            CorrectManualEventCommand(
                account_id=approved.manual_account_id,
                corrects_event_id=original.event_id,
                replacement=ManualEventInput.cash(
                    event_type="deposit",
                    trade_date=approval_day,
                    settlement_date=approval_day,
                    idempotency_key="q4-manual-deposit-correction-v1",
                    actor=operator_id,
                    amount=Decimal(approved.manual_corrected_deposit),
                ),
            )
        )
        account = journal.get_account(approved.manual_account_id)
        if account is None:
            raise RuntimeError("manual acceptance account was not persisted")
        events = journal.list_events(approved.manual_account_id)
        snapshot = AccountLedgerRebuilder().rebuild(
            account=account,
            events=events,
            as_of=approval_day,
            valuation_prices={instrument: price},
        )
    position = snapshot.position(instrument)
    return {
        "account_status": account_receipt.status,
        "account_id": approved.manual_account_id,
        "event_statuses": [item.status for item in (*receipts, correction)],
        "event_count": len(events),
        "event_hashes": [event.event_hash for event in events],
        "ledger_hash": snapshot.ledger_hash,
        "cash": format(snapshot.cash.available, "f"),
        "position_quantity": format(position.quantity, "f"),
        "position_average_cost": format(position.average_cost, "f"),
        "valuation_complete": snapshot.valuation_complete,
        "owner_approval_hash": approved.request_hash,
    }


def _bootstrap_approved_acceptance_unlocked(
    proposal: Mapping[str, object],
    *,
    approved_request_hash: str,
    approved_at: datetime,
    operator_id: str,
) -> dict[str, object]:
    """Create the exact Manual/Paper accounts after operator approval."""
    approved = approved_acceptance_request(
        proposal, approved_request_hash=approved_request_hash
    )
    timestamp = parse_timestamp(rfc3339(approved_at), field="approved_at")
    if timestamp < approved.generated_at:
        raise ValueError("approval cannot predate proposal")
    operator = canonical_text(operator_id, field="operator_id")
    database, signing_key_path, receipt_path = acceptance_state_paths(approved)
    approved.data_root.mkdir(parents=True, exist_ok=True)
    approved.evidence_root.mkdir(parents=True, exist_ok=True)
    key = load_signing_key(signing_key_path, create=True)
    if receipt_path.exists():
        existing, _existing_approved_at, _signature = _bootstrap_receipt(
            approved,
            key=key,
        )
        atomic_write_json(approved.evidence_root / "bootstrap.json", existing)
        return existing
    persisted_at = acceptance_opened_at(
        database,
        account_ids=(approved.manual_account_id, approved.paper_account_id),
    )
    if persisted_at is not None:
        timestamp = persisted_at
    manual = _bootstrap_manual(
        approved,
        database=database,
        approved_at=timestamp,
        operator_id=operator,
    )
    approval_day = timestamp.astimezone(SHANGHAI).date().isoformat()
    with SqliteAccountEventJournal(str(database)) as journal:
        paper = CreatePaperAccountHandler(
            journal=journal,
            clock=lambda: timestamp,
        ).handle(
            CreatePaperAccountCommand(
                account_id=approved.paper_account_id,
                name="PAP-09 Real Provider Paper Acceptance",
                opened_at=timestamp,
                trade_date=approval_day,
                initial_cash=Decimal(approved.paper_opening_cash),
                idempotency_key="pap09-account-bootstrap-v1",
            )
        )
    with SqlitePaperSessionStore(str(database)):
        pass
    unsigned: dict[str, object] = {
        "schema": BOOTSTRAP_SCHEMA,
        "status": "passed",
        "request_hash": approved.request_hash,
        "approved_at": rfc3339(timestamp),
        "operator_id": operator,
        "manual": manual,
        "paper": {
            "account_id": approved.paper_account_id,
            "account_status": paper.status,
            "opening_event_id": paper.opening_event_id,
            "session_count": count_acceptance_rows(database, "paper_sessions"),
            "execution_count": count_acceptance_rows(database, "paper_executions"),
            "real_broker_connections": 0,
        },
        "signing": {
            "algorithm": "hmac-sha256",
            "private_key_exported": False,
            "private_key_mode": "0600",
        },
    }
    receipt = sign_payload(
        unsigned,
        key=key,
        approval_hash=approved.request_hash,
        previous_signature=None,
    )
    atomic_write_json(receipt_path, receipt)
    atomic_write_json(approved.evidence_root / "bootstrap.json", receipt)
    return receipt


def _session_complete(store: SqlitePaperSessionStore, *, trade_date: str) -> bool:
    session_id = f"pap09-session-{trade_date}"
    session = store.get_session(session_id)
    executions = store.list_executions(session_id)
    reconciliation = store.latest_reconciliation(session_id)
    return bool(
        session is not None
        and session.status is PaperSessionStatus.PAUSED
        and len(executions) == 1
        and executions[0].result.fill is not None
        and executions[0].ledger_event_id is not None
        and reconciliation is not None
        and reconciliation.balanced
        and reconciliation.fill_count == 1
        and reconciliation.ledger_fill_count == 1
    )


def _completed_prefix(
    store: SqlitePaperSessionStore, *, open_dates: Sequence[str], target_days: int
) -> tuple[str, ...]:
    completed: list[str] = []
    seen_incomplete = False
    for trade_date in open_dates[:target_days]:
        is_complete = _session_complete(store, trade_date=trade_date)
        if is_complete and seen_incomplete:
            raise ValueError("persisted Paper sessions are not a consecutive prefix")
        if is_complete:
            completed.append(trade_date)
        else:
            seen_incomplete = True
    return tuple(completed)


def _paper_pre_trade_quantities(
    journal: AccountEventJournalPort,
    *,
    approved: ApprovedAcceptance,
    trade_date: str,
    close: Decimal,
    existing: PaperExecutionRecord | None,
) -> tuple[int, int]:
    account = journal.get_account(approved.paper_account_id)
    if account is None:
        raise RuntimeError("Paper acceptance account disappeared")
    projection = AccountLedgerRebuilder().rebuild(
        account=account,
        events=journal.list_events(approved.paper_account_id),
        as_of=trade_date,
        valuation_prices={InstrumentId(approved.instrument_id): close},
    )
    position = next(
        (
            item
            for item in projection.positions
            if int(item.instrument_id) == approved.instrument_id
        ),
        None,
    )
    quantity = int(position.quantity) if position is not None else 0
    available = int(position.available_quantity) if position is not None else 0
    if existing is not None and existing.result.fill is not None:
        quantity -= existing.result.fill.quantity
    return quantity, available


def record_acceptance_day(request: AcceptanceDayRequest) -> dict[str, object]:
    """Record one exact provider-backed Paper acceptance day."""
    (
        approved,
        database,
        source,
        trade_date,
        settlement_date,
        now,
        operator_id,
        session_prefix,
        pause_reason,
    ) = (
        request.approved,
        request.database,
        request.source,
        request.trade_date,
        request.settlement_date,
        request.now,
        request.operator_id,
        request.session_prefix,
        request.pause_reason,
    )
    session_id = f"{session_prefix}-{trade_date}"
    operate_key = f"{session_id}:operate:v1"
    bar_frame = source.fetch_etf_daily(
        source_ticker=approved.instrument_code,
        start_date=trade_date,
        end_date=trade_date,
    )
    bar = _frame_bar(bar_frame, trade_date=trade_date)
    snapshot_id = f"snapshot:tushare:etf_daily:sha256:{canonical_hash(bar)}"
    decision_at = datetime.combine(
        date.fromisoformat(trade_date),
        time(8, 55),
        tzinfo=SHANGHAI,
    ).astimezone(UTC)
    with (
        SqliteAccountEventJournal(str(database)) as journal,
        SqlitePaperSessionStore(str(database)) as store,
    ):
        reconciler = ReconcilePaperAccount(store=store, account_journal=journal)
        lifecycle = PaperSessionCommandHandler(
            store=store,
            account_journal=journal,
            clock=lambda: now,
            reconciler=reconciler,
        )
        session = store.get_session(session_id)
        if session is None:
            lifecycle.create(
                CreatePaperSessionCommand(
                    session_id=session_id,
                    account_id=approved.paper_account_id,
                    strategy_id=approved.strategy_id,
                    trade_date=trade_date,
                    idempotency_key=f"{session_id}:create:v1",
                )
            )
            lifecycle.start(
                StartPaperSessionCommand(
                    session_id=session_id,
                    idempotency_key=f"{session_id}:start:v1",
                )
            )
        elif session.status is PaperSessionStatus.CREATED:
            lifecycle.start(
                StartPaperSessionCommand(
                    session_id=session_id,
                    idempotency_key=f"{session_id}:start:v1",
                )
            )
        elif session.status is PaperSessionStatus.PAUSED and not store.list_executions(
            session_id
        ):
            raise ValueError("paused Paper session cannot be resumed without evidence")
        existing = store.get_execution(session_id, operate_key)
        position_quantity, available_quantity = _paper_pre_trade_quantities(
            journal,
            approved=approved,
            trade_date=trade_date,
            close=Decimal(str(bar["close"])),
            existing=existing,
        )
        if existing is None:
            previous_close = positive_number(bar["pre_close"], field="bar.pre_close")
            command = OperatePaperOrderCommand(
                session_id=session_id,
                idempotency_key=operate_key,
                order_id=f"{session_id}:order:1",
                instrument_id=approved.instrument_id,
                side="buy",
                order_type="market",
                quantity=approved.paper_order_quantity,
                price=None,
                trade_date=trade_date,
                market=PaperMarketSnapshotInput(
                    dataset_id="etf_daily",
                    source="tushare",
                    source_snapshot_id=snapshot_id,
                    observed_at=now,
                    publication_cutoff=now,
                    open=positive_number(bar["open"], field="bar.open"),
                    high=positive_number(bar["high"], field="bar.high"),
                    low=positive_number(bar["low"], field="bar.low"),
                    close=positive_number(bar["close"], field="bar.close"),
                    prev_close=previous_close,
                    volume=positive_number(bar["volume"], field="bar.volume"),
                    amount=positive_number(bar["amount"], field="bar.amount"),
                    limit_up=None,
                    limit_down=None,
                    avg_volume_20d=None,
                ),
                rules=PaperInstrumentRulesInput(
                    asset_class="etf",
                    exchange="XSHG",
                    tick_size=0.001,
                    lot_size=100,
                    board_segment="fund",
                    settlement_cycle=1,
                    commission_rate=0.0003,
                    min_commission=5.0,
                    stamp_duty_rate=0.0,
                    transfer_fee_rate=0.00001,
                ),
                assumption=PaperFillAssumptionInput(
                    assumption_id="pap09-real-close-v1",
                    version=1,
                    reference_price_field="close",
                    slippage_bps=1.0,
                ),
                decision_at=decision_at,
                execution_at=now,
                settlement_date=settlement_date,
                position_quantity=position_quantity,
                available_quantity=available_quantity,
            )
            execution = OperatePaperSession(
                store=store,
                account_journal=journal,
            ).execute(command)
            info = execution.execution
        else:
            info = OperatePaperSession(
                store=store,
                account_journal=journal,
            ).recover(session_id)[0]
            if (
                info.fill is None
                or existing.lineage.dataset_id != "etf_daily"
                or existing.lineage.source != "tushare"
                or existing.lineage.source_snapshot_id != snapshot_id
                or info.fill.market_snapshot_hash != existing.lineage.snapshot_hash
            ):
                raise ValueError("persisted execution provider bar drifted")
        reconciliation = lifecycle.reconcile(
            ReconcilePaperSessionCommand(
                session_id=session_id,
                idempotency_key=f"{session_id}:eod:v1",
            )
        )
        current = store.get_session(session_id)
        if current is None:
            raise RuntimeError("Paper session disappeared")
        if current.status is PaperSessionStatus.RUNNING:
            session_status = lifecycle.pause(
                PausePaperSessionCommand(
                    session_id=session_id,
                    idempotency_key=f"{session_id}:pause:v1",
                    reason=pause_reason,
                )
            ).session.status
        else:
            session_status = current.status.value
        executions = store.list_executions(session_id)
        persisted = executions[0]
        fill = persisted.result.fill
        if fill is None:
            raise ValueError("Paper order did not produce a fill")
    return {
        "session_id": session_id,
        "session_status": session_status,
        "execution_id": persisted.execution_id,
        "execution_request_hash": persisted.request_hash,
        "execution_count": len(executions),
        "pre_trade_position_quantity": position_quantity,
        "pre_trade_available_quantity": available_quantity,
        "fill_count": reconciliation.fill_count,
        "ledger_fill_count": reconciliation.ledger_fill_count,
        "balanced": reconciliation.balanced,
        "reconciliation_checksum": reconciliation.checksum,
        "ledger_event_id": persisted.ledger_event_id,
        "fill_id": fill.fill_id,
        "fill_price": fill.fill_price,
        "reference_price": fill.reference_price,
        "total_cost": fill.total_cost,
        "market_snapshot_hash": fill.market_snapshot_hash,
        "market_lineage_hash": fill.market_lineage_hash,
        "source_snapshot_id": snapshot_id,
        "bar": bar,
        "decision_at": rfc3339(decision_at),
        "observed_at": rfc3339(persisted.lineage.observed_at),
        "publication_cutoff": rfc3339(persisted.lineage.publication_cutoff),
        "execution_at": rfc3339(fill.event_time),
        "settlement_date": settlement_date,
        "operator_id": operator_id,
    }


def _record_next_paper_day_unlocked(
    proposal: Mapping[str, object],
    *,
    approved_request_hash: str,
    operator_id: str,
    source: AcceptanceMarketSource,
    now: datetime,
    evidence_root: Path | None = None,
    closed_day_authorization: str | None = None,
) -> dict[str, object]:
    """Append at most one closed, published, provider-calendar Paper day."""
    approved = approved_acceptance_request(
        proposal, approved_request_hash=approved_request_hash
    )
    if evidence_root is not None and evidence_root.resolve() != approved.evidence_root:
        raise ValueError("evidence_root does not match exact approval")
    timestamp = parse_timestamp(rfc3339(now), field="now")
    operator = canonical_text(operator_id, field="operator_id")
    database, signing_key_path, _receipt_path = acceptance_state_paths(approved)
    key = load_signing_key(signing_key_path, create=False)
    _receipt, approved_at, _bootstrap_signature = _bootstrap_receipt(approved, key=key)
    progress = verify_soak_progress(
        data_root=approved.data_root,
        evidence_root=approved.evidence_root,
        expected_approval_hash=approved.request_hash,
        require_public=False,
    )
    restore_public_evidence_mirrors(
        data_root=approved.data_root,
        evidence_root=approved.evidence_root,
        progress=progress,
    )
    authorization, local_day, end, open_dates = _eligibility_calendar_context(
        source=source,
        approved_at=approved_at,
        timestamp=timestamp,
        progress=progress,
        closed_day_authorization=closed_day_authorization,
    )
    with SqlitePaperSessionStore(str(database)) as store:
        database_completed = _completed_prefix(
            store,
            open_dates=open_dates,
            target_days=approved.paper_target_days,
        )
    completed = reconcile_completed_dates(
        progress,
        database_completed=database_completed,
    )
    candidate = select_next_eligible_trade_date(
        open_dates=open_dates,
        completed_dates=completed,
        approval_at=approved_at,
        now=timestamp,
        target_days=approved.paper_target_days,
        allow_current_closed_day=end == local_day,
    )
    if candidate is None:
        return {
            "status": (
                "complete"
                if len(completed) >= approved.paper_target_days
                else "waiting_for_next_published_day"
            ),
            "completed_days": len(completed),
            "last_completed_trade_date": completed[-1] if completed else None,
            "calendar_checked_through": end.isoformat(),
        }
    future_open = tuple(item for item in open_dates if item > candidate)
    if not future_open:
        raise ValueError("provider calendar lacks the next settlement trading day")
    previous_signature = _previous_day_signature(
        approved=approved,
        key=key,
        completed_dates=completed,
    )
    execution = record_acceptance_day(
        AcceptanceDayRequest(
            approved=approved,
            database=database,
            source=source,
            trade_date=candidate,
            settlement_date=future_open[0],
            now=timestamp,
            operator_id=operator,
        )
    )
    decision_at = canonical_text(
        execution["decision_at"], field="execution.decision_at"
    )
    execution_at = canonical_text(
        execution["execution_at"], field="execution.execution_at"
    )
    candidate_is_approval_day = (
        date.fromisoformat(candidate) == approved_at.astimezone(SHANGHAI).date()
    )
    candidate_close = datetime.combine(
        date.fromisoformat(candidate),
        time(15, 0),
        tzinfo=SHANGHAI,
    ).astimezone(UTC)
    unsigned: dict[str, object] = {
        "schema": DAY_SCHEMA,
        "status": "recorded",
        "work_package": "PAP-09",
        "qualifies_as_real_soak": True,
        "real_trading_day_ordinal": len(completed) + 1,
        "trade_date": candidate,
        "recorded_at": rfc3339(timestamp),
        "request_hash": approved.request_hash,
        "provider": {
            "name": "tushare",
            "calendar_confirmed_open": True,
            "market_dataset": "etf_daily",
            "source_snapshot_id": execution["source_snapshot_id"],
            "observed_at": execution["observed_at"],
            "bar": execution.pop("bar"),
        },
        "pit": {
            "decision_at": decision_at,
            "execution_at": execution_at,
            "decision_precedes_execution": decision_at < execution_at,
            "trade_day_precedes_execution_local_date": date.fromisoformat(candidate)
            < timestamp.astimezone(SHANGHAI).date(),
            "market_close_at": rfc3339(candidate_close),
            "market_close_precedes_recording": candidate_close <= timestamp,
            "publication_cutoff": execution["publication_cutoff"],
        },
        "execution": {
            key_: value
            for key_, value in execution.items()
            if key_
            not in {
                "source_snapshot_id",
                "observed_at",
                "publication_cutoff",
                "decision_at",
                "execution_at",
            }
        },
        "safety": {
            "paper_only": True,
            "broker_connections": 0,
            "real_orders": 0,
            "daily_execution_count": 1,
        },
    }
    if candidate_is_approval_day:
        if authorization is None:
            raise ValueError(
                "current closed day requires explicit operator authorization"
            )
        unsigned["eligibility_override"] = {
            "kind": "approval_day_after_market_close",
            "operator_authorization": authorization,
            "supersedes_first_day_policy": True,
        }
    signed = sign_payload(
        unsigned,
        key=key,
        approval_hash=approved.request_hash,
        previous_signature=previous_signature,
    )
    durable_path = approved.data_root / "evidence" / "days" / f"{candidate}.json"
    public_path = approved.evidence_root / "days" / f"{candidate}.json"
    if durable_path.exists():
        existing = load_json(durable_path, field=f"day evidence {candidate}")
        if existing != signed:
            raise ValueError("existing day evidence drifted")
    else:
        atomic_write_json(durable_path, signed)
    atomic_write_json(public_path, signed)
    progress = verify_soak_progress(
        data_root=approved.data_root,
        evidence_root=approved.evidence_root,
        expected_approval_hash=approved.request_hash,
    )
    atomic_write_json(approved.evidence_root / "soak-progress.json", progress)
    return signed


@contextmanager
def exclusive_acceptance_state_lock(data_root: Path) -> Generator[None]:
    """Serialize bootstrap/day mutations across scheduler and operator runs."""
    import fcntl  # noqa: PLC0415 - POSIX host lock is entrypoint infrastructure

    lock_path = data_root / "state" / "acceptance.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as stream:
        lock_path.chmod(0o600)
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def bootstrap_approved_acceptance(
    proposal: Mapping[str, object],
    *,
    approved_request_hash: str,
    approved_at: datetime,
    operator_id: str,
) -> dict[str, object]:
    """Serialize and execute one exact account-acceptance bootstrap."""
    approved = approved_acceptance_request(
        proposal, approved_request_hash=approved_request_hash
    )
    with exclusive_acceptance_state_lock(approved.data_root):
        return _bootstrap_approved_acceptance_unlocked(
            proposal,
            approved_request_hash=approved_request_hash,
            approved_at=approved_at,
            operator_id=operator_id,
        )


def record_next_paper_day(
    proposal: Mapping[str, object],
    *,
    approved_request_hash: str,
    operator_id: str,
    source: AcceptanceMarketSource,
    now: datetime,
    evidence_root: Path | None = None,
    closed_day_authorization: str | None = None,
) -> dict[str, object]:
    """Serialize and append at most one exactly approved Paper day."""
    approved = approved_acceptance_request(
        proposal, approved_request_hash=approved_request_hash
    )
    with exclusive_acceptance_state_lock(approved.data_root):
        return _record_next_paper_day_unlocked(
            proposal,
            approved_request_hash=approved_request_hash,
            operator_id=operator_id,
            source=source,
            now=now,
            evidence_root=evidence_root,
            closed_day_authorization=closed_day_authorization,
        )
