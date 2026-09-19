import { createFileRoute } from "@tanstack/react-router";
import { ChartCockpit, type CockpitSeriesSpec } from "@/components/chart";
import { LoadingSkeleton, Metric, Sparkline } from "@/components/data";
import { StatusBadge, StatusDot } from "@/components/status";
import { DittoErrorBoundary, ErrorState } from "@/lib/error-boundary";
import { StaleIndicator } from "@/lib/stale-indicator";

export const Route = createFileRoute("/showcase")({
	component: ShowcasePage,
	staticData: { title: "组件展示" },
});

const STATUS_VARIANTS = ["healthy", "degraded", "warning", "critical", "live", "idle", "error", "info"] as const;

const BADGE_VARIANTS = [
	"default",
	"healthy",
	"degraded",
	"warning",
	"critical",
	"live",
	"idle",
	"error",
	"trade",
	"risk",
	"research",
	"platform",
	"data",
	"priority",
	"regime-on",
	"regime-off",
	"regime-mixed",
	"active",
	"inactive",
] as const;

const SPARKLINE_DATA_UP = [20, 25, 22, 30, 28, 35, 32, 40, 38, 45];
const SPARKLINE_DATA_DOWN = [45, 40, 38, 35, 32, 30, 28, 25, 22, 20];
const SPARKLINE_DATA_FLAT = [30, 32, 28, 31, 29, 30, 32, 28, 31, 30];

/* ── Chart Cockpit fixtures（固定数据，无网络）── */

const DAY_SECONDS = 86_400;
/** 固定日历：2026-06-01 起 95 个交易日（跳过周末），索引 40–45 挖空演示断口。 */
const DAILY_TRADE_TIMES: number[] = (() => {
	const times: number[] = [];
	let day = Date.UTC(2026, 5, 1) / 1000;
	while (times.length < 95) {
		const weekday = new Date(day * 1000).getUTCDay();
		if (weekday !== 0 && weekday !== 6) {
			times.push(day);
		}
		day += DAY_SECONDS;
	}
	return times;
})();

function dailyClose(index: number): number {
	return Number((100 + 8 * Math.sin(index / 9) + 0.15 * index + ((index * index) % 7) * 0.2).toFixed(2));
}

const DAILY_BARS = DAILY_TRADE_TIMES.map((time, index) => {
	const missing = index >= 40 && index <= 45;
	const close = dailyClose(index);
	const previous = index > 0 ? dailyClose(index - 1) : close;
	return {
		time,
		close: missing ? null : close,
		volume: missing ? null : 8_000 + ((index * 37) % 23) * 400 + (close >= previous ? 1_500 : 0),
	};
});

const DAILY_AS_OF = DAILY_TRADE_TIMES[70] ?? 0;
const DAILY_SERIES: CockpitSeriesSpec[] = [{ id: "close", bars: DAILY_BARS, color: "var(--chart-combo-model)" }];

/** 新鲜度时变 fixture：锚定页面加载时刻，覆盖 live→expired 五档 + 一处断口。 */
const FRESHNESS_NOW_MS = Date.now();
// 年龄（分钟）：expired(≥30) / stale(5–30) / aging(0.5–5) / recent(5s–30s≈0.083–0.5) / live(<5s≈0.083)
const FRESHNESS_AGES_MINUTES = [180, 170, 160, 50, 45, 40, 20, 15, 10, 1, 0.4, 0.2, 0.05];
const FRESHNESS_SERIES: CockpitSeriesSpec[] = [
	{
		id: "rt-price",
		color: "var(--chart-run-1)",
		bars: FRESHNESS_AGES_MINUTES.map((minutes, index) => {
			const time = Math.floor((FRESHNESS_NOW_MS - minutes * 60_000) / 1000);
			const value = Number((42 + 3 * Math.sin(index / 2.5) + (index % 3) * 0.4).toFixed(2));
			const missing = minutes === 40;
			return { time, close: missing ? null : value, volume: null };
		}),
	},
];

