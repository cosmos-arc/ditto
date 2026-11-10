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

it.each(["valid", "nav", "kind", "locked", "cost", "listing", "asset", "etfShares"])(
	"validates saved distribution evidence over HTTP: %s",
	async (field) => {
		const statement = {
			currency: "CNY",
			policy: "saved",
			events: [
				{
					event_id: "1:2020-06-02",
					asset_class: "stock",
					instrument_id: 1,
					source_ticker: "600000.SH",
					source_snapshot_id: "source:shares",
					announcement_date: "2020-05-28",
					record_date: "2020-06-02",
					ex_date: "2020-06-03",
					pay_date: null,
					gross_per_share: 0,
					share_ratio: 0.5,
					listing_date: "2020-06-05",
					taxable_share_income: 0,
					share_tax_basis: "issuer:premium-capital",
					registered_quantity: 100,
				},
			],
			entries: [
				{
					event_id: "1:2020-06-02",
					day: "2020-06-03",
					kind: "receivable",
					amount: 100,
					quantity: 100,
					acquired: "2020-06-01",
				},
			],
			balances: [
				{
					trade_date: "2020-06-03",
					cash: 1000,
					available_cash: 1000,
					receivable: 100,
					tax_payable: 0,
					market_value: 900,
					nav: 2000,
					positions: [
						{
							instrument_id: 1,
							source_ticker: "600000.SH",
							quantity: 150,
							available_quantity: 100,
							locked_quantity: 50,
							average_cost: 8,
							total_cost: 1200,
							market_value: 900,
						},
					],
				},
			],
		};
		if (field === "asset") statement.events[0]!.asset_class = "unknown";
		if (field === "etfShares") statement.events[0]!.asset_class = "etf";
		if (field === "nav") statement.balances[0]!.nav = 2100;
		if (field === "kind") statement.entries[0]!.kind = "unknown";
		if (field === "locked") statement.balances[0]!.positions[0]!.locked_quantity = 0;
		if (field === "cost") statement.balances[0]!.positions[0]!.total_cost = 800;
		if (field === "listing") statement.events[0]!.listing_date = "2020-06-01";
		vi.stubGlobal(
			"fetch",
			vi.fn<typeof fetch>(async () =>
				Response.json({ data: { ...mockBacktestReport, dividend_statement: statement } }),
			),
		);
		if (field === "valid") {
			const report = await fetchBacktestReport("run-1");
			expect(report.dividendStatement?.events[0]).toMatchObject({ pay: null, shareRatio: 0.5, listing: "2020-06-05" });
			expect(report.dividendStatement?.balances[0]?.positions[0]).toMatchObject({
				quantity: 150,
				availableQuantity: 100,
				lockedQuantity: 50,
				totalCost: 1200,
			});
		} else await expect(fetchBacktestReport("run-1")).rejects.toThrow("分红账本金额或来源不一致");
	},
);

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

it("preserves other statistics when undefined optional ratios are omitted by HTTP", async () => {
	vi.stubGlobal(
		"fetch",
		vi.fn<typeof fetch>(async () =>
			Response.json({
				data: {
					...mockBacktestReport,
					aggregated_trade_stats: {
						...mockBacktestReport.aggregated_trade_stats,
						profit_factor: undefined,
						avg_win_loss_ratio: undefined,
						total_trades: 3,
					},
				},
			}),
		),
	);
	const report = await fetchBacktestReport("bt-001");
	expect(report.tradeStats).toMatchObject({ totalTrades: 3, profitFactor: null, avgWinLossRatio: null });
});
