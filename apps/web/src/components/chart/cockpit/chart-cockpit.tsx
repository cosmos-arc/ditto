import {
	CandlestickSeries,
	ColorType,
	CrosshairMode,
	createChart,
	createSeriesMarkers,
	HistogramSeries,
	type IChartApi,
	type ISeriesApi,
	LineSeries,
	LineStyle,
	type LogicalRange,
	type MouseEventParams,
	type SeriesType,
	type Time,
} from "lightweight-charts";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { readWebBuildMetadata } from "@/api/build-metadata";
import { Button } from "@/components/ui/button";
import { withAlpha } from "@/lib/oklch";
import { StaleIndicator } from "@/lib/stale-indicator";
import { AsOfWatermark } from "./as-of-watermark";
import {
	buildPngFooterLines,
	type ChartExportIdentity,
	type CockpitBar,
	directionColorToken,
	FRESHNESS_THRESHOLDS,
	type FreshnessBucket,
	findGapRanges,
	formatReadoutTime,
	lastNonNullClose,
	splitByFreshness,
	toCandleSeriesData,
	toCsvExport,
	toHistogramSeriesData,
	toLineSeriesData,
	toVolumeSeriesData,
} from "./chart-data";
import { useChartTheme } from "./chart-theme";
import { broadcastCrosshairTime, broadcastVisibleRange, joinRangeGroup } from "./cockpit-link";
import { PaneBands } from "./pane-bands";

/**
 * Chart Cockpit 核心 shell：lightweight-charts 5 多 pane 工作台。
 *
 * - 跨 pane 时间轴联动 + 十字线同步：单一 chart 实例的价格/成交量 pane 天然共享；
 *   同 rangeId 的独立 cockpit 实例经 cockpit-link 同步可见区间与十字线时间戳。
 * - 键盘：←/→ 平移、↑/↓ 粗平移、+/− 缩放、Home/End 跳首尾、双击回全区间；容器可聚焦有焦点环。
 * - as_of 水位线（pane primitive）+ stale 徽标；数据缺失渲染断口不插值；
 *   实时序列可开 freshnessFade 按 --data-freshness-* 透明度时变（EOD 图表默认关）。
 * - PNG/CSV 导出携带完整 PIT 身份（裁决 #208-4：snapshot id 不截断）。
 *
 * 交互实现即时更新（无缓动动画），天然满足 prefers-reduced-motion。
 */

export type CockpitSeriesSpec = {
	readonly id: string;
	/** 图例读数标签（缺省用 id；CSV 列名始终用 id）。 */
	readonly label?: string;
	readonly bars: readonly CockpitBar[];
	/** CSS token 引用，如 "var(--chart-run-1)"（canvas 经 useChartTheme 解析）。 */
	readonly color: string;
	readonly lineWidth?: 1 | 2 | 3 | 4;
	/** 序列形态：线（默认，color 生效）或蜡烛（涨跌色走 Market 域 token）。 */
	readonly kind?: "line" | "candle";
	/** 图例读数格式化（与页面 KPI 同口径，如净值 4 位小数、百分比带符号）。 */
	readonly format?: (value: number) => string;
	/** 价格轴（双轴序列，如 IC 左轴 + 滚动 IR 右轴）；缺省右轴。 */
	readonly priceScaleId?: "left" | "right";
};

/** 主图（pane 0）叠加线，如 MA/Donchian 轨道/ETF 净值。 */
export type CockpitOverlay = {
	readonly id: string;
	readonly points: readonly CockpitBar[];
	readonly color: string;
	readonly lineWidth?: 1 | 2 | 3 | 4;
};

/** 独立副图（新 pane），与主图共享时间轴，如 MACD/RSI/ATR/超额/回撤。 */
export type CockpitSubPaneSeries = {
	readonly id: string;
	readonly points: readonly CockpitBar[];
	readonly color: string;
	/** 柱状（如 MACD histogram、回撤水下柱，涨跌色）或线（默认）。 */
	readonly kind?: "line" | "histogram";
	/** 图例读数标签（缺省用 id）。 */
	readonly label?: string;
	/** 图例读数格式化（与页面 KPI 同口径）。 */
	readonly format?: (value: number) => string;
};

export type CockpitSubPane = {
	readonly id: string;
	readonly label: string;
	readonly series: readonly CockpitSubPaneSeries[];
	readonly height?: number;
};

