import type { CockpitSeriesSpec } from "@/components/chart";
import type { BacktestReport, BacktestRun } from "../types";
import { formatNav, normalizedNavPoints } from "./nav-chart-mapping";

/**
 * 多 run 净值叠加视图模型（#215 ②）。
 *
 * - 色板：8 色顺序 run 色（--chart-run-1..8，M1 token），第 9 个起循环——
 *   页面在选取上限 8 处已拦截，循环仅作类型层兜底；
 * - 归一：各 run 的 nav/nav₀（与 #212 单 run 净值同口径），跨初始资金可比；
 *   绝对净值与关键指标在差异表中按 run 原值呈现，不混入图内；
 * - 诚实性：nav 为空（未发布/未落盘）的 run 保留序列位（空 bars），图上无曲线、
 *   差异表标「未发布」，不虚构。
 */

const RUN_COLOR_TOKENS = [
	"--chart-run-1",
	"--chart-run-2",
	"--chart-run-3",
	"--chart-run-4",
	"--chart-run-5",
	"--chart-run-6",
	"--chart-run-7",
	"--chart-run-8",
] as const;

export const MAX_COMPARE_RUNS = RUN_COLOR_TOKENS.length;

export function runColor(index: number): string {
	return `var(${RUN_COLOR_TOKENS[index % RUN_COLOR_TOKENS.length]})`;
}

export type RunNavInput = {
	readonly runId: string;
	readonly nav: readonly { readonly tradeDate: string; readonly nav: number }[];
};

/** 可见 run → Cockpit 序列（归一化净值；空 nav → 空 bars 序列，保留图例位）。 */
export function multiRunSeries(runs: readonly RunNavInput[]): CockpitSeriesSpec[] {
	return runs.map((run, index) => ({
		id: run.runId,
		label: run.runId,
		bars: normalizedNavPoints(run.nav),
		color: runColor(index),
		lineWidth: index === 0 ? 2 : 1,
		format: formatNav,
	}));
}

export type MultiRunMetricsRow = {
	readonly runId: string;
	readonly strategyId: string;
	readonly period: string;
	readonly initialCash: string;
	readonly finalNav: string;
	readonly annualizedReturn: string;
	readonly maxDrawdown: string;
	readonly sharpe: string;
	readonly reportPublished: boolean;
};

const money = (value: number): string => new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 2 }).format(value);

/** 引擎 alpha_stats 为百分数单位（#212 已对齐），此处不再 ×100。 */
const percent = (value: number): string => `${value.toFixed(2)}%`;

function metricsRow(run: BacktestRun, report: BacktestReport | undefined): MultiRunMetricsRow {
	if (!report) {
		return {
			runId: run.runId,
			strategyId: run.strategyId,
			period: "—",
			initialCash: "—",
			finalNav: "—",
			annualizedReturn: "未发布",
			maxDrawdown: "—",
			sharpe: "—",
			reportPublished: false,
		};
	}
	const alpha = report.alphaStats;
	return {
		runId: run.runId,
		strategyId: run.strategyId,
		period: report.periodStart && report.periodEnd ? `${report.periodStart} → ${report.periodEnd}` : "—",
		initialCash: money(report.initialCash),
		finalNav: money(report.finalNav),
		annualizedReturn: alpha ? percent(alpha.annualizedReturn) : "—",
		maxDrawdown: alpha ? percent(alpha.maxDrawdown) : "—",
		sharpe: alpha ? alpha.sharpeRatio.toFixed(2) : "—",
		reportPublished: true,
	};
}

/** 指标差异表行：按传入 run 顺序（= 色板顺序），缺 report 的 run 诚实标注。 */
export function metricsRows(
	runs: readonly BacktestRun[],
	reports: ReadonlyMap<string, BacktestReport>,
): MultiRunMetricsRow[] {
	return runs.map((run) => metricsRow(run, reports.get(run.runId)));
}
