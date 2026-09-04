"""Seed an isolated production database for the R1/R4 live acceptance.

This helper is deliberately test-only. It reuses the deterministic R1 E2E
harness, never reaches a provider, and refuses to touch a non-temporary root.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path

from ditto_application.processes.execution.eod_coordinator import EodStrategyOutcome
from ditto_application.processes.risk.persistence import DailyRiskProjectionRecord
from ditto_application.queries.daily_decision import DailyDecisionV2Report
from ditto_application.queries.daily_decision_v3 import (
    DailyDecisionV3Projection,
    FactorRiskSection,
    PortfolioConstructionSection,
    ProvenanceSection,
    ReconciliationSection,
    StressTestSection,
    TailRiskSection,
)
from ditto_apps.registry.infra.risk_persistence import (
    SQLiteRiskPersistence,
    initialize_r4_risk_schema,
)
from e2e import test_r1_daily_manual_trading as r1


def _temporary_root() -> Path:
    raw = os.environ.get("DITTO_STATE_ROOT", "")
    if os.environ.get("DITTO_ENVIRONMENT") != "testing":
        raise RuntimeError("DITTO_ENVIRONMENT=testing is required")
    root = Path(raw).expanduser().resolve()
    if not raw or not root.is_relative_to(Path("/private/tmp")):
        raise RuntimeError("DITTO_STATE_ROOT must resolve below /private/tmp")
    return root


def _projection() -> DailyDecisionV3Projection:
    return DailyDecisionV3Projection(
        portfolio_construction=PortfolioConstructionSection(
            status="optimal",
            mode="mvo",
            policy_digest="sha256:r1-r4-live-policy",
            solver="OSQP",
            solver_version="1.1.3",
            solver_status="optimal",
            duration_ms=11.8,
        ),
        tail_risk=TailRiskSection(0.041, 0.032, 0.029, 0.031, 42),
        factor_risk=FactorRiskSection(
            availability="available",
            total_risk=0.127,
            marginal_contributions={"market": 0.071, "size": 0.033},
            percentage_contributions={"market": 0.68, "size": 0.32},
            euler_residual=0.0,
        ),
        stress_tests=StressTestSection(
            catalog_version="r4-live-v1",
            losses={"market_crash": 0.087, "liquidity_shock": 0.046},
        ),
        reconciliation=ReconciliationSection(
            status="reconciled",
            differences=(),
            alert_idempotency_key=None,
        ),
        provenance=ProvenanceSection(
            decision_time="2026-07-10T15:00:00+08:00",
            knowledge_cutoff="2026-07-10T15:00:00+08:00",
            publication_cutoff="2026-07-10T15:00:00+08:00",
            source_snapshot_ids=("sha256:r1-r4-live-market",),
            generated_at="2026-07-10T15:01:00+08:00",
        ),
    )


def _seed_identity(
    database: Path,
    *,
    strategy_id: str,
    account_id: str,
    current_weight: float,
    target_weight: float,
) -> tuple[EodStrategyOutcome, DailyDecisionV2Report]:
    r1.STRATEGY_ID = strategy_id
    r1.ACCOUNT_ID = account_id
    harness = r1._harness(database)
    try:
        harness.bootstrap()
        harness.import_baseline(current_weight=current_weight)
        outcome = harness.run_eod(target_weight=target_weight)
        decision = harness.decision()
        return outcome, decision
    finally:
        harness.pool.close_all()


def main() -> None:
    root = _temporary_root()
    database = root / "metadata" / "metadata.sqlite"
    database.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(database) as connection:
        initialize_r4_risk_schema(connection)

    if os.environ.get("DITTO_ACCEPTANCE_ADDITIONAL") == "1":
        review_outcome, review = _seed_identity(
            database,
            strategy_id="seed_etf_trend_swing",
            account_id="r4-review",
            current_weight=0.4,
            target_weight=0.4,
        )
        blocked_outcome, blocked = _seed_identity(
            database,
            strategy_id="seed_stock_selection_rotation",
            account_id="r4-blocked",
            current_weight=0.0,
            target_weight=0.4,
        )
        review_sleeve_id = str(review.identity["sleeve_id"])
        SQLiteRiskPersistence(lambda: sqlite3.connect(database)).append_daily_report(
            DailyRiskProjectionRecord(
                report_id="r4-live-review",
                strategy_id="seed_etf_trend_swing",
                account_id="r4-review",
                sleeve_id=review_sleeve_id,
                trade_date=r1.SIGNAL_DATE,
                projection=_projection(),
                created_at="2026-07-10T15:02:00+08:00",
            )
        )
        sys.stdout.write(
            json.dumps(
                {
                    "review": {
                        "strategy_id": "seed_etf_trend_swing",
                        "account_id": "r4-review",
                        "readiness": review.readiness["status"],
                        "outcome": review_outcome.status,
                    },
                    "blocked": {
                        "strategy_id": "seed_stock_selection_rotation",
                        "account_id": "r4-blocked",
                        "readiness": blocked.readiness["status"],
                        "outcome": blocked_outcome.status,
                    },
                },
                sort_keys=True,
            )
            + "\n"
        )
        return

    # Align the deterministic R1 harness with the frontend's published ETF seed.
    outcome, decision = _seed_identity(
        database,
        strategy_id="seed_etf_industry_rotation",
        account_id="r1-paper",
        current_weight=0.0,
        target_weight=0.4,
    )
    if outcome.status != "completed":
        raise RuntimeError(f"unexpected EOD status: {outcome.status}")

    sleeve_id = str(decision.identity["sleeve_id"])
    risk = SQLiteRiskPersistence(lambda: sqlite3.connect(database))
    risk.append_daily_report(
        DailyRiskProjectionRecord(
            report_id="r4-live-ready",
            strategy_id="seed_etf_industry_rotation",
            account_id="r1-paper",
            sleeve_id=sleeve_id,
            trade_date=r1.SIGNAL_DATE,
            projection=_projection(),
            created_at="2026-07-10T15:01:00+08:00",
        )
    )
    sys.stdout.write(
        json.dumps(
            {
                "database": str(database),
                "strategy_id": "seed_etf_industry_rotation",
                "account_id": "r1-paper",
                "trade_date": r1.SIGNAL_DATE,
                "intended_trade_date": r1.INTENDED_TRADE_DATE,
                "sleeve_id": sleeve_id,
                "artifact_id": outcome.artifact_id,
            },
            sort_keys=True,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
