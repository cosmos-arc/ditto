import { useMemo, useState } from "react";
import { ChartCockpit, type CockpitOverlay } from "@/components/chart";
import { type BarPeriod, resampleBars } from "@/components/chart/cockpit/chart-data";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { ContextSection } from "@/components/domain";
import { ErrorState } from "@/lib/error-boundary";
import { StaleIndicator } from "@/lib/stale-indicator";
import type { OverlayKind } from "../api/indicator-overlays";
import type { BarAdjustment } from "../api/instrument-workspace";
import { useEtfNav, useIndicatorSeries, useInstrumentChart, useInstrumentDetail } from "../hooks";
import {
	BAR_PERIOD_OPTIONS,
	barsAgeDays,
	findCalendarGaps,
	formatTradeDate,
	primaryAnswerFromBars,
	toCockpitBars,
	tradeDateToUnix,
} from "../lib/chart-mapping";
import {
	type IndicatorToggles,
	indicatorOverlays,
	indicatorSubPanes,
	readIndicatorToggles,
	writeIndicatorToggles,
} from "../lib/indicator-overlays";

interface InstrumentChartViewProps {
	readonly id: string;
}

/** 数据级陈旧阈值：最近一根 bar 距今超过 7 个自然日视为 stale。 */
const STALE_AFTER_DAYS = 7;

const ADJUSTMENT_OPTIONS: ReadonlyArray<{ readonly value: BarAdjustment; readonly label: string }> = [
	{ value: "none", label: "原始" },
	{ value: "qfq", label: "前复权" },
	{ value: "hfq", label: "后复权" },
];

function dateDaysAgo(days: number): string {
	const date = new Date();
	date.setDate(date.getDate() - days);
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

export function InstrumentChartView({ id }: InstrumentChartViewProps) {
	const [period, setPeriod] = useState<BarPeriod>("daily");
	const [adjustment, setAdjustment] = useState<BarAdjustment>("none");
	const [includeExperimental, setIncludeExperimental] = useState(false);
	const [startDate, setStartDate] = useState(() => dateDaysAgo(365));
	const [endDate, setEndDate] = useState(() => new Date().toISOString().slice(0, 10));
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

	const bars = useMemo(() => (query.data ? toCockpitBars(query.data) : []), [query.data]);
	const displayBars = useMemo(() => resampleBars(bars, period), [bars, period]);
	const answer = useMemo(() => primaryAnswerFromBars(bars), [bars]);
	const ageDays = useMemo(() => barsAgeDays(bars, Date.now()), [bars]);
	const stale = ageDays !== null && ageDays > STALE_AFTER_DAYS;
	// API Bar 合同不携带 null OHLC：partial 以日线日历缺口表达（缺失交易日区间）。
	const calendarGaps = useMemo(() => findCalendarGaps(bars), [bars]);
	const firstGap = calendarGaps[0];

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

	const experimentalBlocked =
		query.isError && String((query.error as Error | null)?.message ?? "").includes("experimental");

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
						快照标识未由接口提供，仅作研究浏览，不生成交易建议
					</div>
				</div>

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
						{stale && (
							<span className="inline-flex items-center gap-1.5 text-xs text-(--color-foreground-tertiary)">
								<StaleIndicator isStale />
								数据延迟 {ageDays} 天
							</span>
						)}
						{firstGap && (
							<span
								className="tabular-nums text-xs text-(--color-foreground-muted)"
								data-testid={`chart-gaps-${id}`}
								data-state="bars-partial"
							>
								{calendarGaps.length > 1 ? `缺口 ${calendarGaps.length} 处 · 首处 ` : "缺口 "}
								{formatTradeDate(firstGap.from)} → {formatTradeDate(firstGap.to)}
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
				{query.data?.length === 0 && (
					<div className="p-10 text-center text-sm text-(--color-foreground-tertiary)">
						所选日期范围没有可见行情；可放宽日期范围或在数据看台确认该标的的摄取覆盖。
					</div>
				)}
				{displayBars.length > 0 && (
					<div className="p-3">
						<ChartCockpit
							chartId={`instrument-candles-${id}`}
							rangeId={`instrument-${id}`}
							ariaLabel={`${detail.data?.name ?? id} ${period === "daily" ? "日" : period === "weekly" ? "周" : "月"}K 线（${effectiveAdjustment === "none" ? "原始价" : effectiveAdjustment === "qfq" ? "前复权" : "后复权"}），含成交量`}
							series={[{ id: "ohlc", kind: "candle", color: "var(--chart-series-neutral)", bars: displayBars }]}
							overlays={navOverlay ? [...indicatorOverlaysList, navOverlay] : indicatorOverlaysList}
							subPanes={indicatorSubPaneList}
							showVolumePane
							height={360}
							identity={{
								dataSourceName: "本地市场库（tushare/tdx 摄取）",
								knowledgeCutoff: null,
								publicationCutoff: null,
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
