"""
#196 股票 Paper 首次真实走单（2026-10-20 滚动选池 → 2026-10-21 执行）.

信号源：selection-run:sha256:b38de6d2…（#585 停牌真值治愈后口径，10 候选，
research-case:sha256:0a7e0454…）。行情/涨跌停取自真实认证分区
（trade_date=2026-10-21）的留存 payload，仅写入新建隔离根。
完整历史 OHLC 用于事后执行模拟，不证明开盘可见性或策略严格 PIT。
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import sqlite3
import subprocess
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import orjson
import polars as pl
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
from ditto_data.catalog.provider_payload import (
    FilesystemProviderPayloadStore,
    ProviderPayloadArtifact,
)
from ditto_execution.paper.sqlite_store import SqlitePaperSessionStore
from ditto_execution.storage.sqlite.account_journal import SqliteAccountEventJournal
from ditto_kernel.identity import InstrumentId
from ditto_portfolio.account_projection import AccountLedgerRebuilder

REPO = Path(__file__).resolve().parents[3]

ACCOUNT_ID = "stock-paper-live-20261021"
SESSION_ID = "stock-paper-live-20261021:s1"
STRATEGY_ID = "stock-core"
RESEARCH_CASE = (
    "research-case:sha256:"
    "0a7e0454f670a8008ff4863ff108444d3dcb3c0bd47138fa8a4df1dd6d4652cc"
)
SIGNAL_AS_OF = datetime(2026, 10, 20, 7, 0, tzinfo=UTC)  # 选池 as_of 15:00 CST
TRADE_DATE = date(2026, 10, 21)
SETTLEMENT_DATE = date(2026, 10, 22)
INITIAL_CASH = Decimal("200000")
PER_NAME_BUDGET = 19_000.0
LOT_SIZE = 100
SNAPSHOT_STOCK_DAILY = (
    "snapshot:tushare:stock_daily:sha256:"
    "d6465767689476990d6b03f9769cd43c0199247ee1c18a0b1795315d0bef8ea3"
)
SNAPSHOT_STOCK_LIMIT = (
    "snapshot:tushare:stock_limit:sha256:"
    "0bdf6624d4901f33d97d301afab0185e39ad64b29be411dc5b4d0cef4308526f"
)

CANDIDATES: tuple[tuple[int, str, float], ...] = (  # (instrument_id, name, score)
    (1001032, "新华传媒", 1.0),
    (1004130, "善水科技", 0.9998),
    (1003933, "澳弘电子", 0.9995),
    (1002532, "新华文轩", 0.9993),
    (1000588, "时代万恒", 0.9991),
    (1001563, "慈文传媒", 0.9989),
    (1004594, "高凌信息", 0.9987),
    (1005005, "近岸蛋白", 0.9986),
    (1005248, "众捷股份", 0.9984),
    (1002589, "郑中设计", 0.998),
)


def _board(ticker: str) -> tuple[str, str, float]:
    """(exchange, board_segment, price_limit_pct) 从源 ticker 推板信息."""
    exchange = "XSHG" if ticker.endswith(".SH") else "XSHE"
    code = ticker.split(".", maxsplit=1)[0]
    if ticker.endswith(".SH") and code.startswith("688"):
        return exchange, "star", 0.2
    if ticker.endswith(".SZ") and code.startswith(("300", "301")):
        return exchange, "chinext", 0.2
    return exchange, "main", 0.1


def load_market(source_root: Path) -> tuple[dict[int, dict[str, object]], list[dict]]:
    """Verify the original retained responses; never relabel today's partitions."""
    ids = [c[0] for c in CANDIDATES]
    frames = []
    evidence = []
    with sqlite3.connect(
        f"file:{source_root}/metadata/metadata.sqlite?mode=ro", uri=True
    ) as connection:
        connection.row_factory = sqlite3.Row
        instruments = pl.DataFrame(
            [
                dict(row)
                for row in connection.execute(
                    "SELECT instrument_id, ticker || CASE exchange WHEN 'SSE' "
                    "THEN '.SH' WHEN 'SZSE' THEN '.SZ' END AS source_ticker "
                    "FROM instrument"
                )
            ]
        ).filter(pl.col("instrument_id").is_in(ids))
        for snapshot_id in (SNAPSHOT_STOCK_DAILY, SNAPSHOT_STOCK_LIMIT):
            row = connection.execute(
                "SELECT * FROM provider_snapshots WHERE snapshot_id=?", (snapshot_id,)
            ).fetchone()
            if row is None or not row["payload_retained"]:
                raise RuntimeError(f"retained snapshot missing: {snapshot_id}")
            frame = (
                FilesystemProviderPayloadStore(source_root)
                .read_payload(
                    ProviderPayloadArtifact(
                        dataset_id=row["dataset_id"],
                        source=row["source"],
                        checksum=row["checksum"],
                        row_count=row["row_count"],
                        uri=row["payload_uri"],
                        schema_fingerprint=row["schema_fingerprint"],
                    )
                )
                .filter(pl.col("trade_date") == TRADE_DATE)
                .join(instruments, on="source_ticker", how="inner", validate="1:1")
            )
            frames.append(frame)
            evidence.append(
                {
                    "snapshot_id": snapshot_id,
                    "observed_at": row["created_at"],
                    "knowledge_date": str(frame["knowledge_date"].max()),
                    "payload_uri": row["payload_uri"],
                    "sha256": hashlib.sha256(
                        (source_root / row["payload_uri"]).read_bytes()
                    ).hexdigest(),
                }
            )
    bars, limits = frames
    limit_by_id = {r["instrument_id"]: r for r in limits.to_dicts()}
    market: dict[int, dict[str, object]] = {}
    for row in bars.to_dicts():
        lim = limit_by_id.get(row["instrument_id"])
        if lim is None:
            raise RuntimeError(f"limit truth missing: {row['instrument_id']}")
        market[row["instrument_id"]] = {
            **row,
            "up_limit": lim["up_limit"],
            "down_limit": lim["down_limit"],
        }
    missing = set(ids) - set(market)
    if missing:
        raise RuntimeError(f"bars missing for {missing}")
    return market, evidence