/** 主图（pane 0）横向区间底色，如回撤 peak→trough 区间；from/to 为 Unix 秒。 */
export type CockpitBand = {
	readonly id: string;
	readonly from: number;
	readonly to: number;
	/** CSS token 引用（canvas 经 useChartTheme 解析并降透明度）。 */
	readonly color: string;
};

/** 主序列上的事件标记（如回测买卖点）；buy 在 bar 上方箭头、sell 在 bar 下方箭头。 */
export type CockpitMarker = {
	readonly id: string;
	readonly time: number;
	readonly direction: "buy" | "sell";
	/** 标记悬停/图例短标签（如 "买入 400 股"）。 */
	readonly label?: string;
};

export type ChartCockpitIdentity = {
	readonly dataSourceName: string;
	readonly snapshotId?: string | null;
	readonly knowledgeCutoff?: string | null;
	readonly publicationCutoff?: string | null;
};

export type ChartCockpitProps = {
	readonly chartId: string;
	readonly rangeId: string;
	readonly ariaLabel: string;
	readonly series: readonly CockpitSeriesSpec[];
	readonly identity: ChartCockpitIdentity;
	readonly showVolumePane?: boolean;
	readonly overlays?: readonly CockpitOverlay[];
	readonly subPanes?: readonly CockpitSubPane[];
	readonly bands?: readonly CockpitBand[];
	/** 主序列事件标记（买卖点）；点击标记时回调 onMarkerClick。 */
	readonly markers?: readonly CockpitMarker[];
	readonly onMarkerClick?: (marker: CockpitMarker) => void;
	/** 初始定位（Unix 秒）：优先于 fitContent，把该时点滚到可视区中心（下钻定位）。 */
	readonly initialFocusTime?: number | null;
	readonly asOf?: { readonly time: number; readonly label?: string } | null;
	/** 实时数据透明度时变（live 1.0 → expired 0.25）；默认关闭，EOD 图表只用水位线 + stale 徽标。 */
	readonly freshnessFade?: boolean;
	readonly timeVisible?: boolean;
	readonly height?: number;
	/** 注入当前时间（测试固定新鲜度）；默认 Date.now()。 */
	readonly nowMs?: number;
	readonly exportName?: string;
};

const VOLUME_PANE_HEIGHT = 84;
const SUB_PANE_HEIGHT = 96;
// 空默认值必须用稳定引用：每次渲染新建数组会让内容 effect 失稳（重跑→fitContent 重置区间）。
const EMPTY_OVERLAYS: readonly CockpitOverlay[] = [];
const EMPTY_SUBPANES: readonly CockpitSubPane[] = [];
const EMPTY_BANDS: readonly CockpitBand[] = [];
const EMPTY_MARKERS: readonly CockpitMarker[] = [];
const AFFORDANCES = "crosshair tooltip zoom-pan linked-time-range";

type Readout = {
	readonly time: number;
	readonly values: readonly (number | null)[];
	readonly subValues: readonly (number | null)[];
	readonly volume: number | null;
};

/** time → close/volume 查找索引：数据变更时构建一次，crosshair mousemove 上 O(1) 读数。 */
type ReadoutIndex = {
	readonly seriesValues: readonly ReadonlyMap<number, number | null>[];
	readonly subPaneValues: readonly ReadonlyMap<number, number | null>[];
	readonly volume: ReadonlyMap<number, number | null>;
};

function buildCloseIndex(bars: readonly CockpitBar[]): ReadonlyMap<number, number | null> {
	const index = new Map<number, number | null>();
	for (const bar of bars) {
		if (!index.has(bar.time)) index.set(bar.time, bar.close);
	}
	return index;
}

function buildVolumeIndex(bars: readonly CockpitBar[]): ReadonlyMap<number, number | null> {
	const index = new Map<number, number | null>();
	for (const bar of bars) {
		if (!index.has(bar.time)) index.set(bar.time, bar.volume);
	}
	return index;
}

function buildReadoutIndex(series: readonly CockpitSeriesSpec[], subPanes: readonly CockpitSubPane[]): ReadoutIndex {
	return {
		seriesValues: series.map((spec) => buildCloseIndex(spec.bars)),
		subPaneValues: subPanes.flatMap((pane) => pane.series.map((paneSeries) => buildCloseIndex(paneSeries.points))),
		volume: buildVolumeIndex(series[0]?.bars ?? []),
	};
}

