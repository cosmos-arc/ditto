import { HttpResponse, http, type RequestHandler } from "msw";
import type {
	DailyDecisionReportResponse,
	DailyDecisionV2Response,
	DailyDecisionV3Response,
	TradeIntentResponse,
} from "@/features/portfolio/api/daily-decision";
import type {
	FillAdjustmentResponse,
	FillResponse,
	RecordFillRequest,
	ReplaceFillRequest,
	VoidFillRequest,
} from "@/features/portfolio/api/fills";
import type { ManualAccountLedger } from "@/features/portfolio/api/manual-accounts";
import {
	mockEquity,
	mockOrdersSummary,
	mockPositions,
	mockRiskSummary,
	mockSignalDetail,
	mockSignals,
	mockSignalsQueue,
	mockTradingSession,
} from "../fixtures/portfolio";

const manualAccountLedger: ManualAccountLedger = {
	account: {
		account_id: "manual-a",
		currency: "CNY",
		kind: "manual",
		name: "我的实盘记录",
		opened_at: "2026-08-01T00:00:00+08:00",
	},
	events: [
		{
			account_id: "manual-a",
			account_kind: "manual",
			actor: "local-user",
			attachment_refs: ["broker-statement-202608"],
			corrects_event_id: null,
			currency: "CNY",
			event_hash: "account-event:sha256:7a4db91c8f2e",
			event_id: "manual-a-opening-cash",
			event_type: "opening_cash",
			external_reference: "broker-20260801",
			fees: "0.00",
			gross_amount: "100000.00",
			idempotency_key: "manual-a:opening-cash:v1",
			instrument_id: null,
			net_cash: "100000.00",
			note: "券商月结单期初余额",
			price: "0.0000",
			quantity: "0",
			recorded_at: "2026-08-01T08:00:00+08:00",
			replacement_event_type: null,
			reverses_event_id: null,
			settlement_date: "2026-08-01",
			source: "manual_entry",
			tax: "0.00",
			trade_date: "2026-08-01",
		},
	],
	snapshot: {
		account_id: "manual-a",
		account_kind: "manual",
		as_of: "2026-08-31",
		cash: { available: "80885.00", frozen: "0.00", settled: "80885.00", total: "80885.00" },
		currency: "CNY",
		event_count: 1,
		ledger_hash: "account-ledger:sha256:189c7d3e5f284f55",
		positions: [
			{
				available_quantity: "100",
				average_cost: "191.1500",
				instrument_id: 42,
				last_price: "191.1500",
				market_value: "19115.00",
				quantity: "100",
				realized_pnl: "0.00",
				total_fees: "5.00",
				unrealized_pnl: "0.00",
			},
		],
		realized_pnl: "0.00",
		total_fees: "5.00",
		total_value: "100000.00",
		unrealized_pnl: "0.00",
		valuation_complete: true,
	},
};

const liveTradeIntents: TradeIntentResponse[] = [
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
		target_weight: 0.1,
		current_weight: 0.18,
		delta_weight: -0.08,
		quantity: 500,
		status: "filled",
	},
];

const liveFills: FillResponse[] = [
	{
		fill_id: "fill-159915-001",
		intent_id: "intent-159915",
		strategy_id: "seed_etf_industry_rotation",
		trade_date: "2026-07-02",
		instrument_id: 159915,
		direction: "sell",
		quantity: 500,
		fill_price: 2.68,
		fee: 1.2,
		slippage: 0.02,
		notes: "manual paper fill",
		settlement_date: "2026-07-03",
	},
];

const liveFillAdjustments: FillAdjustmentResponse[] = [];

