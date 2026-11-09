"""Save ordinary run bills from actual fills and the execution rule provider."""

from dataclasses import asdict
from math import isclose

from ditto_backtest.statistics import BacktestReport
from ditto_execution.reality.fee import AShareFeeModel
from ditto_kernel.identity import InstrumentId
from ditto_kernel.trading import FeeModel, InstrumentRuleProvider

from ditto_application.exceptions import AppProcessError


def build_fee_statement(
    report: BacktestReport,
    provider: InstrumentRuleProvider | None,
    model: FeeModel | None,
    display_map: dict[InstrumentId, str] | None,
) -> dict[str, object] | None:
    """Never backfill legacy/override costs with a different model at read time."""
    if provider is None or not isinstance(model, AShareFeeModel):
        return None
    rows: list[dict[str, object]] = []
    for fill in report.fill_log:
        day = fill.event_time.date().isoformat()
        schedule = provider.get_fee_schedule(fill.instrument_id, day)
        if schedule is None:
            raise AppProcessError(f"missing executed fee schedule: {fill.fill_id}")
        commission, stamp, transfer = model.components(
            fill.fill_price, fill.filled_quantity, fill.direction, schedule
        )
        if not isclose(
            commission + stamp + transfer, fill.fee, rel_tol=1e-12, abs_tol=1e-8
        ):
            raise AppProcessError(
                f"fee statement disagrees with actual fill: {fill.fill_id}"
            )
        rows.append(
            {
                "fill_id": fill.fill_id,
                "order_id": fill.order_id,
                "instrument_id": int(fill.instrument_id),
                "symbol": (display_map or {}).get(
                    fill.instrument_id, str(fill.instrument_id)
                ),
                "trade_date": day,
                "direction": str(fill.direction),
                "quantity": fill.filled_quantity,
                "price": fill.fill_price,
                "commission": commission,
                "stamp_duty": stamp,
                "transfer_fee": transfer,
                "total_fee": fill.fee,
                "schedule": asdict(schedule),
            }
        )
    return {
        "currency": "CNY",
        "policy": "研究佣金包含经手费、证管费及券商留存。已剔除单列的中登过户费。"
        + "佣金按每笔成交费率及最低费计收。印花税仅股票卖出计收。ETF 不收股票税费。"
        + "金额保留计算精度。不模拟券商逐项分币舍入或同日合单优惠。",
        "rules_observed_at": "2026-11-09",
        "source_ref": "docs/evidence/historical-fees-757.md",
        "final_cash": report.final_account_state.cash.total
        if report.final_account_state is not None
        else None,
        "fills": rows,
    }
