import { describe, expect, it } from "vitest";
import type { components } from "@/types/generated/api";
import {
	mapDailyDecisionToSignalDetail,
	mapDailyDecisionToSignalsQueue,
	mapDailyDecisionToSignalsResponse,
	mapDailyDecisionV2ToLegacy,
	mapDailyDecisionV3,
	mapPositionsResponse,
	mapReadinessStatus,
} from "../mappers";

type DailyDecisionReportResponse = components["schemas"]["DailyDecisionReportResponse"];
type DailyDecisionV2Response = components["schemas"]["DailyDecisionV2Response"];
type DailyDecisionV3Response = components["schemas"]["DailyDecisionV3Response"];

const report: DailyDecisionReportResponse = {
	strategy_id: "seed_etf_industry_rotation",
	trade_date: "2026-07-02",
	readiness: {
		status: "review",
		reasons: ["manual review required"],
	},
	signal_intents: [
		{
			intent_id: "intent-510300",
			strategy_id: "seed_etf_industry_rotation",
			signal_date: "2026-07-02",
			instrument_id: 510300,
			direction: "buy",
			target_weight: 0.3,
			current_weight: 0.12,
			delta_weight: 0.18,
			quantity: 1000,
			status: "pending",
		},
		{
			intent_id: "intent-159915",
			strategy_id: "seed_etf_industry_rotation",
			signal_date: "2026-07-02",
			instrument_id: 159915,
			direction: "sell",
			target_weight: 0.05,
			current_weight: 0.11,
			delta_weight: -0.06,
			quantity: 600,
			status: "filled",
		},
	],
	positions: [
		{
			snapshot_id: "pos-510300",
			strategy_id: "seed_etf_industry_rotation",
			snapshot_date: "2026-07-02",
			instrument_id: 510300,
			quantity: 1000,
			available_quantity: 800,
			average_cost: 4.12,
			market_value: 4300,
			unrealized_pnl: 180,
			realized_pnl: 20,
			total_fees: 3,
		},
	],
	deviation: {
		strategy_id: "seed_etf_industry_rotation",
		signal_date: "2026-07-02",
		total_signals: 2,
		filled: 1,
		unfilled: 1,
		items: [
			{
				instrument_id: 510300,
				signal_action: "buy",
				signal_weight: 0.3,
				actual_weight: 0.12,
				deviation_bps: 125,
				fill_status: "unfilled",
			},
		],
	},
	pnl: {
		total_realized_pnl: 20,
		total_unrealized_pnl: 180,
		total_fees: 3,
		net_pnl: 197,
	},
};

const v3Report: DailyDecisionV3Response = {
	v2: {
		identity: {
			strategy_id: "strategy-r4",
			strategy_version: "7",
			signal_date: "2026-08-18",
			intended_trade_date: "2026-08-19",
			account_id: "paper-r4",
		},
		readiness: { status: "ready", reason_codes: [], details: [] },
		data: {
			required_datasets: [],
			snapshot_ids: { bars: "snapshot-bars-r4" },
			dataset_states: [],
			freshness: "ready",
			dq_state: "passed",
		},
		run_package: {
			outcome: "completed",
			checksum_valid: true,
			no_rebalance: false,
			factor_evidence: {},
			risk_evidence: [],
		},
		account_positions: {
			as_of: "2026-08-18T07:00:00Z",
			baseline_id: "baseline-r4",
			cash_available: 250_000,
			total_value: 1_000_000,
			exposure: 750_000,
			positions: [],
		},
		actions: [
			{
				intent_id: "intent-r4",
				instrument_id: 510300,
				direction: "buy",
				target_weight: 0.35,
				current_weight: 0.25,
				delta_weight: 0.1,
				suggested_quantity: 1000,
				filled_quantity: 0,
				remaining_quantity: 1000,
				risk_flags: [],
				intent_status: "pending",
				sizing_readiness: "ready",
			},
		],
		execution_review: { effective_fills: [], exceptions: [], unresolved_conflicts: [] },
	},
	readiness: "ready",
	blocking_reasons: [],
	portfolio_construction: {
		status: "completed",
		solver: "clarabel",
		solver_version: "0.10",
		mode: "risk_budget",
		solver_status: "optimal",
		duration_ms: 18.5,
		policy_digest: "sha256:policy-r4",
		failure_code: null,
	},
	tail_risk: {
		historical_es99: 0.041,
		historical_var99: 0.031,
		parametric_var99: 0.029,
		monte_carlo_var99: 0.033,
		monte_carlo_seed: 42,
	},
	factor_risk: {
		availability: "available",
		total_risk: 0.12,
		marginal_contributions: { market: 0.08 },
		percentage_contributions: { market: 0.67 },
		euler_residual: 0.0001,
	},
	stress_tests: {
		catalog_version: "stress-v3",
		losses: { liquidity_crunch: 0.08 },
		unavailable_scenarios: [],
	},
	reconciliation: { status: "matched", differences: [], alert_idempotency_key: null },
	provenance: {
		decision_time: "2026-08-18T07:00:00Z",
		knowledge_cutoff: "2026-08-18T06:55:00Z",
		publication_cutoff: "2026-08-18T06:50:00Z",
		source_snapshot_ids: ["snapshot-bars-r4"],
		generated_at: "2026-08-18T07:01:00Z",
	},
};