const COMBO_SWATCHES = [
	["Model", "bg-[var(--chart-combo-model)]"],
	["Paper", "bg-[var(--chart-combo-paper)]"],
	["Manual", "bg-[var(--chart-combo-manual)]"],
] as const;
const RUN_SWATCHES = [
	["run-1", "bg-[var(--chart-run-1)]"],
	["run-2", "bg-[var(--chart-run-2)]"],
	["run-3", "bg-[var(--chart-run-3)]"],
	["run-4", "bg-[var(--chart-run-4)]"],
	["run-5", "bg-[var(--chart-run-5)]"],
	["run-6", "bg-[var(--chart-run-6)]"],
	["run-7", "bg-[var(--chart-run-7)]"],
	["run-8", "bg-[var(--chart-run-8)]"],
] as const;
const QUANTILE_SWATCHES = [
	["Q1", "bg-[var(--chart-quantile-1)]"],
	["Q2", "bg-[var(--chart-quantile-2)]"],
	["Q3", "bg-[var(--chart-quantile-3)]"],
	["Q4", "bg-[var(--chart-quantile-4)]"],
	["Q5", "bg-[var(--chart-quantile-5)]"],
] as const;

function Section({ title, children }: { readonly title: string; readonly children: React.ReactNode }) {
	return (
		<section className="mb-8">
			<h2 className="mb-4 text-[var(--text-lg)] font-semibold text-[var(--color-foreground)]">{title}</h2>
			{children}
		</section>
	);
}

function SwatchRow({
	label,
	swatches,
}: {
	readonly label: string;
	readonly swatches: ReadonlyArray<readonly [label: string, className: string]>;
}) {
	return (
		<div className="flex flex-wrap items-center gap-3">
			<span className="w-20 text-[var(--text-xs)] text-[var(--color-foreground-muted)]">{label}</span>
			{swatches.map(([name, className]) => (
				<span key={name} className="inline-flex items-center gap-1.5 text-[var(--text-xs)]">
					<span aria-hidden="true" className={`inline-block size-3 rounded-sm ${className}`} />
					{name}
				</span>
			))}
		</div>
	);
}