const liveDailyDecision: DailyDecisionReportResponse = {
	strategy_id: "seed_etf_industry_rotation",
	trade_date: "2026-07-02",
	readiness: {
		status: "review",
		reasons: ["manual review required"],
	},
	signal_intents: liveTradeIntents,
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
			{
				instrument_id: 159915,
				signal_action: "sell",
				signal_weight: 0.1,
				actual_weight: 0.1,
				deviation_bps: 8,
				fill_status: "filled",
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

export const liveDailyDecisionV2: DailyDecisionV2Response = {
	identity: {
		strategy_id: liveDailyDecision.strategy_id,
		strategy_version: "1",
		account_id: "paper-a",
		sleeve_id: "manual-paper-a-seed_etf_industry_rotation",
		signal_date: liveDailyDecision.trade_date ?? null,
		decision_date: "2026-07-02",
		intended_trade_date: "2026-07-03",
	},
	readiness: {
		status: "review",
		reason_codes: ["RISK_WARNING"],
		details: ["风险证据需要人工复核"],
	},
	data: {
		required_datasets: ["etf_daily"],
		snapshot_ids: { etf_daily: "sha256:etf-daily-20260702" },
		dataset_states: [
			{
				dataset: "etf_daily",
				status: "ready",
				snapshot_id: "sha256:etf-daily-20260702",
				reason: "",
			},
		],
		freshness: "ready",
		dq_state: "passed",
	},
	run_package: {
		outcome: "completed",
		batch_key: "eod-2026-07-02-seed_etf_industry_rotation-1",
		artifact_id: "signal-package-seed_etf_industry_rotation-2026-07-02-v1",
		checksum: "sha256:mock-signal-package",
		checksum_valid: true,
		no_rebalance: false,
		factor_evidence: { "510300": { momentum_20d: 0.82 } },
		risk_evidence: ["RISK_WARNING"],
	},
	account_positions: {
		baseline_id: "baseline-paper-a-20260702",
		account_id: "paper-a",
		sleeve_id: "manual-paper-a-seed_etf_industry_rotation",
		cash_available: 60_000,
		cash_settled: 60_000,
		cash_frozen: 0,
		total_value: 100_000,
		nav: 1,
		exposure: 40_000,
		as_of: "2026-07-02",
		positions: liveDailyDecision.positions,
	},
	actions: liveTradeIntents.map((intent) => ({
		intent_id: intent.intent_id,
		instrument_id: intent.instrument_id,
		direction: intent.direction,
		target_weight: intent.target_weight,
		current_weight: intent.current_weight,
		delta_weight: intent.delta_weight,
		raw_quantity: intent.quantity ?? null,
		rounded_quantity: intent.quantity ?? null,
		suggested_quantity: intent.quantity ?? null,
		reference_price: intent.instrument_id === 510300 ? 4.31 : 2.68,
		lot_size: 100,
		cash_impact:
			(intent.direction === "buy" ? -1 : 1) * (intent.quantity ?? 0) * (intent.instrument_id === 510300 ? 4.31 : 2.68),
		reason: "exact_board_lot",
		sizing_readiness: "ready",
		risk_flags: intent.intent_id === "intent-510300" ? ["RISK_WARNING"] : [],
		filled_quantity: intent.intent_id === "intent-510300" ? 400 : (intent.quantity ?? 0),
		remaining_quantity: intent.intent_id === "intent-510300" ? 600 : 0,
		intent_status: intent.status,
	})),
	execution_review: {
		deviation: liveDailyDecision.deviation ?? null,
		pnl: liveDailyDecision.pnl ?? null,
		effective_fills: liveFills,
		exceptions: [],
		unresolved_conflicts: [],
	},
};

export const liveDailyDecisionV3: DailyDecisionV3Response = {
	v2: liveDailyDecisionV2,
	readiness: "review",
	blocking_reasons: [],
	portfolio_construction: {
		status: "completed",
		solver: "clarabel",
		solver_version: "0.10",
		mode: "risk_budget",
		solver_status: "optimal",
		duration_ms: 18.5,
		policy_digest: "sha256:mock-policy-r4",
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
		marginal_contributions: { market: 0.08, size: 0.04 },
		percentage_contributions: { market: 0.67, size: 0.33 },
		euler_residual: 0.0001,
	},
	stress_tests: {
		catalog_version: "stress-v3",
		losses: { liquidity_crunch: 0.08, rate_shock: 0.03 },
		unavailable_scenarios: [],
	},
	reconciliation: {
		status: "matched",
		differences: [],
		alert_idempotency_key: null,
	},
	provenance: {
		decision_time: "2026-07-02T07:00:00Z",
		knowledge_cutoff: "2026-07-02T06:55:00Z",
		publication_cutoff: "2026-07-02T06:50:00Z",
		source_snapshot_ids: ["sha256:etf-daily-20260702"],
		generated_at: "2026-07-02T07:01:00Z",
	},
};

function isRecordFillRequest(value: unknown): value is RecordFillRequest {
	if (typeof value !== "object" || value === null) return false;
	const candidate = value as Partial<RecordFillRequest>;
	return (
		typeof candidate.fill_id === "string" &&
		typeof candidate.intent_id === "string" &&
		typeof candidate.strategy_id === "string" &&
		typeof candidate.trade_date === "string" &&
		typeof candidate.instrument_id === "number" &&
		(candidate.direction === "buy" || candidate.direction === "sell") &&
		typeof candidate.quantity === "number" &&
		typeof candidate.fill_price === "number"
	);
}

function isVoidFillRequest(value: unknown): value is VoidFillRequest {
	if (typeof value !== "object" || value === null) return false;
	const candidate = value as Partial<VoidFillRequest>;
	return typeof candidate.adjustment_id === "string" && typeof candidate.reason === "string";
}

function isReplaceFillRequest(value: unknown): value is ReplaceFillRequest {
	if (typeof value !== "object" || value === null) return false;
	const candidate = value as Partial<ReplaceFillRequest>;
	return (
		typeof candidate.adjustment_id === "string" &&
		typeof candidate.replacement_fill_id === "string" &&
		typeof candidate.trade_date === "string" &&
		typeof candidate.quantity === "number" &&
		typeof candidate.fill_price === "number" &&
		typeof candidate.reason === "string" &&
		typeof candidate.fee === "number" &&
		typeof candidate.slippage === "number" &&
		typeof candidate.notes === "string"
	);
}

function findEffectiveFill(fillId: string): FillResponse | undefined {
	const isAdjusted = liveFillAdjustments.some((adjustment) => adjustment.fill_id === fillId);
	return isAdjusted ? undefined : liveFills.find((fill) => fill.fill_id === fillId);
}

function correctionConflict(fillId: string) {
	return HttpResponse.json(
		{
			status_code: 409,
			error: "Conflict",
			detail: `fill ${fillId} was already adjusted`,
			error_code: "fill_adjustment_conflict",
		},
		{ status: 409 },
	);
}

export const portfolioHandlers: RequestHandler[] = [
	http.get("/api/v1/manual/accounts/:accountId/ledger", () => {
		return HttpResponse.json({ data: manualAccountLedger });
	}),

	http.post("/api/v1/manual/accounts", () => {
		return HttpResponse.json(
			{ data: { account: manualAccountLedger.account, event: null, status: "created" } },
			{ status: 201 },
		);
	}),

	http.post("/api/v1/manual/accounts/:accountId/events", () => {
		return HttpResponse.json(
			{ data: { account: manualAccountLedger.account, event: manualAccountLedger.events[0], status: "created" } },
			{ status: 201 },
		);
	}),

	http.post("/api/v1/manual/accounts/:accountId/corrections", () => {
		return HttpResponse.json(
			{ data: { account: manualAccountLedger.account, event: manualAccountLedger.events[0], status: "created" } },
			{ status: 201 },
		);
	}),

	http.post("/api/v1/manual/accounts/:accountId/reversals", () => {
		return HttpResponse.json(
			{ data: { account: manualAccountLedger.account, event: manualAccountLedger.events[0], status: "created" } },
			{ status: 201 },
		);
	}),

	http.get("/api/v1/manual/daily-decision/v3", () => {
		return HttpResponse.json({ data: liveDailyDecisionV3 });
	}),

	http.get("/api/v1/manual/daily-decision/v2", () => {
		return HttpResponse.json({ data: liveDailyDecisionV2 });
	}),

	http.get("/api/v1/manual/daily-decision", () => {
		return HttpResponse.json({ data: liveDailyDecision });
	}),

	http.get("/api/v1/manual/intents", ({ request }) => {
		const url = new URL(request.url);
		const status = url.searchParams.get("status");
		const filtered = status ? liveTradeIntents.filter((intent) => intent.status === status) : liveTradeIntents;

		return HttpResponse.json({
			data: filtered,
			pagination: { total: filtered.length, limit: filtered.length, offset: 0, has_more: false },
		});
	}),

	http.put("/api/v1/manual/intents/:intentId/status", () => {
		return HttpResponse.json({ data: true });
	}),

	http.get("/api/v1/manual/fills", () => {
		return HttpResponse.json({
			data: liveFills,
			pagination: { total: liveFills.length, limit: liveFills.length, offset: 0, has_more: false },
		});
	}),

	http.get("/api/v1/manual/fills/effective", () => {
		const data = liveFills.filter((fill) => findEffectiveFill(fill.fill_id));
		return HttpResponse.json({
			data,
			pagination: { total: data.length, limit: data.length, offset: 0, has_more: false },
		});
	}),

	http.get("/api/v1/manual/fill-adjustments", ({ request }) => {
		const url = new URL(request.url);
		const fillId = url.searchParams.get("fill_id");
		const intentId = url.searchParams.get("intent_id");
		const data = liveFillAdjustments.filter((adjustment) => {
			const fill = liveFills.find((candidate) => candidate.fill_id === adjustment.fill_id);
			return (!fillId || adjustment.fill_id === fillId) && (!intentId || fill?.intent_id === intentId);
		});
		return HttpResponse.json({
			data,
			pagination: { total: data.length, limit: data.length, offset: 0, has_more: false },
		});
	}),

	http.get("/api/v1/manual/comparison", () => {
		return HttpResponse.json({
			data: {
				backtest_return: 0.08,
				actual_return: 0.071,
				return_diff: -0.009,
				return_diff_bps: -90,
				backtest_sharpe: 1.3,
				actual_sharpe: 1.1,
				backtest_total_cost: 12,
				actual_total_cost: 18,
				cost_drag_bps: 6,
				nav_correlation: 0.98,
				max_nav_diff_bps: 42,
				avg_daily_tracking_error_bps: 12.5,
			},
		});
	}),

	http.post("/api/v1/manual/fills", async ({ request }) => {
		const payload = await request.json();

		if (!isRecordFillRequest(payload)) {
			return HttpResponse.json(
				{
					status_code: 400,
					error: "Bad Request",
					detail: "Invalid fill payload",
					error_code: "invalid_record_fill",
				},
				{ status: 400 },
			);
		}

		return HttpResponse.json({
			data: {
				fill_id: payload.fill_id,
				intent_id: payload.intent_id,
				strategy_id: payload.strategy_id,
				trade_date: payload.trade_date,
				instrument_id: payload.instrument_id,
				direction: payload.direction,
				quantity: payload.quantity,
				fill_price: payload.fill_price,
				fee: payload.fee ?? 0,
				slippage: payload.slippage ?? 0,
				notes: payload.notes ?? "",
				settlement_date: payload.trade_date,
			} satisfies FillResponse,
		});
	}),

	http.post("/api/v1/manual/fills/:fillId/void", async ({ params, request }) => {
		const fillId = String(params["fillId"]);
		const payload = await request.json();
		if (!isVoidFillRequest(payload)) return HttpResponse.json({ detail: "Invalid void payload" }, { status: 400 });
		const replay = liveFillAdjustments.find((item) => item.adjustment_id === payload.adjustment_id);
		if (replay) return HttpResponse.json({ data: replay });
		if (!findEffectiveFill(fillId)) return correctionConflict(fillId);
		const adjustment = {
			adjustment_id: payload.adjustment_id,
			fill_id: fillId,
			adjustment_type: "void",
			replacement_fill_id: null,
			reason: payload.reason,
			created_at: new Date().toISOString(),
		} satisfies FillAdjustmentResponse;
		liveFillAdjustments.push(adjustment);
		return HttpResponse.json({ data: adjustment });
	}),

	http.post("/api/v1/manual/fills/:fillId/replace", async ({ params, request }) => {
		const fillId = String(params["fillId"]);
		const payload = await request.json();
		if (!isReplaceFillRequest(payload))
			return HttpResponse.json({ detail: "Invalid replace payload" }, { status: 400 });
		const replay = liveFillAdjustments.find((item) => item.adjustment_id === payload.adjustment_id);
		if (replay) return HttpResponse.json({ data: replay });
		const original = findEffectiveFill(fillId);
		if (!original) return correctionConflict(fillId);
		const replacement = {
			...original,
			fill_id: payload.replacement_fill_id,
			trade_date: payload.trade_date,
			quantity: payload.quantity,
			fill_price: payload.fill_price,
			fee: payload.fee,
			slippage: payload.slippage,
			notes: payload.notes,
			settlement_date: payload.trade_date,
		} satisfies FillResponse;
		const adjustment = {
			adjustment_id: payload.adjustment_id,
			fill_id: fillId,
			adjustment_type: "replace",
			replacement_fill_id: replacement.fill_id,
			reason: payload.reason,
			created_at: new Date().toISOString(),
		} satisfies FillAdjustmentResponse;
		liveFills.push(replacement);
		liveFillAdjustments.push(adjustment);
		return HttpResponse.json({ data: adjustment });
	}),

	http.get("/api/trading/session", () => {
		return HttpResponse.json(mockTradingSession);
	}),

	http.get("/api/trading/equity", () => {
		return HttpResponse.json({ series: mockEquity });
	}),

	http.get("/api/trading/positions", () => {
		return HttpResponse.json({ positions: mockPositions });
	}),

	http.get("/api/trading/risk/summary", () => {
		return HttpResponse.json(mockRiskSummary);
	}),

	http.get("/api/portfolio/review/queue", () => {
		return HttpResponse.json(mockSignalsQueue);
	}),

	http.get("/api/trading/orders/summary", () => {
		return HttpResponse.json(mockOrdersSummary);
	}),

	http.get("/api/portfolio/review", ({ request }) => {
		const url = new URL(request.url);
		const tab = url.searchParams.get("tab") ?? "pending";
		const page = Number(url.searchParams.get("page") ?? 1);
		const limit = Number(url.searchParams.get("limit") ?? 20);

		const filtered = mockSignals.items.filter((s) => s.status === tab);
		const start = (page - 1) * limit;
		const paged = filtered.slice(start, start + limit);

		return HttpResponse.json({
			items: paged,
			total: filtered.length,
			page,
			pageSize: limit,
		});
	}),

	http.get("/api/portfolio/review/:id", () => {
		return HttpResponse.json(mockSignalDetail);
	}),
];
