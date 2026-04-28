import { createFileRoute } from "@tanstack/react-router";
import { StatusDot } from "@/components/status";
import { StatusBadge } from "@/components/status";
import { Sparkline } from "@/components/data";
import { Metric } from "@/components/data";
import { LoadingSkeleton } from "@/components/data";
import { ErrorState, DittoErrorBoundary } from "@/lib/error-boundary";
import { StaleIndicator } from "@/lib/stale-indicator";

export const Route = createFileRoute("/showcase")({
	component: ShowcasePage,
	staticData: { title: "组件展示" },
});

const STATUS_VARIANTS = [
	"healthy",
	"degraded",
	"warning",
	"critical",
	"live",
	"idle",
	"error",
	"info",
] as const;

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

function Section({ title, children }: { readonly title: string; readonly children: React.ReactNode }) {
	return (
		<section className="mb-8">
			<h2 className="mb-4 text-[var(--text-lg)] font-semibold text-[var(--color-foreground)]">
				{title}
			</h2>
			{children}
		</section>
	);
}

function ShowcasePage() {
	return (
		<div className="mx-auto max-w-4xl space-y-6 p-6">
			<StaleIndicator isStale />

			<h1 className="text-[var(--text-2xl)] font-bold text-[var(--color-foreground)]">
				Phase 1 共享组件展示
			</h1>

			{/* StatusDot */}
			<Section title="StatusDot 状态指示灯">
				<div className="space-y-3">
					<div className="flex items-center gap-4">
						{STATUS_VARIANTS.map((v) => (
							<div key={v} className="flex flex-col items-center gap-1">
								<StatusDot variant={v} size="sm" />
								<StatusDot variant={v} size="md" />
								<StatusDot variant={v} size="lg" />
								<span className="text-[var(--text-xs)] text-[var(--color-foreground-muted)]">
									{v}
								</span>
							</div>
						))}
					</div>
					<div className="flex items-center gap-4">
						<span className="text-[var(--text-xs)] text-[var(--color-foreground-muted)]">
							live + pulse:
						</span>
						<StatusDot variant="live" pulse />
						<StatusDot variant="healthy" pulse />
						<span className="text-[var(--text-xs)] text-[var(--color-foreground-muted)]">
							(non-live ignores pulse)
						</span>
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
					<span className="text-[var(--text-xs)] text-[var(--color-foreground-muted)] leading-5">
						(sm size)
					</span>
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

			{/* Metric */}
			<Section title="Metric KPI 指标">
				<div className="grid grid-cols-3 gap-4">
					<Metric label="总收益率" value={0.1234} trend="up" size="md" variant="standard" />
					<Metric label="最大回撤" value={-0.0567} trend="down" size="md" variant="standard" />
					<Metric label="夏普比率" value={1.82} trend="flat" size="md" variant="standard" />
				</div>
				<div className="mt-4 grid grid-cols-3 gap-4">
					<Metric
						label="沪深 300"
						value={3842.56}
						trend="up"
						size="md"
						variant="strip"
						sparkline={SPARKLINE_DATA_UP}
					/>
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
					<Metric
						label="贵州茅台"
						value={1688.00}
						trend="up"
						size="lg"
						variant="equity"
						sub={["+2.34%", "+38.50"]}
					/>
					<Metric
						label="宁德时代"
						value={215.60}
						trend="down"
						size="lg"
						variant="equity"
						sub={["-1.28%", "-2.80"]}
					/>
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
						<ErrorState
							title="加载失败"
							description="网络连接超时，请检查网络后重试"
							onRetry={() => {
								window.console.log("retry clicked");
							}}
						/>
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
