import type { CockpitBand, CockpitBar } from "@/components/chart";
import type { BacktestBenchmark, BacktestNavPoint } from "../types";

/**
 * 回测净值图表视图模型：NAV/基准 → Cockpit 序列的纯函数映射。
 *
 * 口径对齐：
 * - 归一：策略净值与基准都归一到首点 1.0（服务端基准已归一；nav/nav₀ 本地归一），
 *   两侧同尺度才可叠加。
 * - 回撤：nav/peak − 1（peak 取自首点起的滚动高点），与后端
 *   `drawdown_analysis` 同口径（KPI strip 的最大回撤 = 水下曲线最深点的绝对值）。
 * - 断口：基准缺失区间映射为 whitespace（不插值、不补零）。
 */

export function dateToUnix(tradeDate: string): number {
	return Date.parse(`${tradeDate}T00:00:00Z`) / 1000;
}

function toBars(points: readonly { readonly tradeDate: string; readonly nav: number }[]): CockpitBar[] {
	return points.map((point) => ({
		time: dateToUnix(point.tradeDate),
		close: point.nav,
		volume: null,
	}));
}

/** 策略净值（绝对值 → 归一 1.0 起步）。空序列返回空。 */
export function normalizedNavPoints(nav: readonly BacktestNavPoint[]): CockpitBar[] {
	const base = nav[0]?.nav;
	if (base === undefined || base === 0) return [];
	return toBars(nav).map((bar) => ({
		...bar,
		close: bar.close === null ? null : bar.close / base,
	}));
}

/**
 * 基准序列按净值时间轴对齐：缺失日插入 whitespace 断口。
 * 基准超出净值范围的多余日期丢弃（时间轴以策略证据为锚）。
 */
export function alignedBenchmarkPoints(
	navBars: readonly CockpitBar[],
	benchmark: Pick<BacktestBenchmark, "dates" | "navs">,
): CockpitBar[] {
	if (navBars.length === 0 || benchmark.dates.length === 0) return [];
	const byDate = new Map<number, number>(
		benchmark.dates.map((date, index) => [dateToUnix(date), benchmark.navs[index] ?? Number.NaN]),
	);
	return navBars.map((navBar) => {
		const value = byDate.get(navBar.time);
		return {
			time: navBar.time,
			close: value === undefined || Number.isNaN(value) ? null : value,
			volume: null,
		};
	});
}

/** 超额收益（小数）：navNorm − benchNorm；任一侧缺失即为断口。 */
export function excessPoints(navBars: readonly CockpitBar[], benchmarkBars: readonly CockpitBar[]): CockpitBar[] {
	const benchByTime = new Map(benchmarkBars.map((bar) => [bar.time, bar.close]));
	return navBars.map((navBar) => {
		const bench = benchByTime.get(navBar.time) ?? null;
		return {
			time: navBar.time,
			close: navBar.close !== null && bench !== null ? navBar.close - bench : null,
			volume: null,
		};
	});
}

/** 回撤水下序列（小数，≤0）：nav/peak − 1，peak 自首点起滚动。 */
export function drawdownPoints(navBars: readonly CockpitBar[]): CockpitBar[] {
	let peak = Number.NaN;
	return navBars.map((navBar) => {
		if (navBar.close === null) {
			return { time: navBar.time, close: null, volume: null };
		}
		peak = Number.isNaN(peak) ? navBar.close : Math.max(peak, navBar.close);
		return { time: navBar.time, close: peak === 0 ? null : navBar.close / peak - 1, volume: null };
	});
}

/** 回撤区间（peak→恢复）：连续水下段并为一条底色带；未恢复段延至末点。 */
export function drawdownBands(navBars: readonly CockpitBar[]): CockpitBand[] {
	const bands: CockpitBand[] = [];
	let underwaterFrom: number | null = null;
	let previousPeak = Number.NaN;
	for (const bar of navBars) {
		if (bar.close === null) continue;
		previousPeak = Number.isNaN(previousPeak) ? bar.close : Math.max(previousPeak, bar.close);
		const underwater = bar.close < previousPeak;
		if (underwater && underwaterFrom === null) {
			underwaterFrom = bar.time;
		} else if (!underwater && underwaterFrom !== null) {
			bands.push({
				id: `drawdown-${underwaterFrom}`,
				from: underwaterFrom,
				to: bar.time,
				color: "var(--chart-series-down)",
			});
			underwaterFrom = null;
		}
	}
	if (underwaterFrom !== null) {
		const lastTime = navBars.at(-1)?.time;
		if (lastTime !== undefined) {
			bands.push({
				id: `drawdown-${underwaterFrom}`,
				from: underwaterFrom,
				to: lastTime,
				color: "var(--chart-series-down)",
			});
		}
	}
	return bands;
}

/** 基准缺失区间数（对齐后 close === null 的连续段），用于 partial 标注。 */
export function benchmarkGapCount(benchmarkBars: readonly CockpitBar[]): number {
	let gaps = 0;
	let inGap = false;
	for (const bar of benchmarkBars) {
		if (bar.close === null) {
			if (!inGap) {
				gaps += 1;
				inGap = true;
			}
		} else {
			inGap = false;
		}
	}
	return gaps;
}

const NAV_DIGITS = 4;

/** 图例读数格式化（与 KPI strip 同数值纪律：tabular-nums、固定位数）。 */
export const formatNav = (value: number): string => value.toFixed(NAV_DIGITS);

export const formatSignedPercent = (value: number): string => {
	const sign = value > 0 ? "+" : value < 0 ? "−" : "";
	return `${sign}${Math.abs(value * 100).toFixed(2)}%`;
};
