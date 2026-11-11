import { useMemo, useState } from "react";
import { ChartCockpit, type CockpitMarker, type CockpitOverlay } from "@/components/chart";
import type { BarPeriod, CockpitBar } from "@/components/chart/cockpit/chart-data";
import { LoadingSkeleton } from "@/components/data/skeleton/loading-skeleton";
import { ContextSection } from "@/components/domain";
import { ErrorState } from "@/lib/error-boundary";
import { dateYearsBefore, isValidIsoCalendarDate } from "@/lib/iso-calendar-date";
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
	/**
	 * 观察日锚点（如自选/筛选带入）：合法 YYYY-MM-DD 时成为初始截至日期，
	 * 使 K 线 Primary Answer 与来源观察面同日同口径；非法值忽略。
	 */
	readonly observeDate?: string | undefined;
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

export function InstrumentChartView({ id, drill, observeDate }: InstrumentChartViewProps) {
	// 观察日锚点：来自观察面（自选等）的合法日期成为初始截至日期；与图表
	// 默认窗口同一状态位，用户手动改期即覆盖锚点（不锁死后续分析）。
	// 观察日经 Date 往返校验：正则放行的假日期（如 2026-13-45）会让
	// 日期算术抛 RangeError 炸掉整页，两层（route + view）同规则拒绝。
	const anchoredEndDate = observeDate !== undefined && isValidIsoCalendarDate(observeDate) ? observeDate : null;
	const [period, setPeriod] = useState<BarPeriod>("daily");
	const [adjustment, setAdjustment] = useState<BarAdjustment>("none");
	const [includeExperimental, setIncludeExperimental] = useState(false);
	const [startDate, setStartDate] = useState(() =>
		anchoredEndDate ? dateYearsBefore(anchoredEndDate, 1) : dateDaysAgo(365),
	);
	const [endDate, setEndDate] = useState(() => anchoredEndDate ?? dateDaysAgo(0));
	const [toggles, setToggles] = useState<IndicatorToggles>(() => readIndicatorToggles());
	const updateToggle = (key: keyof IndicatorToggles, value: boolean) => {
		setToggles((previous) => {
			const next = { ...previous, [key]: value };
			writeIndicatorToggles(next);
			return next;
		});
	};

	const detail = useInstrumentDetail(id);
	// ETF 复权已接入服务端留存 payload 链（fund_adj，批次3）——
	// 股票/ETF 同一复权切换，缺因子由服务端 fail closed 而非前端静默降级。
	const isEtf = detail.data?.asset_class === "etf";
	const effectiveAdjustment: BarAdjustment = adjustment;

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
	// 缺失会话补 whitespace 点：chart engine 只对 close === null 的 bar 渲染
	// 断口，服务端 missing_sessions 若不合并会相邻连线（合同：缺口不插值）。
	// 日频按天补点；周/月频只在整桶无 bar 时补一个点，桶内有 bar 的缺口由
	// 服务端 partial 语义表达，客户端不能再拆 candle。
	const displayBars = useMemo(() => {
		if (!query.data) return bars;
		const missing = query.data.missing_sessions;
		if (missing.length === 0) return bars;
		if (period === "daily") {
			const present = new Set(bars.map((bar) => bar.time));
			const holes: CockpitBar[] = missing
				.filter((day) => !present.has(tradeDateToUnix(day)))
				.map((day) => ({ time: tradeDateToUnix(day), close: null, volume: null }));
			return [...bars, ...holes].sort((left, right) => left.time - right.time);
		}
		const bucketOf = (unix: number): string => {
			const date = new Date(unix * 1000);
			if (period === "weekly") {
				const monday = new Date(date);
				monday.setUTCDate(monday.getUTCDate() - ((monday.getUTCDay() + 6) % 7));
				return `w${monday.getUTCFullYear()}-${monday.getUTCMonth() + 1}-${monday.getUTCDate()}`;
			}
			return `m${date.getUTCFullYear()}-${date.getUTCMonth() + 1}`;
		};
		const populated = new Set(bars.map((bar) => bucketOf(bar.time)));
		const emptyBuckets = new Map<string, number>();
		for (const day of missing) {
			const time = tradeDateToUnix(day);
			const bucket = bucketOf(time);
			if (populated.has(bucket)) continue;
			const current = emptyBuckets.get(bucket);
			if (current === undefined || time > current) emptyBuckets.set(bucket, time);
		}
		const holes: CockpitBar[] = [...emptyBuckets.values()].map((time) => ({
			time,
			close: null,
			volume: null,
		}));
		return [...bars, ...holes].sort((left, right) => left.time - right.time);
	}, [bars, period, query.data]);
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
	const navCoverage = navQuery.data?.data_coverage ?? null;
	const navOverlay = useMemo<CockpitOverlay | null>(() => {
		if (!isEtf || !toggles.nav || navPoints.length === 0) return null;
		return {
			id: "etf-nav",
			color: "var(--chart-combo-manual)",
			label: "净值",
			format: (value: number) => value.toFixed(4),
			lineWidth: 2,
			points: navPoints.map((point: { nav_date: string; nav: number }) => ({
				time: tradeDateToUnix(point.nav_date),
				close: point.nav,
				volume: null,
			})),
		};
	}, [isEtf, navPoints, toggles.nav]);
	const navUnavailable = isEtf && toggles.nav && !navQuery.isLoading && navPoints.length === 0;
	const navUnavailableTitle = navCoverage
		? `本地净值库覆盖 ${navCoverage.measured_start ?? "?"} ~ ${navCoverage.measured_end ?? "?"}（${navCoverage.status}；${navCoverage.gaps.join("；") || "无缺口说明"}；测量时点 ${navCoverage.measured_at}）`
		: "本地净值库无该标的数据（etf_nav 摄取未覆盖）";
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
					{/* 身份串（snapshot:...:sha256:...）不可在右缘切半：break-all
					    安全换行，完整身份始终可见可下钻（视觉门 V2）。 */}
					<div className="max-w-lg break-all text-right text-xs leading-5 text-(--color-foreground-tertiary)">
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
						{/* 定位标的与日期后可返回源运行：跨域跳转合同的回程入口。
						    runId 缺失（旧链接未携带来源）时不虚构返回目标。 */}
						{drill.runId.trim() ? (
							<a
								href={`/research/backtests/${encodeURIComponent(drill.runId)}`}
								className="font-medium text-(--color-accent) underline underline-offset-2 hover:text-(--brand-accent-hover) focus-visible:outline-2 focus-visible:outline-offset-2"
							>
								返回回测 {drill.runId}
							</a>
						) : null}
					</div>
				)}

				{anchoredEndDate && (
					<div
						data-state="observe-anchor"
						data-testid={`observe-anchor-${id}`}
						className="flex flex-wrap items-center gap-x-4 gap-y-1 border-b border-(--color-border-subtle) px-3 py-2 text-xs"
					>
						<span className="font-medium text-(--color-foreground)">观察日锚定</span>
						<span className="font-data text-(--color-foreground-secondary)">{anchoredEndDate}</span>
						<span className="text-(--color-foreground-muted)">
							来自观察面（自选/筛选）的同一交易日；
							{endDate === anchoredEndDate
								? "K 线截至该日，知识截止仍为服务端当前时钟"
								: "截至日期已手动覆盖，知识截止仍为服务端当前时钟"}
						</span>
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
							title={navUnavailableTitle}
						>
							净值数据不可得
							{navCoverage?.measured_end ? `（库内至 ${navCoverage.measured_end}）` : ""}
						</span>
					)}
					{overlayShown && (
						// 导出范围说明（P4 裁决）：叠加线/净值线只在图上，不入 CSV——
						// 不是"线没画出来"或来源缺失；线本身的身份见图例与覆盖说明。
						<span className="text-xs text-(--color-foreground-muted)">
							CSV 导出仅含 K 线；叠加线（MA/轨道/净值）不入导出，身份见图例
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
							<span className="inline-flex items-center gap-1.5 whitespace-nowrap text-xs text-(--color-foreground-tertiary)">
								<StaleIndicator isStale />
								最新价格日 {query.data?.latest_price_date ?? "—"} ·{" "}
								{query.data?.stale_reason === "missing_expected_session" ? "交易日价格缺失" : "当前没有可见价格"}
							</span>
						)}
						{missingSessions.length > 0 && (
							// 长缺口（数百日）收敛为摘要行：默认折叠，主图优先；
							// 展开后仍是完整逐日清单，不删证据
							<details
								className="text-xs text-(--color-foreground-muted)"
								data-testid={`chart-gaps-${id}`}
								data-state="bars-partial"
							>
								<summary className="cursor-pointer list-none underline underline-offset-2 focus-visible:outline-2 focus-visible:outline-offset-2">
									缺失交易日 {missingSessions.length} 天（展开查看）
								</summary>
								<span className="tabular-nums break-words">{missingSessions.join("、")}</span>
							</details>
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
							// as_of 是服务端决策时钟，不是数据观测新鲜度；
							// 陈旧状态由外层面板按 stale_reason 表达。
							asOfIsDecisionClock
							showVolumePane
							height={360}
							identity={{
								// P4（issue 628）：叠加限制随身份进导出——NAV 不入 CSV，
								// 其覆盖限制（状态/库尾/测量时点）随 dataSourceName 携带。
								dataSourceName: `K线 ${query.data?.sources.join(", ") ?? ""}${overlayShown ? "；叠加线不入 CSV 导出" : ""}${isEtf && toggles.nav ? `；etf_nav ${navCoverage ? `${navCoverage.status}(库内至 ${navCoverage.measured_end ?? "?"}, 测量 ${navCoverage.measured_at})` : "覆盖未知"}` : ""}`,
								// Exports carry the actual chart cutoff: the bars
								// always come from the server's current decision
								// clock, so a drill timestamp would claim a
								// historical as_of for current-cutoff data.
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
