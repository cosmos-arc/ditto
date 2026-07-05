import { describe, expect, it } from "vitest";
import type { components } from "@/types/generated/api";
import {
	mapDailyDecisionToSignalDetail,
	mapDailyDecisionToSignalsQueue,
	mapDailyDecisionToSignalsResponse,
	mapPositionsResponse,
	mapReadinessStatus,
} from "../mappers";

type DailyDecisionReportResponse = components["schemas"]["DailyDecisionReportResponse"];

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

describe("trading api mappers", () => {
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
		});
		expect(queue).toEqual({
			pending: 1,
			confirmed: 0,
			ignored: 0,
			ordered: 1,
		});
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

		expect(detail.riskChecks).toHaveLength(5);
		expect(detail.riskChecks[4]).toEqual({
			name: "价格合理性",
			status: "warn",
			message: "信号与成交偏差 125 bps，需复核执行价格",
		});
		expect(detail.actions).toEqual(
			expect.arrayContaining([
				{ type: "record_fill", label: "录入手工成交", enabled: true },
				{ type: "update_status", label: "更新意图状态", enabled: true },
			]),
		);
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
});
