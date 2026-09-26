import { useMemo, useState } from "react";
import { ChartCockpit, type CockpitMarker, type CockpitOverlay } from "@/components/chart";
import type { BarPeriod } from "@/components/chart/cockpit/chart-data";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { ContextSection } from "@/components/domain";
import { ErrorState } from "@/lib/error-boundary";
import { StaleIndicator } from "@/lib/stale-indicator";
import type { OverlayKind } from "../api/indicator-overlays";
import type { BarAdjustment } from "../api/instrument-workspace";
import { useEtfNav, useIndicatorSeries, useInstrumentChart, useInstrumentDetail } from "../hooks";
import { BAR_PERIOD_OPTIONS, primaryAnswerFromBars, toCockpitBars, tradeDateToUnix } from "../lib/chart-mapping";
import {
	type IndicatorToggles,
	indicatorOverlays,
	indicatorSubPanes,
	readIndicatorToggles,
	writeIndicatorToggles,
} from "../lib/indicator-overlays";
import type { InstrumentDrillContext } from "../types";

interface InstrumentChartViewProps {
	readonly id: string;
	/** 回测买卖点下钻上下文：定位日滚入可视中心 + 买卖 marker + as_of 水位线。 */
	readonly drill?: InstrumentDrillContext | undefined;
}

const ADJUSTMENT_OPTIONS: ReadonlyArray<{ readonly value: BarAdjustment; readonly label: string }> = [
	{ value: "none", label: "原始" },
	{ value: "qfq", label: "前复权" },
	{ value: "hfq", label: "后复权" },
];

function dateDaysAgo(days: number): string {
	const date = new Date(Date.now() + 8 * 60 * 60 * 1000);
	date.setUTCDate(date.getUTCDate() - days);
	return date.toISOString().slice(0, 10);
}

function formatSigned(value: number, digits = 2): string {
	const sign = value > 0 ? "+" : value < 0 ? "−" : "";
	return `${sign}${Math.abs(value).toFixed(digits)}`;
}

function SegmentedControl<T extends string>({
	label,
	options,
	value,
	onChange,
	disabled = false,
	note,
}: {
	readonly label: string;
	readonly options: ReadonlyArray<{ readonly value: T; readonly label: string }>;
	readonly value: T;
	readonly onChange: (value: T) => void;
	readonly disabled?: boolean | undefined;
	readonly note?: string | undefined;
}) {
	return (
		<div className="flex items-center gap-2" data-testid={`chart-${label}-control`}>
			<span className="text-xs text-(--color-foreground-tertiary)">{label}</span>
			<div className="inline-flex overflow-hidden rounded-md border border-(--color-border-primary)">
				{options.map((option) => (
					<button
						key={option.value}
						type="button"
						aria-pressed={option.value === value}
						disabled={disabled}
						onClick={() => onChange(option.value)}
						className={`px-2.5 py-1 text-xs whitespace-nowrap transition-colors disabled:pointer-events-none disabled:opacity-50 ${
							option.value === value
								? "bg-(--color-interaction-active-bg) text-(--color-foreground)"
								: "bg-(--color-surface-1) text-(--color-foreground-secondary) hover:bg-(--color-interaction-hover-subtle-bg)"
						}`}
					>
						{option.label}
					</button>
				))}
			</div>
			{note && <span className="text-xs text-(--color-foreground-muted)">{note}</span>}
		</div>
	);
}

