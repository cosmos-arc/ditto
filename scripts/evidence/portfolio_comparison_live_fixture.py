"""Seed an isolated CMP-07 live fixture and prove the production query path.

The fixture is deliberately restricted to a fresh directory below ``/private/tmp``.
It never reaches a provider and never writes to a user's configured Ditto data root.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlencode

import orjson
import polars as pl
from ditto_application.commands.account_ledger import (
    CreateAccountCommand,
    CreateAccountHandler,
    ManualAccountCommandHandler,
    ManualEventInput,
    RecordManualEventCommand,
    TradeEventTerms,
)
from ditto_application.commands.paper_account import (
    CreatePaperAccountCommand,
    CreatePaperAccountHandler,
)
from ditto_application.commands.paper_session import (
    CreatePaperSessionCommand,
    PaperSessionCommandHandler,
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
from ditto_application.queries.account_ledger import AccountLedgerQuery
from ditto_application.queries.portfolio_comparison import (
    GetPortfolioComparisonQuery,
    PortfolioComparisonRequest,
)
from ditto_application.queries.portfolio_comparison_source import (
    LivePortfolioComparisonSource,
)
from ditto_application.queries.portfolio_scenario import (
    PortfolioScenarioRequest,
    PreviewPortfolioScenarioQuery,
)
from ditto_application.queries.technical_analysis_source import (
    ProviderPayloadTechnicalAnalysisSource,
)
from ditto_application.signal_package_contract import compute_signal_package_checksum
from ditto_data.catalog import DataAssetRef
from ditto_data.catalog.provider_payload import FilesystemProviderPayloadStore
from ditto_data.catalog.source_snapshot import ProviderSnapshot, ProviderSnapshotDraft
from ditto_data.catalog.source_snapshot_store import SQLiteProviderSnapshotStore
from ditto_execution.paper.sqlite_store import SqlitePaperSessionStore
from ditto_execution.storage.sqlite.account_journal import SqliteAccountEventJournal
from ditto_kernel.identity import InstrumentId
from ditto_platform.foundation import SQLiteClient, SQLitePool
from ditto_strategy.models import ArtifactKind, StrategyArtifactRecord
from ditto_strategy.storage.sqlite.services.strategy_artifact_service import (
    StrategyArtifactService,
)
from ditto_strategy.storage.sqlite.strategy_artifact_store import (
    SQLiteStrategyArtifactReader,
    SQLiteStrategyArtifactWriter,
)

AS_OF = "2026-08-31"
NOW = datetime(2026, 8, 31, 7, 0, tzinfo=UTC)
CUTOFF = datetime(2026, 8, 31, 7, 30, tzinfo=UTC)
STRATEGY_ID = "cmp-live-strategy"
MODEL_ID = "cmp-live-model"
PAPER_ACCOUNT_ID = "cmp-live-paper"
MANUAL_ACCOUNT_ID = "cmp-live-manual"
PAPER_SESSION_ID = "cmp-live-session"
STOCK_ID = 600519
ETF_ID = 510300


def _fresh_temporary_root(raw: str) -> Path:
    root = Path(raw).expanduser().resolve(strict=False)
    temporary_root = Path("/private/tmp").resolve()
    if not root.is_relative_to(temporary_root):
        raise ValueError("--data-root must resolve below /private/tmp")
    if root.exists() and any(root.iterdir()):
        raise ValueError("--data-root must be absent or empty")
    root.mkdir(parents=True, exist_ok=True)
    return root


def _payload_and_snapshot(
    root: Path,
    snapshot_store: SQLiteProviderSnapshotStore,
) -> ProviderSnapshot:
    payload = pl.DataFrame(
        {
            "instrument_id": [STOCK_ID, ETF_ID],
            "trade_date": [AS_OF, AS_OF],
            "open": [498.0, 39.8],
            "high": [506.0, 40.4],
            "low": [496.0, 39.6],
            "close": [500.0, 40.0],
            "volume": [1_200_000.0, 8_500_000.0],
            "amount": [600_000_000.0, 340_000_000.0],
            "published_at": [NOW, NOW],
            "available_at": [NOW, NOW],
        }
    )
    artifact = FilesystemProviderPayloadStore(root).retain_payload(
        dataset_id="stock_daily",
        source="cmp_fixture",
        payload=payload,
    )
    snapshot = ProviderSnapshot.create(
        ProviderSnapshotDraft(
            dataset_id="stock_daily",
            source="cmp_fixture",
            request_start=AS_OF,
            request_end=AS_OF,
            schema_version="market.stock_daily.v1",
            checksum=artifact.checksum,
            canonical_asset=DataAssetRef(
                dataset_id="stock_daily",
                namespace="market",
                partition_keys=(f"trade_date={AS_OF}",),
            ),
            request_parameters_hash="sha256:cmp-live-request-v1",
            response_metadata=(("fixture", "cmp-07-live"),),
            license_record_id="license:cmp-fixture:v1",
            row_count=artifact.row_count,
            payload_uri=artifact.uri,
            payload_retained=True,
            created_at=NOW,
        )
    )
    snapshot_store.append_snapshot(snapshot)
    return snapshot


def _signal_package(
    artifacts: StrategyArtifactService,
    snapshot_id: str,
) -> StrategyArtifactRecord:
    payload: dict[str, object] = {
        "dataset_snapshot_ids": {"stock_daily": snapshot_id},
        "factor_ids": [],
        "factor_values": {},
        "intents": [],
        "risk_flags": [],
        "selection_reasons": {
            str(STOCK_ID): {"target_weight": 0.55},
            str(ETF_ID): {"target_weight": 0.30},
        },
        "signal_date": AS_OF,
        "strategy_id": STRATEGY_ID,
        "strategy_version": "1",
    }
    checksum = compute_signal_package_checksum(payload)
    record = StrategyArtifactRecord(
        artifact_id=MODEL_ID,
        strategy_id=STRATEGY_ID,
        run_id=f"eod-{AS_OF}-{STRATEGY_ID}-1",
        artifact_type=ArtifactKind.SIGNAL_PACKAGE,
        file_path="evidence/cmp-live-signal-package.json",
        metadata={
            **payload,
            "schema_version": "1.0",
            "business_payload": payload,
            "batch_key": f"eod-{AS_OF}-{STRATEGY_ID}-1",
            "checksum": checksum,
            "no_rebalance": True,
            "outcome": "no_rebalance",
        },
        status="active",
        created_at=NOW.isoformat(),
    )
    return artifacts.save_artifact(record)


def _paper_command(
    *,
    instrument_id: int,
    order_id: str,
    quantity: int,
    close: float,
    order_type: str,
    price: float | None,
) -> OperatePaperOrderCommand:
    return OperatePaperOrderCommand(
        session_id=PAPER_SESSION_ID,
        idempotency_key=f"cmp-live:{order_id}",
        order_id=order_id,
        instrument_id=instrument_id,
        side="buy",
        order_type=order_type,
        quantity=quantity,
        price=price,
        trade_date=AS_OF,
        market=PaperMarketSnapshotInput(
            dataset_id="stock_daily",
            source="cmp_fixture",
            source_snapshot_id="cmp-live-order-snapshot",
            observed_at=NOW,
            publication_cutoff=NOW,
            open=close,
            high=close,
            low=close,
            close=close,
            prev_close=close,
            volume=1_000_000.0,
            amount=close * 1_000_000,
        ),
        rules=PaperInstrumentRulesInput(
            asset_class="stock" if instrument_id == STOCK_ID else "etf",
            exchange="XSHG",
            tick_size=0.01,
            lot_size=100,
            board_segment="main" if instrument_id == STOCK_ID else "fund",
            settlement_cycle=1,
            commission_rate=0.0003,
            min_commission=5.0,
            stamp_duty_rate=0.0005 if instrument_id == STOCK_ID else 0.0,
            transfer_fee_rate=0.00001,
        ),
        assumption=PaperFillAssumptionInput(
            assumption_id="cmp-live-fill-v1",
            version=1,
            reference_price_field="close",
            slippage_bps=5.0,
        ),
        decision_at=NOW,
        execution_at=NOW,
        settlement_date="2026-09-01",
        position_quantity=0,
        available_quantity=0,
    )


def _accounts(
    journal: SqliteAccountEventJournal,
    sessions: SqlitePaperSessionStore,
) -> None:
    CreatePaperAccountHandler(journal=journal, clock=lambda: NOW).handle(
        CreatePaperAccountCommand(
            account_id=PAPER_ACCOUNT_ID,
            name="CMP Live Paper",
            opened_at=NOW,
            trade_date=AS_OF,
            initial_cash=Decimal("150000"),
            idempotency_key="cmp-live-paper-open",
        )
    )
    session_handler = PaperSessionCommandHandler(
        store=sessions,
        account_journal=journal,
        clock=lambda: NOW,
    )
    session_handler.create(
        CreatePaperSessionCommand(
            session_id=PAPER_SESSION_ID,
            account_id=PAPER_ACCOUNT_ID,
            strategy_id=STRATEGY_ID,
            trade_date=AS_OF,
            idempotency_key="cmp-live-session-create",
        )
    )
    session_handler.start(
        StartPaperSessionCommand(
            session_id=PAPER_SESSION_ID,
            idempotency_key="cmp-live-session-start",
        )
    )
    operator = OperatePaperSession(store=sessions, account_journal=journal)
    operator.execute(
        _paper_command(
            instrument_id=STOCK_ID,
            order_id="cmp-live-paper-fill",
            quantity=100,
            close=500.0,
            order_type="market",
            price=None,
        )
    )
    operator.execute(
        _paper_command(
            instrument_id=ETF_ID,
            order_id="cmp-live-paper-unfilled",
            quantity=1000,
            close=40.0,
            order_type="limit",
            price=39.0,
        )
    )

    CreateAccountHandler(journal=journal).handle(
        CreateAccountCommand.manual(
            account_id=MANUAL_ACCOUNT_ID,
            name="CMP Live Manual",
            opened_at=NOW,
        )
    )
    manual = ManualAccountCommandHandler(journal=journal, clock=lambda: NOW)
    manual.record(
        RecordManualEventCommand(
            account_id=MANUAL_ACCOUNT_ID,
            event=ManualEventInput.cash(
                event_type="opening_cash",
                trade_date=AS_OF,
                settlement_date=AS_OF,
                idempotency_key="cmp-live-manual-cash",
                actor="cmp-live-fixture",
                amount=Decimal("150000"),
            ),
        )
    )
    for instrument_id, quantity, price in (
        (STOCK_ID, Decimal("80"), Decimal("480")),
        (ETF_ID, Decimal("500"), Decimal("39")),
    ):
        manual.record(
            RecordManualEventCommand(
                account_id=MANUAL_ACCOUNT_ID,
                event=ManualEventInput.buy_or_sell(
                    side="buy",
                    trade_date=AS_OF,
                    settlement_date=AS_OF,
                    idempotency_key=f"cmp-live-manual-buy-{instrument_id}",
                    actor="cmp-live-fixture",
                    instrument_id=InstrumentId(instrument_id),
                    terms=TradeEventTerms(
                        quantity=quantity,
                        price=price,
                        fees=Decimal("5"),
                    ),
                ),
            )
        )


def seed(root: Path) -> dict[str, object]:
    """Write the isolated fixture and return exact browser/API identities."""
    database = root / "metadata" / "metadata.sqlite"
    database.parent.mkdir(parents=True, exist_ok=True)
    pool = SQLitePool(str(database))
    client = SQLiteClient(pool)
    try:
        snapshot_store = SQLiteProviderSnapshotStore(client)
        payload_store = FilesystemProviderPayloadStore(root)
        snapshot = _payload_and_snapshot(root, snapshot_store)
        artifact_writer = SQLiteStrategyArtifactWriter(pool)
        artifact_writer.init_schema()
        artifacts = StrategyArtifactService(
            reader=SQLiteStrategyArtifactReader(pool),
            writer=artifact_writer,
        )
        artifact = _signal_package(artifacts, snapshot.snapshot_id)
        journal = SqliteAccountEventJournal(client)
        sessions = SqlitePaperSessionStore(client)
        _accounts(journal, sessions)
        request = PortfolioComparisonRequest(
            strategy_id=STRATEGY_ID,
            model_portfolio_id=MODEL_ID,
            paper_account_id=PAPER_ACCOUNT_ID,
            manual_account_id=MANUAL_ACCOUNT_ID,
            paper_session_id=PAPER_SESSION_ID,
            as_of=AS_OF,
            knowledge_cutoff=CUTOFF,
            publication_cutoff=CUTOFF,
            source_snapshot_ids=(snapshot.snapshot_id,),
        )
        query = GetPortfolioComparisonQuery(
            source=LivePortfolioComparisonSource(
                artifact_reader=artifacts,
                account_query=AccountLedgerQuery(journal=journal),
                paper_store=sessions,
                snapshot_reader=snapshot_store,
                valuation_source=ProviderPayloadTechnicalAnalysisSource(
                    snapshot_reader=snapshot_store,
                    payload_reader=payload_store,
                ),
            )
        )
        comparison = query.get(request)
        scenario = PreviewPortfolioScenarioQuery(comparison=query).preview(
            PortfolioScenarioRequest(
                comparison=request,
                baseline_kind="paper",
                excluded_instrument_ids=frozenset({ETF_ID}),
                max_position_weight=Decimal("0.80"),
                cash_reserve_weight=Decimal("0.20"),
                market_shock=-0.08,
            )
        )
        query_params: list[tuple[str, str]] = [
            ("mode", "comparison"),
            ("strategy_id", STRATEGY_ID),
            ("model_portfolio_id", MODEL_ID),
            ("paper_account_id", PAPER_ACCOUNT_ID),
            ("manual_account_id", MANUAL_ACCOUNT_ID),
            ("paper_session_id", PAPER_SESSION_ID),
            ("as_of", AS_OF),
            ("knowledge_cutoff", CUTOFF.isoformat()),
            ("publication_cutoff", CUTOFF.isoformat()),
            ("source_snapshot_ids", snapshot.snapshot_id),
            ("valuation_snapshot_id", comparison.valuation_snapshot_id),
        ]
        return {
            "data_root": str(root),
            "database": str(database),
            "artifact_id": artifact.artifact_id,
            "artifact_checksum": artifact.metadata["checksum"],
            "source_snapshot_id": snapshot.snapshot_id,
            "valuation_snapshot_id": comparison.valuation_snapshot_id,
            "paper_unfilled_bps": str(
                comparison.model_vs_paper.attribution.unfilled_bps
            ),
            "paper_fee_amount": str(comparison.model_vs_paper.attribution.fee_amount),
            "manual_user_choice_bps": str(
                comparison.model_vs_manual.attribution.user_choice_bps
            ),
            "scenario_turnover": scenario.risk.turnover,
            "frontend_path": f"/trading/portfolio?{urlencode(query_params)}",
        }
    finally:
        pool.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", required=True)
    args = parser.parse_args()
    root = _fresh_temporary_root(args.data_root)
    print(orjson.dumps(seed(root), option=orjson.OPT_SORT_KEYS).decode())


if __name__ == "__main__":
    main()
