import { http, HttpResponse, type RequestHandler } from "msw";
import type { components } from "@/types/generated/api";
import {
	mockEquity,
	mockOrdersSummary,
	mockPositions,
	mockRiskSummary,
	mockSignalDetail,
	mockSignals,
	mockSignalsQueue,
	mockTradingSession,
} from "../fixtures/trading";

type DailyDecisionReportResponse = components["schemas"]["DailyDecisionReportResponse"];
type TradeIntentResponse = components["schemas"]["TradeIntentResponse"];
type FillResponse = components["schemas"]["FillResponse"];
type RecordFillRequest = components["schemas"]["RecordFillRequest"];

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

export const tradingHandlers: RequestHandler[] = [
	http.get("/api/v1/trade/daily-decision", () => {
		return HttpResponse.json({ data: liveDailyDecision });
	}),

	http.get("/api/v1/trade/intents", ({ request }) => {
		const url = new URL(request.url);
		const status = url.searchParams.get("status");
		const filtered = status
			? liveTradeIntents.filter((intent) => intent.status === status)
			: liveTradeIntents;

		return HttpResponse.json({
			data: filtered,
			pagination: { total: filtered.length, limit: filtered.length, offset: 0, has_more: false },
		});
	}),

	http.put("/api/v1/trade/intents/:intentId/status", () => {
		return HttpResponse.json({ data: true });
	}),

	http.get("/api/v1/trade/fills", () => {
		return HttpResponse.json({
			data: liveFills,
			pagination: { total: liveFills.length, limit: liveFills.length, offset: 0, has_more: false },
		});
	}),

	http.get("/api/v1/trade/comparison", () => {
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

	http.post("/api/v1/trade/fills", async ({ request }) => {
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

	http.get("/api/trading/signals/queue", () => {
		return HttpResponse.json(mockSignalsQueue);
	}),

	http.get("/api/trading/orders/summary", () => {
		return HttpResponse.json(mockOrdersSummary);
	}),

	http.get("/api/trading/signals", ({ request }) => {
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

	http.get("/api/trading/signals/:id", () => {
		return HttpResponse.json(mockSignalDetail);
	}),
];