export function InstrumentChartView({ id, drill }: InstrumentChartViewProps) {
	const [period, setPeriod] = useState<BarPeriod>("daily");
	const [adjustment, setAdjustment] = useState<BarAdjustment>("none");
	const [includeExperimental, setIncludeExperimental] = useState(false);
	const [startDate, setStartDate] = useState(() => dateDaysAgo(365));
	const [endDate, setEndDate] = useState(() => dateDaysAgo(0));
	const [toggles, setToggles] = useState<IndicatorToggles>(() => readIndicatorToggles());
	const updateToggle = (key: keyof IndicatorToggles, value: boolean) => {
		setToggles((previous) => {
			const next = { ...previous, [key]: value };
			writeIndicatorToggles(next);
			return next;
		});
	};

	const detail = useInstrumentDetail(id);
	// ETF 复权在服务端 bars 查询未接线（apply_adjustment 仅覆盖股票）：
	// 诚实降级为禁用复权切换，不静默返回未复权价格冒充已复权。
	const isEtf = detail.data?.asset_class === "etf";
	const effectiveAdjustment: BarAdjustment = isEtf ? "none" : adjustment;

	const query = useInstrumentChart(id, {
		adjustment: effectiveAdjustment,
		allowExperimental: includeExperimental,
		endDate,
		startDate,
		period,
	});

	// 指标序列口径为日线（周/月指标窗口语义不同，不近似换算）。
	const indicatorKinds = useMemo(() => {
		const kinds: OverlayKind[] = [];
		if (toggles.ma || toggles.donchian) kinds.push("ma", "donchian");
		if (toggles.macd) kinds.push("macd");
		if (toggles.rsi) kinds.push("rsi");
		if (toggles.atr) kinds.push("atr");
		return kinds;
	}, [toggles]);
	const indicatorsEnabled = period === "daily" && indicatorKinds.length > 0;
	const indicatorQuery = useIndicatorSeries(id, {
		adjustment: effectiveAdjustment,
		allowExperimental: includeExperimental,
		endDate,
		indicators: indicatorKinds,
		startDate,
	});
	const navQuery = useEtfNav(id, { startDate, endDate });

	const bars = useMemo(() => (query.data ? toCockpitBars(query.data.bars) : []), [query.data]);
	const displayBars = bars;
	const answer = useMemo(() => primaryAnswerFromBars(bars), [bars]);
	const latestBar = query.data?.bars.at(-1);
	const stale = query.data?.stale_reason != null;
	const missingSessions = query.data?.missing_sessions ?? [];
	const partial = query.data?.bars.some((bar) => bar.partial) ?? false;

	const indicatorOverlaysList = useMemo(
		() => (indicatorsEnabled && indicatorQuery.data ? indicatorOverlays(indicatorQuery.data, toggles) : []),
		[indicatorQuery.data, indicatorsEnabled, toggles],
	);
	const indicatorSubPaneList = useMemo(
		() => (indicatorsEnabled && indicatorQuery.data ? indicatorSubPanes(indicatorQuery.data, toggles) : []),
		[indicatorQuery.data, indicatorsEnabled, toggles],
	);
	const navPoints = navQuery.data?.points ?? [];
	const navOverlay = useMemo<CockpitOverlay | null>(() => {
		if (!isEtf || !toggles.nav || navPoints.length === 0) return null;
		return {
			id: "etf-nav",
			color: "var(--chart-combo-manual)",
			lineWidth: 2,
			points: navPoints.map((point: { nav_date: string; nav: number }) => ({
				time: tradeDateToUnix(point.nav_date),
				close: point.nav,
				volume: null,
			})),
		};
	}, [isEtf, navPoints, toggles.nav]);
	const navUnavailable = isEtf && toggles.nav && !navQuery.isLoading && navPoints.length === 0;
	const overlayShown = indicatorOverlaysList.length > 0 || indicatorSubPaneList.length > 0 || navOverlay !== null;

	const experimentalBlocked =
		query.isError && String((query.error as Error | null)?.message ?? "").includes("experimental");

	// 下钻定位（跨域跳转合同）：日线锚定 marker + as_of 水位线；周/月重采样不承载 marker 语义。
	const drillTime = drill ? tradeDateToUnix(drill.date) : null;
	const drillMarkers = useMemo<readonly CockpitMarker[]>(
		() =>
			drill && drillTime !== null && period === "daily"
				? [
						{
							id: `drill-${drill.runId}-${drill.date}-${drill.direction}`,
							time: drillTime,
							direction: drill.direction,
							label: `${drill.direction === "buy" ? "买入" : "卖出"} · ${drill.runId}`,
						},
					]
				: [],
		[drill, drillTime, period],
	);
	const drillAsOf = useMemo(
		() =>
			drill && drill.asOf
				? {
						time: tradeDateToUnix(drill.asOf.slice(0, 10)),
						label: `as_of ${drill.asOf.slice(0, 10)} · 回测下钻 ${drill.runId}`,
					}
				: null,
		[drill],
	);

	return (
		<div className="p-[var(--density-panel-padding)]">
			<ContextSection title="行情图表">
				<div
					className="flex flex-wrap items-end justify-between gap-3 border-b border-(--color-border-subtle) p-3"
					data-info-unit="instrument-chart-toolbar"
				>
					<div className="flex flex-wrap items-center gap-4">
						<SegmentedControl label="周期" options={BAR_PERIOD_OPTIONS} value={period} onChange={setPeriod} />
						<SegmentedControl
							label="复权"
							options={ADJUSTMENT_OPTIONS}
							value={effectiveAdjustment}
							onChange={setAdjustment}
							disabled={isEtf}
							note={isEtf ? "ETF 复权暂未接入" : undefined}
						/>
						<label className="flex items-center gap-1.5 text-xs text-(--color-foreground-tertiary)">
							<input
								type="checkbox"
								checked={includeExperimental}
								onChange={(event) => setIncludeExperimental(event.currentTarget.checked)}
								data-testid="chart-experimental-toggle"
							/>
							含 experimental 数据
						</label>
						<label className="grid gap-1 text-xs text-(--color-foreground-tertiary)">
							开始日期
							<input
								type="date"
								value={startDate}
								onChange={(event) => setStartDate(event.currentTarget.value)}
								className="rounded-md border border-(--color-border-primary) bg-(--color-surface-1) px-2 py-1.5 text-sm text-(--color-foreground)"
							/>
						</label>
						<label className="grid gap-1 text-xs text-(--color-foreground-tertiary)">
							截至日期
							<input
								type="date"
								value={endDate}
								onChange={(event) => setEndDate(event.currentTarget.value)}
								className="rounded-md border border-(--color-border-primary) bg-(--color-surface-1) px-2 py-1.5 text-sm text-(--color-foreground)"
							/>
						</label>
					</div>
					<div className="max-w-lg text-right text-xs leading-5 text-(--color-foreground-tertiary)">
						复权：{effectiveAdjustment} · experimental：{includeExperimental ? "开" : "关"}
						<br />
						{query.data
							? `决策 ${query.data.as_of} · 可得截止 ${query.data.knowledge_cutoff} · 发布截止 ${query.data.publication_cutoff}`
							: "读取图表来源中"}
						<br />
						{query.data
							? `来源 ${query.data.sources.join(", ")} · 快照 ${query.data.source_snapshot_ids.join(", ")} · 日历 ${query.data.calendar_snapshot_ids.join(", ")}`
							: ""}
					</div>
				</div>

				{drill && (
					<div
						data-state="drill-focus"
						data-testid={`drill-focus-${id}`}
						className="flex flex-wrap items-center gap-x-4 gap-y-1 border-b border-(--color-border-subtle) bg-(--color-interaction-hover-subtle-bg) px-3 py-2 text-xs"
					>
						<span className="font-medium text-(--color-foreground)">回测买卖点下钻</span>
						<span className="font-data text-(--color-foreground-secondary)">
							{drill.direction === "buy" ? "买入" : "卖出"} · {drill.date}
						</span>
						<span className="font-data text-(--color-foreground-tertiary)">run {drill.runId}</span>
						<span className="font-data text-(--color-foreground-tertiary)">as_of {drill.asOf || "—"}</span>
						<span className="text-(--color-foreground-muted)">决策线为源 run as_of；K 线按当前图表来源截止</span>
					</div>
				)}

				<div
					className="flex flex-wrap items-center gap-x-4 gap-y-1.5 border-b border-(--color-border-subtle) px-3 py-2"
					data-info-unit="instrument-chart-indicators"
				>
					<span className="text-xs text-(--color-foreground-tertiary)">指标</span>
					{(
						[
							["ma", "MA(5/20/60)"],
							["donchian", "DON(20)"],
							["macd", "MACD"],
							["rsi", "RSI"],
							["atr", "ATR"],
						] as const
					).map(([key, label]) => (
						<label key={key} className="flex items-center gap-1.5 text-xs text-(--color-foreground-secondary)">
							<input
								type="checkbox"
								checked={toggles[key]}
								disabled={period !== "daily"}
								onChange={(event) => updateToggle(key, event.currentTarget.checked)}
								data-testid={`indicator-toggle-${key}`}
							/>
							{label}
						</label>
					))}
					{isEtf && (
						<label className="flex items-center gap-1.5 text-xs text-(--color-foreground-secondary)">
							<input
								type="checkbox"
								checked={toggles.nav}
								onChange={(event) => updateToggle("nav", event.currentTarget.checked)}
								data-testid="indicator-toggle-nav"
							/>
							净值
						</label>
					)}
					{period !== "daily" && <span className="text-xs text-(--color-foreground-muted)">指标叠加仅日线周期</span>}
					{navUnavailable && (
						<span
							data-state="nav-unavailable"
							className="text-xs text-(--color-foreground-muted)"
							title="本地净值库无该标的数据（etf_nav 摄取未覆盖）"
						>
							净值数据不可得
						</span>
					)}
					{overlayShown && (
						<span className="text-xs text-(--color-foreground-muted)">叠加线来源未绑定；CSV 仅含 K 线</span>
					)}
				</div>

				{answer && (
					<div data-primary-answer className="flex flex-wrap items-baseline gap-x-6 gap-y-1 px-3 py-2.5 text-sm">
						<span data-answer-metric className="text-[var(--text-lg)] font-semibold tabular-nums">
							{answer.close.toFixed(2)}
						</span>
						<span
							data-answer-metric
							className={`tabular-nums font-medium ${
								answer.direction === "up"
									? "text-(--color-market-up)"
									: answer.direction === "down"
										? "text-(--color-market-down)"
										: "text-(--color-foreground-secondary)"
							}`}
						>
							{answer.change !== null ? formatSigned(answer.change) : "—"}{" "}
							{answer.changePercent !== null ? `(${formatSigned(answer.changePercent)}%)` : ""}
						</span>
						<span data-answer-scope className="tabular-nums text-xs text-(--color-foreground-tertiary)">
							{answer.tradeDate} 收盘 · 区间 {answer.windowLow.toFixed(2)}–{answer.windowHigh.toFixed(2)}
						</span>
						{latestBar && (
							<span className="tabular-nums text-xs text-(--color-foreground-tertiary)">
								价格可得 {latestBar.available_at} · 发布 {latestBar.published_at}
							</span>
						)}
						{partial && (
							<span data-state="bars-partial" className="text-xs">
								部分周期不完整
							</span>
						)}
					</div>
				)}

				{(stale || missingSessions.length > 0) && (
					<div className="flex flex-wrap items-baseline gap-x-6 gap-y-1 px-3 py-2.5 text-sm">
						{stale && (
							<span className="inline-flex items-center gap-1.5 text-xs text-(--color-foreground-tertiary)">
								<StaleIndicator isStale />
								最新价格日 {query.data?.latest_price_date ?? "—"} ·{" "}
								{query.data?.stale_reason === "missing_expected_session" ? "交易日价格缺失" : "当前没有可见价格"}
							</span>
						)}
						{missingSessions.length > 0 && (
							<span
								className="tabular-nums text-xs text-(--color-foreground-muted)"
								data-testid={`chart-gaps-${id}`}
								data-state="bars-partial"
							>
								缺失交易日 {missingSessions.join("、")}
							</span>
						)}
					</div>
				)}

				{query.isLoading && <LoadingSkeleton variant="chart" />}
				{query.isError && !experimentalBlocked && <ErrorState onRetry={() => void query.refetch()} />}
				{experimentalBlocked && (
					<div
						data-state="experimental-disabled"
						className="m-3 rounded-md border border-(--color-border-primary) bg-(--color-surface-1) p-4 text-sm text-(--color-foreground-secondary)"
					>
						该资产类别行情数据集尚未晋级（experimental 成熟度门控，fail closed）。
						<br />
						勾选「含 experimental 数据」仅用于显式研究浏览；晋级治理见数据成熟度看板。
						<ButtonLikeRetry onClick={() => void query.refetch()} />
					</div>
				)}
				{query.data?.bars.length === 0 && (
					<div className="p-10 text-center text-sm text-(--color-foreground-tertiary)">
						所选日期范围没有可见行情；可放宽日期范围或在数据看台确认该标的的摄取覆盖。
					</div>
				)}
				{query.data && (
					<div className="p-3">
						<ChartCockpit
							chartId={`instrument-candles-${id}`}
							rangeId={`instrument-${id}`}
							ariaLabel={`${detail.data?.name ?? id} ${period === "daily" ? "日" : period === "weekly" ? "周" : "月"}K 线（${effectiveAdjustment === "none" ? "原始价" : effectiveAdjustment === "qfq" ? "前复权" : "后复权"}），含成交量`}
							series={[{ id: "ohlc", kind: "candle", color: "var(--chart-series-neutral)", bars: displayBars }]}
							overlays={navOverlay ? [...indicatorOverlaysList, navOverlay] : indicatorOverlaysList}
							subPanes={indicatorSubPaneList}
							markers={drillMarkers}
							initialFocusTime={drillTime}
							asOf={
								drillAsOf ?? {
									time: Date.parse(query.data.as_of) / 1000,
									label: `行情决策 ${query.data.as_of}`,
								}
							}
							showVolumePane
							height={360}
							identity={{
								dataSourceName: `K线 ${query.data?.sources.join(", ") ?? ""}${overlayShown ? "；叠加线来源未绑定" : ""}`,
								asOfIso: query.data?.as_of ?? null,
								snapshotId: query.data?.source_snapshot_ids.join(",") ?? null,
								calendarSnapshotIds: query.data?.calendar_snapshot_ids.join(",") ?? null,
								missingSessions,
								knowledgeCutoff: query.data?.knowledge_cutoff ?? null,
								publicationCutoff: query.data?.publication_cutoff ?? null,
								adjustment: effectiveAdjustment,
								period,
							}}
							exportName={`instrument-${id}-${period}`}
						/>
					</div>
				)}
			</ContextSection>
		</div>
	);
}

function ButtonLikeRetry({ onClick }: { readonly onClick: () => void }) {
	return (
		<button
			type="button"
			onClick={onClick}
			className="mt-3 rounded-md border border-(--color-border-primary) bg-(--color-surface-1) px-3 py-1.5 text-xs text-(--color-foreground-secondary) hover:bg-(--color-interaction-hover-subtle-bg)"
		>
			重试
		</button>
	);
}