describe("trading api mappers", () => {
	it("maps the V3 decision surface into a component-safe view model", () => {
		const mapped = mapDailyDecisionV3(v3Report);

		expect(mapped.identity).toEqual({
			strategyId: "strategy-r4",
			strategyVersion: "7",
			signalDate: "2026-08-18",
			tradeDate: "2026-08-19",
			accountId: "paper-r4",
			sleeveId: null,
		});
		expect(mapped.readiness).toMatchObject({ status: "ready", reportedStatus: "ready", blockingReasons: [] });
		expect(mapped.portfolioConstruction).toMatchObject({ solver: "clarabel", status: "completed" });
		expect(mapped.provenance).toMatchObject({ complete: true, sourceSnapshotIds: ["snapshot-bars-r4"] });
		expect(mapped.completeness).toEqual({ status: "complete", issues: [] });
	});

	it("fails closed when required PIT provenance is missing", () => {
		const mapped = mapDailyDecisionV3({
			...v3Report,
			provenance: { ...v3Report.provenance, publication_cutoff: null, source_snapshot_ids: [] },
		});

		expect(mapped.readiness.status).toBe("blocked");
		expect(mapped.readiness.blockingReasons).toContain("PIT_PROVENANCE_INCOMPLETE");
		expect(mapped.provenance).toMatchObject({ complete: false });
		expect(mapped.completeness.status).toBe("blocked");
	});

	it.each(["review", "blocked"] as const)("preserves the backend %s readiness decision", (status) => {
		const mapped = mapDailyDecisionV3({
			...v3Report,
			readiness: status,
			blocking_reasons: status === "blocked" ? ["RISK_LIMIT_BREACH"] : ["MANUAL_REVIEW_REQUIRED"],
		});

		expect(mapped.readiness.reportedStatus).toBe(status);
		expect(mapped.readiness.status).toBe(status);
	});

	it("maps readiness ready/review/blocked/failed states to cockpit copy", () => {
		expect(mapReadinessStatus("ready").label).toBe("可执行");
		expect(mapReadinessStatus("review").label).toBe("需复核");
		expect(mapReadinessStatus("blocked").label).toBe("阻塞");
		expect(mapReadinessStatus("failed").label).toBe("加载失败");
	});

	it("maps signal intents to the existing Signals view model and queue counts", () => {
		const signals = mapDailyDecisionToSignalsResponse(report, { tab: "pending" });
		const queue = mapDailyDecisionToSignalsQueue(report);

		expect(signals.total).toBe(1);
		expect(signals.items[0]).toMatchObject({
			id: "intent-510300",
			instrument: "#510300",
			direction: "BUY",
			status: "pending",
			weight: 0.3,
			confidence: null,
		});
		expect(queue).toEqual({
			pending: 1,
			confirmed: 0,
			ignored: 0,
			ordered: 1,
		});
	});

	it("keeps a partially filled intent in the actionable queue for subsequent fills", () => {
		const partiallyFilled = {
			...report,
			signal_intents: [
				{
					...report.signal_intents[0],
					status: "partially_filled",
				},
			],
		} satisfies DailyDecisionReportResponse;

		const signals = mapDailyDecisionToSignalsResponse(partiallyFilled, { tab: "pending" });

		expect(signals.items).toEqual([expect.objectContaining({ id: "intent-510300", status: "pending" })]);
		expect(mapDailyDecisionToSignalsQueue(partiallyFilled)).toEqual({
			pending: 1,
			confirmed: 0,
			ignored: 0,
			ordered: 0,
		});
		expect(mapDailyDecisionToSignalDetail(partiallyFilled, "intent-510300").actions).toEqual(
			expect.arrayContaining([{ type: "record_fill", label: "录入手工成交", enabled: true }]),
		);
	});

	it("adapts persisted V2 actions and account positions without inventing live data", () => {
		const v2: DailyDecisionV2Response = {
			identity: {
				strategy_id: "seed_etf_industry_rotation",
				signal_date: "2026-07-02",
				intended_trade_date: "2026-07-03",
			},
			readiness: {
				status: "review",
				reason_codes: ["RISK_WARNING"],
				details: ["risk review"],
			},
			data: {
				required_datasets: [],
				snapshot_ids: {},
				dataset_states: [],
				freshness: "ready",
				dq_state: "passed",
			},
			run_package: {
				outcome: "completed",
				checksum_valid: true,
				no_rebalance: false,
				factor_evidence: {},
				risk_evidence: [],
			},
			account_positions: { positions: report.positions },
			actions: [
				{
					intent_id: "intent-510300",
					instrument_id: 510300,
					direction: "buy",
					target_weight: 0.3,
					current_weight: 0.12,
					delta_weight: 0.18,
					suggested_quantity: 1000,
					filled_quantity: 400,
					remaining_quantity: 600,
					risk_flags: ["RISK_WARNING"],
					intent_status: "pending",
				},
			],
			execution_review: {
				deviation: report.deviation,
				pnl: report.pnl,
				effective_fills: [],
				exceptions: [],
				unresolved_conflicts: [],
			},
		};
		Reflect.deleteProperty(v2.actions[0], "intent_status");

		const adapted = mapDailyDecisionV2ToLegacy(v2);

		expect(adapted.readiness).toEqual({ status: "review", reasons: ["RISK_WARNING"] });
		expect(adapted.signal_intents[0]).toMatchObject({
			intent_id: "intent-510300",
			signal_date: "2026-07-03",
			quantity: 1000,
			status: "pending",
		});
		expect(adapted.positions).toEqual(report.positions);
		expect(mapDailyDecisionToSignalDetail(adapted, "intent-510300").execution).toMatchObject({
			quantity: 1000,
			filledQuantity: 400,
			remainingQuantity: 600,
			reviewReasons: ["RISK_WARNING"],
		});
	});

	it("fails closed instead of coercing an unknown V2 direction to BUY", () => {
		const v2 = {
			identity: {
				strategy_id: "seed_etf_industry_rotation",
				signal_date: "2026-07-02",
				intended_trade_date: "2026-07-03",
			},
			readiness: {
				status: "ready",
				reason_codes: ["READY_FOR_REVIEW"],
				details: ["ready"],
			},
			data: {
				required_datasets: [],
				snapshot_ids: {},
				dataset_states: [],
				freshness: "ready",
				dq_state: "passed",
			},
			run_package: {
				outcome: "completed",
				checksum_valid: true,
				no_rebalance: false,
				factor_evidence: {},
				risk_evidence: [],
			},
			account_positions: { positions: [] },
			actions: [
				{
					intent_id: "intent-invalid-direction",
					instrument_id: 510300,
					direction: "sideways",
					target_weight: 0.3,
					current_weight: 0.12,
					delta_weight: 0.18,
					suggested_quantity: 1000,
					filled_quantity: 0,
					risk_flags: [],
					intent_status: "pending",
				},
			],
			execution_review: {
				effective_fills: [],
				exceptions: [],
				unresolved_conflicts: [],
			},
		} satisfies DailyDecisionV2Response;

		expect(mapDailyDecisionV2ToLegacy(v2).signal_intents).toEqual([]);
	});

	it("omits an invalid legacy direction instead of rendering it as BUY", () => {
		const invalid = {
			...report,
			signal_intents: [
				{
					...report.signal_intents[0],
					direction: "sideways",
				},
			],
		} as DailyDecisionReportResponse;

		expect(mapDailyDecisionToSignalsResponse(invalid, { tab: "pending" }).items).toEqual([]);
		expect(mapDailyDecisionToSignalDetail(invalid, "intent-510300").execution).toBeUndefined();
	});

	it("maps positions with available quantity into T+1 frozen quantity", () => {
		expect(mapPositionsResponse(report).positions[0]).toMatchObject({
			code: "#510300",
			name: "#510300",
			qty: 1000,
			availableQty: 800,
			frozenQty: 200,
			avgCost: 4.12,
			currentPrice: 4.3,
			pnl: 200,
		});
	});

	it("adds deviation bps as the fifth risk check in signal detail", () => {
		const detail = mapDailyDecisionToSignalDetail(report, "intent-510300");

		expect(detail.riskChecks).toHaveLength(4);
		expect(detail.riskChecks[0]).toMatchObject({ status: "warn" });
		expect(detail.portfolioImpact).toBeUndefined();
		expect(detail.riskChecks[3]).toEqual({
			name: "成交偏差证据",
			status: "warn",
			message: "后端偏差证据 125 bps；未提供风险阈值结论",
		});
		expect(detail.actions).toEqual(
			expect.arrayContaining([{ type: "record_fill", label: "录入手工成交", enabled: true }]),
		);
		expect(detail.actions.some((action) => action.type === "update_status")).toBe(false);
		expect(detail.actions.some((action) => action.type === "ai_interpret")).toBe(false);
		expect(detail.execution).toMatchObject({
			intentId: "intent-510300",
			strategyId: "seed_etf_industry_rotation",
			tradeDate: "2026-07-02",
			instrumentId: 510300,
			direction: "buy",
			quantity: 1000,
			status: "pending",
		});
	});

	it("disables execution mutations when readiness is blocked", () => {
		const blocked = {
			...report,
			readiness: { status: "blocked" as const, reasons: ["ACCOUNT_BASELINE_MISSING"] },
		};

		const detail = mapDailyDecisionToSignalDetail(blocked, "intent-510300");

		expect(detail.actions.filter((action) => action.type !== "ai_interpret")).toEqual(
			expect.arrayContaining([expect.objectContaining({ type: "record_fill", enabled: false })]),
		);
	});

	it("does not turn overall readiness into a fabricated portfolio-impact risk check", () => {
		const ready = {
			...report,
			readiness: { status: "ready" as const, reasons: ["READY_FOR_REVIEW"] },
		};

		const detail = mapDailyDecisionToSignalDetail(ready, "intent-510300");

		expect(detail.riskChecks.some((check) => check.name === "组合影响")).toBe(false);
	});
});