function readoutAtIndex(index: ReadoutIndex, time: number): Readout | null {
	if (index.seriesValues.length === 0 && index.subPaneValues.length === 0) return null;
	return {
		time,
		values: index.seriesValues.map((closeByTime) => closeByTime.get(time) ?? null),
		subValues: index.subPaneValues.map((closeByTime) => closeByTime.get(time) ?? null),
		volume: index.volume.get(time) ?? null,
	};
}

function lastReadoutTime(series: readonly CockpitSeriesSpec[], subPanes: readonly CockpitSubPane[]): number | null {
	const lastBar = lastNonNullClose(series[0]?.bars ?? []);
	if (lastBar) return lastBar.time;
	return subPanes.length > 0 ? (lastNonNullClose(subPanes[0]?.series[0]?.points ?? [])?.time ?? null) : null;
}

function exportIdentity(
	identity: ChartCockpitIdentity,
	asOf: ChartCockpitProps["asOf"],
	nowMs: number,
): ChartExportIdentity {
	let productVersion = "unknown";
	try {
		productVersion = readWebBuildMetadata().productVersion;
	} catch {
		// 无构建元数据注入的环境（纯静态预览）回落 unknown，不阻断导出。
	}
	return {
		asOf: asOf?.time ?? null,
		snapshotId: identity.snapshotId ?? null,
		knowledgeCutoff: identity.knowledgeCutoff ?? null,
		publicationCutoff: identity.publicationCutoff ?? null,
		dataSourceName: identity.dataSourceName,
		productVersion,
		exportedAtMs: nowMs,
	};
}

function downloadBlob(blob: Blob, filename: string): void {
	const url = URL.createObjectURL(blob);
	const anchor = document.createElement("a");
	anchor.href = url;
	anchor.download = filename;
	anchor.click();
	URL.revokeObjectURL(url);
}

