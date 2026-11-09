import { afterEach, describe, expect, it, vi } from "vitest";
import { mockBacktestReport, mockBacktestRuns } from "@/mocks/fixtures/backtest";
import { capturedRequest, requestPath } from "@/test/request";
import type { BacktestReportResponse, RunResponse } from "./backtests";
import {
	fetchBacktestAudit,
	fetchBacktestBenchmark,
	fetchBacktestReport,
	mapBacktestReport,
	mapBacktestRun,
} from "./backtests";

afterEach(() => vi.unstubAllGlobals());

describe("backtest API view-model boundaries", () => {
	it("keeps report scope and original provenance through mapping, with conservative legacy defaults", () => {
		const provenance = { strategy_version: "7", data_catalog_identities: ["snapshot:retained"] };
		const report = mapBacktestReport({
			...mockBacktestReport,
			strategy_promotion: provenance,
			pit_policy: { policy: "knowledge_date_fail_closed" },
			usage_context: {
				intended_use: "limited_historical_research",
				historical_availability: "not_certified",
				sample_pool: "recorded_input_union",
				input_instrument_ids: [510300],
				limitations: ["仅固定样本池"],
			},
		});
		expect(report.usageContext).toMatchObject({ inputInstrumentIds: [510300], limitations: ["仅固定样本池"] });
		expect(report.strategyPromotion).toEqual(provenance);
		expect(report.pitPolicy).toEqual({ policy: "knowledge_date_fail_closed" });
		const legacy = mapBacktestReport(mockBacktestReport);
		expect(legacy.usageContext).toMatchObject({
			intendedUse: "unclassified",
			historicalAvailability: "not_certified",
			samplePool: "unknown",
		});
		expect(legacy.usageContext.limitations.length).toBeGreaterThan(0);
	});

	it("maps an incomplete report to explicit empty periods and unavailable statistics", () => {
		const report = mapBacktestReport({
			...mockBacktestReport,
			period: null,
			alpha_stats: null,
			aggregated_trade_stats: null,
		} as unknown as BacktestReportResponse);
		expect(report).toMatchObject({ periodStart: "", periodEnd: "", alphaStats: null, tradeStats: null });

		const firstRun = mockBacktestRuns[0];
		if (!firstRun) throw new Error("expected a backtest run fixture");
		expect(mapBacktestRun({ ...firstRun, benchmark_return: null } as RunResponse).benchmarkReturn).toBeNull();
	});

	it("preserves unavailable optional alpha evidence as explicit nulls", () => {
		const report = mapBacktestReport({
			...mockBacktestReport,
			alpha_stats: {
				...mockBacktestReport.alpha_stats,
				information_ratio: null,
				tracking_error: null,
				beta: null,
				alpha_annualized: null,
			},
		} as BacktestReportResponse);

		expect(report.alphaStats).toMatchObject({
			informationRatio: null,
			trackingError: null,
			beta: null,
			alphaAnnualized: null,
		});
	});

	it("fails closed when benchmark arrays and audit payload identity are absent", async () => {
		const fetchMock = vi.fn<typeof fetch>(async (input, init) => {
			const path = requestPath(capturedRequest([[input, init]])).split("?")[0];
			if (path === "/api/v1/backtests/runs/run-1/benchmark") {
				return Response.json({ data: { run_id: "run-1", dates: null, navs: null, benchmark_return: null } });
			}
			if (path === "/api/v1/backtests/runs/run-1/audit") {
				return Response.json({
					data: [
						{
							id: 1,
							run_id: "run-1",
							trade_date: "2026-09-04",
							record_type: "backtest.completed",
							created_at: "2026-09-04T00:00:00Z",
						},
					],
				});
			}
			throw new Error(`Unhandled backtest request ${path}`);
		});
		vi.stubGlobal("fetch", fetchMock);

		await expect(fetchBacktestBenchmark("run-1")).resolves.toEqual({
			runId: "run-1",
			dates: [],
			navs: [],
			benchmarkReturn: null,
		});
		await expect(fetchBacktestAudit("run-1")).resolves.toEqual([
			{
				id: 1,
				runId: "run-1",
				tradeDate: "2026-09-04",
				recordType: "backtest.completed",
				instrumentId: null,
				payload: {},
				createdAt: "2026-09-04T00:00:00Z",
			},
		]);
	});
});

it.each(["currency", "direction", "identity", "quantity"])(
	"rejects a malformed saved fee bill over HTTP: %s",
	async (field) => {
		const bill = {
			currency: "CNY",
			policy: "saved",
			rules_observed_at: "2026-11-09",
			source_ref: "fees",
			final_cash: 8994.97,
			fills: [
				{
					fill_id: "f",
					order_id: "o",
					instrument_id: 1,
					symbol: "600000.SSE",
					trade_date: "2014-01-02",
					direction: "buy",
					quantity: 100,
					price: 10,
					commission: 5,
					stamp_duty: 0,
					transfer_fee: 0.03,
					total_fee: 5.03,
					schedule: {
						instrument_id: 1,
						as_of_date: "2014-01-01",
						commission_rate: 0.0003,
						min_commission: 5,
						stamp_duty_rate: 0.001,
						transfer_fee_rate: 0,
						transfer_fee_per_share: 0.0003,
					},
				},
			],
		};
		const fill = bill.fills[0];
		if (!fill) throw new Error("missing test fill");
		if (field === "currency") bill.currency = "USD";
		if (field === "direction") fill.direction = "unknown";
		if (field === "identity") fill.schedule.instrument_id = 2;
		if (field === "quantity") fill.quantity = -100;
		vi.stubGlobal(
			"fetch",
			vi.fn<typeof fetch>(async () => Response.json({ data: { ...mockBacktestReport, fee_statement: bill } })),
		);
		await expect(fetchBacktestReport("bt-001")).rejects.toThrow("费用账单响应无效");
	},
);
