import type { CockpitBar, CockpitOverlay, CockpitSubPane } from "@/components/chart";
import type { IndicatorSeriesResponse } from "../api/indicator-overlays";
import { tradeDateToUnix } from "./chart-mapping";

/**
 * 指标叠加视图模型：序列 API 的列式响应 → Cockpit overlay/subPane。
 * warm-up 段（null）映射为断口；仅日线周期（周/月指标口径不同，不近似）。
 */

export type IndicatorToggles = {
	readonly ma: boolean;
	readonly donchian: boolean;
	readonly macd: boolean;
	readonly rsi: boolean;
	readonly atr: boolean;
	readonly nav: boolean;
};

export const DEFAULT_INDICATOR_TOGGLES: IndicatorToggles = {
	ma: false,
	donchian: false,
	macd: false,
	rsi: false,
	atr: false,
	nav: false,
};

const STORAGE_KEY = "ditto.instrument-chart-indicators.v1";

export function readIndicatorToggles(): IndicatorToggles {
	if (typeof localStorage === "undefined") return DEFAULT_INDICATOR_TOGGLES;
	try {
		const raw = localStorage.getItem(STORAGE_KEY);
		if (!raw) return DEFAULT_INDICATOR_TOGGLES;
		const parsed = JSON.parse(raw) as Partial<IndicatorToggles>;
		return { ...DEFAULT_INDICATOR_TOGGLES, ...parsed };
	} catch {
		return DEFAULT_INDICATOR_TOGGLES;
	}
}

export function writeIndicatorToggles(toggles: IndicatorToggles): void {
	if (typeof localStorage === "undefined") return;
	localStorage.setItem(STORAGE_KEY, JSON.stringify(toggles));
}

function seriesToBars(tradeDates: readonly string[], values: readonly (number | null)[]): CockpitBar[] {
	return tradeDates.map((tradeDate, index) => ({
		time: tradeDateToUnix(tradeDate),
		close: values[index] ?? null,
		volume: null,
	}));
}

function column(response: IndicatorSeriesResponse, name: string): CockpitBar[] {
	const found = response.series.find((item) => item.name === name);
	return found ? seriesToBars(response.trade_dates, found.values) : [];
}

/** 主图叠加线：MA(5/20/60) + Donchian 上下轨。 */
export function indicatorOverlays(response: IndicatorSeriesResponse, toggles: IndicatorToggles): CockpitOverlay[] {
	const overlays: CockpitOverlay[] = [];
	if (toggles.ma) {
		overlays.push({ id: "ma_5", points: column(response, "ma_5"), color: "var(--chart-run-1)", lineWidth: 1 });
		overlays.push({ id: "ma_20", points: column(response, "ma_20"), color: "var(--chart-run-2)", lineWidth: 1 });
		overlays.push({ id: "ma_60", points: column(response, "ma_60"), color: "var(--chart-run-3)", lineWidth: 1 });
	}
	if (toggles.donchian) {
		overlays.push({
			id: "donchian_high",
			points: column(response, "donchian_high"),
			color: "var(--chart-run-6)",
			lineWidth: 1,
		});
		overlays.push({
			id: "donchian_low",
			points: column(response, "donchian_low"),
			color: "var(--chart-run-6)",
			lineWidth: 1,
		});
	}
	return overlays.filter((overlay) => overlay.points.length > 0);
}

/** 指标副图：MACD（柱+双线）/ RSI / ATR。 */
export function indicatorSubPanes(response: IndicatorSeriesResponse, toggles: IndicatorToggles): CockpitSubPane[] {
	const panes: CockpitSubPane[] = [];
	if (toggles.macd) {
		const macdSeries = (
			[
				{
					id: "macd_histogram",
					points: column(response, "macd_histogram"),
					color: "var(--chart-series-neutral)",
					kind: "histogram",
				},
				{ id: "macd", points: column(response, "macd"), color: "var(--chart-run-1)" },
				{ id: "macd_signal", points: column(response, "macd_signal"), color: "var(--chart-run-6)" },
			] as const
		).filter((series) => series.points.length > 0);
		panes.push({ id: "macd", label: "MACD(12,26,9)", series: macdSeries });
	}
	if (toggles.rsi) {
		panes.push({
			id: "rsi",
			label: "RSI(14)",
			series: [{ id: "rsi", points: column(response, "rsi"), color: "var(--chart-run-4)" }].filter(
				(series) => series.points.length > 0,
			),
		});
	}
	if (toggles.atr) {
		panes.push({
			id: "atr",
			label: "ATR(14)",
			series: [{ id: "atr", points: column(response, "atr"), color: "var(--chart-run-7)" }].filter(
				(series) => series.points.length > 0,
			),
		});
	}
	return panes.filter((pane) => pane.series.length > 0);
}
