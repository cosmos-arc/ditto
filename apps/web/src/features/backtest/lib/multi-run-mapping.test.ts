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

	it("inserts whitespace gaps on the union timeline without extending a run's own range", () => {
		const day = (iso: string) => Date.parse(`${iso}T00:00:00Z`) / 1000;
		const series = multiRunSeries([
			{
				runId: "a",
				// 自身缺 01-06：被另一 run 覆盖 → 内部补 null 断口，不视觉插值
				nav: [
					{ tradeDate: "2026-01-05", nav: 1 },
					{ tradeDate: "2026-01-07", nav: 2 },
				],
			},
			{
				runId: "b",
				// 晚开始的 run：并集里的 01-05 不外延为前导 null
				nav: [
					{ tradeDate: "2026-01-06", nav: 5 },
					{ tradeDate: "2026-01-07", nav: 6 },
				],
			},
		]);
		expect(series[0]?.bars.map((bar) => [bar.time, bar.close])).toEqual([
			[day("2026-01-05"), 1],
			[day("2026-01-06"), null],
			[day("2026-01-07"), 2],
		]);
		expect(series[1]?.bars.map((bar) => bar.time)).toEqual([day("2026-01-06"), day("2026-01-07")]);
	});

	it("builds metrics rows from published reports and distinguishes pending/failed/unpublished", () => {
		const rows = metricsRows(
			[run("r1"), run("r2"), run("r3"), run("r4")],
			new Map([
				["r1", { report: report("r1"), pending: false, failed: false }],
				["r2", { report: undefined, pending: true, failed: false }],
				["r3", { report: undefined, pending: false, failed: true }],
				["r4", { report: undefined, pending: false, failed: false }],
			]),
		);
		expect(rows[0]).toMatchObject({
			runId: "r1",
			period: "2025-01-02 → 2025-12-31",
			annualizedReturn: "18.20%",
			maxDrawdown: "-12.50%",
			sharpe: "1.47",
			reportPublished: true,
		});
		// 查询未定/失败是「未知」：不提前标「未发布」（404 落定才是）
		expect(rows[1]).toMatchObject({ runId: "r2", annualizedReturn: "读取中…", reportPublished: false });
		expect(rows[2]).toMatchObject({ runId: "r3", annualizedReturn: "读取失败", reportPublished: false });
		expect(rows[3]).toMatchObject({ runId: "r4", annualizedReturn: "未发布", reportPublished: false });
		// 缓存 report + 重取失败：failed 优先，不把 stale 缓存当已发布（与 fetch-error alert 一致）
		const staleRows = metricsRows(
			[run("r5")],
			new Map([["r5", { report: report("r5"), pending: false, failed: true }]]),
		);
		expect(staleRows[0]).toMatchObject({ runId: "r5", annualizedReturn: "读取失败", reportPublished: false });
	});
});