export function ChartCockpit(props: ChartCockpitProps) {
	const {
		chartId,
		rangeId,
		ariaLabel,
		series,
		identity,
		showVolumePane = false,
		overlays = EMPTY_OVERLAYS,
		subPanes = EMPTY_SUBPANES,
		bands = EMPTY_BANDS,
		markers = EMPTY_MARKERS,
		initialFocusTime = null,
		asOf = null,
		freshnessFade = false,
		timeVisible = false,
		height = 320,
		nowMs,
		exportName,
	} = props;
	const theme = useChartTheme();
	const hostRef = useRef<HTMLDivElement | null>(null);
	const chartRef = useRef<IChartApi | null>(null);
	const watermarkRef = useRef<AsOfWatermark | null>(null);
	const bandsRef = useRef<PaneBands | null>(null);
	const primarySeriesRef = useRef<ISeriesApi<SeriesType, Time> | null>(null);
	const contentSeriesRef = useRef<ISeriesApi<SeriesType, Time>[]>([]);
	const applyingLinkedRangeRef = useRef(false);
	const applyingLinkedCrosshairRef = useRef(false);
	const propsRef = useRef(props);
	propsRef.current = props;

	const [visibleRangeLabel, setVisibleRangeLabel] = useState("");
	// 读数索引随数据重建一次；mousemove 联动回调经 ref 取最新索引，O(1) 查值。
	const readoutIndex = useMemo(() => buildReadoutIndex(series, subPanes), [series, subPanes]);
	const readoutIndexRef = useRef(readoutIndex);
	readoutIndexRef.current = readoutIndex;
	const initialReadout = useMemo(
		() => readoutAtIndex(readoutIndex, lastReadoutTime(series, subPanes) ?? 0),
		[readoutIndex, series, subPanes],
	);
	// 十字线只锚定时间：读数形状随当前索引派生，数据后到（如基准慢一拍）不会残留旧形状。
	const [readoutTime, setReadoutTime] = useState<number | null>(null);
	const [selection, setSelection] = useState<{ readonly from: number; readonly to: number } | null>(null);
	const activeReadout = readoutTime === null ? initialReadout : readoutAtIndex(readoutIndex, readoutTime);
	// 新鲜度时变的「当前时刻」：注入 nowMs（测试）固定，否则随 30s 心跳推进，
	// 使 live→expired 分档在会话中随数据老化刷新。
	const [effectiveNowMs, setEffectiveNowMs] = useState(() => nowMs ?? Date.now());
	useEffect(() => {
		if (!freshnessFade || nowMs !== undefined) return;
		const timer = window.setInterval(() => setEffectiveNowMs(Date.now()), 30_000);
		return () => window.clearInterval(timer);
	}, [freshnessFade, nowMs]);

	const stale = asOf !== null && effectiveNowMs - asOf.time * 1000 >= FRESHNESS_THRESHOLDS.stale;
	const gaps = useMemo(() => findGapRanges(series[0]?.bars ?? []), [series]);

	const applyLinkedCrosshair = useCallback((time: Time | null) => {
		const chart = chartRef.current;
		if (!chart) return;
		if (time === null) {
			chart.clearCrosshairPosition();
			setReadoutTime(null);
			return;
		}
		const seconds = typeof time === "number" ? time : null;
		if (seconds === null) return;
		const readoutRow = readoutAtIndex(readoutIndexRef.current, seconds);
		const lastValue =
			readoutRow?.values.find((value) => value !== null) ??
			lastNonNullClose(propsRef.current.series[0]?.bars ?? [])?.close;
		if (primarySeriesRef.current && lastValue !== null && lastValue !== undefined) {
			applyingLinkedCrosshairRef.current = true;
			chart.setCrosshairPosition(lastValue, time, primarySeriesRef.current);
			window.setTimeout(() => {
				applyingLinkedCrosshairRef.current = false;
			}, 0);
			if (readoutRow) setReadoutTime(readoutRow.time);
		}
	}, []);

	// 图表实例生命周期：主题/rangeId 变化时整体重建；序列数据由下方内容 effect 填充。
	useEffect(() => {
		const host = hostRef.current;
		if (!host) return;
		const chart = createChart(host, {
			autoSize: true,
			layout: {
				background: { type: ColorType.Solid, color: theme.background },
				textColor: theme.axisText,
				panes: { separatorColor: theme.axisLine, separatorHoverColor: theme.crosshair, enableResize: false },
				attributionLogo: false,
			},
			grid: { vertLines: { color: theme.grid }, horzLines: { color: theme.grid } },
			crosshair: {
				mode: CrosshairMode.Normal,
				vertLine: { color: theme.crosshair, style: LineStyle.Dashed, labelBackgroundColor: theme.axisLine },
				horzLine: { color: theme.crosshair, style: LineStyle.Dashed, labelBackgroundColor: theme.axisLine },
			},
			rightPriceScale: { borderColor: theme.axisLine },
			timeScale: {
				borderColor: theme.axisLine,
				timeVisible,
				secondsVisible: false,
				rightOffset: 4,
			},
		});
		chartRef.current = chart;
		const watermark = new AsOfWatermark({
			time: 0 as Time,
			label: "",
			lineColor: theme.crosshair,
			labelColor: theme.axisText,
		});
		watermarkRef.current = watermark;
		chart.panes()[0]?.attachPrimitive(watermark);
		const paneBands = new PaneBands({ ranges: [] });
		bandsRef.current = paneBands;
		chart.panes()[0]?.attachPrimitive(paneBands);

		const timeScale = chart.timeScale();
		timeScale.subscribeVisibleLogicalRangeChange((range) => {
			if (range) {
				setVisibleRangeLabel(`${range.from.toFixed(1)},${range.to.toFixed(1)}`);
			}
			if (range && !applyingLinkedRangeRef.current) {
				broadcastVisibleRange(rangeId, chartId, range);
			}
		});
		chart.subscribeCrosshairMove((param: MouseEventParams<Time>) => {
			const seconds = typeof param.time === "number" ? param.time : null;
			if (applyingLinkedCrosshairRef.current) return;
			if (seconds === null || !param.point) {
				setReadoutTime(null);
				broadcastCrosshairTime(rangeId, chartId, null);
				return;
			}
			setReadoutTime(seconds);
			broadcastCrosshairTime(rangeId, chartId, param.time ?? null);
		});
		// 点击时点命中事件标记（买卖点）→ 下钻回调；未命中不拦截（保留框选等交互）。
		chart.subscribeClick((param: MouseEventParams<Time>) => {
			const seconds = typeof param.time === "number" ? param.time : null;
			if (seconds === null || !param.point) return;
			const hit = propsRef.current.markers?.find((marker) => marker.time === seconds);
			if (hit) propsRef.current.onMarkerClick?.(hit);
		});

		const leave = joinRangeGroup(rangeId, {
			id: chartId,
			applyVisibleRange: (range: LogicalRange) => {
				const current = timeScale.getVisibleLogicalRange();
				if (current && Math.abs(current.from - range.from) < 0.01 && Math.abs(current.to - range.to) < 0.01) {
					return;
				}
				applyingLinkedRangeRef.current = true;
				timeScale.setVisibleLogicalRange(range);
				window.setTimeout(() => {
					applyingLinkedRangeRef.current = false;
				}, 0);
			},
			onLinkedCrosshair: applyLinkedCrosshair,
		});

		return () => {
			leave();
			chart.remove();
			chartRef.current = null;
			primarySeriesRef.current = null;
			contentSeriesRef.current = [];
			watermarkRef.current = null;
			bandsRef.current = null;
		};
	}, [theme, rangeId, chartId, applyLinkedCrosshair, timeVisible]);

	// 内容 effect：序列/水位线/成交量随数据、新鲜度或主题更新。
	useEffect(() => {
		const chart = chartRef.current;
		if (!chart) return;
		for (const existing of contentSeriesRef.current) {
			chart.removeSeries(existing);
		}
		contentSeriesRef.current = [];

		let primary: ISeriesApi<"Line", Time> | null = null;
		let primaryCandle: ISeriesApi<"Candlestick", Time> | null = null;
		for (const spec of series) {
			if (spec.kind === "candle") {
				// 蜡烛为 EOD 语义：不做 freshness 分段（时变透明度仅用于实时线序列）。
				const candle = chart.addSeries(
					CandlestickSeries,
					{
						upColor: theme.up,
						downColor: theme.down,
						wickUpColor: theme.up,
						wickDownColor: theme.down,
						borderVisible: false,
						priceLineVisible: false,
						lastValueVisible: false,
					},
					0,
				);
				candle.setData(toCandleSeriesData(spec.bars));
				contentSeriesRef.current.push(candle);
				primaryCandle ??= candle;
				continue;
			}
			const baseColor = theme.resolve(spec.color);
			const segments: Array<{ bucket: FreshnessBucket; points: readonly CockpitBar[] }> = freshnessFade
				? splitByFreshness(spec.bars, effectiveNowMs)
				: [{ bucket: "live", points: spec.bars }];
			for (const segment of segments) {
				const line = chart.addSeries(
					LineSeries,
					{
						color: withAlpha(baseColor, theme.freshness[segment.bucket]),
						lineWidth: spec.lineWidth ?? 2,
						priceLineVisible: false,
						lastValueVisible: false,
						crosshairMarkerVisible: true,
						...(spec.priceScaleId ? { priceScaleId: spec.priceScaleId } : {}),
					},
					0,
				);
				line.setData(toLineSeriesData(segment.points));
				contentSeriesRef.current.push(line);
				if (!primary) {
					primary = line;
				}
			}
		}
		primarySeriesRef.current = primary ?? primaryCandle;

		// 主图叠加线（MA/Donchian/净值等）：pane 0，warm-up 断口由 whitespace 语义承载。
		for (const overlay of overlays) {
			const line = chart.addSeries(
				LineSeries,
				{
					color: theme.resolve(overlay.color),
					lineWidth: overlay.lineWidth ?? 1,
					priceLineVisible: false,
					lastValueVisible: false,
					crosshairMarkerVisible: false,
				},
				0,
			);
			line.setData(toLineSeriesData(overlay.points));
			contentSeriesRef.current.push(line);
		}

		let nextPaneIndex = 1;
		const primarySpec = series[0];
		if (showVolumePane && primarySpec) {
			const volume = chart.addSeries(
				HistogramSeries,
				{ priceFormat: { type: "volume" }, priceLineVisible: false, lastValueVisible: false },
				nextPaneIndex,
			);
			volume.setData(
				toVolumeSeriesData(primarySpec.bars, (direction) =>
					withAlpha(theme.resolve(directionColorToken(direction)), 0.55),
				),
			);
			contentSeriesRef.current.push(volume);
			chart.panes()[nextPaneIndex]?.setHeight(VOLUME_PANE_HEIGHT);
			nextPaneIndex += 1;
		}

		// 指标副图（MACD/RSI/ATR 等）：新 pane，与主图共享时间轴与十字线。
		for (const pane of subPanes) {
			for (const paneSeries of pane.series) {
				if (paneSeries.kind === "histogram") {
					const histogram = chart.addSeries(
						HistogramSeries,
						{ priceLineVisible: false, lastValueVisible: false },
						nextPaneIndex,
					);
					histogram.setData(
						toHistogramSeriesData(paneSeries.points, (direction) =>
							withAlpha(theme.resolve(directionColorToken(direction)), 0.6),
						),
					);
					contentSeriesRef.current.push(histogram);
					continue;
				}
				const line = chart.addSeries(
					LineSeries,
					{
						color: theme.resolve(paneSeries.color),
						lineWidth: 2,
						priceLineVisible: false,
						lastValueVisible: false,
						crosshairMarkerVisible: false,
					},
					nextPaneIndex,
				);
				line.setData(toLineSeriesData(paneSeries.points));
				contentSeriesRef.current.push(line);
			}
			chart.panes()[nextPaneIndex]?.setHeight(pane.height ?? SUB_PANE_HEIGHT);
			nextPaneIndex += 1;
		}

		// 主图区间底色（如回撤 peak→trough）：低透明度填充，逐带解析 token。
		bandsRef.current?.updateOptions({
			ranges: bands.map((band) => ({
				from: band.from,
				to: band.to,
				fill: withAlpha(theme.resolve(band.color), 0.12),
			})),
		});

		// 主序列事件标记（买卖点）：buy 在 bar 上方箭头（涨色）、sell 在 bar 下方箭头（跌色）。
		if (primarySeriesRef.current) {
			createSeriesMarkers(
				primarySeriesRef.current,
				[...markers]
					.sort((a, b) => a.time - b.time)
					.map((marker) => ({
						time: marker.time as Time,
						position: marker.direction === "buy" ? "aboveBar" : "belowBar",
						shape: marker.direction === "buy" ? "arrowUp" : "arrowDown",
						color: theme.resolve(directionColorToken(marker.direction === "buy" ? "up" : "down")),
						text: marker.label ?? "",
					})),
			);
		}

		if (asOf) {
			watermarkRef.current?.updateOptions({
				time: asOf.time as Time,
				label: asOf.label ?? `as_of ${formatReadoutTime(asOf.time)}`,
				lineColor: theme.crosshair,
				labelColor: theme.axisText,
			});
		} else {
			watermarkRef.current?.updateOptions({
				time: 0 as Time,
				label: "",
				lineColor: "transparent",
				labelColor: "transparent",
			});
		}

		if (!freshnessFade) {
			const timeScale = chart.timeScale();
			if (initialFocusTime !== null) {
				// 下钻定位：把目标时点滚到可视区中心（约 60 根可见），优先于 fitContent。
				const bars = series[0]?.bars ?? [];
				const index = bars.findIndex((bar) => bar.time === initialFocusTime);
				if (index >= 0) {
					const span = Math.min(60, Math.max(bars.length, 1));
					timeScale.setVisibleLogicalRange({
						from: index - span / 2,
						to: index + span / 2,
					});
				} else {
					timeScale.fitContent();
				}
			} else {
				timeScale.fitContent();
			}
		}
	}, [
		series,
		overlays,
		subPanes,
		bands,
		markers,
		initialFocusTime,
		asOf,
		freshnessFade,
		effectiveNowMs,
		theme,
		showVolumePane,
	]);

	const handleKeyDown = useCallback((event: React.KeyboardEvent<HTMLDivElement>) => {
		const chart = chartRef.current;
		if (!chart) return;
		const timeScale = chart.timeScale();
		const range = timeScale.getVisibleLogicalRange();
		if (!range) return;
		const span = range.to - range.from;
		const step = event.shiftKey ? span * 0.25 : span * 0.1;
		if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
			timeScale.setVisibleLogicalRange({ from: range.from - step, to: range.to - step });
		} else if (event.key === "ArrowRight" || event.key === "ArrowDown") {
			timeScale.setVisibleLogicalRange({ from: range.from + step, to: range.to + step });
		} else if (event.key === "Home") {
			timeScale.setVisibleLogicalRange({ from: -1, to: span - 1 });
		} else if (event.key === "End") {
			const barCount = propsRef.current.series[0]?.bars.length ?? 0;
			timeScale.setVisibleLogicalRange({ from: barCount - span + 1, to: barCount + 1 });
		} else if (event.key === "+" || event.key === "=") {
			const center = (range.from + range.to) / 2;
			const zoomed = span * 0.8;
			timeScale.setVisibleLogicalRange({ from: center - zoomed / 2, to: center + zoomed / 2 });
		} else if (event.key === "-" || event.key === "_") {
			const center = (range.from + range.to) / 2;
			const zoomed = span * 1.25;
			timeScale.setVisibleLogicalRange({ from: center - zoomed / 2, to: center + zoomed / 2 });
		} else {
			return;
		}
		event.preventDefault();
	}, []);

	const handleDoubleClick = useCallback(() => {
		chartRef.current?.timeScale().fitContent();
	}, []);

	// 区间框选缩放（spec 21 §二）：Shift+左键拖拽框选 → 缩放到所选逻辑区间。
	// capture 阶段拦截，避免 lightweight-charts 把同一次拖拽当作平移。
	const selectionRef = useRef<{ from: number; to: number } | null>(null);
	const beginSelection = useCallback((event: React.MouseEvent<HTMLDivElement>) => {
		if (!event.shiftKey || event.button !== 0) return;
		const bounds = event.currentTarget.getBoundingClientRect();
		const x = event.clientX - bounds.left;
		selectionRef.current = { from: x, to: x };
		setSelection({ from: x, to: x });
		event.stopPropagation();
		event.preventDefault();
	}, []);
	const moveSelection = useCallback((event: React.MouseEvent<HTMLDivElement>) => {
		if (selectionRef.current === null) return;
		const bounds = event.currentTarget.getBoundingClientRect();
		const next = { from: selectionRef.current.from, to: event.clientX - bounds.left };
		selectionRef.current = next;
		setSelection(next);
	}, []);
	const finishSelection = useCallback(() => {
		const selectionRect = selectionRef.current;
		selectionRef.current = null;
		setSelection(null);
		const chart = chartRef.current;
		if (!chart || !selectionRect || Math.abs(selectionRect.to - selectionRect.from) < 8) return;
		const timeScale = chart.timeScale();
		const fromLogical = timeScale.coordinateToLogical(Math.min(selectionRect.from, selectionRect.to));
		const toLogical = timeScale.coordinateToLogical(Math.max(selectionRect.from, selectionRect.to));
		if (fromLogical === null || toLogical === null || toLogical <= fromLogical) return;
		timeScale.setVisibleLogicalRange({ from: fromLogical, to: toLogical });
	}, []);
	const cancelSelection = useCallback(() => {
		selectionRef.current = null;
		setSelection(null);
	}, []);

	const handleExportPng = useCallback(() => {
		const chart = chartRef.current;
		if (!chart) return;
		const shot = chart.takeScreenshot();
		const footerLines = buildPngFooterLines(exportIdentity(identity, asOf, nowMs ?? Date.now()));
		const footerHeight = 10 + footerLines.length * 14;
		const canvas = document.createElement("canvas");
		canvas.width = shot.width;
		canvas.height = shot.height + footerHeight;
		const ctx = canvas.getContext("2d");
		if (!ctx) return;
		ctx.fillStyle = theme.background;
		ctx.fillRect(0, 0, canvas.width, canvas.height);
		ctx.drawImage(shot, 0, 0);
		ctx.fillStyle = theme.axisText;
		ctx.font = "11px sans-serif";
		footerLines.forEach((line, index) => {
			ctx.fillText(line, 6, shot.height + 12 + index * 14);
		});
		canvas.toBlob((blob) => {
			if (blob) {
				downloadBlob(blob, `${exportName ?? chartId}.png`);
			}
		}, "image/png");
	}, [identity, asOf, nowMs, theme, chartId, exportName]);

	const handleExportCsv = useCallback(() => {
		const csv = toCsvExport(
			series.map((spec) => ({ id: spec.id, bars: spec.bars })),
			exportIdentity(identity, asOf, nowMs ?? Date.now()),
		);
		downloadBlob(new Blob([csv], { type: "text/csv;charset=utf-8;" }), `${exportName ?? chartId}.csv`);
	}, [series, identity, asOf, nowMs, chartId, exportName]);

	// 副图读数芯片与 subValues 同序（subPanes.flatMap(series)），供图例逐条展示。
	const subPaneChips = subPanes.flatMap((pane) =>
		pane.series.map((paneSeries) => ({ paneSeries, paneLabel: pane.label })),
	);
	const formatValue = (value: number | null | undefined, format?: (value: number) => string): string => {
		if (value === null || value === undefined) return "—";
		return format ? format(value) : String(value);
	};

	return (
		<div className="rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface-1)] p-3">
			<div className="mb-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[var(--text-xs)] text-[var(--color-foreground-secondary)]">
				{series.map((spec, index) => (
					<span key={spec.id} className="inline-flex items-center gap-1.5">
						<span
							aria-hidden="true"
							className="inline-block size-2 rounded-full"
							style={{ background: theme.resolve(spec.color) }}
						/>
						<span className="font-medium">{spec.label ?? spec.id}</span>
						<span className="tabular-nums" data-testid={`chart-readout-${chartId}-${spec.id}`}>
							{activeReadout ? formatValue(activeReadout.values[index], spec.format) : "—"}
						</span>
					</span>
				))}
				{subPaneChips.map(({ paneSeries }, index) => (
					<span key={paneSeries.id} className="inline-flex items-center gap-1.5">
						<span
							aria-hidden="true"
							className="inline-block size-2 rounded-full"
							style={{ background: theme.resolve(paneSeries.color) }}
						/>
						<span className="font-medium">{paneSeries.label ?? paneSeries.id}</span>
						<span className="tabular-nums" data-testid={`chart-readout-${chartId}-${paneSeries.id}`}>
							{activeReadout ? formatValue(activeReadout.subValues[index], paneSeries.format) : "—"}
						</span>
					</span>
				))}
				{activeReadout && (
					<span className="tabular-nums">
						{formatReadoutTime(activeReadout.time)}
						{activeReadout.volume !== null && ` · vol ${activeReadout.volume}`}
					</span>
				)}
				{asOf && (
					<span className="inline-flex items-center gap-1.5">
						<StaleIndicator isStale={stale} />
						<span className="tabular-nums">as_of {formatReadoutTime(asOf.time)}</span>
					</span>
				)}
				{gaps.length > 0 && (
					<span className="tabular-nums" data-testid={`chart-gaps-${chartId}`}>
						{gaps.length > 1 ? `缺口 ${gaps.length} 处 · 首处 ` : "缺口 "}
						{formatReadoutTime(gaps[0]!.from)} → {formatReadoutTime(gaps[0]!.to)}
					</span>
				)}
				<span className="ml-auto inline-flex items-center gap-1.5">
					<Button
						variant="outline"
						size="xs"
						type="button"
						data-testid={`chart-export-png-${chartId}`}
						onClick={handleExportPng}
					>
						PNG
					</Button>
					<Button
						variant="outline"
						size="xs"
						type="button"
						data-testid={`chart-export-csv-${chartId}`}
						onClick={handleExportCsv}
					>
						CSV
					</Button>
				</span>
			</div>
			<div
				ref={hostRef}
				role="img"
				// biome-ignore lint/a11y/noNoninteractiveTabindex: 图表宿主必须可聚焦以承载键盘平移/缩放/首尾跳转（图表交互合同）。
				tabIndex={0}
				aria-label={ariaLabel}
				className="relative w-full touch-none rounded-[var(--radius-md)] outline-none focus-visible:ring-3 focus-visible:ring-(--color-focus-ring)"
				style={{ height }}
				data-chart-interaction-contract={chartId}
				data-chart-affordances={AFFORDANCES}
				data-chart-linked-time-range={rangeId}
				data-chart-panes={1 + (showVolumePane ? 1 : 0) + subPanes.length}
				data-chart-visible-range={visibleRangeLabel}
				data-chart-as-of={asOf ? String(asOf.time) : undefined}
				data-chart-marker-times={markers.length > 0 ? markers.map((marker) => marker.time).join(",") : undefined}
				onKeyDown={handleKeyDown}
				onDoubleClick={handleDoubleClick}
				onMouseDownCapture={beginSelection}
				onMouseMove={moveSelection}
				onMouseUp={finishSelection}
				onMouseLeave={cancelSelection}
			>
				{selection && (
					<div
						data-testid={`chart-selection-${chartId}`}
						aria-hidden="true"
						className="pointer-events-none absolute inset-y-0 border border-[var(--chart-crosshair)] bg-[var(--chart-crosshair)]"
						style={{
							left: Math.min(selection.from, selection.to),
							width: Math.abs(selection.to - selection.from),
						}}
					/>
				)}
			</div>
			{/* 读数时间/缺口/键盘提示用条内已审计的 secondary 色：quaternary 在 surface-1 上 4.38:1 跌穿 AA */}
			<p className="mt-1.5 text-[var(--text-xs)] text-[var(--color-foreground-secondary)]">
				键盘：←/→ 平移 · ↑/↓ 粗平移 · +/− 缩放 · Home/End 首尾 · Shift+拖拽框选缩放 · 双击复位；断口 =
				数据缺失（不插值）
			</p>
		</div>
	);
}
