import {
	ColorType,
	CrosshairMode,
	createChart,
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
	toCsvExport,
	toLineSeriesData,
	toVolumeSeriesData,
} from "./chart-data";
import { useChartTheme } from "./chart-theme";
import { broadcastCrosshairTime, broadcastVisibleRange, joinRangeGroup } from "./cockpit-link";

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
	readonly bars: readonly CockpitBar[];
	/** CSS token 引用，如 "var(--chart-run-1)"（canvas 经 useChartTheme 解析）。 */
	readonly color: string;
	readonly lineWidth?: 1 | 2 | 3 | 4;
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
const AFFORDANCES = "crosshair tooltip zoom-pan linked-time-range";

type Readout = {
	readonly time: number;
	readonly values: readonly (number | null)[];
	readonly volume: number | null;
};

function readoutAt(series: readonly CockpitSeriesSpec[], time: number): Readout | null {
	if (series.length === 0) return null;
	const values = series.map((spec) => spec.bars.find((bar) => bar.time === time)?.close ?? null);
	const volume = series[0]?.bars.find((bar) => bar.time === time)?.volume ?? null;
	return { time, values, volume };
}

function lastReadout(series: readonly CockpitSeriesSpec[]): Readout | null {
	const lastBar = lastNonNullClose(series[0]?.bars ?? []);
	if (!lastBar) return null;
	return readoutAt(series, lastBar.time);
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
	const primarySeriesRef = useRef<ISeriesApi<"Line", Time> | null>(null);
	const contentSeriesRef = useRef<ISeriesApi<SeriesType, Time>[]>([]);
	const applyingLinkedRangeRef = useRef(false);
	const applyingLinkedCrosshairRef = useRef(false);
	const propsRef = useRef(props);
	propsRef.current = props;

	const [visibleRangeLabel, setVisibleRangeLabel] = useState("");
	const [readout, setReadout] = useState<Readout | null>(() => lastReadout(series));
	const [selection, setSelection] = useState<{ readonly from: number; readonly to: number } | null>(null);
	const fallbackReadout = useMemo(() => lastReadout(series), [series]);
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
			setReadout(null);
			return;
		}
		const seconds = typeof time === "number" ? time : null;
		if (seconds === null) return;
		const readoutRow = readoutAt(propsRef.current.series, seconds);
		const lastValue =
			readoutRow?.values.find((value) => value !== null) ??
			lastNonNullClose(propsRef.current.series[0]?.bars ?? [])?.close;
		if (primarySeriesRef.current && lastValue !== null && lastValue !== undefined) {
			applyingLinkedCrosshairRef.current = true;
			chart.setCrosshairPosition(lastValue, time, primarySeriesRef.current);
			window.setTimeout(() => {
				applyingLinkedCrosshairRef.current = false;
			}, 0);
			if (readoutRow) setReadout(readoutRow);
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
				setReadout(null);
				broadcastCrosshairTime(rangeId, chartId, null);
				return;
			}
			setReadout(readoutAt(propsRef.current.series, seconds));
			broadcastCrosshairTime(rangeId, chartId, param.time ?? null);
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
		for (const spec of series) {
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
		primarySeriesRef.current = primary;

		const primarySpec = series[0];
		if (showVolumePane && primarySpec) {
			const volume = chart.addSeries(
				HistogramSeries,
				{ priceFormat: { type: "volume" }, priceLineVisible: false, lastValueVisible: false },
				1,
			);
			volume.setData(
				toVolumeSeriesData(primarySpec.bars, (direction) =>
					withAlpha(theme.resolve(directionColorToken(direction)), 0.55),
				),
			);
			contentSeriesRef.current.push(volume);
			chart.panes()[1]?.setHeight(VOLUME_PANE_HEIGHT);
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
			chart.timeScale().fitContent();
		}
	}, [series, asOf, freshnessFade, effectiveNowMs, theme, showVolumePane]);

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

	const activeReadout = readout ?? fallbackReadout;

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
						<span className="font-medium">{spec.id}</span>
						<span className="tabular-nums">{activeReadout ? (activeReadout.values[index] ?? "—") : "—"}</span>
					</span>
				))}
				{activeReadout && (
					<span className="tabular-nums text-[var(--color-foreground-muted)]">
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
					<span className="tabular-nums text-[var(--color-foreground-muted)]" data-testid={`chart-gaps-${chartId}`}>
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
				data-chart-visible-range={visibleRangeLabel}
				data-chart-as-of={asOf ? String(asOf.time) : undefined}
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
			<p className="mt-1.5 text-[var(--text-xs)] text-[var(--color-foreground-muted)]">
				键盘：←/→ 平移 · ↑/↓ 粗平移 · +/− 缩放 · Home/End 首尾 · Shift+拖拽框选缩放 · 双击复位；断口 =
				数据缺失（不插值）
			</p>
		</div>
	);
}
