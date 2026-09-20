import type { CockpitBar, CockpitSeriesSpec } from "@/components/chart";
import type { FactorEvaluationSeriesResponse } from "../api/factor-series";

/**
 * 因子评估序列视图模型：列式响应 → Cockpit 序列与热力图模型的纯函数映射。
 * 缺失值（null，如滚动 IR warm-up）映射为断口；月度 IC 聚合为年份×月份网格。
 */

export type MonthlyIcRow = {
	readonly year: number;
	readonly cells: ReadonlyArray<{ readonly month: number; readonly meanIc: number | null; readonly days: number }>;
};

function dateToUnix(tradeDate: string): number {
	return Date.parse(`${tradeDate}T00:00:00Z`) / 1000;
}

function toBars(dates: readonly string[], values: ReadonlyArray<number | null>): CockpitBar[] {
	return dates.map((tradeDate, index) => ({
		time: dateToUnix(tradeDate),
		close: values[index] ?? null,
		volume: null,
	}));
}

/** IC（左轴）+ 滚动 IR（右轴）双轴序列。 */
export function icSeries(response: FactorEvaluationSeriesResponse): CockpitSeriesSpec[] {
	const dates = response.dates;
	const formatIc = (value: number): string => `${value > 0 ? "+" : ""}${value.toFixed(3)}`;
	return [
		{
			id: "ic",
			label: "Rank IC",
			bars: toBars(dates, response.ic),
			color: "var(--chart-run-1)",
			lineWidth: 1,
			format: formatIc,
			priceScaleId: "left",
		},
		{
			id: "rolling_ir",
			label: `滚动IR(${response.rolling_ir_window}d)`,
			bars: toBars(dates, response.rolling_ir),
			color: "var(--chart-run-6)",
			lineWidth: 2,
			format: (value) => `${value > 0 ? "+" : ""}${value.toFixed(2)}`,
			priceScaleId: "right",
		},
	];
}

/** Q1–QN 分位净值 + 多空 spread（同一净值尺度）。 */
export function quantileSeries(response: FactorEvaluationSeriesResponse): CockpitSeriesSpec[] {
	const dates = response.dates;
	const quantiles: CockpitSeriesSpec[] = response.quantile_nav.map((column, index) => ({
		id: `q_${column.quantile}`,
		label: `Q${column.quantile}`,
		bars: toBars(dates, column.nav),
		color: `var(--chart-quantile-${column.quantile})`,
		lineWidth: column.quantile === 1 || column.quantile === response.n_quantiles ? 2 : 1,
		format: (value) => value.toFixed(3),
		...(index === 0 ? {} : {}),
	}));
	return [
		...quantiles,
		{
			id: "ls_spread",
			label: "多空 spread",
			bars: toBars(dates, response.ls_nav),
			color: "var(--chart-ls-spread)",
			lineWidth: 2,
			format: (value) => value.toFixed(3),
		},
	];
}

/** 月度 IC 热力图模型：按年份分行的 12 月网格（缺月为 null）。 */
export function monthlyIcRows(response: FactorEvaluationSeriesResponse): MonthlyIcRow[] {
	const byYear = new Map<number, Map<number, { meanIc: number | null; days: number }>>();
	for (const cell of response.monthly_ic) {
		const months = byYear.get(cell.year) ?? new Map();
		months.set(cell.month, { meanIc: cell.mean_ic ?? null, days: cell.days });
		byYear.set(cell.year, months);
	}
	return [...byYear.entries()]
		.sort(([a], [b]) => a - b)
		.map(([year, months]) => ({
			year,
			cells: Array.from(
				{ length: 12 },
				(_, month) =>
					months.get(month + 1) ?? {
						meanIc: null,
						days: 0,
					},
			).map((cell, index) => ({ month: index + 1, ...cell })),
		}));
}

/**
 * 热力图单元格热度桶：正负走涨跌色 token，幅度分 5 档（每 0.02 IC 一档，
 * 封顶 0.1）；缺失月为 "none"（无底色）。样式由 globals.css 的 .heat-cell 承载。
 */
export function heatmapBucket(meanIc: number | null): string {
	if (meanIc === null) return "none";
	const level = Math.min(Math.trunc(Math.abs(meanIc) / 0.02) + 1, 5);
	return `${meanIc >= 0 ? "up" : "down"}-${level}`;
}