def _order(
    spec: tuple[int, str, float],
    market: dict[int, dict[str, object]],
    index: int,
    execution_at: datetime,
) -> OperatePaperOrderCommand:
    instrument_id, _, _ = spec
    bar = market[instrument_id]
    ticker = str(bar["source_ticker"])
    exchange, board, limit_pct = _board(ticker)
    qty = int(PER_NAME_BUDGET / float(bar["open"]) // LOT_SIZE) * LOT_SIZE
    if qty < LOT_SIZE:
        raise RuntimeError(f"budget too small for {ticker} open={bar['open']}")
    return OperatePaperOrderCommand(
        session_id=SESSION_ID,
        idempotency_key=f"{SESSION_ID}:order:{index}:v1",
        order_id=f"{SESSION_ID}:order:{index}",
        instrument_id=instrument_id,
        side="buy",
        order_type="market",
        quantity=qty,
        price=None,
        trade_date=TRADE_DATE.isoformat(),
        market=PaperMarketSnapshotInput(
            dataset_id="stock_daily",
            source="tushare",
            source_snapshot_id=SNAPSHOT_STOCK_DAILY,
            observed_at=execution_at,
            publication_cutoff=execution_at,
            open=float(bar["open"]),
            high=float(bar["high"]),
            low=float(bar["low"]),
            close=float(bar["close"]),
            prev_close=float(bar["pre_close"]),
            volume=float(bar["volume"]),
            amount=float(bar["amount"]),
            is_suspended=False,
            limit_up=float(bar["up_limit"]),
            limit_down=float(bar["down_limit"]),
            avg_volume_20d=None,
        ),
        rules=PaperInstrumentRulesInput(
            asset_class="stock",
            exchange=exchange,
            tick_size=0.01,
            lot_size=LOT_SIZE,
            board_segment=board,
            settlement_cycle=1,
            commission_rate=0.0003,
            min_commission=5.0,
            stamp_duty_rate=0.0005,
            transfer_fee_rate=0.00001,
            price_limit_pct=limit_pct,
        ),
        assumption=PaperFillAssumptionInput(
            assumption_id="paper-default-v1",
            version=1,
            reference_price_field="open",
            slippage_bps=10.0,
        ),
        decision_at=SIGNAL_AS_OF,
        execution_at=execution_at,
        settlement_date=SETTLEMENT_DATE.isoformat(),
    )


def _require[T](value: T | None, message: str) -> T:
    if value is None:
        raise RuntimeError(message)
    return value


def verify_restart(
    trading_db: Path, market: dict[int, dict[str, object]], execution_at: datetime
) -> dict[str, object]:
    """Reopen storage, replay orders, and reconcile with a new idempotency key."""
    with (
        SqliteAccountEventJournal(str(trading_db)) as journal,
        SqlitePaperSessionStore(str(trading_db)) as store,
    ):
        before = len(journal.list_events(ACCOUNT_ID))
        operator = OperatePaperSession(store=store, account_journal=journal)
        recovered = operator.recover(SESSION_ID)
        for index, spec in enumerate(CANDIDATES, start=1):
            if (
                operator.execute(_order(spec, market, index, execution_at)).status
                != "replayed"
            ):
                raise RuntimeError("restart did not replay the original execution")
        if len(journal.list_events(ACCOUNT_ID)) != before:
            raise RuntimeError("restart duplicated ledger events")
        handler = PaperSessionCommandHandler(
            store=store,
            account_journal=journal,
            clock=lambda: execution_at,
            reconciler=ReconcilePaperAccount(store=store, account_journal=journal),
        )
        reconciled = handler.reconcile(
            ReconcilePaperSessionCommand(
                session_id=SESSION_ID,
                idempotency_key=f"{SESSION_ID}:issue710-restart-eod",
            )
        )
        if not reconciled.balanced:
            raise RuntimeError("restart reconciliation is unbalanced")
        handler.pause(
            PausePaperSessionCommand(
                session_id=SESSION_ID,
                idempotency_key=f"{SESSION_ID}:pause:v1",
                reason="#710 historical simulation and restart EOD complete",
            )
        )
        return {
            "recovered": len(recovered),
            "ledger_events": before,
            "balanced": reconciled.balanced,
        }


def main() -> None:
    """Run the historical simulation once in a fresh, explicit acceptance root."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--run-root", type=Path, required=True)
    args = parser.parse_args()
    source_root = args.source_root.resolve(strict=True)
    run_root = args.run_root.resolve()
    if (
        source_root == run_root
        or source_root in run_root.parents
        or run_root in source_root.parents
    ):
        raise ValueError("source and acceptance roots must be independent")
    market, sources = load_market(source_root)
    execution_at = datetime.now(UTC)
    for source in sources:
        if (
            datetime.fromisoformat(source["observed_at"]) > execution_at
            or date.fromisoformat(source["knowledge_date"]) >= execution_at.date()
        ):
            raise ValueError("source evidence is not yet visible")
    run_root.mkdir(parents=True, exist_ok=False)
    trading_db = run_root / "paper.sqlite"
    report: dict[str, object] = {
        "code_sha": subprocess.check_output(  # noqa: S603 - resolved git, fixed read-only arguments
            [_require(shutil.which("git"), "git missing"), "rev-parse", "HEAD"],
            cwd=REPO,
            text=True,
        ).strip(),
        "acceptance_mode": "historical_simulation",
        "qualifies_as_strict_pit": False,
        "qualifies_as_wall_clock_soak": False,
        "execution_at": execution_at.isoformat(),
        "sources": sources,
        "safety": {"broker_connections": 0, "real_orders": 0, "strategy_publishes": 0},
        "account_id": ACCOUNT_ID,
        "session_id": SESSION_ID,
        "research_case_id": RESEARCH_CASE,
        "signal_as_of": SIGNAL_AS_OF.isoformat(),
        "trade_date": TRADE_DATE.isoformat(),
        "database": str(trading_db),
        "orders": [],
    }
    with SqliteAccountEventJournal(str(trading_db)) as journal:
        CreatePaperAccountHandler(journal=journal, clock=lambda: execution_at).handle(
            CreatePaperAccountCommand(
                account_id=ACCOUNT_ID,
                name="#196 股票 Paper 首次真实走单",
                opened_at=execution_at,
                trade_date=TRADE_DATE.isoformat(),
                initial_cash=INITIAL_CASH,
                idempotency_key=f"{ACCOUNT_ID}:create:v1",
            )
        )
    with (
        SqliteAccountEventJournal(str(trading_db)) as journal,
        SqlitePaperSessionStore(str(trading_db)) as store,
    ):
        handler = PaperSessionCommandHandler(
            store=store,
            account_journal=journal,
            clock=lambda: execution_at,
            reconciler=ReconcilePaperAccount(store=store, account_journal=journal),
        )
        if store.get_session(SESSION_ID) is None:
            handler.create(
                CreatePaperSessionCommand(
                    session_id=SESSION_ID,
                    account_id=ACCOUNT_ID,
                    strategy_id=STRATEGY_ID,
                    trade_date=TRADE_DATE.isoformat(),
                    idempotency_key=f"{SESSION_ID}:create:v1",
                )
            )
            handler.start(
                StartPaperSessionCommand(
                    session_id=SESSION_ID, idempotency_key=f"{SESSION_ID}:start:v1"
                )
            )
            operator = OperatePaperSession(store=store, account_journal=journal)
            for index, spec in enumerate(CANDIDATES, start=1):
                command = _order(spec, market, index, execution_at)
                first = operator.execute(command)
                replay = operator.execute(command)
                if (
                    first.status not in {"created", "replayed"}
                    or replay.status != "replayed"
                ):
                    outcome = f"{first.status}/{replay.status}"
                    raise RuntimeError(
                        f"order {index} not executed/replayed: {outcome}"
                    )
            handler.reconcile(
                ReconcilePaperSessionCommand(
                    session_id=SESSION_ID, idempotency_key=f"{SESSION_ID}:eod:v1"
                )
            )
        session = _require(store.get_session(SESSION_ID), "session missing")
        reconciliation = _require(
            store.latest_reconciliation(SESSION_ID), "reconciliation missing"
        )
        specs = {spec[0]: spec for spec in CANDIDATES}
        for record in store.list_executions(SESSION_ID):
            order = record.result.order.ticket.order
            spec = specs[int(order.instrument_id)]
            fill = record.result.fill
            # 涨停买入拒单（limit_up_no_buy）等市场规则 NoFill 是合法结果，如实留档。
            report["orders"].append(
                {
                    "order_id": order.order_id,
                    "instrument_id": spec[0],
                    "name": spec[1],
                    "score": spec[2],
                    "ticker": market[spec[0]]["source_ticker"],
                    "quantity": order.quantity,
                    "filled": fill is not None,
                    "reality_status": record.result.status.value,
                    "no_fill_reason": record.result.reason,
                    "fill_price": fill.fill_price if fill else None,
                    "fill_quantity": fill.quantity if fill else 0,
                    "reference_price": fill.reference_price if fill else None,
                    "slippage": fill.slippage if fill else None,
                    "commission": fill.commission if fill else None,
                    "tax": fill.tax if fill else None,
                    "transfer_fee": fill.transfer_fee if fill else None,
                    "total_cost": fill.total_cost if fill else None,
                }
            )
        account = _require(journal.get_account(ACCOUNT_ID), "account missing")
        ledger = AccountLedgerRebuilder().rebuild(
            account=account,
            events=journal.list_events(ACCOUNT_ID),
            as_of=TRADE_DATE.isoformat(),
            valuation_prices={
                InstrumentId(spec[0]): Decimal(str(market[spec[0]]["close"]))
                for spec in CANDIDATES
            },
        )
        report["summary"] = {
            "session_status": session.status,
            "reconciliation_balanced": reconciliation.balanced,
            "reconciliation_order_count": reconciliation.order_count,
            "reconciliation_fill_count": reconciliation.fill_count,
            "reconciliation_ledger_fill_count": reconciliation.ledger_fill_count,
            "filled_orders": sum(1 for o in report["orders"] if o["filled"]),
            "ledger_hash": ledger.ledger_hash,
            "cash": str(ledger.cash),
            "positions": {
                str(position.instrument_id): {
                    "quantity": position.quantity,
                    "market_value": str(position.market_value),
                }
                for position in ledger.positions
            },
            "total_market_value": str(
                sum((p.market_value for p in ledger.positions), Decimal("0"))
            ),
        }
    report["restart"] = verify_restart(trading_db, market, execution_at)
    report["summary"]["session_status"] = "paused"
    (run_root / "report.json").write_bytes(
        orjson.dumps(report, option=orjson.OPT_INDENT_2, default=str)
    )


if __name__ == "__main__":
    main()
