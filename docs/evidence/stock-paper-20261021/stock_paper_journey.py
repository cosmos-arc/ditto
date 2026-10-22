"""
#196 股票 Paper 首次真实走单（2026-10-20 滚动选池 → 2026-10-21 执行）.

信号源：selection-run:sha256:b38de6d2…（#585 停牌真值治愈后口径，10 候选，
research-case:sha256:0a7e0454…）。行情/涨跌停取自真实认证分区
（bars/limit 2026.parquet，trade_date=2026-10-21），写入真实账本
data/trading/trading.sqlite。每单执行后重放一次验证幂等，会话 EOD 对账后暂停。
"""

from __future__ import annotations

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
from ditto_execution.paper.sqlite_store import SqlitePaperSessionStore
from ditto_execution.storage.sqlite.account_journal import SqliteAccountEventJournal
from ditto_kernel.identity import InstrumentId
from ditto_portfolio.account_projection import AccountLedgerRebuilder

REPO = Path(__file__).resolve().parents[3]
STATE = REPO / "data"
TRADING_DB = STATE / "trading" / "trading.sqlite"
OUT = Path(__file__).resolve().parent / "report.json"

ACCOUNT_ID = "stock-paper-live-20261021"
SESSION_ID = "stock-paper-live-20261021:s1"
STRATEGY_ID = "stock-core"
RESEARCH_CASE = (
    "research-case:sha256:"
    "0a7e0454f670a8008ff4863ff108444d3dcb3c0bd47138fa8a4df1dd6d4652cc"
)
SIGNAL_AS_OF = datetime(2026, 10, 20, 7, 0, tzinfo=UTC)  # 选池 as_of 15:00 CST
EXECUTION_AT = datetime(2026, 10, 21, 1, 30, tzinfo=UTC)  # 09:30 CST 开盘
TRADE_DATE = date(2026, 10, 21)
SETTLEMENT_DATE = date(2026, 10, 22)
INITIAL_CASH = Decimal("200000")
PER_NAME_BUDGET = 19_000.0
LOT_SIZE = 100
SNAPSHOT_STOCK_DAILY = (
    "snapshot:tushare:stock_daily:sha256:"
    "d6465767689476990d6b03f9769cd43c0199247ee1c18a0b1795315d0bef8ea3"
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


def load_market() -> dict[int, dict[str, object]]:
    """读 10-21 真实 bars 并按标的合并涨跌停真值."""
    ids = [c[0] for c in CANDIDATES]
    bars = pl.read_parquet(STATE / "market/stock/bars/2026.parquet").filter(
        (pl.col("trade_date") == TRADE_DATE) & pl.col("instrument_id").is_in(ids)
    )
    limits = pl.read_parquet(STATE / "market/stock/limit/2026.parquet").filter(
        (pl.col("trade_date") == TRADE_DATE) & pl.col("instrument_id").is_in(ids)
    )
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
    return market


def _order(
    spec: tuple[int, str, float],
    market: dict[int, dict[str, object]],
    index: int,
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
            observed_at=EXECUTION_AT,
            publication_cutoff=EXECUTION_AT,
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
        execution_at=EXECUTION_AT,
        settlement_date=SETTLEMENT_DATE.isoformat(),
        position_quantity=0,
        available_quantity=0,
    )


def _require[T](value: T | None, message: str) -> T:
    if value is None:
        raise RuntimeError(message)
    return value


def main() -> None:
    """执行（幂等一次性）走单并写 report.json."""
    market = load_market()
    report: dict[str, object] = {
        "account_id": ACCOUNT_ID,
        "session_id": SESSION_ID,
        "research_case_id": RESEARCH_CASE,
        "signal_as_of": SIGNAL_AS_OF.isoformat(),
        "trade_date": TRADE_DATE.isoformat(),
        "database": str(TRADING_DB),
        "orders": [],
    }
    with SqliteAccountEventJournal(str(TRADING_DB)) as journal:
        CreatePaperAccountHandler(journal=journal, clock=lambda: EXECUTION_AT).handle(
            CreatePaperAccountCommand(
                account_id=ACCOUNT_ID,
                name="#196 股票 Paper 首次真实走单",
                opened_at=EXECUTION_AT,
                trade_date=TRADE_DATE.isoformat(),
                initial_cash=INITIAL_CASH,
                idempotency_key=f"{ACCOUNT_ID}:create:v1",
            )
        )
    with (
        SqliteAccountEventJournal(str(TRADING_DB)) as journal,
        SqlitePaperSessionStore(str(TRADING_DB)) as store,
    ):
        handler = PaperSessionCommandHandler(
            store=store,
            account_journal=journal,
            clock=lambda: EXECUTION_AT,
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
                command = _order(spec, market, index)
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
            handler.pause(
                PausePaperSessionCommand(
                    session_id=SESSION_ID,
                    idempotency_key=f"{SESSION_ID}:pause:v1",
                    reason="#196 股票 Paper 首次走单 EOD 完成",
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
    OUT.write_bytes(orjson.dumps(report, option=orjson.OPT_INDENT_2, default=str))


if __name__ == "__main__":
    main()
