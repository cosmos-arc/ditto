import { afterEach, describe, expect, it, vi } from "vitest";
import { mockBacktestReport, mockBacktestRuns } from "@/mocks/fixtures/backtest";
import { capturedRequest, requestPath } from "@/test/request";
import type { BacktestReportResponse, RunResponse } from "./backtests";
import { fetchBacktestAudit, fetchBacktestBenchmark, mapBacktestReport, mapBacktestRun } from "./backtests";

afterEach(() => vi.unstubAllGlobals());

describe("backtest API view-model boundaries", () => {
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
