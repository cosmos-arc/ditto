import { describe, expect, it } from "vitest";
import type { BacktestReport, BacktestRun } from "../types";
import { MAX_COMPARE_RUNS, metricsRows, multiRunSeries, runColor } from "./multi-run-mapping";

function run(runId: string): BacktestRun {
	return {
		runId,
		strategyId: "seed_etf_industry_rotation",
		strategyVersion: "4",
		mode: "backtest",
		status: "completed",
		startedAt: "2026-08-28T09:00:00Z",
		completedAt: "2026-08-28T09:14:00Z",
		errorMessage: "",
		parentRunId: "",
		benchmarkReturn: null,
		progressPct: 100,
		currentStep: "completed",
		completedDays: 244,
		totalDays: 244,
	};
}

const report = (runId: string): BacktestReport => ({
	runId,
	periodStart: "2025-01-02",
	periodEnd: "2025-12-31",
	initialCash: 1_000_000,
	finalNav: 1_182_000,
	rebalanceFreq: "weekly",
	alphaStats: {
		annualizedReturn: 18.2,
		annualizedVolatility: 12.4,
		sharpeRatio: 1.47,
		sortinoRatio: 2.1,
		maxDrawdown: -12.5,
		maxDrawdownDurationDays: 48,
		calmarRatio: 1.46,
		informationRatio: null,
		trackingError: null,
		beta: null,
		alphaAnnualized: null,
		totalTurnover: 9.8,
		avgTurnoverPerRebalance: 0.4,
		totalFees: 5400,
		netReturnAfterCost: 17.1,
		costDrag: 1.1,
	},
	tradeStats: null,
});

describe("multi-run-mapping", () => {
	it("colors runs by the 8-slot sequential palette and caps selection", () => {
		expect(runColor(0)).toBe("var(--chart-run-1)");
		expect(runColor(7)).toBe("var(--chart-run-8)");
		expect(MAX_COMPARE_RUNS).toBe(8);
	});

	it("normalizes each run nav to its own first point and keeps empty navs honest", () => {
		const series = multiRunSeries([
			{
				runId: "r1",
				nav: [
					{ tradeDate: "2026-01-05", nav: 2 },
					{ tradeDate: "2026-01-06", nav: 3 },
				],
			},
			{ runId: "r2", nav: [] },
		]);
		expect(series[0]?.bars.map((bar) => bar.close)).toEqual([1, 1.5]);
		expect(series[0]?.color).toBe("var(--chart-run-1)");
		// nav₀ 为 0 的序列同样映射为空（不虚构归一基准）
		expect(multiRunSeries([{ runId: "r3", nav: [{ tradeDate: "2026-01-05", nav: 0 }] }])[0]?.bars).toEqual([]);
		// 空 nav 保留序列位（图例可见、图上无曲线）
		expect(series[1]?.bars).toEqual([]);
		expect(series[1]?.id).toBe("r2");
	});

	it("builds metrics rows from published reports and marks unpublished runs", () => {
		const rows = metricsRows([run("r1"), run("r2")], new Map([["r1", report("r1")]]));
		expect(rows[0]).toMatchObject({
			runId: "r1",
			period: "2025-01-02 → 2025-12-31",
			annualizedReturn: "18.20%",
			maxDrawdown: "-12.50%",
			sharpe: "1.47",
			reportPublished: true,
		});
		expect(rows[1]).toMatchObject({ runId: "r2", annualizedReturn: "未发布", reportPublished: false });
	});
});
