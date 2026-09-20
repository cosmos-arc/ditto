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

/** 可见 run → Cockpit 序列（归一化净值；空 nav → 空 bars 序列，保留图例位）。
 * 等宽线（CR #236-4）：勾选顺序是操作顺序而非优先级，序列区分只靠色板。
 * 并集时间轴（CR：内部缺失插 whitespace）：各 run 自身缺失的交易日若被其他 run
 * 覆盖，在该序列自身 [首日, 末日] 范围内补 close: null 断口，不视觉插值；
 * 序列范围之外的并集日期不外延（晚开始的 run 不加前导 null）。 */
export function multiRunSeries(runs: readonly RunNavInput[]): CockpitSeriesSpec[] {
	const normalized = runs.map((run) => normalizedNavPoints(run.nav));
	const unionTimes = [...new Set(normalized.flat().map((bar) => bar.time))].sort((left, right) => left - right);
	const aligned = normalized.map((bars) => {
		if (bars.length === 0) return bars;
		const byTime = new Map(bars.map((bar) => [bar.time, bar]));
		const first = bars[0]!.time;
		const last = bars[bars.length - 1]!.time;
		return unionTimes
			.filter((time) => time >= first && time <= last)
			.map((time) => byTime.get(time) ?? { time, close: null, volume: null });
	});
	return aligned.map((bars, index) => ({
		id: runs[index]!.runId,
		label: runs[index]!.runId,
		bars,
		color: runColor(index),
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

/** 单 run 的 report 查询状态：未定（加载/失败）期间不得标注「未发布」。 */
export type ReportReadState = {
	readonly report: BacktestReport | undefined;
	/** 查询仍在进行——指标尚未可知。 */
	readonly pending: boolean;
	/** 404 之外的失败——与页面 fetch-error alert 同源。 */
	readonly failed: boolean;
};

const money = (value: number): string => new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 2 }).format(value);

/** 引擎 alpha_stats 为百分数单位（#212 已对齐），此处不再 ×100。 */
const percent = (value: number): string => `${value.toFixed(2)}%`;

function metricsRow(run: BacktestRun, read: ReportReadState): MultiRunMetricsRow {
	if (!read.report) {
		// 加载中/读取失败是「未知」，404 落定才是「未发布」——不提前下结论
		const annualized = read.pending ? "读取中…" : read.failed ? "读取失败" : "未发布";
		return {
			runId: run.runId,
			strategyId: run.strategyId,
			period: "—",
			initialCash: "—",
			finalNav: "—",
			annualizedReturn: annualized,
			maxDrawdown: "—",
			sharpe: "—",
			reportPublished: false,
		};
	}
	const alpha = read.report.alphaStats;
	return {
		runId: run.runId,
		strategyId: run.strategyId,
		period:
			read.report.periodStart && read.report.periodEnd ? `${read.report.periodStart} → ${read.report.periodEnd}` : "—",
		initialCash: money(read.report.initialCash),
		finalNav: money(read.report.finalNav),
		annualizedReturn: alpha ? percent(alpha.annualizedReturn) : "—",
		maxDrawdown: alpha ? percent(alpha.maxDrawdown) : "—",
		sharpe: alpha ? alpha.sharpeRatio.toFixed(2) : "—",
		reportPublished: true,
	};
}

/** 指标差异表行：按传入 run 顺序（= 色板顺序），report 未定/失败/未发布逐格诚实标注。 */
export function metricsRows(
	runs: readonly BacktestRun[],
	reports: ReadonlyMap<string, ReportReadState>,
): MultiRunMetricsRow[] {
	return runs.map((run) =>
		metricsRow(run, reports.get(run.runId) ?? { report: undefined, pending: false, failed: false }),
	);
}