function ShowcasePage() {
	return (
		<div className="mx-auto max-w-4xl space-y-6 p-6">
			<StaleIndicator isStale />

			<h1 className="text-[var(--text-2xl)] font-bold text-[var(--color-foreground)]">Phase 1 共享组件展示</h1>

			{/* StatusDot */}
			<Section title="StatusDot 状态指示灯">
				<div className="space-y-3">
					<div className="flex items-center gap-4">
						{STATUS_VARIANTS.map((v) => (
							<div key={v} className="flex flex-col items-center gap-1">
								<StatusDot variant={v} size="sm" />
								<StatusDot variant={v} size="md" />
								<StatusDot variant={v} size="lg" />
								<span className="text-[var(--text-xs)] text-[var(--color-foreground-muted)]">{v}</span>
							</div>
						))}
					</div>
					<div className="flex items-center gap-4">
						<span className="text-[var(--text-xs)] text-[var(--color-foreground-muted)]">live + pulse:</span>
						<StatusDot variant="live" pulse />
						<StatusDot variant="healthy" pulse />
						<span className="text-[var(--text-xs)] text-[var(--color-foreground-muted)]">(non-live ignores pulse)</span>
					</div>
				</div>
			</Section>

			{/* StatusBadge */}
			<Section title="StatusBadge 状态标签">
				<div className="flex flex-wrap gap-2">
					{BADGE_VARIANTS.map((v) => (
						<StatusBadge key={v} variant={v} label={v} size="md" />
					))}
				</div>
				<div className="mt-3 flex flex-wrap gap-2">
					{(["healthy", "error", "live", "trade"] as const).map((v) => (
						<StatusBadge key={v} variant={v} label={v} size="sm" />
					))}
					<span className="text-[var(--text-xs)] text-[var(--color-foreground-muted)] leading-5">(sm size)</span>
				</div>
			</Section>

			{/* Sparkline */}
			<Section title="Sparkline 迷你折线图">
				<div className="flex items-end gap-6">
					<div className="flex flex-col items-center gap-1">
						<Sparkline data={SPARKLINE_DATA_UP} color="up" gradient />
						<span className="text-[var(--text-xs)] text-[var(--color-foreground-muted)]">up + gradient</span>
					</div>
					<div className="flex flex-col items-center gap-1">
						<Sparkline data={SPARKLINE_DATA_DOWN} color="down" gradient />
						<span className="text-[var(--text-xs)] text-[var(--color-foreground-muted)]">down + gradient</span>
					</div>
					<div className="flex flex-col items-center gap-1">
						<Sparkline data={SPARKLINE_DATA_FLAT} color="neutral" />
						<span className="text-[var(--text-xs)] text-[var(--color-foreground-muted)]">neutral (no gradient)</span>
					</div>
					<div className="flex flex-col items-center gap-1">
						<Sparkline data={SPARKLINE_DATA_UP} color="up" animate gradient />
						<span className="text-[var(--text-xs)] text-[var(--color-foreground-muted)]">up + animate</span>
					</div>
					<div className="flex flex-col items-center gap-1">
						<Sparkline data={[]} color="neutral" />
						<span className="text-[var(--text-xs)] text-[var(--color-foreground-muted)]">empty</span>
					</div>
					<div className="flex flex-col items-center gap-1">
						<Sparkline data={[42]} color="neutral" />
						<span className="text-[var(--text-xs)] text-[var(--color-foreground-muted)]">single</span>
					</div>
				</div>
			</Section>

			{/* Chart Cockpit tokens */}
			<Section title="Chart Cockpit chart.* 语义色板（双主题 WCAG AA）">
				<div className="space-y-2">
					<SwatchRow label="三组合" swatches={COMBO_SWATCHES} />
					<SwatchRow label="8 色 run" swatches={RUN_SWATCHES} />
					<SwatchRow label="Q1–Q5 色带" swatches={QUANTILE_SWATCHES} />
					<div className="flex flex-wrap items-center gap-3">
						<span className="w-20 text-[var(--text-xs)] text-[var(--color-foreground-muted)]" />
						<span className="inline-flex items-center gap-1.5 text-[var(--text-xs)]">
							<span aria-hidden="true" className="inline-block size-3 rounded-sm bg-[var(--chart-ls-spread)]" />
							LS spread
						</span>
					</div>
				</div>
			</Section>

			{/* Chart Cockpit core shell */}
			<Section title="Chart Cockpit 核心 shell（收盘价线图 + 量副图）">
				<ChartCockpit
					chartId="showcase-daily-close"
					rangeId="showcase-daily"
					ariaLabel="演示：日收盘价线图（fixture，含 6 个交易日缺失断口与 as_of 水位线）"
					series={DAILY_SERIES}
					showVolumePane
					asOf={{ time: DAILY_AS_OF }}
					identity={{
						dataSourceName: "tushare (showcase fixture)",
						snapshotId: "snap-a3f5c90e1b2d47f8a6e0c3d5918f2b74d6a8e1f0c2b4d6e8f0a1b3c5d7e9f24",
						knowledgeCutoff: "2026-09-10T00:00:00Z",
					}}
					height={300}
					exportName="showcase-daily-close"
				/>
				<p className="mt-2 text-[var(--text-xs)] text-[var(--color-foreground-muted)]">
					断口（索引 40–45 交易日缺失）不插值；as_of 水位线右侧为未知区域；量副图涨跌着色（红涨绿跌）。
				</p>
			</Section>

			<Section title="Chart Cockpit 新鲜度透明度时变（live 1.0 → expired 0.25）">
				<ChartCockpit
					chartId="showcase-freshness"
					rangeId="showcase-freshness"
					ariaLabel="演示：实时序列新鲜度透明度时变（fixture，随页面加载时刻锚定）"
					series={FRESHNESS_SERIES}
					freshnessFade
					timeVisible
					identity={{ dataSourceName: "showcase fixture" }}
					height={200}
					exportName="showcase-freshness"
				/>
				<p className="mt-2 text-[var(--text-xs)] text-[var(--color-foreground-muted)]">
					透明度随数据年龄衰减：live &gt; recent &gt; aging &gt; stale &gt; expired；40 分钟处有一处断口。
				</p>
			</Section>

			{/* Metric */}
			<Section title="Metric KPI 指标">
				<div className="grid grid-cols-3 gap-4">
					<Metric label="总收益率" value={0.1234} trend="up" size="md" variant="standard" />
					<Metric label="最大回撤" value={-0.0567} trend="down" size="md" variant="standard" />
					<Metric label="夏普比率" value={1.82} trend="flat" size="md" variant="standard" />
				</div>
				<div className="mt-4 grid grid-cols-3 gap-4">
					<Metric label="沪深 300" value={3842.56} trend="up" size="md" variant="strip" sparkline={SPARKLINE_DATA_UP} />
					<Metric
						label="中证 500"
						value={5210.33}
						trend="down"
						size="md"
						variant="strip"
						sparkline={SPARKLINE_DATA_DOWN}
					/>
					<Metric label="波动率" value="12.5%" size="sm" variant="strip" />
				</div>
				<div className="mt-4 grid grid-cols-2 gap-4">
					<Metric label="贵州茅台" value={1688.0} trend="up" size="lg" variant="equity" sub={["+2.34%", "+38.50"]} />
					<Metric label="宁德时代" value={215.6} trend="down" size="lg" variant="equity" sub={["-1.28%", "-2.80"]} />
				</div>
			</Section>

			{/* LoadingSkeleton */}
			<Section title="LoadingSkeleton 骨架屏">
				<div className="space-y-4">
					<LoadingSkeleton variant="panel" rows={3} />
					<LoadingSkeleton variant="table" columns={4} rows={3} />
					<div className="grid grid-cols-2 gap-4">
						<LoadingSkeleton variant="card" />
						<LoadingSkeleton variant="card" />
					</div>
					<div className="grid grid-cols-3 gap-4">
						<LoadingSkeleton variant="metric" />
						<LoadingSkeleton variant="metric" />
						<LoadingSkeleton variant="metric" />
					</div>
					<LoadingSkeleton variant="chart" />
				</div>
			</Section>

			{/* ErrorState + StaleIndicator */}
			<Section title="ErrorState + StaleIndicator">
				<div className="grid grid-cols-2 gap-4">
					<div className="rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface-1)] p-4">
						<ErrorState title="加载失败" description="网络连接超时，请检查网络后重试" onRetry={() => undefined} />
					</div>
					<div className="rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface-1)] p-4">
						<ErrorState title="数据过期" description="最近更新：3 分钟前" />
					</div>
				</div>
				<div className="mt-4 space-y-2">
					<p className="text-[var(--text-xs)] text-[var(--color-foreground-muted)]">StaleIndicator (isStale=true):</p>
					<StaleIndicator isStale />
					<p className="text-[var(--text-xs)] text-[var(--color-foreground-muted)]">StaleIndicator (isStale=false):</p>
					<StaleIndicator isStale={false} />
				</div>
			</Section>

			{/* DittoErrorBoundary */}
			<Section title="DittoErrorBoundary">
				<div className="rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface-1)] p-4">
					<DittoErrorBoundary fallbackProps={{ title: "组件异常", description: "请刷新页面重试" }}>
						<p className="text-[var(--text-sm)] text-[var(--color-foreground-secondary)]">
							正常渲染的内容（ErrorBoundary 包裹区域）
						</p>
					</DittoErrorBoundary>
				</div>
			</Section>
		</div>
	);
}
