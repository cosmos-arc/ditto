import type { BarPeriod, CockpitBar } from "@/components/chart";
import type { InstrumentBar } from "../api/instrument-workspace";

/**
 * 标的页图表映射：API Bar DTO → Chart Cockpit view model。
 * 纯函数，只承诺外部行为（时间口径、Primary Answer 数字纪律、陈旧判定）。
 */

/** `YYYY-MM-DD` → Unix 秒（UTC，与导出/读数统一口径）。 */
export function tradeDateToUnix(tradeDate: string): number {
	return Date.parse(`${tradeDate}T00:00:00Z`) / 1000;
}

/** Unix 秒 → `YYYY-MM-DD`（UTC 日期）。 */
export function formatTradeDate(unixSeconds: number): string {
	return new Date(unixSeconds * 1000).toISOString().slice(0, 10);
}

export function toCockpitBars(bars: readonly InstrumentBar[]): CockpitBar[] {
	return [...bars]
		.sort((left, right) => left.trade_date.localeCompare(right.trade_date))
		.map((bar) => ({
			time: tradeDateToUnix(bar.trade_date),
			open: bar.open,
			high: bar.high,
			low: bar.low,
			close: bar.close,
			volume: bar.volume,
		}));
}

export type ChartPrimaryAnswer = {
	readonly tradeDate: string;
	readonly close: number;
	readonly previousClose: number | null;
	readonly change: number | null;
	readonly changePercent: number | null;
	readonly windowLow: number;
	readonly windowHigh: number;
	readonly direction: "up" | "down" | "flat";
};

/** 由（升序）bars 推导 Primary Answer 关键数字：最新收盘、对前收盘涨跌、区间高低。 */
export function primaryAnswerFromBars(bars: readonly CockpitBar[]): ChartPrimaryAnswer | null {
	const last = lastBar(bars);
	if (!last || last.close === null) return null;
	const previous = lastBar(bars.slice(0, -1));
	const lows = bars.filter((bar) => bar.close !== null).map((bar) => bar.low ?? bar.close ?? Number.NaN);
	const highs = bars.filter((bar) => bar.close !== null).map((bar) => bar.high ?? bar.close ?? Number.NaN);
	const change = previous?.close != null ? last.close - previous.close : null;
	const changePercent = change !== null && previous?.close ? (change / previous.close) * 100 : null;
	return {
		tradeDate: new Date(last.time * 1000).toISOString().slice(0, 10),
		close: last.close,
		previousClose: previous?.close ?? null,
		change,
		changePercent,
		windowLow: Math.min(...lows),
		windowHigh: Math.max(...highs),
		direction: change === null || change === 0 ? "flat" : change > 0 ? "up" : "down",
	};
}

/** 最近一根 bar 距今天数（UTC 口径），用于数据级陈旧判定。 */
export function barsAgeDays(bars: readonly CockpitBar[], nowMs: number): number | null {
	const last = lastBar(bars);
	if (!last) return null;
	return Math.floor((nowMs - last.time * 1000) / 86_400_000);
}

function nextWeekdayUnix(unixSeconds: number): number {
	const date = new Date(unixSeconds * 1000);
	let add = 1;
	if (date.getUTCDay() === 5) add = 3;
	else if (date.getUTCDay() === 6) add = 2;
	return unixSeconds + add * 86_400;
}

/**
 * 日历缺口：日线序列中缺失的交易日区间（API Bar 合同不携带 null OHLC，
 * 缺失日即缺席行）。仅跳过周末；缺失 ≥1 个交易日即视为断口。
 */
export function findCalendarGaps(bars: readonly CockpitBar[]): Array<{ from: number; to: number }> {
	const sorted = [...bars].sort((a, b) => a.time - b.time);
	const gaps: Array<{ from: number; to: number }> = [];
	for (let index = 1; index < sorted.length; index += 1) {
		const previous = sorted[index - 1];
		const current = sorted[index];
		if (previous === undefined || current === undefined) continue;
		if (current.time > nextWeekdayUnix(previous.time)) {
			gaps.push({ from: previous.time, to: current.time });
		}
	}
	return gaps;
}

function lastBar(bars: readonly CockpitBar[]): CockpitBar | null {
	return bars.length > 0 ? (bars[bars.length - 1] ?? null) : null;
}

/** 展示周期标签（控制条与 aria 用）。 */
export const BAR_PERIOD_OPTIONS: ReadonlyArray<{ readonly value: BarPeriod; readonly label: string }> = [
	{ value: "daily", label: "日" },
	{ value: "weekly", label: "周" },
	{ value: "monthly", label: "月" },
];
